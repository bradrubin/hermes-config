#!/usr/bin/env python3
"""Read triage rows from stdin, one per line:
CATEGORY|YYYY-MM-DD|sender name|sender email|note|subject
Subject is last, so it may contain | " ' or anything else."""
import json, os, re, sys, time
B = os.path.dirname(os.path.abspath(__file__))
valid = {"REPLY", "ACT", "READ", "ARCHIVE", "DELETE"}
n = bad = 0
with open(os.path.join(B, "work.jsonl"), "a") as f:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        p = [x.strip() for x in line.split("|", 5)]
        if len(p) < 6:
            bad += 1
            print(f"SKIPPED (needs 6 fields): {line[:80]}")
            continue
        cat = p[0].upper()
        if cat not in valid or not re.match(r"\d{4}-\d{2}-\d{2}", p[1]):
            bad += 1
            print(f"SKIPPED (category must be REPLY/ACT/READ/ARCHIVE/DELETE and date YYYY-MM-DD): {line[:80]}")
            continue
        f.write(json.dumps({"cat": cat, "date": p[1][:10], "from": p[2], "email": p[3],
                            "note": p[4], "subject": p[5][:60]}) + "\n")
        n += 1
with open(os.path.join(B, "timing.log"), "a") as t:
    t.write(f"save {int(time.time())}\n")
print(f"added {n} rows" + (f", {bad} skipped" if bad else ""))
