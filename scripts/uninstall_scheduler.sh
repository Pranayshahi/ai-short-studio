#!/usr/bin/env bash
# Stops and removes the hands-off scheduler LaunchAgent.
set -euo pipefail
LABEL="com.aishortsstudio.scheduler"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Removed $LABEL."
