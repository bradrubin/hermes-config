# tpaw-load v3 — maintainer notes (not read by the model)

## Install
Files live in git (`skills/finance/tpaw-load/`); edit in place and roll back with git.
Files used: SKILL.md, tpaw.py, plan_path.txt, balance_source.txt, expect.txt, NOTES.md.
- Edit `plan_path.txt` to point at your plan file (kept outside Documents/Desktop/Downloads).
- Make the original plan read-only so no model can edit it: `chmod a-w "<plan file>"`.
  (The skill only ever writes a copy, in `work/`.)
- The plan file is NOT in git (it is outside the whitelist). Keep your own backup.
- Test in a fresh Hermes session: `tpaw-load 1468825`.
- Old v2 files (setup.sh, report.py, load_plan.py, patch_plan.py) were removed in v3.3.2.

## Why v3 is one call
In v2, Qwen ran a stale `setup.sh`, got an error, and then improvised: it read the scripts,
hand-wrote JSON, clicked around the page, and edited the original plan file. v3 removes every
place to improvise:
- One `browser_exec` call. `tpaw.py` does setup, the balance patch, the page load, the checks,
  the screenshot, and the timing.
- It always prints a finished REPLY block, including on failure, so a failure never needs
  investigating.
- One code file, so old and new files can't mix. Nothing is imported, so the browser session's
  import cache can't serve an old version.
- SKILL.md forbids reading or editing files, clicking, and follow-up calls.

## Balance input
`ARGS = "1468825"` (also accepts $1,468,825, 1.47m, 950k). A path ending in .txt in ARGS
overrides plan_path.txt. The patch appends one `setCurrentPortfolioBalance` entry to a copy of
the plan, then checks the result by replaying the history.

How the entry is built (v3.0.1): TPAW records each change as a fast-json-patch `compare(old, new)`
diff. `tpaw.py` has a Python port of that function, and it reproduces all 212 recorded diffs in
the 2026 plan exactly. It copies the current state, applies what the app applies, and diffs:
- When the month has changed since the last entry, every "now" `monthOfEntry` moves to the
  current month. The app does this on the first change in each new month, of any type.
  v3.0.0 skipped it, which is the likely cause of TPAW's "Not a valid TPAW file".
- It sets the balance (`updatedHere: true`, `amount`) and the timestamp.

If TPAW still rejects the file, the reply says which file it rejected: the copy with the new
balance, or your original. Run once with `ARGS = ""` to test the original by itself.

The page's "Current Portfolio Balance" for a dated plan is the last entered balance moved
forward by market returns (e.g. $1,506,811 from $1,544,148). After the patch, the last entry is
"now", so the page shows exactly the amount you gave.

## Screenshot
Before the screenshot, the page scrolls the balance (or the "Portfolio Balance" label) into
view, so the value you care about is in the image.

## Timing (TIMING line + timing_history.csv)
patch (only with a balance), page_load, file_set, plan_render, verify (checks + screenshot).
Qwen's own time before and after the call isn't included; with only one call, it should be small.

## Balance from Google Sheets (v3.3)
With no amount (`ARGS = ""`), `tpaw.py` reads the balance with the Hermes Google Workspace skill's
CLI, the same command that worked by hand:

    python3 google_api.py sheets get 1Eoaa9-Z-zbBLAhz6LF9cN_aw4iW1b769Mz_5PxQZcJE "AA!D20"

That's the Sheets API `spreadsheets.values.get`, with OAuth handled by that skill. It runs as a
subprocess from inside the same single call, so Qwen does nothing extra. An amount given in ARGS
still overrides it.

`balance_source.txt` settings:
- `sheet_id`, `sheet`, `cell`: what to read (`AA!D20`).
- `google_api`: path to google_api.py. If blank, the first `~/.hermes/skills/**/google_api.py` found.
- `python`: the interpreter with the Google skill's libraries (default `python3`). If Hermes runs
  that skill in its own venv, put that venv's python here.

Parsing: takes the first cell value from the JSON (full API response, bare values list, or plain
text all work). If the value is a number, it's rounded to whole dollars; if it's currency text
(the default "$1,468,825.00"), the dollar amount is parsed out. An empty cell, a non-dollar
value, or a CLI error (e.g. an expired token) gives a one-line "failed" reply. The skill never
falls back to the old balance silently.

The reply shows the source: "Portfolio balance set to $X (from Google Sheet AA!D20)".
Timing adds a `sheet` phase.

## Results: monthly spending and stocks % (v3.2, based on TPAW's source)
Source: https://github.com/bengmathew/tpaw (packages/web). This replaces the Claude Desktop `tpaw`
skill. `make_inject_js.py` isn't needed, because `tpaw.py` hands the file to the page directly
over CDP, with no OS file picker. Nothing is saved on the site.

- **Monthly spending** = the label at the first (left-edge) point of "Monthly Spending During
  Retirement". NOT the Tasks card's "Withdraw" figure (e.g. balance $1,459,401 -> $12,305;
  Withdraw showed $5,051).
  - The chart is a `<canvas>`. Before the page loads, `tpaw.py` wraps the canvas text-drawing
    calls (`fillText` / `strokeText`) and records each number drawn, with its position, opacity
    and text baseline. TPAW's `Chart.draw()` clears the whole canvas each frame, which resets
    the record, so only the latest frame is kept.
  - In `ChartSalientPoints.ts`, the point labels are the only text drawn with
    `textBaseline = 'bottom'` (y-axis: 'middle', x-axis: 'top', hover box: 'alphabetic'), and
    they're formatted with `formatCurrency` (e.g. "$12,305", exact).
  - `GetPlanResultsChartSalientPoints.ts` puts the 95th/50th/5th-percentile labels at the left
    edge, all at the same x. Duplicates (the usual case: this month's spending is one value) are
    drawn at opacity 0 and ignored. If the visible values differ, the median is reported.
  - Waiting: TPAW shows "calculating..." (`PlanResultsLoading.tsx`) once a simulation passes
    750 ms. The value is accepted only after it stays the same, with no "calculating...", for
    6 polls (~2.4 s), with a 25 s limit. If it never settles, the reply says "chart was still
    changing".
- **Stocks % / bonds %**: from the Tasks card (`PlanResultsSidePanelTasksCard.tsx`), always
  visible on desktop: "Rebalance / Stocks / 34% / Bonds / 66%", each on its own line.
- The viewport is fixed at 1400x1000 (desktop layout, so the side panel shows).
- The screenshot is a crop of the spending chart.
- Every run writes `work/extract_debug.json`: canvases, the labels drawn in the latest frame,
  the left-edge candidates, the poll history, and the Tasks text.

Tested in headless Chromium against a mock page that reproduces TPAW's drawing code: canvas at
2x pixel density, y-axis/x-axis/hover text, hidden duplicate labels, a stale value plus
"calculating..." before the result, and multi-line Tasks text. For the first real run, use
1459401 (expected $12,305).

## Verify on the first run
- `cdp()` call form: both `cdp(method, **kw)` and `cdp(method, dict)` are handled.
- `js()` must evaluate an expression and return its value. If it needs a function body, the
  `js(...)` strings need `return`.
