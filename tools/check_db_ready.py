#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the food CSVs against the real constraints in db/schema.sql.

Different from `validate_foods.py`, which checks whether the **content** is
plausible (Atwater, tags, value ranges). This one checks **structural**
validity: which column goes into which table, whether a value is in the enum,
whether a string exceeds its length, whether a number overflows its DECIMAL.

One CSV row does not load into one table. It splits three ways:

    foods            <- identity and classification
    food_nutrition   <- 15 nutrition columns
    food_tags        <- one row per tag, joined through the tags table

Run:
    python tools/check_db_ready.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# SCHEMA_FILE lets this point at a different schema file. Useful for trying a
# schema patch out before running it against the real database:
#
#     SCHEMA_FILE=db/schema_after_migration.sql python tools/check_db_ready.py
SCHEMA = Path(os.environ.get("SCHEMA_FILE", ROOT / "db" / "schema.sql"))
SEED = ROOT / "db" / "seed.sql"
FOODS_DIR = ROOT / "data" / "foods"

# CSV column -> (target table, target column). `None` means it has nowhere to
# go yet.
COLUMN_MAP = {
    "name": ("foods", "name"),
    # The CSV holds the category **code**; the loader resolves `category_id`
    # by joining `food_categories`. Marked as a lookup so it is not
    # type-checked like an ordinary column.
    "category": ("foods", "category_id", "lookup"),
    "dish_role": ("foods", "dish_role"),
    "spice_level": ("foods", "spice_level"),
    "note": ("foods", "description"),
    "serving_size_g": ("food_nutrition", "serving_size_g"),
    "calories_kcal": ("food_nutrition", "calories_kcal"),
    "protein_g": ("food_nutrition", "protein_g"),
    "carbs_g": ("food_nutrition", "carbs_g"),
    "fat_g": ("food_nutrition", "fat_g"),
    "fiber_g": ("food_nutrition", "fiber_g"),
    "sugar_g": ("food_nutrition", "sugar_g"),
    "sodium_mg": ("food_nutrition", "sodium_mg"),
    "cholesterol_mg": ("food_nutrition", "cholesterol_mg"),
    "purine_mg": ("food_nutrition", "purine_mg"),
    "calcium_mg": ("food_nutrition", "calcium_mg"),
    "iron_mg": ("food_nutrition", "iron_mg"),
    "zinc_mg": ("food_nutrition", "zinc_mg"),
    "vitamin_a_mcg": ("food_nutrition", "vitamin_a_mcg"),
    "vitamin_c_mg": ("food_nutrition", "vitamin_c_mg"),
    "tags": ("food_tags", "tag_id", "lookup"),
}


def read_schema(text: str) -> dict[str, dict]:
    """Pull each table's column definitions out of the schema file."""
    tables: dict[str, dict] = {}
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE", text, re.S
    ):
        name, body = m.group(1), m.group(2)
        columns: dict[str, dict] = {}
        for line in body.split("\n"):
            line = line.split("--")[0].strip().rstrip(",")
            if not line or line.upper().startswith(
                ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT")
            ):
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            col, rest = parts[0], parts[1]
            info: dict = {"raw": rest, "nullable": "NOT NULL" not in rest.upper()}

            enum = re.match(r"(ENUM|SET)\s*\((.*?)\)", rest, re.S | re.I)
            if enum:
                info["kind"] = enum.group(1).upper()
                info["values"] = set(re.findall(r"'([^']*)'", enum.group(2)))

            varchar = re.match(r"VARCHAR\((\d+)\)", rest, re.I)
            if varchar:
                info["kind"] = "VARCHAR"
                info["max_len"] = int(varchar.group(1))

            dec = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", rest, re.I)
            if dec:
                info["kind"] = "DECIMAL"
                info["precision"] = int(dec.group(1))
                info["scale"] = int(dec.group(2))

            if re.match(r"(SMALLINT|TINYINT|INT|BIGINT)", rest, re.I):
                info.setdefault("kind", "INT")
                info["unsigned"] = "UNSIGNED" in rest.upper()

            columns[col] = info
        tables[name] = columns
    return tables


def main() -> int:
    _env.use_utf8()
    schema = read_schema(SCHEMA.read_text(encoding="utf-8"))
    seed = SEED.read_text(encoding="utf-8")

    categories = set(
        re.findall(r"^\('([^']+)',\s*'[^']*'\)[,;]?$", seed, re.M)
    )
    tags = set(re.findall(r"^\('([^']+)',\s*'\w+',", seed, re.M))
    # The last row of each block ends with `;` rather than `,`, so the regex
    # above misses the final tag; catch the description-less form separately.
    tags |= set(re.findall(r"^\('([^']+)',\s*'\w+',.*\)[,;]$", seed, re.M))

    blockers: list[str] = []
    errors: list[str] = []
    notes: list[str] = []

    print("=" * 72)
    print("DATABASE LOAD READINESS")
    print("=" * 72)

    # -- 1. Does every CSV column have somewhere to go? --
    print("\n1. CSV column -> table mapping")
    homeless = [c for c, spec in COLUMN_MAP.items() if spec[0] is None]
    for col, spec in COLUMN_MAP.items():
        table, target = spec[0], spec[1]
        if table is None:
            continue
        if table not in schema:
            blockers.append(f"table `{table}` is not in the schema")
        elif target not in schema[table] and table != "food_tags":
            blockers.append(
                f"`{table}.{target}` does not exist (CSV column `{col}`)"
            )
    if homeless:
        notes.append(
            f"{len(homeless)} CSV columns have nowhere to go: "
            f"{', '.join(homeless)}"
        )
    print(
        f"   {len(COLUMN_MAP) - len(homeless)}/{len(COLUMN_MAP)} columns have "
        f"a destination"
    )

    # -- 2. Read the data --
    rows = []
    for path in sorted(FOODS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if any(v.strip() for v in row.values()):
                    rows.append((path.name, lineno, row))

    print(f"\n2. Data: {len(rows)} rows")

    # -- 3. Enums and foreign keys --
    print("\n3. Enums, SETs and foreign keys")
    foods = schema.get("foods", {})

    def check_enum(row, where, csv_col, schema_col, multi=False):
        raw = row.get(csv_col, "").strip()
        if not raw:
            return
        info = foods.get(schema_col, {})
        allowed = info.get("values")
        if not allowed:
            return
        values = raw.split("|") if multi else [raw]
        for v in values:
            if v not in allowed:
                errors.append(
                    f"{where}: `{schema_col}` = {v!r} is not in "
                    f"ENUM({', '.join(sorted(allowed))})"
                )

    bad_roles = set()
    for fname, lineno, row in rows:
        where = f"{fname}:{lineno}"

        role = row.get("dish_role", "").strip()
        allowed_roles = foods.get("dish_role", {}).get("values", set())
        if role and allowed_roles and role not in allowed_roles:
            bad_roles.add(role)

        cat = row.get("category", "").strip()
        if cat and categories and cat not in categories:
            errors.append(
                f"{where}: `category` = {cat!r} is not in food_categories"
            )

        for tag in [t.strip() for t in row.get("tags", "").split("|") if t.strip()]:
            if tags and tag not in tags:
                errors.append(f"{where}: tag {tag!r} is not in the tags table")

    if bad_roles:
        allowed = foods.get("dish_role", {}).get("values", set())
        blockers.append(
            f"`foods.dish_role` is ENUM({', '.join(sorted(allowed))}) but the "
            f"CSV also uses: {', '.join(sorted(bad_roles))}"
        )

    print(f"   {len(errors)} enum / foreign-key errors")

    # -- 4. String length and numeric overflow --
    print("\n4. String length and numeric types")
    overflow = 0
    for fname, lineno, row in rows:
        where = f"{fname}:{lineno}"
        for csv_col, spec in COLUMN_MAP.items():
            table, target = spec[0], spec[1]
            # Lookup columns were checked in section 3; no type check here.
            if table is None or len(spec) > 2:
                continue
            info = schema.get(table, {}).get(target, {})
            raw = row.get(csv_col, "").strip()
            if not raw:
                if not info.get("nullable", True) and csv_col != "note":
                    errors.append(
                        f"{where}: `{table}.{target}` is NOT NULL but empty"
                    )
                continue

            if info.get("kind") == "VARCHAR" and len(raw) > info["max_len"]:
                errors.append(
                    f"{where}: `{target}` is {len(raw)} characters, over "
                    f"VARCHAR({info['max_len']})"
                )
                overflow += 1

            if info.get("kind") == "DECIMAL":
                try:
                    value = float(raw)
                except ValueError:
                    errors.append(
                        f"{where}: `{target}` = {raw!r} is not a number"
                    )
                    continue
                limit = 10 ** (info["precision"] - info["scale"])
                if abs(value) >= limit:
                    errors.append(
                        f"{where}: `{target}` = {value} overflows "
                        f"DECIMAL({info['precision']},{info['scale']})"
                    )
                    overflow += 1

            if info.get("kind") == "INT" and info.get("unsigned"):
                try:
                    if float(raw) < 0:
                        errors.append(
                            f"{where}: `{target}` is negative but the column "
                            f"is UNSIGNED"
                        )
                except ValueError:
                    errors.append(
                        f"{where}: `{target}` = {raw!r} is not a number"
                    )

    print(f"   {overflow} values over their size limit")

    # -- 5. Verdict --
    print("\n" + "=" * 72)
    if blockers:
        print(f"LOAD BLOCKED — {len(blockers)} structural problems:\n")
        for b in blockers:
            print(f"  x {b}")
    if errors:
        # Grouped by file: the dataset is being built one group at a time, so
        # knowing which group is already clean matters more than reading 129
        # near-identical error lines.
        by_file: dict[str, list[str]] = {}
        for e in errors:
            by_file.setdefault(e.split(":")[0], []).append(e)

        print(f"\n{len(errors)} data errors, by file:\n")
        for fname in sorted(by_file):
            print(f"  {fname:<20} {len(by_file[fname]):>4} errors")

        clean = sorted({f for f, _, _ in rows} - set(by_file))
        if clean:
            print(f"\n  Clean files: {', '.join(clean)}")

        print("\n  Examples:")
        for e in errors[:5]:
            print(f"    - {e}")
    if notes:
        print("\nNotes:")
        for n in notes:
            print(f"  ! {n}")

    if not blockers and not errors:
        print("READY TO LOAD — no problems found.")

    print("=" * 72)
    return 1 if blockers or errors else 0


if __name__ == "__main__":
    sys.exit(main())
