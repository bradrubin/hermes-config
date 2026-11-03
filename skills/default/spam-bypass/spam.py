#!/usr/bin/env python3
"""spam-bypass helper. Three commands:
  spam.py start            print yesterday's date (YYYY-MM-DD) and start timing
  spam.py check <<'ROWS'   rows: emailId|sender name|sender email|subject  -> prints NEW: / SKIP: per row
  spam.py done <<'ROWS'    rows: emailId|OK or FAIL|sender name|sender email|subject  -> prints the REPLY block
State (ids already drafted, so a daily run never drafts twice): ~/.hermes/state/spam-bypass/handled.json"""
import csv, datetime, json, os, sys, time

STATE = "/Users/hermes/.hermes/state/spam-bypass"
HANDLED = os.path.join(STATE, "handled.json")
TL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timing.log")
KEEP_DAYS = 30


def load():
    try:
        with open(HANDLED) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def rows(n):
    out = []
    for line in sys.stdin.read().splitlines():
        p = [x.strip() for x in line.split("|", n - 1)]
        if len(p) == n and p[0]:
            out.append(p)
        elif line.strip():
            print(f"SKIPPED (needs {n} fields): {line[:80]}")
    return out


def start():
    with open(TL, "w") as f:
        f.write(f"{time.time():.3f}\n")
    print((datetime.date.today() - datetime.timedelta(days=1)).isoformat())


def check():
    done = load()
    for eid, name, email, subj in rows(4):
        print(("SKIP (already drafted): " if eid in done else "NEW: ") + f"{eid} | {name} | {subj}")


def timing():
    try:
        secs = time.time() - float(open(TL).read().split()[0])
        os.replace(TL, TL + ".last")
    except (OSError, ValueError, IndexError):
        return "TIMING: unavailable (start was not run this time)", None
    return f"TIMING: {secs:.0f}s from start to done", secs


def done_cmd():
    done = load()
    today = datetime.date.today().isoformat()
    ok, fail = [], []
    for eid, status, name, email, subj in rows(5):
        if status.upper() == "OK":
            done[eid] = today
            ok.append((name or email, subj))
        else:
            fail.append(name or email)
    cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    done = {k: v for k, v in done.items() if v >= cutoff}
    os.makedirs(STATE, exist_ok=True)
    tmp = HANDLED + ".tmp"
    with open(tmp, "w") as f:
        json.dump(done, f, indent=1, sort_keys=True)
    os.replace(tmp, HANDLED)
    tl, secs = timing()
    try:
        h = os.path.join(STATE, "timing_history.csv")
        new = not os.path.exists(h)
        with open(h, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["run_at", "drafts", "failures", "total_s"])
            w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), len(ok), len(fail),
                        "" if secs is None else f"{secs:.0f}"])
    except OSError:
        pass
    lines = []
    if fail:
        lines.append("[CRON_FAILURE]")
        lines.append("Spam bypass: could not create a draft for " + ", ".join(fail) + ".")
    if ok:
        n = len(ok)
        lines.append(f"Spam bypass: {n} reply draft{'s' if n > 1 else ''} added to Fastmail Drafts (not sent):")
        lines += [f"- {a}: Re: {b}" for a, b in ok]
    if lines:
        lines.append(tl)
    else:
        lines = [f"[SILENT] Spam bypass: nothing new. {tl}"]
    print("REPLY START")
    print("\n".join(lines))
    print("REPLY END")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"start": start, "check": check, "done": done_cmd}.get(cmd, lambda: print("usage: spam.py start|check|done"))()
