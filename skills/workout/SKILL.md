---
name: workout
description: "Parse handwritten workout log images into CSVs (date, exercise, sets, reps, weight), one new CSV per page, and send each as a Telegram file attachment via a MEDIA: line. Never paste CSV rows into chat."
version: 1.7.0
author: Hermes Agent
---

# Workout

## Output contract (read this first)

Your FINAL reply is the label line, a blank line, then one MEDIA: line per page, each separated by a blank line. Nothing else, no code block, no quotes:

Here is your workout log CSV:

MEDIA:<path printed by the script for page 1>

MEDIA:<path printed by the script for page 2, if any>

CSV rows must NEVER appear in the chat. The files are the deliverable.

## One page = one new file

- Every image (page) gets its OWN CSV. Never combine pages into one file.
- Never append to, reuse, or overwrite an existing CSV. The script below always creates a brand-new file with a unique name.
- Run the script once per page, with only that page's rows.

## Steps

1. **Read each image** with `vision_analyze`. Keep each page's entries separate. Extract every entry: date, exercise, sets, reps, weight (weight may be missing).

2. **Map exercise names.** Use:
   - BOX SQUAT / BOX -> Box Squat
   - PRESS -> Press
   - RDL -> Romanian Deadlift
   - TRAP BAR / TRAP -> Trap Bar Deadlift - high handle
   - BENCH -> Bench Press
   - LAT P / LATP / Lat Pulldown -> Lat Pulldown - underhand grip
   - HIP T / HIPT -> Hip Thrust
   - ROW -> Machine Row - neutral grip
   - ROMAN -> Roman Chair
   Unknown abbreviation: keep it as written.

3. **Write one file per page with ONE terminal call per page.** Replace the example rows with that page's real rows and run it exactly as below. One tuple per row: (date as written, exercise, sets, reps, weight). Use "" for missing weight. Separate sets on the same line (e.g. "1x5x125 2x5x135") become separate rows. Keep weights exactly as written (77.5, 132.5). Do not change the file-naming or open() logic.

```bash
python3 - <<'EOF'
import csv, datetime, os
rows = [
    ("10/01/2026", "Box Squat", 3, 5, "225"),
    ("10/01/2026", "Hip Thrust", 3, 10, ""),
]
def key(r):
    try:
        return datetime.datetime.strptime(r[0], "%m/%d/%Y")
    except ValueError:
        return datetime.datetime.max
rows.sort(key=key)
d = "/Users/hermes/.hermes/attachments"
os.makedirs(d, exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
n = 1
while True:
    path = f"{d}/workout_log_{stamp}_{n}.csv"
    try:
        f = open(path, "x", newline="")  # "x" = create new only; fails if the file exists
        break
    except FileExistsError:
        n += 1
with f:
    f.write("Date, Exercise Name, Number of Sets, Number of Reps, weight\n")
    csv.writer(f).writerows(rows)
print(f"MEDIA:{path}")
EOF
```

   If the command errors, fix the rows and run it again. Do not fall back to pasting the CSV.

4. **Reply** using the output contract above, copying each `MEDIA:` line the script printed, character for character, in page order.

