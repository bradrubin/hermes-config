#!/bin/bash
# Hermes dev kit installer. Run on the Mac Mini as hermes:
#   bash ~/hermes-dev-kit/install.sh <github-user>/<repo>      e.g.  bash ~/hermes-dev-kit/install.sh bradrubin/hermes-config
# Safe to rerun. It never deletes anything, and never overwrites an existing CLAUDE.md or .claude/settings.json.
#  1. Copies ops/ scripts into ~/.hermes/ops, and the two admin scripts to /Users/Shared/hermes-ops (for brad).
#  2. Makes ~/.hermes a git repo (whitelist .gitignore, secret-blocking pre-commit hook) and commits.
#  3. Installs Claude Code (native installer, into ~/.local/bin; no admin needed) and an `hdev` shortcut.
#  4. With a repo name: makes a deploy key, waits while you add it on GitHub, then pushes.
#  5. Adds a nightly backup (1:00 am) to hermes's crontab.
set -e
KIT="$(cd "$(dirname "$0")" && pwd)"
H="${HERMES_HOME:-$HOME/.hermes}"
# Runs from the downloaded kit folder, or from ~/.hermes/ops/install.sh (a copy kept there for disaster recovery).
if [ -d "$KIT/ops" ]; then OPS="$KIT/ops"; CMD="$KIT/CLAUDE.md"; else OPS="$KIT"; CMD="$KIT/../CLAUDE.md"; fi
REPO="${1:-}"
step() { echo; echo "== $*"; }

[ "$(whoami)" = hermes ] || [ -n "${KIT_TEST:-}" ] || { echo "STOP: run this as hermes (you are $(whoami))."; exit 1; }
[ -d "$H" ] || { echo "STOP: $H not found. Is Hermes installed for this user?"; exit 1; }
if [ "$(uname)" = Darwin ] && ! xcode-select -p >/dev/null 2>&1; then
  echo "STOP: git needs Apple's Command Line Tools, which aren't installed. As brad, run:"
  echo "  touch /tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress"
  echo "  softwareupdate -l | grep -o 'Command Line Tools for Xcode-[0-9.]*' | tail -1"
  echo "  sudo softwareupdate -i \"<the name printed above>\""
  echo "then rerun this script."
  exit 1
fi
if [ -n "$REPO" ] && ! [[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "STOP: give the repo as <github-user>/<repo>, e.g. bradrubin/hermes-config"; exit 1
fi

step "1. Installing ops scripts"
mkdir -p "$H/ops" "$H/.claude"
if [ "$(cd "$OPS" && pwd)" != "$(cd "$H/ops" && pwd)" ]; then
  for f in "$OPS"/*; do [ -f "$f" ] && cp "$f" "$H/ops/"; done
  cp "$KIT/install.sh" "$H/ops/install.sh"
fi
chmod +x "$H"/ops/*.sh "$H/ops/secrets.py"
if [ -f "$H/.gitignore" ] && ! cmp -s "$OPS/gitignore" "$H/.gitignore"; then
  cp "$H/.gitignore" "$H/.gitignore.bak-$(date +%Y%m%d-%H%M%S)"; echo "old .gitignore backed up"
fi
cp "$OPS/gitignore" "$H/.gitignore"
for pair in "$CMD:CLAUDE.md" "$OPS/claude-settings.json:.claude/settings.json"; do
  src="${pair%%:*}"; dst="$H/${pair##*:}"
  if [ ! -f "$dst" ]; then cp "$src" "$dst"; echo "installed ${pair##*:}"
  elif ! cmp -s "$src" "$dst"; then cp "$src" "$dst.new"; echo "kept your ${pair##*:}; the kit's version is ${pair##*:}.new"; fi
done
if mkdir -p /Users/Shared/hermes-ops 2>/dev/null; then
  cp "$OPS/install_chrome.sh" "$OPS/setup_autologin.sh" /Users/Shared/hermes-ops/
  chmod 755 /Users/Shared/hermes-ops /Users/Shared/hermes-ops/*.sh
  echo "admin scripts for brad: /Users/Shared/hermes-ops/"
fi

step "2. Git repo in $H"
cd "$H"
if [ ! -d .git ]; then
  git init -q
  git symbolic-ref HEAD refs/heads/main
fi
git config user.name "Hermes on homechat-llm"
git config user.email "hermes@homechat-llm"
printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/ops/secrets.py" scan\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
python3 ops/secrets.py redact
git ls-files -ci --exclude-standard -z | xargs -0 git rm -q --cached --ignore-unmatch --  # drop files now ignored (e.g. staged by an earlier blocked run)
git add -A
if git diff --cached --quiet; then
  echo "nothing new to commit"
else
  git commit -q -m "dev kit install $(date '+%Y-%m-%d %H:%M')"
  echo "committed $(git ls-files | wc -l | tr -d ' ') tracked files"
fi
echo "Tracked top-level:  $(git ls-files | cut -d/ -f1 | sort -u | tr '\n' ' ')"
echo "Left out (ignored): $(ls -A | while read -r f; do git check-ignore -q "$f" && printf '%s ' "$f"; done)"

step "3. Claude Code"
export PATH="$HOME/.local/bin:$PATH"
if command -v claude >/dev/null 2>&1; then
  echo "already installed: $(claude --version 2>/dev/null)"
elif [ -n "${KIT_TEST:-}" ]; then
  echo "(test mode: skipped)"
else
  curl -fsSL https://claude.ai/install.sh | bash
fi
RC="$HOME/.zshrc"; touch "$RC"
grep -q '.local/bin' "$RC" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
grep -q 'alias hdev=' "$RC" || echo "alias hdev='cd ~/.hermes && claude'" >> "$RC"
echo "shortcut: hdev  (opens Claude Code in ~/.hermes)"

if [ -n "$REPO" ]; then
  step "4. GitHub backup to $REPO"
  KEY="$HOME/.ssh/hermes_backup_ed25519"
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "hermes-backup@homechat-llm" -f "$KEY"
  if ! grep -q '^Host github-hermes$' "$HOME/.ssh/config" 2>/dev/null; then
    printf '\nHost github-hermes\n  HostName github.com\n  User git\n  IdentityFile %s\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n' "$KEY" >> "$HOME/.ssh/config"
    chmod 600 "$HOME/.ssh/config"
  fi
  if ! ssh -o BatchMode=yes -T github-hermes 2>&1 | grep -q "successfully authenticated"; then
    echo "On GitHub (in your browser on the Air):"
    echo "  a. Create an EMPTY private repo named ${REPO#*/} (no README, no .gitignore)."
    echo "  b. In that repo: Settings > Deploy keys > Add deploy key. Title: homechat-llm."
    echo "     Paste this key and tick 'Allow write access':"
    echo
    cat "$KEY.pub"
    echo
    read -r -p "Press Enter once the key is added... "
    ssh -o BatchMode=yes -T github-hermes 2>&1 | grep -q "successfully authenticated" \
      || { echo "STOP: GitHub didn't accept the key yet. Check step b, then rerun this script."; exit 1; }
  fi
  git remote remove origin 2>/dev/null || true
  git remote add origin "git@github-hermes:$REPO.git"
  if ! out=$(git push -u origin main 2>&1); then
    echo "$out"; echo "STOP: push failed. Is the repo empty, and does the key have write access?"; exit 1
  fi
  echo "pushed to github.com/$REPO"

  step "5. Nightly backup"
  LINE="0 1 * * * /bin/bash $H/ops/backup.sh >> $HOME/Library/Logs/hermes-backup.log 2>&1"
  mkdir -p "$HOME/Library/Logs"
  if crontab -l 2>/dev/null | grep -q 'ops/backup.sh'; then echo "already in crontab"
  else (crontab -l 2>/dev/null; echo "$LINE") | crontab - && echo "added to crontab: 1:00 am daily"; fi
else
  echo; echo "(No repo given: skipped GitHub and nightly backup. Rerun with <github-user>/<repo> to add them.)"
fi

echo
echo "Done. Next, as hermes:  source ~/.zshrc && hdev"
echo "The first run prints a sign-in link; open it in a browser on your Air."
