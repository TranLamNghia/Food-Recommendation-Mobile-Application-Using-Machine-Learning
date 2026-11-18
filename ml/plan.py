# -*- coding: utf-8 -*-
"""Step 4's database wiring — what `ml/serve.py` is to Step 3.

`ml/menu_builder.py` is pure: foods, a profile and targets in, a plan out.
This file is what reads those out of MySQL and hands the result to
`POST /plan`.

    load_targets      Step 1's numbers, as the backend computed them
    build_daily_plan  Step 3 -> Step 4, for one user and one day

## It consumes Step 3 rather than scoring again

`build_daily_plan` calls `serve.recommend` and feeds its candidates into the
builder. That is deliberate: the alternative is to load the model, build the
feature rows and score them here, which is the fourth place in this
repository that would do the same arithmetic. `tools/check_be_parity.py`
exists because three implementations of Step 1 drifted apart in ways nothing
reported, and `recommend` already returns everything Step 4 needs — the
F1-safe set, the per-food model score, the stage, α and the model version.

## It does NOT write anything

No `meal_plans` row is created here. A table should have one owner for
writes, and `meal_plans` belongs to the backend: it carries the `409
MEAL_PLAN_EXISTS` rule, the ownership check and the authentication that go
with a user's own data. This service writes the `ml_*` tables and reads
everything else.

## Step 1 is read, not recomputed

`health_profiles.daily_calories_target` and the three `target_*_pct` columns
hold Step 1's output, computed by the backend. They are read as they stand.
Recomputing the TDEE here would make a **fourth** implementation of Step 1,
and the plan would then be built against a target the user was never shown.

## Note on language

Identifiers and comments are English. The `code` of a `PlanInputError` is a
stable string the backend branches on — the §4 catalogue — and its `message`
is developer-facing English for the log, not text for a user.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from ml.f1_filter import conditions_for_user, daily_limit_rules, soft_rules
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods
from ml.menu_builder import (
    DailyPlan,
    MenuBuilder,
    NutrientTarget,
    targets_from_limit_rows,
)
from ml.serve import load_preference_profile, recommend

#: Energy per gram, for turning a macro percentage into grams. Protein and
#: carbohydrate 4 kcal/g, fat 9 — the Atwater factors the whole project uses.
KCAL_PER_GRAM = {"protein": 4.0, "carb": 4.0, "fat": 9.0}


class PlanInputError(Exception):
    """Something the user has to supply is missing.

    Carries a `code` from the §4 catalogue so the backend can turn it into
    the right answer: this is never "the ML service is broken", it is "this
    person cannot have a plan yet", and the two must not reach the user as
    the same screen.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PlanTargets:
    """Step 1's output for one user, in the units Step 4 needs."""

    kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    #: The three percentages as stored, for the explanation and for the
    #: `meal_plans` row.
    macro_pct: tuple[float, float, float]


def load_targets(cn, user_id: str) -> PlanTargets:
    """Read Step 1's numbers out of `health_profiles`.

    Raises rather than inventing a default. A plan built against a guessed
    energy target is worse than no plan: it looks exactly like a real one,
    the user follows it, and `calorie_deviation_pct` reports a tidy figure
    against a number nobody computed.
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT daily_calories_target, target_protein_pct, "
            "       target_carbs_pct, target_fat_pct "
            "FROM health_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise PlanInputError(
            "PROFILE_REQUIRED",
            f"User {user_id} has no health_profiles row, so Step 1 has "
            "never run: there is no energy target to build a plan against.",
        )
    if row["daily_calories_target"] is None:
        raise PlanInputError(
            "ONBOARDING_REQUIRED",
            f"User {user_id} has a health profile but "
            "daily_calories_target is NULL — Step 1 has not been computed "
            "for them yet.",
        )

    kcal = float(row["daily_calories_target"])
    protein_pct = float(row["target_protein_pct"])
    carb_pct = float(row["target_carbs_pct"])
    fat_pct = float(row["target_fat_pct"])

    return PlanTargets(
        kcal=kcal,
        protein_g=kcal * protein_pct / 100 / KCAL_PER_GRAM["protein"],
        carb_g=kcal * carb_pct / 100 / KCAL_PER_GRAM["carb"],
        fat_g=kcal * fat_pct / 100 / KCAL_PER_GRAM["fat"],
        macro_pct=(protein_pct, carb_pct, fat_pct),
    )


@dataclass(frozen=True)
class PlanResult:
    """The plan, with everything the backend needs to record beside it."""

    plan: DailyPlan
    targets: PlanTargets
    #: Which scoring stage produced the preference scores, and the α used —
    #: `cold`, `content`, `hybrid` or `ml`.
    stage: str
    alpha: float
    generation_source: str
    model_version: str | None
    feature_version: str
    n_signals: int
    n_foods_before_f1: int
    n_foods_after_f1: int
    warnings: tuple[str, ...]


def build_daily_plan(
    cn,
    user_id: str,
    *,
    plan_date: date,
    exclude_food_ids: Sequence[str] = (),
    exploration_ratio: float = 0.3,
    seed: int | None = None,
) -> PlanResult:
    """Steps 3 and 4 for one user and one day.

    `exclude_food_ids` are the foods not to use — what the user has already
    eaten today, so the plan does not repeat a dish. It comes from the
    backend because the request is the backend's: this service could read
    `food_diary` itself, and `ml/daily_limits.py` does, but then two callers
    would disagree about what "today" means for a user in another time zone.

    `seed` makes the exploration group reproducible. `None` is a fresh plan
    each time, which is what a user wants; a fixed seed is for the checkers,
    which cannot compare a plan that changes on every run.
    """
    targets = load_targets(cn, user_id)

    # Step 3, over the whole F1-safe catalogue. `limit=None` so nothing is
    # truncated: Step 4 has to see every food it is allowed to choose from,
    # and `recommend`'s default of 20 would quietly hand it a shortlist.
    scored = recommend(
        cn,
        user_id,
        limit=None,
        exclude_foods=exclude_food_ids,
    )

    foods, _ = load_foods(cn)
    space = FeatureSpace.from_foods(foods)
    profile, profile_warning = load_preference_profile(cn, user_id, space)

    conditions = conditions_for_user(cn, user_id)
    # The hard per-day thresholds are what phase 5 repairs against. Soft
    # per-day rules are `ml/daily_limits.py`'s business, not Step 4's.
    day_targets: list[NutrientTarget] = targets_from_limit_rows(
        daily_limit_rules(cn, conditions, hard_only=True)
    )
    # The per-meal soft rules — the scope that had no enforcing layer until
    # Step 4 existed. `MenuBuilder` filters by scope again, so a wrong one
    # cannot slip through, but filtering here keeps the intent visible.
    per_meal = [r for r in soft_rules(cn, conditions) if r.scope == "per_meal"]

    builder = MenuBuilder(
        candidates=[c.food for c in scored.candidates],
        space=space,
        profile=profile,
        exploration_ratio=exploration_ratio,
        nutrient_targets=day_targets,
        per_meal_rules=per_meal,
        ml_scores={
            c.food.id: c.ml_score
            for c in scored.candidates
            if c.ml_score is not None
        },
        rng=random.Random(seed) if seed is not None else random.Random(),
    )
    plan = builder.build(
        plan_date=plan_date,
        target_kcal=targets.kcal,
        target_protein=targets.protein_g,
        target_carb=targets.carb_g,
        target_fat=targets.fat_g,
    )

    warnings = list(scored.warnings) + list(plan.warnings)
    if profile_warning:
        warnings.append(profile_warning)
    pct_sum = sum(targets.macro_pct)
    if abs(pct_sum - 100.0) > 0.5:
        # Not fatal: the grams are still computed from the stored
        # percentages, which is what the user was shown. Reported because
        # the three columns are meant to sum to 100, and a plan built
        # against 90 % of an energy target will look mysteriously light.
        warnings.append(
            f"health_profiles target_*_pct sums to {pct_sum:g}, not 100, for "
            f"user {user_id}: the macro targets are off by that much."
        )

    return PlanResult(
        plan=plan,
        targets=targets,
        stage=scored.stage,
        alpha=round(scored.alpha, 3),
        generation_source=scored.generation_source,
        model_version=scored.model_version,
        feature_version=FEATURE_VERSION,
        n_signals=profile.n_signals,
        n_foods_before_f1=scored.n_foods_before_f1,
        n_foods_after_f1=scored.n_foods_after_f1,
        warnings=tuple(warnings),
    )
