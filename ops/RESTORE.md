# Rebuilding the Hermes Mini from the backup repo

The private GitHub repo holds everything in `~/.hermes` that you made: skills, their state, cron jobs,
Hermes's memories, these ops scripts and CLAUDE.md. It deliberately does NOT hold secrets.
Keep these in your password manager, and update them when they change:

- `~/.hermes/.env` (the whole file). `env.keys` in the repo lists the variable names it needs.
- The secret values in `~/.hermes/config.yaml`. `config.redacted.yaml` in the repo shows every one as `<REDACTED>`.
- `~/.hermes/auth.json`, if Hermes made one (sign-ins such as the Google Workspace connector), or be ready to redo those sign-ins.
- The `hermes` account's password (auto-login needs it).

Not backed up, and rebuilt by use: Chrome's profile (Amazon etc. may ask for a robot check once), Hermes's
sessions and logs, and `attachments/`.

## Steps (new or wiped Mac)

1. **As brad:** create a standard (non-admin) user `hermes`. Make sure FileVault is off (`fdesetup status`),
   or auto-login won't work. Turn on Remote Login (SSH) for brad and hermes.
2. **As brad:** install the local model server and the model exactly as before. (This isn't in the repo.)
3. **As hermes:** install Hermes Agent per its own instructions, and set up its Telegram gateway. Don't
   configure skills yet.
4. **As hermes:** put the backup on top of the fresh `~/.hermes`. You'll need a deploy key first: make one with
   `ssh-keygen -t ed25519 -N "" -f ~/.ssh/hermes_backup_ed25519`. On GitHub, in the repo's Settings >
   Deploy keys, delete the old key and add the new `.pub` with write access. Then:
   ```
   GIT_SSH_COMMAND="ssh -i ~/.ssh/hermes_backup_ed25519 -o IdentitiesOnly=yes" git clone git@github.com:<github-user>/<repo>.git ~/hermes-restore
   rsync -a ~/hermes-restore/ ~/.hermes/
   rm -rf ~/hermes-restore
   ```
5. **As hermes:** restore secrets. Paste `.env` from the password manager into `~/.hermes/.env`. Merge
   `config.redacted.yaml` into `~/.hermes/config.yaml`, filling each `<REDACTED>` from the password manager.
   Restore `auth.json`, or sign in again.
6. **As hermes:** `bash ~/.hermes/ops/install.sh <github-user>/<repo>`. This reinstalls the git hook, Claude Code,
   the nightly backup, and the admin scripts in `/Users/Shared/hermes-ops`. It reuses the deploy key from step 4.
7. **As brad:** `bash /Users/Shared/hermes-ops/install_chrome.sh`
8. **As brad:** `bash /Users/Shared/hermes-ops/setup_autologin.sh`, then `sudo reboot`.
9. **As hermes** (after the reboot): `bash ~/.hermes/ops/setup_hermes_chrome.sh`, then `hermes gateway restart`.
10. **In Telegram:** send `/new`, then try one skill of each kind: an email skill (inbox-triage), a browser
   skill (tpaw-load), and an API skill (restaurant-finder). Ask Hermes to list its cron jobs to confirm they came back.
