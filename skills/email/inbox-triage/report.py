#!/usr/bin/env python3
"""Build the inbox triage report; prints COUNTS:, TIMING:, MEDIA: lines."""
import json, datetime, os, re, time
B = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("TRIAGE_OUT", "/Users/hermes/.hermes/attachments")
os.makedirs(OUT, exist_ok=True)
work = os.path.join(B, "work.jsonl")
unsub = []
uf = os.path.join(B, "unsubscribe.txt")
if os.path.exists(uf):
    for line in open(uf):
        s = line.split("#", 1)[0].strip().lower()
        if s:
            unsub.append(s)
order = ["REPLY", "ACT", "READ", "ARCHIVE", "UNSUBSCRIBE", "DELETE"]
prio = {c: i for i, c in enumerate(order)}
def norm(s):
    s = s.lower().strip()
    while True:
        t = re.sub(r"^(re|fwd|fw)\s*:\s*", "", s)
        if t == s:
            return s
        s = t
best = {}
if os.path.exists(work):
    for line in open(work):
        if not line.strip():
            continue
        r = json.loads(line)
        if any(u in r["email"].lower() for u in unsub):
            r["cat"] = "UNSUBSCRIBE"
        key = (r["email"].lower(), norm(r["subject"]))
        cur = best.get(key)
        # newest message per thread; same day -> more urgent category
        if cur is None or (r["date"], -prio[r["cat"]]) > (cur["date"], -prio[cur["cat"]]):
            best[key] = r
rows = list(best.values())
titles = {
    "REPLY": "Reply (someone is waiting on you)",
    "ACT": "Act (bill, deadline, form, appointment)",
    "READ": "Read, then archive",
    "ARCHIVE": "Archive (records and finished conversations)",
    "UNSUBSCRIBE": "Unsubscribe, then delete",
    "DELETE": "Delete",
}
counts = {c: sum(1 for r in rows if r["cat"] == c) for c in order}

# ---- timing ----
marks = []
tl = os.path.join(B, "timing.log")
if os.path.exists(tl):
    for line in open(tl):
        p = line.split()
        if len(p) == 2 and p[1].isdigit():
            marks.append((p[0], int(p[1])))
now = int(time.time())
def fmt(x):
    m, x = divmod(max(x, 0), 60)
    return f"{m}m{x:02d}s" if m else f"{x}s"
def first(k):
    return next((t for n, t in marks if n == k), None)
st, fe = first("start"), first("fetched")
saves = [t for n, t in marks if n == "save"]
seg = {}
if st:
    if fe:
        seg["fetch"] = fe - st
    if saves:
        seg["classify"] = saves[0] - (fe or st)
        if len(saves) > 1:
            seg["more_batches"] = saves[-1] - saves[0]
        seg["report"] = now - saves[-1]
    seg["total"] = now - st
if not st:
    timing = "TIMING: unavailable (setup.sh was not run this time)"
elif not saves:
    timing = "TIMING: unavailable (save.py was not run this time)"
elif seg:
    timing = "TIMING: " + " | ".join(f"{k.replace('_', ' ')} {fmt(v)}" for k, v in seg.items())
    timing += f" ({len(rows)} emails, {len(saves)} batches)"
    hist = os.path.join(B, "timing_history.csv")
    new = not os.path.exists(hist)
    with open(hist, "a") as h:
        if new:
            h.write("run,emails,batches,fetch,classify,more_batches,report,total\n")
        h.write(",".join([datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), str(len(rows)), str(len(saves))]
                         + [str(seg.get(k, "")) for k in ["fetch", "classify", "more_batches", "report", "total"]]) + "\n")
else:
    timing = "TIMING: unavailable"
# consume the log so a later run can never reuse these marks
if os.path.exists(tl):
    os.replace(tl, tl + ".last")

lines = [f"# Inbox triage: {len(rows)} conversations, past 7 days", "",
         "Work top to bottom. When every section is done, the week is at inbox zero."]
for c in order:
    items = sorted((r for r in rows if r["cat"] == c), key=lambda r: r["date"])
    if not items:
        continue
    lines += ["", f"## {titles[c]} ({len(items)})", ""]
    for r in items:
        note = f" | {r['note']}" if r["note"] else ""
        lines.append(f"- {r['date']} | {r['from']} | {r['subject']}{note}")
lines += ["", timing]
stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
n = 1
while True:
    path = os.path.join(OUT, f"inbox_triage_{stamp}_{n}.md")
    try:
        f = open(path, "x")
        break
    except FileExistsError:
        n += 1
with f:
    f.write("\n".join(lines) + "\n")
if os.path.exists(work):
    os.remove(work)
count_line = "COUNTS: " + (", ".join(f"{c.title()} {counts[c]}" for c in order if counts[c]) or "none")
print("REPLY START")
print("Here is your inbox triage for the past week:")
print()
print(count_line)
print()
print(timing)
print()
print(f"MEDIA:{path}")
print("REPLY END")
