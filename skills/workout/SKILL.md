---
name: workout
description: Handwritten workout log photos to CSV files
version: 2.0.0
author: Hermes Agent
---

# Workout

Use when the user sends photos of a handwritten workout log and wants a CSV. Trigger phrases: "workout log", "parse my workout".

## Steps

1. Read each image with `vision_analyze`. Keep each page's entries separate. For each entry get: date, exercise, sets, reps, weight (weight may be missing).
   - Write the exercise as it appears (BOX SQUAT, RDL, LAT P, ...). The script maps abbreviations to full names.
   - Separate sets on one line (e.g. "1x5x125 2x5x135") become separate rows.
   - Keep weights exactly as written (77.5, 132.5). Date as written, e.g. 10/01/2026.

2. ONE terminal call per page (never combine pages). Rows go in the heredoc, one per line, weight LAST (leave it empty if missing):

```bash
python3 /Users/hermes/.hermes/skills/workout/workout.py <<'ROWS'
10/01/2026|Box Squat|3|5|225
10/01/2026|Hip Thrust|3|10|
ROWS
```

   If it prints SKIPPED, fix only those lines and run again for them only.

3. Reply with the label line, a blank line, then each page's `MEDIA:` line exactly as printed (one per page, blank line between), then the last `TIMING:` line:

```
Here is your workout log CSV:

MEDIA:<page 1 path>

MEDIA:<page 2 path, if any>

TIMING: <from the last script output>
```

## Rules

- Each page gets its own new file; never append to or reuse a CSV.
- CSV rows must NEVER appear in the chat. The files are the deliverable.
- No other tools besides `vision_analyze` and the script call. No execute_code.
