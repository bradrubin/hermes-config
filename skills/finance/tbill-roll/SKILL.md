---
name: tbill-roll
description: Find replacement T-bills for auto-rolled bills
version: 1.2.0
author: Hermes Agent
---

# T-bill Roll

Use when the user asks to update their T-bills or Treasuries, check auto-rolls, find replacement bills, or runs "tbill-roll".

This skill is ONE tool call. Call `terminal` once with exactly this command:

```bash
python3 /Users/hermes/.hermes/skills/finance/tbill-roll/roll.py
```

The scheduled nightly run does not use this skill: it is a script-only cron job (`~/.hermes/scripts/tbill_roll.py`, no model) that alerts on Telegram only when there is a new row, a warning, or a reinvestment window that opened for the first time.

The script's output has a line `REPLY START`, then the reply, then a line `REPLY END`. Your final reply is only the lines in between, copied character for character, including the `MEDIA:` line if there is one.

- Do NOT write the `REPLY START` or `REPLY END` lines themselves. The first character of your reply is the first character of the line after `REPLY START`.
- Add nothing after the last line: no explanation, no advice, no question, even when the reply says "failed".
- The dates, rates and row counts must stay exact, and without the `MEDIA:` prefix the user gets no file.

## Rules

- Make that one call and nothing else. No execute_code, no web search, no browser, no other terminal commands.
- If the reply says "failed", send it as-is. Do not investigate or fix anything.
- Never read, edit, or create files for this skill, and never write to the Google Sheet.
- Do not add a table, summary, or advice of your own.
