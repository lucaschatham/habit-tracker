#!/bin/bash
# Sync Streaks data to habit tracker dashboard
# Runs daily at 11:59 PM via launchd
# Extracts data -> updates mockup -> commits -> pushes to GitHub -> Vercel auto-deploys

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACT_SCRIPT="$SCRIPT_DIR/extract_streaks.py"
BACKUP_DIR="$HOME/Library/Mobile Documents/iCloud~com~streaksapp~streak/Documents"
OUTPUT="$SCRIPT_DIR/streaks-data.json"
MOCKUP="$SCRIPT_DIR/index.html"
LOG="$SCRIPT_DIR/sync.log"

echo "$(date): Starting habit sync..." >> "$LOG"

# Find the latest backup file
LATEST=$(ls -t "$BACKUP_DIR"/*.streaks 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
  echo "$(date): ERROR - No backup files found" >> "$LOG"
  exit 1
fi

echo "$(date): Using backup: $(basename "$LATEST")" >> "$LOG"

# Update the extract script with the latest backup path and today's date
TODAY=$(date +%Y-%m-%d)
YEAR=$(date +%Y)
MONTH=$(date +%-m)
DAY=$(date +%-d)

python3 -c "
import re

with open('$EXTRACT_SCRIPT') as f:
    content = f.read()

# Update backup path
content = re.sub(
    r'BACKUP_PATH = \".*?\"',
    'BACKUP_PATH = \"$LATEST\"',
    content
)

# Update end date to today
content = re.sub(
    r'END = datetime\(\d+, \d+, \d+\)',
    'END = datetime($YEAR, $MONTH, $DAY)',
    content
)

with open('$EXTRACT_SCRIPT', 'w') as f:
    f.write(content)
"

# Run extraction
python3 "$EXTRACT_SCRIPT" >> "$LOG" 2>&1

# Update inline data in mockup.html
python3 -c "
import json

with open('$MOCKUP') as f:
    lines = f.readlines()

with open('$OUTPUT') as f:
    data = json.load(f)

# Find the line starting with 'const D = '
for i, line in enumerate(lines):
    if line.strip().startswith('const D = '):
        lines[i] = 'const D = ' + json.dumps(data) + ';\n'
        break

with open('$MOCKUP', 'w') as f:
    f.writelines(lines)

print(f'Updated mockup: {len(data[\"habits\"])} habits, {len(data[\"dates\"])} days')
" >> "$LOG" 2>&1

# Git commit and push
cd "$SCRIPT_DIR"
if git diff --quiet index.html streaks-data.json 2>/dev/null; then
  echo "$(date): No data changes, skipping commit" >> "$LOG"
else
  git add index.html streaks-data.json
  git commit -m "Daily sync: $(date +%Y-%m-%d) habit data update"
  git push origin master >> "$LOG" 2>&1
  echo "$(date): Pushed to GitHub" >> "$LOG"

  # Deploy to Vercel
  vercel deploy --prod --yes >> "$LOG" 2>&1
  echo "$(date): Deployed to Vercel" >> "$LOG"
fi

echo "$(date): Sync complete" >> "$LOG"
