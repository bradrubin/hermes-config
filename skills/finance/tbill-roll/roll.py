#!/usr/bin/env python3
"""tbill-roll: find the T-bills that replaced auto-rolled (AR) bills in the Treasuries sheet.

One call does everything:
  1. read Treasuries!A:F with the Google Workspace skill's google_api.py
  2. pick AR rows that matured recently (or will mature soon) and have no replacement row yet
  3. download recent bill auctions from TreasuryDirect (fallback: Fiscal Data)
  4. match: issue date == old maturity, same term in weeks; chain if the replacement also matured
  5. write a tab-separated file of new rows (columns A-Q, formulas for rows 2..N+1)
Always prints a complete REPLY START / REPLY END block, also on failure.
"""
import csv, datetime as dt, glob, json, os, re, subprocess, sys, time, urllib.request

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
ATTACH_DIR = "/Users/hermes/.hermes/attachments"
WORK_DIR = os.path.join(SKILL_DIR, "work")
FEDINVEST = "https://www.treasurydirect.gov/GA-FI/FedInvest/todaySecurityPriceDate.htm"
TA_WS = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type=Bill&days={days}"
FISCAL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/"
          "auctions_query?filter=security_type:eq:Bill,issue_date:gte:{since}&page%5Bsize%5D=10000")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) tbill-roll/1.0"


class Stop(Exception):
    pass


T0 = time.time()
MARKS = []
PHASES = ("sheet", "treasury", "write")
WINDOW_DAYS = 6   # maturity within this many days: the window to add to an auto-roll position is open


def mark(phase):
    MARKS.append((phase, time.time()))


def timing_line():
    parts, prev = [], T0
    for name, t in MARKS:
        parts.append(f"{name} {t - prev:.1f}s")
        prev = t
    total = (MARKS[-1][1] if MARKS else time.time()) - T0
    try:
        hist = os.path.join(SKILL_DIR, "timing_history.csv")
        new = not os.path.exists(hist)
        done, prev = {}, T0
        for name, t in MARKS:
            done[name] = f"{t - prev:.1f}"
            prev = t
        with open(hist, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["run_at", "total_s"] + [p + "_s" for p in PHASES])
            w.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), f"{total:.1f}"]
                       + [done.get(p, "") for p in PHASES])
    except OSError:
        pass
    return f"TIMING: total {total:.1f}s ({', '.join(parts)})" if parts else f"TIMING: total {total:.1f}s"


# ---------------- settings ----------------
def read_kv(path):
    d = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
    except OSError:
        pass
    return d


def settings():
    path = os.path.join(SKILL_DIR, "settings.txt")
    if not os.path.exists(path):
        raise Stop(f"settings.txt is missing from {SKILL_DIR}")
    cfg = read_kv(path)
    if not cfg.get("sheet_id"):
        raise Stop("settings.txt has no sheet_id")
    # Reuse tpaw-load's Google settings when ours are blank.
    tp = read_kv(os.path.expanduser("~/.hermes/skills/finance/tpaw-load/balance_source.txt"))
    for k in ("google_api", "python"):
        if not cfg.get(k) and tp.get(k):
            cfg[k] = tp[k]
    cfg.setdefault("sheet", "Treasuries")
    cfg["sheet"] = cfg["sheet"] or "Treasuries"
    try:
        cfg["lookback_days"] = int(cfg.get("lookback_days") or 60)
    except ValueError:
        raise Stop("lookback_days in settings.txt must be a whole number")
    return cfg


def find_google_api(cfg):
    p = os.path.expanduser(cfg.get("google_api") or "")
    if p and os.path.isfile(p):
        return p
    hits = sorted(glob.glob(os.path.expanduser("~/.hermes/skills/**/google_api.py"), recursive=True))
    if not hits:
        raise Stop("couldn't find the Google Workspace skill's google_api.py "
                   "(set google_api = <path> in settings.txt)")
    return hits[0]


# ---------------- sheet ----------------
def find_rows(d):
    """The list of rows in whatever google_api.py printed."""
    if isinstance(d, dict):
        for k in ("values", "result", "data", "valueRanges"):
            if k in d:
                r = find_rows(d[k])
                if r is not None:
                    return r
        return None
    if isinstance(d, list):
        if all(isinstance(x, list) for x in d):
            return d
        for x in d:
            r = find_rows(x)
            if r is not None:
                return r
    return None


def parse_date(s):
    if s is None:
        return None
    if isinstance(s, (int, float)) and not isinstance(s, bool):   # Sheets serial number
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(s)) if 20000 < s < 80000 else None
    s = str(s).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        return parse_date(float(s))
    s = s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else s
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_num(s):
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return s
    m = re.search(r"-?\d[\d,]*(\.\d+)?", str(s or ""))
    return float(m.group(0).replace(",", "")) if m else None


def python_candidates(cfg, tool):
    """Interpreters to try for google_api.py, best guesses first. It needs Python 3.11+
    (datetime.UTC) plus the Google libraries; macOS's /usr/bin/python3 is 3.9."""
    home = os.path.expanduser("~")
    c = []
    if cfg.get("python"):
        c.append(os.path.expanduser(cfg["python"]))
    d = os.path.dirname(tool)
    for _ in range(6):   # a venv next to (or above) the Google skill
        for v in ("venv", ".venv", "env"):
            c.append(os.path.join(d, v, "bin", "python3"))
        d = os.path.dirname(d)
    for pat in ("~/.hermes/*/bin/python3", "~/.hermes/*/*/bin/python3", "~/.hermes/*/*/*/bin/python3",
                "~/.local/share/*/venv/bin/python3", "~/.local/bin/python3*"):
        c += sorted(glob.glob(os.path.expanduser(pat)))
    c.append(sys.executable)
    for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python"):
        for d in ("/opt/homebrew/bin", "/usr/local/bin", os.path.join(home, ".local", "bin")):
            c.append(os.path.join(d, name))
        c.append(name)
    seen, out = set(), []
    for p in c:
        if p not in seen and (os.sep not in p or os.path.isfile(p)):
            seen.add(p)
            out.append(p)
    return out


def read_sheet(cfg):
    tool = find_google_api(cfg)
    rng = f"{cfg['sheet']}!A1:F"
    last = "no Python found"
    for py in python_candidates(cfg, tool):
        try:
            r = subprocess.run([py, tool, "sheets", "get", cfg["sheet_id"], rng], capture_output=True,
                               text=True, timeout=60, cwd=os.path.dirname(tool))
        except Exception as e:
            last = f"{py}: {type(e).__name__}"
            continue
        out = (r.stdout or "").strip()
        if r.returncode == 0:
            break
        err = ((r.stderr or out).strip().splitlines() or ["no output"])[-1]
        if re.search(r"ImportError|ModuleNotFoundError|SyntaxError|No module named", err):
            last = f"{py}: {err[:120]}"   # wrong interpreter: try the next one
            continue
        raise Stop(f"Google Sheets read failed: {err[:200]}")
    else:
        raise Stop("no Python could run google_api.py (it needs 3.11+ with the Google libraries; "
                   f"set python = <path> in settings.txt). Last error: {last}")
    try:
        data = json.loads(out)
    except ValueError:
        raise Stop(f"Google Sheets read returned something that isn't JSON: {out[:120]}")
    raw = find_rows(data)
    if not raw:
        raise Stop(f"the Google Sheet range {rng} came back empty")
    head = [str(x).strip().lower() for x in raw[0]] + [""] * 6
    if head[0] != "fund" or head[1] != "cusip":
        raise Stop(f"row 1 of {cfg['sheet']} doesn't start with Fund, CUSIP (got {raw[0][:2]})")
    rows = []
    for i, r in enumerate(raw[1:], start=2):
        r = list(r) + [""] * (6 - len(r))
        fund = str(r[0]).strip()
        if not fund and not str(r[1]).strip():
            continue
        rows.append({"row": i, "fund": fund, "cusip": str(r[1]).strip().upper(),
                     "settle": parse_date(r[2]), "maturity": parse_date(r[3]),
                     "weeks": parse_num(r[4]), "qty": parse_num(r[5])})
    return rows


# ---------------- Treasury auctions ----------------
def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "null"):
            return v
    return None


def normalize(rec):
    issue = parse_date(pick(rec, "issueDate", "issue_date"))
    mat = parse_date(pick(rec, "maturityDate", "maturity_date"))
    high = parse_num(pick(rec, "highDiscountRate", "high_discnt_rate"))
    inv = parse_num(pick(rec, "highInvestmentRate", "high_investment_rate"))
    cusip = str(pick(rec, "cusip") or "").strip().upper()
    if not (issue and mat and cusip and high is not None and inv is not None):
        return None
    term = str(pick(rec, "securityTerm", "security_term") or "")
    cmb = str(pick(rec, "cashManagementBillCMB", "cash_management_bill_cmb") or "").lower()
    m = re.match(r"(\d+)\s*-?\s*week", term.lower())
    return {"cusip": cusip, "issue": issue, "maturity": mat, "high": float(high), "inv": float(inv),
            "term_weeks": int(m.group(1)) if m else None, "term": term, "cmb": cmb in ("yes", "true", "y"),
            "auction": parse_date(pick(rec, "auctionDate", "auction_date"))}


def load_auctions(since, today):
    days = max(14, (today - since).days + 10)
    errors = []
    sources = [("TreasuryDirect", TA_WS.format(days=days)),
               ("Fiscal Data", FISCAL.format(since=(since - dt.timedelta(days=7)).isoformat()))]
    for name, url in sources:
        try:
            data = fetch_json(url)
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:80]}")
            continue
        recs = data.get("data", []) if isinstance(data, dict) else data
        out = [n for n in (normalize(r) for r in recs if isinstance(r, dict)) if n]
        return out, name, len(recs)
    raise Stop("couldn't download auction results (" + "; ".join(errors) + ")")


def find_replacement(auctions, maturity, weeks):
    cands = [a for a in auctions if a["issue"] == maturity and not a["cmb"]
             and abs((a["maturity"] - a["issue"]).days - weeks * 7) <= 3]
    exact = [a for a in cands if a["term_weeks"] == weeks]
    cands = exact or cands
    uniq = {a["cusip"]: a for a in cands}
    if len(uniq) > 1:
        raise Stop(f"more than one {weeks}-week bill was issued {fmt_date(maturity)}: "
                   + ", ".join(sorted(uniq)))
    return next(iter(uniq.values()), None)


# ---------------- output ----------------
def fmt_date(d):
    return f"{d.month}/{d.day}/{d.year}"


def fmt_qty(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def tsv_row(r, n):
    k = (f'=IF(TODAY()>=D{n},100,IFNA(VLOOKUP(B{n},IMPORTHTML("{FEDINVEST}","table",1),7,FALSE),J{n}))')
    cells = [r["fund"], r["cusip"], fmt_date(r["settle"]), fmt_date(r["maturity"]), fmt_qty(r["weeks"]),
             fmt_qty(r["qty"]), f"{r['high']:.3f}%", f"{r['inv']:.3f}%",
             f"=TBILLPRICE(C{n},D{n},G{n})",
             f"=IF(TODAY()>=D{n},100, PRICEDISC(TODAY(),D{n},G{n},100,1))",
             k, f"=F{n}*I{n}", f"=K{n}*F{n}", f"=M{n}-L{n}",
             f'=IF(TODAY()>=D{n},"Matured", YIELDDISC(TODAY(),D{n},K{n},100,1))',
             f"=(100-I{n})*360/(D{n}-C{n})/100",
             f"=(100-I{n})*(EDATE(C{n},12)-C{n})/(D{n}-C{n})/I{n}"]
    return "\t".join(c.replace("\t", " ").replace("\n", " ") for c in cells)


def write_tsv(new_rows):
    os.makedirs(ATTACH_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    n = 1
    while True:
        path = f"{ATTACH_DIR}/tbill_rows_{stamp}_{n}.tsv"
        try:
            f = open(path, "x", newline="")
            break
        except FileExistsError:
            n += 1
    with f:
        for i, r in enumerate(new_rows):
            f.write(tsv_row(r, i + 2) + "\n")
    return path


# ---------------- main ----------------
def run(today):
    cfg = settings()
    rows = read_sheet(cfg)
    mark("sheet")

    def has_row(fund, cusip, settle):
        return any(x["fund"] == fund and x["settle"] == settle and (not cusip or x["cusip"] == cusip)
                   for x in rows)

    lo = today - dt.timedelta(days=cfg["lookback_days"])
    todo = [r for r in rows if "(AR)" in r["fund"].upper() and r["maturity"] and r["settle"]
            and r["weeks"] and r["qty"] and lo <= r["maturity"] <= today + dt.timedelta(days=7)
            and not has_row(r["fund"], None, r["maturity"])]
    debug = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "today": today.isoformat(),
             "sheet_rows": len(rows), "candidates": [], "new_rows": [], "source": None}
    new_rows, warnings, upcoming = [], [], []
    if todo:
        auctions, source, nrec = load_auctions(min(r["maturity"] for r in todo), today)
        debug["source"] = f"{source} ({nrec} records, {len(auctions)} with results)"
        mark("treasury")
        for r in todo:
            cur, steps = r, 0
            debug["candidates"].append({k: str(v) for k, v in r.items()})
            while steps < 20:
                rep = find_replacement(auctions, cur["maturity"], int(cur["weeks"]))
                if not rep:
                    if cur["maturity"] <= today:
                        warnings.append(f"No auction result found for the {int(cur['weeks'])}-week bill that "
                                        f"replaced {cur['cusip']} ({cur['fund']}, matured "
                                        f"{fmt_date(cur['maturity'])}). Check Fidelity.")
                    else:
                        upcoming.append(cur)
                    break
                if has_row(cur["fund"], rep["cusip"], rep["issue"]):
                    break
                new = {"fund": cur["fund"], "cusip": rep["cusip"], "settle": rep["issue"],
                       "maturity": rep["maturity"], "weeks": cur["weeks"], "qty": cur["qty"],
                       "high": rep["high"], "inv": rep["inv"], "old": cur["cusip"],
                       "old_mat": cur["maturity"]}
                new_rows.append(new)
                cur, steps = new, steps + 1
                if cur["maturity"] > today + dt.timedelta(days=7):
                    break
    else:
        mark("treasury")
    # Next roll that hasn't happened yet (for the reply).
    rolled = {(x["fund"], x["settle"]) for x in new_rows}
    future = [r for r in rows if "(AR)" in r["fund"].upper() and r["maturity"] and r["maturity"] > today
              and not has_row(r["fund"], None, r["maturity"]) and (r["fund"], r["maturity"]) not in rolled]
    future += [x for x in new_rows if x["maturity"] > today and (x["fund"], x["maturity"]) not in rolled]

    new_rows.sort(key=lambda x: (x["settle"], x["fund"]), reverse=True)
    lines, path = [], None
    if new_rows:
        path = write_tsv(new_rows)
        n = len(new_rows)
        lines.append(f"T-bill roll: {n} new row{'s' if n > 1 else ''} for the Treasuries sheet. "
                     f"Insert {n} row{'s' if n > 1 else ''} above row 2, click A2, and paste the attached file.")
        for x in new_rows:
            lines.append(f"{x['fund']}: {x['old']} ({'matured' if x['old_mat'] <= today else 'matures'} {fmt_date(x['old_mat'])}) "
                         f"{'was' if x['old_mat'] <= today else 'will be'} replaced by "
                         f"{x['cusip']}, {fmt_date(x['settle'])} to {fmt_date(x['maturity'])}, "
                         f"quantity {fmt_qty(x['qty'])}, high rate {x['high']:.3f}%, "
                         f"investment rate {x['inv']:.3f}%.")
            debug["new_rows"].append({k: str(v) for k, v in x.items()})
        placeholders = [r for r in rows if not r["settle"] and any(r["cusip"] == x["cusip"] for x in new_rows)]
        for p in placeholders:
            lines.append(f"Row {p['row']} already has {p['cusip']} without dates. Delete it before inserting.")
    else:
        lines.append("T-bill roll: no new rows. Every auto-roll bill that has matured already has its replacement in the sheet.")
    lines += warnings
    window = sorted((x for x in future if (x["maturity"] - today).days <= WINDOW_DAYS),
                    key=lambda x: (x["maturity"], x["fund"]))
    for x in window:
        d = (x["maturity"] - today).days
        lines.append(f"REINVESTMENT WINDOW OPEN: {x['cusip']} ({x['fund']}, quantity {fmt_qty(x['qty'])}) "
                     f"matures {fmt_date(x['maturity'])}, in {d} day{'s' if d != 1 else ''}. "
                     "You can add to this position before it rolls.")
    if future and not window:
        nxt = min(future, key=lambda x: x["maturity"])
        lines.append(f"Next roll: {nxt['cusip']} ({nxt['fund']}) matures {fmt_date(nxt['maturity'])}. "
                     "Its replacement isn't auctioned yet.")
    mark("write")
    try:
        os.makedirs(WORK_DIR, exist_ok=True)
        with open(os.path.join(WORK_DIR, "last_run.json"), "w") as f:
            json.dump(debug, f, indent=1)
    except OSError:
        pass
    return lines, path


def main():
    today = dt.date.today()
    if len(sys.argv) > 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        today = dt.date.fromisoformat(sys.argv[1])   # for testing
    try:
        lines, path = run(today)
    except Stop as e:
        lines, path = [f"T-bill roll failed: {e}"], None
    except Exception as e:
        lines, path = [f"T-bill roll failed: {type(e).__name__}: {str(e)[:200]}"], None
    lines.append(timing_line())
    print("REPLY START")
    print("\n\n".join(lines))
    if path:
        print(f"\nMEDIA:{path}")
    print("REPLY END")


if __name__ == "__main__":
    main()
