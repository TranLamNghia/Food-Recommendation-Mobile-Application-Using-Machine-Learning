#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the Step 1 test cases, plus the Python reference to compare against.

Why it is needed. Step 1 — BMI, BMR, TDEE, the calorie limit, the macro split
and the per-meal split — is implemented **three times** in this project:

    backend/Api/Nutrition/NutritionTargets.cs        C#, the server
    mobile/lib/data/models/health_profile.dart       Dart, the app
    tools/gen_buoc1_cases.py (this file)             Python, the reference

The three run in three layers and never meet, so when they drift nothing
reports it: the app shows one limit, the server generates a meal plan from a
different one, and both numbers look plausible. It has happened: Dart hard-
coded the macro split 17/60/23, the API specification said 15/60/25, and the
`DEFAULT` column in the database also said 15/60/25 — three sources, two
numbers, unnoticed for weeks.

The formulas come from `docs/SYSTEM_ARCHITECTURE.md` §3.1. This file must NOT
copy them from the C# or the Dart — it has to be rewritten from the document,
otherwise it merely confirms that all three implementations are wrong the same
way.

The cases cover: all three genders (including `other`, for which no published
Mifflin constant exists), all five activity levels, all four goals, the
BMR floor constraint on `lose_weight`, all four BMI categories, and the .5
rounding cases.

Run:
    python tools/gen_buoc1_cases.py            # write data/buoc1_cases.json
    python tools/gen_buoc1_cases.py --print    # print it, write nothing

Note on language: the per-case keys `ten`, `vao` and `ra` stay as they are —
they are read by `backend/Api.Tests/Buoc1ParityTests.cs` and
`mobile/test/buoc1_parity_test.dart`, so renaming them has to happen in all
three files at once.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "buoc1_cases.json"

#: A FIXED reference date. Age depends on the day it is computed, so a case set
#: that hard-codes a date of birth without hard-coding "today" changes its
#: results every year — and changes on exactly one day of the year, so it would
#: slip past every other run.
TODAY = "2026-11-08"

ACTIVITY_FACTOR = {
    "sedentary": "1.200",
    "light": "1.375",
    "moderate": "1.550",
    "active": "1.725",
    "very_active": "1.900",
}

#: The midpoints of the ranges in §3.1: breakfast 25-30, lunch 35-40,
#: dinner 25-30, snack 5-10.
MEAL_SHARE = {
    "breakfast": "0.275",
    "lunch": "0.375",
    "dinner": "0.275",
    "snack": "0.075",
}

#: The Mifflin-St Jeor constants. `other` is the MIDPOINT of the other two — a
#: derived number with no published source. See the long note in
#: `NutritionTargets.Bmr`.
MIFFLIN_CONSTANT = {
    "male": Decimal("5"),
    "female": Decimal("-161"),
    "other": (Decimal("5") + Decimal("-161")) / Decimal("2"),
}


def age(date_of_birth: date, today: date) -> int:
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return years


def bmi(weight: Decimal, height_cm: Decimal) -> Decimal:
    metres = height_cm / Decimal(100)
    return weight / (metres * metres)


def bmi_category(value: Decimal) -> str:
    """The WHO 2004 Asian thresholds: 23 and 25, not 25 and 30."""
    if value < Decimal("18.5"):
        return "underweight"
    if value < Decimal(23):
        return "normal"
    if value < Decimal(25):
        return "overweight"
    return "obese"


def bmr(gender: str, weight: Decimal, height_cm: Decimal,
        age_years: int) -> Decimal:
    base = (Decimal(10) * weight + Decimal("6.25") * height_cm
            - Decimal(5) * Decimal(age_years))
    return base + MIFFLIN_CONSTANT[gender]


def tdee(bmr_value: Decimal, activity: str) -> Decimal:
    return bmr_value * Decimal(ACTIVITY_FACTOR[activity])


def calorie_limit(tdee_value: Decimal, bmr_value: Decimal,
                  goal: str) -> Decimal:
    if goal == "lose_weight":
        # Never below BMR — the safety constraint in §3.1.
        return max(tdee_value - Decimal(500), bmr_value)
    if goal == "gain_weight":
        return tdee_value + Decimal(500)
    return tdee_value          # maintain, healthy_eating


def round_half_up(value: Decimal, places: int = 0) -> float:
    """Round AWAY FROM ZERO, as Dart does and as
    `MidpointRounding.AwayFromZero` does.

    .NET's `Math.Round` defaults to rounding to EVEN (2.5 becomes 2), and
    Python's `round()` does the same. Dart rounds away from zero. The
    difference surfaces only on exactly the .5 cases — rare, so it would slip
    past every manual test.
    """
    quantum = Decimal(1) if places == 0 else Decimal(1).scaleb(-places)
    quantized = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return int(quantized) if places == 0 else float(quantized)


def one_case(name: str, gender: str, years_ago: int, height_cm: str,
             weight: str, activity: str, goal: str,
             pct=(15, 60, 25), date_of_birth: str | None = None) -> dict:
    today = date.fromisoformat(TODAY)
    if date_of_birth:
        born = date.fromisoformat(date_of_birth)
    else:
        born = date(today.year - years_ago, today.month, today.day)

    height, weight_kg = Decimal(height_cm), Decimal(weight)
    age_years = age(born, today)
    bmi_value = bmi(weight_kg, height)
    bmr_value = bmr(gender, weight_kg, height, age_years)
    tdee_value = tdee(bmr_value, activity)
    limit = calorie_limit(tdee_value, bmr_value, goal)
    protein_pct, carbs_pct, fat_pct = pct
    assert protein_pct + carbs_pct + fat_pct == 100, (
        f"{name}: the three percentages sum to "
        f"{protein_pct + carbs_pct + fat_pct}%"
    )

    return {
        # `ten` / `vao` / `ra` — see the note on language in the module
        # docstring: these three keys are a contract with the C# and Dart
        # parity tests.
        "ten": name,
        "vao": {
            "gender": gender,
            "dateOfBirth": born.isoformat(),
            "heightCm": float(height),
            "weightKg": float(weight_kg),
            "activityLevel": activity,
            "goal": goal,
            "proteinPct": protein_pct,
            "carbsPct": carbs_pct,
            "fatPct": fat_pct,
            "today": TODAY,
        },
        "ra": {
            "age": age_years,
            "bmi": round_half_up(bmi_value, 2),
            "bmiCategory": bmi_category(bmi_value),
            "bmrKcal": round_half_up(bmr_value),
            "tdeeKcal": round_half_up(tdee_value),
            "activityFactor": float(ACTIVITY_FACTOR[activity]),
            "dailyCaloriesTarget": round_half_up(limit),
            "goalAdjustmentKcal": round_half_up(limit - tdee_value),
            "proteinG": round_half_up(limit * Decimal(protein_pct) / 100 / 4, 1),
            "carbsG": round_half_up(limit * Decimal(carbs_pct) / 100 / 4, 1),
            "fatG": round_half_up(limit * Decimal(fat_pct) / 100 / 9, 1),
            "mealKcal": {
                meal: round_half_up(limit * Decimal(share))
                for meal, share in MEAL_SHARE.items()
            },
        },
    }


def all_cases() -> list[dict]:
    cases: list[dict] = []

    # -- The case from specification §7.2.3 -------------------------------
    cases.append(one_case("spec-7.2.3", "male", 22, "172", "68.5",
                          "moderate", "maintain"))

    # -- All three genders, everything else equal ------------------------
    for gender in ("male", "female", "other"):
        cases.append(one_case(f"gender-{gender}", gender, 22, "172", "68.5",
                              "moderate", "maintain"))

    # -- All five activity levels ----------------------------------------
    for activity in ACTIVITY_FACTOR:
        cases.append(one_case(f"activity-{activity}", "female", 30, "160",
                              "55", activity, "maintain"))

    # -- All four goals --------------------------------------------------
    for goal in ("lose_weight", "maintain", "gain_weight", "healthy_eating"):
        cases.append(one_case(f"goal-{goal}", "male", 25, "175", "80",
                              "active", goal))

    # -- The BMR floor: losing weight while sedentary makes TDEE-500 < BMR
    # BMR 1655 x 1.2 = 1986; 1986 - 500 = 1486, below BMR. Without the floor
    # the system would recommend eating below the basal metabolic rate.
    cases.append(one_case("bmr-floor", "male", 22, "172", "68.5",
                          "sedentary", "lose_weight"))
    cases.append(one_case("bmr-floor-female", "female", 60, "150", "45",
                          "sedentary", "lose_weight"))

    # -- All four BMI categories on the Asian thresholds -----------------
    for name, height, weight in (("bmi-underweight", "175", "50"),
                                 ("bmi-normal", "175", "68"),
                                 ("bmi-overweight", "175", "72"),
                                 ("bmi-obese", "175", "85")):
        cases.append(
            one_case(name, "male", 25, height, weight, "moderate", "maintain")
        )

    # -- Exactly on the 23 and 25 thresholds -----------------------------
    # 1.75^2 = 3.0625. 23 x 3.0625 = 70.4375; 25 x 3.0625 = 76.5625.
    cases.append(one_case("bmi-exactly-23", "male", 25, "175", "70.4375",
                          "moderate", "maintain"))
    cases.append(one_case("bmi-exactly-25", "male", 25, "175", "76.5625",
                          "moderate", "maintain"))

    # -- A birthday that has NOT yet occurred this year ------------------
    # The source of 12 failing checks on the smoke test's first run: a date of
    # birth of 14 Nov with a today of 08 Nov gives age 21, not 22.
    cases.append(one_case("birthday-not-yet", "male", 0, "172", "68.5",
                          "moderate", "maintain", date_of_birth="2004-11-14"))
    cases.append(one_case("birthday-exactly-today", "male", 0, "172", "68.5",
                          "moderate", "maintain", date_of_birth="2004-11-08"))
    cases.append(one_case("birthday-just-passed", "male", 0, "172", "68.5",
                          "moderate", "maintain", date_of_birth="2004-11-07"))

    # -- The edges of the allowed ranges ---------------------------------
    cases.append(one_case("edge-age-13", "female", 13, "150", "40",
                          "light", "healthy_eating"))
    cases.append(one_case("edge-age-100", "male", 100, "165", "60",
                          "sedentary", "maintain"))
    cases.append(one_case("edge-height-50", "other", 20, "50", "20",
                          "sedentary", "maintain"))
    cases.append(one_case("edge-height-250", "other", 20, "250", "300",
                          "very_active", "gain_weight"))

    # -- A .5 rounding case ----------------------------------------------
    # The BMR must land exactly on x.5 to tell rounding-to-even apart from
    # rounding away from zero. 10x60.05 + 6.25x170 - 5x25 + 5 = 600.5 + 1062.5
    # - 125 + 5 = 1543 — not .5 yet. An odd height is used to produce the .5.
    cases.append(one_case("round-half", "male", 25, "170.04", "60",
                          "sedentary", "maintain"))

    # -- Macro splits other than the default -----------------------------
    cases.append(one_case("macro-17-60-23", "male", 22, "172", "68.5",
                          "moderate", "maintain", pct=(17, 60, 23)))
    cases.append(one_case("macro-20-55-25", "male", 22, "172", "68.5",
                          "moderate", "maintain", pct=(20, 55, 25)))
    cases.append(one_case("macro-13-62-25", "female", 40, "158", "52",
                          "light", "lose_weight", pct=(13, 62, 25)))

    return cases


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="print it, write no file")
    args = parser.parse_args(argv)

    cases = all_cases()
    names = [c["ten"] for c in cases]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        print(f"duplicate case names: {sorted(duplicates)}", file=sys.stderr)
        return 1

    payload = {
        "_doc": "Step 1 test cases. Generated by tools/gen_buoc1_cases.py — "
                "do not edit by hand. The reference implementation is "
                "rewritten from SYSTEM_ARCHITECTURE §3.1, not copied from the "
                "C# or the Dart.",
        "today": TODAY,
        "activityFactor": {k: float(v) for k, v in ACTIVITY_FACTOR.items()},
        "mealShare": {k: float(v) for k, v in MEAL_SHARE.items()},
        "cases": cases,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.print_only:
        print(text)
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(cases)} test cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
