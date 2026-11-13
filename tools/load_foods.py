#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load the food dataset from CSV into MySQL.

One CSV row does not load into one table; it splits three ways:

    foods           <- identity, classification, role in the meal
    food_nutrition  <- 15 nutrition columns, one-to-one with foods
    food_tags       <- one row per tag, joined through the tags table

That is why `LOAD DATA INFILE` is unusable: `category_id` and `tag_id` have to
be resolved from their codes, and the inserts have to run in dependency order
inside one transaction.

Two modes:

    python tools/load_foods.py               -> write db/seed_foods.sql to review
    python tools/load_foods.py --apply       -> connect and insert for real

Generating SQL is the default on purpose. The first load should be read with
your own eyes before running, and the SQL file also runs on another machine
that has no Python.

Prerequisites:
    db/migrations/001_dataset_readiness.sql
    db/migrations/002_food_name_unique.sql
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FOODS_DIR = ROOT / "data" / "foods"
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATION_001 = ROOT / "db" / "migrations" / "001_dataset_readiness.sql"
OUT_SQL = ROOT / "db" / "seed_foods.sql"


def required_nutrition_columns() -> set[str]:
    """`food_nutrition`'s NOT NULL columns, minus those migration 001 relaxed.

    Read from the schema rather than hard-listed: the schema still changes,
    and a hand-copied list drifts without warning. The consequence would be
    the loader letting an incomplete row through and the whole transaction
    failing halfway.
    """
    body = re.search(
        r"CREATE TABLE food_nutrition\s*\((.*?)\n\) ENGINE",
        SCHEMA.read_text(encoding="utf-8"),
        re.S,
    )
    if not body:
        return set()

    required = set()
    for line in body.group(1).split("\n"):
        line = line.split("--")[0].strip().rstrip(",")
        if not line or line.upper().startswith(
            ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT")
        ):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and "NOT NULL" in parts[1].upper():
            required.add(parts[0])

    # Migration 001 made these four columns nullable.
    if MIGRATION_001.exists():
        text = MIGRATION_001.read_text(encoding="utf-8")
        for column in re.findall(r"MODIFY (\w+)\s+DECIMAL\([\d, ]+\) NULL", text):
            required.discard(column)

    return required - {"food_id", "updated_at"}


FOOD_COLUMNS = [
    "name", "description",
    "spice_level", "dish_role",
]

# Foods loaded from CSV always belong to the SHARED CATALOGUE, so `owner_id`
# stays NULL.
#
# It has to be stated explicitly in the INSERT: `uq_food_name` is a key on the
# pair (owner_id, name); omitting the column means ON DUPLICATE KEY UPDATE
# cannot match the existing row, and a second load would duplicate every food.
#
# Every subquery resolving a `food_id` must carry `owner_id IS NULL` too,
# otherwise it will one day pick up a user's private food that happens to
# share a name with a shared one.
PUBLIC_CATALOG = "NULL"

NUTRITION_COLUMNS = [
    "serving_size_g", "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg", "purine_mg",
    "calcium_mg", "iron_mg", "zinc_mg", "vitamin_a_mcg", "vitamin_c_mg",
]

# CSV column -> table column, where the two names differ.
RENAME = {"note": "description"}

TEXT_COLUMNS = {
    "name", "description", "dish_role",
}


def quote(value: str) -> str:
    """A string for MySQL. Escapes quotes and backslashes."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def sql_value(column: str, raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return "NULL"
    if column in TEXT_COLUMNS:
        return quote(raw)
    return raw


def read_rows() -> list[dict]:
    rows = []
    for path in sorted(FOODS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if not any(v.strip() for v in row.values()):
                    continue
                if not row.get("name", "").strip():
                    continue
                row["_origin"] = f"{path.name}:{lineno}"
                rows.append(row)
    return rows


def statements_for(row: dict) -> list[str]:
    """Build the statements for one food."""
    name = row["name"].strip()
    out = []

    # -- foods --
    # `category_id` is resolved with a subquery rather than a hard-coded
    # number: ids come from AUTO_INCREMENT and therefore differ between
    # rebuilds of the database, while the category code is fixed.
    values = []
    for column in FOOD_COLUMNS:
        csv_col = next((k for k, v in RENAME.items() if v == column), column)
        values.append(sql_value(column, row.get(csv_col, "")))

    out.append(
        "INSERT INTO foods (category_id, owner_id, {cols})\n"
        "VALUES ((SELECT id FROM food_categories WHERE name = {cat}), "
        "{owner}, {vals})\n"
        "ON DUPLICATE KEY UPDATE\n"
        "    category_id = VALUES(category_id),\n"
        "    {updates};".format(
            cols=", ".join(FOOD_COLUMNS),
            cat=quote(row["category"].strip()),
            owner=PUBLIC_CATALOG,
            vals=", ".join(values),
            updates=",\n    ".join(
                f"{c} = VALUES({c})" for c in FOOD_COLUMNS if c != "name"
            ),
        )
    )

    # -- food_nutrition --
    # `food_id` is UNIQUE, so ON DUPLICATE KEY UPDATE updates the right row.
    nut_values = [sql_value(c, row.get(c, "")) for c in NUTRITION_COLUMNS]
    out.append(
        "INSERT INTO food_nutrition (food_id, {cols})\n"
        "VALUES ((SELECT id FROM foods WHERE name = {name} "
        "AND owner_id IS NULL), {vals})\n"
        "ON DUPLICATE KEY UPDATE\n"
        "    {updates};".format(
            cols=", ".join(NUTRITION_COLUMNS),
            name=quote(name),
            vals=", ".join(nut_values),
            updates=",\n    ".join(f"{c} = VALUES({c})" for c in NUTRITION_COLUMNS),
        )
    )

    # -- food_tags --
    # Delete then reinsert: a food's tags are a set, and removing a tag is a
    # legitimate change too. Inserting only additions would leave a removed
    # tag in place — and for an allergen tag that is a safety failure.
    tags = [t.strip() for t in row.get("tags", "").split("|") if t.strip()]
    out.append(
        "DELETE FROM food_tags "
        f"WHERE food_id = (SELECT id FROM foods WHERE name = {quote(name)} "
        "AND owner_id IS NULL);"
    )
    for tag in tags:
        out.append(
            "INSERT INTO food_tags (food_id, tag_id) VALUES ("
            f"(SELECT id FROM foods WHERE name = {quote(name)} "
            "AND owner_id IS NULL), "
            f"(SELECT id FROM tags WHERE name_vi = {quote(tag)}));"
        )

    return out


def build_script(rows: list[dict]) -> str:
    lines = [
        "-- Generated by tools/load_foods.py — DO NOT EDIT BY HAND.",
        "-- Source: data/foods/*.csv",
        "--",
        "-- Run these first:",
        "--   db/migrations/001_dataset_readiness.sql",
        "--   db/migrations/002_food_name_unique.sql",
        "",
        "SET NAMES utf8mb4;",
        "START TRANSACTION;",
        "",
    ]
    for row in rows:
        lines.append(f"-- {row['_origin']}  {row['name']}")
        lines.extend(statements_for(row))
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines)


def apply(rows: list[dict]) -> int:
    try:
        import pymysql
    except ImportError:
        sys.exit("pymysql is required:  pip install pymysql")

    config = {
        "host": _env.get("MYSQL_HOST", "localhost"),
        "port": int(_env.get("MYSQL_PORT", "3306")),
        "user": _env.require("MYSQL_USER"),
        "password": _env.require("MYSQL_PASSWORD"),
        "database": _env.require("MYSQL_DATABASE"),
        "charset": "utf8mb4",
    }

    print(
        f"Connecting {config['user']}@{config['host']}:{config['port']}"
        f"/{config['database']}"
    )

    connection = pymysql.connect(**config, autocommit=False)
    done = 0
    try:
        with connection.cursor() as cursor:
            for row in rows:
                for statement in statements_for(row):
                    cursor.execute(statement)
                done += 1
        connection.commit()
        print(f"Loaded {done} foods.")
    except Exception as exc:
        connection.rollback()
        # The whole batch is rolled back: a half-load is worse than no load,
        # because a meal plan built from an incomplete food set still looks
        # perfectly normal.
        sys.exit(
            f"FAILED on food number {done + 1} — everything rolled back.\n{exc}"
        )
    finally:
        connection.close()

    return 0


def main() -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="connect to MySQL and insert for real, instead of writing SQL",
    )
    args = parser.parse_args()

    rows = read_rows()
    if not rows:
        sys.exit("No rows found in data/foods/*.csv")

    # Skip rows missing a required column. Inserting NULL into a NOT NULL
    # column would fail the whole transaction, taking the valid foods down
    # with it — so filter here, and say what was dropped rather than staying
    # silent.
    required = required_nutrition_columns()
    skipped = []
    keep = []
    for row in rows:
        missing = [c for c in sorted(required) if not row.get(c, "").strip()]
        if missing:
            skipped.append((row["_origin"], row["name"], missing))
        else:
            keep.append(row)

    if skipped:
        print(
            f"Skipping {len(skipped)} foods missing a required column "
            f"({', '.join(sorted(required))}):"
        )
        by_file: dict[str, int] = {}
        for origin, _, _ in skipped:
            f = origin.split(":")[0]
            by_file[f] = by_file.get(f, 0) + 1
        for f in sorted(by_file):
            print(f"  {f:<18} {by_file[f]:>3}")
        print()

    rows = keep
    if not rows:
        sys.exit("No valid rows left to load.")

    by_category: dict[str, int] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1

    print(f"{len(rows)} foods:")
    for code in sorted(by_category):
        print(f"  {code:<14} {by_category[code]:>3}")
    print()

    if args.apply:
        return apply(rows)

    OUT_SQL.write_text(build_script(rows), encoding="utf-8")
    size = OUT_SQL.stat().st_size / 1024
    print(f"Wrote {OUT_SQL}  ({size:.0f} KB)")
    print("\nReview it, then run:")
    print(f"  mysql -u <user> -p <database> < {OUT_SQL.relative_to(ROOT)}")
    print("or load directly:")
    print("  python tools/load_foods.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
