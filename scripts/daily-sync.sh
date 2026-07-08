#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
LOG="$PROJECT_DIR/sync.log"
STAMP="$(date '+%Y-%m-%dT%H:%M:%S%z')"
SYNC_DIR="${HABITS_SYNC_DIR:-$HOME/Projects/habits.lucaschatham.com-sync}"

log_line() {
  echo "[$STAMP] $*" >> "$LOG"
}

if [[ "${HABITS_SYNC_INNER:-0}" != "1" && "$PROJECT_DIR" != "$SYNC_DIR" ]]; then
  if [[ ! -d "$SYNC_DIR/.git" ]]; then
    ORIGIN="$(git -C "$PROJECT_DIR" remote get-url origin)"
    mkdir -p "$(dirname "$SYNC_DIR")"
    git clone "$ORIGIN" "$SYNC_DIR"
  fi
  exec env HABITS_SYNC_INNER=1 bash "$SYNC_DIR/scripts/daily-sync.sh"
fi

cd "$PROJECT_DIR"

if [[ "${HABITS_SYNC_INNER:-0}" == "1" && "$PROJECT_DIR" == "$SYNC_DIR" ]]; then
  git restore --staged --worktree -- streaks-data.json index.html >/tmp/habits-sync-clean.log 2>&1 || true
fi

BRANCH="$(git symbolic-ref --quiet --short HEAD || true)"
if [[ "$BRANCH" != "master" ]]; then
  if ! git checkout master >/tmp/habits-sync-checkout.log 2>&1; then
    log_line "STATUS=error SOURCE=sqlite NOTE=checkout_master_failed BRANCH=${BRANCH:-detached}"
    cat /tmp/habits-sync-checkout.log >&2
    exit 1
  fi
fi

git fetch origin master:refs/remotes/origin/master
git rebase origin/master
python3 extract_streaks.py

if ! VALIDATION_OUTPUT="$(python3 scripts/validate_streaks_data.py streaks-data.json 2>&1)"; then
  UNKNOWN_COUNT="$(python3 - <<'PY'
import json
with open("streaks-data.json", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("unknown_count", "unknown"))
PY
)"
  log_line "STATUS=fail SOURCE=sqlite UNKNOWN_COUNT=$UNKNOWN_COUNT SITE=not_pushed REASON=validation_failed DETAILS=$(printf '%s' "$VALIDATION_OUTPUT" | tr '\n' ';' | sed 's/  */ /g')"
  if [[ "${HABITS_SYNC_INNER:-0}" == "1" && "$PROJECT_DIR" == "$SYNC_DIR" ]]; then
    git restore --staged --worktree -- streaks-data.json index.html >/tmp/habits-sync-clean.log 2>&1 || true
  fi
  printf '%s\n' "$VALIDATION_OUTPUT" >&2
  exit 1
fi

HABITS="$(python3 - <<'PY'
import json
with open("streaks-data.json", encoding="utf-8") as f:
    data = json.load(f)
print(len(data["habits"]))
PY
)"
read -r DATES GENERATED_AT FINALIZED_THROUGH SOURCE_KIND DB_MTIME UNKNOWN_COUNT < <(python3 - <<'PY'
import json
with open("streaks-data.json", encoding="utf-8") as f:
    data = json.load(f)
source = data["source"]
print(
    f'{data["dates"][0]}..{data["dates"][-1]} '
    f'{data["generated_at"]} '
    f'{data["finalized_through"]} '
    f'{source["kind"]} '
    f'{source["db_mtime"]} '
    f'{data["unknown_count"]}'
)
PY
)

git add streaks-data.json index.html

if git diff --cached --quiet; then
  SHA="$(git rev-parse HEAD)"
  log_line "STATUS=ok SOURCE=$SOURCE_KIND DB_MTIME=$DB_MTIME GENERATED_AT=$GENERATED_AT FINALIZED_THROUGH=$FINALIZED_THROUGH HABITS=$HABITS DATES=$DATES UNKNOWN_COUNT=$UNKNOWN_COUNT SITE=unchanged SHA=$SHA NOTE=no_diff"
  exit 0
fi

git commit -m "sync: $(date +%F)"
git push origin master:master
SHA="$(git rev-parse HEAD)"
log_line "STATUS=ok SOURCE=$SOURCE_KIND DB_MTIME=$DB_MTIME GENERATED_AT=$GENERATED_AT FINALIZED_THROUGH=$FINALIZED_THROUGH HABITS=$HABITS DATES=$DATES UNKNOWN_COUNT=$UNKNOWN_COUNT SITE=pushed SHA=$SHA"
