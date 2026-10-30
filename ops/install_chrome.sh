#!/bin/bash
# Run on the Mac Mini as brad (admin; asks for brad's password):   bash /Users/Shared/hermes-ops/install_chrome.sh
# Installs Google Chrome over SSH (no screen needed). Chrome then updates itself.
set -e
APP="/Applications/Google Chrome.app"
if [ -d "$APP" ]; then echo "Chrome is already installed: $("$APP/Contents/MacOS/Google Chrome" --version)"; exit 0; fi
TMP=$(mktemp -d)
curl -L -o "$TMP/googlechrome.dmg" https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg
hdiutil attach "$TMP/googlechrome.dmg" -nobrowse -quiet -mountpoint "$TMP/mnt"
sudo cp -R "$TMP/mnt/Google Chrome.app" /Applications/
hdiutil detach "$TMP/mnt" -quiet
rm -rf "$TMP"
echo "Installed: $("$APP/Contents/MacOS/Google Chrome" --version)"
