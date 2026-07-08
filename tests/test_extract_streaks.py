import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import extract_streaks
import validate_streaks_data


def entry(entry_type, total=0, progress=0, created=100):
    return {
        "date": 20260706,
        "type": entry_type,
        "progress": progress,
        "total": total,
        "created": created,
        "unique_id": f"{entry_type}-{total}-{progress}-{created}",
    }


def task(target=None, unit="", is_negative=False):
    return {
        "target": target,
        "unit": unit,
        "is_negative": is_negative,
    }


class DayStateTests(unittest.TestCase):
    def test_manual_done_is_complete(self):
        state, value, progress, unknown = extract_streaks.day_state(
            task(), [entry(1)], set()
        )
        self.assertEqual(state, "complete")
        self.assertIsNone(value)
        self.assertIsNone(progress)
        self.assertEqual(unknown, [])

    def test_manual_miss_is_missed(self):
        state, *_ = extract_streaks.day_state(task(), [entry(2)], set())
        self.assertEqual(state, "missed")

    def test_auto_backfill_is_incomplete(self):
        state, *_ = extract_streaks.day_state(task(), [entry(4)], set())
        self.assertEqual(state, "incomplete")

    def test_non_batch_retro_is_complete(self):
        state, *_ = extract_streaks.day_state(task(), [entry(5, created=123)], set())
        self.assertEqual(state, "complete")

    def test_batch_retro_is_incomplete(self):
        state, *_ = extract_streaks.day_state(
            task(), [entry(5, created=123)], {123}
        )
        self.assertEqual(state, "incomplete")

    def test_timer_is_complete(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=1200, unit="seconds"), [entry(6, total=1200)], set()
        )
        self.assertEqual(state, "complete")
        self.assertEqual(value, 1200)

    def test_positive_healthkit_above_target_is_complete(self):
        state, value, progress, *_ = extract_streaks.day_state(
            task(target=180, unit="grams"),
            [entry(15, total=200, progress=200 / 180)],
            set(),
        )
        self.assertEqual(state, "complete")
        self.assertEqual(value, 200)
        self.assertGreater(progress, 1)

    def test_positive_healthkit_below_target_is_missed(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=180, unit="grams"),
            [entry(15, total=100, progress=100 / 180)],
            set(),
        )
        self.assertEqual(state, "missed")
        self.assertEqual(value, 100)

    def test_positive_healthkit_uses_value_not_progress_for_completion(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=180, unit="grams"),
            [entry(15, total=100, progress=1.1)],
            set(),
        )
        self.assertEqual(state, "missed")
        self.assertEqual(value, 100)

    def test_positive_healthkit_zero_is_incomplete(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=180, unit="grams"), [entry(15, total=0, progress=0)], set()
        )
        self.assertEqual(state, "incomplete")
        self.assertEqual(value, 0)

    def test_negative_healthkit_under_limit_is_complete_despite_rollover_miss(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=2500, unit="kcal", is_negative=True),
            [entry(2), entry(15, total=2200, progress=0.88)],
            set(),
        )
        self.assertEqual(state, "complete")
        self.assertEqual(value, 2200)

    def test_negative_healthkit_over_limit_is_missed(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=2500, unit="kcal", is_negative=True),
            [entry(15, total=2800, progress=1.12)],
            set(),
        )
        self.assertEqual(state, "missed")
        self.assertEqual(value, 2800)

    def test_duplicate_healthkit_samples_are_deduped(self):
        state, value, *_ = extract_streaks.day_state(
            task(target=100, unit="floz_us"),
            [
                entry(15, total=60, progress=0.6, created=1),
                entry(15, total=60, progress=0.6, created=2),
            ],
            set(),
        )
        self.assertEqual(state, "missed")
        self.assertEqual(value, 60)

    def test_unproven_entry_type_is_unknown(self):
        state, value, progress, unknown = extract_streaks.day_state(
            task(), [entry(7)], set()
        )
        self.assertEqual(state, "unknown")
        self.assertIsNone(value)
        self.assertIsNone(progress)
        self.assertEqual(unknown, [7])

    def test_finalized_end_excludes_today(self):
        self.assertEqual(
            extract_streaks.finalized_end(date(2026, 7, 7)),
            date(2026, 7, 6),
        )


class ValidateDataTests(unittest.TestCase):
    def valid_data(self):
        return {
            "schema_version": 2,
            "generated_at": "2026-07-08T17:00:00+00:00",
            "finalized_through": "2026-07-07",
            "source": {
                "kind": "streaks_sqlite",
                "db_mtime": "2026-07-08T16:00:00+00:00",
            },
            "dates": ["2026-07-06", "2026-07-07"],
            "unknown_count": 0,
            "habits": [
                {
                    "name": f"Habit {index}",
                    "states": ["complete", "missed"],
                    "completions": [1, 0],
                }
                for index in range(20)
            ],
        }

    def test_valid_schema_passes(self):
        errors = validate_streaks_data.validate_data(
            self.valid_data(), today=date(2026, 7, 8)
        )
        self.assertEqual(errors, [])

    def test_unknown_state_blocks_publish(self):
        data = self.valid_data()
        data["habits"][0]["states"][1] = "unknown"
        data["habits"][0]["completions"][1] = -1
        data["unknown_count"] = 1
        errors = validate_streaks_data.validate_data(data, today=date(2026, 7, 8))
        self.assertIn("unknown_count must be 0 before publishing, got 1", errors)

    def test_today_is_not_finalized(self):
        data = self.valid_data()
        errors = validate_streaks_data.validate_data(data, today=date(2026, 7, 7))
        self.assertIn("finalized_through must be before today", errors)


if __name__ == "__main__":
    unittest.main()
