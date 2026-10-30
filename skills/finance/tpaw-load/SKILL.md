---
name: tpaw-load
description: Run TPAW plan; report stocks % and spending
version: 3.2.1
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

The script's output has a line `REPLY START`, then the reply, then a line `REPLY END`. Your final reply is only the lines in between, copied character for character (including the `MEDIA:` line). Do NOT write the `REPLY START` or `REPLY END` lines themselves. Nothing else.

## Rules

- Make that one call and nothing else. No terminal, no execute_code, no other browser calls.
- If the reply says "failed", send it as-is. Do not investigate or fix anything.
- Never read, edit, or create files for this skill, and never open or edit the plan file.
- Never click or type on the TPAW page.
