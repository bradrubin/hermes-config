#!/usr/bin/env python3
"""workout: turn one page of handwritten workout rows into a NEW CSV in attachments/.
Usage: workout.py <<'ROWS'
10/01/2026|Box Squat|3|5|225
10/01/2026|Hip Thrust|3|10|
ROWS
Line format: date as written|exercise|sets|reps|weight (weight last, may be empty).
Always prints a complete REPLY START / REPLY END block (once per call = one page)."""
import csv, datetime, os, sys, time

T0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/Users/hermes/.hermes/attachments"
NAMES = {"BOX SQUAT": "Box Squat", "BOX": "Box Squat", "PRESS": "Press", "RDL": "Romanian Deadlift",
         "TRAP BAR": "Trap Bar Deadlift - high handle", "TRAP": "Trap Bar Deadlift - high handle",
         "BENCH": "Bench Press", "LAT P": "Lat Pulldown - underhand grip", "LATP": "Lat Pulldown - underhand grip",
         "LAT PULLDOWN": "Lat Pulldown - underhand grip", "HIP T": "Hip Thrust", "HIPT": "Hip Thrust",
         "ROW": "Machine Row - neutral grip", "ROMAN": "Roman Chair"}


def key(r):
    try:
        return datetime.datetime.strptime(r[0], "%m/%d/%Y")
    except ValueError:
        return datetime.datetime.max


def main():
    rows, skipped = [], []
    for line in sys.stdin.read().splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in line.split("|", 4)]
        if len(p) < 4 or not p[2].isdigit() or not p[3].isdigit():
            skipped.append(line[:60])
            continue
        p += [""] * (5 - len(p))
        rows.append((p[0], NAMES.get(p[1].upper(), p[1]), int(p[2]), int(p[3]), p[4]))
    if not rows:
        return ["Workout CSV failed: no valid rows (format: date|exercise|sets|reps|weight)"]
    rows.sort(key=key)
    os.makedirs(OUT, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    n = 1
    while True:
        path = f"{OUT}/workout_log_{stamp}_{n}.csv"
        try:
            f = open(path, "x", newline="")
            break
        except FileExistsError:
            n += 1
    with f:
        f.write("Date,Exercise Name,Number of Sets,Number of Reps,weight\n")
        csv.writer(f).writerows(rows)
    secs = time.time() - T0
    try:
        h = os.path.join(HERE, "timing_history.csv")
        new = not os.path.exists(h)
        with open(h, "a") as t:
            if new:
                t.write("run,rows,script_s\n")
            t.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M},{len(rows)},{secs:.2f}\n")
    except OSError:
        pass
    out = [f"SKIPPED {len(skipped)} malformed line(s): " + " / ".join(skipped)] if skipped else []
    return out + [f"MEDIA:{path}", f"TIMING: script {secs:.2f}s ({len(rows)} rows)"]


if __name__ == "__main__":
    try:
        lines = main()
    except Exception as e:
        lines = [f"Workout CSV failed: {type(e).__name__}: {e}"]
    print("REPLY START")
    print("\n".join(lines))
    print("REPLY END")
