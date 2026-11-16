#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sum a dish's nutrition from its ingredient quantities.

The Vietnamese Food Composition Table 2007 lists **ingredients**, not dishes:
it has "bánh phở", "thịt bò thăn" and "hành lá", but no "phở bò". The system,
meanwhile, needs the nutrition of **one real serving**.

This step bridges the two. Each dish is described by a recipe — a list of
ingredients with weights — and the dish's nutrition is the weighted sum:

    dish_value = sum (ingredient_value_per_100g * grams / 100)

This gives `data_source` a clean answer: every figure traces back to exactly
one entry in the source table, and the recipe is recorded in the `note`
column so an examiner can verify each step.

Run:
    python tools/compose_dishes.py data/foods/recipes/mon_nuoc.json
    python tools/compose_dishes.py data/foods/recipes/*.json --write

Note on language: the tag names below stay Vietnamese because they must match
`tags.name_vi` in the database, and the `note` text stays Vietnamese because
it goes into `foods.description`, which is shown to users.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "data" / "reference"
FCT_PATH = REF_DIR / "fct2007.json"
INGREDIENTS_PATH = REF_DIR / "ingredients.json"
FOODS_DIR = ROOT / "data" / "foods"

# Food-code groups of animal origin, derived from the leading digits of the
# code: 7 = meat, 8 = seafood, 9 = egg, 10 = milk. The fermented fish sauces
# in the seasoning group are added because they are made from fish and shrimp
# — and that is precisely the trap: a dish tagged vegetarian but seasoned
# with fish sauce looks entirely normal in the CSV.
ANIMAL_GROUPS = ("7", "8", "9", "10")

# Allergenic ingredients: food code -> the tag that must be present. Omitting
# a tag here is a genuine safety failure — someone with a peanut allergy gets
# recommended a dish containing peanut, and no other check can see it because
# the CSV holds only nutrition figures, not an ingredient list.
ALLERGEN_INGREDIENTS = {
    "3017": "Có đậu phộng",   # dried peanut
    "3024": "Có đậu phộng",   # peanut flour
    "3007": "Có đậu nành",    # soybean
    "3021": "Có đậu nành",
    "3022": "Có đậu nành",
    "3025": "Có đậu nành",    # tofu
    "3026": "Có đậu nành",
    "3027": "Có đậu nành",
    "3032": "Có đậu nành",
    "13010": "Có đậu nành",   # soy sauce
    "13022": "Có đậu nành",
    "9001": "Có trứng",
    "9002": "Có trứng",
    "9004": "Có trứng",
    "1022": "Có gluten",      # wheat egg noodles
    "1012": "Có gluten",      # bread
    "1018": "Có gluten",      # wheat flour
}

# High-purine ingredients — the basis for the `Giàu purin` tag used for gout.
#
# Why this list is needed rather than the `purine_mg` column: the source table
# publishes purine for only 82 of 526 ingredients, and it is missing exactly
# where it matters most — shrimp, crab, squid, snail and clam all have no
# figure. The consequence: only 64 of 305 dishes get a purine total, so the
# per-day threshold rule covers 21% of the catalogue. The tag is the primary
# protection mechanism.
#
# Classified following dietary guidance for gout:
#   - organ meat, blood  — very high purine, must be avoided
#   - shellfish          — high purine, must be avoided
#   - fish               — high purine, to be strongly limited
#
# Red meat (beef, pork, goat) is DELIBERATELY absent: its purine is moderate
# at 130-170 mg, and the guidance says *limit* rather than *avoid*. Tagging red
# meat too would exclude 154 of 305 dishes and leave only 8 protein dishes —
# a gout patient would have almost nothing to eat, the same failure mode as
# the earlier 600 mg sodium threshold.
HIGH_PURINE_INGREDIENTS = {
    # Organ meat and blood
    "7059",
    # Shellfish: shrimp, crab, snail, clam, squid, oyster
    "8033", "8034", "8037", "8040", "8041", "8048", "8049", "8051",
    # Fish
    "8003", "8010", "8011", "8019", "8022", "8023", "8024", "8026",
    "8030", "8038",
}

ANIMAL_SEASONINGS = {
    "13011", "13012", "13013", "13014", "13015", "13016", "13017", "13018",
}

SOURCE_NAME = "Bảng thành phần thực phẩm Việt Nam 2007 (cộng dồn từ nguyên liệu)"
SOURCE_URL = (
    "https://www.fao.org/fileadmin/templates/food_composition/documents/pdf/"
    "VTN_FCT_2007.pdf"
)

# The nutrients that can be summed. An ingredient missing a figure for one
# nutrient contributes 0 for it — but the number of missing entries is counted
# and reported, because silently summing over incomplete data produces a
# figure that looks complete while actually being an undercount.
SUMMABLE = [
    "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg",
    "purine_mg", "calcium_mg", "iron_mg", "zinc_mg",
    # `vitamin_a_mcg` is a **derived** column in the ingredient table: RAE
    # activity converted from retinol and three carotenoids (see
    # `extract_fct.py`). Summing RAE is valid because RAE is already a common
    # activity unit — retinol and beta-carotene must never be added together
    # before conversion.
    "vitamin_a_mcg", "vitamin_c_mg",
]

CSV_COLUMNS = [
    "name", "category", "dish_role", "spice_level",
    "serving_size_g", "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg",
    "purine_mg", "calcium_mg", "iron_mg", "zinc_mg",
    "vitamin_a_mcg", "vitamin_c_mg",
    "tags", "note",
]


def load_ingredients() -> dict[str, dict]:
    """Prefer the merged ingredient table, fall back to the source table.

    `ingredients.json` is the source table with its gaps filled from USDA, and
    it carries a source for **each field**. Using it rather than `fct2007.json`
    lets the dishes inherit the patched values, and lets the `note` column
    record which nutrients are borrowed figures.
    """
    if not FCT_PATH.exists():
        sys.exit(
            f"{FCT_PATH} is missing. Run this first:\n"
            f"  python tools/extract_fct.py <path>/VTN_FCT_2007.pdf"
        )

    # The base is **all** 526 entries of the source table.
    data = json.loads(FCT_PATH.read_text(encoding="utf-8"))
    table = {f["code"]: {**f, "_sources": {}} for f in data}

    if not INGREDIENTS_PATH.exists():
        print("! ingredients.json is missing — using the unpatched source table.\n")
        return table

    # The patched table holds only the ingredients mapped to USDA, that is a
    # **subset**. Overlay it on the source table rather than replacing it:
    # replacing would make every unmapped ingredient vanish from the recipes,
    # leaving only a warning line while the dish still produces a
    # realistic-looking figure.
    merged = json.loads(INGREDIENTS_PATH.read_text(encoding="utf-8"))
    for code, entry in merged.items():
        table[code] = {
            **table.get(code, {}),
            **entry["values"],
            "_sources": entry["sources"],
            "name_en": entry["name_en_fct"],
        }

    return table


def compose(recipe: dict, fct: dict[str, dict]) -> tuple[dict, list[str]]:
    """Return (the CSV row, the list of warnings)."""
    warnings: list[str] = []
    borrowed_fields: set[str] = set()
    totals = {key: 0.0 for key in SUMMABLE}
    gaps: dict[str, list[str]] = {key: [] for key in SUMMABLE}
    weight = 0.0
    parts = []

    for item in recipe["ingredients"]:
        code = str(item["code"])
        grams = float(item["g"])
        source = fct.get(code)

        if source is None:
            warnings.append(f"code {code} is not in the source table")
            continue

        weight += grams
        parts.append(f"{item.get('label', source['name_en'])} {grams:g}g")

        factor = grams / 100
        for key in SUMMABLE:
            value = source.get(key)
            if value is None:
                gaps[key].append(item.get("label", code))
                continue
            totals[key] += value * factor
            if source.get("_sources", {}).get(key) == "USDA":
                borrowed_fields.add(key)

    # A nutrient missing across more than half the recipe's ingredients is
    # left empty rather than written as an undercount that looks real. Empty
    # means "not known"; an undercount means "known wrong".
    row = {c: "" for c in CSV_COLUMNS}
    for key in SUMMABLE:
        if len(gaps[key]) > len(recipe["ingredients"]) / 2:
            warnings.append(
                f"{key}: missing from {len(gaps[key])} ingredients -> left empty"
            )
            continue
        row[key] = f"{totals[key]:.1f}"
        if gaps[key]:
            warnings.append(f"{key}: undercounted, missing {', '.join(gaps[key])}")

    # Vegetarian tags must agree with the recipe. The CSV checker cannot catch
    # this because it only sees the result row, not the ingredients; and this
    # is a safety failure — a vegetarian gets recommended a dish seasoned with
    # fish sauce.
    tags = set(recipe.get("tags", []))
    if tags & {"Món chay", "Món thuần chay"}:
        offenders = []
        for item in recipe["ingredients"]:
            code = str(item["code"])
            group = code[:-3] if len(code) > 3 else code
            is_dairy_or_egg = group in ("9", "10")
            if code in ANIMAL_SEASONINGS or group in ANIMAL_GROUPS:
                # Egg and dairy are still valid for vegetarian, they only
                # violate vegan.
                if is_dairy_or_egg and "Món thuần chay" not in tags:
                    continue
                offenders.append(item.get("label", code))
        if offenders:
            warnings.append(
                "WRONGLY TAGGED: vegetarian dish with animal ingredients — "
                + ", ".join(offenders)
            )

    # An allergen implied by an ingredient has to appear in the tags.
    missing_allergens = set()
    for item in recipe["ingredients"]:
        needed = ALLERGEN_INGREDIENTS.get(str(item["code"]))
        if needed and needed not in tags:
            missing_allergens.add(f"{needed} ({item.get('label', item['code'])})")
    if missing_allergens:
        warnings.append(
            "MISSING ALLERGEN TAG: " + ", ".join(sorted(missing_allergens))
        )

    # Seafood in the recipe has to be declared too.
    if any(str(i["code"]).startswith("8") for i in recipe["ingredients"]):
        if "Có hải sản" not in tags:
            warnings.append("MISSING ALLERGEN TAG: Có hải sản")

    # A high-purine ingredient has to carry the tag for gout patients.
    purine_src = [
        i.get("label", i["code"]) for i in recipe["ingredients"]
        if str(i["code"]) in HIGH_PURINE_INGREDIENTS
    ]
    if purine_src and "Giàu purin" not in tags:
        warnings.append(
            "MISSING HIGH-PURINE TAG: " + ", ".join(sorted(set(purine_src)))
        )

    row.update({
        "name": recipe["name"],
        "category": recipe["category"],
        "dish_role": recipe["dish_role"],
        "spice_level": str(recipe.get("spice_level", 0)),
        "serving_size_g": f"{weight:.0f}",
        "tags": "|".join(recipe.get("tags", [])),
        # `note` goes into `foods.description` — a field DISPLAYED to users,
        # so it carries no provenance metadata. It used to append
        # ". Vay USDA: zinc_mg", a sentence that means something only to a
        # data maintainer. The provenance column has been dropped from the
        # schema, so this information has nowhere to live in the database
        # either; `borrowed_fields` is now used only for tool-time warnings.
        # The text stays Vietnamese because users read it.
        "note": "Công thức: " + " + ".join(parts)
                + (". " + recipe["note"] if recipe.get("note") else ""),
    })

    return row, warnings


def _use_utf8() -> None:
    """Make stdout accept non-ASCII output on Windows (it defaults to cp1252).

    Without it the script dies mid-run with `UnicodeEncodeError` as soon as
    output is redirected through a pipe or into a file — which is to say
    exactly when running in CI. A copy of `tools/_env.use_utf8`, kept here
    because this script does not otherwise need `_env`.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def main() -> int:
    _use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipes", nargs="+", type=Path)
    parser.add_argument(
        "--write", action="store_true",
        help="overwrite data/foods/<category>.csv instead of only printing",
    )
    args = parser.parse_args()

    fct = load_ingredients()
    by_category: dict[str, list[dict]] = {}
    total_warnings = 0

    for path in args.recipes:
        recipes = json.loads(path.read_text(encoding="utf-8"))
        for recipe in recipes:
            row, warnings = compose(recipe, fct)
            by_category.setdefault(row["category"], []).append(row)

            kcal = float(row["calories_kcal"]) if row["calories_kcal"] else 0
            check = (
                4 * float(row["protein_g"] or 0)
                + 4 * float(row["carbs_g"] or 0)
                + 9 * float(row["fat_g"] or 0)
            )
            drift = abs(check - kcal) / kcal * 100 if kcal else 0

            print(f"\n{recipe['name']}  ({row['serving_size_g']} g/serving)")
            print(
                f"  {kcal:.0f} kcal - protein {row['protein_g']} g - "
                f"carbohydrate {row['carbs_g']} g - fat {row['fat_g']} g"
                f"  [Atwater off by {drift:.1f} %]"
            )
            if row["sodium_mg"]:
                print(f"  sodium {row['sodium_mg']} mg")
            for w in warnings:
                print(f"  ! {w}")
                total_warnings += 1

    if args.write:
        # The CSV file name comes from the RECIPE file name, not from the
        # `category` value. Since the `code` column was dropped, `category`
        # holds a Vietnamese name with diacritics and spaces — using it as a
        # file name would produce "Món luộc hấp.csv" next to
        # "mon_luoc_hap.csv", two files for one group and the data counted
        # twice.
        stem = args.recipes[0].stem if len(args.recipes) == 1 else None
        for category, rows in by_category.items():
            path = FOODS_DIR / f"{stem or category}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\nWrote {len(rows)} dishes -> {path}")
    else:
        print("\n(Run again with --write to write the CSV)")

    print(f"\n{total_warnings} warnings in total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
