#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync the pk / fk / uq / uqc flags **and ENUM values** in the ERD HTML from
the database.

Each column on the diagram is a four-element array:

    ['role', 'ENUM', 'uq', 'user|admin']
      name    type   flags  ENUM values, separated by |

The fourth element exists only on ENUM and SET columns, and is **always
generated from `information_schema`** rather than typed by hand: 30 ENUM
columns with 108 values will be wrong if copied by hand, and wrong in a silent
way — the diagram still renders perfectly with a value that does not exist.

The flags in `docs/database_erd.html` used to be typed by hand, and they were
wrong in a way that is very hard to spot: `body_logs.logged_on` and
`meal_plans.plan_date` carried a bare `UQ` badge, implying **that column alone
is unique** — that is, that two users could not both log a weight on the same
day. The real constraint is `UNIQUE (user_id, logged_on)`, which allows it
perfectly.

The opposite direction was wrong too: five composite UNIQUE constraints were
not shown at all, so a reader had no idea they existed.

This script reads `information_schema` and rewrites the flags, so the diagram
can no longer drift from the database. Run it again after every schema change.

The four flags:
    pk   primary key
    fk   foreign key
    uq   unique, ONE column
    uqc  unique across a COMBINATION of columns

Run:
    python tools/sync_erd_flags.py            # write into the ERD
    python tools/sync_erd_flags.py --dry-run  # print the differences only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ERD = ROOT / "docs" / "database_erd.html"

# Generated columns keep their `gen` flag — that information is not in the
# constraint tables but in information_schema's `extra`.
KEEP = {"gen"}


def read_enums(database: str) -> dict[tuple[str, str], str]:
    """Each ENUM/SET column's values, joined with `|`.

    Keeps the **declaration order** from the database rather than sorting:
    an ENUM's order is part of its meaning — `severity_min` runs from `mild`
    to `severe`, and MySQL compares ENUMs in that order.
    """
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND DATA_TYPE IN ('enum', 'set')",
                (database,),
            )
            return {
                (table, column): "|".join(
                    re.findall(r"'([^']*)'", column_type)
                )
                for table, column, column_type in cur.fetchall()
            }
    finally:
        conn.close()


def read_keys(database: str) -> dict[tuple[str, str], set[str]]:
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database, charset="utf8mb4",
    )
    flags: dict[tuple[str, str], set[str]] = {}

    try:
        with conn.cursor() as cur:
            # Primary and unique keys. The index's column count decides
            # between `uq` and `uqc`.
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, INDEX_NAME,
                       COUNT(*) OVER (PARTITION BY TABLE_NAME, INDEX_NAME) AS n
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s AND NON_UNIQUE = 0
                """,
                (database,),
            )
            for table, column, index, n in cur.fetchall():
                key = (table, column)
                if index == "PRIMARY":
                    flags.setdefault(key, set()).add("pk")
                else:
                    flags.setdefault(key, set()).add("uq" if n == 1 else "uqc")

            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                """,
                (database,),
            )
            for table, column in cur.fetchall():
                flags.setdefault((table, column), set()).add("fk")
    finally:
        conn.close()

    return flags


def order(flags: set[str]) -> str:
    """A fixed order, so a diff between runs carries no noise."""
    return " ".join(f for f in ("pk", "fk", "uq", "uqc", "gen") if f in flags)


def _use_utf8() -> None:
    """Make stdout accept non-ASCII output on Windows (it defaults to cp1252).

    Without it the script dies mid-run with `UnicodeEncodeError` as soon as
    output is redirected through a pipe or into a file — which is to say
    exactly when running in CI. A copy of `tools/_env.use_utf8`, kept here so
    the script also runs when only `tools/` is importable.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def main() -> int:
    _use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="nutrition_rec")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    live_flags = read_keys(args.database)
    enums = read_enums(args.database)
    html = ERD.read_text(encoding="utf-8")
    changes: list[str] = []

    def patch_table(match: re.Match) -> str:
        table = match.group(1)
        body = match.group(2)

        def patch_col(cm: re.Match) -> str:
            column = cm.group(1)
            column_type = cm.group(2)
            old = set((cm.group(3) or "").split()) - {""}
            old_values = cm.group(4)

            new = set(live_flags.get((table, column), set())) | (old & KEEP)
            if new != old:
                changes.append(
                    f"  {table}.{column:<22} flags "
                    f"[{order(old) or '-'}] -> [{order(new) or '-'}]"
                )

            values = enums.get((table, column))
            if (values or "") != (old_values or ""):
                changes.append(
                    f"  {table}.{column:<22} ENUM "
                    f"[{old_values or '-'}] -> [{values or '-'}]"
                )

            tail = f",'{values}'" if values else ""
            return f"['{column}','{column_type}','{order(new)}'{tail}]"

        patched = re.sub(
            r"\['(\w+)','([^']*)'(?:,'([^']*)')?(?:,'([^']*)')?\]",
            patch_col,
            body,
        )
        return match.group(0).replace(body, patched)

    out = re.sub(
        r"\{ id:'(\w+)'.*?cols:\[(.*?)\]\s*\}", patch_table, html, flags=re.S
    )

    if not changes:
        print(
            "The ERD's flags and ENUM values already match the database; "
            "nothing to change."
        )
        return 0

    print(f"{len(changes)} things to change:\n")
    for line in changes:
        print(line)

    if args.dry_run:
        print("\n(--dry-run: no file written)")
        return 1

    ERD.write_text(out, encoding="utf-8")
    print(f"\nWrote -> {ERD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
