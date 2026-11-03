---
name: jama-email-scan
description: Scan JAMA emails by topic into a monthly index
version: 1.2.2
author: Brad Rubin, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [jama, email, fastmail, medical-literature]
---

# JAMA Email Scan

Triggers: "scan JAMA", "JAMA monthly scan", "JAMA digest", a scheduled JAMA cron run.

One script reads the Fastmail JAMA folder, matches topics, writes `~/Documents/JAMA/JAMA_<Month>_<Year>.md` and prints the whole reply.

## Steps

1. Run exactly one terminal command. Put the settings on one line, `key=value; key=value`. Use this line exactly, and change it only as listed below:

```
python3 /Users/hermes/.hermes/skills/research/jama-email-scan/scan.py <<'ARGS'
cron=0
ARGS
```

   - Replace `cron=0` with `cron=1` if this is a scheduled/cron run with no user chat.
   - Add `; month=YYYY-MM` ONLY if the user named a month. Otherwise never write `month` (the script picks the latest unscanned month).
   - Add `; force=1` ONLY if the user asked to rebuild an existing month.

2. Reply with the text between REPLY START and REPLY END, exactly as printed. Do NOT write the REPLY START or REPLY END lines; the first character of your reply is the first character after REPLY START. Keep the `MEDIA:` line (without it the file does not attach) and the TIMING line.

## Rules

- No other calls. Do not use the Fastmail MCP tools, execute_code, or read any email yourself.
- If the script prints a failure, send it as-is. Do not investigate, retry, or read or edit skill files.
- Do not summarize, reformat or add comments about the articles.

Topics (editable by Brad): `/Users/hermes/.hermes/state/jama-email-scan/topics.txt` (plain text, one regex per line; the script reports bad lines).
