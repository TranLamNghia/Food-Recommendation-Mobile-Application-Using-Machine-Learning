#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-check the two Step 4 implementations — Python and Dart.

Why it is needed. `ml/menu_builder.py` is a port of
`mobile/lib/data/recommender/menu_builder.dart`, and the Dart one stays: it is
the app's fallback when the ML service cannot be reached. Two implementations
of the same five phases is exactly the situation `tools/check_be_parity.py`
was written for — three implementations of Step 1 drifted apart and nothing
reported it. A drift here does not raise either. Both sides return a plan,
both plans look like plans, and only the dishes differ.

How it works. Python loads the catalogue, builds a plan, and writes the
**inputs** and the **expected plan** into a JSON fixture. The Dart test reads
it, runs its own builder over the same foods with the same profile and
targets, and compares meal by meal, dish by dish.

    python tools/check_step4_parity.py                 # fixture, then flutter test
    python tools/check_step4_parity.py --fixture-only   # fixture only

## What is compared, and what is NOT

**Exploration is switched off** (`explorationRatio = 0`). The 70-30 mechanism
draws Gaussian noise, and Dart's `math.Random` and Python's `random` are
different generators: the same seed gives different numbers, so an
exploration serving cannot be compared dish for dish. At ratio 0 the whole of
phases 1 to 5 is deterministic on both sides — that is 100 % of the algorithm
and 70 % of a real plan's servings.

The exploration branch is covered by property checks instead, in
`tools/check_step4.py`: the right number of servings, δ recorded, the ratio
capped at 0.5.

**The model score is switched off** too (`ml_scores` empty). The Dart side has
no model to consult, so the comparable path is the cosine one. What the blend
does is checked in `tools/check_step4.py` section 13.

## The dish-role translation

The two sides do not even agree on how to name a dish role. `foods.dish_role`
is an ENUM of English codes — `main`, `side_protein`, … — and the Dart meal
structure is keyed on Vietnamese labels from `MockFoods`: `'Món chính'`,
`'Món mặn'`, … Four of those five labels exist nowhere in the database, and
the fifth, `'Món canh'`, exists as a *category* — a different column
entirely. Pointed at the real catalogue, the Dart builder matches no food and
silently produces an empty plan (`menu_builder.dart:154` skips a serving when
its pool is empty).

So the fixture writes `dishRole` **translated into the Dart labels**, through
`ml.menu_builder.ROLE_FROM_DART` read backwards. That makes this checker
honest about what it proves: the two **algorithms** agree. It does not prove
the Dart side works against the database — it cannot, until the app gets a
`DishRole` enum carrying the schema's codes, the way `MealType` already
carries `'breakfast'`. The agreed labels for that enum, when someone writes
it: main → "Món chính", side_protein → "Món mặn", side_veg → "Món rau",
soup → "Món canh", snack → "Món phụ", dessert → "Tráng miệng",
drink → "Đồ uống".

Note on language: the fixture keys are a contract with
`mobile/test/step4_parity_test.dart` and stay as they are. The dish-role
values in it are Vietnamese because they are what the Dart side keys on —
data, not prose.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import connect, use_utf8  # noqa: E402
from ml.features import FeatureSpace, load_foods  # noqa: E402
from ml.menu_builder import (  # noqa: E402
    MEAL_STRUCTURE,
    ROLE_FROM_DART,
    MenuBuilder,
    NutrientTarget,
)
from ml.rocchio import PreferenceProfile  # noqa: E402

FIXTURE = ROOT / "mobile" / "test" / "fixtures" / "step4_parity.json"
DART_TEST = "test/step4_parity_test.dart"

#: Schema code -> the label the Dart side keys on. `ROLE_FROM_DART` read
#: backwards, so the two directions cannot disagree.
ROLE_TO_DART = {code: label for label, code in ROLE_FROM_DART.items()}

#: The day, the targets and the profile are fixed so the fixture is
#: reproducible. A real user's numbers would change the fixture every time
#: their profile did, and then a diff would mean nothing.
PLAN_DATE = date(2026, 11, 18)
TARGET_KCAL = 2000.0
#: 20 / 50 / 30 of energy, in grams. Protein and carbohydrate 4 kcal/g, fat 9.
TARGET_PROTEIN = TARGET_KCAL * 0.20 / 4
TARGET_CARB = TARGET_KCAL * 0.50 / 4
TARGET_FAT = TARGET_KCAL * 0.30 / 9

#: Two day-level constraints, so phase 5 runs rather than returning early.
#: Loose enough that a plan exists, tight enough that the repair has work:
#: sodium is the one the real rule set uses (WHO, 2000 mg), fibre the floor.
NUTRIENT_TARGETS = [
    NutrientTarget.at_most("sodium_mg", 2000.0, "Tăng huyết áp"),
    NutrientTarget.at_least("fiber_g", 20.0, "Mục tiêu"),
]


def synthetic_profile(space: FeatureSpace) -> PreferenceProfile:
    """A fixed preference vector, built from the dimension index alone.

    Deterministic and written into the fixture, so both sides score from
    exactly the same numbers. A real `user_preference_profiles` row would do
    as well, but it changes whenever that user swipes, and a fixture that
    moves on its own cannot be diffed.

    The values are spread over [-1, 1] by a sine so the vector has a
    direction in every dimension — an all-equal vector would make the cosine
    identical for whole groups of foods and hide an ordering difference.
    """
    weights = tuple(
        round(math.sin(i * 0.7) * 0.6, 6) for i in range(space.length)
    )
    return PreferenceProfile(
        weights=weights,
        sum_abs_weight=sum(abs(w) for w in weights),
        #: 40 signals — above the `hybrid` threshold, which is where a real
        #: user sits. It changes nothing here, since no model score is
        #: supplied, but it keeps the fixture honest about the stage.
        n_signals=40,
    )


def build_fixture() -> tuple[Path, int, int]:
    """Load the catalogue, build the plan, write the fixture.

    Returns (path, food count, serving count).
    """
    cn = connect()
    try:
        foods, _ = load_foods(cn)
    finally:
        cn.close()

    space = FeatureSpace.from_foods(foods)
    profile = synthetic_profile(space)

    builder = MenuBuilder(
        candidates=foods,
        space=space,
        profile=profile,
        # Off, both of them. See the module docstring.
        exploration_ratio=0.0,
        ml_scores=None,
        nutrient_targets=NUTRIENT_TARGETS,
    )
    plan = builder.build(
        plan_date=PLAN_DATE,
        target_kcal=TARGET_KCAL,
        target_protein=TARGET_PROTEIN,
        target_carb=TARGET_CARB,
        target_fat=TARGET_FAT,
    )

    missing = sorted(
        {f.dish_role for f in foods} - set(ROLE_TO_DART) - {"dessert", "drink"}
    )
    if missing:
        raise SystemExit(
            f"These dish roles have no Dart label: {missing}. The Dart meal "
            "structure cannot be keyed on them, so the comparison would be "
            "against a plan the Dart side could never build. Add them to "
            "ml.menu_builder.ROLE_FROM_DART first."
        )

    fixture = {
        "_doc": (
            "Generated by tools/check_step4_parity.py — do not edit by hand. "
            "Holds the inputs and the plan the Python side expects, for "
            "mobile/test/step4_parity_test.dart to rebuild and compare. "
            "`dishRole` is translated into the Vietnamese labels the Dart "
            "meal structure keys on; the database stores English ENUM codes."
        ),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "featureVersion": space.params()["feature_version"],
        "planDate": PLAN_DATE.isoformat(),
        "targets": {
            "kcal": TARGET_KCAL,
            "protein": TARGET_PROTEIN,
            "carb": TARGET_CARB,
            "fat": TARGET_FAT,
        },
        "params": {
            "explorationRatio": 0.0,
            "explorationDelta": builder.exploration_delta,
            "energyPenalty": builder.energy_penalty,
            "macroPenalty": builder.macro_penalty,
            "localSearchRounds": builder.local_search_rounds,
            "nutrientRepairRounds": builder.nutrient_repair_rounds,
            "maxEnergyDeviation": builder.max_energy_deviation,
        },
        "profile": {
            "weights": list(profile.weights),
            "signalCount": profile.n_signals,
        },
        "nutrientTargets": [
            {
                "nutrient": t.nutrient,
                "amount": t.amount,
                "isFloor": t.is_floor,
            }
            for t in NUTRIENT_TARGETS
        ],
        # The required roles, translated, so the Dart test can assert that it
        # read the same meal structure rather than only the same result.
        "mealStructure": {
            meal: {
                "required": [ROLE_TO_DART[r] for r in shape.required],
                "optional": [ROLE_TO_DART[r] for r in shape.optional],
            }
            for meal, shape in MEAL_STRUCTURE.items()
        },
        "foods": [
            {
                "id": f.id,
                "name": f.name,
                "category": f.category,
                # Translated on purpose — see the module docstring.
                "dishRole": ROLE_TO_DART.get(f.dish_role, f.dish_role),
                "dishRoleCode": f.dish_role,
                "spiceLevel": f.spice_level,
                "kcal": f.kcal,
                "protein": f.protein,
                "carb": f.carb,
                "fat": f.fat,
                "sugar": f.sugar,
                "sodium": f.sodium,
                "fiber": f.fiber,
                "servingSizeG": f.serving_size_g,
            }
            for f in foods
        ],
        "expected": {
            "actualKcal": plan.actual_kcal,
            "actualProtein": plan.actual_protein,
            "actualCarb": plan.actual_carb,
            "actualFat": plan.actual_fat,
            "deviationPct": plan.deviation_pct,
            "totalPreferenceScore": plan.total_preference_score,
            "meals": [
                {
                    "mealType": slot.meal_type,
                    "targetKcal": slot.target_kcal,
                    "actualKcal": slot.actual_kcal,
                    "items": [
                        {
                            "foodId": item.food.id,
                            "dishRole": ROLE_TO_DART.get(
                                item.food.dish_role, item.food.dish_role
                            ),
                            "score": item.score,
                            "kcal": item.food.kcal,
                        }
                        for item in slot.items
                    ],
                }
                for slot in plan.slots
            ],
            "nutrientViolations": [
                {"nutrient": t.nutrient, "actual": actual}
                for t, actual in plan.nutrient_violations
            ],
        },
        "warnings": list(plan.warnings),
    }

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    return FIXTURE, len(foods), len(plan.items)


def run_dart_test() -> int:
    flutter = shutil.which("flutter")
    if flutter is None:
        print(
            "\n`flutter` is not on PATH — the fixture was written, run the "
            "Dart part by hand:\n"
            f"    cd mobile && flutter test {DART_TEST}"
        )
        return 0
    print(f"\n$ flutter test {DART_TEST}")
    completed = subprocess.run(
        [flutter, "test", DART_TEST],
        cwd=str(ROOT / "mobile"),
    )
    return completed.returncode


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="write the fixture only, do not call flutter test",
    )
    args = parser.parse_args()

    path, food_count, servings = build_fixture()
    print(
        f"\nWrote {path.relative_to(ROOT)} — {food_count} foods, a plan of "
        f"{servings} servings."
    )
    print(
        "Dish roles are translated into the Dart labels: "
        + ", ".join(f"{code} -> {label}" for code, label in ROLE_TO_DART.items())
    )
    print(
        "Exploration and the model score are OFF — the deterministic part is "
        "what can be compared. See the note at the top of this file."
    )

    if args.fixture_only:
        return 0
    return run_dart_test()


if __name__ == "__main__":
    raise SystemExit(main())
