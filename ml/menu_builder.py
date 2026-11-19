# -*- coding: utf-8 -*-
"""Step 4 — assembling one day's meal plan.

Before this file, Step 4 existed in exactly one place: `menu_builder.dart`,
675 lines of Dart running on `MockFoods`. That left the server unable to
produce a meal plan at all — `ml/serve.py` scores foods (Step 3) and stops.
Since the backend delegates Steps 3 and 4 to this service, the plan has to be
assembled here.

    phase 1   greedy over the required servings, by score density
    phase 2   top up with optional servings, at the DAY level
    phase 3   local search inside each meal, on a penalised objective
    phase 4   top up again, because phase 3 optimises meals separately
    phase 5   repair the day-level nutrient constraints, by swapping

This module is **pure**: foods, a profile and targets in, a plan out. No
database, no HTTP. `ml/api.py` does the wiring and `tools/check_step4.py`
tests the phases on hand-built input, the same division as
`tools/check_ml.py`.

## Note on the dish-role vocabulary

`MEAL_STRUCTURE` below is keyed on the values of the `foods.dish_role` column
— `main`, `side_protein`, `side_veg`, `soup`, `dessert`, `drink`, `snack`, as
`db/schema.sql` declares them.

The Dart implementation uses **different strings** for the same thing:
`'Món chính'`, `'Món mặn'`, `'Món rau'`, `'Món canh'`, `'Món phụ'`. Its
`Food.dishRole` is documented as "the `foods.dish_role` column", but
`MockFoods` fills it with those Vietnamese labels, so the two agree with each
other and with nothing else. Pointed at the real catalogue, the Dart meal
structure matches no food at all and builds an empty plan.

This file follows the schema, because the schema is what the data has.
`ROLE_FROM_DART` records the mapping so `tools/check_step4_parity.py` can
compare the two implementations, and so that whoever moves the Flutter app
off its mocks has the translation written down rather than guessed.

## A limitation this port inherits

The meal structure uses five of the seven roles. `dessert` and `drink` appear
in no meal, so 46 of the 318 active foods can never be selected. That comes
straight from the Dart structure and is kept rather than silently extended —
adding a dessert serving to every day is a product decision, not a port. The
plan reports it in `DailyPlan.warnings` instead of leaving it to be
discovered.

## Note on language

Identifiers and comments are English. The dish-role strings, the condition
names inside a `SoftRule` and the nutrient column names are **data** — they
are what the database holds — so they stay as they are.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Mapping, Sequence

from ml.features import FeatureSpace, Food
from ml.f1_filter import SoftRule
from ml.rocchio import PreferenceProfile
from ml.scoring import blend, meal_penalty

# ── The shape of a day ────────────────────────────────────────────────

#: The four meals, in the order a day runs. Also the iteration order of every
#: loop below, so a plan is reproducible.
MEAL_TYPES: tuple[str, ...] = ("breakfast", "lunch", "dinner", "snack")

#: Each meal's share of the day's energy — the midpoint of the National
#: Institute of Nutrition's ranges (breakfast 25-30 %, lunch 35-40 %, dinner
#: 25-30 %, snack 5-10 %). The four add up to exactly 1, and
#: `tools/check_step4.py` asserts that.
MEAL_ENERGY_SHARE: dict[str, float] = {
    "breakfast": 0.275,
    "lunch": 0.375,
    "dinner": 0.275,
    "snack": 0.075,
}


@dataclass(frozen=True)
class MealShape:
    """The dish roles a meal must have, and the ones it may add.

    `required` exists because taking the top-scoring foods does **not** make
    a meal: all of them could be soups, or all desserts for someone with a
    sweet tooth. The roles force the shape before taste is considered.

    `optional` exists because one dish cannot cover a meal's allowance.
    Breakfast for someone needing 2 500 kcal is 27.5 %, about 690 kcal, while
    the heaviest dish in the catalogue is just over 600. Without optional
    servings the plan always falls short, however well the picking works.
    """

    required: tuple[str, ...]
    optional: tuple[str, ...] = ()


#: Ported from `menu_builder.dart:31`, translated into the schema's role
#: codes. See the note on vocabulary at the top of this file.
MEAL_STRUCTURE: dict[str, MealShape] = {
    "breakfast": MealShape(required=("main",), optional=("snack",)),
    "lunch": MealShape(required=("main", "side_protein"), optional=("soup",)),
    "dinner": MealShape(required=("main", "side_veg"), optional=("side_protein",)),
    "snack": MealShape(required=("snack",)),
}

#: Dart label -> schema code. Used by the parity checker, and by whoever
#: moves the app off `MockFoods`.
#:
#: `'Món phụ'` -> `snack` is the one judgement call: the Dart structure uses
#: it both as breakfast's optional serving and as the snack meal's required
#: one, which is what `snack` is for in the schema. The other four are
#: direct.
ROLE_FROM_DART: dict[str, str] = {
    "Món chính": "main",
    "Món mặn": "side_protein",
    "Món rau": "side_veg",
    "Món canh": "soup",
    "Món phụ": "snack",
}

#: Roles the meal structure never asks for. Reported, not corrected — see the
#: limitation noted at the top.
UNUSED_ROLES: tuple[str, ...] = ("dessert", "drink")


# ── Day-level nutrient constraints ────────────────────────────────────


@dataclass(frozen=True)
class NutrientTarget:
    """One nutrient constraint at the **day** level.

    Every medical guideline is stated per day, not per dish, and
    `condition_rules` follows that with `scope = 'per_day'`. Both directions
    are needed: sodium <= 2000 mg/day (WHO) is a ceiling, fibre >= 25 g/day
    (WHO 2023) is a floor.

    The constraint **repairs a built plan**; it does not filter foods out of
    the input. Hard-filtering on a numeric threshold wipes out whole roles —
    `fiber >= 2 g` leaves `side_protein` with nothing, because meat and fish
    have no fibre — and then no meal can be built. Hard filtering is for
    allergens and tags.
    """

    nutrient: str
    amount: float
    #: True is a floor (`gte`), False a ceiling (`lte`).
    is_floor: bool
    #: Which condition asked for it, for the explanation. Empty when the
    #: target is the user's own stated goal rather than a medical rule.
    condition: str = ""

    @classmethod
    def at_least(cls, nutrient: str, amount: float, condition: str = "") -> "NutrientTarget":
        return cls(nutrient, amount, True, condition)

    @classmethod
    def at_most(cls, nutrient: str, amount: float, condition: str = "") -> "NutrientTarget":
        return cls(nutrient, amount, False, condition)

    def violation(self, actual: float) -> float:
        """How far off, as a **fraction** of the threshold. 0 when satisfied.

        A fraction rather than an absolute amount, because phase 5 has to
        compare nutrients measured in different units: 5 g short of fibre and
        5 mg over on sodium are not the same size of problem.
        """
        if self.amount <= 0:
            return 0.0
        short = self.amount - actual if self.is_floor else actual - self.amount
        return 0.0 if short <= 0 else short / self.amount

    def is_satisfied_by(self, actual: float) -> bool:
        return self.violation(actual) == 0.0

    def __str__(self) -> str:
        return f"{self.nutrient} {'>=' if self.is_floor else '<='} {self.amount}"


#: The nutrients Step 4 can enforce at the day level, keyed to `Food`.
#:
#: **`purine_mg` is deliberately absent.** The hard rule for gout is purine
#: <= 400 mg/day, but the composition table publishes purine for only 70 of
#: 318 foods. Summing the missing ones as 0 would make the ceiling almost
#: unreachable — a safety layer failing OPEN with nothing in the logs. Gout
#: is protected by the `exclude_tag 'Giàu purin'` rule at Step 2 instead, and
#: `DailyPlan.unenforceable_targets` keeps the unchecked ones visible rather
#: than reporting them as met.
NUTRIENT_OF_FOOD: dict[str, str] = {
    "calories_kcal": "kcal",
    "protein_g": "protein",
    "carbs_g": "carb",
    "fat_g": "fat",
    "sugar_g": "sugar",
    "sodium_mg": "sodium",
    "fiber_g": "fiber",
}

SUPPORTED_NUTRIENTS: frozenset[str] = frozenset(NUTRIENT_OF_FOOD)


def value_of(food: Food, nutrient: str) -> float | None:
    """One nutrient of one food, or `None` when `Food` does not carry it.

    `None`, never 0 — the difference between "this food has no fibre" and
    "nobody measured the fibre" is the difference between a plan that is safe
    and a plan that looks safe.
    """
    attribute = NUTRIENT_OF_FOOD.get(nutrient)
    if attribute is None:
        return None
    return float(getattr(food, attribute))


def targets_from_limit_rows(rows: Iterable[Mapping[str, object]]) -> list[NutrientTarget]:
    """Convert `f1_filter.daily_limit_rules` rows into targets.

    Only `lte` and `gte` are produced, because those are the two comparators
    `condition_rules.comparator` holds. An unknown comparator raises rather
    than being dropped: a threshold silently discarded is a threshold
    enforced nowhere, which is the bug this whole phase exists to fix.
    """
    targets: list[NutrientTarget] = []
    for row in rows:
        comparator = str(row["comparator"])
        nutrient = str(row["nutrient"])
        amount = float(row["threshold"])  # type: ignore[arg-type]
        condition = str(row.get("name_vi", "") or "")
        if comparator == "lte":
            targets.append(NutrientTarget.at_most(nutrient, amount, condition))
        elif comparator == "gte":
            targets.append(NutrientTarget.at_least(nutrient, amount, condition))
        else:
            raise ValueError(
                f"Unknown comparator {comparator!r} for {nutrient} "
                f"({condition}). condition_rules.comparator holds 'lte' or "
                "'gte'; a threshold that is neither cannot be enforced, and "
                "dropping it silently would leave it enforced nowhere."
            )
    return targets


# ── The plan ──────────────────────────────────────────────────────────


@dataclass
class PlanItem:
    """One serving of the plan — a `meal_plan_items` row, before it is
    written."""

    food: Food
    #: The preference score the food was chosen on, in [0, 1]. Goes to
    #: `meal_plan_items.predicted_score`.
    score: float
    #: The noise amplitude used if this is an **exploration** serving;
    #: `None` is an exploitation serving. `meal_plan_items.exploration_delta`
    #: holds exactly this, which is why no `is_exploration` column is needed.
    exploration_delta: float | None = None
    #: Servings on the plate — `meal_plan_items.portion_multiplier`.
    #:
    #: Always 1.0 for a serving this builder picks: Step 4 chooses dishes,
    #: not portions, and every nutrition figure in `Food` is per serving.
    #: Another value arrives only with a **kept** serving, because §7.6.5
    #: lets a user replace a dish and ask for a different weight. The day's
    #: energy then has to count what is served rather than one serving of
    #: it.
    portion: float = 1.0

    @property
    def is_exploration(self) -> bool:
        return self.exploration_delta is not None

    @property
    def kcal(self) -> float:
        return float(self.food.kcal) * self.portion

    @property
    def protein(self) -> float:
        return self.food.protein * self.portion

    @property
    def carb(self) -> float:
        return self.food.carb * self.portion

    @property
    def fat(self) -> float:
        return self.food.fat * self.portion

    def amount_of(self, nutrient: str) -> float | None:
        """This serving's amount of `nutrient`, or `None` when unmeasured.

        `None` stays `None` rather than becoming 0: a food with no sodium
        figure is not a food with no sodium, and the callers that sum
        nutrients decide for themselves what to do with the gap.
        """
        value = value_of(self.food, nutrient)
        return None if value is None else value * self.portion


@dataclass
class MealSlotResult:
    """One meal of the plan, with that meal's own energy target."""

    meal_type: str
    target_kcal: float
    items: list[PlanItem] = field(default_factory=list)

    @property
    def actual_kcal(self) -> float:
        return sum(i.kcal for i in self.items)

    @property
    def protein(self) -> float:
        return sum(i.protein for i in self.items)

    @property
    def carb(self) -> float:
        return sum(i.carb for i in self.items)

    @property
    def fat(self) -> float:
        return sum(i.fat for i in self.items)

    @property
    def deviation_pct(self) -> float:
        if self.target_kcal <= 0:
            return 0.0
        return (self.actual_kcal - self.target_kcal) / self.target_kcal * 100


@dataclass
class DailyPlan:
    """One day's plan — a `meal_plans` row with its `meal_plan_items`."""

    plan_date: date
    target_kcal: float
    target_protein: float
    target_carb: float
    target_fat: float
    slots: list[MealSlotResult]
    #: The **intended** exploration share, capped at 0.5 by `chk_expl_ratio`:
    #: more than half the plan being a trial dish is no longer a personalised
    #: recommendation.
    exploration_ratio: float
    nutrient_targets: tuple[NutrientTarget, ...] = ()
    #: Developer-facing English, for the log and for `/predict`-style
    #: warnings. Never shown to a user as it stands.
    warnings: tuple[str, ...] = ()

    @property
    def items(self) -> list[PlanItem]:
        return [i for s in self.slots for i in s.items]

    @property
    def actual_kcal(self) -> float:
        return sum(s.actual_kcal for s in self.slots)

    @property
    def actual_protein(self) -> float:
        return sum(s.protein for s in self.slots)

    @property
    def actual_carb(self) -> float:
        return sum(s.carb for s in self.slots)

    @property
    def actual_fat(self) -> float:
        return sum(s.fat for s in self.slots)

    @property
    def deviation_pct(self) -> float:
        """What `meal_plans.calorie_deviation_pct` computes. The proposal
        commits to keeping it within 10 %, so it has to be quotable."""
        if self.target_kcal <= 0:
            return 0.0
        return (self.actual_kcal - self.target_kcal) / self.target_kcal * 100

    @property
    def within_tolerance(self) -> bool:
        return abs(self.deviation_pct) <= 10.0

    @property
    def total_preference_score(self) -> float:
        return sum(i.score for i in self.items)

    def total_of(self, nutrient: str) -> float:
        return sum(i.amount_of(nutrient) or 0.0 for i in self.items)

    @property
    def nutrient_violations(self) -> list[tuple[NutrientTarget, float]]:
        """The constraints **not** satisfied, with the actual amount.

        Empty is good. Non-empty means phase 5 ran out of usable swaps —
        usually because the catalogue holds no food that would close the gap.
        It has to be shown rather than hidden: a plan that breaches a limit
        while looking perfectly ordinary is the worst kind of failure for
        someone with a condition.
        """
        out: list[tuple[NutrientTarget, float]] = []
        for target in self.nutrient_targets:
            if target.nutrient not in SUPPORTED_NUTRIENTS:
                continue
            actual = self.total_of(target.nutrient)
            if not target.is_satisfied_by(actual):
                out.append((target, actual))
        return out

    @property
    def unenforceable_targets(self) -> list[NutrientTarget]:
        """Constraints on a nutrient `Food` does not carry — today only
        `purine_mg`.

        Kept apart from `nutrient_violations` on purpose. Folded in,
        `at_most('purine_mg', 400)` would report **satisfied**, because the
        total reads 0: a plan whose purine was never checked would appear to
        meet a gout limit. That is worse than reporting a violation.
        """
        return [
            t for t in self.nutrient_targets
            if t.nutrient not in SUPPORTED_NUTRIENTS
        ]

    @property
    def meets_nutrient_targets(self) -> bool:
        """Every enforceable constraint satisfied **and** nothing left
        unenforceable. The second half is deliberately strict: never claim
        "met" for something that could not be checked."""
        return not self.nutrient_violations and not self.unenforceable_targets

    @property
    def actual_exploration_ratio(self) -> float:
        items = self.items
        if not items:
            return 0.0
        return sum(1 for i in items if i.is_exploration) / len(items)


# ── The builder ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Slot:
    """One serving to fill: which meal, which role, exploration or not."""

    meal: str
    role: str
    explore: bool


class MenuBuilder:
    """Assembles one day's plan from an F1-safe food set and a profile.

    **The F1 filter sits outside this class** and has to have run already:
    `candidates` is an already-safe set. Exploration loosens taste, never
    safety.
    """

    def __init__(
        self,
        *,
        candidates: Sequence[Food],
        space: FeatureSpace,
        profile: PreferenceProfile,
        exploration_ratio: float = 0.3,
        exploration_delta: float = 0.35,
        energy_penalty: float = 1.2,
        macro_penalty: float = 0.6,
        local_search_rounds: int = 20,
        nutrient_targets: Sequence[NutrientTarget] = (),
        nutrient_repair_rounds: int = 12,
        max_energy_deviation: float = 0.10,
        per_meal_rules: Sequence[SoftRule] = (),
        ml_scores: Mapping[str, float] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.candidates = list(candidates)
        self.space = space
        self.profile = profile
        self.exploration_ratio = exploration_ratio
        self.exploration_delta = exploration_delta
        #: λ, the coefficient on the energy deviation in the objective.
        self.energy_penalty = energy_penalty
        #: μ, the coefficient on each macronutrient's deviation.
        self.macro_penalty = macro_penalty
        self.local_search_rounds = local_search_rounds
        self.nutrient_targets = list(nutrient_targets)
        #: An upper bound on phase 5's swaps, so the repair stops when the
        #: catalogue holds nothing that would satisfy the constraint.
        self.nutrient_repair_rounds = nutrient_repair_rounds
        #: The ceiling phase 5 may push the energy deviation to. 10 % is the
        #: proposal's commitment, and phase 5 never trades past it: curing
        #: one violation by creating another is not a repair.
        self.max_energy_deviation = max_energy_deviation
        #: The **soft** `per_meal` rules. Until this file existed, nothing
        #: enforced them — see `enforce_per_meal` below.
        self.per_meal_rules = [r for r in per_meal_rules if r.scope == "per_meal"]
        #: Stage 2 model scores by food id, from Step 3. See `_score`.
        self.ml_scores = dict(ml_scores) if ml_scores else {}
        self.rng = rng or random.Random()

    # -- the scoring helpers ------------------------------------------

    def _score(self, profile: PreferenceProfile, food: Food) -> float:
        """What Step 4 ranks a food by, in [0, 1].

        Without `ml_scores` this is the cosine score alone, which is what the
        Dart implementation computes and what the parity checker compares.

        With them it is the **blend** — `α·ML + (1−α)·cosine`, α from the
        signal count, the same formula Step 3 uses. That matters more than it
        looks: Step 4 is what decides the plan, so a Step 4 that ranks by
        cosine alone leaves the trained model with no influence on anything
        the user sees. The model would still be trained, still be evaluated,
        still report its AUC — and change nothing. The Dart side ranks by
        cosine because the app has no model to consult, not because the
        model should be ignored.

        The blend is recomputed here rather than taking Step 3's final score
        whole, because the exploration group needs the cosine half against a
        **rotated** vector while the model half stays as it is: the jitter
        explores taste, and the model's opinion of a food does not change
        because the user's vector was nudged.
        """
        content = profile.score(self.space, food)
        ml = self.ml_scores.get(food.id)
        if ml is None:
            return content
        return blend(ml, content, profile.n_signals)

    def _jittered(self, profile: PreferenceProfile) -> PreferenceProfile:
        """`p_u' = p_u + δ·n/‖n‖`, the exploration profile.

        The noise is Gaussian per dimension and then normalised to a unit
        vector, so the rotation points evenly in every direction. Drawn
        uniformly per dimension it would lean towards the corners of the
        cube, and "exploration" would mean the same handful of foods for
        everyone.
        """
        if profile.is_empty:
            return profile
        noise = [self.rng.gauss(0.0, 1.0) for _ in profile.weights]
        norm = math.sqrt(sum(n * n for n in noise))
        if norm == 0:
            return profile
        rotated = tuple(
            w + self.exploration_delta * n / norm
            for w, n in zip(profile.weights, noise)
        )
        return PreferenceProfile(
            weights=rotated,
            sum_abs_weight=profile.sum_abs_weight,
            n_signals=profile.n_signals,
        )

    # -- the entry point ----------------------------------------------

    def build(
        self,
        *,
        plan_date: date,
        target_kcal: float,
        target_protein: float,
        target_carb: float,
        target_fat: float,
        only_meals: Sequence[str] | None = None,
        kept: Mapping[str, Sequence[PlanItem]] | None = None,
    ) -> DailyPlan:
        """The five phases, in order.

        `target_kcal` is the whole day's energy target from Step 1 — the TDEE
        adjusted for the goal. Each meal's share follows from
        `MEAL_ENERGY_SHARE`.

        ## Rebuilding one meal of a day

        `only_meals` names the meals to assemble; `kept` carries the servings
        of the meals that stay. Omit both and the whole day is built, which
        is the path `tools/check_step4_parity.py` compares against the Dart
        implementation.

        **The day stays the unit of measurement.** The kept servings are in
        `picks` from the start, so they count towards the day's energy, every
        `per_day` nutrient total, `deviation_pct` and `used` — the same
        numbers the full-day build produces. What changes is only which
        servings the five phases are allowed to touch. Assembling one meal
        against one meal's share instead would make `deviation_pct` a
        deviation from 37.5 % of a target, recorded in the column that
        reports the day's.

        Two things follow from that, and both are intended:

        * phase 5 may only swap dishes inside `only_meals`, so a day-level
          threshold the kept meals breach on their own cannot be repaired —
          it is reported instead, which is the honest answer;
        * exploration is counted over the servings being built, so
          regenerating a one-dish meal draws no exploration serving at all
          (`round(1 * 0.3) == 0`). The 70-30 share is a property of a plan,
          not of a single serving.
        """
        mutable = self._mutable_meals(only_meals)
        fixed = self._fixed_items(kept, mutable)

        ratio = min(max(self.exploration_ratio, 0.0), 0.5)
        explore_profile = self._jittered(self.profile)

        slots = self._assign_exploration_slots(ratio, mutable)
        picks: dict[str, list[PlanItem]] = {
            m: list(fixed.get(m, ())) for m in MEAL_TYPES
        }
        # The kept dishes are in `used` before phase 1 runs, so a meal being
        # rebuilt cannot pick a food that is already on the plate in another
        # meal. Without this the same dish appears twice in one day — the
        # exact bug the `usedIds` bookkeeping of phase 3 exists to prevent.
        used: set[str] = {
            i.food.id for items in picks.values() for i in items
        }
        warnings: list[str] = list(self._input_warnings())

        # ── Phase 1 — greedy over the required servings ──
        for slot in slots:
            active = explore_profile if slot.explore else self.profile
            pool = [
                f for f in self.candidates
                if f.dish_role == slot.role and f.id not in used
            ]
            # No food left in the right role: skip the serving rather than
            # force in the wrong role. A lunch without its soup is more
            # sensible than a lunch with two main dishes.
            if not pool:
                continue

            meal_target = target_kcal * MEAL_ENERGY_SHARE[slot.meal]
            already = sum(i.kcal for i in picks[slot.meal])
            # Ported as it stands from `menu_builder.dart:158`: this counts
            # ALL the servings of the meal, not the ones still to fill, so
            # the per-slot target shrinks less than the remaining allowance
            # would suggest. Phases 2 to 4 correct the resulting shortfall at
            # the day level. Kept identical on purpose — the parity checker
            # compares the two implementations, and "fixing" it here alone
            # would move every Chapter 3 number with nothing to compare
            # against.
            remaining_slots = max(1, min(99, sum(1 for s in slots if s.meal == slot.meal)))

            best = self._greedy_pick(
                pool=pool,
                profile=active,
                slot_target_kcal=(meal_target - already) / remaining_slots,
            )
            used.add(best.id)
            picks[slot.meal].append(
                PlanItem(
                    food=best,
                    score=self._score(active, best),
                    exploration_delta=self.exploration_delta if slot.explore else None,
                )
            )

        # ── Phase 2 — top up with optional servings, at the day level ──
        self._top_up(
            picks=picks, used=used, target_kcal=target_kcal, meals=mutable
        )

        # ── Phase 3 — local search inside each meal ──
        for meal in mutable:
            before = {i.food.id for i in picks[meal]}
            share = MEAL_ENERGY_SHARE[meal]
            refined = self._local_search(
                meal=meal,
                selected=picks[meal],
                used=used,
                target_kcal=target_kcal * share,
                target_protein=target_protein * share,
                target_carb=target_carb * share,
                target_fat=target_fat * share,
            )
            # Update `used` from the swap result before the next meal.
            # Without this, a food just swapped INTO breakfast is not in
            # `used`, so lunch still sees it as free and takes it too — the
            # same dish twice in one day. A food swapped OUT has to go back
            # to the candidate set, because it is no longer in the plan.
            after = {i.food.id for i in refined}
            used -= before - after
            used |= after
            picks[meal] = refined

        # ── Phase 4 — top up again at the day level ──
        #
        # Phase 3 optimises each meal separately, so it can pull the day's
        # energy away from the target while every single meal improves:
        # swapping a lighter main into lunch fits that meal's macros better
        # and leaves the day shorter still. `_top_up` only adds a food when
        # it makes the day-level gap smaller, so another pass can never make
        # things worse.
        self._top_up(
            picks=picks, used=used, target_kcal=target_kcal, meals=mutable
        )

        # ── Phase 5 — the day-level nutrient constraints ──
        #
        # Last, and at the day level, because "sodium under 2000 mg/day" is a
        # statement about the whole day's total: it cannot be checked in
        # phase 1, which picks one serving at a time, nor in phase 3, which
        # optimises one meal at a time.
        self._repair_nutrients(
            picks=picks, used=used, target_kcal=target_kcal, meals=mutable
        )

        slots_out = [
            MealSlotResult(
                meal_type=meal,
                target_kcal=target_kcal * MEAL_ENERGY_SHARE[meal],
                items=picks[meal],
            )
            for meal in MEAL_TYPES
        ]
        plan = DailyPlan(
            plan_date=plan_date,
            target_kcal=target_kcal,
            target_protein=target_protein,
            target_carb=target_carb,
            target_fat=target_fat,
            slots=slots_out,
            exploration_ratio=ratio,
            nutrient_targets=tuple(self.nutrient_targets),
            warnings=tuple(warnings + self._result_warnings(slots_out)),
        )
        return plan

    # -- which meals this build may touch ------------------------------

    def _mutable_meals(
        self, only_meals: Sequence[str] | None
    ) -> tuple[str, ...]:
        """The meals to assemble, in `MEAL_TYPES` order.

        The order is not cosmetic: phase 1 walks the slots in it and phase 3
        updates `used` between meals, so two runs over the same set in a
        different order can pick different dishes. Taking the order from
        `MEAL_TYPES` rather than from the caller's list makes the result
        depend on the SET of meals, never on how they were typed.
        """
        if only_meals is None:
            return MEAL_TYPES

        wanted = set(only_meals)
        unknown = sorted(wanted - set(MEAL_TYPES))
        if unknown:
            raise ValueError(
                f"not a meal of this plan: {unknown}. "
                f"MEAL_TYPES is {list(MEAL_TYPES)}."
            )
        if not wanted:
            raise ValueError(
                "only_meals is empty: there would be nothing to build. Pass "
                "None to build the whole day."
            )
        return tuple(m for m in MEAL_TYPES if m in wanted)

    def _fixed_items(
        self,
        kept: Mapping[str, Sequence[PlanItem]] | None,
        mutable: tuple[str, ...],
    ) -> dict[str, list[PlanItem]]:
        """The servings that stay, validated.

        Refuses a `kept` entry for a meal that is also being rebuilt, rather
        than silently preferring one of the two. That combination is a caller
        bug with two plausible readings — "keep these and add more" or
        "replace these" — and guessing either would show up only as a meal
        with the wrong number of dishes.
        """
        if not kept:
            return {}

        unknown = sorted(set(kept) - set(MEAL_TYPES))
        if unknown:
            raise ValueError(f"not a meal of this plan: {unknown}")

        clash = sorted(set(kept) & set(mutable))
        if clash:
            raise ValueError(
                f"{clash} appear in both only_meals and kept: a meal is "
                "either rebuilt or kept, not both."
            )

        # A kept serving in one of `UNUSED_ROLES` is passed through rather
        # than refused: the row exists in `meal_plan_items`, so a plan
        # containing it has to remain readable, and it still counts towards
        # the day's energy. `MEAL_STRUCTURE` simply has no slot that could
        # have produced it, which is a product question, not a bad input.
        return {meal: list(items) for meal, items in kept.items()}

    # -- warnings ------------------------------------------------------

    def _input_warnings(self) -> list[str]:
        out: list[str] = []
        roles = {f.dish_role for f in self.candidates}
        unreachable = sorted(r for r in UNUSED_ROLES if r in roles)
        if unreachable:
            n = sum(1 for f in self.candidates if f.dish_role in unreachable)
            out.append(
                f"{n} candidate foods have a role no meal asks for "
                f"({', '.join(unreachable)}), so they can never be selected. "
                "MEAL_STRUCTURE covers five of the seven roles — see the note "
                "in ml/menu_builder.py."
            )
        for meal in MEAL_TYPES:
            for role in MEAL_STRUCTURE[meal].required:
                if role not in roles:
                    out.append(
                        f"No candidate food has role {role!r}, required by "
                        f"{meal}: that serving will be missing from the plan."
                    )
        return out

    def _result_warnings(self, slots: Sequence[MealSlotResult]) -> list[str]:
        """What the finished plan is missing.

        Compares the required ROLES present, not the number of servings. An
        earlier version counted servings, and an optional serving added by
        phase 2 then filled the hole in the count: a lunch with its main dish
        and a soup reported 2 of 2 required servings while its
        `side_protein` was never placed. The count matched and the meal was
        still wrong.
        """
        out: list[str] = []
        for slot in slots:
            present = {i.food.dish_role for i in slot.items}
            missing = [
                role for role in MEAL_STRUCTURE[slot.meal_type].required
                if role not in present
            ]
            if missing:
                out.append(
                    f"{slot.meal_type} is missing {len(missing)} of its "
                    f"{len(MEAL_STRUCTURE[slot.meal_type].required)} required "
                    f"servings ({', '.join(missing)})."
                )
        return out

    # -- phase helpers -------------------------------------------------

    def _assign_exploration_slots(
        self, ratio: float, meals: Sequence[str] = MEAL_TYPES
    ) -> list[Slot]:
        """Which servings are exploration, counted over the **whole plan**.

        The 70-30 split is a property of the plan, which is why
        `exploration_ratio` sits on the `meal_plans` table and not on each
        item. Split per meal and rounded down, a one-dish meal would always
        get 0 exploration servings and so would a three-dish one, and the
        mechanism would never run at all.

        Exploration servings go preferentially to the meals with more dishes,
        so no single meal becomes nothing but trial food.
        """
        base = [
            (meal, role)
            for meal in meals
            for role in MEAL_STRUCTURE[meal].required
        ]
        budget = round(len(base) * ratio)
        if budget == 0:
            return [Slot(meal, role, False) for meal, role in base]

        # Shuffle first, then sort by the meal's dish count descending, so
        # meals of equal size do not always come out in the same order.
        # `sorted` is stable, so the shuffle survives inside a size group.
        order = list(range(len(base)))
        self.rng.shuffle(order)
        order.sort(key=lambda i: -len(MEAL_STRUCTURE[base[i][0]].required))

        explore = set(order[:budget])
        return [
            Slot(meal, role, i in explore)
            for i, (meal, role) in enumerate(base)
        ]

    def _greedy_pick(
        self,
        *,
        pool: Sequence[Food],
        profile: PreferenceProfile,
        slot_target_kcal: float,
    ) -> Food:
        """Greedy by **score density**.

        `score / kcal` rather than `score` alone, the classic knapsack move:
        prefer the food that delivers the most preference per unit of energy
        spent. By score alone a 650 kcal food at 0.9 always beats a 300 kcal
        one at 0.8, and the meal spends its whole allowance on one dish.

        The density is then weighted by how well the food fits the serving's
        target; without that the lightest food always wins, because it has
        the smallest denominator.
        """
        best: Food | None = None
        best_value = -math.inf
        for food in pool:
            kcal = float(food.kcal)
            if kcal <= 0:
                continue
            density = self._score(profile, food) / kcal
            if slot_target_kcal <= 0:
                fit = 1.0
            else:
                fit = 1 - min(1.0, max(0.0, abs(kcal - slot_target_kcal) / slot_target_kcal))
            value = density * (0.35 + 0.65 * fit)
            if value > best_value:
                best_value = value
                best = food
        return best if best is not None else pool[0]

    def _top_up(
        self,
        *,
        picks: dict[str, list[PlanItem]],
        used: set[str],
        target_kcal: float,
        meals: Sequence[str] = MEAL_TYPES,
    ) -> None:
        """Add optional servings one at a time, while each one brings the
        day's energy closer to the target.

        At the day level, not per meal, because the proposal's commitment is
        about the **plan's** deviation. One meal being light can be made up
        by another, and that is the right behaviour: people do eat a small
        breakfast and a big lunch.

        `meals` restricts where a serving may be ADDED; the energy it is
        judged against is still the whole day's, kept meals included.
        """
        while True:
            current = sum(
                i.kcal for items in picks.values() for i in items
            )
            best_gap = abs(current - target_kcal)
            best_meal: str | None = None
            best_food: Food | None = None

            for meal in meals:
                for role in MEAL_STRUCTURE[meal].optional:
                    # Never two servings of the same role in one meal.
                    if any(i.food.dish_role == role for i in picks[meal]):
                        continue
                    for food in self.candidates:
                        if food.dish_role != role or food.id in used:
                            continue
                        gap = abs(current + float(food.kcal) - target_kcal)
                        if gap < best_gap:
                            best_gap = gap
                            best_meal = meal
                            best_food = food

            if best_meal is None or best_food is None:
                return
            used.add(best_food.id)
            picks[best_meal].append(
                PlanItem(food=best_food, score=self._score(self.profile, best_food))
            )

    def _local_search(
        self,
        *,
        meal: str,
        selected: Sequence[PlanItem],
        used: set[str],
        target_kcal: float,
        target_protein: float,
        target_carb: float,
        target_fat: float,
    ) -> list[PlanItem]:
        """Swap one serving at a time, keeping whatever raises the objective.

        The greedy phase sees one serving at a time, so a meal's total can
        miss its target even when every serving is sensible on its own.
        """
        current = list(selected)
        current_score = self._objective(
            current,
            meal=meal,
            target_kcal=target_kcal,
            target_protein=target_protein,
            target_carb=target_carb,
            target_fat=target_fat,
        )

        for _ in range(self.local_search_rounds):
            improved = False
            for i in range(len(current)):
                item = current[i]
                in_plan = {e.food.id for e in current}
                for swap in self.candidates:
                    if swap.dish_role != item.food.dish_role:
                        continue
                    if swap.id in in_plan or swap.id in used:
                        continue
                    trial = list(current)
                    trial[i] = PlanItem(
                        food=swap,
                        score=self._score(self.profile, swap),
                        exploration_delta=item.exploration_delta,
                    )
                    trial_score = self._objective(
                        trial,
                        meal=meal,
                        target_kcal=target_kcal,
                        target_protein=target_protein,
                        target_carb=target_carb,
                        target_fat=target_fat,
                    )
                    if trial_score > current_score:
                        current = trial
                        current_score = trial_score
                        improved = True
            if not improved:
                break
        return current

    def _objective(
        self,
        items: Sequence[PlanItem],
        *,
        meal: str,
        target_kcal: float,
        target_protein: float,
        target_carb: float,
        target_fat: float,
    ) -> float:
        """The penalised objective.

            F(S) = Σ score(i) · P_meal(S)
                   − λ·|kcal(S) − E| / E
                   − μ·Σ_k |macro_k(S) − T_k| / T_k

        The nutrition constraints enter as penalty terms rather than
        disqualifying a violating solution, so the search can pass through a
        slightly-off solution on its way to a better one instead of getting
        stuck early on a poor but valid one.

        `P_meal` is the **per-meal soft-rule multiplier** — see
        `enforce_per_meal`. It is 1.0 when there are no such rules, which is
        every case the Dart implementation covers, so the two stay comparable.
        """
        total_score = sum(i.score for i in items) * self._meal_multiplier(items)

        kcal = sum(i.kcal for i in items)
        energy_term = 0.0 if target_kcal <= 0 else abs(kcal - target_kcal) / target_kcal

        def macro_term(actual: float, target: float) -> float:
            return 0.0 if target <= 0 else abs(actual - target) / target

        macro_sum = (
            macro_term(sum(i.protein for i in items), target_protein)
            + macro_term(sum(i.carb for i in items), target_carb)
            + macro_term(sum(i.fat for i in items), target_fat)
        )
        return (
            total_score
            - self.energy_penalty * energy_term
            - self.macro_penalty * macro_sum
        )

    def _meal_multiplier(self, items: Sequence[PlanItem]) -> float:
        """The per-meal soft-rule multiplier for one meal's selection.

        **This is the `per_meal` scope finally getting an enforcing layer.**
        `f1_filter.ENFORCED_BY` used to map it to `None`: the rule set holds
        one such rule — diabetes, carbohydrate <= 60 g per meal — and nothing
        in the system applied it. It could not be applied per food, because
        `scope = 'per_meal'` is a statement about the meal's TOTAL: applied
        per food it misses a meal that goes over while no single dish does,
        and it penalises a large dish in a meal that still has room.

        Step 4 is the first layer that knows a meal's total, so it is the
        only place this can live. The multiplier is applied to the meal's
        taste score inside the objective, which makes a meal over the
        threshold lose to an equivalent one under it — a penalty, not a
        prohibition, which is what `is_hard = 0` means.
        """
        if not self.per_meal_rules:
            return 1.0
        totals = {
            nutrient: sum(i.amount_of(nutrient) or 0.0 for i in items)
            for nutrient in {r.nutrient for r in self.per_meal_rules}
        }
        missing = {
            nutrient: sum(
                1 for i in items if i.amount_of(nutrient) is None
            )
            for nutrient in totals
        }
        return meal_penalty(totals, self.per_meal_rules, missing=missing).factor

    def _day_totals(self, picks: Mapping[str, Sequence[PlanItem]]) -> dict[str, float]:
        return {
            nutrient: sum(
                i.amount_of(nutrient) or 0.0
                for items in picks.values()
                for i in items
            )
            for nutrient in SUPPORTED_NUTRIENTS
        }

    def _repair_nutrients(
        self,
        *,
        picks: dict[str, list[PlanItem]],
        used: set[str],
        target_kcal: float,
        meals: Sequence[str] = MEAL_TYPES,
    ) -> None:
        """Phase 5 — swap foods until the day-level constraints hold.

        It **swaps within a role**, adding nothing and removing nothing:
        adding a serving would break the energy target, removing one would
        break the meal's structure.

        Each round takes the **worst violation** first, measured as a
        fraction of its threshold so nutrients in different units compare. A
        swap is accepted only when

          1. it makes that violation smaller;
          2. it breaks no other constraint that is currently satisfied;
          3. the energy deviation afterwards is still within
             `max_energy_deviation`, or at least no worse than it already is.

        Condition 2 is the easy one to get wrong. Without it this phase fixes
        a fibre shortfall by stuffing in high-sodium dishes, and someone with
        hypertension gets a plan that meets its fibre goal while breaching
        the one threshold that matters to them.

        Among swaps that improve things equally, the one that **keeps taste
        best** wins: dropping that tie-break was measured to cost 7.1 % of
        the taste-match score instead of 2.1 %.

        `meals` restricts which servings may be swapped. The totals are
        always the whole day's, so when only one meal is being rebuilt a
        threshold the other three breach on their own cannot be repaired
        here. It is then reported in `nutrient_violations` rather than
        silently left out — the plan says what it could not fix.
        """
        active = [
            t for t in self.nutrient_targets
            if t.nutrient in SUPPORTED_NUTRIENTS
        ]
        if not active:
            return

        for _ in range(self.nutrient_repair_rounds):
            totals = self._day_totals(picks)

            worst: NutrientTarget | None = None
            worst_violation = 0.0
            for target in active:
                v = target.violation(totals.get(target.nutrient, 0.0))
                if v > worst_violation:
                    worst_violation = v
                    worst = target
            if worst is None:
                return

            kcal_now = sum(
                i.kcal for items in picks.values() for i in items
            )
            deviation_now = (
                0.0 if target_kcal <= 0
                else abs(kcal_now - target_kcal) / target_kcal
            )
            deviation_cap = max(deviation_now, self.max_energy_deviation)

            best_meal: str | None = None
            best_index = -1
            best_food: Food | None = None
            best_violation = worst_violation
            best_score = -1.0

            for meal in meals:
                items = picks[meal]
                for i, item in enumerate(items):
                    current = item.food
                    current_value = value_of(current, worst.nutrient) or 0.0

                    for swap in self.candidates:
                        if swap.dish_role != current.dish_role:
                            continue
                        if swap.id in used:
                            continue

                        swap_value = value_of(swap, worst.nutrient) or 0.0
                        new_total = (
                            totals.get(worst.nutrient, 0.0)
                            - current_value
                            + swap_value
                        )
                        new_violation = worst.violation(new_total)
                        if new_violation > best_violation:
                            continue

                        new_kcal = kcal_now - float(current.kcal) + float(swap.kcal)
                        new_deviation = (
                            0.0 if target_kcal <= 0
                            else abs(new_kcal - target_kcal) / target_kcal
                        )
                        if new_deviation > deviation_cap:
                            continue

                        breaks_other = False
                        for other in active:
                            if other is worst:
                                continue
                            before = totals.get(other.nutrient, 0.0)
                            if not other.is_satisfied_by(before):
                                continue
                            after = (
                                before
                                - (value_of(current, other.nutrient) or 0.0)
                                + (value_of(swap, other.nutrient) or 0.0)
                            )
                            if not other.is_satisfied_by(after):
                                breaks_other = True
                                break
                        if breaks_other:
                            continue

                        score = self._score(self.profile, swap)
                        strictly_better = new_violation < best_violation - 1e-9
                        if strictly_better or score > best_score:
                            best_violation = new_violation
                            best_score = score
                            best_meal = meal
                            best_index = i
                            best_food = swap

            # Nothing improves any more: the catalogue holds no food that
            # would satisfy this constraint. Stop and let
            # `DailyPlan.nutrient_violations` report it, rather than swapping
            # pointlessly or returning an empty plan.
            if best_meal is None or best_food is None:
                return
            if best_violation >= worst_violation:
                return

            replaced = picks[best_meal][best_index]
            used.discard(replaced.food.id)
            used.add(best_food.id)
            picks[best_meal][best_index] = PlanItem(
                food=best_food,
                score=self._score(self.profile, best_food),
                exploration_delta=replaced.exploration_delta,
            )

    # -- used by the "swap this dish" feature -------------------------

    def alternatives_for(
        self,
        item: PlanItem,
        *,
        exclude_ids: Iterable[str] = (),
        limit: int = 6,
    ) -> list[Food]:
        """Replacements for one serving, best taste first.

        A swap produces two training signals at once: the dropped food takes
        a low label, the chosen one a high label — the `plan_replaced` and
        `plan_kept` rows of the label mapping.
        """
        blocked = set(exclude_ids)
        pool = [
            f for f in self.candidates
            if f.dish_role == item.food.dish_role and f.id not in blocked
        ]
        pool.sort(
            key=lambda f: (
                -self._score(self.profile, f),
                abs(float(f.kcal) - float(item.food.kcal)),
                f.name,
                f.id,
            )
        )
        return pool[:limit]
