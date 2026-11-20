#!/usr/bin/env bash
# Removes the web dashboard LaunchAgent (start it by hand afterwards with: python main.py --server)
set -euo pipefail
LABEL="com.aishortsstudio.web"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed $LABEL"
