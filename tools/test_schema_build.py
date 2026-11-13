#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build `db/schema.sql` + `db/seed.sql` into a throwaway database, then check it.

Why this needs its own tool instead of running the schema file directly:
**`db/schema.sql` opens with `DROP DATABASE IF EXISTS nutrition_rec`**. It is a
rebuild-from-scratch script, so running it to "see whether the schema is right"
wipes the working database.

This happened for real once: a rebuild test believed to be running against a
scratch database deleted 305 dishes from the real one, because the `USE
nutrition_rec` statement at the top of the file silently moved the connection
there regardless of the `database=` connection parameter. Nothing was lost that
time — every dish rebuilds from `data/foods/*.csv` — but once the database
holds real user data there will be no such luck.

This tool renames the database inside both files before running them, and then
**verifies that the connection really is on the scratch database** before
measuring anything. That verification matters as much as the renaming: if the
rename did not take, every number below still comes back correct because it is
measuring the real database, and the test turns out meaningless while looking
like it passed.

What it checks:
  - scale: table count, foreign-key columns, CHECK constraints, total columns
  - no UNIQUE key contains a nullable column any more (see migration 003)
  - no identifier carries Vietnamese diacritics (an ERD assignment requirement)
  - the seed loads and the lookup tables hold the right number of rows

Run:
    python tools/test_schema_build.py
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _env  # noqa: E402

# Reuse `run_sql.py`'s statement splitter rather than keeping a second copy.
# Two copies drift: fix an odd case in one and the other stays wrong, while
# both run against the same database.
from run_sql import split_statements  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
SEED = ROOT / "db" / "seed.sql"
SANDBOX = "nutrition_rec_buildtest"

# The expected figures. Compared rather than merely printed, because an
# unintended schema change usually moves exactly one number — printed, that is
# very easy to read past.
EXPECTED = {
    "tables": 24,
    "fk_columns": 32,
    "checks": 18,
    "columns": 225,
}

LOOKUP_ROWS = {
    "food_categories": 12,
    "tags": 13,
    "conditions": 13,
    "condition_rules": 20,
    "rda_reference": 12,
}


def read_env() -> dict[str, str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        sys.exit("No .env file yet")
    return dict(
        re.findall(r"^(\w+)=(.*)$", env_file.read_text(encoding="utf-8"), re.M)
    )


def rename_database(text: str, real: str) -> str:
    """Point the file at the scratch database.

    Matches on a word boundary; without it, `nutrition_rec_buildtest` would be
    renamed a second time on the later matches.
    """
    return re.compile(rf"\b{re.escape(real)}\b").sub(SANDBOX, text)


def assert_no_real_db(label: str, text: str, real: str) -> None:
    """The last safety gate: no DROP DATABASE / USE statement still points at
    the real database."""
    for line in text.split("\n"):
        upper = line.upper().strip()
        touches = "DROP DATABASE" in upper or upper.startswith("USE ")
        if touches and re.search(rf"\b{re.escape(real)}\b", line):
            sys.exit(
                f"{label} still has a statement pointing at the real database "
                f"after renaming — stopping:\n  {line.strip()}"
            )


def main() -> int:
    _env.use_utf8()
    try:
        import pymysql
    except ImportError:
        sys.exit("pymysql is required:  pip install pymysql")

    env = read_env()
    real_db = env.get("MYSQL_DATABASE", "nutrition_rec")

    if SANDBOX == real_db:
        sys.exit(
            f"The scratch database has the same name as the real one "
            f"({real_db}) — continuing would delete real data. Stopping."
        )

    schema_sql = rename_database(SCHEMA.read_text(encoding="utf-8"), real_db)
    seed_sql = rename_database(SEED.read_text(encoding="utf-8"), real_db)
    assert_no_real_db("schema.sql", schema_sql, real_db)
    assert_no_real_db("seed.sql", seed_sql, real_db)

    print("=" * 70)
    print(f"BUILDING THE SCHEMA INTO THE SCRATCH DATABASE  {SANDBOX}")
    print(f"(the real database {real_db} is not touched)")
    print("=" * 70)

    connect = dict(
        host=env.get("MYSQL_HOST", "localhost"),
        port=int(env.get("MYSQL_PORT", "3306")),
        user=env["MYSQL_USER"],
        password=env["MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
    )

    connection = pymysql.connect(**connect)
    failures: list[str] = []

    try:
        with connection.cursor() as cursor:
            for label, text in (
                ("schema.sql", schema_sql),
                ("seed.sql", seed_sql),
            ):
                statements = split_statements(text)
                errors = 0
                for number, statement in enumerate(statements, start=1):
                    try:
                        cursor.execute(statement)
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        failures.append(f"{label} statement {number}: {exc}")
                        print(f"  BAD  statement {number}: {exc}")
                        if errors > 3:
                            break
                print(f"{label}: {len(statements)} statements, {errors} errors")

            cursor.execute("SELECT DATABASE()")
            current = cursor.fetchone()[0]
            if current != SANDBOX:
                sys.exit(
                    f"The connection is on database {current!r}, not "
                    f"{SANDBOX!r}. Stopping, so as not to measure the real "
                    f"database by mistake."
                )
            print(f"\non database: {current}")

            # -- Scale --
            cursor.execute("SHOW TABLES")
            measured = {"tables": len(cursor.fetchall())}

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND REFERENCED_TABLE_NAME IS NOT NULL"
            )
            measured["fk_columns"] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'CHECK'"
            )
            measured["checks"] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE()"
            )
            measured["columns"] = cursor.fetchone()[0]

            print("\nScale:")
            for key, want in EXPECTED.items():
                got = measured[key]
                mark = "ok " if got == want else "BAD"
                print(f"  {mark} {key:<12}{got:>5}   (expected {want})")
                if got != want:
                    failures.append(f"{key}: measured {got}, expected {want}")

            # -- UNIQUE keys defeated by NULL --
            cursor.execute(
                "SELECT s.TABLE_NAME, s.INDEX_NAME,"
                "       GROUP_CONCAT(CASE WHEN s.NULLABLE = 'YES'"
                "                    THEN s.COLUMN_NAME END"
                "                    ORDER BY s.SEQ_IN_INDEX) AS nullable_cols"
                "  FROM information_schema.STATISTICS s"
                " WHERE s.TABLE_SCHEMA = DATABASE() AND s.NON_UNIQUE = 0"
                " GROUP BY s.TABLE_NAME, s.INDEX_NAME"
                " HAVING nullable_cols IS NOT NULL"
            )
            leaky = cursor.fetchall()
            print(f"\nUNIQUE keys containing a nullable column: {len(leaky)}")
            for table, index, columns in leaky:
                print(f"  BAD  {table}.{index} — nullable columns: {columns}")
                failures.append(
                    f"{table}.{index} does not prevent duplicates because "
                    f"column {columns} is nullable"
                )
            if not leaky:
                print("  ok   no key is defeated by NULL any more")

            # -- Vietnamese diacritics in identifiers --
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
            )
            identifiers: set[str] = set()
            for table, column in cursor.fetchall():
                identifiers.add(table)
                identifiers.add(column)

            accented = sorted(n for n in identifiers if not n.isascii())
            print(
                f"\nIdentifiers: {len(identifiers)} names, "
                f"{len(accented)} with diacritics"
            )
            if accented:
                for name in accented:
                    print(f"  BAD  {name}")
                failures.append(
                    f"{len(accented)} identifiers carry Vietnamese diacritics"
                )
            else:
                print(
                    "  ok   no name carries diacritics — as the ERD assignment "
                    "requires"
                )

            # -- Seed --
            print("\nLookup tables after seeding:")
            for table, want in LOOKUP_ROWS.items():
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                got = cursor.fetchone()[0]
                mark = "ok " if got == want else "BAD"
                print(f"  {mark} {table:<18}{got:>4}   (expected {want})")
                if got != want:
                    failures.append(f"{table}: {got} rows, expected {want}")
    finally:
        # Clean up on a separate connection: the open one is sitting inside
        # the very database about to be dropped.
        cleanup = pymysql.connect(**connect)
        with cleanup.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {SANDBOX}")
        cleanup.close()
        connection.close()
        print(f"\n(dropped the scratch database {SANDBOX})")

    print("\n" + "=" * 70)
    if failures:
        print(f"{len(failures)} problems:\n")
        for item in failures:
            print(f"  BAD  {item}")
    else:
        print("THE SCHEMA REBUILDS FROM SCRATCH — no problems found.")
    print("=" * 70)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
