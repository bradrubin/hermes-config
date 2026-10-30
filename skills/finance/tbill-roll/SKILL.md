---
name: tbill-roll
description: Find replacement T-bills for auto-rolled bills
version: 1.1.0
author: Hermes Agent
---

# T-bill Roll

Use when the user asks to update their T-bills or Treasuries, check auto-rolls, find replacement bills, or runs "tbill-roll".

This skill is ONE tool call. Call `terminal` once with exactly this command:

```bash
python3 /Users/hermes/.hermes/skills/finance/tbill-roll/roll.py
```

Your final reply is exactly the lines between `REPLY START` and `REPLY END`, copied character for character, including the `MEDIA:` line if there is one. Nothing else. The dates, rates and row counts must stay exact, and without the `MEDIA:` prefix the user gets no file.

## Rules

- Make that one call and nothing else. No execute_code, no web search, no browser, no other terminal commands.
- If the reply says "failed", send it as-is. Do not investigate or fix anything.
- Never read, edit, or create files for this skill, and never write to the Google Sheet.
- Do not add a table, summary, or advice of your own.
