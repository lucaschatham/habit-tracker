#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path


DEFAULT_DB = (
    Path.home()
    / "Library/Group Containers/group.com.streaksapp.streak.today/Streaks-CloudKit.sqlite"
)
KNOWN_TYPES = {1, 2, 4, 5, 6, 15}


def date_int(value):
    return int(value.replace("-", ""))


def connect(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def print_rows(rows):
    for row in rows:
        print(
            f"type={row['type']} count={row['count']} "
            f"first={row['first_date']} last={row['last_date']}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Audit Streaks SQLite log entry types without guessing state mappings."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2026-03-23")
    parser.add_argument("--end")
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args()

    clauses = ["e.ZENTRYDATE >= ?"]
    params = [date_int(args.start)]
    if args.end:
        clauses.append("e.ZENTRYDATE <= ?")
        params.append(date_int(args.end))
    where = " AND ".join(clauses)

    with connect(args.db) as conn:
        rows = conn.execute(
            f"""
            SELECT
              e.ZENTRYTYPE AS type,
              COUNT(*) AS count,
              MIN(e.ZENTRYDATE) AS first_date,
              MAX(e.ZENTRYDATE) AS last_date
            FROM ZTASKLOGENTRY e
            JOIN ZTASK t ON t.Z_PK = e.ZTASK
            WHERE {where} AND t.ZSTATUS = 'N'
            GROUP BY e.ZENTRYTYPE
            ORDER BY e.ZENTRYTYPE
            """,
            params,
        ).fetchall()

        print("Entry type summary for active tasks")
        print_rows(rows)

        unknown_types = [row["type"] for row in rows if row["type"] not in KNOWN_TYPES]
        if not unknown_types:
            print("\nNo unproven entry types in range.")
            return 0

        print("\nUnproven entry type samples")
        for entry_type in unknown_types:
            samples = conn.execute(
                f"""
                SELECT
                  e.ZENTRYTYPE AS type,
                  e.ZENTRYDATE AS date,
                  t.ZDISPLAYORDER AS task_order,
                  t.ZTITLE AS title,
                  e.ZPROGRESSTOTAL AS total,
                  e.ZPROGRESS AS progress,
                  e.ZCREATEDTIMESTAMP AS created
                FROM ZTASKLOGENTRY e
                JOIN ZTASK t ON t.Z_PK = e.ZTASK
                WHERE {where} AND t.ZSTATUS = 'N' AND e.ZENTRYTYPE = ?
                ORDER BY e.ZENTRYDATE DESC, t.ZDISPLAYORDER
                LIMIT ?
                """,
                [*params, entry_type, args.samples],
            ).fetchall()
            for row in samples:
                print(
                    f"type={row['type']} date={row['date']} "
                    f"order={row['task_order']} task={row['title']} "
                    f"total={row['total']} progress={row['progress']} "
                    f"created={row['created']}"
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
