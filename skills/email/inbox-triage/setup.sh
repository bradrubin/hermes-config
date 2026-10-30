#!/bin/bash
# inbox-triage setup: reset work files, start timing, print START date (YYYY-MM-DD).
B="$(cd "$(dirname "$0")" && pwd)"
rm -f "$B/work.jsonl"
echo "start $(date +%s)" > "$B/timing.log"
[ -f "$B/unsubscribe.txt" ] || printf '# One sender email (or part of one) per line. Matching senders go to Unsubscribe.\ninfo@mortiseandtenonmag.com\nno-reply@substack.com\n' > "$B/unsubscribe.txt"
date -v-7d +%Y-%m-%d 2>/dev/null || date -d '-7 days' +%Y-%m-%d
