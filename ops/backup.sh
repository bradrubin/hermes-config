#!/bin/bash
# Nightly backup of ~/.hermes to its private GitHub repo. Run by hermes's crontab; safe to run by hand (as hermes).
# Commits only if something changed. The pre-commit hook still blocks secrets.
set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
cd "$HOME/.hermes" || exit 1
echo "== $(date '+%Y-%m-%d %H:%M:%S') backup"
# Local-only copies of data/ (TPAW plan etc.): dated, only when changed, newest 30 kept. Never goes to git (not whitelisted).
if [ -d data ]; then
  mkdir -p backups/data
  for f in data/*; do
    [ -f "$f" ] || continue
    b="$(basename "$f")"
    last="$(ls -t backups/data/*"__$b" 2>/dev/null | head -n 1)"
    if [ -z "$last" ] || ! cmp -s "$f" "$last"; then
      cp -p "$f" "backups/data/$(date '+%Y-%m-%d_%H%M%S')__$b" && echo "local copy: $b"
    fi
    ls -t backups/data/*"__$b" 2>/dev/null | tail -n +31 | while IFS= read -r old; do rm -f "$old"; done
  done
fi
python3 ops/secrets.py redact >/dev/null || { echo "redact failed"; exit 1; }
git add -A
if git diff --cached --quiet; then
  echo "no changes"
else
  git commit -q -m "auto backup $(date '+%Y-%m-%d')" || { echo "commit failed (see above)"; exit 1; }
  echo "committed: $(git log -1 --stat --format=%h | tail -1)"
fi
if git remote get-url origin >/dev/null 2>&1; then
  git push -q origin HEAD 2>&1 && echo "pushed" || { echo "push failed"; exit 1; }
fi
