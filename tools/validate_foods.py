#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the food dataset in data/foods/*.csv.

This dataset is entered by several people and several agents from several
sources, so mistakes are a certainty rather than a risk. The validator runs
before every load into MySQL, and should also run in a pre-commit hook.

The most important check is the **Atwater cross-check**: the declared energy
must approximate 4*protein + 4*carbohydrate + 9*fat. It catches nearly every
transcription error — wrong column, misplaced decimal point, mixed units —
without needing to know how many calories the dish really has.

Run:
    python tools/validate_foods.py            # validate and print a report
    python tools/validate_foods.py --strict    # treat warnings as errors

Note on language: the category, tag and file-mapping values below stay
Vietnamese because they must match `food_categories.name` and `tags.name_vi`
in the database. Only the code and the report text are English.
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "foods"

# -- The allowed vocabulary; must match the enums in db/schema.sql ---------

CATEGORIES = {
    "Món nước", "Cơm", "Món kho",
    "Món xào", "Món canh", "Món chiên rán",
    "Món nướng", "Món luộc hấp", "Món cuốn",
    "Món gỏi / nộm", "Tráng miệng", "Đồ uống",
}

# CSV file name -> the category name in the database.
#
# The files keep diacritic-free names because they are easier to type and to
# use on a command line, while the `category` column inside them holds the
# **Vietnamese name** — exactly the value `food_categories.name` stores, since
# the `code` column was dropped from the schema.
FILE_TO_CATEGORY = {
    "mon_nuoc": "Món nước",
    "com": "Cơm",
    "mon_kho": "Món kho",
    "mon_xao": "Món xào",
    "mon_canh": "Món canh",
    "mon_chien": "Món chiên rán",
    "mon_nuong": "Món nướng",
    "mon_luoc_hap": "Món luộc hấp",
    "mon_cuon": "Món cuốn",
    "mon_goi": "Món gỏi / nộm",
    "trang_mieng": "Tráng miệng",
    "do_uong": "Đồ uống",
}

# Dish roles. Wider than the current `foods.dish_role` enum (main/side/soup/
# dessert/drink) because the meal-plan generator needs `side_protein` apart
# from `side_veg` — a Vietnamese meal without a savoury dish is not a meal,
# and the current enum folds both into `side` so it cannot express that
# constraint.
DISH_ROLES = {
    "main",          # the main dish — rice, pho, noodles
    "side_protein",  # the savoury dish — meat, fish, egg, tofu
    "side_veg",      # the vegetable dish — boiled, stir-fried, salad
    "soup",          # the soup
    "snack",         # a side or a snack
    "dessert",       # dessert
    "drink",         # a drink
}

TAGS = {
    "Có hải sản", "Có đậu phộng", "Có trứng",
    "Có sữa / chế phẩm sữa", "Có gluten", "Có đậu nành",
    "Món chay", "Món thuần chay", "Ít natri",
    "Ít đường", "Giàu đạm", "Giàu chất xơ",
    "Giàu purin",
}

# -- Columns: required, wanted, optional ----------------------------------

REQUIRED = [
    "name", "category", "dish_role", "spice_level",
    "serving_size_g", "calories_kcal",
    "protein_g", "carbs_g", "fat_g",
]

# The F1 rule set in db/seed.sql references these columns. Leaving one empty
# means the matching rule silently never fires — a hypertensive user still
# receives salty dishes while the system believes it has filtered them.
RULE_COLUMNS = {
    "sodium_mg": "hypertension, kidney disease",
    "sugar_g": "diabetes",
    "cholesterol_mg": "dyslipidaemia",
    "purine_mg": "gout",
    "calcium_mg": "osteoporosis",
    "iron_mg": "anaemia",
    "vitamin_c_mg": "micronutrient recommendations",
}

NUMERIC = {
    "spice_level": (0, 3),
    "serving_size_g": (1, 2000),
    "calories_kcal": (0, 2000),
    "protein_g": (0, 200),
    "carbs_g": (0, 300),
    "fat_g": (0, 200),
    "fiber_g": (0, 100),
    "sugar_g": (0, 200),
    "sodium_mg": (0, 10000),
    "cholesterol_mg": (0, 1000),
    "purine_mg": (0, 1000),
    "calcium_mg": (0, 3000),
    "iron_mg": (0, 100),
    "zinc_mg": (0, 100),
    "vitamin_a_mcg": (0, 5000),
    "vitamin_c_mg": (0, 1000),
}

# The tolerance for the Atwater cross-check. Genuine drift has real causes:
# fiber yields less energy than carbohydrate, alcohol yields 7 kcal/g, and
# published figures are usually already rounded. 12% is wide enough to avoid
# false alarms and tight enough to catch a misplaced decimal point.
ATWATER_TOLERANCE = 0.12

#: The two severity levels. Internal sentinels compared with `==`, so they
#: are code rather than display text.
ERROR = "ERROR"
WARNING = "WARNING"


class Issue:
    __slots__ = ("level", "file", "row", "name", "message")

    def __init__(self, level, file, row, name, message):
        self.level = level
        self.file = file
        self.row = row
        self.name = name
        self.message = message

    def __str__(self):
        where = f"{self.file}:{self.row}"
        who = f" [{self.name}]" if self.name else ""
        return f"  {where}{who}  {self.message}"


def normalize(text: str) -> str:
    """Strip diacritics and lowercase, used to detect duplicate dish names.

    "Phở bò tái" and "pho bo tai" are the same dish, and different people
    entering data very easily type them differently.
    """
    stripped = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").strip()


def parse_number(value: str):
    """Return (number, error). An empty string returns (None, None)."""
    raw = value.strip()
    if not raw:
        return None, None
    # Data entry habitually uses the Vietnamese decimal comma.
    raw = raw.replace(",", ".")
    try:
        return float(raw), None
    except ValueError:
        return None, f"not a number: {value!r}"


def check_row(issues, filename, lineno, row, expected_category):
    name = row.get("name", "").strip()

    for column in REQUIRED:
        if not row.get(column, "").strip():
            issues.append(
                Issue(
                    ERROR, filename, lineno, name,
                    f"required column `{column}` is missing",
                )
            )

    if not name:
        return None

    # -- Vocabulary --
    category = row.get("category", "").strip()
    if category and category not in CATEGORIES:
        issues.append(
            Issue(ERROR, filename, lineno, name, f"unknown `category`: {category!r}")
        )
    elif category and category != FILE_TO_CATEGORY.get(
        expected_category, expected_category
    ):
        issues.append(
            Issue(
                ERROR, filename, lineno, name,
                f"`category` is {category!r} but the row is in "
                f"{expected_category}.csv",
            )
        )

    role = row.get("dish_role", "").strip()
    if role and role not in DISH_ROLES:
        issues.append(
            Issue(ERROR, filename, lineno, name, f"unknown `dish_role`: {role!r}")
        )

    for tag in [t.strip() for t in row.get("tags", "").split("|") if t.strip()]:
        if tag not in TAGS:
            issues.append(
                Issue(ERROR, filename, lineno, name, f"unknown tag: {tag!r}")
            )

    # -- Numbers --
    values = {}
    for column, (low, high) in NUMERIC.items():
        number, error = parse_number(row.get(column, ""))
        if error:
            issues.append(
                Issue(ERROR, filename, lineno, name, f"`{column}` {error}")
            )
            continue
        if number is None:
            continue
        if not (low <= number <= high):
            issues.append(
                Issue(
                    ERROR, filename, lineno, name,
                    f"`{column}` = {number:g} is outside the plausible range "
                    f"[{low}, {high}]",
                )
            )
        values[column] = number

    # -- The Atwater cross-check --
    kcal = values.get("calories_kcal")
    protein = values.get("protein_g")
    carbs = values.get("carbs_g")
    fat = values.get("fat_g")

    if None not in (kcal, protein, carbs, fat):
        computed = 4 * protein + 4 * carbs + 9 * fat
        if kcal > 0:
            drift = abs(computed - kcal) / kcal
            if drift > ATWATER_TOLERANCE:
                issues.append(
                    Issue(
                        ERROR, filename, lineno, name,
                        f"energy does not match the three macros: declared "
                        f"{kcal:g} kcal, computed {computed:.0f} kcal "
                        f"(off by {drift * 100:.0f} %)",
                    )
                )
        elif computed > 20:
            issues.append(
                Issue(
                    ERROR, filename, lineno, name,
                    f"`calories_kcal` = 0 but the three macros sum to "
                    f"{computed:.0f} kcal",
                )
            )

    # Sugar and fiber are both part of carbohydrate, so in principle neither
    # may exceed it.
    #
    # But in the Vietnamese Food Composition Table 2007, **29 of 211 entries**
    # have more sugar than carbohydrate — watermelon, for instance, lists 2.3 g
    # carbohydrate and 6.2 g sugar. This is a contradiction in THE SOURCE
    # TABLE ITSELF, not a transcription error: the "Glucid" column is usually
    # computed by difference while "total sugar" is measured directly, and the
    # two methods diverge on watery fruit.
    #
    # Hence this is a WARNING, not an ERROR. Reporting an error for something
    # that cannot be fixed trains the reader to ignore the validator's output —
    # and then the real errors drift past too. The code caps the sugar ratio at
    # 1.0 anyway, so it stays safe.
    for part in ("sugar_g", "fiber_g"):
        if part in values and carbs is not None and values[part] > carbs + 0.01:
            issues.append(
                Issue(
                    WARNING, filename, lineno, name,
                    f"`{part}` = {values[part]:g} exceeds `carbs_g` = {carbs:g}"
                    f" — a contradiction present in the source table, the "
                    f"source figures are kept as published",
                )
            )

    # -- Tags consistent with the figures --
    # The three checks below used to look tags up by their English names —
    # `vegan`, `vegetarian`, `contains_seafood`, `low_sodium` — while the tag
    # vocabulary had moved to Vietnamese names when the `code` column was
    # dropped. No tag matched any more, so **none of the three ever ran**,
    # including the ERROR-level check for "vegetarian and contains seafood".
    #
    # Worth noting because exactly this kind of failure let two dishes tagged
    # `Món chay` with fish sauce in their recipe through: the check was still
    # in the source, looking like protection, while being a dead `if`.
    tags = {t.strip() for t in row.get("tags", "").split("|") if t.strip()}
    if "Món thuần chay" in tags and "Món chay" not in tags:
        issues.append(
            Issue(
                WARNING, filename, lineno, name,
                "tagged `Món thuần chay` but missing `Món chay`",
            )
        )
    if "Món chay" in tags and tags & {"Có hải sản"}:
        issues.append(
            Issue(
                ERROR, filename, lineno, name,
                "tagged vegetarian and containing seafood at the same time",
            )
        )
    if "Ít natri" in tags and values.get("sodium_mg", 0) > 400:
        issues.append(
            Issue(
                WARNING, filename, lineno, name,
                f"tagged `Ít natri` but sodium is {values['sodium_mg']:g} mg",
            )
        )

    return {"name": name, "values": values, "role": role}


def main() -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="treat warnings as errors"
    )
    args = parser.parse_args()

    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        print(f"No CSV file found in {DATA_DIR}")
        return 1

    issues: list[Issue] = []
    rows = []
    seen: dict[str, tuple[str, int]] = {}
    per_file = Counter()
    per_role = Counter()
    coverage = defaultdict(int)

    for path in files:
        expected = path.stem
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if not any(v.strip() for v in row.values()):
                    continue

                parsed = check_row(issues, path.name, lineno, row, expected)
                per_file[expected] += 1
                if parsed is None:
                    continue

                rows.append(parsed)
                per_role[parsed["role"]] += 1
                for column in RULE_COLUMNS:
                    if row.get(column, "").strip():
                        coverage[column] += 1

                key = normalize(parsed["name"])
                if key in seen:
                    first_file, first_line = seen[key]
                    issues.append(
                        Issue(
                            ERROR, path.name, lineno, parsed["name"],
                            f"duplicate name, also at {first_file}:{first_line}",
                        )
                    )
                else:
                    seen[key] = (path.name, lineno)

    total = len(rows)
    errors = [i for i in issues if i.level == ERROR]
    warnings = [i for i in issues if i.level == WARNING]

    print("=" * 72)
    print(f"FOOD DATASET — {total} dishes across {len(files)} files")
    print("=" * 72)

    print("\nDishes per group:")
    for code in sorted(per_file):
        bar = "#" * min(per_file[code], 40)
        print(f"  {code:<14} {per_file[code]:>4}  {bar}")

    if per_role:
        print("\nDishes per role in the meal:")
        for role in sorted(per_role):
            print(f"  {role:<14} {per_role[role]:>4}")
        missing_roles = DISH_ROLES - set(per_role)
        if missing_roles:
            print(f"  -> no dish yet for: {', '.join(sorted(missing_roles))}")

    if total:
        print("\nCoverage of the columns the F1 rule set needs:")
        for column, purpose in RULE_COLUMNS.items():
            filled = coverage[column]
            pct = filled / total * 100
            flag = "" if pct >= 80 else "  <- rule not usable yet"
            print(
                f"  {column:<16} {filled:>4}/{total}  {pct:>5.1f} %{flag}"
                f"   ({purpose})"
            )

    if errors:
        print(f"\n-- {len(errors)} ERRORS --")
        for issue in errors:
            print(issue)

    if warnings:
        print(f"\n-- {len(warnings)} WARNINGS --")
        for issue in warnings:
            print(issue)

    print()
    if not errors and not warnings:
        print("No problems found.")
    else:
        print(f"Total: {len(errors)} errors, {len(warnings)} warnings.")

    if total < 300:
        print(
            f"{300 - total} more dishes needed to reach the proposal's "
            f"minimum of 300."
        )

    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
