#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model serving — scoring candidates for a real user.

This is task 6 of `ML_PIPELINE.md` section 12, and the place where **the four
stages meet**. The stage is chosen by how many signals the user has given,
not by which model happens to exist:

| `n_signals` | Stage | Scored by | `generation_source` |
|---|---|---|---|
| 0 | `cold` | popularity + macro fit | `rule_based` |
| 1-29 | `content` | `(1 + cos(p_u, v_i)) / 2` | `content_based` |
| 30-100 | `hybrid` | `alpha*ML + (1-alpha)*cosine` | `hybrid` |
| > 100 | `ml` | the global model | `ml` |

**The F1 filter runs first, always.** It is the safety layer, not an
optimisation step: a food violating a hard constraint must be removed even if
the model scores it highest. So it sits outside and before all scoring, not
as a score penalty.

**Degradation is announced.** If the stage calls for a model and none is
`is_active = 1`, or the active model belongs to a different feature version,
the system falls back to a lower stage and **says so**. Silently returning
the neutral score would still produce a plan that looks normal, and nobody
would know when the machine learning part stopped working.

**Three checks before a model is used**, because all three fail silently if
unchecked:

1.  The model's `feature_version` must equal the code's — a mismatch means
    the model is loaded against an entirely different vector.
2.  The `feature_names` stored in the model file must match the list built
    from the current space — new foods can create a new category, which
    lengthens the vector, and `StandardScaler` would then receive the wrong
    number of columns.
3.  The preference vector in `user_preference_profiles` must have the right
    length — a profile from before a dimension was added is shorter.

Run:
    python -m ml.serve --user <id>            # the top 20 recommendations
    python -m ml.serve --user <id> --explain
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np

from . import scoring
from .dataset import UserProfile, build_feature_row, feature_names, load_user_profiles
from .db import connect, use_utf8
from .f1_filter import allowed_foods
from .features import FEATURE_VERSION, FeatureSpace, Food, load_foods
from .rocchio import (
    PreferenceProfile,
    alpha,
    build_profile,
    empty_profile,
    stage as stage_for,
)

ROOT = Path(__file__).resolve().parent.parent

#: The `meal_plans.generation_source` matching each stage.
SOURCE_BY_STAGE = {
    "cold": "rule_based",
    "content": "content_based",
    "hybrid": "hybrid",
    "ml": "ml",
}


# ── The model currently serving ───────────────────────────────────────


@dataclass
class ServingModel:
    model_id: int
    version: str
    algorithm: str
    scaler: Any
    model: Any
    feature_names: list[str]

    def score(self, rows: Sequence[Sequence[float]]) -> np.ndarray:
        """The probability of the "liked" class — a preference score in [0, 1].

        `predict_proba`, not `predict`: `predict` returns 0 or 1, so every
        "liked" food would tie and Step 4 would have nothing left to rank by.
        """
        X = self.scaler.transform(np.asarray(rows, dtype=float))
        return self.model.predict_proba(X)[:, 1]


def load_active_model(
    cn, space: FeatureSpace
) -> tuple[ServingModel | None, str | None]:
    """Load the `is_active = 1` model. Returns `(model, why not)`.

    Returns the reason as a string rather than raising, because having no
    model **is a valid state** of the system: Stages 0 and 1 run without one.
    Raising here would take down the meal-plan path for users who never
    needed a model in the first place.
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id, version, algorithm, feature_version, artifact_path "
            "FROM ml_models WHERE is_active = 1"
        )
        rows = cur.fetchall()

    if not rows:
        return None, "no model has is_active = 1"
    if len(rows) > 1:
        # `is_active` has no uniqueness constraint at the schema level, so
        # this can happen if someone updates it by hand. Refuse to pick
        # arbitrarily: an arbitrary choice is not reproducible.
        names = ", ".join(d["version"] for d in rows)
        return None, f"{len(rows)} models share is_active = 1 ({names})"

    d = rows[0]
    if d["feature_version"] != FEATURE_VERSION:
        return None, (
            f"model {d['version']!r} belongs to feature version "
            f"{d['feature_version']!r}, the code is at {FEATURE_VERSION!r}"
        )

    path = ROOT / d["artifact_path"]
    if not path.exists():
        return None, f"model file {d['artifact_path']} is missing"

    payload = joblib.load(path)
    current_names = feature_names(space)
    if list(payload.get("feature_names", [])) != current_names:
        return None, (
            f"model {d['version']!r} was trained on "
            f"{len(payload.get('feature_names', []))} features, the current "
            f"space has {len(current_names)} — the food catalogue changed, "
            f"it must be retrained"
        )

    return (
        ServingModel(
            model_id=int(d["id"]),
            version=d["version"],
            algorithm=d["algorithm"],
            scaler=payload["scaler"],
            model=payload["model"],
            feature_names=current_names,
        ),
        None,
    )


# ── The current preference profile ────────────────────────────────────


def load_preference_profile(
    cn, user_id: str, space: FeatureSpace
) -> tuple[PreferenceProfile, str | None]:
    """Read `user_preference_profiles`. Returns `(profile, warning)`.

    This uses the **current** vector, not a snapshot — and that is correct.
    A snapshot is only needed when *building the training set*, where using
    the current vector would be leakage because it has already been updated
    by the very signal serving as the label. At inference there is no label
    to leak into: the current vector is everything the system knows about
    this person.
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT feature_version, weights, sum_abs_weight, n_signals, stage "
            "FROM user_preference_profiles WHERE user_id = %s",
            (user_id,),
        )
        d = cur.fetchone()

    if d is None:
        return empty_profile(space), None

    if d["feature_version"] != FEATURE_VERSION:
        return empty_profile(space), (
            f"the preference profile belongs to feature version "
            f"{d['feature_version']!r}; ignoring it and falling back to Stage 0"
        )

    weights = json.loads(d["weights"])
    if isinstance(weights, dict):
        weights = weights.get("weights", [])
    if len(weights) != space.length:
        return empty_profile(space), (
            f"the preference profile has {len(weights)} dimensions but the "
            f"current space has {space.length}; ignoring it and falling back "
            f"to Stage 0"
        )

    return (
        PreferenceProfile(
            weights=tuple(float(x) for x in weights),
            sum_abs_weight=float(d["sum_abs_weight"]),
            n_signals=int(d["n_signals"]),
        ),
        None,
    )


# ── Recommending ──────────────────────────────────────────────────────


@dataclass
class Candidate:
    food: Food
    score: float
    #: Each component's score, kept so the recommendation can be explained.
    #: Not used for ranking.
    content_score: float
    rule_score: float
    ml_score: float | None


@dataclass
class Recommendation:
    user_id: str
    stage: str
    generation_source: str
    n_signals: int
    alpha: float
    model_id: int | None
    model_version: str | None
    n_foods_before_f1: int
    n_foods_after_f1: int
    candidates: list[Candidate]
    #: Everything that had to be degraded or skipped. Empty is good.
    warnings: list[str] = field(default_factory=list)


def recommend(
    cn,
    user_id: str,
    *,
    limit: int = 20,
    exclude_foods: Sequence[str] = (),
    only_candidates: Sequence[str] | None = None,
) -> Recommendation:
    """Score and rank candidates for one user.

    `exclude_foods` are the foods already used today — Step 4 passes them in
    so a plan does not repeat a dish. Excluded here rather than left for
    Step 4 to drop, so that `limit` returns exactly that many usable foods.

    `only_candidates` restricts scoring to that list, for `POST /predict`:
    the backend already has its own candidate set and only needs scores. **The
    F1 filter still runs first** and still trims that list — a food the
    backend sent that this person must not eat receives no score at all,
    rather than a low one. Running F1 afterwards, or skipping it once a list
    is supplied, would turn the safety layer into a ranking preference, which
    is exactly what section 4 of `ML_PIPELINE.md` forbids.
    """
    foods, _ = load_foods(cn)
    space = FeatureSpace.from_foods(foods)
    foods_by_id = {f.id: f for f in foods}

    warnings: list[str] = []

    # ── Step F1: the safety layer, before any scoring ──
    safe = allowed_foods(cn, user_id=user_id)
    excluded = set(exclude_foods)
    keep = None if only_candidates is None else set(only_candidates)
    candidate_foods = [
        foods_by_id[d["id"]]
        for d in safe
        if d["id"] in foods_by_id
        and d["id"] not in excluded
        and (keep is None or d["id"] in keep)
    ]

    # ── Profile and stage ──
    profile, warning = load_preference_profile(cn, user_id, space)
    if warning:
        warnings.append(warning)

    n = profile.n_signals
    stage = stage_for(n)
    a = alpha(n)

    model: ServingModel | None = None
    if stage in ("hybrid", "ml"):
        model, reason = load_active_model(cn, space)
        if model is None:
            warnings.append(
                f"Stage {stage} needs a model but {reason} — falling back to "
                f"Stage 1 (content_based)."
            )
            stage = "content"
            a = 0.0

    health = load_user_profiles(cn).get(user_id)
    if health is None:
        health = UserProfile(is_default=True)
        warnings.append(
            "The user has no health_profiles row — the user feature block "
            "and the macro fit are running on defaults."
        )

    # ── Scoring ──
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id, popularity_score FROM foods WHERE owner_id IS NULL "
            "OR owner_id = %s",
            (user_id,),
        )
        popularity = {d["id"]: float(d["popularity_score"]) for d in cur.fetchall()}

    ml_scores: np.ndarray | None = None
    if model is not None and candidate_foods:
        names = feature_names(space)
        rows = [
            build_feature_row(
                health,
                profile.weights,
                space.encode(food),
                popularity.get(food.id, 0.0),
                expected_length=len(names),
            )
            for food in candidate_foods
        ]
        ml_scores = model.score(rows)

    candidates: list[Candidate] = []
    for i, food in enumerate(candidate_foods):
        vector = space.encode(food)
        rule = scoring.rule_score(
            vector, health.target_macro, popularity.get(food.id, 0.0)
        )
        content = scoring.content_score(profile.weights, vector)
        ml = float(ml_scores[i]) if ml_scores is not None else None

        if stage == "cold":
            total = rule
        elif stage == "content":
            total = content
        elif stage == "hybrid":
            total = scoring.blend(ml or scoring.NEUTRAL_SCORE, content, n)
        else:
            total = ml if ml is not None else content

        candidates.append(Candidate(food, total, content, rule, ml))

    # Ties break on food name so the result is reproducible — at Stage 0,
    # with `popularity_score` all zero, ties are extremely common.
    candidates.sort(key=lambda c: (-c.score, c.food.name, c.food.id))

    return Recommendation(
        user_id=user_id,
        stage=stage,
        generation_source=SOURCE_BY_STAGE[stage],
        n_signals=n,
        alpha=a,
        model_id=model.model_id if model else None,
        model_version=model.version if model else None,
        n_foods_before_f1=len(foods),
        n_foods_after_f1=len(candidate_foods),
        candidates=candidates[:limit],
        warnings=warnings,
    )


# ── Explaining in sentences, not numbers ──────────────────────────────
#
# `debug_explanation` returns `"Tỷ lệ đạm (+0.182), Nhóm: Món canh (+0.061)"`.
# The dimension labels are already readable Vietnamese, but `+0.182` means
# nothing to a user: it is one term in the numerator of a cosine, not a
# percentage, with no unit, and its magnitude depends on both the profile and
# the food.
#
# **The order is the information.** So the code below keeps the order and the
# RELATIVE share against the largest contribution, and drops the absolute
# value from what is displayed.
#
# ## Why only positive dimensions, and why the sentence is always "more X"
#
# Every dimension of a food vector lies in [0, 1] —
# `food_vector_parity_test.dart` asserts it and `FeatureSpace._normalize`
# clamps it. So `v[i] >= 0` always, and the sign of `p_u[i]*v[i]` is the sign
# of `p_u[i]`.
#
# It follows that a POSITIVE contribution means `p_u[i] > 0`, that is, the
# foods this person likes score high on that dimension. The sentence is
# therefore always in the "more X" direction, never "less X" — "you lean
# toward less sweet food" corresponds to a NEGATIVE `p_u`, and such a
# contribution is negative and has already been filtered out of this list.

#: Dimension label -> a phrase describing the food, to build the sentence
#: "Bạn thường chọn món ...". **Vietnamese on purpose**: this is end-user
#: product text, shown in a Vietnamese app.
#:
#: A missing label here does NOT raise — the interface still runs, that
#: dimension simply has no sentence. But `dimensions_without_phrase` reports
#: it and `tools/check_ml.py` calls that, so a newly added dimension with no
#: phrase fails a check instead of silently showing a technical label to a
#: user.
PHRASE_BY_DIMENSION: dict[str, str] = {
    "Tỷ lệ đạm": "nhiều đạm",
    "Tỷ lệ bột đường": "nhiều bột đường",
    "Tỷ lệ béo": "nhiều chất béo",
    "Năng lượng": "nhiều năng lượng",
    "Vị ngọt": "có vị ngọt",
    "Vị mặn": "đậm vị mặn",
    "Chất xơ": "nhiều chất xơ",
    "Mức cay": "có vị cay",
}

#: The prefix `FeatureSpace.labels` puts on the category one-hot dimensions.
CATEGORY_PREFIX = "Nhóm: "


@dataclass(frozen=True)
class Contribution:
    """One dimension's contribution to a food's taste-match score."""

    #: The dimension's technical label, kept for debugging — NOT shown to
    #: users.
    dimension: str
    #: `p_u[i] * v_i[i]`. Kept for testing and debugging, not displayed.
    value: float
    #: Relative to the largest contribution **of this same food**, in (0, 1].
    #:
    #: This is what gets drawn as a comparison bar, but it only describes the
    #: order WITHIN one food; it does NOT say how strongly that food matches
    #: the taste at all. Banana — a food this user swiped `dislike` — yields
    #: three shares of 100% / 91% / 88% while the absolute contribution is
    #: merely +0.0093: normalising against its own peak means a very weak
    #: match still produces three nearly full bars.
    #:
    #: The interface therefore **must** show the overall match score
    #: (`scoring.content_score`) beside them. Drawing these bars alone tells
    #: the user that every food matches equally strongly.
    share: float
    #: The sentence for the user. `None` when the dimension has no phrase —
    #: the interface skips that line rather than showing a technical label.
    sentence: str | None


def _sentence_for(label: str) -> str | None:
    if label.startswith(CATEGORY_PREFIX):
        return f"Bạn thích nhóm {label[len(CATEGORY_PREFIX):]}"
    phrase = PHRASE_BY_DIMENSION.get(label)
    return None if phrase is None else f"Bạn thường chọn món {phrase}"


def dimensions_without_phrase(space: FeatureSpace) -> list[str]:
    """Dimensions that have no user-facing sentence.

    Category dimensions always have one because it is built from the category
    name, so this list only contains fixed dimensions forgotten in
    `PHRASE_BY_DIMENSION`.
    """
    return [label for label in space.labels if _sentence_for(label) is None]


def contributions(
    space: FeatureSpace,
    profile: PreferenceProfile,
    food: Food,
    count: int = 3,
) -> list[Contribution]:
    """The `count` dimensions contributing most to `food`'s taste match.

    Only **positive** dimensions: a negative one means the food loses points
    there, which is not a reason it was recommended. An empty profile returns
    an empty list — there is no basis for saying what this person likes.
    """
    if profile.is_empty:
        return []

    vector = space.encode(food)
    top = sorted(
        (
            (p * x, label)
            for p, x, label in zip(profile.weights, vector, space.labels)
            if p * x > 0
        ),
        key=lambda t: -t[0],
    )[:count]
    if not top:
        return []

    largest = top[0][0]
    return [
        Contribution(
            dimension=label,
            value=value,
            share=value / largest,
            sentence=_sentence_for(label),
        )
        for value, label in top
    ]


def explanation_sentences(
    space: FeatureSpace,
    profile: PreferenceProfile,
    food: Food,
    count: int = 3,
) -> list[str]:
    """The explanation sentences, with phrase-less dimensions dropped. For
    the interface."""
    return [
        c.sentence
        for c in contributions(space, profile, food, count)
        if c.sentence is not None
    ]


def debug_explanation(
    space: FeatureSpace, profile: PreferenceProfile, food: Food, count: int = 3
) -> str:
    """The **debugging** form of the explanation — technical labels and raw
    numbers.

    For the command line and for troubleshooting, NOT for the interface:
    `+0.182` is one term in the numerator of a cosine and means nothing to a
    user. The interface calls `explanation_sentences` or `contributions`.

    The ordering and the positive-dimension filter live in `contributions`;
    this function only reformats — otherwise the two could rank differently.
    """
    if profile.is_empty:
        return "no preference profile yet"
    top = contributions(space, profile, food, count)
    if not top:
        return "no dimension contributes positively"
    return ", ".join(f"{c.dimension} ({c.value:+.3f})" for c in top)


# ── Rebuilding the preference profile from swipe history ──────────────


def rebuild_profile(cn, user_id: str, *, write: bool = True) -> PreferenceProfile:
    """Recompute `user_preference_profiles` from `interactions`, then store it.

    Serves `POST /profiles/{userId}/rebuild`. Called after onboarding
    completes, and **required** again whenever the user declares a new
    condition or changes diet.

    ## F1 has to run again here, even though it ran at import time

    The swipes in `interactions` were already F1-filtered once —
    `import_swipes.py` does not write rows that violate a hard constraint.
    But constraints **change over time**: someone who declares "Ăn thuần
    chay" six months after the survey still has their `like` swipes on meat
    dishes sitting in `interactions`, and rebuilding without filtering would
    keep their vector saying "likes meat" while F1 blocks every meat dish —
    the system contradicting itself.

    Measured on the simulated set: filtering with F1 before building the
    vector moves `cos(p_u, t_u)` from 0.119 to 0.666 across the 21 users with
    constraints. See `tools/check_mo_phong.py` check 7.

    ## Chronological order

    Read by ascending `interacted_at`. Rocchio is a signed mean so the order
    does **not** change the result, but it does change `profile_snapshot`
    when the training set is built, and reading in the same order in both
    places is the cheapest way to keep the two from drifting.
    """
    foods, _ = load_foods(cn)
    space = FeatureSpace.from_foods(foods)
    foods_by_id = {f.id: f for f in foods}

    # The foods F1 permits, under the user's CURRENT conditions.
    permitted = {d["id"] for d in allowed_foods(cn, user_id=user_id)}

    with cn.cursor() as cur:
        cur.execute(
            "SELECT food_id, action FROM interactions WHERE user_id = %s "
            "ORDER BY interacted_at, id",
            (user_id,),
        )
        swipes = [
            (foods_by_id[d["food_id"]], d["action"])
            for d in cur.fetchall()
            if d["food_id"] in foods_by_id and d["food_id"] in permitted
        ]

    profile = build_profile(space, swipes)
    if not write:
        return profile

    with cn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_preference_profiles (user_id, feature_version, "
            "weights, sum_abs_weight, n_signals, stage, alpha) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE feature_version = VALUES(feature_version), "
            "weights = VALUES(weights), sum_abs_weight = VALUES(sum_abs_weight), "
            "n_signals = VALUES(n_signals), stage = VALUES(stage), "
            "alpha = VALUES(alpha)",
            (
                user_id,
                FEATURE_VERSION,
                json.dumps(list(profile.weights)),
                profile.sum_abs_weight,
                profile.n_signals,
                stage_for(profile.n_signals),
                round(alpha(profile.n_signals), 3),
            ),
        )
    cn.commit()
    return profile


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="`users.id`")
    parser.add_argument("--db", default=None)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="list each food's contributing dimensions",
    )
    t = parser.parse_args(argv)

    cn = connect(t.db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT display_name FROM users WHERE id = %s", (t.user,))
            user_row = cur.fetchone()
        if user_row is None:
            print(f"No user has id = {t.user!r}.", file=sys.stderr)
            return 1

        result = recommend(cn, t.user, limit=t.top)

        print(f"User: {user_row['display_name']}  ({t.user})")
        print(
            f"Stage {result.stage} - generation_source = "
            f"{result.generation_source} - n_signals = {result.n_signals} - "
            f"alpha = {result.alpha:.3f}"
        )
        print(
            "Model: "
            + (
                f"{result.model_version} (id={result.model_id})"
                if result.model_version
                else "none used"
            )
        )
        print(
            f"F1 filter: {result.n_foods_before_f1} foods -> "
            f"{result.n_foods_after_f1} safe"
        )
        for warning in result.warnings:
            print(f"  ! {warning}")
        print()

        if not result.candidates:
            print("No food left after the F1 filter.")
            return 0

        space = None
        profile = None
        if t.explain:
            foods, _ = load_foods(cn)
            space = FeatureSpace.from_foods(foods)
            profile, _ = load_preference_profile(cn, t.user, space)

        print(f"{'#':>3}  {'score':>6}  {'content':>9}  {'ML':>6}  food")
        for i, candidate in enumerate(result.candidates, start=1):
            ml = (
                f"{candidate.ml_score:.3f}"
                if candidate.ml_score is not None
                else "-"
            )
            print(
                f"{i:>3}  {candidate.score:>6.3f}  "
                f"{candidate.content_score:>9.3f}  "
                f"{ml:>6}  {candidate.food.name}  [{candidate.food.category}]"
            )
            if t.explain and space is not None and profile is not None:
                print(
                    f"       because: "
                    f"{debug_explanation(space, profile, candidate.food)}"
                )
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
