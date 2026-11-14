#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the F1 filter **in pure SQL** to prove the schema is sufficient.

Why this file exists. The F1 filter — the step that removes foods unsafe for a
user's conditions, allergies and diet — has **not one line of code** in the app
yet. The question to answer before freezing the ERD is not "has it been
written" but:

    Is the current schema enough to express F1, or are more tables/columns
    needed?

This file answers by **actually running it**: F1 built entirely in SQL over
`conditions`, `user_conditions`, `condition_rules`, `tags`, `food_tags` and
`foods` — no extra table, no application-layer processing. If it produces the
right results, the rest is translating this query into Dart or into the API
layer, and the ERD does not have to wait.

The three rule types in `condition_rules`:

    exclude_tag     drop every food carrying that tag    -> filterable per FOOD
    require_tag     keep only foods carrying that tag     -> filterable per FOOD
    nutrient_limit  a numeric threshold                   -> see below

Every **hard** `nutrient_limit` has `scope = 'per_day'`, so it filters NO food
at the candidate stage — a salty dish is still valid if the whole day stays
under the threshold. That is deliberate: an earlier version set hard
per-serving thresholds, and a 600 mg sodium limit removed 58 of 60 foods,
leaving Step 4 unable to build a meal plan at all. The daily part is enforced
by Step 4 phase 5, not by F1.

Run:
    python tools/check_f1.py

Note on language: the condition names in `SCENARIOS` are `conditions.name_vi`
values from the database and stay as they are; the `dish_role` keys are enum
values.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

# -- The F1 filter, written once in SQL ----------------------------------
#
# The only parameter is the user's list of condition ids. In the real system
# it comes from `user_conditions WHERE user_id = ?`; here it is passed
# directly so every combination can be tried without creating fake users.
#
# `owner_id IS NULL OR owner_id = ?` is the food-scope part: the shared
# catalogue plus the user's own foods. The `idx_active_category` index puts
# `owner_id` first precisely because of this clause.
F1_SQL = """
SELECT f.id, f.name
FROM foods f
WHERE f.is_active = 1
  AND (f.owner_id IS NULL OR f.owner_id = %(user_id)s)

  -- (1) exclude_tag — drop foods carrying a forbidden tag
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN food_tags ft ON ft.tag_id = cr.tag_id
        WHERE cr.rule_type = 'exclude_tag'
          AND cr.is_hard = 1
          AND cr.condition_id IN ({conds})
          AND ft.food_id = f.id
      )

  -- (2) require_tag — the food must carry EVERY required tag
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        WHERE cr.rule_type = 'require_tag'
          AND cr.is_hard = 1
          AND cr.condition_id IN ({conds})
          AND NOT EXISTS (
                SELECT 1 FROM food_tags ft
                WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
              )
      )

  -- (3) hard PER-SERVING nutrient_limit — no such row exists today; the
  --     clause is kept so the schema still holds if one is added later.
  --     Missing data means EXCLUDE, because safety cannot be proven.
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN food_nutrition fn ON fn.food_id = f.id
        WHERE cr.rule_type = 'nutrient_limit'
          AND cr.is_hard = 1
          AND cr.scope = 'per_serving'
          AND cr.condition_id IN ({conds})
          AND (
            CASE cr.nutrient
              WHEN 'sodium_mg'      THEN fn.sodium_mg
              WHEN 'sugar_g'        THEN fn.sugar_g
              WHEN 'purine_mg'      THEN fn.purine_mg
              WHEN 'protein_g'      THEN fn.protein_g
              WHEN 'fat_g'          THEN fn.fat_g
              WHEN 'carbs_g'        THEN fn.carbs_g
              WHEN 'cholesterol_mg' THEN fn.cholesterol_mg
              WHEN 'fiber_g'        THEN fn.fiber_g
              WHEN 'calories_kcal'  THEN fn.calories_kcal
            END IS NULL
            OR (cr.comparator = 'lte' AND
                CASE cr.nutrient
                  WHEN 'sodium_mg'      THEN fn.sodium_mg
                  WHEN 'sugar_g'        THEN fn.sugar_g
                  WHEN 'purine_mg'      THEN fn.purine_mg
                  WHEN 'protein_g'      THEN fn.protein_g
                  WHEN 'fat_g'          THEN fn.fat_g
                  WHEN 'carbs_g'        THEN fn.carbs_g
                  WHEN 'cholesterol_mg' THEN fn.cholesterol_mg
                  WHEN 'fiber_g'        THEN fn.fiber_g
                  WHEN 'calories_kcal'  THEN fn.calories_kcal
                END > cr.threshold)
          )
      )
"""

# Hard PER-DAY thresholds — these filter no food; Step 4 phase 5 enforces them.
PER_DAY_SQL = """
SELECT co.name_vi, cr.nutrient, cr.comparator, cr.threshold
FROM condition_rules cr
JOIN conditions co ON co.id = cr.condition_id
WHERE cr.rule_type = 'nutrient_limit'
  AND cr.is_hard = 1
  AND cr.scope = 'per_day'
  AND cr.condition_id IN ({conds})
ORDER BY co.name_vi, cr.nutrient
"""

# The user's self-declared targets — looked up by gender and age.
RDA_SQL = """
SELECT nutrient, rda_value, unit, source
FROM rda_reference
WHERE nutrient = %(nutrient)s
  AND gender IN ('all', %(gender)s)
  AND %(age)s BETWEEN age_min AND age_max
"""

# The combinations worth trying. The condition names are exactly
# `conditions.name_vi`.
SCENARIOS = [
    ("No condition", []),
    ("Hypertension", ["Tăng huyết áp"]),
    ("Gout", ["Gút"]),
    ("Kidney disease", ["Bệnh thận"]),
    ("Diabetes", ["Đái tháo đường"]),
    ("Dyslipidaemia", ["Rối loạn mỡ máu"]),
    ("Seafood allergy", ["Dị ứng hải sản"]),
    ("Peanut allergy", ["Dị ứng đậu phộng"]),
    ("Vegetarian", ["Ăn chay"]),
    ("Vegan", ["Ăn thuần chay"]),
    # Combinations — the most fragile part, because the rules intersect.
    ("Gout + seafood allergy", ["Gút", "Dị ứng hải sản"]),
    ("Vegetarian + egg allergy", ["Ăn chay", "Dị ứng trứng"]),
    (
        "Vegan + gout + hypertension",
        ["Ăn thuần chay", "Gút", "Tăng huyết áp"],
    ),
    (
        "Four metabolic conditions at once",
        ["Tăng huyết áp", "Đái tháo đường", "Gút", "Rối loạn mỡ máu"],
    ),
    # The hardest edge case: tofu and soy sauce ARE soy, so if every
    # vegetarian dish relies on them, this combination drops to 0 savoury
    # dishes and 0 soups. The catalogue deliberately includes vegetarian
    # dishes seasoned with salt and taking their protein from mushrooms
    # because of this case.
    ("Vegetarian + soy allergy", ["Ăn chay", "Dị ứng đậu nành"]),
    (
        "Vegan + soy allergy + hypertension",
        ["Ăn thuần chay", "Dị ứng đậu nành", "Tăng huyết áp"],
    ),
    ("Soy allergy", ["Dị ứng đậu nành"]),
]

# The minimum number of foods per role for Step 4 to build one day.
ROLES_NEEDED = {
    "main": 3,
    "side_protein": 2,
    "side_veg": 3,
    "soup": 2,
    "dessert": 1,
    "drink": 1,
}


def main() -> int:
    _env.use_utf8()
    try:
        import pymysql
    except ImportError:
        sys.exit("pymysql is required:  pip install pymysql")

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=_env.require("MYSQL_DATABASE"),
        charset="utf8mb4",
    )

    problems: list[str] = []

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name_vi FROM conditions")
            id_by_name = {name: cid for cid, name in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM foods WHERE is_active = 1")
            total = cur.fetchone()[0]

            print("=" * 78)
            print("THE F1 FILTER RUNNING IN PURE SQL")
            print(f"Catalogue: {total} active foods")
            print("=" * 78)

            print(f"\n{'Scenario':<36}{'candidates':>10}{'%':>7}"
                  f"{'roles met':>13}")
            print("-" * 78)

            for label, names in SCENARIOS:
                unknown = [n for n in names if n not in id_by_name]
                if unknown:
                    problems.append(
                        f"{label}: condition {unknown} is not in the "
                        f"`conditions` table"
                    )
                    continue

                ids = [id_by_name[n] for n in names]
                # An empty IN () is a syntax error; NULL makes the clause
                # always false instead.
                conds = ", ".join(str(i) for i in ids) if ids else "NULL"

                cur.execute(
                    F1_SQL.format(conds=conds), {"user_id": None}
                )
                allowed = cur.fetchall()

                # Count per role, to see whether Step 4 can still build a meal.
                if allowed:
                    # `foods.id` is a UUID string, not a number, so it cannot
                    # be interpolated into the statement directly — a missing
                    # quote is an immediate syntax error. Pass them as
                    # parameters, which is also the right way.
                    allowed_ids = [r[0] for r in allowed]
                    placeholders = ", ".join(["%s"] * len(allowed_ids))
                    cur.execute(
                        f"SELECT dish_role, COUNT(*) FROM foods "
                        f"WHERE id IN ({placeholders}) GROUP BY dish_role",
                        allowed_ids,
                    )
                    per_role = dict(cur.fetchall())
                else:
                    per_role = {}

                shortfall = [
                    f"{role} {per_role.get(role, 0)}/{need}"
                    for role, need in ROLES_NEEDED.items()
                    if per_role.get(role, 0) < need
                ]
                mark = "ok" if not shortfall else "BAD"
                print(
                    f"{label:<36}{len(allowed):>8}"
                    f"{len(allowed) / total * 100:>8.0f}%"
                    f"{mark:>9}  {', '.join(shortfall)}"
                )
                if shortfall:
                    problems.append(
                        f"{label}: too few foods in role "
                        f"{', '.join(shortfall)} — Step 4 cannot build a day"
                    )

            # -- Daily thresholds: filter nothing, but must be queryable --
            print("\n" + "-" * 78)
            print(
                "Hard PER-DAY thresholds — F1 does not filter; Step 4 phase 5 "
                "enforces"
            )
            print("-" * 78)
            all_ids = ", ".join(str(i) for i in id_by_name.values())
            cur.execute(PER_DAY_SQL.format(conds=all_ids))
            rows = cur.fetchall()
            for name, nutrient, comparator, threshold in rows:
                sign = "<=" if comparator == "lte" else ">="
                print(f"   {name:<20}{nutrient:<16}{sign} {threshold}")
            if not rows:
                problems.append(
                    "no hard per-day threshold could be queried — is "
                    "`condition_rules` empty?"
                )

            # -- Self-declared targets: queryable from rda_reference --
            print("\n" + "-" * 78)
            print("Self-declared targets looked up in `rda_reference`")
            print("-" * 78)
            for gender, age in (("male", 24), ("female", 24), ("male", 8)):
                cur.execute(
                    RDA_SQL,
                    {"nutrient": "fiber_g", "gender": gender, "age": age},
                )
                found = cur.fetchall()
                if not found:
                    problems.append(
                        f"no fibre requirement could be found for {gender} "
                        f"aged {age}"
                    )
                    print(f"   BAD  {gender} aged {age}: no row")
                    continue
                nutrient, value, unit, source = found[0]
                print(
                    f"   ok   {gender} aged {age}: {nutrient} >= {value} "
                    f"{unit}   ({source})"
                )
    finally:
        conn.close()

    print("\n" + "=" * 78)
    if problems:
        print(f"{len(problems)} problems:\n")
        for p in problems:
            print(f"  BAD  {p}")
    else:
        print("F1 IS FULLY EXPRESSIBLE WITH THE CURRENT SCHEMA.")
        print("No table missing, no column missing. What remains is")
        print("translating this query into the application layer.")
    print("=" * 78)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
