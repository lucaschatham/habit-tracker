import json, re
from datetime import datetime, timedelta
from collections import Counter

import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_PATH = os.path.join(SCRIPT_DIR, "latest.streaks")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "streaks-data.json")

START = datetime(2026, 3, 23)
END = datetime(2026, 4, 9)
dates = []
d = START
while d <= END:
    dates.append(d.strftime("%Y-%m-%d"))
    d += timedelta(days=1)
date_ints = [int(d.replace("-", "")) for d in dates]
date_int_set = set(date_ints)

with open(BACKUP_PATH) as f:
    data = json.load(f)

cat_map = {}
for c in data.get("categories", []):
    cat_map[c["id"]] = c["t"]

NUMERIC_UNITS = {"grams", "floz_us", "kcal", "hours", "seconds"}
BATCH_THRESHOLD = 3

def clean_tf_name(tf):
    if not tf:
        return "Unknown"
    m = re.match(r'^(.+?),\s*(\d+:\d+(?::\d+)?|\d+(?:\.\d+)?(?:g|oz|kcal|hours?|hrs?|mins?|seconds?|lbs?))$', tf, re.I)
    if m:
        return m.group(1).strip()
    return tf.strip()

# Regex to match trailing emojis (common emoji unicode ranges)
EMOJI_RE = re.compile(
    r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0000200D\U00002600-\U000026FF]+\s*$'
)

def strip_trailing_emoji(name):
    """Remove trailing emojis from a name to avoid duplication."""
    return EMOJI_RE.sub('', name).strip()

def get_icon_emoji(task):
    """Extract emoji from the 'i' field (format: 'em_EMOJI')."""
    icon = task.get('i', '')
    if icon.startswith('em_'):
        return icon[3:]
    return ''

def find_batch_timestamps(log_entries):
    t5_entries = [e for e in log_entries if e.get("t") == 5]
    ts_counts = Counter(e.get("ts", "none") for e in t5_entries)
    return {ts for ts, count in ts_counts.items() if count >= BATCH_THRESHOLD}

habits = []
app_order = 0

for task in data["tasks"]:
    if task.get("st") != "N":
        continue

    name = task.get("t")
    if not isinstance(name, str) or not name:
        name = clean_tf_name(task.get("tf", ""))

    # Strip trailing emojis only (names already have leading emojis)
    name = strip_trailing_emoji(name)
    # If name has no leading emoji, prepend icon emoji
    if name and not any(ord(c) > 0x2000 for c in name[:2]):
        icon = get_icon_emoji(task)
        if icon:
            name = icon + ' ' + name

    cat_ids = task.get("cat", [])
    category = "Uncategorized"
    for cid in cat_ids:
        if cid in cat_map:
            category = cat_map[cid]
            break

    target = task.get("tyt")
    unit = task.get("tyu", "")
    is_numeric = bool(target and unit in NUMERIC_UNITS)

    if target:
        try:
            target = float(target)
        except (ValueError, TypeError):
            target = None
            is_numeric = False

    # typ/typd: Streaks app's own HealthKit total for one day (authoritative)
    hk_today_val = task.get("typ", 0)
    hk_today_date = task.get("typd", 0)

    log = task.get("log", [])
    batch_ts = find_batch_timestamps(log)

    day_entries = {}
    for entry in log:
        ed = entry.get("d")
        if ed and ed in date_int_set:
            if ed not in day_entries:
                day_entries[ed] = []
            day_entries[ed].append(entry)

    completions = []
    values_list = []
    done_count = 0
    missed_count = 0
    logged_count = 0

    for i, date_int in enumerate(date_ints):
        entries = day_entries.get(date_int, [])

        if not entries:
            completions.append(-1)
            values_list.append(None)
            continue

        has_manual_done = any(e["t"] == 1 for e in entries)
        has_manual_miss = any(e["t"] == 2 for e in entries)
        has_legit_retro = any(
            e["t"] == 5 and e.get("ts") and e["ts"] not in batch_ts
            for e in entries
        )
        has_auto_backfill = any(e["t"] == 4 for e in entries)
        has_timer = any(e["t"] == 6 for e in entries)
        hk_entries = [e for e in entries if e["t"] == 15]

        if is_numeric and hk_entries:
            # Use Streaks app's own authoritative total for the day it computed (typ/typd).
            # For all other days, deduplicate t=15 entries by unique p value.
            # Streaks writes duplicate t=15 entries (2-3x per item with identical p values
            # but different IDs). p-value dedup is close but can slightly undercount if
            # two genuinely different items have the exact same value.
            if hk_today_val and date_int == hk_today_date:
                day_total = float(hk_today_val)
            else:
                seen_p = set()
                deduped_values = []
                for e in hk_entries:
                    p = e.get("p", 0)
                    if p not in seen_p:
                        seen_p.add(p)
                        deduped_values.append(p)
                day_total = sum(deduped_values)
            values_list.append(round(day_total, 1) if day_total else None)

            if has_manual_done:
                completions.append(1); done_count += 1; logged_count += 1
            elif has_manual_miss:
                completions.append(0); missed_count += 1; logged_count += 1
            elif target and day_total >= target:
                completions.append(1); done_count += 1; logged_count += 1
            elif day_total > 0:
                completions.append(0); missed_count += 1; logged_count += 1
            else:
                completions.append(-1)
        else:
            values_list.append(None)
            if has_manual_done:
                completions.append(1); done_count += 1; logged_count += 1
            elif has_manual_miss:
                completions.append(0); missed_count += 1; logged_count += 1
            elif has_legit_retro:
                completions.append(1); done_count += 1; logged_count += 1
            elif has_timer:
                completions.append(1); done_count += 1; logged_count += 1
            elif has_auto_backfill:
                completions.append(-1)
            else:
                completions.append(-1)

    habit_data = {
        "name": name,
        "category": category,
        "order": app_order,
        "completions": completions,
        "done": done_count,
        "missed": missed_count,
        "logged": logged_count,
    }
    app_order += 1

    if is_numeric:
        habit_data["numeric"] = True
        habit_data["unit"] = unit
        habit_data["target"] = target
        habit_data["values"] = values_list

    habits.append(habit_data)

output = {"habits": habits, "dates": dates}

with open(OUTPUT_PATH, "w") as f:
    json.dump(output, f)

print(f"Extracted {len(habits)} habits:\n")
for h in habits:
    rate = f"{h['done']/h['logged']*100:.0f}%" if h['logged'] > 0 else "N/A"
    print(f"  {h['name']:<45s} {rate:>5s}")

