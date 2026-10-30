#!/usr/bin/env python3
"""Builds the final reply for tpaw-load and records timing."""
import csv, datetime, json, os, time

D = os.path.dirname(os.path.abspath(__file__))
TL = os.path.join(D, "timing.log")
RES = os.path.join(D, "last_result.json")


def load_result():
    if not os.path.exists(RES):
        return {"ok": False, "error": "load step did not run (load_plan.py)"}
    with open(RES) as f:
        return json.load(f)


def timing(ok):
    if not os.path.exists(TL):
        return "TIMING: unavailable (setup.sh was not run this time)"
    marks = []
    with open(TL) as f:
        for line in f:
            p = line.split()
            if len(p) == 2:
                try:
                    marks.append((p[0], float(p[1])))
                except ValueError:
                    pass
    if not marks or marks[0][0] != "start":
        return "TIMING: unavailable (setup.sh was not run this time)"
    if not any(m[0] == "save" for m in marks):
        return "TIMING: unavailable (load_plan.py was not run this time)"
    marks.append(("report", time.time()))
    phases = [(marks[i][0], marks[i][1] - marks[i - 1][1]) for i in range(1, len(marks))]
    total = marks[-1][1] - marks[0][1]
    detail = ", ".join(f"{n} {s:.1f}s" for n, s in phases)

    hist = os.path.join(D, "timing_history.csv")
    new = not os.path.exists(hist)
    with open(hist, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "ok", "total_s", "phases"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), ok,
                    f"{total:.1f}", "; ".join(f"{n}={s:.1f}" for n, s in phases)])
    os.replace(TL, TL + ".last")  # stale marks can never be reused
    return f"TIMING: total {total:.1f}s ({detail})"


def balance_line(r):
    p = os.path.join(D, "current_balance.json")
    if not os.path.exists(p):
        return ""
    with open(p) as f:
        b = json.load(f)
    line = f"Portfolio balance set to ${b['new']:,}"
    if b.get("old") is not None:
        when = ""
        if b.get("old_ts"):
            when = " on " + datetime.date.fromtimestamp(b["old_ts"] / 1000).isoformat()
        line += f" (last entered ${b['old']:,}{when})"
    if r.get("ok"):
        line += "; shown on page" if r.get("balance_on_page") else "; NOT found on page, check the screenshot"
    return line


r = load_result()
lines = []
if r.get("ok"):
    lines.append(f"TPAW plan loaded: {os.path.basename(r.get('plan', ''))}")
    lines.append(f"Page: {r.get('title', '')}")
    if balance_line(r):
        lines.append(balance_line(r))
    if r.get("missing"):
        lines.append("Missing expected values: " + ", ".join(r["missing"]))
    elif r.get("found"):
        lines.append(f"Checks: all {len(r['found'])} expected values found")
else:
    lines.append(f"TPAW plan load failed: {r.get('error', 'unknown error')}")
lines.append(timing(bool(r.get("ok"))))
if r.get("screenshot"):
    lines.append("")
    lines.append(f"MEDIA:{r['screenshot']}")

print("REPLY START")
print("\n".join(lines))
print("REPLY END")
