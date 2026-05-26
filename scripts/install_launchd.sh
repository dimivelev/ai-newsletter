#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LA_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LA_DIR"

for name in com.ainews.tracker com.ainews.web; do
    src="$SCRIPT_DIR/${name}.plist"
    dst="$LA_DIR/${name}.plist"
    cp "$src" "$dst"
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    echo "Loaded $dst"
done

echo
echo "Status:        launchctl list | grep ainews"
echo "Web URL:       http://127.0.0.1:8765/"
echo "Stop tracker:  launchctl unload ~/Library/LaunchAgents/com.ainews.tracker.plist"
echo "Stop web:     launchctl unload ~/Library/LaunchAgents/com.ainews.web.plist"
