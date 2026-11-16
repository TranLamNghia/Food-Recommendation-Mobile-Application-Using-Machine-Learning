# -*- coding: utf-8 -*-
"""Scoring one food for one user — four stages, a single place.

Why this is its own file. The preference score is computed in **two
different places**:

    ml/evaluate.py  — during evaluation, to produce the Chapter 3 figures
    ml/serve.py     — during serving, to build a plan for a real user

If each implemented its own formula, the reported numbers would no longer
describe the running system. And that is the kind of drift **nobody
notices**: both sides run, both return numbers in [0, 1], they just describe
two different systems. So every scoring formula lives here and both sides
call in.

Every function here is **pure**: numbers in, numbers out, no database. That
is what lets `tools/check_ml.py` test them without a database, including the
edge cases that the real data does not contain.

The shared scale is [0, 1] for all four stages. That is the precondition for
`alpha*ML + (1-alpha)*cosine` to mean anything — two numbers on one scale can
be blended; on different scales the blend is meaningless even though it still
produces a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .f1_filter import SoftRule
from .features import cosine_similarity
from .rocchio import alpha

#: The split between popularity and macro fit in Stage 0.
#:
#: A **hand-set** ratio, named as a constant rather than buried in an
#: expression. Half and half because at Stage 0 the system knows nothing
#: about this person: there is no basis for trusting popularity over
#: nutritional fit or the other way round.
STAGE0_POPULARITY_WEIGHT = 0.5

#: The neutral score. Returned when there is no basis for ranking this food
#: above or below another — an empty preference profile, or no active model.
#: 0.5 rather than 0: a score of 0 means "disliked", which is a different
#: claim from "unknown", and dropping everything to 0 would strip Step 4 of
#: all ranking information.
NEUTRAL_SCORE = 0.5


def popularity_score(popularity: float) -> float:
    """The trivial baseline — popularity only, no personalisation at all.

    `foods.popularity_score` already lives in [0, 1] (`DECIMAL(5,4)`), so no
    conversion is needed. Clamped so that one bad row cannot push a score off
    the shared scale.
    """
    return min(1.0, max(0.0, popularity))


def macro_fit(
    food_vector: Sequence[float], target_macro_pct: Sequence[float]
) -> float:
    """How well this food fits the user's target macro split, in [0, 1].

        fit = 1 - (sum of absolute differences) / 2

    Divided by 2 because both share vectors sum to 1, so the total absolute
    difference between them is at most 2 — halving maps it onto exactly
    [0, 1] with no clamping needed.

    The first three dimensions of the food vector are shares of **energy**
    from protein / carbohydrate / fat, and `health_profiles.target_*_pct` are
    energy shares too, so the two compare directly once divided by 100.
    """
    if len(food_vector) < 3:
        raise ValueError("food vector must have at least 3 macro dimensions")
    if len(target_macro_pct) != 3:
        raise ValueError("the macro target must be exactly 3 percentages")

    total_pct = sum(target_macro_pct)
    if total_pct <= 0:
        return NEUTRAL_SCORE
    # Normalise to sum 1 rather than hard-dividing by 100: `chk_macro_sum`
    # requires the total to be 100, but if that constraint is ever relaxed
    # the comparison stays correct instead of drifting silently.
    target = [x / total_pct for x in target_macro_pct]
    diff = sum(abs(a - b) for a, b in zip(food_vector[:3], target))
    return max(0.0, 1 - diff / 2)


def rule_score(
    food_vector: Sequence[float],
    target_macro_pct: Sequence[float],
    popularity: float,
) -> float:
    """Stage 0 — no taste signal yet.

    Blends popularity with fit to the target macro split. Medical filtering
    is **not** here: F1 applies identically at every stage so it cannot
    distinguish between them, and folding it into the scoring function would
    mix a **safety** decision with a **preference** decision. Those two have
    to stay apart, otherwise explaining why a food was dropped cannot
    separate "your condition forbids it" from "you would not like it".
    """
    w = STAGE0_POPULARITY_WEIGHT
    return w * popularity_score(popularity) + (1 - w) * macro_fit(
        food_vector, target_macro_pct
    )


def content_score(p_u: Sequence[float], food_vector: Sequence[float]) -> float:
    """Stage 1 — `(1 + cos(p_u, v_i)) / 2`.

    An empty profile returns the neutral score, exactly as
    `PreferenceProfile.score` does on the Dart side: when every weight is
    zero the angle is undefined, and every food must receive the same score
    so that the other criteria decide the order.
    """
    if not any(p_u):
        return NEUTRAL_SCORE
    return (1 + cosine_similarity(p_u, food_vector)) / 2


def blend(ml: float, content: float, n_signals: int) -> float:
    """The smooth transition — `alpha*ML + (1-alpha)*cosine`, alpha from
    `n_signals`.

    Not an abrupt switch at the threshold, because the user would see their
    meal plan change oddly within a single day.
    """
    a = alpha(n_signals)
    return a * ml + (1 - a) * content


# ── Soft constraints — the per-serving penalty ────────────────────────
#
# `penalty` is a **MULTIPLIER**, not an amount to subtract.
#
# The schema only says `DECIMAL(4,3)` and `docs/DATABASE_DESIGN.md` once
# called it a "score deduction factor". The data itself refutes that reading:
#
#     Hypertension - sodium <= 700 mg/serving - mild   - penalty 0.600
#     Hypertension - sodium <= 500 mg/serving - severe - penalty 0.400
#         note: "SOFT constraint, penalised harder at the severe level"
#
# As a subtraction, 0.400 subtracts less than 0.600, meaning the severe level
# is penalised MORE LIGHTLY — the exact opposite of that row's own note. As a
# multiplier, x0.400 is harsher than x0.600, which matches. Multiplication
# also keeps the score inside [0, 1], whereas subtracting 0.750 would push a
# score in [0, 1] negative.


@dataclass(frozen=True)
class SoftViolation:
    """One soft constraint that this food exceeds."""

    condition: str
    nutrient: str
    comparator: str
    threshold: float
    value: float
    penalty: float
    note: str = ""

    @property
    def excess(self) -> float:
        """How far past the threshold, always a positive number."""
        if self.comparator == "lte":
            return self.value - self.threshold
        return self.threshold - self.value


@dataclass(frozen=True)
class PenaltyResult:
    """A food's penalty factor, with the reasons for the interface to state."""

    factor: float
    violations: tuple[SoftViolation, ...] = ()
    #: Nutrients this food has no measurement for, so none of their soft
    #: rules could be evaluated. Not penalised, but not to be treated as
    #: checked either.
    missing_data: tuple[str, ...] = ()

    @property
    def is_penalised(self) -> bool:
        return self.factor < 1.0

    def apply(self, score: float) -> float:
        """Apply the factor to a score in [0, 1].

        The caller keeps the original `score`: the interface needs to say
        "taste match 0.78, reduced because it is salty" rather than just
        showing 0.47 with no explanation.
        """
        return score * self.factor


def penalty(
    measurements: Mapping[str, float | None],
    rules: Sequence[SoftRule],
) -> PenaltyResult:
    """A food's penalty factor under the **per-serving** soft constraints.

    `measurements` holds one serving's nutrition as `{nutrient: value}`; a
    value of `None` means there is no measurement.

    **Accepts `scope = 'per_serving'` only.** Passing a `per_meal` or
    `per_day` rule in here is a programming error, not unusual data: applying
    one per food is wrong in both directions — it misses the case where a
    meal total is exceeded although no single food exceeds it, and it
    wrongly penalises a large food in a meal that still has room. So the
    function raises rather than quietly producing a plausible-looking number.

    **Penalties combine.** Two rules sharing a (condition, nutrient) are
    nested bands — sodium <= 700 mg and <= 500 mg for the same hypertension,
    say: a food at 800 mg exceeds both, but that is **one** concern, not two.
    Multiplying both gives x0.24 instead of x0.40 — double counting. So
    within each (condition, nutrient) group take the HARSHEST factor, then
    multiply across distinct groups.

    Missing data means **no penalty**, but it is recorded. A soft constraint
    is a ranking decision, not a safety one, so lowering a food's score
    because the catalogue lacks a measurement penalises the wrong party. This
    is the opposite of `f1_filter.allowed_foods`, where missing data excludes
    — the question there is "is this food safe".
    """
    harshest: dict[tuple[str, str], SoftViolation] = {}
    missing: list[str] = []

    for rule in rules:
        if rule.scope != "per_serving":
            raise ValueError(
                f"`penalty` accepts per_serving rules only, got {rule.scope!r} "
                f"({rule.condition} - {rule.nutrient}). per_meal belongs to "
                f"Step 4, per_day to ml/daily_limits.py"
            )
        value = measurements.get(rule.nutrient)
        if value is None:
            if rule.nutrient not in missing:
                missing.append(rule.nutrient)
            continue
        value = float(value)
        if not rule.is_violated(value):
            continue
        violation = SoftViolation(
            condition=rule.condition,
            nutrient=rule.nutrient,
            comparator=rule.comparator,
            threshold=rule.threshold,
            value=value,
            penalty=rule.penalty,
            note=rule.note,
        )
        key = (rule.condition, rule.nutrient)
        current = harshest.get(key)
        if current is None or violation.penalty < current.penalty:
            harshest[key] = violation

    factor = 1.0
    for violation in harshest.values():
        factor *= violation.penalty

    return PenaltyResult(
        factor=factor,
        violations=tuple(
            sorted(
                harshest.values(),
                key=lambda v: (v.penalty, v.condition, v.nutrient),
            )
        ),
        missing_data=tuple(sorted(missing)),
    )
