#!/usr/bin/env python3
"""JAMA monthly email scan: JMAP fetch, keyword match, index file, REPLY block.
Usage: scan.py <<'ARGS'
month=2026-10; force=1; cron=1
ARGS
month omitted or 'auto': most recent month (up to 12 back) with no index file."""
import os, re, sys, json, time, html, shutil, datetime, urllib.request, urllib.error

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


def load_token(name="FASTMAIL_API_TOKEN", required=True):
    t = os.environ.get(name)
    if not t:
        try:
            for ln in open(f"{HOME}/.env"):
                if ln.startswith(name + "="):
                    t = ln.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass
    if not t and required:
        raise RuntimeError(f"{name} not found in the environment or .env")
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


def jmap_fetch(j, y, m):
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
    return emails


class MCP:
    """Fastmail's MCP endpoint over plain HTTP JSON-RPC, with the same token Hermes uses."""
    URL = "https://api.fastmail.com/mcp"

    def __init__(self, tok):
        self.h = {"Authorization": "Bearer " + tok, "Content-Type": "application/json",
                  "Accept": "application/json, text/event-stream"}
        self.n = 0
        r = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                    "clientInfo": {"name": "hermes-jama-scan", "version": "1"}})
        self.server = (r.get("serverInfo") or {}).get("name", "?")
        self.rpc("notifications/initialized", {}, notify=True)
        self.tools = {t["name"]: t for t in self.rpc("tools/list", {}).get("tools", [])}

    def rpc(self, method, params, notify=False):
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notify:
            self.n += 1
            body["id"] = self.n
        req = urllib.request.Request(self.URL, json.dumps(body).encode(), self.h)
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Fastmail MCP HTTP {e.code} on {method}")
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.h["Mcp-Session-Id"] = sid
        raw = resp.read().decode()
        if notify or not raw.strip():
            return {}
        if "text/event-stream" in resp.headers.get("content-type", ""):
            msgs = [json.loads(l[5:]) for l in raw.splitlines() if l.startswith("data:") and l[5:].strip()]
            msg = next((x for x in msgs if x.get("id") == self.n), None) or {}
        else:
            msg = json.loads(raw)
        if "error" in msg:
            raise RuntimeError(f"Fastmail MCP {method} error: {str(msg['error'])[:150]}")
        return msg.get("result", {})

    def tool(self, name, args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        if r.get("isError"):
            raise RuntimeError(f"Fastmail MCP {name} failed: {str(r.get('content'))[:150]}")
        v = r.get("structuredContent")
        if v is None:
            v = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        for _ in range(3):
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except ValueError:
                    break
            if isinstance(v, dict) and isinstance(v.get("result"), (str, dict)):
                v = v["result"]
        return v


def mcp_fetch(c, y, m):
    q = f"in:JAMA after:{y}-{m:02d}-01 before:{y + (m == 12)}-{m % 12 + 1:02d}-01"
    props = (c.tools.get("search_email", {}).get("inputSchema") or {}).get("properties", {})
    cur_key = next((k for k in ("cursor", "nextCursor", "pageToken") if k in props), "cursor")
    rows, cursor = [], None
    while True:
        a = {"query": q, "limit": 50}
        if cursor:
            a[cur_key] = cursor
        r = c.tool("search_email", a)
        if not isinstance(r, dict) or "results" not in r:
            raise RuntimeError("unexpected search_email reply")
        rows += r["results"]
        cursor = r.get("nextCursor")
        if not (r.get("hasMore") and cursor) or len(rows) > 1000:
            break
    emails = []
    for row in rows:
        d = c.tool("read_email", {"id": row["id"]})
        if not isinstance(d, dict):
            raise RuntimeError("unexpected read_email reply")
        txt = d.get("bodyText") or d.get("body") or d.get("preview") or ""
        emails.append({"subject": row.get("subject", ""), "date": row["receivedAt"],
                       "from": (row.get("from") or [{}])[0].get("name") or "", "text": txt})
    return emails


def fetch_month(sources, y, m):
    cache = f"{WORK}/cache/{y}-{m:02d}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 86400:
        return json.load(open(cache))
    errs = []
    for fn, build in sources:
        try:
            emails = fn(build(), y, m)
            break
        except Exception as e:
            errs.append(str(e))
    else:
        raise RuntimeError("; ".join(errs) or "no Fastmail token available")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(emails, open(cache, "w"))
    return emails


LINK = re.compile(r"<(https?://[^>\s]*/t\.do\?id=[^>\s]*)>|\((https?://click\.alerts\.jamanetwork\.com/click/[^)\s]+)\)")
JUNK = re.compile(r", and more$|dr habil|dr rer|dr med|volume \d+|facebook|twitter|linked ?in|pinterest|youtube|instagram|alt content|advertisement|trouble viewing|"
                  r"ideal for sharing|visual abstract|subscribe|podcast|masthead|unsubscribe|thank you for|read it online|sign up|view in browser|released online first", re.I)
PREFIX = re.compile(r"^((review(?= women.s health)|research summary|audio|less is more|mpp editorial|ma medical news|medical news|original investigation|research letter|brief report|special communication|editorial|comment & response|invited commentary|"
                    r"viewpoint|clinical review|from jama this week|podcast|women.s health|jama (internal medicine|oncology|cardiology|network open|insights|pediatrics|psychiatry|surgery|neurology)|"
                    r"online first|new issue)\b[:\s]*)+", re.I)
LABEL = re.compile(r"\*[A-Z][A-Za-z&,' -]{3,40}\*\s*")
AUTHORS = re.compile(r"(\b(MD|PhD|MS|MPH|MSc|DO|RN|MBBS|ScD|DrPH)\b.*;|et al\.?$)")


def articles(text):
    """[(title, url)]: the text just before each article click-link in a JAMA email."""
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 <\2>", text)
    out, pos = [], 0
    for mt in LINK.finditer(text):
        seg = text[pos:mt.start()]
        pos = mt.end()
        url = mt.group(1) or mt.group(2)
        if "&a=" in url:
            continue
        seg = re.sub(r"https?://\S+", " ", seg)
        chunk = re.split(r"\n\s*\n", seg)[-1]
        parts = LABEL.split(chunk)
        chunk = parts[-1] if parts else chunk
        title = re.sub(r"\s+", " ", chunk).strip(" *_#>")
        if re.search(r"\bet al\.?\*?\s*\S{3}", title):
            title = re.sub(r"^.*\bet al\.?\*?\s*", "", title)
        else:
            lines = [re.sub(r"\s+", " ", l).strip(" *_#>") for l in chunk.splitlines()]
            lines = [l for l in lines if l]
            while lines and AUTHORS.search(lines[0]):
                lines.pop(0)
            title = " ".join(lines).strip()
        title = re.sub(r"^.*\bCollaborators\s+", "", title)
        m = list(re.finditer(r"\b(MD|PhD|MS|MA|MAS|MPH|DO|MSc|ScD|PharmD|MFA|BSN)\b\*?[,;]?\s+|\b(MD|PhD|MPH|MSc|ScD|PharmD|MFA|BSN)(?=[A-Z][a-z]|JAMA)", title))
        if m and len(title) - m[-1].end() >= 15:
            title = title[m[-1].end():]
        title = PREFIX.sub("", title).strip(" ;*")
        if 15 <= len(title) <= 400 and not JUNK.search(title):
            out.append((title, url))
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
        low = e["subject"].lower()
        itype = "Online First" if "online first" in low else "Med News" if "news" in low or "news" in e["from"].lower() else "New Issue" if re.search(r"issue|new", low) else "Email"
        d = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        arts = articles(e["text"])
        if not arts:
            subj = PREFIX.sub("", re.sub(r"^(online first|new issue|med news)\s*:\s*", "", e["subject"], flags=re.I)).strip()
            arts = [(subj, "")] if len(subj) >= 25 and not JUNK.search(subj) else []
        for title, url in arts:
            hits = classify(topics, title)
            if not hits:
                continue
            key = re.sub(r"\W+", "", title.lower())
            ent = found.setdefault(key, {"title": title, "journal": e["from"] or "JAMA", "date": d, "type": itype, "url": url, "hits": {}})
            if d < ent["date"]:
                ent.update(date=d, type=itype, journal=e["from"] or "JAMA", url=url)
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


def load_topics():
    """Read state/jama-email-scan/topics.txt (seeded from topics.default.txt if missing)."""
    tf = f"{STATE}/topics.txt"
    if not os.path.exists(tf):
        shutil.copyfile(f"{HERE}/topics.default.txt", tf)
    topics, cur = {}, None
    for n, ln in enumerate(open(tf), 1):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith("[") and ln.endswith("]"):
            cur = topics.setdefault(ln[1:-1].strip(), {"core": [], "related": []})
            continue
        kind, _, pat = ln.partition(":")
        kind, pat = kind.strip().lower(), pat.strip()
        if cur is None or kind not in ("core", "related") or not pat:
            raise RuntimeError(f"topics.txt line {n} not understood: {ln[:60]}")
        try:
            re.compile(pat)
        except re.error as e:
            raise RuntimeError(f"topics.txt line {n} has a bad pattern ({e}): {pat[:60]}")
        cur[kind].append(pat)
    if not topics:
        raise RuntimeError("topics.txt has no [Topic] sections")
    return topics


def default_sources():
    src = [(mcp_fetch, lambda: MCP(load_token()))]
    if load_token("FASTMAIL_JMAP_TOKEN", False):
        src.append((jmap_fetch, lambda: JMAP(load_token("FASTMAIL_JMAP_TOKEN"))))
    return src


def run(args, sources=None):
    sources = sources or default_sources()
    kv = dict(p.split("=", 1) for p in re.split(r"\s*;\s*", args.strip()) if "=" in p)
    cron = kv.get("cron") == "1"
    if kv.get("check") == "1":
        c = MCP(load_token())
        return f"Fastmail MCP connection OK: server {c.server}, tools: {', '.join(sorted(c.tools))}"
    ym = pick_month(kv.get("month", "auto"))
    if ym is None:
        return ("[SILENT] JAMA scan: last 12 months already indexed." if cron
                else "All of the last 12 months already have an index file in ~/Documents/JAMA. Nothing to scan.")
    y, m = ym
    path = f"{OUT_DIR}/JAMA_{datetime.date(y, m, 1):%B_%Y}.md"
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(STATE, exist_ok=True)
    topics = load_topics()
    if os.path.exists(path) and kv.get("force") != "1":
        return f"The {datetime.date(y, m, 1):%B %Y} index already exists at {path}. Re-run with force=1 to rebuild it (the old file is backed up first)."
    emails = fetch_month(sources, y, m)
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
