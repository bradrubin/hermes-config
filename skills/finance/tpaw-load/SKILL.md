---
name: tpaw-load
description: Run TPAW plan; report stocks % and spending
version: 3.3.1
author: Hermes Agent
---

# TPAW Load

Use when the user mentions TPAW or their TPAW plan: loading it, updating the portfolio balance, or asking what stock percentage or monthly spending it shows, e.g. "tpaw-load 1468825".

This skill is ONE tool call. Call `browser_exec` once with this code, as one line:

```python
ARGS = ""; exec(open("/Users/hermes/.hermes/skills/finance/tpaw-load/tpaw.py").read(), globals())
```

Put what the user gave between the quotes of ARGS:
- A dollar amount: digits only, e.g. `ARGS = "1468825"`.
- Nothing given: leave it as `ARGS = ""`.
- If this run was started by a cron job (a scheduled run, not a chat), add the word `cron`: `ARGS = "cron"`, or `ARGS = "cron 1468825"` with an amount. Never add it for a chat run.

The script's output has a line `REPLY START`, then the reply, then a line `REPLY END`. Your final reply is only the lines in between, copied character for character, including a `[CRON_FAILURE]` first line and the `MEDIA:` line when they are there.

- Do NOT write the `REPLY START` or `REPLY END` lines themselves. The first character of your reply is the first character of the line after `REPLY START`. Hermes reads `[CRON_FAILURE]` only when it is the very first thing in your reply.
- On a cron run the script may print just `[SILENT]` between the markers (it already sent the report itself). Then your whole reply is exactly `[SILENT]`.
- Your reply ends with the last line before `REPLY END`. Add nothing after it: no explanation, no suggestion, no question, even when the reply says "failed".

## Rules

- Make that one call and nothing else. No terminal, no execute_code, no other browser calls.
- If the reply says "failed", send it as-is. Do not investigate or fix anything.
- Never read, edit, or create files for this skill, and never open or edit the plan file.
- Never click or type on the TPAW page.
