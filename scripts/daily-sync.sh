#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$PROJECT_DIR/sync.log"
STAMP="$(date '+%Y-%m-%dT%H:%M:%S%z')"

log_line() {
  echo "[$STAMP] $*" >> "$LOG"
}

cd "$PROJECT_DIR"

BRANCH="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$BRANCH" != "master" ]]; then
  log_line "STATUS=error SOURCE=sqlite NOTE=wrong_branch BRANCH=${BRANCH:-detached}"
  exit 1
fi

git fetch origin master:refs/remotes/origin/master
git rebase origin/master
python3 extract_streaks.py

HABITS="$(python3 - <<'PY'
import json
with open("streaks-data.json", encoding="utf-8") as f:
    data = json.load(f)
print(len(data["habits"]))
PY
)"
DATES="$(python3 - <<'PY'
import json
with open("streaks-data.json", encoding="utf-8") as f:
    data = json.load(f)
print(f'{data["dates"][0]}..{data["dates"][-1]}')
PY
)"

git add streaks-data.json index.html

if git diff --cached --quiet; then
  log_line "STATUS=ok SOURCE=sqlite HABITS=$HABITS DATES=$DATES SITE=unchanged NOTE=no_diff"
  exit 0
fi

git commit -m "sync: $(date +%F)"
git push origin master:master
log_line "STATUS=ok SOURCE=sqlite HABITS=$HABITS DATES=$DATES SITE=pushed"
