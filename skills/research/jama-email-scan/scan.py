#!/usr/bin/env python3
"""JAMA monthly email scan: JMAP fetch, keyword match, index file, REPLY block.
Usage: scan.py <<'ARGS'
month=2026-10; force=1; cron=1
ARGS
month omitted or 'auto': most recent month (up to 12 back) with no index file."""
import os, re, sys, json, time, html, datetime, urllib.request, urllib.error

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = "/Users/hermes/.hermes"
STATE = f"{HOME}/state/jama-email-scan"
OUT_DIR = os.path.expanduser("~/Documents/JAMA")
ATT = f"{HOME}/attachments"
WORK = f"{HERE}/work"
marks = [("start", T0)]


def mark(n):
    marks.append((n, time.time()))


def fmt(s):
    s = int(round(s))
    return f"{s}s" if s < 60 else f"{s // 60}m{s % 60:02d}s"


DEFAULT_TOPICS = {
    "Hormone-Sensitive Breast Cancer": {
        "core": [r"breast.*(hormone|estrogen|endocrine|tamoxifen|aromatase|letrozole|anastrozole|fulvestrant|CDK4|luminal|ER-positive|HR\+|HR-positive)",
                 r"(hormone|estrogen|endocrine|tamoxifen|aromatase|letrozole|anastrozole|fulvestrant|CDK4|luminal|ER-positive|HR\+|HR-positive).*breast"],
        "related": [r"breast (cancer|carcinoma|neoplasm)"]},
    "Prostate Cancer Screening": {
        "core": [r"prostate.*(screen|PSA|prostate-specific|early detection|MRI|biops)",
                 r"(screen|PSA|prostate-specific|early detection).*prostate"],
        "related": [r"prostate"]},
    "General Medical Overviews for Family Medicine": {
        "core": [r"primary care", r"family (medicine|physician)", r"clinical review", r"\boverview\b", r"JAMA Insights"],
        "related": []},
    "Calcium Score and Cardiovascular Risk Assessment": {
        "core": [r"coronary artery calcium", r"calcium score", r"\bCAC\b"],
        "related": [r"coronary calcif"]},
}
HEADERS = {"original investigation", "research letter", "viewpoint", "special communication", "review", "editorial",
           "comment & response", "brief report", "clinical review", "jama insights", "online first", "new issue"}


def load_token():
    t = os.environ.get("FASTMAIL_API_TOKEN")
    if not t:
        try:
            for ln in open(f"{HOME}/.env"):
                if ln.startswith("FASTMAIL_API_TOKEN="):
                    t = ln.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass
    if not t:
        raise RuntimeError("FASTMAIL_API_TOKEN not found in the environment or .env")
    return t


class JMAP:
    def __init__(self, tok):
        self.h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
        s = self._open(urllib.request.Request("https://api.fastmail.com/jmap/session", headers=self.h))
        self.api = s["apiUrl"]
        self.acct = s["primaryAccounts"]["urn:ietf:params:jmap:mail"]

    def _open(self, req):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Fastmail HTTP {e.code} (token lacks JMAP access?)" if e.code in (401, 403) else f"Fastmail HTTP {e.code}")

    def call(self, method, args):
        args = dict(args, accountId=self.acct)
        body = {"using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"], "methodCalls": [[method, args, "a"]]}
        r = self._open(urllib.request.Request(self.api, json.dumps(body).encode(), self.h))
        name, res, _ = r["methodResponses"][0]
        if name == "error":
            raise RuntimeError(f"JMAP {method} error: {res.get('type')}")
        return res


def fetch_month(get_jmap, y, m):
    cache = f"{WORK}/cache/{y}-{m:02d}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 86400:
        return json.load(open(cache))
    j = get_jmap()
    boxes = j.call("Mailbox/get", {"properties": ["name"]})["list"]
    ids = [b["id"] for b in boxes if b["name"].strip().lower() == "jama"]
    if not ids:
        raise RuntimeError("no Fastmail folder named JAMA")
    start = datetime.date(y, m, 1)
    end = datetime.date(y + (m == 12), m % 12 + 1, 1)
    flt = {"inMailbox": ids[0], "after": start.isoformat() + "T00:00:00Z", "before": end.isoformat() + "T00:00:00Z"}
    eids, pos = [], 0
    while True:
        q = j.call("Email/query", {"filter": flt, "sort": [{"property": "receivedAt", "isAscending": False}],
                                   "position": pos, "limit": 200, "calculateTotal": True})
        eids += q["ids"]
        pos += len(q["ids"])
        if not q["ids"] or pos >= q.get("total", pos):
            break
    emails = []
    for i in range(0, len(eids), 20):
        g = j.call("Email/get", {"ids": eids[i:i + 20], "properties": ["subject", "receivedAt", "from", "textBody", "htmlBody", "bodyValues"],
                                 "fetchTextBodyValues": True, "fetchHTMLBodyValues": True, "maxBodyValueBytes": 300000})
        for e in g["list"]:
            bv = e.get("bodyValues", {})
            txt = "\n".join(bv[p["partId"]]["value"] for p in e.get("textBody") or [] if p["partId"] in bv and p.get("type") == "text/plain")
            if len(txt.strip()) < 200:
                h = "\n".join(bv[p["partId"]]["value"] for p in e.get("htmlBody") or [] if p["partId"] in bv)
                h = re.sub(r"(?is)<(script|style).*?</\1>", "", h)
                h = re.sub(r"(?is)<a [^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", r"\2 \1 ", h)
                h = re.sub(r"(?i)</(p|div|tr|h\d|li|table)>|<br\s*/?>", "\n\n", h)
                txt = html.unescape(re.sub(r"<[^>]+>", " ", h))
            emails.append({"subject": e.get("subject", ""), "date": e["receivedAt"],
                           "from": (e.get("from") or [{}])[0].get("name") or "", "text": txt})
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(emails, open(cache, "w"))
    return emails


def blocks(text):
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", text)
    out = []
    for b in re.split(r"\n\s*\n", text):
        lines = [re.sub(r"\s+", " ", l).strip(" *_#>") for l in b.splitlines()]
        lines = [l for l in lines if l]
        if not lines:
            continue
        url = next((u for l in lines for u in re.findall(r"https?://\S+", l)), "")
        words = [re.sub(r"https?://\S+", "", l).strip() for l in lines]
        words = [w for w in words if w]
        if url and not words and out and not out[-1]["url"]:
            out[-1]["url"] = url
            continue
        out.append({"lines": words, "url": url})
    return out


def classify(topics, text):
    hit = []
    for cat, p in topics.items():
        for kind in ("core", "related"):
            ms = [pat for pat in p.get(kind, []) if re.search(pat, text, re.I)]
            if ms:
                hit.append((cat, kind))
                break
    return hit


def scan(emails, topics):
    found = {}
    for e in emails:
        subj = e["subject"]
        low = subj.lower()
        itype = "Online First" if "online first" in low else "Med News" if "news" in low or "news" in e["from"].lower() else "New Issue" if re.search(r"issue|new", low) else "Email"
        d = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        for b in blocks(e["text"]):
            body = [l for l in b["lines"] if l.lower() not in HEADERS]
            if not body or len(body[0]) < 15 or len(body[0]) > 400:
                continue
            hits = classify(topics, " ".join(b["lines"]))
            if not hits:
                continue
            key = re.sub(r"\W+", "", body[0].lower())
            ent = found.setdefault(key, {"title": body[0], "journal": e["from"] or "JAMA", "date": d, "type": itype, "url": b["url"], "hits": {}})
            if b["url"] and not ent["url"]:
                ent["url"] = b["url"]
            for cat, kind in hits:
                if ent["hits"].get(cat) != "core":
                    ent["hits"][cat] = kind
    return found


def write_index(path, y, m, found, n_emails, topics):
    mon = datetime.date(y, m, 1).strftime("%B %Y")
    core = {c: [] for c in topics}
    rel = []
    for ent in found.values():
        cs = [c for c, k in ent["hits"].items() if k == "core"]
        for c in cs:
            core[c].append(ent)
        if not cs:
            rel.append(ent)
    key = lambda x: x["date"]

    def entry(e, why):
        s = f"### {e['title']}\n- **Journal:** {e['journal']}\n- **Date:** {e['date'].strftime('%B %-d, %Y')} ({e['type']})\n"
        if e["url"]:
            s += f"- **Link:** {e['url']}\n"
        return s + f"- **Reason:** {why}\n\n"

    o = [f"# JAMA Monthly Index — {mon}\n\n**Scanned:** {datetime.date.today():%B %-d, %Y}  \n"
         f"**Topics:** {', '.join(topics)}  \n**Emails scanned:** {n_emails}  \n**Matches:** {len(found)}\n\n---\n"]
    for c in topics:
        o.append(f"\n## {c}\n\n")
        o += [entry(e, "Keyword match for this topic") for e in sorted(core[c], key=key, reverse=True)] or ["_None this month._\n"]
    o.append("\n## Related but Not Core Matches\n\n")
    o += [entry(e, "Mentions " + ", ".join(sorted(e["hits"])) + " only secondarily") for e in sorted(rel, key=key, reverse=True)] or ["_None this month._\n"]
    with open(path, "w") as f:
        f.write("".join(o))
    return sum(len(v) for v in core.values()), len(rel)


def pick_month(arg):
    if arg and arg != "auto":
        a = re.fullmatch(r"(\d{4})-(\d{2})", arg)
        if not a or not 1 <= int(a[2]) <= 12:
            raise RuntimeError(f"bad month '{arg}' (use YYYY-MM)")
        return int(a[1]), int(a[2])
    t = datetime.date.today()
    yy, mm = t.year - (t.month == 1), (t.month - 2) % 12 + 1
    for _ in range(12):
        if not os.path.exists(f"{OUT_DIR}/JAMA_{datetime.date(yy, mm, 1):%B_%Y}.md"):
            return yy, mm
        yy, mm = yy - (mm == 1), (mm - 2) % 12 + 1
    return None


def run(args, get_jmap=lambda: JMAP(load_token())):
    kv = dict(p.split("=", 1) for p in re.split(r"\s*;\s*", args.strip()) if "=" in p)
    cron = kv.get("cron") == "1"
    ym = pick_month(kv.get("month", "auto"))
    if ym is None:
        return ("[SILENT] JAMA scan: last 12 months already indexed." if cron
                else "All of the last 12 months already have an index file in ~/Documents/JAMA. Nothing to scan.")
    y, m = ym
    path = f"{OUT_DIR}/JAMA_{datetime.date(y, m, 1):%B_%Y}.md"
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)
    tf = f"{STATE}/topics.json"
    if not os.path.exists(tf):
        json.dump(DEFAULT_TOPICS, open(tf, "w"), indent=1)
    topics = json.load(open(tf))
    if os.path.exists(path) and kv.get("force") != "1":
        return f"The {datetime.date(y, m, 1):%B %Y} index already exists at {path}. Re-run with force=1 to rebuild it (the old file is backed up first)."
    emails = fetch_month(get_jmap, y, m)
    mark("fetch")
    if not emails:
        raise RuntimeError(f"the JAMA folder has no emails for {datetime.date(y, m, 1):%B %Y}")
    found = scan(emails, topics)
    mark("scan")
    if os.path.exists(path):
        os.makedirs(f"{WORK}/backups", exist_ok=True)
        os.replace(path, f"{WORK}/backups/{os.path.basename(path)}.{int(time.time())}")
    core, rel = write_index(path, y, m, found, len(emails), topics)
    os.makedirs(ATT, exist_ok=True)
    n = 0
    while True:
        att = f"{ATT}/{os.path.basename(path)[:-3]}{'' if n == 0 else '_' + str(n)}.md"
        try:
            with open(att, "x") as f:
                f.write(open(path).read())
            break
        except FileExistsError:
            n += 1
    mark("report")
    return emails, core, rel, path, att, y, m


def timing(n_emails=""):
    seg = [(marks[i][0], marks[i][1] - marks[i - 1][1]) for i in range(1, len(marks))]
    total = marks[-1][1] - T0
    line = "TIMING: " + " | ".join(f"{k} {fmt(v)}" for k, v in seg) + f" | total {fmt(total)}"
    try:
        h = f"{HERE}/timing_history.csv"
        new = not os.path.exists(h)
        d = dict(seg)
        with open(h, "a") as f:
            if new:
                f.write("run,emails,fetch,scan,report,total\n")
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')},{n_emails},{round(d.get('fetch', 0))},{round(d.get('scan', 0))},{round(d.get('report', 0))},{round(total)}\n")
    except OSError:
        pass
    return line


def main(args):
    cron = "cron=1" in args
    try:
        r = run(args)
        if isinstance(r, str):
            return "REPLY START\n" + r + "\nREPLY END"
        emails, core, rel, path, att, y, m = r
        return ("REPLY START\n"
                f"JAMA scan for {datetime.date(y, m, 1):%B %Y}: scanned {len(emails)} emails and found {core} core articles plus {rel} related ones. "
                f"The index is saved at {path}.\n{timing(len(emails))}\nMEDIA:{att}\nREPLY END")
    except Exception as e:
        mark("failed")
        timing()
        return "REPLY START\n" + ("[CRON_FAILURE]\n" if cron else "") + f"JAMA scan failed: {e}\nREPLY END"


if __name__ == "__main__":
    print(main(sys.stdin.read()))
