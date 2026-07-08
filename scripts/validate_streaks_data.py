#!/usr/bin/env python3
import json
import sys
from datetime import date
from pathlib import Path


VALID_STATES = {
    "complete",
    "missed",
    "incomplete",
    "skipped",
    "allowed_miss",
    "paused",
    "partial_complete",
    "partial_missed",
    "unknown",
}


def validate_data(data, today=None):
    today = today or date.today()
    errors = []

    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")

    dates = data.get("dates")
    habits = data.get("habits")
    finalized_through = data.get("finalized_through")
    source = data.get("source") or {}

    if not data.get("generated_at"):
        errors.append("generated_at is required")
    if not finalized_through:
        errors.append("finalized_through is required")
    if source.get("kind") != "streaks_sqlite":
        errors.append("source.kind must be streaks_sqlite")
    if not source.get("db_mtime"):
        errors.append("source.db_mtime is required")
    if not isinstance(dates, list) or not dates:
        errors.append("dates must be a non-empty array")
    if not isinstance(habits, list):
        errors.append("habits must be an array")
        habits = []

    if dates and finalized_through:
        if dates[-1] != finalized_through:
            errors.append("last date must equal finalized_through")
        try:
            finalized_date = date.fromisoformat(finalized_through)
            if finalized_date >= today:
                errors.append("finalized_through must be before today")
        except ValueError:
            errors.append("finalized_through must be an ISO date")

    if habits and not (20 <= len(habits) <= 30):
        errors.append(f"habit count {len(habits)} outside expected 20..30 range")

    unknown_count = 0
    for index, habit in enumerate(habits):
        name = habit.get("name") or f"habit[{index}]"
        states = habit.get("states")
        completions = habit.get("completions")
        if not isinstance(states, list):
            errors.append(f"{name}: states must be an array")
            states = []
        if not isinstance(completions, list):
            errors.append(f"{name}: completions must be an array")
            completions = []
        if dates and len(states) != len(dates):
            errors.append(f"{name}: states length must match dates")
        if dates and len(completions) != len(dates):
            errors.append(f"{name}: completions length must match dates")
        invalid = sorted({state for state in states if state not in VALID_STATES})
        if invalid:
            errors.append(f"{name}: invalid states {invalid}")
        unknown_count += sum(1 for state in states if state == "unknown")

        if habit.get("numeric"):
            values = habit.get("values")
            progress = habit.get("progress")
            if not isinstance(values, list):
                errors.append(f"{name}: numeric values must be an array")
            elif dates and len(values) != len(dates):
                errors.append(f"{name}: values length must match dates")
            if not isinstance(progress, list):
                errors.append(f"{name}: numeric progress must be an array")
            elif dates and len(progress) != len(dates):
                errors.append(f"{name}: progress length must match dates")

    if data.get("unknown_count") != unknown_count:
        errors.append("unknown_count does not match habit states")
    if unknown_count:
        errors.append(f"unknown_count must be 0 before publishing, got {unknown_count}")

    return errors


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else Path("streaks-data.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_data(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "ok "
        f"schema={data['schema_version']} "
        f"habits={len(data['habits'])} "
        f"dates={data['dates'][0]}..{data['dates'][-1]} "
        f"finalized_through={data['finalized_through']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
