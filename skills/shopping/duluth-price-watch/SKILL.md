---
name: duluth-price-watch
description: Nightly Duluth Buck Naked boxer price check
version: 1.0.3
author: Hermes Agent
---

# Duluth price watch

Use when the user asks to check Duluth Trading prices, the Buck Naked boxers or boxer briefs, or the Duluth price watch. Also run by a nightly cron job. It checks the single-pair price of every solid color of Men's Buck Naked Performance Boxers and Boxer Briefs and reports only solid colors at or under $15.

## Do exactly this: ONE browser_exec call

If this run was started by a cron job, call `browser_exec` with this code, exactly, as one line:

```python
ARGS = "cron"; exec(open("/Users/hermes/.hermes/skills/shopping/duluth-price-watch/duluth.py").read(), globals())
```

If the user asked in chat, use the same line with `ARGS = ""` instead of `ARGS = "cron"`.

Only if the user asks to test the alert at some price (for example "test the Duluth alert at $18"), use `ARGS = "threshold=18"` with that number. Never use a threshold on a cron run.

Use a `timeout_s` of 120. The script opens Duluth's site, reads every price, applies the $15 limit, and prints the finished reply.

## Your reply

On a cron run the script prints only the finished reply (no marker lines). Your final reply is the script's entire output, copied character for character: the first character of your reply is the first character the script printed. Add nothing before or after it.

On a chat run the output has a line `REPLY START`, then the reply, then a line `REPLY END`. Your final reply is only the lines in between. Do NOT write the `REPLY START` or `REPLY END` lines themselves.

In both cases, copy failures as printed, including any `[CRON_FAILURE]` line. Do not summarize, explain, add advice, or add headings. Do not turn the list into a table.

Copy it exactly. `[SILENT]` and `[CRON_FAILURE]` are delivery markers that Hermes reads only when they are the very first thing in your reply, and the prices, colors and links are already checked. Anything you add in front of them makes Hermes send a message that should have been silent. Rewording, reformatting or adding to the reply gives the user wrong numbers. If a line asks the user to edit the colors file, copy it as is.

## Rules

- Make no other tool calls. Do not retry. Do not use execute_code, web_search, web_extract or terminal.
- If the script reports a failure, send that failure as-is. Do not investigate it.
- Never click or type on web pages.
- Never read, edit or create files in the skill folder or in `/Users/hermes/.hermes/state/duluth-price-watch/`. The user edits `solid_colors.txt` there.
