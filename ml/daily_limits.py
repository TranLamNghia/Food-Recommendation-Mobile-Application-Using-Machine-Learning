# -*- coding: utf-8 -*-
"""Per-day nutrient limits — one person's real state on one day.

`f1_filter.daily_limit_rules` returns the **thresholds** that apply to a
person (`purine_mg <= 400`, `sodium_mg <= 2000`, ...). It does not know what
they have eaten today, so it cannot answer the question the interface needs:
*how much is left*. This file supplies that missing half.

## Two sources, and why they must not be merged

The schema records eating in two different places, with different meanings:

    food_diary                     eaten — a real record, no longer changeable
    meal_plan_items (suggested,    planned — still changeable, still skippable
                     kept)

Adding the two into one number loses exactly the information the user needs:
when a food does not fit the remaining allowance, they have to see that they
are choosing between *dropping a planned dish* and *going over the limit*. A
single total would make both parts look already fixed. So `DailyLimitStatus`
keeps `eaten` and `planned` apart and only adds them when computing
`remaining`.

## The counting convention — avoiding double counting

**`food_diary` is the only source of the "eaten" part.**
`meal_plan_items.status = 'eaten'` must NOT be added in: when the user marks
something eaten, the app writes a diary row, so counting both counts one
serving twice. `check_double_counting` audits that exact condition and
reports any drift, because nothing in the database enforces the convention.

**One `meal_plan_items` row is a slot in the plan**, not an eating event. So
when a slot has been swapped (`status = 'replaced'`), its nutrition is that
of the **new** food (`replaced_by_food_id`), not the old one — the old food
is no longer in the plan. A `skipped` slot counts for nothing.

## Missing measurements — why they have to be counted, not ignored

`food_nutrition` has many NULL cells, and for one nutrient a great many:
**248 of 318 active foods have no `purine_mg`**. SQL's `SUM()` skips NULL, so
simply adding and returning a number would compute a gout patient's purine
allowance from 70 foods and present it as complete — eating five foods with
no data would record 0 mg against a 400 mg ceiling. A safety filter that
fails **open** with no warning is the worst kind of failure here.

Three ways to handle it, and why the third was chosen:

1. *Impute the missing value* the way `features.py` does for the vector. No:
   imputing a number and then drawing a safety conclusion from it is worse
   than admitting ignorance. The vector only ranks; a limit blocks food.
2. *Treat missing as blocking.* No: 248 of 318 foods would be blocked for
   every gout patient, leaving the system useless.
3. *Sum what is known, and count what is not.* `NutrientTotals` carries the
   number of missing cells per nutrient, `DailyLimit.n_missing_servings`
   says how many servings the figure is missing data for, and
   `classify_foods` returns the **undecidable** group separately. The
   interface can then say "allowance computed over 3 of 5 servings with
   purine data" instead of presenting a falsely certain number.

The rule set anticipated this elsewhere: gout's `exclude_tag` rule on the
"Giàu purin" tag carries the note *"dùng khi thiếu số liệu purine_mg"* — the
tag is a workaround for exactly those 248 foods. But a tag can only block
known high-purine foods; it does not make the daily total any more complete.

## The two directions of a threshold

`comparator` in the schema accepts both `lte` and `gte`, and the two are not
symmetric. `lte` is a **ceiling**: what remains is what may still be eaten,
and a food can *exceed* it. `gte` is a **floor**: it says how much is still
**missing**, and no food "exceeds" a floor. The data currently holds only
`lte` at the hard per-day level, but mapping both onto one subtraction and
calling the result "remaining" would let a floor added later silently block
food — so the two directions are separated from the start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence

from .f1_filter import (
    CITABLE_EVIDENCE,
    EVIDENCE_LABELS,
    NUTRIENT_COLUMNS,
    Condition,
    daily_limit_rules,
)

#: Which plan-item statuses count toward the "planned" part.
#:
#: `eaten` is deliberately absent — see the counting convention above.
#: `replaced` is present because the slot still occupies a serving, just
#: with a different food.
PLANNED_ITEM_STATUSES = ("suggested", "kept", "replaced")

#: Which plan statuses count. `completed` is a closed day's plan.
ACTIVE_PLAN_STATUSES = ("draft", "active")


@dataclass(frozen=True)
class NutrientTotals:
    """Per-nutrient totals for a group of servings, with missing-data counts.

    `totals` only sums the cells that hold a number. `missing` says how many
    servings have no measurement for each nutrient — without it, `totals`
    would be a falsely certain number.
    """

    totals: dict[str, float]
    missing: dict[str, int]
    n_servings: int

    def has_full_data(self, nutrient: str) -> bool:
        return self.missing.get(nutrient, 0) == 0


@dataclass(frozen=True)
class DailyLimit:
    """One per-day threshold, with today's consumption against it."""

    condition: str
    nutrient: str
    comparator: str
    threshold: float
    eaten: float
    planned: float
    note: str = ""
    #: Servings eaten / planned with NO measurement for this nutrient.
    missing_eaten: int = 0
    missing_planned: int = 0
    #: Hard **blocks** food; soft only **penalises**. Merging the two would
    #: turn a recommendation into a prohibition — WHO's sugar <= 25 g/day is
    #: a recommendation, sodium <= 2000 mg is a blocking threshold.
    is_hard: bool = True
    #: The multiplier applied when exceeded; soft thresholds only. See
    #: `scoring.penalty`.
    penalty: float | None = None
    #: How well-founded the threshold is — see `f1_filter.EVIDENCE_LEVELS`.
    #: The 2000 mg sodium bar can cite WHO; the 300 mg cholesterol bar
    #: cannot, because that threshold has been withdrawn. The interface has
    #: to state that difference.
    evidence_level: str = "derived"

    @property
    def is_citable(self) -> bool:
        return self.evidence_level in CITABLE_EVIDENCE

    @property
    def evidence_label(self) -> str:
        return EVIDENCE_LABELS.get(self.evidence_level, self.evidence_level)

    @property
    def n_missing_servings(self) -> int:
        """Total servings with no measurement for this nutrient."""
        return self.missing_eaten + self.missing_planned

    @property
    def has_full_data(self) -> bool:
        """Every serving counted toward this limit has a measurement.

        False means `used` is lower than reality, so `remaining` is HIGHER
        than reality — the allowance is being loosened. The interface has to
        say so rather than show the bare number.
        """
        return self.n_missing_servings == 0

    @property
    def used(self) -> float:
        """The consumed part — eaten plus still in the plan."""
        return self.eaten + self.planned

    @property
    def is_ceiling(self) -> bool:
        return self.comparator == "lte"

    @property
    def remaining(self) -> float:
        """How much more may be eaten. Meaningful only for a ceiling.

        Not clamped at 0: a negative number means the limit has been
        exceeded, and the interface needs to know by how much in order to say
        so, rather than seeing a flat 0.
        """
        if not self.is_ceiling:
            raise ValueError(
                f"{self.nutrient}: a `gte` threshold is a floor, ask for "
                "`shortfall` rather than `remaining`"
            )
        return self.threshold - self.used

    @property
    def shortfall(self) -> float:
        """How much more must be eaten to reach a floor. `gte` only."""
        if self.is_ceiling:
            raise ValueError(
                f"{self.nutrient}: an `lte` threshold is a ceiling, ask for "
                "`remaining` rather than `shortfall`"
            )
        return max(0.0, self.threshold - self.used)

    @property
    def is_exceeded(self) -> bool:
        """Whether the ceiling has been passed. A floor is never `exceeded`."""
        return self.is_ceiling and self.used > self.threshold

    @property
    def ratio(self) -> float:
        """Used over threshold, for drawing a progress bar. Not clamped."""
        if self.threshold <= 0:
            return 0.0
        return self.used / self.threshold

    def fits(self, amount: float) -> bool:
        """Would adding `amount` of this nutrient stay within the threshold?

        A floor always returns `True`: eating more never breaks a floor.
        """
        if not self.is_ceiling:
            return True
        return self.used + amount <= self.threshold


@dataclass(frozen=True)
class DailyLimitStatus:
    """All of one person's per-day limits for one day."""

    user_id: str
    day: date
    limits: tuple[DailyLimit, ...] = ()
    #: Eaten, including nutrients with no threshold — the interface also uses
    #: it to show energy and macronutrients.
    eaten: NutrientTotals = field(
        default_factory=lambda: NutrientTotals({}, {}, 0)
    )
    #: In today's plan but not yet eaten.
    planned: NutrientTotals = field(
        default_factory=lambda: NutrientTotals({}, {}, 0)
    )

    @property
    def is_empty(self) -> bool:
        """No per-day hard threshold at all — this person has no limits."""
        return not self.limits

    def for_nutrient(self, nutrient: str) -> list[DailyLimit]:
        """The thresholds applying to one nutrient.

        Returns a list because two conditions may restrict the same nutrient
        with different thresholds — hypertension and kidney disease both cap
        sodium at 2000 mg. Take the tightest with `tightest_limit`.
        """
        return [limit for limit in self.limits if limit.nutrient == nutrient]

    def tightest_limit(self, nutrient: str) -> DailyLimit | None:
        """The ceiling with the least headroom for a nutrient, or `None`."""
        ceilings = [
            limit
            for limit in self.for_nutrient(nutrient)
            if limit.is_ceiling and limit.is_hard
        ]
        return min(ceilings, key=lambda limit: limit.remaining) if ceilings else None

    def exceeded(self) -> list[DailyLimit]:
        """Thresholds already passed, hard and soft alike."""
        return [limit for limit in self.limits if limit.is_exceeded]

    def hard_limits(self) -> list[DailyLimit]:
        """Thresholds that block food."""
        return [limit for limit in self.limits if limit.is_hard]

    def soft_limits(self) -> list[DailyLimit]:
        """Thresholds that only penalise — recommendations, not prohibitions."""
        return [limit for limit in self.limits if not limit.is_hard]

    def exceeded_recommendations(self) -> list[DailyLimit]:
        """SOFT thresholds already passed — the interface says "over the
        recommendation", not "excluded"."""
        return [
            limit for limit in self.limits if limit.is_exceeded and not limit.is_hard
        ]


# ── Reading consumption ───────────────────────────────────────────────

#: The nutrients that get summed. Reuses F1's declaration so the two places
#: cannot drift apart.
NUTRIENTS: tuple[str, ...] = tuple(NUTRIENT_COLUMNS)


def _totals_select() -> str:
    """The SELECT clause: per-nutrient totals scaled by portion, plus the
    count of missing cells.

    Two columns per nutrient. The `missing_*` column is what keeps `totals`
    from becoming a falsely certain number: `SUM` skips NULL, so without the
    count a nutrient missing from 248 of 318 foods still produces a
    perfectly ordinary-looking total.
    """
    parts = []
    for nutrient in NUTRIENTS:
        parts.append(f"COALESCE(SUM(fn.{nutrient} * {{factor}}), 0) AS {nutrient}")
        parts.append(f"SUM(fn.{nutrient} IS NULL) AS missing_{nutrient}")
    return ",\n       ".join(parts)


_SQL_EATEN = f"""
SELECT COUNT(*) AS n_servings,
       {_totals_select().format(factor='fd.portion_multiplier')}
FROM food_diary fd
JOIN food_nutrition fn ON fn.food_id = fd.food_id
WHERE fd.user_id = %s
  AND fd.ate_on  = %s
"""

# A swapped slot counts as the NEW food: join `food_nutrition` through
# COALESCE rather than through `mpi.food_id`, otherwise the slot's nutrition
# is that of the food that was dropped.
_SQL_PLANNED = f"""
SELECT COUNT(*) AS n_servings,
       {_totals_select().format(factor='mpi.portion_multiplier')}
FROM meal_plans mp
JOIN meal_plan_items mpi ON mpi.meal_plan_id = mp.id
JOIN food_nutrition fn
  ON fn.food_id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
WHERE mp.user_id   = %s
  AND mp.plan_date = %s
  AND mp.status    IN ({", ".join(["%s"] * len(ACTIVE_PLAN_STATUSES))})
  AND mpi.status   IN ({", ".join(["%s"] * len(PLANNED_ITEM_STATUSES))})
"""


def _totals_row(cn, sql: str, params: Sequence[Any]) -> NutrientTotals:
    with cn.cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
    if not row:
        return NutrientTotals(
            {n: 0.0 for n in NUTRIENTS}, dict.fromkeys(NUTRIENTS, 0), 0
        )
    return NutrientTotals(
        totals={n: float(row[n] or 0.0) for n in NUTRIENTS},
        missing={n: int(row[f"missing_{n}"] or 0) for n in NUTRIENTS},
        n_servings=int(row["n_servings"] or 0),
    )


def eaten_totals(cn, user_id: str, day: date) -> NutrientTotals:
    """What this person has **eaten** today, per nutrient, from `food_diary`."""
    return _totals_row(cn, _SQL_EATEN, (user_id, day))


def planned_totals(cn, user_id: str, day: date) -> NutrientTotals:
    """What is in today's plan but **not yet eaten**, per nutrient."""
    return _totals_row(
        cn,
        _SQL_PLANNED,
        (user_id, day, *ACTIVE_PLAN_STATUSES, *PLANNED_ITEM_STATUSES),
    )


def status(
    cn,
    user_id: str,
    *,
    conditions: Sequence[Condition] = (),
    day: date | None = None,
) -> DailyLimitStatus:
    """One person's per-day limit status.

    An empty `conditions` means no thresholds, but consumption is still read:
    the interface uses it to show energy and macronutrients for people with
    no medical condition at all.
    """
    today = day or date.today()
    eaten = eaten_totals(cn, user_id, today)
    planned = planned_totals(cn, user_id, today)

    limits: list[DailyLimit] = []
    for rule in daily_limit_rules(cn, conditions, hard_only=False):
        nutrient = rule["nutrient"]
        if nutrient not in NUTRIENTS:
            # The schema may add a new nutrient; skipping it silently would
            # drop a safety threshold, so raise instead.
            raise ValueError(
                f"`condition_rules` has a threshold for nutrient "
                f"`{nutrient}` that `NUTRIENT_COLUMNS` does not declare — "
                "update `ml/f1_filter.py`"
            )
        limits.append(
            DailyLimit(
                condition=rule["name_vi"],
                nutrient=nutrient,
                comparator=rule["comparator"],
                threshold=float(rule["threshold"]),
                eaten=eaten.totals[nutrient],
                planned=planned.totals[nutrient],
                note=rule.get("note") or "",
                missing_eaten=eaten.missing[nutrient],
                missing_planned=planned.missing[nutrient],
                is_hard=bool(rule["is_hard"]),
                evidence_level=rule["evidence_level"],
                penalty=(
                    None if rule["penalty"] is None else float(rule["penalty"])
                ),
            )
        )

    return DailyLimitStatus(
        user_id=user_id,
        day=today,
        limits=tuple(limits),
        eaten=eaten,
        planned=planned,
    )


# ── Which foods do not fit the remaining allowance ────────────────────


@dataclass(frozen=True)
class LimitExceedance:
    """A food that does not fit today's remaining allowance."""

    food_id: str
    name: str
    nutrient: str
    condition: str
    food_value: float
    remaining: float
    threshold: float
    note: str = ""

    @property
    def excess(self) -> float:
        return self.food_value - self.remaining


@dataclass(frozen=True)
class LimitCheckResult:
    """A set of foods classified against today's remaining allowance."""

    #: `{food_id: [reason, ...]}` — definitely does not fit. One food may
    #: breach several thresholds at once.
    does_not_fit: dict[str, list[LimitExceedance]]
    #: `{food_id: [nutrient, ...]}` — no measurement, so **no conclusion is
    #: possible**. This is not the "fits" group: it is the unknown group, and
    #: folding it into "fits" is how a safety filter fails open.
    undecidable: dict[str, list[str]]

    def fits(self, food_id: str) -> bool:
        """This food fits every limit, and every nutrient has a measurement."""
        return food_id not in self.does_not_fit and food_id not in self.undecidable


def classify_foods(
    status_today: DailyLimitStatus,
    foods: Iterable[dict[str, Any]],
) -> LimitCheckResult:
    """Classify `foods` against the remaining allowance — three groups, not two.

    `foods` are the rows returned by `f1_filter.allowed_foods`: they have
    passed every hard per-serving constraint, so the only remaining reason to
    drop one here is that **today's allowance is nearly used up**. Telling
    those two reasons apart is something the interface must do: a food
    excluded by its nature is never acceptable, while a food dropped here
    **is selectable on another day**.

    The third group, `undecidable`, is foods with no measurement for a
    restricted nutrient. For `purine_mg` that is 248 of 318 foods, so folding
    this group into "fits" would mean a gout patient's purine ceiling is
    almost never reached. The final decision about this group belongs to the
    layer above — show the food with a note, or drop it — but it has to be a
    decision that is stated.
    """
    # Only HARD thresholds block food. Soft per-day thresholds stay in
    # `status_today.limits` so the interface can draw a progress bar, but
    # exceeding one is a penalty matter, not a reason to drop the food.
    ceilings = [
        limit
        for limit in status_today.limits
        if limit.is_ceiling and limit.is_hard
    ]
    if not ceilings:
        return LimitCheckResult({}, {})

    does_not_fit: dict[str, list[LimitExceedance]] = {}
    undecidable: dict[str, list[str]] = {}
    for food in foods:
        reasons: list[LimitExceedance] = []
        missing: list[str] = []
        for limit in ceilings:
            value = food.get(limit.nutrient)
            if value is None:
                missing.append(limit.nutrient)
                continue
            value = float(value)
            if not limit.fits(value):
                reasons.append(
                    LimitExceedance(
                        food_id=food["id"],
                        name=food.get("name", ""),
                        nutrient=limit.nutrient,
                        condition=limit.condition,
                        food_value=value,
                        remaining=limit.remaining,
                        threshold=limit.threshold,
                        note=limit.note,
                    )
                )
        # Breaching one known threshold settles it, even if another threshold
        # has no measurement: it definitely does not fit.
        if reasons:
            does_not_fit[food["id"]] = reasons
        elif missing:
            undecidable[food["id"]] = missing
    return LimitCheckResult(does_not_fit=does_not_fit, undecidable=undecidable)


# ── Auditing the counting convention ──────────────────────────────────


def check_double_counting(cn, user_id: str, day: date) -> list[dict[str, Any]]:
    """Audit the "`food_diary` is the only source of the eaten part" rule.

    Nothing in the database forces the app to write a diary row when the user
    marks something eaten, so the convention can be broken without anyone
    noticing — and the consequence is an under-counted allowance, that is, a
    safety filter silently loosened. This returns the `status = 'eaten'`
    slots that have **no** matching diary row.

    An empty list means the convention is being honoured.
    """
    sql = """
SELECT mpi.id          AS item_id,
       mpi.meal_type,
       f.name          AS food_name,
       COALESCE(mpi.replaced_by_food_id, mpi.food_id) AS food_id
FROM meal_plans mp
JOIN meal_plan_items mpi ON mpi.meal_plan_id = mp.id
JOIN foods f ON f.id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
WHERE mp.user_id   = %s
  AND mp.plan_date = %s
  AND mpi.status   = 'eaten'
  AND NOT EXISTS (
        SELECT 1 FROM food_diary fd
        WHERE fd.user_id = mp.user_id
          AND fd.ate_on  = mp.plan_date
          AND fd.food_id = COALESCE(mpi.replaced_by_food_id, mpi.food_id)
      )
ORDER BY mpi.meal_type, f.name
"""
    with cn.cursor() as cur:
        cur.execute(sql, (user_id, day))
        return list(cur.fetchall())
