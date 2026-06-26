#!/usr/bin/env python3
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path


START = date(2026, 3, 23)
# Only publish completed days; today's Streaks/HealthKit totals are still in flux.
END = date.today() - timedelta(days=1)
BATCH_THRESHOLD = 3
NUMERIC_UNITS = {"grams", "floz_us", "kcal", "hours", "seconds"}

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = (
    Path.home()
    / "Library/Group Containers/group.com.streaksapp.streak.today/Streaks-CloudKit.sqlite"
)
OUTPUT_PATH = SCRIPT_DIR / "streaks-data.json"
INDEX_PATH = SCRIPT_DIR / "index.html"


def date_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def db_uri():
    return f"file:{DB_PATH}?mode=ro"


def as_date_int(day):
    return int(day.strftime("%Y%m%d"))


def batch_key(timestamp):
    if timestamp is None:
        return None
    return int(float(timestamp))


def is_numeric(task):
    target = task["target"]
    unit = task["unit"] or ""
    return target is not None and target > 0 and unit in NUMERIC_UNITS


def value_is_done(value, target, is_negative):
    if value is None or target is None:
        return None
    if is_negative:
        return 1 if value <= target else 0
    if value <= 0:
        return None
    return 1 if value >= target else 0


def load_tasks(conn):
    rows = conn.execute(
        """
        SELECT
          t.Z_PK,
          t.ZTITLE,
          COALESCE(t.ZSTATUS, '') AS ZSTATUS,
          COALESCE(t.ZDISPLAYORDER, 0) AS ZDISPLAYORDER,
          COALESCE(t.ZTYPENAME, '') AS ZTYPENAME,
          t.ZTYPETARGET,
          COALESCE(t.ZTYPEUNIT, '') AS ZTYPEUNIT,
          COALESCE(t.ZISNEGATIVE, 0) AS ZISNEGATIVE,
          COALESCE(t.ZDAYSMODE, 0) AS ZDAYSMODE,
          COALESCE(t.ZDAYSOFWEEK, 127) AS ZDAYSOFWEEK,
          COALESCE(t.ZDAYSPERWEEK, 0) AS ZDAYSPERWEEK,
          COALESCE(group_concat(c.ZTITLE, '|'), '') AS categories
        FROM ZTASK t
        LEFT JOIN Z_4TASKCATEGORIES tc ON tc.Z_4TASKS = t.Z_PK
        LEFT JOIN ZTASKCATEGORY c ON c.Z_PK = tc.Z_5TASKCATEGORIES
        WHERE t.ZSTATUS = 'N'
        GROUP BY t.Z_PK
        ORDER BY t.ZDISPLAYORDER, t.Z_PK
        """
    ).fetchall()

    tasks = []
    for row in rows:
        category = row["categories"].split("|", 1)[0] if row["categories"] else ""
        tasks.append(
            {
                "pk": row["Z_PK"],
                "name": row["ZTITLE"],
                "category": category or "Uncategorized",
                "order": int(row["ZDISPLAYORDER"]),
                "typename": row["ZTYPENAME"] or "",
                "target": float(row["ZTYPETARGET"])
                if row["ZTYPETARGET"] is not None
                else None,
                "unit": row["ZTYPEUNIT"] or "",
                "is_negative": bool(row["ZISNEGATIVE"]),
                # Streaks schedule: ZDAYSMODE 0 + all 7 weekdays (127) = daily;
                # anything else (X-times-per-week, specific weekdays) = weekly cadence.
                "schedule": (
                    "daily"
                    if int(row["ZDAYSMODE"]) == 0 and int(row["ZDAYSOFWEEK"]) == 127
                    else "weekly"
                ),
            }
        )
    return tasks


def load_entries(conn, start_int, end_int):
    rows = conn.execute(
        """
        SELECT
          ZTASK,
          ZENTRYDATE,
          ZENTRYTYPE,
          ZPROGRESS,
          ZPROGRESSTOTAL,
          ZCREATEDTIMESTAMP,
          ZUNIQUEID
        FROM ZTASKLOGENTRY
        WHERE ZENTRYDATE BETWEEN ? AND ?
        ORDER BY ZTASK, ZENTRYDATE, ZENTRYTYPE, Z_PK
        """,
        (start_int, end_int),
    ).fetchall()

    entries = defaultdict(list)
    batch_counts = defaultdict(Counter)

    for row in rows:
        task_id = row["ZTASK"]
        entry = {
            "date": row["ZENTRYDATE"],
            "type": row["ZENTRYTYPE"],
            "progress": row["ZPROGRESS"],
            "total": row["ZPROGRESSTOTAL"],
            "created": row["ZCREATEDTIMESTAMP"],
            "unique_id": row["ZUNIQUEID"],
        }
        entries[(task_id, row["ZENTRYDATE"])].append(entry)
        if row["ZENTRYTYPE"] == 5:
            key = batch_key(row["ZCREATEDTIMESTAMP"])
            if key is not None:
                batch_counts[task_id][key] += 1

    batch_keys = {
        task_id: {
            key
            for key, count in counts.items()
            if count >= BATCH_THRESHOLD
        }
        for task_id, counts in batch_counts.items()
    }
    return entries, batch_keys


def healthkit_value(entries):
    samples = set()
    total = 0.0
    progress = 0.0

    for entry in entries:
        if entry["type"] != 15:
            continue
        sample_total = float(entry["total"] or 0)
        sample_progress = float(entry["progress"] or 0)
        # Streaks duplicates HealthKit samples with new row IDs/timestamps.
        sample_key = (round(sample_total, 6), round(sample_progress, 9))
        if sample_key in samples:
            continue
        samples.add(sample_key)
        total += sample_total
        progress += sample_progress

    if not samples:
        return None, None
    return total, progress


def non_healthkit_value(entries):
    totals = [
        float(entry["total"] or 0)
        for entry in entries
        if entry["type"] in {1, 6} and float(entry["total"] or 0) > 0
    ]
    if not totals:
        return None
    return max(totals)


def day_status(task, entries, batch_keys):
    has_manual_done = any(entry["type"] == 1 for entry in entries)
    has_manual_miss = any(entry["type"] == 2 for entry in entries)
    has_timer = any(entry["type"] == 6 for entry in entries)

    legit_retro = False
    for entry in entries:
        if entry["type"] != 5:
            continue
        key = batch_key(entry["created"])
        if key is not None and key not in batch_keys:
            legit_retro = True
            break

    hk_total, hk_progress = healthkit_value(entries)
    value = hk_total
    if value is None and is_numeric(task):
        value = non_healthkit_value(entries)

    if has_manual_done:
        return 1, value
    if is_numeric(task) and task["is_negative"] and hk_total is not None:
        # Streaks writes type-2 rollover rows for HealthKit limits even when
        # the final lower-is-better value is within target.
        value_done = value_is_done(value, task["target"], task["is_negative"])
        return value_done if value_done is not None else -1, value
    if has_manual_miss:
        return 0, value

    if is_numeric(task) and value is not None:
        progress_done = (
            None
            if hk_progress is None
            else (1 if hk_progress >= 1.0 else 0)
        )
        value_done = value_is_done(value, task["target"], task["is_negative"])
        if task["is_negative"]:
            return value_done if value_done is not None else -1, value
        if progress_done == 1 or value_done == 1:
            return 1, value
        if value > 0:
            return 0, value
        return -1, value

    if legit_retro or has_timer:
        return 1, value

    return -1, value


def build_data():
    dates = list(date_range(START, END))
    date_strings = [day.isoformat() for day in dates]
    date_ints = [as_date_int(day) for day in dates]

    conn = sqlite3.connect(db_uri(), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tasks = load_tasks(conn)
        entries, all_batch_keys = load_entries(conn, date_ints[0], date_ints[-1])
    finally:
        conn.close()

    habits = []
    for task in tasks:
        completions = []
        values = []
        done = 0
        missed = 0

        task_batch_keys = all_batch_keys.get(task["pk"], set())
        for date_int in date_ints:
            day_entries = entries.get((task["pk"], date_int), [])
            if not day_entries:
                status, value = -1, None
            else:
                status, value = day_status(task, day_entries, task_batch_keys)

            completions.append(status)
            if status == 1:
                done += 1
            elif status == 0:
                missed += 1

            if is_numeric(task):
                values.append(round(value, 1) if value is not None else None)

        habit = {
            "name": task["name"],
            "category": task["category"],
            "order": task["order"],
            "schedule": task["schedule"],
            "completions": completions,
            "done": done,
            "missed": missed,
            "logged": done + missed,
        }
        if is_numeric(task):
            numeric_fields = {
                "numeric": True,
                "unit": task["unit"],
                "target": task["target"],
                "values": values,
            }
            if task["is_negative"]:
                numeric_fields["is_negative"] = True
            habit.update(numeric_fields)
        habits.append(habit)

    return {"dates": date_strings, "habits": habits}


def write_json(data):
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def inject_index(data):
    lines = INDEX_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    replacement = (
        "const D = "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )

    for index, line in enumerate(lines):
        if line.lstrip().startswith("const D = "):
            lines[index] = replacement
            INDEX_PATH.write_text("".join(lines), encoding="utf-8")
            return

    raise ValueError("index.html does not contain a const D assignment")


def main():
    data = build_data()
    write_json(data)
    inject_index(data)

    print(
        f"Extracted {len(data['habits'])} habits from SQLite: "
        f"{data['dates'][0]}..{data['dates'][-1]} ({len(data['dates'])} days)"
    )
    for habit in data["habits"]:
        rate = (
            f"{habit['done'] / habit['logged'] * 100:.0f}%"
            if habit["logged"]
            else "N/A"
        )
        print(f"  {habit['name']:<38s} {rate:>5s} logged={habit['logged']}")


if __name__ == "__main__":
    main()
