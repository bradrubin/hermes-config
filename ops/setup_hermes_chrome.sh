#!/bin/bash
# Run on the Mac Mini as the hermes user:   bash ~/.hermes/ops/setup_hermes_chrome.sh
# Starts real Google Chrome for Hermes (own profile, debug port on 127.0.0.1 only) via a LaunchAgent,
# and points Hermes's browser at it (browser: cdp_url in config.yaml). Safe to rerun.
# Needs: Chrome installed (ops/install_chrome.sh, as brad) and hermes auto-logged in (ops/setup_autologin.sh, as brad).
# DevTools from the Air: ssh -N -L 9223:127.0.0.1:9222 hermes@homechat-llm, then chrome://inspect -> localhost:9223.
# Undo: launchctl bootout gui/$(id -u)/com.hermes.chrome-debug; rm ~/Library/LaunchAgents/com.hermes.chrome-debug.plist
#       and remove the cdp_url line from ~/.hermes/config.yaml (a backup is saved next to it).
set -e
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE="$HOME/.hermes/chrome-debug"
PORT=9222
LABEL=com.hermes.chrome-debug
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CONFIG="$HOME/.hermes/config.yaml"
UID_=$(id -u)

[ -x "$CHROME" ] || { echo "STOP: Google Chrome is not installed. As brad, run: bash /Users/Shared/hermes-ops/install_chrome.sh"; exit 1; }
CONSOLE_USER=$(stat -f %Su /dev/console)
if [ "$CONSOLE_USER" != "$(whoami)" ]; then
  echo "STOP: the screen is logged in as '$CONSOLE_USER', not $(whoami) ('root' means the login window)."
  echo "As brad, run: bash /Users/Shared/hermes-ops/setup_autologin.sh   then: sudo reboot"
  exit 1
fi

# 1. LaunchAgent. The --disable-* flags keep a hidden tab rendering on the monitorless Mini (tpaw-load needs it).
mkdir -p "$PROFILE" "$HOME/Library/LaunchAgents"
NEW=$(mktemp)
cat > "$NEW" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$CHROME</string>
    <string>--remote-debugging-port=$PORT</string>
    <string>--remote-debugging-address=127.0.0.1</string>
    <string>--user-data-dir=$PROFILE</string>
    <string>--no-first-run</string>
    <string>--no-default-browser-check</string>
    <string>--remote-allow-origins=http://localhost:9223</string>
    <string>--disable-background-timer-throttling</string>
    <string>--disable-renderer-backgrounding</string>
    <string>--disable-backgrounding-occluded-windows</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$PROFILE/chrome.log</string>
</dict></plist>
EOF

port_ok() { curl -s "http://127.0.0.1:$PORT/json/version" | grep -q '"Browser"'; }

if [ -f "$PLIST" ] && cmp -s "$NEW" "$PLIST" && port_ok; then
  echo "Chrome LaunchAgent unchanged and running; not restarting it."
  rm -f "$NEW"
else
  mv "$NEW" "$PLIST"
  launchctl bootout "gui/$UID_/$LABEL" 2>/dev/null || true
  sleep 2
  if ! launchctl bootstrap "gui/$UID_" "$PLIST" 2>/dev/null; then
    echo "STOP: macOS wouldn't (re)start the Chrome LaunchAgent from this SSH session. Either:"
    echo "  - as brad run:  sudo launchctl bootout gui/$UID_/$LABEL; sudo launchctl bootstrap gui/$UID_ $PLIST"
    echo "  - or as brad run:  sudo reboot   (the agent loads at hermes's auto-login)"
    echo "then rerun this script to finish the config.yaml step."
    exit 1
  fi
  for i in $(seq 1 30); do port_ok && break; sleep 1; done
  port_ok || { echo "STOP: Chrome started but port $PORT isn't answering. See $PROFILE/chrome.log"; exit 1; }
fi
echo "Chrome is running: $(curl -s http://127.0.0.1:$PORT/json/version | grep '"Browser"' | tr -d ' ,')"

# 2. config.yaml: add cdp_url under the top-level browser: block (once).
[ -f "$CONFIG" ] || { echo "STOP: $CONFIG not found. Install/configure Hermes first, then rerun."; exit 1; }
if grep -q '^  cdp_url:' "$CONFIG"; then
  echo "config.yaml already has: $(grep '^  cdp_url:' "$CONFIG" | head -1 | sed 's/^ *//')"
else
  cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d-%H%M%S)"
  python3 - "$CONFIG" "$PORT" <<'PY'
import sys
path, port = sys.argv[1], sys.argv[2]
lines = open(path).read().split("\n")
idx = [i for i, l in enumerate(lines) if l.rstrip() == "browser:"]
line = f"  cdp_url: http://127.0.0.1:{port}"
if len(idx) > 1:
    sys.exit(f"STOP: found {len(idx)} top-level 'browser:' lines in {path}. Add '{line.strip()}' under the right one by hand.")
if idx:
    lines.insert(idx[0] + 1, line)
else:
    while lines and lines[-1] == "":
        lines.pop()
    lines += ["browser:", line]
open(path, "w").write("\n".join(lines).rstrip("\n") + "\n")
print("config.yaml: added " + line.strip())
PY
  echo "Now restart Hermes so it uses this Chrome:  hermes gateway restart"
fi
