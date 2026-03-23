#!/bin/bash
# Runs via LaunchAgent at 9:50am daily (10 min before Cowork sync task).
# Copies the newest .streaks backup from iCloud into the project dir so the
# Cowork VM can read it at ./latest.streaks.

STREAKS_DIR="$HOME/Library/Mobile Documents/iCloud~com~streaksapp~streak/Documents"
PROJECT_DIR="$HOME/Projects/habits.lucaschatham.com"
LOG="$PROJECT_DIR/sync.log"

LATEST=$(ls -t "$STREAKS_DIR"/*.streaks 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "$(date): [copy-latest-streaks] ERROR - no .streaks files found in $STREAKS_DIR" >> "$LOG"
    exit 1
fi

cp "$LATEST" "$PROJECT_DIR/latest.streaks"
echo "$(date): [copy-latest-streaks] Copied $(basename "$LATEST") -> latest.streaks" >> "$LOG"
