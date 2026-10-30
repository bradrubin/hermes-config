#!/usr/bin/env python3
"""Make a copy of a TPAW plan file with a new current portfolio balance.

Usage: patch_plan.py <plan.txt> <balance>
  balance: digits, optionally with $ and commas, or a k/m suffix (1468825, $1,468,825, 1.47m)

Appends one setCurrentPortfolioBalance entry to planParamsHistory, built exactly the way
the TPAW app records the change, writes the copy to <skill dir>/work/<same file name>,
and prints the copy's path. The original file is never modified.
"""
import copy, json, os, re, sys, time, uuid

D = os.path.dirname(os.path.abspath(__file__))
MARKER = "---- PLAN DATA STARTS HERE ----"


def fail(msg):
    print(f"PATCH FAILED: {msg}")
    sys.exit(1)


def parse_amount(s):
    s = s.strip().lower().replace("$", "").replace(",", "").replace("_", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([km]?)", s)
    if not m:
        fail(f"not a dollar amount: {s!r}")
    v = float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2)]
    v = int(round(v))
    if not 1 <= v <= 10_000_000_000:
        fail(f"balance out of range: {v}")
    return v


def apply(doc, ops):
    """Minimal RFC 6902 add/remove/replace, enough for TPAW plan history."""
    for op in ops:
        parts = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].split("/")[1:]]
        if not parts:
            doc = copy.deepcopy(op["value"])
            continue
        c = doc
        for p in parts[:-1]:
            c = c[int(p)] if isinstance(c, list) else c[p]
        k = parts[-1]
        if isinstance(c, list):
            k = len(c) if k == "-" else int(k)
            if op["op"] == "add":
                c.insert(k, copy.deepcopy(op["value"]))
            elif op["op"] == "remove":
                c.pop(k)
            else:
                c[k] = copy.deepcopy(op["value"])
        else:
            if op["op"] == "remove":
                del c[k]
            else:
                c[k] = copy.deepcopy(op["value"])
    return doc


def replay(history):
    doc = {}
    for e in history:
        doc = apply(doc, e["diff"])
    return doc


if len(sys.argv) != 3:
    fail("usage: patch_plan.py <plan.txt> <balance>")
src, amount = sys.argv[1], parse_amount(sys.argv[2])

with open(src, encoding="utf-8") as f:
    text = f.read()
if MARKER not in text:
    fail("not a TPAW plan file (no PLAN DATA marker)")
head, body = text.split(MARKER, 1)
lead = body[: len(body) - len(body.lstrip())]
try:
    plan = json.loads(body)
    hist = plan["planParamsHistory"]
except Exception as e:
    fail(f"could not read plan data: {e}")

# Drop any undone (redo) entries, as the app does when you make a new change.
rhi = int(plan.get("reverseHeadIndex", 0) or 0)
if rhi:
    hist = hist[: len(hist) - rhi]

try:
    state = replay(hist)
    pb = state["wealth"]["portfolioBalance"]
except Exception as e:
    fail(f"could not replay plan history: {e}")

if pb.get("updatedHere"):
    old, old_ts = pb.get("amount"), state.get("timestamp")
    diff = [{"op": "replace", "path": "/wealth/portfolioBalance/amount", "value": amount}]
else:
    old, old_ts = pb.get("updatedTo"), pb.get("updatedAtTimestamp")
    diff = [{"op": "remove", "path": f"/wealth/portfolioBalance/{k}"}
            for k in ("updatedAtTimestamp", "updatedTo", "updatedAtId") if k in pb]
    diff += [{"op": "replace", "path": "/wealth/portfolioBalance/updatedHere", "value": True},
             {"op": "add", "path": "/wealth/portfolioBalance/amount", "value": amount}]

now_ms = max(int(time.time() * 1000), int(state.get("timestamp", 0)) + 1)
diff.append({"op": "replace", "path": "/timestamp", "value": now_ms})
hist.append({"id": str(uuid.uuid4()),
             "change": {"type": "setCurrentPortfolioBalance", "value": amount},
             "diff": diff})
plan["planParamsHistory"] = hist
plan["reverseHeadIndex"] = 0
plan["lastSavedTimestamp"] = now_ms

# Verify: replaying the new history must give exactly the new balance.
check = replay(hist)["wealth"]["portfolioBalance"]
if check.get("amount") != amount or not check.get("updatedHere"):
    fail("verification failed after patch")

out_dir = os.path.join(D, "work")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, os.path.basename(src))
with open(out, "w", encoding="utf-8") as f:
    f.write(head + MARKER + lead + json.dumps(plan, separators=(",", ":"), ensure_ascii=False))

with open(os.path.join(D, "current_balance.json"), "w") as f:
    json.dump({"new": amount, "old": old, "old_ts": old_ts}, f)
with open(os.path.join(D, "timing.log"), "a") as f:
    f.write(f"patch {time.time():.3f}\n")
print(out)
