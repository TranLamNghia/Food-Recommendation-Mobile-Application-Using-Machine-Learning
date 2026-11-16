#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fill micronutrient gaps for ingredients from USDA FoodData Central.

Patched at the **ingredient** level, not the dish level. The first ten soup
dishes share 15 ingredients; fixing one ingredient fixes every dish that uses
it. Fixing dish by dish repeats the same work hundreds of times, and each
repetition is another chance to diverge.

The result is written to `data/reference/ingredients.json` — a merged
ingredient table in which **each value carries its own source**. Recording the
source per entry would be wrong, because one ingredient can take its
macronutrients from the Vietnamese table while borrowing sodium from USDA.

Run:
    python tools/fill_gaps_usda.py            # patch and write
    python tools/fill_gaps_usda.py --dry-run  # look only, write nothing

Note on language: identifiers and output here are English, but the keys and
values inside `ingredient_map.json` stay Vietnamese — they are **data**, a
hand-maintained reference file, not code.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
FCT_PATH = REF / "fct2007.json"
MAP_PATH = REF / "ingredient_map.json"
OUT_PATH = REF / "ingredients.json"

# The nutrients that may be borrowed. Deliberately WITHOUT calories_kcal,
# protein_g, fat_g and carbs_g — see SOURCING_POLICY.md section 2. Mixing
# macronutrients across two tables invents an ingredient that does not exist
# and also breaks the Atwater cross-check, which is the only check that
# catches a bad figure.
BORROWABLE = {
    "sodium_mg": ("Sodium, Na", "MG"),
    "sugar_g": ("Sugars, total including NLEA", "G"),
    "cholesterol_mg": ("Cholesterol", "MG"),
    "zinc_mg": ("Zinc, Zn", "MG"),
    "iron_mg": ("Iron, Fe", "MG"),
    "calcium_mg": ("Calcium, Ca", "MG"),
    "vitamin_c_mg": ("Vitamin C, total ascorbic acid", "MG"),
}

# The nutrients kept from the Vietnamese table, never borrowed.
LOCKED = ["calories_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "purine_mg"]

SRC_FCT = "FCT2007"
SRC_USDA = "USDA"


def fetch_usda(fdc_id: int, api_key: str) -> dict[str, float]:
    """Fetch one USDA entry's borrowable nutrients, normalised per 100 g."""
    url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}?api_key={api_key}"
    with urllib.request.urlopen(url, timeout=45) as response:
        data = json.load(response)

    wanted = {v: k for k, v in BORROWABLE.items()}
    values: dict[str, float] = {}

    for item in data.get("foodNutrients", []):
        nutrient = item.get("nutrient", {})
        key = (nutrient.get("name"), nutrient.get("unitName", "").upper())
        amount = item.get("amount")
        if key in wanted and amount is not None:
            values[wanted[key]] = float(amount)

    return values


def main() -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = _env.require(
        "USDA_API_KEY",
        hint="Sign up free at https://api.data.gov/signup/",
    )

    fct = {f["code"]: f for f in json.loads(FCT_PATH.read_text(encoding="utf-8"))}
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    pairs = mapping["mappings"]
    # `khong_anh_xa` ("not mapped") is a key in the data file, kept as-is.
    unmapped = {k: v for k, v in mapping["khong_anh_xa"].items() if k != "_doc"}

    result: dict[str, dict] = {}
    filled_count = 0
    skipped: list[str] = []

    codes = list(pairs) + list(unmapped)
    print(f"Processing {len(codes)} ingredients.\n")

    for code in codes:
        source = fct.get(code)
        if source is None:
            print(f"  ! code {code} is not in the source table, skipping")
            continue

        entry = {
            "code": code,
            "name_vi": pairs.get(code, {}).get("vi") or unmapped.get(code, ""),
            "name_en_fct": source["name_en"],
            "values": {},
            "sources": {},
        }

        for key in LOCKED + list(BORROWABLE):
            value = source.get(key)
            if value is not None:
                entry["values"][key] = value
                entry["sources"][key] = SRC_FCT

        pair = pairs.get(code)
        if pair is None:
            result[code] = entry
            continue

        gaps = [k for k in BORROWABLE if k not in entry["values"]]
        if not gaps:
            result[code] = entry
            continue

        try:
            usda = fetch_usda(pair["fdc_id"], api_key)
        except urllib.error.HTTPError as exc:
            print(f"  ! {entry['name_vi']}: USDA call failed with {exc.code}")
            skipped.append(entry["name_vi"])
            result[code] = entry
            continue

        borrowed = []
        for key in gaps:
            if key in usda:
                entry["values"][key] = usda[key]
                entry["sources"][key] = SRC_USDA
                borrowed.append(key)
                filled_count += 1

        entry["usda_ref"] = {
            "fdc_id": pair["fdc_id"],
            "description": pair["usda"],
            "confidence": pair["confidence"],
        }

        # The confidence values are Vietnamese because they come from the
        # data file.
        flag = {"cao": " ", "trung binh": "~", "thap": "!"}.get(
            pair["confidence"], " "
        )
        still_missing = [k for k in gaps if k not in usda]
        print(
            f"  {flag} {entry['name_vi']:<18} borrowed {len(borrowed)}: "
            f"{', '.join(borrowed) or '-'}"
        )
        if still_missing:
            print(f"      still missing: {', '.join(still_missing)}")

        result[code] = entry
        # Be polite to the server; the quota is 1,000 calls per hour, so
        # there is no need to rush.
        time.sleep(0.4)

    print(f"\nBorrowed {filled_count} values.")
    if skipped:
        print(f"Could not call: {', '.join(skipped)}")

    print("\nCoverage after patching:")
    total = len(result)
    for key in LOCKED + list(BORROWABLE):
        have = sum(1 for e in result.values() if key in e["values"])
        from_usda = sum(
            1 for e in result.values() if e["sources"].get(key) == SRC_USDA
        )
        tail = f"  (borrowed {from_usda})" if from_usda else ""
        print(f"  {key:<16} {have:>3}/{total}  {have / total * 100:>5.1f} %{tail}")

    if args.dry_run:
        print("\n(--dry-run: no file written)")
        return 0

    OUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nWrote -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
