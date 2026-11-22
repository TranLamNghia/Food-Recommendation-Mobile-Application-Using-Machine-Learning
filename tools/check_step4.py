#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check Step 4 — the meal-plan builder. **No database needed.**

`ml/menu_builder.py` is a port of 675 lines of Dart, and a port is exactly
where a silent difference hides: both implementations return a plan, both
plans look like plans, and only the numbers differ. So every phase is checked
here on hand-built input, where the right answer can be worked out by hand.

The cases that matter are the ones the real catalogue does not contain: a role
with no food left in it, a nutrient ceiling no combination can satisfy, a meal
whose foods have no measurement for the nutrient a rule is about. The real data
has none of those today.

Run:
    python tools/check_step4.py

What this file does NOT do: compare against the Dart implementation. That is
`tools/check_step4_parity.py`, which needs Flutter.

Note on language: the dish-role strings, condition names and nutrient column
names asserted below are **data** — they are what `db/schema.sql` and
`condition_rules` hold.
"""

from __future__ import annotations

import random
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import use_utf8  # noqa: E402
from ml.f1_filter import ENFORCED_BY, SoftRule, unenforced_rules  # noqa: E402
from ml.features import FeatureSpace, Food  # noqa: E402
from ml.menu_builder import (  # noqa: E402
    MEAL_ENERGY_SHARE,
    MEAL_STRUCTURE,
    MEAL_TYPES,
    NUTRIENT_OF_FOOD,
    ROLE_FROM_DART,
    SUPPORTED_NUTRIENTS,
    UNUSED_ROLES,
    DailyPlan,
    MenuBuilder,
    NutrientTarget,
    PlanItem,
    targets_from_limit_rows,
    value_of,
)
from ml.rocchio import PreferenceProfile, empty_profile  # noqa: E402
from ml.scoring import meal_penalty  # noqa: E402

#: The `foods.dish_role` ENUM, copied from `db/schema.sql:409`. Written out
#: rather than read from the schema on purpose: if someone edits the ENUM, the
#: meal structure has to be revisited, and a check that reads the new value
#: would simply agree with it.
SCHEMA_ROLES = (
    "main", "side_protein", "side_veg", "soup", "dessert", "drink", "snack",
)

_passed = 0
_failures: list[str] = []


def check(condition: bool, description: str) -> None:
    global _passed
    if condition:
        _passed += 1
    else:
        _failures.append(description)
        print(f"  BAD  {description}")


def approx(actual: float, expected: float, description: str) -> None:
    check(
        abs(actual - expected) < 1e-9,
        f"{description}: got {actual!r}, expected {expected!r}",
    )


def raises(fn, exception_type, description: str) -> None:
    try:
        fn()
    except exception_type:
        check(True, description)
        return
    except Exception as e:
        check(
            False,
            f"{description}: raised {type(e).__name__} instead of "
            f"{exception_type.__name__}",
        )
        return
    check(False, f"{description}: raised nothing")


# ── Fixtures ──────────────────────────────────────────────────────────


def food(
    food_id: str,
    role: str,
    kcal: int,
    *,
    name: str | None = None,
    category: str = "Cơm",
    protein: float = 10.0,
    carb: float = 20.0,
    fat: float = 5.0,
    sugar: float = 4.0,
    sodium: float = 300.0,
    fiber: float = 2.0,
) -> Food:
    return Food(
        id=food_id,
        name=name or f"Dish {food_id}",
        category=category,
        dish_role=role,
        spice_level=0,
        kcal=kcal,
        protein=protein,
        carb=carb,
        fat=fat,
        sugar=sugar,
        sodium=sodium,
        fiber=fiber,
    )


def catalogue() -> list[Food]:
    """A small catalogue covering every role the meal structure asks for.

    Three foods per required role, so phase 3 and phase 5 have something to
    swap to; two categories, so the feature space has more than one one-hot
    dimension.
    """
    out: list[Food] = []
    plan = {
        "main": [(420, "Cơm"), (500, "Cơm"), (300, "Món nước")],
        "side_protein": [(180, "Món kho"), (220, "Món kho"), (140, "Món xào")],
        "side_veg": [(90, "Món xào"), (120, "Món luộc hấp"), (60, "Món xào")],
        "soup": [(80, "Món canh"), (110, "Món canh"), (50, "Món canh")],
        "snack": [(150, "Tráng miệng"), (200, "Tráng miệng"), (100, "Đồ uống")],
    }
    for role, rows in plan.items():
        for i, (kcal, category) in enumerate(rows, start=1):
            out.append(food(f"{role}-{i}", role, kcal, category=category))
    return out


def builder(
    foods: list[Food] | None = None,
    *,
    profile: PreferenceProfile | None = None,
    rng: random.Random | None = None,
    **kwargs,
) -> MenuBuilder:
    foods = catalogue() if foods is None else foods
    space = FeatureSpace.from_foods(foods)
    return MenuBuilder(
        candidates=foods,
        space=space,
        profile=profile if profile is not None else empty_profile(space),
        # A fixed seed by default, so a failure here is reproducible.
        rng=rng or random.Random(20261118),
        **kwargs,
    )


def role_catalogue(per_role: int = 4, **shared) -> list[Food]:
    """`per_role` foods in each role the meal structure asks for.

    Three of the four meals require a `main`, so a role needs at least three
    foods before any meal is complete and a fourth before phase 5 has
    anywhere to swap to. An earlier version of these fixtures gave each role
    two foods, and the repair phase had nothing to work with — the test
    failed on its own fixture rather than on the code.
    """
    out: list[Food] = []
    for role, kcal in (("main", 400), ("side_protein", 180),
                       ("side_veg", 90), ("soup", 80), ("snack", 150)):
        for i in range(1, per_role + 1):
            out.append(food(f"{role}-{i}", role, kcal, **shared))
    return out


DAY = date(2026, 11, 18)


def build(b: MenuBuilder, kcal: float = 2000.0) -> DailyPlan:
    """A plan with macro targets in the usual 20/50/30 energy split."""
    return b.build(
        plan_date=DAY,
        target_kcal=kcal,
        target_protein=kcal * 0.20 / 4,
        target_carb=kcal * 0.50 / 4,
        target_fat=kcal * 0.30 / 9,
    )


# -- 1. The shape of a day ---------------------------------------------


def check_structure() -> None:
    print("1. The shape of a day — meals, shares and dish roles")

    approx(sum(MEAL_ENERGY_SHARE.values()), 1.0, "the four shares sum to 1")
    check(
        tuple(MEAL_ENERGY_SHARE) == MEAL_TYPES,
        "every meal has a share, and in the same order",
    )
    check(
        MEAL_ENERGY_SHARE["lunch"] > MEAL_ENERGY_SHARE["breakfast"]
        > MEAL_ENERGY_SHARE["snack"],
        "lunch is the largest meal and the snack the smallest",
    )

    used = {r for s in MEAL_STRUCTURE.values() for r in s.required + s.optional}
    check(
        used <= set(SCHEMA_ROLES),
        f"every role in the meal structure exists in the schema ENUM, got "
        f"{sorted(used - set(SCHEMA_ROLES))} outside it",
    )
    # The limitation the port inherits, asserted so it cannot be forgotten:
    # two roles are in the ENUM and in no meal, so those foods are
    # unreachable. The builder reports it in `warnings`.
    check(
        set(UNUSED_ROLES) == set(SCHEMA_ROLES) - used,
        f"UNUSED_ROLES lists exactly the roles no meal asks for, got "
        f"{sorted(set(SCHEMA_ROLES) - used)}",
    )
    check(
        all(s.required for s in MEAL_STRUCTURE.values()),
        "every meal requires at least one serving",
    )

    # The Dart vocabulary. `menu_builder.dart` keys its structure on
    # Vietnamese labels from `MockFoods`, so the two implementations cannot be
    # compared without this mapping.
    check(
        set(ROLE_FROM_DART.values()) <= set(SCHEMA_ROLES),
        "every Dart role maps onto a schema role",
    )
    check(
        len(set(ROLE_FROM_DART.values())) == len(ROLE_FROM_DART),
        "the Dart mapping is one-to-one — two labels onto one role would "
        "make a parity comparison ambiguous",
    )
    check(ROLE_FROM_DART["Món canh"] == "soup", "'Món canh' is the soup role")


# -- 2. Day-level nutrient targets -------------------------------------


def check_nutrient_target() -> None:
    print("2. Day-level nutrient targets — fractions, both directions")

    ceiling = NutrientTarget.at_most("sodium_mg", 2000.0)
    floor = NutrientTarget.at_least("fiber_g", 25.0)

    approx(ceiling.violation(1500.0), 0.0, "under a ceiling is no violation")
    approx(ceiling.violation(2000.0), 0.0, "exactly at the ceiling is fine")
    approx(ceiling.violation(2400.0), 0.2, "400 over 2000 is a 0.2 violation")
    approx(floor.violation(20.0), 0.2, "5 g short of 25 g is 0.2")
    approx(floor.violation(30.0), 0.0, "over a floor is no violation")
    check(ceiling.is_satisfied_by(2000.0), "the boundary counts as satisfied")

    # A fraction, not an absolute amount: the repair phase has to rank a
    # fibre shortfall against a sodium excess, and 5 g against 5 mg is not a
    # comparison.
    check(
        NutrientTarget.at_most("sodium_mg", 2000.0).violation(2200.0)
        < NutrientTarget.at_least("fiber_g", 25.0).violation(15.0),
        "200 mg over a 2000 mg ceiling is a smaller problem than 10 g short "
        "of a 25 g floor",
    )
    approx(
        NutrientTarget.at_most("sodium_mg", 0.0).violation(500.0), 0.0,
        "a zero threshold cannot be divided by, so it reports no violation",
    )

    # `null` is not 0 — the invariant that keeps a safety layer from failing
    # open on missing data.
    dish = food("x", "main", 400)
    check(value_of(dish, "sodium_mg") == 300.0, "value_of reads sodium")
    check(value_of(dish, "purine_mg") is None, "purine has no Food field")
    check(
        "purine_mg" not in SUPPORTED_NUTRIENTS,
        "purine is deliberately unsupported — the table publishes it for 70 "
        "of 318 foods, and summing the rest as 0 makes the gout ceiling "
        "unreachable",
    )
    check(
        set(NUTRIENT_OF_FOOD) == SUPPORTED_NUTRIENTS,
        "the supported set is exactly the mapped set",
    )
    check(
        all(hasattr(dish, attribute) for attribute in NUTRIENT_OF_FOOD.values()),
        "every mapped nutrient names a real Food field",
    )

    rows = [
        {"nutrient": "sodium_mg", "comparator": "lte", "threshold": 2000.0,
         "name_vi": "Tăng huyết áp"},
        {"nutrient": "fiber_g", "comparator": "gte", "threshold": 25.0,
         "name_vi": ""},
    ]
    targets = targets_from_limit_rows(rows)
    check(len(targets) == 2, "two rows convert to two targets")
    check(not targets[0].is_floor and targets[1].is_floor, "lte is a ceiling, gte a floor")
    check(targets[0].condition == "Tăng huyết áp", "the condition travels with the target")
    raises(
        lambda: targets_from_limit_rows(
            [{"nutrient": "sodium_mg", "comparator": "between",
              "threshold": 1.0, "name_vi": ""}]
        ),
        ValueError,
        "an unknown comparator raises rather than being dropped — a "
        "threshold silently discarded is enforced nowhere",
    )


# -- 3. Phase 1, the greedy pick ---------------------------------------


def check_greedy() -> None:
    print("3. Phase 1 — greedy by score density")

    # Score density, NOT score: `score / kcal`, weighted by how well the
    # food fits the serving's target.
    #
    # The consequence is worth writing down, because it is easy to expect the
    # opposite. With an empty profile every food scores 0.5, so the density
    # is 0.5/kcal and the lightest food wins — even when a heavier one sits
    # exactly on the slot target. The fit weight spans [0.35, 1], a factor of
    # 2.86, while halving the energy doubles the density: on tied scores the
    # weighting narrows the gap but cannot reverse it.
    b = builder()
    pool = [food("300", "main", 300), food("600", "main", 600),
            food("450", "main", 450)]
    for target in (0.0, 450.0, 600.0, 2000.0):
        picked = b._greedy_pick(pool=pool, profile=b.profile, slot_target_kcal=target)
        check(
            picked.id == "300",
            f"on tied scores the lightest food wins at target {target}, got "
            f"{picked.id}",
        )

    # So what the fit term actually does is break the tie between foods of
    # the same energy — and taste is what separates them. A profile pointing
    # at one category makes that category's food win at equal energy.
    space = FeatureSpace.from_foods(catalogue())
    tied = [
        food("rice", "main", 400, category="Cơm"),
        food("soup", "main", 400, category="Món nước"),
    ]
    rice_weights = [0.0] * space.length
    rice_weights[space.length - len(space.categories) + space.categories.index("Cơm")] = 1.0
    leaning = PreferenceProfile(
        weights=tuple(rice_weights), sum_abs_weight=1.0, n_signals=40
    )
    picked = MenuBuilder(
        candidates=tied, space=space, profile=leaning,
    )._greedy_pick(pool=tied, profile=leaning, slot_target_kcal=400.0)
    check(
        picked.id == "rice",
        f"at equal energy the preferred category wins, got {picked.id}",
    )

    # A 0 kcal food would divide by zero. It is skipped, not crashed on.
    only_zero = [food("z", "main", 0)]
    picked = b._greedy_pick(pool=only_zero, profile=b.profile, slot_target_kcal=400.0)
    check(
        picked.id == "z",
        "a pool of only 0 kcal foods still returns a food rather than failing",
    )


# -- 4. A whole plan ---------------------------------------------------


def check_plan() -> None:
    print("4. A whole plan — structure, no repeats, and the energy target")

    plan = build(builder())

    check(len(plan.slots) == 4, "a plan has the four meals")
    check(
        [s.meal_type for s in plan.slots] == list(MEAL_TYPES),
        "the meals come out in day order",
    )
    for slot in plan.slots:
        shape = MEAL_STRUCTURE[slot.meal_type]
        roles = [i.food.dish_role for i in slot.items]
        check(
            all(role in roles for role in shape.required),
            f"{slot.meal_type} has every required role, got {roles}",
        )
        check(
            len(roles) == len(set(roles)),
            f"{slot.meal_type} has no two servings of the same role, got {roles}",
        )
        approx(
            slot.target_kcal,
            plan.target_kcal * MEAL_ENERGY_SHARE[slot.meal_type],
            f"{slot.meal_type}'s target is its share of the day",
        )

    ids = [i.food.id for i in plan.items]
    check(
        len(ids) == len(set(ids)),
        f"no food appears twice in a day, got {sorted(ids)}",
    )
    # The `usedIds` bookkeeping between phase 3 and the next meal is what
    # protects this. Without it a food swapped into breakfast is still free
    # for lunch, and the same dish is served twice.

    approx(
        plan.actual_kcal,
        sum(float(i.food.kcal) for i in plan.items),
        "the plan's energy is the sum of its servings",
    )
    check(
        plan.within_tolerance,
        f"the plan is within the 10 % the proposal commits to, got "
        f"{plan.deviation_pct:.2f} %",
    )
    approx(
        plan.deviation_pct,
        (plan.actual_kcal - 2000.0) / 2000.0 * 100,
        "deviation_pct matches what the generated column computes",
    )
    check(
        plan.total_preference_score > 0,
        "the plan carries a total preference score for `meal_plans`",
    )

    # A target of 0 must not divide by zero anywhere.
    zero = builder().build(
        plan_date=DAY, target_kcal=0.0, target_protein=0.0,
        target_carb=0.0, target_fat=0.0,
    )
    approx(zero.deviation_pct, 0.0, "a zero target reports zero deviation")


def check_missing_roles() -> None:
    print("5. Phase 1 — a role with no food left")

    # Lunch needs `main` and `side_protein`. Take `side_protein` away
    # entirely: the serving must be SKIPPED, not filled with the wrong role.
    foods = [f for f in catalogue() if f.dish_role != "side_protein"]
    plan = build(builder(foods))

    lunch = next(s for s in plan.slots if s.meal_type == "lunch")
    roles = [i.food.dish_role for i in lunch.items]
    check(
        "side_protein" not in roles,
        f"the missing role is not filled by another, got {roles}",
    )
    check(
        all(r in ("main", "soup") for r in roles),
        f"lunch holds only roles it asked for, got {roles}",
    )
    check(
        any("side_protein" in w for w in plan.warnings),
        f"the plan says which role was missing, got {plan.warnings}",
    )
    check(
        any("required servings" in w for w in plan.warnings),
        "and that a meal came out short",
    )

    # An unreachable role is reported too: `dessert` and `drink` are in the
    # schema and in no meal.
    with_dessert = catalogue() + [food("d1", "dessert", 150)]
    plan = build(builder(with_dessert))
    check(
        any("never be selected" in w for w in plan.warnings),
        f"foods whose role no meal asks for are reported, got {plan.warnings}",
    )
    check(
        all(i.food.dish_role != "dessert" for i in plan.items),
        "and are indeed never selected",
    )


# -- 6. Phase 2 and 4, the top-up --------------------------------------


def check_top_up() -> None:
    print("6. Phases 2 and 4 — topping up at the day level")

    # A target far above what the required servings can reach, so the
    # optional roles have to be used.
    plan = build(builder(), kcal=2000.0)
    optional_used = [
        i.food.dish_role
        for s in plan.slots
        for i in s.items
        if i.food.dish_role in MEAL_STRUCTURE[s.meal_type].optional
    ]
    check(
        optional_used != [],
        "optional servings are added when the day is short of its target",
    )
    check(
        all(i.exploration_delta is None for s in plan.slots for i in s.items
            if i.food.dish_role in MEAL_STRUCTURE[s.meal_type].optional),
        "an optional serving is never an exploration serving — the 70-30 "
        "budget is counted over the required servings only",
    )

    # A tiny target: topping up must not make the gap worse, so nothing is
    # added beyond the required servings.
    small = build(builder(), kcal=200.0)
    check(
        all(
            i.food.dish_role in MEAL_STRUCTURE[s.meal_type].required
            for s in small.slots
            for i in s.items
        ),
        "nothing optional is added when the plan is already over its target",
    )


# -- 7. Phase 3, the local search --------------------------------------


def check_local_search() -> None:
    print("7. Phase 3 — local search on the penalised objective")

    b = builder()
    items = [PlanItem(food=food("main-1", "main", 420), score=0.5)]
    low = b._objective(
        items, meal="lunch", target_kcal=420.0, target_protein=10.0,
        target_carb=20.0, target_fat=5.0,
    )
    off = b._objective(
        items, meal="lunch", target_kcal=900.0, target_protein=10.0,
        target_carb=20.0, target_fat=5.0,
    )
    check(
        low > off,
        "the objective prefers the selection closer to the energy target",
    )

    # The penalty terms are penalties, not disqualifications: a solution far
    # from target still scores, so the search can pass through it.
    check(off > -100, "a far-off selection is penalised, not rejected outright")

    # λ and μ have to bite.
    strict = builder(energy_penalty=10.0)
    check(
        strict._objective(
            items, meal="lunch", target_kcal=900.0, target_protein=10.0,
            target_carb=20.0, target_fat=5.0,
        )
        < off,
        "a larger λ penalises the same deviation harder",
    )

    # Local search must not pick a food another meal already holds.
    plan = build(builder())
    ids = [i.food.id for i in plan.items]
    check(len(ids) == len(set(ids)), "no duplicate survives the local search")


# -- 8. Phase 5, the nutrient repair -----------------------------------


def check_repair() -> None:
    print("8. Phase 5 — repairing the day-level constraints")

    # Every role gets four salty foods and four mild ones of the same
    # energy, so phase 1 fills the plan from either group and phase 5 has
    # somewhere to swap to.
    foods: list[Food] = []
    for role, kcal in (("main", 400), ("side_protein", 180), ("side_veg", 90),
                       ("soup", 80), ("snack", 150)):
        for i in range(1, 5):
            foods.append(food(f"{role}-salty-{i}", role, kcal, sodium=900.0))
            foods.append(food(f"{role}-mild-{i}", role, kcal, sodium=100.0))

    ceiling = NutrientTarget.at_most("sodium_mg", 1000.0, "Tăng huyết áp")
    plan = build(builder(foods, nutrient_targets=[ceiling]))
    total_sodium = plan.total_of("sodium_mg")
    check(
        total_sodium <= 1000.0,
        f"the repair brought the day under its sodium ceiling, got "
        f"{total_sodium}",
    )
    check(plan.nutrient_violations == [], "so nothing is reported as violated")
    check(plan.meets_nutrient_targets, "and the plan reports its targets met")

    # Now make it impossible: every food is salty. The phase must stop and
    # REPORT, not swap pointlessly or return an empty plan.
    salty = role_catalogue(sodium=900.0)
    plan = build(builder(salty, nutrient_targets=[ceiling]))
    check(plan.items != [], "an unsatisfiable constraint still returns a plan")
    violations = plan.nutrient_violations
    check(
        len(violations) == 1 and violations[0][0].nutrient == "sodium_mg",
        f"the violation is reported rather than hidden, got {violations}",
    )
    check(
        not plan.meets_nutrient_targets,
        "and the plan does not claim its targets are met",
    )

    # Condition 2: a swap must not break a constraint that currently holds.
    # Fibre floor and sodium ceiling together, where the only high-fibre food
    # is also the saltiest — fixing fibre would breach sodium.
    mixed = role_catalogue(sodium=100.0, fiber=1.0) + [
        food("main-fibre", "main", 400, sodium=5000.0, fiber=30.0),
    ]
    plan = build(builder(
        mixed,
        nutrient_targets=[
            NutrientTarget.at_least("fiber_g", 25.0, "Mục tiêu"),
            NutrientTarget.at_most("sodium_mg", 1000.0, "Tăng huyết áp"),
        ],
    ))
    check(
        plan.total_of("sodium_mg") <= 1000.0,
        f"the sodium ceiling that already held is not broken to chase fibre, "
        f"got {plan.total_of('sodium_mg')}",
    )
    check(
        any(t.nutrient == "fiber_g" for t, _ in plan.nutrient_violations),
        "the fibre shortfall is reported instead",
    )

    # Condition 3: the repair must not push the energy deviation past the cap.
    heavy = role_catalogue(sodium=900.0) + [
        food("main-huge", "main", 2000, sodium=10.0),
    ]
    plan = build(builder(
        heavy, nutrient_targets=[NutrientTarget.at_most("sodium_mg", 500.0)],
    ))
    check(
        all(i.food.id != "main-huge" for i in plan.items),
        "a 2000 kcal swap is refused even though it would fix the sodium — "
        "curing one violation by creating another is not a repair",
    )

    # An unsupported nutrient is kept apart, never counted as satisfied.
    plan = build(builder(
        nutrient_targets=[NutrientTarget.at_most("purine_mg", 400.0, "Gút")],
    ))
    check(
        plan.nutrient_violations == [],
        "an unenforceable target is not reported as a violation",
    )
    check(
        [t.nutrient for t in plan.unenforceable_targets] == ["purine_mg"],
        f"it is reported as unenforceable, got {plan.unenforceable_targets}",
    )
    check(
        not plan.meets_nutrient_targets,
        "and `meets_nutrient_targets` is False — a plan whose purine was "
        "never checked must not read as meeting a gout limit",
    )


# -- 9. The per-meal scope, newly enforced -----------------------------


def check_per_meal() -> None:
    print("9. The `per_meal` scope — the gap Step 4 closes")

    check(
        ENFORCED_BY["per_meal"] == "ml/scoring.meal_penalty",
        f"the scope now names its enforcing layer, got {ENFORCED_BY['per_meal']!r}",
    )
    carb_rule = SoftRule(
        condition="Đái tháo đường", severity_min="mild", nutrient="carbs_g",
        comparator="lte", threshold=60.0, penalty=0.700, scope="per_meal",
    )
    check(
        unenforced_rules([carb_rule]) == [],
        "and the rule is no longer reported as unenforced",
    )

    # Applied to the meal TOTAL, not per food. Two 40 g dishes are 80 g: over
    # the 60 g threshold, although neither dish exceeds it on its own. That
    # is the case a per-food reading misses.
    over = meal_penalty({"carbs_g": 80.0}, [carb_rule])
    approx(over.factor, 0.700, "a meal over the threshold is penalised")
    check(over.is_penalised, "and reports itself penalised")
    under = meal_penalty({"carbs_g": 55.0}, [carb_rule])
    approx(under.factor, 1.0, "a meal under the threshold is untouched")
    check(
        len(over.violations) == 1
        and over.violations[0].condition == "Đái tháo đường",
        "the violation names the condition, for the explanation",
    )

    # A multiplier, not a subtraction. The harsher level has the SMALLER
    # coefficient, and two bands of one condition count once.
    harsh = SoftRule(
        condition="Đái tháo đường", severity_min="severe", nutrient="carbs_g",
        comparator="lte", threshold=45.0, penalty=0.400, scope="per_meal",
    )
    combined = meal_penalty({"carbs_g": 80.0}, [carb_rule, harsh])
    approx(
        combined.factor, 0.400,
        "two nested bands of one condition are ONE concern — harshest wins, "
        "not 0.7 x 0.4",
    )
    other = SoftRule(
        condition="Tăng huyết áp", severity_min="mild", nutrient="sodium_mg",
        comparator="lte", threshold=700.0, penalty=0.600, scope="per_meal",
    )
    across = meal_penalty({"carbs_g": 80.0, "sodium_mg": 900.0}, [carb_rule, other])
    approx(
        across.factor, 0.700 * 0.600,
        "two different concerns do multiply",
    )

    # Scope discipline: the wrong scope is a programming error, not odd data.
    raises(
        lambda: meal_penalty(
            {"carbs_g": 80.0},
            [SoftRule(
                condition="x", severity_min="mild", nutrient="carbs_g",
                comparator="lte", threshold=60.0, penalty=0.7,
                scope="per_serving",
            )],
        ),
        ValueError,
        "a per_serving rule passed to meal_penalty raises",
    )

    # Missing data. A total is a LOWER bound, so a ceiling already exceeded
    # by the measured part is certain; anything else is undecided and must
    # not be penalised, only recorded.
    certain = meal_penalty({"carbs_g": 80.0}, [carb_rule], missing={"carbs_g": 2})
    approx(
        certain.factor, 0.700,
        "a ceiling already exceeded stays exceeded whatever is unmeasured",
    )
    check(
        certain.missing_data == ("carbs_g",),
        "and the incompleteness is recorded even so",
    )
    undecided = meal_penalty({"carbs_g": 55.0}, [carb_rule], missing={"carbs_g": 2})
    approx(
        undecided.factor, 1.0,
        "a ceiling not yet reached with servings unmeasured is undecided, so "
        "it is not penalised",
    )
    check(
        undecided.missing_data == ("carbs_g",),
        "but it is NOT reported as checked either",
    )
    floor_rule = SoftRule(
        condition="Mục tiêu", severity_min="mild", nutrient="fiber_g",
        comparator="gte", threshold=10.0, penalty=0.800, scope="per_meal",
    )
    short = meal_penalty({"fiber_g": 4.0}, [floor_rule], missing={"fiber_g": 1})
    approx(
        short.factor, 1.0,
        "a floor not reached is undecided too — the unmeasured servings "
        "could lift the total over it",
    )
    approx(
        meal_penalty({"fiber_g": 4.0}, [floor_rule]).factor, 0.800,
        "with full data the same floor IS penalised",
    )

    # And the effect inside the builder: a meal over the carbohydrate
    # threshold scores lower than the same meal under it.
    b = builder(per_meal_rules=[carb_rule])
    heavy_carb = [PlanItem(food=food("a", "main", 400, carb=80.0), score=1.0)]
    light_carb = [PlanItem(food=food("b", "main", 400, carb=40.0), score=1.0)]
    # target_carb = 70, deliberately between the two dishes. At 80 the two
    # objectives come out EQUAL — the penalty on the heavy dish exactly
    # cancels the macro penalty on the light one — and a test that passes on
    # a tie proves nothing about which way the penalty pushes.
    kwargs = dict(meal="lunch", target_kcal=400.0, target_protein=10.0,
                  target_carb=70.0, target_fat=5.0)
    check(
        b._objective(heavy_carb, **kwargs) < b._objective(light_carb, **kwargs),
        "inside the objective, the meal over its carbohydrate threshold "
        "loses to the one under it",
    )
    # Without the rule the heavy-carb meal would WIN on the macro term, which
    # is what makes the comparison above meaningful rather than incidental.
    plain = builder()
    check(
        plain._objective(heavy_carb, **kwargs) > plain._objective(light_carb, **kwargs),
        "and with no per-meal rule it wins instead — so the penalty is what "
        "changed the outcome",
    )
    # A rule of another scope handed to the builder is ignored rather than
    # applied at the wrong level.
    mixed = builder(per_meal_rules=[
        carb_rule,
        SoftRule(condition="x", severity_min="mild", nutrient="sodium_mg",
                 comparator="lte", threshold=1.0, penalty=0.1,
                 scope="per_day"),
    ])
    check(
        len(mixed.per_meal_rules) == 1,
        "the builder keeps only the per_meal rules it was given",
    )


# -- 10. Exploration ---------------------------------------------------


def check_exploration() -> None:
    print("10. Exploration — the 70-30 mechanism")

    b = builder(exploration_ratio=0.3)
    slots = b._assign_exploration_slots(0.3)
    required = sum(len(MEAL_STRUCTURE[m].required) for m in MEAL_TYPES)
    check(len(slots) == required, f"one slot per required serving, got {len(slots)}")
    check(
        sum(1 for s in slots if s.explore) == round(required * 0.3),
        "the exploration budget is the rounded share of the whole plan — not "
        "a share of each meal, which would round down to 0 every time",
    )

    # The cap. More than half the plan being a trial dish is no longer a
    # personalised recommendation, and `chk_expl_ratio` enforces it in the
    # database too.
    capped = build(builder(exploration_ratio=0.9))
    check(capped.exploration_ratio == 0.5, "the ratio is capped at 0.5")
    check(
        build(builder(exploration_ratio=-1.0)).exploration_ratio == 0.0,
        "and floored at 0",
    )

    plan = build(builder(exploration_ratio=0.3, exploration_delta=0.35))
    deltas = {i.exploration_delta for i in plan.items if i.is_exploration}
    check(
        deltas in ({0.35}, set()),
        f"an exploration serving records the δ it was chosen with, got {deltas}",
    )
    check(
        all(i.exploration_delta is None or i.exploration_delta > 0
            for i in plan.items),
        "an exploitation serving records NULL, not 0 — `exploration_delta IS "
        "NOT NULL` is what distinguishes the two groups",
    )
    check(
        0.0 <= plan.actual_exploration_ratio <= 1.0,
        "the achieved ratio is a ratio",
    )

    # With no exploration the plan is fully deterministic — no RNG is
    # consulted at all. This is the property `check_step4_parity.py` relies
    # on, because Dart and Python do not share a random generator.
    first = build(builder(exploration_ratio=0.0, rng=random.Random(1)))
    second = build(builder(exploration_ratio=0.0, rng=random.Random(99)))
    check(
        [i.food.id for i in first.items] == [i.food.id for i in second.items],
        "two different seeds give the same plan at ratio 0 — the part the "
        "parity checker can compare",
    )
    check(
        all(not i.is_exploration for i in first.items),
        "and no serving is marked as exploration",
    )

    # The jittered profile is a rotation, not a replacement: it keeps the
    # same number of dimensions, and an empty profile has no direction to
    # rotate.
    space = FeatureSpace.from_foods(catalogue())
    weights = tuple([0.1] * space.length)
    rotated = builder()._jittered(
        PreferenceProfile(weights=weights, sum_abs_weight=1.0, n_signals=40)
    )
    check(len(rotated.weights) == space.length, "the rotation keeps the dimensions")
    check(rotated.weights != weights, "and does move the vector")
    check(
        rotated.n_signals == 40,
        "the signal count is carried over — the stage must not change "
        "because the vector was jittered",
    )
    empty = empty_profile(space)
    check(
        builder()._jittered(empty).weights == empty.weights,
        "an empty profile is returned untouched: there is no direction to "
        "rotate, and jitter would invent a preference nobody expressed",
    )


# -- 11. The plan as a row ---------------------------------------------


def check_plan_row() -> None:
    print("11. The plan as `meal_plans` and `meal_plan_items`")

    plan = build(builder(
        nutrient_targets=[NutrientTarget.at_most("sodium_mg", 5000.0)],
    ))
    check(plan.plan_date == DAY, "the plan carries its date")
    check(
        0.0 <= plan.exploration_ratio <= 0.5,
        "exploration_ratio is within what `chk_expl_ratio` allows",
    )
    check(
        all(0.0 <= i.score <= 1.0 for i in plan.items),
        "every predicted_score is in [0, 1], the range the column expects",
    )
    check(
        all(i.food.dish_role in SCHEMA_ROLES for i in plan.items),
        "every serving's role is a value the ENUM accepts",
    )
    approx(
        plan.actual_protein,
        sum(i.food.protein for i in plan.items),
        "actual_protein is the sum over the servings",
    )
    check(
        plan.actual_kcal > 0 and plan.actual_carb > 0 and plan.actual_fat > 0,
        "the actual_* figures are filled in, so `calorie_deviation_pct` has "
        "something to divide — the column must never see a 0 total",
    )

    # An empty plan reports nothing rather than claiming success.
    nothing = MenuBuilder(
        candidates=[],
        space=FeatureSpace.from_foods(catalogue()),
        profile=empty_profile(FeatureSpace.from_foods(catalogue())),
    ).build(
        plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
        target_carb=250.0, target_fat=67.0,
    )
    check(nothing.items == [], "no candidates means no servings")
    approx(nothing.actual_exploration_ratio, 0.0, "and no exploration ratio")
    check(
        len(nothing.warnings) >= len(MEAL_TYPES),
        f"every meal reports itself short, got {nothing.warnings}",
    )


# -- 12. Alternatives for one serving ----------------------------------


def check_alternatives() -> None:
    print("12. Alternatives — the `swap this dish` list")

    b = builder()
    item = PlanItem(food=food("main-1", "main", 420), score=0.5)
    options = b.alternatives_for(item, exclude_ids={"main-1"})
    check(options != [], "there are alternatives")
    check(
        all(f.dish_role == "main" for f in options),
        "every alternative has the same role — a replacement has to fit the "
        "same slot in the meal",
    )
    check(
        all(f.id != "main-1" for f in options),
        "the dish being replaced is not offered back",
    )
    check(
        len(b.alternatives_for(item, exclude_ids=set(), limit=2)) == 2,
        "the limit is honoured",
    )
    # With an empty profile every score ties, so the tie-break decides: the
    # food closest in energy to the one being replaced comes first.
    closest = b.alternatives_for(item, exclude_ids={"main-1"})[0]
    check(
        closest.id == "main-2",
        f"on a score tie the closest in energy comes first, got {closest.id}",
    )


# -- 13. Stage 2 — the model's score reaching the plan -----------------


def check_ml_scores() -> None:
    print("13. Stage 2 — the model's score reaching the plan")

    foods = role_catalogue()
    space = FeatureSpace.from_foods(foods)
    liked, disliked = foods[0], foods[1]
    scores = {liked.id: 0.95, disliked.id: 0.05}

    def with_signals(n: int, ml: dict[str, float] | None) -> MenuBuilder:
        return MenuBuilder(
            candidates=foods,
            space=space,
            profile=PreferenceProfile(
                weights=tuple([0.0] * space.length),
                sum_abs_weight=0.0,
                n_signals=n,
            ),
            ml_scores=ml,
            rng=random.Random(7),
        )

    # No model scores: the cosine alone, which is the Dart behaviour and the
    # path `check_step4_parity.py` compares.
    plain = with_signals(100, None)
    approx(
        plain._score(plain.profile, liked), 0.5,
        "with no model score an empty profile gives the neutral 0.5",
    )

    # Below the hybrid threshold alpha is 0, so the model has no say even
    # when its scores are supplied — the same smooth hand-over Step 3 uses.
    cold = with_signals(0, scores)
    approx(
        cold._score(cold.profile, liked), 0.5,
        "at 0 signals alpha is 0 and the model is ignored",
    )

    # At 100 signals alpha is 1 and the plan ranks by the model.
    hot = with_signals(100, scores)
    approx(hot._score(hot.profile, liked), 0.95, "at 100 signals the score IS the model's")
    approx(hot._score(hot.profile, disliked), 0.05, "for the disliked food too")
    check(
        hot._score(hot.profile, foods[2]) == 0.5,
        "a food the model said nothing about keeps the cosine score",
    )

    # And it changes the plan, which is the point: a Step 4 ranking by cosine
    # alone would leave the trained model influencing nothing the user sees.
    main_foods = [f for f in foods if f.dish_role == "main"]
    favoured = main_foods[-1]
    biased = MenuBuilder(
        candidates=foods,
        space=space,
        profile=PreferenceProfile(
            weights=tuple([0.0] * space.length), sum_abs_weight=0.0,
            n_signals=100,
        ),
        ml_scores={favoured.id: 1.0},
        exploration_ratio=0.0,
        rng=random.Random(7),
    )
    plan = build(biased)
    check(
        any(i.food.id == favoured.id for i in plan.items),
        f"the food the model scored 1.0 is in the plan, got "
        f"{[i.food.id for i in plan.items]}",
    )
    check(
        any(i.score > 0.9 for i in plan.items),
        "and its predicted_score carries the model's number into "
        "`meal_plan_items`",
    )


# -- 14. Rebuilding one meal of a day ----------------------------------


def check_one_meal() -> None:
    print("14. Rebuilding one meal — the day stays the unit of measurement")

    foods = role_catalogue(per_role=5)

    # A whole day first, to take the other three meals from.
    whole = build(builder(foods, exploration_ratio=0.0))
    kept = {
        slot.meal_type: list(slot.items)
        for slot in whole.slots
        if slot.meal_type != "snack"
    }
    before_snack = [
        i.food.id for s in whole.slots if s.meal_type == "snack"
        for i in s.items
    ]

    again = builder(foods, exploration_ratio=0.0).build(
        plan_date=DAY,
        target_kcal=2000.0,
        target_protein=100.0,
        target_carb=250.0,
        target_fat=66.7,
        only_meals=["snack"],
        kept=kept,
    )

    by_meal = {s.meal_type: s for s in again.slots}
    check(
        len(again.slots) == 4,
        "a rebuilt meal still answers with the whole day's four meals",
    )
    for meal, items in kept.items():
        check(
            [i.food.id for i in by_meal[meal].items]
            == [i.food.id for i in items],
            f"{meal} is untouched when only the snack is rebuilt",
        )
    check(
        [i.food.id for i in by_meal["snack"].items] != [],
        "the rebuilt meal has servings",
    )

    # The day's energy includes the kept meals. This is the property the
    # whole design rests on: assembling one meal against one meal's share
    # would make `deviation_pct` a deviation from 7.5 % of a target,
    # reported in the column that states the day's.
    approx(
        again.actual_kcal,
        sum(i.kcal for s in again.slots for i in s.items),
        "the day's energy counts the kept meals too",
    )
    check(
        again.actual_kcal > by_meal["snack"].actual_kcal,
        "and is larger than the rebuilt meal on its own",
    )
    approx(
        again.target_kcal, 2000.0,
        "the target stays the DAY's target, not the meal's share",
    )

    # No dish may appear twice, across the kept meals and the rebuilt one.
    ids = [i.food.id for s in again.slots for i in s.items]
    check(
        len(ids) == len(set(ids)),
        "no dish is served twice when one meal is rebuilt",
    )
    kept_ids = {i.food.id for items in kept.values() for i in items}
    check(
        not (kept_ids & {i.food.id for i in by_meal["snack"].items}),
        "the rebuilt meal cannot take a dish that is already on the plate",
    )

    # Rebuilding every meal is the same thing as building the day.
    all_four = builder(foods, exploration_ratio=0.0).build(
        plan_date=DAY,
        target_kcal=2000.0,
        target_protein=100.0,
        target_carb=250.0,
        target_fat=66.7,
        only_meals=list(MEAL_TYPES),
    )
    check(
        [i.food.id for s in all_four.slots for i in s.items]
        == [i.food.id for s in whole.slots for i in s.items],
        "only_meals naming all four builds exactly the day that `None` does",
    )

    # A kept serving of 1.5 portions has to count as 1.5.
    heavy_kept = {
        "breakfast": [
            PlanItem(food=food("heavy", "main", 400), score=0.5, portion=1.5)
        ],
    }
    heavy = builder(foods, exploration_ratio=0.0).build(
        plan_date=DAY,
        target_kcal=2000.0,
        target_protein=100.0,
        target_carb=250.0,
        target_fat=66.7,
        only_meals=["snack"],
        kept=heavy_kept,
    )
    approx(
        [s for s in heavy.slots if s.meal_type == "breakfast"][0].actual_kcal,
        600.0,
        "a kept serving of 1.5 portions counts 1.5 times its energy",
    )

    # And a serving this builder picks is always exactly one portion.
    check(
        all(i.portion == 1.0 for s in whole.slots for i in s.items),
        "every serving Step 4 picks is one standard portion",
    )

    # The arguments that cannot mean anything.
    raises(
        lambda: builder(foods).build(
            plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
            target_carb=250.0, target_fat=66.7, only_meals=[],
        ),
        ValueError,
        "an empty only_meals is refused, not read as 'the whole day'",
    )
    raises(
        lambda: builder(foods).build(
            plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
            target_carb=250.0, target_fat=66.7, only_meals=["brunch"],
        ),
        ValueError,
        "a meal that does not exist is refused",
    )
    raises(
        lambda: builder(foods).build(
            plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
            target_carb=250.0, target_fat=66.7,
            only_meals=["snack"], kept={"snack": []},
        ),
        ValueError,
        "a meal cannot be both rebuilt and kept",
    )

    # The order of `only_meals` must not change the result: phase 1 walks the
    # slots in order and phase 3 updates `used` between meals, so a plan that
    # depended on how the caller typed the list would not be reproducible.
    forwards = builder(foods, exploration_ratio=0.0).build(
        plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
        target_carb=250.0, target_fat=66.7,
        only_meals=["breakfast", "lunch"],
        kept={m: list(kept[m]) for m in ("dinner",)},
    )
    backwards = builder(foods, exploration_ratio=0.0).build(
        plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
        target_carb=250.0, target_fat=66.7,
        only_meals=["lunch", "breakfast"],
        kept={m: list(kept[m]) for m in ("dinner",)},
    )
    check(
        [i.food.id for s in forwards.slots for i in s.items]
        == [i.food.id for s in backwards.slots for i in s.items],
        "the result depends on WHICH meals are rebuilt, not on their order",
    )

    # Phase 5 may only move dishes in the meals being rebuilt. A threshold
    # the kept meals breach on their own is then reported, not repaired —
    # the honest answer, and the one the response has to carry.
    # The kept breakfast alone is 1800 mg of sodium against a 1000 mg day
    # limit, and the only servings phase 5 may touch are in the snack, whose
    # mildest food carries 1 mg. So the breach cannot be repaired from
    # there — which is the case worth checking.
    salty_main_a = food("salty-main-a", "main", 400, sodium=900.0)
    salty_main_b = food("salty-main-b", "main", 400, sodium=900.0)
    mild = [
        food(f"mild-{i}", "snack", 150, sodium=1.0) for i in range(1, 4)
    ]
    limited = builder(
        [salty_main_a, salty_main_b] + mild,
        exploration_ratio=0.0,
        nutrient_targets=[NutrientTarget.at_most("sodium_mg", 1000.0, "HA")],
    ).build(
        plan_date=DAY, target_kcal=2000.0, target_protein=100.0,
        target_carb=250.0, target_fat=66.7,
        only_meals=["snack"],
        kept={
            "breakfast": [
                PlanItem(food=salty_main_a, score=0.5),
                PlanItem(food=salty_main_b, score=0.5),
            ],
        },
    )
    check(
        [t.nutrient for t, _ in limited.nutrient_violations]
        == ["sodium_mg"],
        "a threshold the kept meals breach is REPORTED rather than hidden",
    )
    check(
        limited.meets_nutrient_targets is False,
        "and the plan does not claim its targets are met",
    )


# -- 15. The C# mirror of the meal structure ---------------------------

#: `backend/Api/Planning/MealStructure.cs` keeps the role sets of each meal so
#: that §7.5.1's `mealType` filter can be answered in SQL. The arrays are
#: matched by the same declaration shape `tools/gen_entities.py` matches in
#: `Api.Profile.Enums`, and for the same reason: a copy nothing compares is a
#: copy that drifts.
MEAL_STRUCTURE_CS = ROOT / "backend" / "Api" / "Planning" / "MealStructure.cs"

#: Spelled as a name so the stripping code above holds no escape sequences.
NEWLINE = chr(10)

RE_CS_ARRAY = re.compile(
    r"public static readonly string\[\]\s+(\w+)\s*=\s*\[(.*?)\]\s*;", re.S)


def check_csharp_mirror() -> None:
    print("15. The C# mirror of MEAL_STRUCTURE")

    if not MEAL_STRUCTURE_CS.exists():
        check(False, f"{MEAL_STRUCTURE_CS} does not exist")
        return

    # Documentation lines are stripped first. The class's own XML
    # comment spells out the declaration shape it has to keep —
    # `string[] Name = [ ... ]` — and without this the audit matched that
    # example and reported a meal called `Name`.
    source = MEAL_STRUCTURE_CS.read_text(encoding="utf-8")
    text = NEWLINE.join(
        line for line in source.split(NEWLINE)
        if not line.lstrip().startswith("///")
    )
    on_disk = {
        m.group(1).lower(): re.findall(r'"([^"]*)"', m.group(2))
        for m in RE_CS_ARRAY.finditer(text)
    }

    check(
        set(on_disk) == set(MEAL_TYPES),
        f"MealStructure.cs declares {sorted(on_disk)}, the four meals are "
        f"{sorted(MEAL_TYPES)}",
    )

    for meal in MEAL_TYPES:
        shape = MEAL_STRUCTURE[meal]
        expected = list(shape.required) + list(shape.optional)
        actual = on_disk.get(meal)
        check(
            actual == expected,
            f"MealStructure.{meal.capitalize()} = {actual}, but "
            f"MEAL_STRUCTURE[{meal!r}] required+optional = {expected}",
        )

    # Every role named on the C# side has to be a real `dish_role`, or the
    # SQL filter silently matches nothing.
    named = {role for roles in on_disk.values() for role in roles}
    unknown = sorted(named - set(SCHEMA_ROLES))
    check(
        not unknown,
        f"MealStructure.cs names roles that are not in the dish_role ENUM: "
        f"{unknown}",
    )


def main() -> int:
    use_utf8()
    print("Step 4 checks — the meal-plan builder, no database needed")
    print("=" * 62)
    for section in (
        check_structure,
        check_nutrient_target,
        check_greedy,
        check_plan,
        check_missing_roles,
        check_top_up,
        check_local_search,
        check_repair,
        check_per_meal,
        check_exploration,
        check_plan_row,
        check_alternatives,
        check_ml_scores,
        check_one_meal,
        check_csharp_mirror,
    ):
        section()
    print("=" * 62)
    if _failures:
        print(f"{_passed} checks passed, {len(_failures)} FAILED:")
        for x in _failures:
            print("  -", x)
        return 1
    print(f"All {_passed} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
