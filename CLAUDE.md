# Hermes on homechat-llm — working notes for Claude Code

You are working on Brad's Hermes Agent server: a headless Mac Mini (hostname `homechat-llm`). You run as the
non-admin user `hermes` in `~/.hermes` (HERMES_HOME = /Users/hermes/.hermes). Hermes runs skills with a local
Qwen model and talks to Brad through Telegram. Brad works with you over SSH from his MacBook Air.

Brad's standing preferences:
- Make execution speed on the local Qwen model a priority in every skill (move work into Python scripts).
- Build per-step time stamps into every skill (see "Timing" below) so he can report timings.
- For every command you ask Brad to run, say which account runs it: `brad` (admin) or `hermes`.
- He pastes commands into zsh, where an inline `# comment` breaks the command. Don't put comments on command lines.

## Layout of ~/.hermes
- `skills/<category>/<name>/` — SKILL.md plus its installed scripts. Edit in place.
- `state/<skill>/` — user-edited lists and long-lived state. `scripts/` — scripts for `no_agent` cron jobs.
- `cron/jobs.json` — Hermes's scheduled jobs. `memories/`, `SOUL.md` — Hermes's memory and persona, if present.
- `attachments/` — files skills deliver with `MEDIA:` lines (not in git).
- `config.yaml`, `.env`, `auth.json` — contain secrets. Not in git; you are blocked from reading them.
  `config.redacted.yaml` and `env.keys` (made by `python3 ops/secrets.py redact`) show what they contain, minus values.
- `chrome-debug/` — the profile of the Chrome that Hermes's browser drives (Brad's site cookies). Never read it.
- `hermes-agent/` — Hermes's own code. Read it to learn how Hermes works; never edit it.
- `ops/` — setup, backup and recovery scripts; `ops/RESTORE.md` rebuilds this machine from the git repo.

## Git (this folder is the repo; it backs up to Brad's private GitHub repo)
- `.gitignore` is a whitelist. A new top-level folder stays untracked until you add it there; say so when you do.
- Commit after each change that works: `<skill>: <what changed> (vX.Y.Z)`, then `git push`.
  Bump `version:` in the SKILL.md frontmatter on every change.
- A pre-commit hook (`ops/secrets.py scan`) blocks secrets. Never bypass it (`--no-verify`) or force-push.
  If it blocks a commit, take the secret out of the file; scripts read secrets from `~/.hermes/.env` at run time.
- `ops/backup.sh` runs nightly from hermes's crontab and commits and pushes anything left uncommitted.
- Roll back with git (`git log`, `git restore`, `git revert`), not by retyping old versions.

## Development loop
1. Read the conventions below before writing or changing a skill.
2. Edit files directly in `skills/<category>/<name>/`. Delete files that are no longer used (`git rm`).
   Git history replaces the old install scripts and the "rm -rf, then install clean" step.
3. Test every script yourself with realistic input, using the exact command lines SKILL.md tells the model to run.
   Use mocks or a fake `post()` for paid APIs. Browser scripts can use the real Chrome at 127.0.0.1:9222:
   open your own tab and close it after; never touch tabs Hermes might be using.
4. Test end to end through Hermes with the local Qwen model, in a fresh session so old skill versions in
   context don't leak in. Look in `hermes --help` for a one-shot or non-interactive mode; once you know the
   exact command, add it here. Qwen runs take minutes. Hermes's logs are under `~/.hermes/logs/`.
5. Brad does the final check in Telegram. Tell him exactly what to send (after `/new`) and what he should see.
6. Ask Brad first before you: change `config.yaml`, cron jobs or LaunchAgents; run `hermes gateway restart`
   (it interrupts Telegram); draft or send email; or run anything that acts on his real accounts
   (tpaw-load uploads, Fastmail, Google Sheets writes).
7. `hermes` has no sudo. For anything that needs admin rights, give Brad the commands to run as `brad`.

## Machine notes
- Hermes's browser attaches to real Google Chrome via `browser: cdp_url: http://127.0.0.1:9222`.
  Chrome is started by the LaunchAgent `com.hermes.chrome-debug`, made by `ops/setup_hermes_chrome.sh`.
  It needs `hermes` auto-logged in at the console: `stat -f %Su /dev/console` must print `hermes`
  (`root` means the login window; fix with `/Users/Shared/hermes-ops/setup_autologin.sh` as brad, then reboot).
- Restarting that LaunchAgent from an SSH session fails (`Bootstrap failed: 5`). Brad runs
  `sudo launchctl bootstrap gui/$(id -u hermes) ~hermes/Library/LaunchAgents/com.hermes.chrome-debug.plist`
  as brad, or reboots.

## Keeping this file current
When you learn something about Hermes, Qwen or this machine that a future session would need, add it to this
file (machine or workflow) or to `ops/hermes-skill-conventions.md` (how to write skills, imported below), in
the same terse style, and commit it. These two files are the source of truth; Brad's claude.ai "Hermes"
project has an older copy of the conventions.

---

@ops/hermes-skill-conventions.md
