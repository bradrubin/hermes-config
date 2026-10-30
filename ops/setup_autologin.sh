#!/bin/bash
# Run on the Mac Mini as brad (admin):   bash /Users/Shared/hermes-ops/setup_autologin.sh
# Makes the Mini log in as hermes at boot, so Hermes's Chrome (a GUI app) can run on a headless machine.
# `sysadminctl -autologin` fails over SSH (error:22), so this writes /etc/kcpassword directly.
# It asks for hermes's password; the password is not stored anywhere else and is not echoed.
# Undo: sudo defaults delete /Library/Preferences/com.apple.loginwindow autoLoginUser; sudo rm /etc/kcpassword
set -e
USER_TO_LOGIN=hermes
if fdesetup status | grep -q "FileVault is On"; then
  echo "STOP: FileVault is on. macOS ignores automatic login while FileVault is on."; exit 1
fi
id "$USER_TO_LOGIN" >/dev/null 2>&1 || { echo "STOP: user $USER_TO_LOGIN doesn't exist."; exit 1; }
read -r -s -p "Password for $USER_TO_LOGIN: " PW; echo
[ -n "$PW" ] || { echo "STOP: empty password."; exit 1; }
# Check the password before saving it, so a typo doesn't leave the Mini stuck at the login window.
dscl /Local/Default -authonly "$USER_TO_LOGIN" "$PW" 2>/dev/null || { echo "STOP: that password is wrong."; exit 1; }
TMP=$(mktemp)
PW="$PW" python3 - "$TMP" <<'PY'
import os, sys
key = [0x7D, 0x89, 0x52, 0x23, 0xD2, 0xBC, 0xDD, 0xEA, 0xA3, 0xB9, 0x1F]
pw = os.environ["PW"].encode()
n = (len(pw) // 12 + 1) * 12          # pad with NULs to a multiple of 12, always at least one NUL
pw = pw + b"\0" * (n - len(pw))
open(sys.argv[1], "wb").write(bytes(b ^ key[i % len(key)] for i, b in enumerate(pw)))
PY
unset PW
sudo install -m 600 -o root -g wheel "$TMP" /etc/kcpassword
rm -f "$TMP"
sudo defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser "$USER_TO_LOGIN"
echo "Automatic login set for $USER_TO_LOGIN. Reboot to apply:  sudo reboot"
echo "After it comes back, this should print '$USER_TO_LOGIN':  stat -f %Su /dev/console"
