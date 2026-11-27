#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the machine-learning layer — **no database needed**.

Why this file exists. The scripts in `ml/` have been exercised against a
scratch database, but that only covers the cases the real data happens to
contain. The most error-prone places are the **edge cases**: a dataset with one
single energy level, a user who swipes nothing but `neutral`, a person with no
food worth recommending, a training set with only one class. The real data has
none of those today, so they have to be constructed by hand.

Every check here runs on pure functions, so this file works immediately after a
clone — no MySQL, no user signals.

The ranking metrics are compared against **hand-computed values**, not against
the output of the code being checked. A test that compares code with itself
only detects change, never error.

Run:
    python tools/check_ml.py

Note on language: the asserted string literals stay as they are — condition
names and tag names come from the database, the explanation sentences and
`EVIDENCE_LABELS` are shown to users, and the dimension labels are the contract
shared with `food_vector.dart`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml import scoring  # noqa: E402
from ml.build_dataset import (  # noqa: E402
    Sample,
    assign_folds,
    deduplicate,
    split_label,
    label_from_rating,
)
from ml.f1_filter import (  # noqa: E402
    CITABLE_EVIDENCE,
    EVIDENCE_LEVELS,
    EVIDENCE_LABELS,
    ENFORCED_BY,
    USER_BLOCKED_LABEL,
    USER_BLOCKED_RULE,
    SoftRule,
    ExclusionReason,
    unenforced_rules,
    soft_rules_by_scope,
)
from ml.scoring import penalty  # noqa: E402
from ml.serve import (  # noqa: E402
    PHRASE_BY_DIMENSION,
    CATEGORY_PREFIX,
    explanation_sentences,
    contributions,
    debug_explanation,
    dimensions_without_phrase,
)
from ml.dataset import LIKE_THRESHOLD  # noqa: E402
from ml.daily_limits import (  # noqa: E402
    DailyLimit,
    NutrientTotals,
    DailyLimitStatus,
    classify_foods,
)
from ml.db import use_utf8  # noqa: E402
from ml.evaluate import (  # noqa: E402
    _dcg,
    ranking_metrics,
    mean_average_precision,
)
from ml.features import (  # noqa: E402
    FEATURE_VERSION,
    FeatureSpace,
    Food,
    cosine_similarity,
    round_kcal,
)
from ml.rocchio import alpha, build_profile, stage, empty_profile  # noqa: E402

from ml.popularity import POSITIVE_STARS, from_samples, wilson_lower_bound  # noqa: E402

from datetime import date, datetime  # noqa: E402

import numpy as np  # noqa: E402

TOLERANCE = 1e-9

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
        abs(actual - expected) < TOLERANCE,
        f"{description}: got {actual!r}, expected {expected!r}",
    )


def approx4(actual: float, expected: float, description: str) -> None:
    """Compare at 4 decimal places — exactly `DECIMAL(5,4)`'s precision.

    Used for values whose reference number was computed by hand and written
    rounded to 4 places. Comparing more tightly would compare against how I
    rounded when writing the documentation, not against the formula.
    """
    check(
        abs(round(actual, 4) - expected) < 1e-9,
        f"{description}: got {round(actual, 4)!r}, expected {expected!r}",
    )


def raises(fn, exception_type, description: str) -> None:
    try:
        fn()
    except exception_type:
        check(True, description)
        return
    except Exception as e:  # pragma: no cover
        check(
            False,
            f"{description}: raised {type(e).__name__} instead of "
            f"{exception_type.__name__}",
        )
        return
    check(False, f"{description}: raised nothing")


def _food(**overrides) -> Food:
    """A sample food. Defaults: 10 g protein, 20 g carbohydrate, 5 g fat."""
    params = dict(
        id="m1", name="Test dish", category="Cơm", dish_role="main",
        spice_level=0, kcal=200, protein=10.0, carb=20.0, fat=5.0,
        sugar=4.0, sodium=300.0, fiber=2.0,
    )
    params.update(overrides)
    return Food(**params)  # type: ignore[arg-type]


# -- 1. Energy rounding ------------------------------------------------


def check_rounding() -> None:
    print("1. kcal rounding — must match Dart's `num.round()`")
    # Python's `round()` gives 2 here; Dart gives 3. That is the whole reason
    # the function exists.
    check(round_kcal(2.5) == 3, "round_kcal(2.5) = 3 (Python round gives 2)")
    check(round_kcal(3.5) == 4, "round_kcal(3.5) = 4")
    check(round_kcal(2.4) == 2, "round_kcal(2.4) = 2")
    check(round_kcal(0.5) == 1, "round_kcal(0.5) = 1")
    check(round_kcal(-2.5) == -3, "round_kcal(-2.5) = -3 (away from zero)")
    check(
        round(2.5) == 2,
        "confirming Python's round() really does round to even",
    )


# -- 2. The feature vector ---------------------------------------------


def check_feature_vector() -> None:
    print("2. The food feature vector")

    food = _food()
    # ENERGY shares: 10*4 = 40, 20*4 = 80, 5*9 = 45, total 165.
    protein, carbs, fat = food.macro_share
    approx(
        protein, 40 / 165,
        "the protein share is an energy share, not a gram share",
    )
    approx(carbs, 80 / 165, "the carbohydrate share")
    approx(fat, 45 / 165, "the fat share")
    approx(protein + carbs + fat, 1.0, "the three macro shares sum to 1")
    # Were anyone to port this as a gram share, protein would be 10/35 —
    # entirely different.
    check(
        abs(protein - 10 / 35) > 0.01,
        "the protein share DIFFERS from the gram share 10/35",
    )

    empty = _food(protein=0, carb=0, fat=0)
    check(
        empty.macro_share == (0.0, 0.0, 0.0),
        "a food with no macros gives (0, 0, 0)",
    )

    # Sugar density: sugar per gram of food, NOT divided by carbohydrate.
    approx(
        _food(sugar=20, serving_size_g=200).sugar_density,
        0.1,
        "sugar density = sugar / serving weight",
    )
    approx(
        _food(sugar=0, serving_size_g=200).sugar_density,
        0.0,
        "no sugar means a density of 0",
    )
    approx(
        _food(sugar=5, serving_size_g=0).sugar_density,
        0.0,
        "a 0 g serving returns 0 rather than dividing by zero",
    )
    # This is the whole reason the denominator changed in v2: a low-carb food
    # is no longer pushed to maximum sweetness. Real boiled egg: 0.6 g
    # carbohydrate, 2 g sugar, a 120 g serving.
    egg = _food(sugar=2.0, carb=0.6, serving_size_g=120)
    banana = _food(sugar=35.5, carb=35.5, serving_size_g=200)
    check(
        egg.sugar_density < banana.sugar_density / 5,
        f"boiled egg ({egg.sugar_density:.4f}) is far less sweet than banana "
        f"({banana.sugar_density:.4f})",
    )
    # Under the old `sugar/carb` formula these two scored EQUALLY, at 1.0.
    check(
        min(1, egg.sugar / egg.carb) == min(1, banana.sugar / banana.carb),
        "confirming the v1 formula scored those two foods identically",
    )

    # A two-category space with values spread wide.
    foods = [
        _food(id="a", category="Cơm", kcal=100, sodium=0, fiber=0, sugar=0),
        _food(
            id="b", category="Món nước", kcal=300, sodium=600, fiber=10,
            sugar=40, serving_size_g=200,
        ),
    ]
    space = FeatureSpace.from_foods(foods)
    check(
        space.length == 10,
        f"dimensions = 8 + 2 categories (got {space.length})",
    )
    check(
        len(space.labels) == space.length,
        "the label count matches the dimension count",
    )
    check(
        space.categories == ["Cơm", "Món nước"],
        f"the categories are sorted (got {space.categories})",
    )

    va = space.encode(foods[0])
    vb = space.encode(foods[1])
    approx(va[3], 0.0, "the lowest energy maps to 0")
    approx(vb[3], 1.0, "the highest energy maps to 1")
    approx(va[4], 0.0, "the lowest sugar density maps to 0")
    approx(vb[4], 1.0, "the highest sugar density maps to 1")
    approx(sum(va[8:]), 1.0, "exactly one one-hot dimension is set")
    approx(va[8], 1.0, "a 'Cơm' food sets the first category dimension")
    approx(vb[9], 1.0, "a 'Món nước' food sets the second")
    approx(va[7], 0.0, "spice level 0 maps to 0")
    approx(space.encode(_food(spice_level=3))[7], 1.0, "spice level 3 maps to 1")

    # Edge case: the whole set has one single energy level -> a zero
    # denominator.
    one_level = [_food(id="x", kcal=200), _food(id="y", kcal=200)]
    space1 = FeatureSpace.from_foods(one_level)
    approx(
        space1.encode(one_level[0])[3], 0.5,
        "a zero energy range maps to 0.5",
    )
    approx(
        space1.encode(one_level[0])[4], 0.5,
        "a zero sugar-density range maps to 0.5",
    )

    # A food in a category the space does not know: the whole one-hot block
    # is zero.
    unknown = space.encode(_food(id="z", category="Nhóm chưa có"))
    approx(
        sum(unknown[8:]), 0.0,
        "an unknown category sets no dimension at all",
    )

    raises(
        lambda: FeatureSpace.from_foods([]),
        ValueError,
        "building a space from an empty set raises ValueError",
    )

    # Saving and reloading must reproduce the same space.
    reloaded = FeatureSpace.from_params(space.params())
    check(
        reloaded.encode(foods[1]) == vb,
        "reloading from scaler_params reproduces the same vector",
    )
    wrong_version = dict(space.params())
    wrong_version["feature_version"] = "v0-old"
    raises(
        lambda: FeatureSpace.from_params(wrong_version),
        ValueError,
        "scaler_params with the wrong feature version raises ValueError",
    )
    check(FEATURE_VERSION == "v2", "the current feature version is v2")


def check_cosine() -> None:
    print("3. Cosine similarity")
    approx(cosine_similarity([1, 0], [1, 0]), 1.0, "identical vectors give 1")
    approx(cosine_similarity([1, 0], [-1, 0]), -1.0, "opposite vectors give -1")
    approx(
        cosine_similarity([1, 0], [0, 1]), 0.0, "orthogonal vectors give 0"
    )
    approx(
        cosine_similarity([0, 0], [1, 1]), 0.0,
        "a zero-length vector gives 0, with no division by zero",
    )
    raises(
        lambda: cosine_similarity([1, 0], [1, 0, 0]),
        ValueError,
        "vectors of different lengths raise ValueError",
    )


# -- 4. Rocchio ---------------------------------------------------------


def check_rocchio() -> None:
    print("4. The Rocchio preference profile")

    foods = [
        _food(id="a", category="Cơm", kcal=100, sodium=0, fiber=0),
        _food(id="b", category="Món nước", kcal=300, sodium=600, fiber=10),
    ]
    space = FeatureSpace.from_foods(foods)
    va, vb = space.encode(foods[0]), space.encode(foods[1])

    # Like a, dislike b: p_u = (1*va - 1*vb) / 2
    profile = build_profile(
        space, [(foods[0], "like"), (foods[1], "dislike")]
    )
    expected = [(x - y) / 2 for x, y in zip(va, vb)]
    check(
        all(
            abs(a - b) < TOLERANCE
            for a, b in zip(profile.weights, expected)
        ),
        "the Rocchio formula: (Σ w·v) / Σ|w|",
    )
    approx(profile.sum_abs_weight, 2.0, "the denominator Σ|w| = 2")
    check(profile.n_signals == 2, "2 signals counted")

    # `unknown` is excluded from BOTH the numerator and the denominator.
    with_unknown = build_profile(
        space,
        [(foods[0], "like"), (foods[1], "dislike"), (foods[0], "unknown")],
    )
    approx(
        with_unknown.sum_abs_weight, 2.0,
        "`unknown` does not inflate the denominator",
    )
    check(
        with_unknown.n_signals == 2,
        "`unknown` is not counted as a signal",
    )
    check(
        all(
            abs(a - b) < TOLERANCE
            for a, b in zip(with_unknown.weights, profile.weights)
        ),
        "adding an `unknown` swipe does not change the vector",
    )

    # All `neutral`: the denominator is 0 -> keep an empty vector, do NOT
    # divide by zero.
    all_neutral = build_profile(
        space, [(foods[0], "neutral"), (foods[1], "neutral")]
    )
    check(
        all_neutral.is_empty,
        "an all-`neutral` session gives an empty profile",
    )
    approx(all_neutral.sum_abs_weight, 0.0, "the denominator is 0")
    check(
        all_neutral.n_signals == 2,
        "`neutral` IS still counted as a signal",
    )
    approx(
        all_neutral.score(space, foods[0]), 0.5,
        "an empty profile scores every food 0.5",
    )

    approx(
        empty_profile(space).score(space, foods[0]), 0.5,
        "the prebuilt empty profile also gives 0.5",
    )
    check(
        len(empty_profile(space).weights) == space.length,
        "the empty profile has the full dimension count",
    )

    # Liking exactly one food gives cosine 1 with itself -> a score of 1.0.
    one_like = build_profile(space, [(foods[0], "like")])
    approx(
        one_like.score(space, foods[0]), 1.0,
        "liking exactly one food scores that food 1.0",
    )

    raises(
        lambda: build_profile(space, [(foods[0], "ghe")]),
        ValueError,
        "an unknown action raises ValueError",
    )

    check(
        profile.to_json()["feature_version"] == FEATURE_VERSION,
        "to_json records the feature version alongside",
    )


def check_alpha() -> None:
    print("5. The blend coefficient α and the stage")
    approx(alpha(0), 0.0, "α(0) = 0")
    approx(alpha(29), 0.0, "α(29) = 0 — below n_min")
    approx(alpha(30), 0.0, "α(30) = 0 — exactly at n_min")
    approx(alpha(65), 0.5, "α(65) = 0.5 — mid-range")
    approx(alpha(100), 1.0, "α(100) = 1 — exactly at n_max")
    approx(alpha(500), 1.0, "α(500) = 1")
    raises(
        lambda: alpha(50, 100, 100),
        ValueError,
        "n_max <= n_min raises ValueError",
    )

    check(stage(0) == "cold", "0 signals -> cold")
    check(stage(10) == "content", "10 signals -> content")
    check(stage(30) == "hybrid", "30 signals -> hybrid")
    check(stage(101) == "ml", "101 signals -> ml")


# -- 6. Scoring --------------------------------------------------------


def check_scoring() -> None:
    print("6. Scoring across the four stages")

    approx(
        scoring.popularity_score(0.4), 0.4,
        "the popularity score is used directly",
    )
    approx(
        scoring.popularity_score(1.7), 1.0,
        "the popularity score is clamped to 1",
    )
    approx(
        scoring.popularity_score(-0.2), 0.0,
        "the popularity score is clamped to 0",
    )

    # A perfect match: the food's shares equal the target shares.
    approx(
        scoring.macro_fit([0.15, 0.60, 0.25], [15, 60, 25]),
        1.0,
        "a perfect macro match gives 1.0",
    )
    # Maximum divergence: an all-protein food against an all-fat target ->
    # total deviation 2 -> a fit of 0.
    approx(
        scoring.macro_fit([1.0, 0.0, 0.0], [0, 0, 100]),
        0.0,
        "maximum macro divergence gives 0.0",
    )
    # A 0.1 deviation in two dimensions -> total 0.2 -> a fit of 0.9.
    approx(
        scoring.macro_fit([0.25, 0.50, 0.25], [15, 60, 25]),
        0.9,
        "a total deviation of 0.2 gives a fit of 0.9",
    )
    approx(
        scoring.macro_fit([0.15, 0.60, 0.25], [0, 0, 0]),
        0.5,
        "an empty macro target gives the neutral score",
    )
    raises(
        lambda: scoring.macro_fit([0.5, 0.5], [15, 60, 25]),
        ValueError,
        "a food vector under 3 dimensions raises ValueError",
    )

    # Stage 0 = half popularity + half macro fit.
    approx(
        scoring.rule_score([0.15, 0.60, 0.25], [15, 60, 25], 0.4),
        0.5 * 0.4 + 0.5 * 1.0,
        "rule score = 0.5*popularity + 0.5*macro fit",
    )

    # Stage 1.
    approx(
        scoring.content_score([0, 0, 0], [1, 1, 1]), 0.5,
        "an empty profile gives the neutral score 0.5",
    )
    approx(
        scoring.content_score([1, 0], [1, 0]), 1.0, "cosine 1 gives a score of 1.0"
    )
    approx(
        scoring.content_score([1, 0], [-1, 0]), 0.0,
        "cosine -1 gives a score of 0.0",
    )
    approx(
        scoring.content_score([1, 0], [0, 1]), 0.5,
        "cosine 0 gives a score of 0.5",
    )

    # Blending.
    approx(scoring.blend(1.0, 0.0, 0), 0.0, "α = 0 takes the content score whole")
    approx(scoring.blend(1.0, 0.0, 500), 1.0, "α = 1 takes the ML score whole")
    approx(scoring.blend(1.0, 0.0, 65), 0.5, "α = 0.5 blends evenly")
    approx(scoring.blend(0.8, 0.4, 65), 0.6, "blending 0.8 and 0.4 at α = 0.5")


# -- 7. Labels and deduplication ---------------------------------------


def check_labels() -> None:
    print("7. Labels, deduplication, fold assignment")

    approx(label_from_rating(5), 1.0, "5 stars -> 1.000")
    approx(label_from_rating(4), 0.75, "4 stars -> 0.750")
    approx(label_from_rating(3), 0.5, "3 stars -> 0.500")
    approx(label_from_rating(1), 0.0, "1 star -> 0.000")
    raises(
        lambda: label_from_rating(0), ValueError, "0 stars raises ValueError"
    )
    raises(
        lambda: label_from_rating(6), ValueError, "6 stars raises ValueError"
    )
    check(
        label_from_rating(3) == LIKE_THRESHOLD,
        "3 stars sits exactly at the like threshold",
    )

    older = Sample("u1", "f1", "feedback", 1.0, 1.0, datetime(2026, 1, 1))
    newer = Sample("u1", "f1", "feedback", 0.25, 1.0, datetime(2026, 2, 1))
    other_source = Sample("u1", "f1", "diary", 0.8, 0.9, datetime(2026, 1, 15))
    kept, removed = deduplicate([older, newer, other_source])
    check(len(kept) == 2, f"deduplication leaves 2 rows (got {len(kept)})")
    check(removed == 1, "it reports 1 row removed")
    feedback = [s for s in kept if s.source == "feedback"][0]
    approx(
        feedback.label, 0.25,
        "the NEWEST row of a given source is kept",
    )
    check(
        any(s.source == "diary" for s in kept),
        "the same user-food pair from a different source keeps both",
    )
    # The input order must not affect the result.
    kept2, _ = deduplicate([newer, older, other_source])
    approx(
        [s for s in kept2 if s.source == "feedback"][0].label,
        0.25,
        "reversing the input order still keeps the newest row",
    )

    users = [f"u{i:02d}" for i in range(10)]
    folds = assign_folds(users, 5, 42)
    sizes = [sum(1 for u in users if folds[u] == f) for f in range(5)]
    check(
        sizes == [2, 2, 2, 2, 2],
        f"10 users across 5 folds split evenly (got {sizes})",
    )
    check(
        assign_folds(users, 5, 42) == folds,
        "reassigning with the same seed reproduces the same split",
    )
    check(
        assign_folds(users, 5, 43) != folds,
        "changing the seed changes the split",
    )
    # 13 users across 5 folds: an imbalance of at most 1.
    users13 = [f"v{i:02d}" for i in range(13)]
    folds13 = assign_folds(users13, 5, 42)
    sizes13 = [sum(1 for u in users13 if folds13[u] == f) for f in range(5)]
    check(
        max(sizes13) - min(sizes13) <= 1,
        f"13 users across 5 folds differ by <= 1 (got {sizes13})",
    )
    raises(
        lambda: assign_folds(users, 1, 42), ValueError,
        "a single fold raises ValueError",
    )

    roles5 = [split_label(f, 5) for f in range(5)]
    check(
        roles5 == ["train", "train", "train", "val", "test"],
        f"5 folds -> 3 train, 1 val, 1 test (got {roles5})",
    )
    roles2 = [split_label(f, 2) for f in range(2)]
    check(
        roles2 == ["train", "test"],
        f"2 folds -> train/test, with NO val (got {roles2})",
    )


# -- 8. Ranking metrics, against hand-computed values ------------------


def check_metrics() -> None:
    print("8. Ranking metrics — against hand-computed values")

    approx(_dcg([1.0]), 1.0, "a one-element DCG = g / log2(2) = g")
    approx(
        _dcg([0.0, 1.0]), 1 / math.log2(3),
        "the second DCG position divides by log2(3)",
    )

    # Three foods for one user. The scores descend in the listed order.
    #   food  score  label   binary
    #    0     0.9    0.0      0
    #    1     0.8    1.0      1
    #    2     0.7    0.5      1
    scores = np.array([0.9, 0.8, 0.7])
    labels = np.array([0.0, 1.0, 0.5])
    classes = np.array([0, 1, 1])
    users = ["u1", "u1", "u1"]

    at2 = ranking_metrics(scores, labels, classes, users, 2)
    approx(at2.precision, 0.5, "precision@2 = 1 hit / 2 positions")
    approx(at2.recall, 0.5, "recall@2 = 1 hit / 2 recommendable foods")
    dcg = 0.0 / math.log2(2) + 1.0 / math.log2(3)
    idcg = 1.0 / math.log2(2) + 0.5 / math.log2(3)
    approx(
        at2.ndcg, dcg / idcg,
        "nDCG@2 uses graded gain from the continuous label",
    )
    check(at2.n_users == 1, "1 user contributes to the average")

    at3 = ranking_metrics(scores, labels, classes, users, 3)
    approx(at3.recall, 1.0, "recall@3 = 1.0 once k covers the whole list")
    approx(at3.precision, 2 / 3, "precision@3 = 2/3")

    # k larger than the food count: the denominator is the food count, not k —
    # dividing by k would depress precision for no reason.
    at9 = ranking_metrics(scores, labels, classes, users, 9)
    approx(
        at9.precision, 2 / 3,
        "with k > the food count, precision divides by the food count",
    )

    # A user with no recommendable food is left out of the average.
    none_relevant = ranking_metrics(
        np.array([0.9, 0.8]), np.array([0.0, 0.1]), np.array([0, 0]),
        ["u2", "u2"], 2,
    )
    check(
        none_relevant.n_users == 0,
        "a user with no recommendable food is left out of the average",
    )

    # Two users, one with no recommendable food -> only the other counts.
    two_users = ranking_metrics(
        np.array([0.9, 0.8, 0.9, 0.8]),
        np.array([0.0, 1.0, 0.0, 0.1]),
        np.array([0, 1, 0, 0]),
        ["u1", "u1", "u2", "u2"],
        1,
    )
    check(
        two_users.n_users == 1,
        "only the user with a recommendable food contributes",
    )
    approx(
        two_users.precision, 0.0,
        "that user's precision@1 = 0 (their hit ranks second)",
    )

    # MAP over the whole list: the hits are at positions 2 and 3.
    map_value, map_users = mean_average_precision(scores, classes, users)
    approx(
        map_value, (1 / 2 + 2 / 3) / 2,
        "MAP = the mean of 1/2 and 2/3",
    )
    check(map_users == 1, "MAP counts 1 user")

    # A perfect ranking -> MAP = 1.
    perfect, _ = mean_average_precision(
        np.array([0.9, 0.8, 0.7]), np.array([1, 1, 0]), users
    )
    approx(perfect, 1.0, "a perfect ranking gives MAP = 1.0")

    # Ties must be broken by index, not by iteration order — otherwise the
    # `popularity` variant (which ties a great deal) gives a different result
    # every run.
    ties = np.array([0.5, 0.5, 0.5])
    first, _ = mean_average_precision(ties, classes, users)
    second, _ = mean_average_precision(ties, classes, users)
    approx(first, second, "ties produce a reproducible result")


# -- 9. Popularity -----------------------------------------------------


def check_popularity() -> None:
    print("9. The Wilson lower bound for `popularity_score`")

    # The reference values were computed separately from the Wilson formula,
    # not taken from the code.
    approx4(
        wilson_lower_bound(2, 2), 0.3424, "2/2 -> 0.3424, not 1.00"
    )
    approx4(wilson_lower_bound(1, 1), 0.2065, "1/1 -> 0.2065")
    approx4(wilson_lower_bound(90, 100), 0.8256, "90/100 -> 0.8256")
    approx4(wilson_lower_bound(9, 10), 0.5958, "9/10 -> 0.5958")

    # The most important property: a small sample must NOT outrank a large one.
    check(
        wilson_lower_bound(2, 2) < wilson_lower_bound(90, 100),
        "a 2/2 food ranks BELOW a 90/100 food — the whole reason for Wilson",
    )
    # A raw proportion reaches the opposite conclusion.
    check(
        2 / 2 > 90 / 100,
        "confirming the raw proportion reaches the opposite conclusion",
    )

    approx(
        wilson_lower_bound(0, 10), 0.0, "0 likes out of 10 views -> 0"
    )
    approx(wilson_lower_bound(0, 0), 0.0, "no signal at all -> 0")

    # The same proportion with a larger sample scores higher — the lower bound
    # tightens.
    check(
        wilson_lower_bound(5, 10)
        < wilson_lower_bound(50, 100)
        < wilson_lower_bound(500, 1000),
        "at the same 50% rate, a larger sample scores higher",
    )
    check(
        wilson_lower_bound(500, 1000) < 0.5,
        "the lower bound is always below the observed rate",
    )

    # Every value must lie within [0, 1] — the column is DECIMAL(5,4) UNSIGNED.
    check(
        all(
            0.0 <= wilson_lower_bound(a, b) <= 1.0
            for b in range(1, 40)
            for a in range(b + 1)
        ),
        "every combination up to 40 samples stays within [0, 1]",
    )
    raises(
        lambda: wilson_lower_bound(5, 2),
        ValueError,
        "more likes than the sample size raises ValueError",
    )
    check(
        POSITIVE_STARS == 4,
        "the positive star threshold is 4, not 3 (3 stars = neutral)",
    )

    print("10. Popularity rebuilt from the training folds — leakage control")

    #  i  user  food  label   source       fold
    #  0   u1    fA   0.9     swipe         0   <- training
    #  1   u2    fA   0.9     swipe         0   <- training
    #  2   u3    fA   0.9     swipe         1   <- TEST, must be excluded
    #  3   u1    fB   0.0     swipe         0   <- training
    #  4   u1    fC   0.1     random_neg    0   <- must be excluded from counts
    users = ["u1", "u2", "u3", "u1", "u1"]
    foods = ["fA", "fA", "fA", "fB", "fC"]
    labels = [0.9, 0.9, 0.9, 0.0, 0.1]
    sources = ["swipe", "swipe", "swipe", "swipe", "random_neg"]
    train = [0, 1, 3, 4]

    popularity = from_samples(
        users, foods, labels, sources, train, positive_threshold=0.5
    )
    approx4(
        popularity["fA"], 0.3424,
        "fA: 2/2 users in the training folds -> Wilson 2/2",
    )
    approx(popularity["fB"], 0.0, "fB: 0/1 users liked it -> 0")
    check(
        "fC" not in popularity,
        "`random_neg` does not enter the counts — the food was never shown",
    )

    # Counting the TEST fold too would make fA 3/3 — distinctly higher. That
    # gap is exactly the leakage `ml/evaluate.py` has to remove.
    leaky = from_samples(
        users, foods, labels, sources, range(len(users)),
        positive_threshold=0.5,
    )
    approx4(
        leaky["fA"], 0.4385,
        "including the test fold pushes fA to 3/3",
    )
    check(
        leaky["fA"] > popularity["fA"],
        "including the test fold raises popularity — that is the leakage",
    )

    check(
        from_samples(
            users, foods, labels, sources, [], positive_threshold=0.5
        ) == {},
        "an empty training fold leaves no food with a score",
    )
    # One person eating the same food many times counts ONCE.
    repeats = from_samples(
        ["u1"] * 20, ["fA"] * 20, [0.9] * 20, ["diary"] * 20,
        range(20), positive_threshold=0.5,
    )
    approx4(
        repeats["fA"], 0.2065,
        "20 swipes from one person count as 1 person",
    )


# -- 11. Daily limits --------------------------------------------------


def check_daily_limits() -> None:
    print("11. Hard daily limits — ceilings, floors and what remains")

    # The scenario comes from the interface mock-up, and every number is a
    # real one in `nutrition_rec`. Keeping both places on the SAME numbers is
    # deliberate: if the formula changes, this check fails immediately rather
    # than letting the mock-up and the code drift apart silently.
    #
    #   eaten    Bánh cuốn nóng             sodium 807.9   purine  76.2
    #   planned  Cơm gạo lứt + giá đậu nành sodium  20.8   purine  96.0
    #            Canh chua chay             sodium 458.7   purine  55.9
    #            Cá chiên xù                sodium 464.0   purine   2.8
    #            Bắp cải luộc               sodium  56.0   purine  44.0
    sodium = DailyLimit(
        condition="Tăng huyết áp",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=807.9,
        planned=20.8 + 458.7 + 464.0 + 56.0,
    )
    approx(sodium.used, 1807.4, "sodium used = eaten + planned")
    approx(sodium.remaining, 192.6, "192.6 mg of sodium remains")
    check(not sodium.is_exceeded, "1807.4 / 2000 is not yet exceeded")
    approx4(sodium.ratio, 0.9037, "a usage ratio of 90.37%")

    purine = DailyLimit(
        condition="Gút",
        nutrient="purine_mg",
        comparator="lte",
        threshold=400.0,
        eaten=76.2,
        planned=96.0 + 55.9 + 2.8 + 44.0,
    )
    approx(purine.used, 274.9, "274.9 mg of purine used")
    approx(purine.remaining, 125.1, "125.1 mg of purine remains")

    # `fits` is what the interface calls for each candidate.
    check(
        not sodium.fits(1022.3),
        "Phở sốt vang at 1022.3 mg sodium does NOT fit the remaining 192.6 mg",
    )
    check(sodium.fits(14.0), "Đậu phụ hấp at 14 mg sodium does fit")
    check(
        sodium.fits(192.6),
        "exactly the remaining amount still fits (lte)",
    )
    check(
        not sodium.fits(192.7),
        "0.1 mg over the remainder does not fit — the boundary must be strict",
    )

    # Over the ceiling: `remaining` must NOT be clamped to 0, because the
    # interface needs to say by how much. Clamped to 0, the sentence
    # "222 mg over" cannot be written.
    exceeded = DailyLimit(
        condition="Tăng huyết áp",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=1500.0,
        planned=700.0,
    )
    check(exceeded.is_exceeded, "2200 / 2000 is exceeded")
    approx(
        exceeded.remaining, -200.0,
        "when exceeded, `remaining` goes negative rather than clamping to 0",
    )
    check(exceeded.ratio > 1.0, "a ratio over 100% is not clamped")

    # The two directions of a threshold are not symmetric. Asking the wrong
    # way must blow up rather than return a meaningless number — this is where
    # a floor added later would silently block foods if both shared one
    # subtraction.
    floor = DailyLimit(
        condition="Thiếu máu",
        nutrient="iron_mg",
        comparator="gte",
        threshold=18.0,
        eaten=5.0,
        planned=4.0,
    )
    check(not floor.is_ceiling, "`gte` is not a ceiling")
    approx(floor.shortfall, 9.0, "the iron floor: 9 mg short")
    check(not floor.is_exceeded, "a floor is never `exceeded`")
    check(floor.fits(999.0), "eating more never breaks a floor")
    raises(
        lambda: floor.remaining, ValueError,
        "asking a floor for `remaining` must blow up",
    )
    raises(
        lambda: sodium.shortfall, ValueError,
        "asking a ceiling for `shortfall` must blow up",
    )

    # Two conditions limiting the same nutrient: the TIGHTEST threshold must
    # win, not the first one encountered. Hypertension and kidney disease both
    # limit sodium.
    kidney = DailyLimit(
        condition="Bệnh thận",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=807.9,
        planned=1000.0,
    )
    status = DailyLimitStatus(
        user_id="u1",
        day=date(2026, 11, 7),
        limits=(sodium, purine, kidney),
    )
    check(not status.is_empty, "with limits present it is not empty")
    check(
        len(status.for_nutrient("sodium_mg")) == 2,
        "sodium has two limits in force",
    )
    tightest = status.tightest_limit("sodium_mg")
    check(
        tightest is not None and tightest.condition == "Bệnh thận",
        "takes the sodium limit with the least headroom "
        "(Bệnh thận: 192.1 < 192.6)",
    )
    check(
        status.tightest_limit("calcium_mg") is None,
        "an unlimited nutrient gives None",
    )
    check(
        DailyLimitStatus(user_id="u1", day=date(2026, 11, 7)).is_empty,
        "no limits means empty",
    )

    # `classify_foods` takes rows that have already passed F1, so the only
    # remaining reason to drop a food is today's limit — and that food is
    # STILL VALID ON ANOTHER DAY.
    today_status = DailyLimitStatus(
        user_id="u1", day=date(2026, 11, 7), limits=(sodium, purine)
    )
    candidates = [
        {"id": "f1", "name": "Phở sốt vang", "sodium_mg": 1022.3,
         "purine_mg": 12.4},
        {"id": "f2", "name": "Hủ tiếu sa tế", "sodium_mg": 990.0,
         "purine_mg": 15.0},
        {"id": "f3", "name": "Đậu phụ hấp", "sodium_mg": 14.0,
         "purine_mg": 136.0},
        {"id": "f4", "name": "Bắp cải luộc", "sodium_mg": 56.0,
         "purine_mg": 44.0},
    ]
    result = classify_foods(today_status, candidates)
    does_not_fit = result.does_not_fit
    check(
        set(does_not_fit) == {"f1", "f2", "f3"},
        "three foods do not fit; Bắp cải luộc does",
    )
    check(result.fits("f4"), "Bắp cải luộc fits both limits")
    approx(
        does_not_fit["f1"][0].excess, 1022.3 - 192.6,
        "Phở exceeds sodium by 829.7 mg",
    )
    check(
        does_not_fit["f1"][0].nutrient == "sodium_mg"
        and does_not_fit["f1"][0].condition == "Tăng huyết áp",
        "the reason names the right nutrient and the right condition",
    )

    # The most valuable item in this whole section. Đậu phụ hấp has 14 mg
    # sodium — the LOWEST of any candidate — but its 136 mg of purine exceeds
    # the gout patient's remaining 125.1 mg. A food can be excellent on the
    # nutrient that is short and still be blocked by another, so the interface
    # must not rank by one nutrient and conclude.
    check(
        [limit.nutrient for limit in does_not_fit["f3"]] == ["purine_mg"],
        "Đậu phụ hấp is blocked by PURINE, not by sodium",
    )
    approx(
        does_not_fit["f3"][0].excess, 136.0 - 125.1,
        "10.9 mg over on purine",
    )
    check(
        all(limit.nutrient == "sodium_mg" for limit in does_not_fit["f2"]),
        "Hủ tiếu sa tế only trips sodium; its 15 mg of purine is ample",
    )

    # A food missing a measurement for a limited nutrient must NOT be quietly
    # treated as fitting — but must not be treated as exceeding either. It is
    # simply undecidable. `purine_mg` is absent for 248 of 318 foods, so
    # folding the unknown group into the fitting group would make the purine
    # ceiling essentially unreachable.
    missing = classify_foods(today_status, [{"id": "f9", "name": "Món lạ"}])
    check(
        missing.does_not_fit == {},
        "a food with no measurement is not declared exceeding",
    )
    check(
        missing.undecidable == {"f9": ["sodium_mg", "purine_mg"]},
        "it goes into `undecidable`, naming both nutrients",
    )
    check(
        not missing.fits("f9"),
        "`fits()` must be False for an undecidable food",
    )

    # Tripping a KNOWN limit decides it immediately, even if another is absent.
    half_known = classify_foods(
        today_status, [{"id": "f8", "name": "Nửa số", "sodium_mg": 9999.0}]
    )
    check(
        set(half_known.does_not_fit) == {"f8"}
        and half_known.undecidable == {},
        "a certain exceedance is not filed as unknown",
    )

    no_limits = classify_foods(
        DailyLimitStatus("u1", date(2026, 11, 7)), candidates
    )
    check(
        no_limits.does_not_fit == {} and no_limits.undecidable == {},
        "with no limits in force, no food is dropped",
    )

    # -- The data-completeness flag --
    check(
        sodium.has_full_data,
        "every serving has sodium data -> complete data",
    )
    incomplete = DailyLimit(
        condition="Gút",
        nutrient="purine_mg",
        comparator="lte",
        threshold=400.0,
        eaten=38.1,
        planned=102.5,
        missing_eaten=1,
        missing_planned=3,
    )
    check(
        not incomplete.has_full_data,
        "a serving with missing data -> NOT complete data",
    )
    check(
        incomplete.n_missing_servings == 4,
        "all 4 servings with missing data are counted",
    )
    check(
        incomplete.remaining > 0,
        "the remainder is still computable, but it is HIGHER than reality — "
        "the `has_full_data` flag is the only thing that says so",
    )

    totals = NutrientTotals(
        totals={"purine_mg": 140.6}, missing={"purine_mg": 4}, n_servings=6
    )
    check(
        not totals.has_full_data("purine_mg"),
        "NutrientTotals reports the right nutrient as incomplete",
    )
    check(
        totals.has_full_data("sodium_mg"),
        "a nutrient with nothing missing is complete",
    )


# -- 12. F1 exclusion reasons ------------------------------------------


def check_exclusion_reasons() -> None:
    print("12. Classifying the reasons F1 excludes a food")

    def _reason(**overrides) -> ExclusionReason:
        base = dict(
            food_id="f1",
            name="Test dish",
            dish_role="main",
            rule_type="nutrient_limit",
            condition="Tăng huyết áp",
            severity_min="mild",
        )
        base.update(overrides)
        return ExclusionReason(**base)

    forbidden_tag = _reason(
        rule_type="exclude_tag", tag="Giàu purin", condition="Gút"
    )
    missing_tag = _reason(
        rule_type="require_tag", tag="Món chay", condition="Ăn chay"
    )
    check(forbidden_tag.kind == "tag", "a forbidden tag -> kind `tag`")
    check(missing_tag.kind == "tag", "a missing required tag -> kind `tag`")

    over = _reason(
        nutrient="sodium_mg", comparator="lte", threshold=500.0, value=879.4
    )
    check(
        over.kind == "serving_threshold",
        "over a per-serving threshold -> kind `serving_threshold`",
    )
    approx(over.excess, 379.4, "over a ceiling: measurement - threshold")

    under = _reason(
        nutrient="fiber_g", comparator="gte", threshold=5.0, value=1.2
    )
    check(
        under.kind == "serving_threshold",
        "under a floor is also `serving_threshold`",
    )
    approx(
        under.excess, 3.8,
        "under a floor: threshold - measurement, still positive",
    )

    # The most important distinction in this whole section. `allowed_foods`
    # excludes foods with missing data at a per-serving threshold, and telling
    # the user "this food exceeds the limit" when the truth is "we do not know"
    # is a false statement.
    no_data = _reason(
        nutrient="purine_mg", comparator="lte", threshold=150.0, value=None
    )
    check(
        no_data.missing_data,
        "a `nutrient_limit` with no measurement -> missing data",
    )
    check(
        no_data.kind == "missing_data",
        "its own kind, not folded into `serving_threshold`",
    )
    check(
        no_data.excess is None,
        "with no measurement it invents no excess amount",
    )

    # The trap: a tag rule also has an empty `value`, but it is NOT missing
    # data — it needs no measurement at all. Conflating the two would make the
    # 181 foods excluded by a tag look as if the system knew nothing about them.
    check(
        not forbidden_tag.missing_data,
        "a tag rule has an empty `value` but is NOT missing data",
    )
    check(
        forbidden_tag.excess is None,
        "a tag rule has no excess — and must not blow up when asked",
    )
    check(
        not missing_tag.missing_data,
        "`require_tag` likewise",
    )

    # The two layers go in opposite directions, and deliberately so: see the
    # `ExclusionReason.missing_data` docstring. This check is kept so that
    # anyone changing one side has to read the reason first.
    check(
        no_data.kind == "missing_data",
        "PER SERVING: missing data means EXCLUDE (the opposite of the PER DAY "
        "limit, where missing data adds 0 and raises a flag)",
    )

    # The fourth kind is not a rule at all: the user asked for this dish not
    # to be suggested. It is a hard filter like the three above — every ML
    # signal is soft, so a disliked dish would come back whenever its role ran
    # thin — but the interface must be able to tell it apart, because this one
    # is the only exclusion the user can lift.
    mine = _reason(
        rule_type=USER_BLOCKED_RULE, condition="", severity_min=""
    )
    check(mine.kind == "user_blocked", "a user's block -> kind `user_blocked`")
    check(
        mine.is_user_choice,
        "and it reports itself as the user's own choice",
    )
    check(
        mine.sentence == USER_BLOCKED_LABEL,
        "it carries a ready-made sentence, which no other kind has",
    )
    check(
        over.sentence is None and forbidden_tag.sentence is None,
        "a medical reason has none: it needs the condition and the numbers to "
        "say anything true, and assembling those is the interface's job",
    )
    check(
        not any(r.is_user_choice for r in (over, under, no_data, forbidden_tag,
                                           missing_tag)),
        "no medical reason claims to be the user's choice — offering to undo "
        "an allergy rule would invite the user to try",
    )
    check(
        not mine.missing_data and mine.excess is None,
        "it has no measurement and invents no excess, without blowing up",
    )
    check(
        not mine.is_citable,
        "and it cannot be cited: `I do not like it` is not a published source",
    )


# -- 13. Soft penalties ------------------------------------------------


def check_soft_penalty() -> None:
    print("13. Soft constraints — the multiplier, and how penalties combine")

    # Two NESTED bands of the same condition and the same nutrient. This is
    # the case where a plain multiplication would double-count.
    mild_band = SoftRule(
        condition="Tăng huyết áp",
        severity_min="mild",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=700.0,
        penalty=0.600,
        scope="per_serving",
    )
    severe_band = SoftRule(
        condition="Tăng huyết áp",
        severity_min="severe",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=500.0,
        penalty=0.400,
        scope="per_serving",
    )
    gout = SoftRule(
        condition="Gút",
        severity_min="mild",
        nutrient="purine_mg",
        comparator="lte",
        threshold=150.0,
        penalty=0.500,
        scope="per_serving",
    )

    # `penalty` is a MULTIPLIER. The evidence is in the data itself: the
    # severe row's note reads "a heavier penalty for the severe level" and its
    # value is 0.400 against the mild level's 0.600. Read as a subtraction,
    # 0.400 subtracts LESS, that is, the severe level is penalised more
    # lightly — the exact opposite of the note.
    check(
        severe_band.penalty < mild_band.penalty,
        "the severe level has the SMALLER coefficient",
    )

    one_group = penalty(
        {"sodium_mg": 800.0, "purine_mg": 10.0},
        [mild_band, severe_band, gout],
    )
    approx(
        one_group.factor,
        0.400,
        "800 mg of sodium breaches BOTH bands of one condition -> take the "
        "harshest, 0.400, rather than multiplying to 0.240",
    )
    check(
        len(one_group.violations) == 1,
        "one concern reports one violation, not two",
    )
    check(
        one_group.violations[0].threshold == 500.0,
        "the violation reported is the tighter band (500 mg), not the 700 mg one",
    )
    approx(
        one_group.violations[0].excess, 300.0,
        "the excess is against the reported band: 800 - 500",
    )

    two_groups = penalty(
        {"sodium_mg": 800.0, "purine_mg": 200.0},
        [mild_band, severe_band, gout],
    )
    approx(
        two_groups.factor, 0.200,
        "two different conditions MULTIPLY across groups: 0.4 x 0.5",
    )
    check(
        len(two_groups.violations) == 2,
        "two concerns report two violations",
    )
    check(
        [v.condition for v in two_groups.violations]
        == ["Tăng huyết áp", "Gút"],
        "violations are ordered harshest penalty first",
    )

    clean = penalty(
        {"sodium_mg": 100.0, "purine_mg": 10.0},
        [mild_band, severe_band, gout],
    )
    approx(clean.factor, 1.0, "breaching nothing gives a factor of 1.0")
    check(not clean.is_penalised, "a factor of 1.0 means no penalty")
    check(clean.violations == (), "no violations")
    approx(clean.apply(0.78), 0.78, "a factor of 1.0 leaves the score alone")
    approx(one_group.apply(0.78), 0.312, "a score of 0.78 x 0.400 = 0.312")

    # The boundary: exactly at the threshold is NOT a breach.
    at_boundary = penalty(
        {"sodium_mg": 700.0, "purine_mg": 150.0}, [mild_band, gout]
    )
    approx(
        at_boundary.factor, 1.0,
        "exactly at an `lte` threshold is not a breach",
    )
    just_over = penalty(
        {"sodium_mg": 700.01, "purine_mg": 10.0}, [mild_band, gout]
    )
    check(
        just_over.is_penalised,
        "0.01 mg over is a breach — the boundary must be strict",
    )

    # Missing data: NO penalty, but it must be recorded. A soft constraint is
    # a ranking decision, so lowering a food's score because the catalogue
    # lacks data penalises the wrong party.
    no_data = penalty(
        {"sodium_mg": None, "purine_mg": 10.0},
        [mild_band, severe_band, gout],
    )
    approx(no_data.factor, 1.0, "missing data means no penalty")
    check(
        no_data.missing_data == ("sodium_mg",),
        "but it records the nutrient it could not judge, once for both rules",
    )
    check(
        no_data.violations == (),
        "it invents no violation out of data that is not there",
    )

    # A `gte` threshold is a floor: being short is penalised, not being over.
    iron_floor = SoftRule(
        condition="Thiếu máu",
        severity_min="mild",
        nutrient="iron_mg",
        comparator="gte",
        threshold=4.0,
        penalty=0.800,
        scope="per_serving",
    )
    below = penalty({"iron_mg": 1.5}, [iron_floor])
    approx(below.factor, 0.800, "below the iron floor is penalised")
    approx(
        below.violations[0].excess, 2.5,
        "a floor's gap: threshold - measurement",
    )
    approx(
        penalty({"iron_mg": 9.0}, [iron_floor]).factor, 1.0,
        "above the floor is not penalised",
    )
    check(
        iron_floor.direction_word == "thiếu",
        "the word for a floor is `thiếu`",
    )
    check(
        mild_band.direction_word == "vượt",
        "the word for a ceiling is `vượt`",
    )

    # The wrong scope must BLOW UP rather than quietly compute a
    # plausible-looking number. Applying a `per_meal` rule per food is wrong in
    # both directions: it misses the case where the meal total is over while no
    # single food is, and it wrongly penalises a large food in a meal with
    # headroom to spare.
    per_meal = SoftRule(
        condition="Đái tháo đường",
        severity_min="mild",
        nutrient="carbs_g",
        comparator="lte",
        threshold=60.0,
        penalty=0.700,
        scope="per_meal",
    )
    per_day = SoftRule(
        condition="Đái tháo đường",
        severity_min="mild",
        nutrient="sugar_g",
        comparator="lte",
        threshold=25.0,
        penalty=0.600,
        scope="per_day",
    )
    raises(
        lambda: penalty({"carbs_g": 80.0}, [per_meal]), ValueError,
        "a per_meal rule must blow up",
    )
    raises(
        lambda: penalty({"sugar_g": 30.0}, [per_day]), ValueError,
        "a per_day rule must blow up",
    )

    # Routing by scope, and the rules with no enforcing layer yet.
    by_scope = soft_rules_by_scope([mild_band, gout, per_meal, per_day])
    check(len(by_scope["per_serving"]) == 2, "two per-serving rules")
    check(
        len(by_scope["per_meal"]) == 1 and len(by_scope["per_day"]) == 1,
        "one rule per remaining scope",
    )
    unenforced = unenforced_rules([mild_band, gout, per_meal, per_day])
    check(
        unenforced == [],
        f"every scope now has an enforcing layer, got "
        f"{[rule.scope for rule in unenforced]}",
    )
    check(
        all(ENFORCED_BY[scope] is not None for scope in ENFORCED_BY),
        "all three scopes have an owner",
    )
    # `per_meal` was the gap: stored in `condition_rules`, documented as
    # enforced, applied nowhere. Step 4 took it on, so the owner is named
    # here — the check stays, because a scope added later must not inherit
    # an owner it does not have.
    check(
        ENFORCED_BY["per_meal"] == "ml/scoring.meal_penalty",
        f"`per_meal` is owned by Step 4's meal penalty, got "
        f"{ENFORCED_BY['per_meal']!r}",
    )


# -- 14. Explanations in sentences -------------------------------------


def check_explanations() -> None:
    print("14. Recommendation explanations — sentences for users, not raw numbers")

    # A two-category space, to test both the fixed dimensions and the category
    # one-hot ones.
    foods = [
        _food(
            id="a", name="Canh A", category="Món canh", protein=20, carb=5,
            fat=2,
        ),
        _food(
            id="b", name="Cơm B", category="Cơm", protein=5, carb=60, fat=3
        ),
    ]
    space = FeatureSpace.from_foods(foods)

    # Every dimension must have a phrase. This check keeps a newly added
    # dimension from silently showing a technical label to users.
    check(
        dimensions_without_phrase(space) == [],
        f"every dimension has a phrase; missing: "
        f"{dimensions_without_phrase(space)}",
    )

    # An empty profile: there is no basis for saying what this person likes.
    empty = empty_profile(space)
    check(
        contributions(space, empty, foods[0]) == [],
        "an empty profile gives no contribution",
    )
    check(
        explanation_sentences(space, empty, foods[0]) == [],
        "and no sentence either",
    )
    check(
        debug_explanation(space, empty, foods[0])
        == "no preference profile yet",
        "the debug form says plainly that there is no profile yet",
    )

    profile = build_profile(
        space, [(foods[0], "like"), (foods[1], "dislike")]
    )
    parts = contributions(space, profile, foods[0])
    check(len(parts) > 0, "a liked food has positive contributions")

    # The category one-hot dimension builds its sentence from the category
    # name, needing no lookup table.
    category_parts = [
        p for p in parts if p.dimension.startswith(CATEGORY_PREFIX)
    ]
    check(
        len(category_parts) == 1,
        "exactly one category dimension contributes (one-hot)",
    )
    check(
        category_parts[0].sentence == "Bạn thích nhóm Món canh",
        f"the category sentence: got {category_parts[0].sentence!r}",
    )

    # A fixed dimension uses the lookup table.
    protein_parts = [p for p in parts if p.dimension == "Tỷ lệ đạm"]
    if protein_parts:
        check(
            protein_parts[0].sentence == "Bạn thường chọn món nhiều đạm",
            f"the protein sentence: got {protein_parts[0].sentence!r}",
        )

    # Descending order, and the share normalised to THAT food's own peak.
    check(
        all(a.value >= b.value for a, b in zip(parts, parts[1:])),
        "contributions are sorted descending",
    )
    approx(parts[0].share, 1.0, "the first contribution has a share of 1.0")
    check(
        all(0.0 < p.share <= 1.0 for p in parts),
        "every share lies within (0, 1]",
    )

    # Every dimension REPORTED must be positive. This is what makes the
    # sentences always take the "high X" direction: because every vector
    # dimension lies in [0, 1], the sign of `p_u[i]·v[i]` is the sign of
    # `p_u[i]`, and a positive contribution means this person leans towards a
    # HIGH value on that dimension.
    v = space.encode(foods[0])
    check(
        all(0.0 <= x <= 1.0 for x in v),
        "every vector dimension lies within [0, 1]",
    )
    check(
        all(p.value > 0 for p in parts),
        "every reported contribution is positive",
    )
    for part in parts:
        i = space.labels.index(part.dimension)
        check(
            profile.weights[i] > 0,
            f"{part.dimension}: a positive contribution implies a positive "
            f"profile weight, so the sentence must take the `high` direction, "
            f"never `low`",
        )

    # `count` limits the number of dimensions.
    check(
        len(contributions(space, profile, foods[0], count=1)) == 1,
        "`count=1` returns exactly one dimension",
    )
    check(
        len(contributions(space, profile, foods[0], count=99)) <= space.length,
        "a large `count` does not exceed the dimension count",
    )

    # The debug form and the interface form must rank IDENTICALLY — they share
    # `contributions`, and this check keeps anyone from reimplementing it.
    debug_text = debug_explanation(space, profile, foods[0])
    check(
        all(p.dimension in debug_text for p in parts),
        "the debug form names exactly the dimensions `contributions` picked",
    )
    check(
        debug_text.index(parts[0].dimension)
        < debug_text.index(parts[-1].dimension)
        or len(parts) == 1,
        "and in the same order",
    )
    sentences = explanation_sentences(space, profile, foods[0])
    check(
        sentences == [p.sentence for p in parts if p.sentence is not None],
        "the interface form only drops phraseless dimensions, keeping the order",
    )
    check(
        all("+" not in s and "0." not in s for s in sentences),
        "no sentence leaks a raw number to the interface",
    )

    # A dimension with no phrase yet: drop the line, do NOT show a technical
    # label.
    saved = PHRASE_BY_DIMENSION.pop("Tỷ lệ đạm")
    try:
        check(
            dimensions_without_phrase(space) == ["Tỷ lệ đạm"],
            "`dimensions_without_phrase` reports the forgotten dimension",
        )
        parts2 = contributions(space, profile, foods[0])
        forgotten = [p for p in parts2 if p.dimension == "Tỷ lệ đạm"]
        if forgotten:
            check(
                forgotten[0].sentence is None,
                "the forgotten dimension has an empty `sentence`",
            )
            check(
                "Tỷ lệ đạm"
                not in explanation_sentences(space, profile, foods[0]),
                "and does not reach the interface's sentence list",
            )
    finally:
        PHRASE_BY_DIMENSION["Tỷ lệ đạm"] = saved
    check(
        dimensions_without_phrase(space) == [],
        "the phrase table has been restored",
    )


# -- 15. Threshold evidence levels -------------------------------------


def check_evidence_levels() -> None:
    print("15. Threshold evidence levels — four levels, and which can cite a source")

    check(
        set(EVIDENCE_LEVELS) == set(EVIDENCE_LABELS),
        "every level has a Vietnamese label for the interface",
    )
    check(
        CITABLE_EVIDENCE == {"published"},
        "ONLY `published` may be cited as a sourced recommendation — "
        "`derived` carries assumptions so it may not, and `unsupported` has "
        "no source at all",
    )
    check(
        "definitional" not in CITABLE_EVIDENCE,
        "`definitional` cannot cite a source because it has no threshold — "
        '"an egg allergy excludes foods with egg" needs no WHO publication',
    )

    def _reason(level: str) -> ExclusionReason:
        return ExclusionReason(
            food_id="f",
            name="Food",
            dish_role="main",
            rule_type="nutrient_limit",
            condition="Tăng huyết áp",
            severity_min="mild",
            evidence_level=level,
        )

    check(
        _reason("published").is_citable,
        "a `published` threshold can cite a source",
    )
    check(not _reason("derived").is_citable, "a `derived` one cannot")
    check(
        not _reason("unsupported").is_citable, "an `unsupported` one cannot"
    )
    check(
        _reason("unsupported").evidence_label
        == "không có nguồn đang hiệu lực",
        f"the `unsupported` label: got "
        f"{_reason('unsupported').evidence_label!r}",
    )

    # The default must be a NON-citable level. Choosing `published` as the
    # default would make every rule added without declaring one claim to be
    # sourced.
    default = ExclusionReason(
        food_id="f", name="Food", dish_role="main",
        rule_type="nutrient_limit", condition="X", severity_min="mild",
    )
    check(
        not default.is_citable,
        f"the default `{default.evidence_level}` is NOT citable",
    )

    # An unknown level must not blow the function up, but must not be citable
    # either.
    unknown = _reason("some_unknown_level")
    check(not unknown.is_citable, "an unknown level cannot cite a source")
    check(
        unknown.evidence_label == "some_unknown_level",
        "an unknown level shows verbatim rather than blowing up",
    )

    # `SoftRule` and `DailyLimit` follow the same convention.
    soft = SoftRule(
        condition="Rối loạn mỡ máu", severity_min="mild",
        nutrient="cholesterol_mg", comparator="lte", threshold=300.0,
        penalty=0.700, scope="per_day", evidence_level="unsupported",
    )
    check(
        not soft.is_citable,
        "an `unsupported` SoftRule cannot cite a source",
    )
    daily = DailyLimit(
        condition="Tăng huyết áp", nutrient="sodium_mg", comparator="lte",
        threshold=2000.0, eaten=0.0, planned=0.0,
        evidence_level="published",
    )
    check(
        daily.is_citable, "a `published` DailyLimit can cite a source"
    )
    check(
        daily.evidence_label == soft.evidence_label.replace(
            "không có nguồn đang hiệu lực", "có nguồn công bố"
        ),
        "all three classes share one label table, with nobody reimplementing it",
    )


# -- 16. A user's own dish does not shape the space --------------------


def check_private_dish_scale() -> None:
    print("16. A user's own dish (§7.5.3) is encoded in the space, never shapes it")
    from ml.features import FeatureSpace

    catalogue = [
        _food(id="a", kcal=200, sodium=100.0),
        _food(id="b", kcal=600, sodium=900.0, category="Bún"),
    ]
    private = _food(
        id="p", kcal=4000, sodium=20000.0, category="Chỉ mình tôi có",
        owner_id="user-1",
    )

    alone = FeatureSpace.from_foods(catalogue)
    mixed = FeatureSpace.from_foods([*catalogue, private])

    check(mixed.params() == alone.params(),
          "the bounds and categories are the catalogue's, private dish or not")
    check(mixed.length == alone.length,
          "a category only a private dish uses adds no dimension "
          "(the active model's feature names stay valid)")
    check(mixed.encode(catalogue[0]) == alone.encode(catalogue[0]),
          "a catalogue dish encodes the same with or without the private one")

    v = mixed.encode(private)
    check(v[3] == 1.0 and v[5] == 1.0,
          "the private dish's out-of-range kcal and sodium clamp to 1")
    check(sum(v[8:]) == 0.0,
          "its unknown category leaves the one-hot block empty")
    check(FeatureSpace.from_foods([private]).length == 9,
          "a space of private dishes only is still buildable (no catalogue)")


def main() -> int:
    use_utf8()
    print("Machine-learning checks — pure functions, no database needed")
    print("=" * 62)
    for section in (
        check_rounding,
        check_feature_vector,
        check_cosine,
        check_rocchio,
        check_alpha,
        check_scoring,
        check_labels,
        check_metrics,
        check_popularity,
        check_daily_limits,
        check_exclusion_reasons,
        check_soft_penalty,
        check_explanations,
        check_evidence_levels,
        check_private_dish_scale,
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
