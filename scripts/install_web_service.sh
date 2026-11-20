#!/usr/bin/env bash
# Installs the web dashboard (python main.py --server, 127.0.0.1:8000) as a macOS LaunchAgent:
#   - starts at login, restarts automatically if it crashes
#   - logs to output/automation/web.log
# Restart it safely with scripts/deploy.sh. Uninstall with scripts/uninstall_web_service.sh
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.aishortsstudio.web"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$PROJECT_DIR/output/automation"
PORT="${STUDIO_PORT:-8000}"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

# A server started by hand would hold the port: stop it first (only if nothing is generating)
if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  "$PROJECT_DIR/scripts/deploy.sh" --check-only || { echo "Not installing now: a video is generating. Try again when it's done."; exit 1; }
  kill $(lsof -tiTCP:"$PORT" -sTCP:LISTEN) 2>/dev/null || true
  sleep 3
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PROJECT_DIR/.venv/bin/python</string>
    <string>$PROJECT_DIR/main.py</string>
    <string>--server</string>
    <string>--port</string>
    <string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>RunAtLoad</key><true/>
  <!-- Restart after a crash, but not after a clean exit -->
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>20</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>StandardOutPath</key><string>$LOG_DIR/web.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/web.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
echo "Installed $LABEL (http://127.0.0.1:$PORT). Logs: $LOG_DIR/web.log"
launchctl print "gui/$(id -u)/$LABEL" | grep -E "state =|pid =" || true
