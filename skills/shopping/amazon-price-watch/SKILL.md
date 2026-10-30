---
name: amazon-price-watch
description: Daily Amazon price-drop check for a watch list
version: 1.0.2
author: Hermes Agent
---

# Amazon price watch

Use when the user asks to check Amazon prices, run the price watch, or look for price drops on their watch list. Also run by a daily cron job.

## Do exactly this: ONE browser_exec call

If this run was started by a cron job, call `browser_exec` with this code, exactly, as one line:

```python
ARGS = "cron"; exec(open("/Users/hermes/.hermes/skills/shopping/amazon-price-watch/price_watch.py").read(), globals())
```

If the user asked in chat, use the same line with `ARGS = ""` instead of `ARGS = "cron"`.

Use a `timeout_s` of 400. The script opens Amazon, reads every price, compares each one with its baseline, and prints the finished reply.

## Your reply

Your final reply is exactly the lines between `REPLY START` and `REPLY END`, copied character for character. Nothing else. This applies to failures too: copy the failure lines as printed, including any `[CRON_FAILURE]` line. Do not summarize, explain, add advice, or add headings.

Copy it exactly. `[SILENT]` and `[CRON_FAILURE]` are delivery markers that Hermes reads, and the prices and links are already checked. Rewording, reformatting or adding to the reply breaks delivery and gives the user wrong numbers.

## Rules

- Make no other tool calls. Do not retry. Do not use execute_code, web_search, web_extract or terminal.
- If the script reports a failure, send that failure as-is. Do not investigate it.
- Never click or type on web pages.
- Never read, edit or create files in the skill folder or in `/Users/hermes/.hermes/state/amazon-price-watch/`. The user edits `items.txt` there.
