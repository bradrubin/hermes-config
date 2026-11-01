---
name: jama-email-scan
description: Scan JAMA emails for topic matches and build a monthly index.
version: 1.1.2
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

1. Run exactly one terminal command. Put the settings on one line, `key=value; key=value`:
   - `month=YYYY-MM` only if the user named a month; otherwise omit it (the script picks the latest unscanned month).
   - `force=1` only if the user asked to rebuild an existing month.
   - `cron=1` if this is a scheduled/cron run with no user chat.

```
python3 /Users/hermes/.hermes/skills/research/jama-email-scan/scan.py <<'ARGS'
month=2026-10
ARGS
```

2. Reply with the text between REPLY START and REPLY END, exactly as printed. Do NOT write the REPLY START or REPLY END lines; the first character of your reply is the first character after REPLY START. Keep the `MEDIA:` line (without it the file does not attach) and the TIMING line.

## Rules

- No other calls. Do not use the Fastmail MCP tools, execute_code, or read any email yourself.
- If the script prints a failure, send it as-is. Do not investigate, retry, or read or edit skill files.
- Do not summarize, reformat or add comments about the articles.

Topics (editable by Brad): `/Users/hermes/.hermes/state/jama-email-scan/topics.json`.
