# -*- coding: utf-8 -*-
"""Rocchio preference profile — **the Python twin of `preference_profile.dart`**.

Stage 1 of the cold-start strategy:

        p_u  =  sum w(a_i) * v_i  /  sum |w(a_i)|
        w: like = +1 , neutral = 0 , dislike = -1
        `unknown` swipes are dropped from **both** numerator and denominator

Why a Python version is needed too. Two callers that the Flutter app cannot
reach:

1.  `profile_snapshot` when building the training set — it has to be the
    vector **at the moment the signal was collected**, so the swipe history
    has to be replayed in chronological order on the server. See
    `ml/build_dataset.py`.
2.  The `content_based` baseline during evaluation — the very baseline this
    project has to beat `rule_based` and `popularity` with.

A `neutral` swipe carries weight 0, so it contributes to neither numerator
nor denominator, **yet it is still counted** in `n_signals`: it is a signal
the user did give, merely a neutral one. That distinction keeps `n_signals`
measuring the right quantity — "how many foods were swiped" — which is what
the stage-transition formula for alpha consumes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .features import FEATURE_VERSION, FeatureSpace, Food, cosine_similarity

#: `interactions.action` -> Rocchio weight. `None` means drop from the
#: computation: "I have never tried this" is nothing like "I find it
#: unremarkable". Folding `unknown` in as a 0 would inflate the denominator
#: and pull the vector toward the origin, diluting every real preference.
WEIGHTS = {
    "like": 1.0,
    "neutral": 0.0,
    "dislike": -1.0,
    "unknown": None,
}


@dataclass(frozen=True)
class PreferenceProfile:
    """The vector `p_u` together with the two quantities stored beside it."""

    weights: tuple[float, ...]
    sum_abs_weight: float
    n_signals: int

    @property
    def is_empty(self) -> bool:
        """Empty when **every weight is zero**, not when there are no swipes.

        The distinction matters because a user can state a nutrition goal
        before their first swipe: the profile then has `n_signals == 0` but
        non-zero weights, and it still has to be able to rank.
        """
        return all(w == 0 for w in self.weights)

    def score(self, space: FeatureSpace, food: Food) -> float:
        """Preference score in [0, 1].

        Cosine lands in [-1, 1]; `(1 + cos) / 2` maps it into [0, 1] so it
        shares **one scale** with the Stage 2 model score — which is what
        lets the blend `alpha*ML + (1-alpha)*cosine` skip any rescaling.
        """
        if self.is_empty:
            return 0.5
        return (1 + cosine_similarity(self.weights, space.encode(food))) / 2

    def to_json(self) -> dict[str, Any]:
        """The form written to `user_preference_profiles.weights` and to
        `ml_training_samples.profile_snapshot`."""
        return {
            "feature_version": FEATURE_VERSION,
            "weights": list(self.weights),
            "sum_abs_weight": self.sum_abs_weight,
            "n_signals": self.n_signals,
        }


def empty_profile(space: FeatureSpace) -> PreferenceProfile:
    return PreferenceProfile(tuple([0.0] * space.length), 0.0, 0)


def build_profile(
    space: FeatureSpace,
    swipes: Sequence[tuple[Food, str]],
) -> PreferenceProfile:
    """Build `p_u` from a sequence of `(food, action)` swipes.

    When the denominator is zero — a session of nothing but `neutral` — keep
    the empty vector instead of dividing by zero: every food then scores 0.5
    and the ordering is decided by the other criteria. The Dart side does the
    same.
    """
    total = [0.0] * space.length
    sum_abs_weight = 0.0
    used = 0

    for food, action in swipes:
        if action not in WEIGHTS:
            raise ValueError(
                f"invalid action: {action!r} — must be one of {tuple(WEIGHTS)}"
            )
        w = WEIGHTS[action]
        if w is None:
            continue

        used += 1
        sum_abs_weight += abs(w)

        if w != 0.0:
            v = space.encode(food)
            for i in range(space.length):
                total[i] += w * v[i]

    if sum_abs_weight > 0:
        total = [x / sum_abs_weight for x in total]

    return PreferenceProfile(tuple(total), sum_abs_weight, used)


def alpha(n_signals: int, n_min: int = 30, n_max: int = 100) -> float:
    """The blend coefficient between Stage 1 and Stage 2.

            alpha = 0                            if n < n_min
                    (n - n_min) / (n_max - n_min) if n_min <= n <= n_max
                    1                            if n > n_max

    A gradual rather than abrupt switch, because the user would otherwise see
    the meal plan change oddly the moment they crossed the threshold.
    """
    if n_max <= n_min:
        raise ValueError("n_max must be greater than n_min")
    if n_signals < n_min:
        return 0.0
    if n_signals > n_max:
        return 1.0
    return (n_signals - n_min) / (n_max - n_min)


def stage(n_signals: int, n_min: int = 30, n_max: int = 100) -> str:
    """The value for `user_preference_profiles.stage`."""
    if n_signals <= 0:
        return "cold"
    if n_signals < n_min:
        return "content"
    if n_signals <= n_max:
        return "hybrid"
    return "ml"


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """The angle between two vectors, used when comparing two profiles."""
    return math.acos(max(-1.0, min(1.0, cosine_similarity(a, b))))
