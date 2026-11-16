# -*- coding: utf-8 -*-
"""Build the global model's feature matrix from `ml_training_samples`.

`ML_PIPELINE.md` section 6 describes the Stage 2 input as

        x = [ user features  (+)  food features  (+)  cross features ]

This file realises those three blocks, and the most interesting part is the
third one.

**Why the cross block decides everything.** The model is **one model for
everybody**, not one model per person. If the input were only the user block
plus the food block, a linear model could learn "people with a high BMI like
low-fat food" but **not** "*this* person likes low-fat food" — personalisation
would have nowhere to live. The cross block is that place:

    cos(p_u, v_i)      — one number: how close this food is to this taste
    p_u (*) v_i        — twenty numbers: close along **which** dimensions

The elementwise product `p_u (*) v_i` is what lets a linear model learn that
for someone who leans spicy the food's "spice" dimension should add to the
score, while for someone who avoids spice the same dimension should subtract.
`cos` alone compresses all twenty dimensions into one number and loses that.

`p_u` **always comes from `profile_snapshot`** — the vector at the time the
signal was collected, not the current one. Using the current vector is data
leakage; see `ML_PIPELINE.md` section 9.4.

**A known limitation, to be stated in the report.** The user block comes from
the **current** `health_profiles`, because the schema stores no history of
health profiles. If someone loses 8 kg while using the app, their older
samples get tagged with the new weight. This is a mild, one-directional leak:
it carries no information about any individual sample's *label*, so it does
not inflate results the way a current `p_u` would. The right fix is a history
table, not another guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from .features import FeatureSpace, Food, cosine_similarity

GENDERS = ("male", "female", "other")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
GOALS = ("lose_weight", "maintain", "gain_weight", "healthy_eating")

#: The BMI range used for normalisation. 15-40 because that is the range
#: where the WHO Asian classification still means something; outside it the
#: value is clamped.
BMI_LOW, BMI_HIGH = 15.0, 40.0


@dataclass
class UserProfile:
    """The user feature block, reduced to numbers."""

    gender: str = "other"
    age: int = 30
    bmi: float = 22.0
    activity_level: str = "moderate"
    goal: str = "maintain"
    #: Target share of energy from protein / carbohydrate / fat, as
    #: percentages. The default 15-60-25 matches `health_profiles`.
    target_macro: tuple[float, float, float] = (15.0, 60.0, 25.0)
    #: `True` when this person has **no** `health_profiles` row and the whole
    #: block is on defaults. Counted so it can be reported, rather than
    #: quietly treated as real.
    is_default: bool = False


def _clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if x < low else high if x > high else x


def load_user_profiles(cn) -> dict[str, UserProfile]:
    """Read `health_profiles`, deriving age from `date_of_birth`.

    Storing `date_of_birth` rather than an age is the schema's right call —
    an age is wrong a year later — but it means age has to be computed here,
    and computed against **today**, not against the date the signal was
    collected. Over a project of a few months the error is under one year;
    recorded here so nobody assumes it was handled.
    """
    sql = """
        SELECT user_id, gender, date_of_birth, bmi, activity_level, goal,
               target_protein_pct, target_carbs_pct, target_fat_pct
        FROM health_profiles
    """
    today = date.today()
    result: dict[str, UserProfile] = {}
    with cn.cursor() as cur:
        cur.execute(sql)
        for d in cur.fetchall():
            dob = d["date_of_birth"]
            age = (
                today.year
                - dob.year
                - ((today.month, today.day) < (dob.month, dob.day))
            )
            result[d["user_id"]] = UserProfile(
                gender=d["gender"],
                age=age,
                bmi=float(d["bmi"]) if d["bmi"] is not None else 22.0,
                activity_level=d["activity_level"],
                goal=d["goal"],
                target_macro=(
                    float(d["target_protein_pct"]),
                    float(d["target_carbs_pct"]),
                    float(d["target_fat_pct"]),
                ),
            )
    return result


def _user_block(profile: UserProfile) -> list[float]:
    """The user profile block. **No** `n_signals` — see the note below.

    ## Why `user.n_signals` was dropped from the feature matrix

    Two reasons, and the first one is sufficient on its own.

    **1. It cannot rank anything.** At scoring time every candidate food for
    the same user carries the **same** `n_signals`. A feature constant across
    the whole candidate set adds the same amount to every score, so the order
    does not change — it cannot affect a recommendation, however large its
    coefficient. `n_signals` has a real job elsewhere: `ml/scoring.py` uses it
    as the blend coefficient alpha. That is where it belongs.

    **2. In the training set it is an IDENTIFIER OF THE SAMPLE SOURCE.**
    `ml/build_dataset.py` stamps each `random_neg` sample with that user's
    `latest_signal_at` — the time of their **last** signal — so its profile
    snapshot is always the fully-populated profile, while `swipe` samples
    carry a running count. Measured over the 50 simulated users:

        source        n_signals (min/avg/max)   label
        random_neg        34 / 39.1 / 43        0.100  (constant)
        swipe              0 / 19.1 / 42        0.535

    At `n_signals >= 38` between 85% and 100% of samples are `random_neg`; at
    `<= 22` none are. The model therefore learns to **recognise the synthetic
    negatives** and predict 0.1 for them, instead of learning taste — and
    that is exactly what happened: before this feature was dropped,
    `user.n_signals` was the **strongest** feature in all three algorithms
    (coefficient -0.714 in logistic regression; importance 0.182 and 0.313 in
    the two tree models). Any score gained from it does not transfer to
    serving, where there are no synthetic negatives to recognise.

    The remaining `user.*` features are constant per user too, so they cannot
    rank on their own either — but they are here to **interact** with the
    food features (a tree model can learn "high-BMI users get high-fat foods
    pushed down"), and their variation is real variation between people.
    `n_signals` is different: it varies **within one person**, and that
    variation is produced by how the dataset is built, not by the data.
    """
    v: list[float] = [0.0] * len(GENDERS)
    if profile.gender in GENDERS:
        v[GENDERS.index(profile.gender)] = 1.0
    v.append(_clamp(profile.age / 100))
    v.append(_clamp((profile.bmi - BMI_LOW) / (BMI_HIGH - BMI_LOW)))
    v.append(ACTIVITY_LEVELS.index(profile.activity_level) / (len(ACTIVITY_LEVELS) - 1))
    goal_block = [0.0] * len(GOALS)
    if profile.goal in GOALS:
        goal_block[GOALS.index(profile.goal)] = 1.0
    v += goal_block
    return v


def user_block_names() -> list[str]:
    return (
        [f"user.gender={g}" for g in GENDERS]
        + ["user.age", "user.bmi", "user.activity"]
        + [f"user.goal={g}" for g in GOALS]
    )


def feature_names(space: FeatureSpace) -> list[str]:
    """The name of every input column, in the order `build_feature_row` emits.

    These two lists **must** travel together: `feature_importance` attaches
    names to columns by position, so one place out of step makes the whole
    importance table read plausibly under wrong names.
    `build_feature_row` checks this on every call.
    """
    return (
        user_block_names()
        + [f"food.{label}" for label in space.labels]
        + ["food.popularity"]
        + ["cross.cos"]
        + [f"cross.prod.{label}" for label in space.labels]
    )


def build_feature_row(
    profile: UserProfile,
    p_u: Sequence[float],
    food_vector: Sequence[float],
    popularity: float,
    *,
    expected_length: int | None = None,
) -> list[float]:
    """Join the three blocks into **one** model input row.

    This function is the only place that knows the column order, and it is
    called from **two** places: `load_feature_set` when building the training
    set, and `ml/serve.py` when scoring for a real user. If each joined its
    own, the model would be trained on one column order and infer on another
    — the same class of bug as the Dart and Python feature extractors
    drifting apart, and just as silent: the matrix still has the right number
    of columns and the model still returns a probability.
    """
    row = (
        _user_block(profile)
        + list(food_vector)
        + [popularity]
        + [cosine_similarity(p_u, food_vector)]
        + [a * b for a, b in zip(p_u, food_vector)]
    )
    if expected_length is not None and len(row) != expected_length:
        raise AssertionError(
            f"Built {len(row)} features but expected {expected_length} — the "
            f"two lists must match, otherwise `feature_importance` attaches "
            f"the wrong names to the wrong columns."
        )
    return row


@dataclass
class FeatureSet:
    """The feature matrix plus everything needed to train and evaluate."""

    X: list[list[float]]
    y: list[float]
    #: Binary label `label >= 0.5`, used for f1 / auc and by classifiers.
    y_class: list[int]
    sample_weight: list[float]
    user_id: list[str]
    food_id: list[str]
    source: list[str]
    fold: list[int]
    #: The role in the **reference split** that `build_dataset` recorded:
    #: `train` / `val` / `test`. Cross-validation ignores this column and
    #: rotates `fold` instead.
    split: list[str]
    #: The preference vector **at the time the signal was collected**, taken
    #: from `profile_snapshot`. The `content_based` baseline scores with it
    #: directly, so it has to surface here rather than only inside the cross
    #: block.
    p_u: list[list[float]]
    #: The snapshot's `n_signals` — the input to the blend coefficient alpha.
    n_signals: list[int]
    #: The food feature vector, kept separately so `content_based` can reuse
    #: it.
    food_vector: list[list[float]]
    #: `foods.popularity_score` — used by the `popularity` baseline.
    popularity: list[float]
    #: The user's target macro split — used by `rule_based`.
    target_macro: list[tuple[float, float, float]]
    feature_names: list[str]
    #: How many samples fall back to a default health profile because the
    #: person never filled one in.
    n_default_profiles: int = 0
    #: How many samples have an empty `profile_snapshot` (no earlier swipe).
    n_empty_snapshots: int = 0

    def __len__(self) -> int:
        return len(self.y)


#: The threshold separating "liked" from "not liked" when a binary label is
#: needed.
#:
#: Set at 0.5 rather than at the midpoint of the observed label range,
#: because 0.5 is the **meaningful neutral point**: a `neutral` swipe carries
#: exactly label 0.500, and so does a 3-star rating. Anything above leans
#: toward liking.
#:
#: `>=` rather than `>`: label 0.500 counts as liked. That is a choice, not a
#: fact — and it has to be consistent between training and evaluation, so
#: this constant is the only place it is defined.
LIKE_THRESHOLD = 0.5


def load_feature_set(
    cn,
    *,
    dataset_version: str,
    space: FeatureSpace,
    foods_by_id: dict[str, Food],
) -> FeatureSet:
    """Build a `FeatureSet` from one dataset version."""
    sql = """
        SELECT s.user_id, s.food_id, s.source, s.label, s.sample_weight,
               s.fold, s.split, s.profile_snapshot, f.popularity_score
        FROM ml_training_samples s
        JOIN foods f ON f.id = s.food_id
        WHERE s.dataset_version = %s
        ORDER BY s.user_id, s.source, s.food_id
    """
    with cn.cursor() as cur:
        cur.execute(sql, (dataset_version,))
        rows = cur.fetchall()

    profiles = load_user_profiles(cn)
    names = feature_names(space)

    fs = FeatureSet(
        X=[], y=[], y_class=[], sample_weight=[], user_id=[], food_id=[],
        source=[], fold=[], split=[], p_u=[], n_signals=[], food_vector=[],
        popularity=[], target_macro=[], feature_names=names,
    )

    for d in rows:
        food = foods_by_id.get(d["food_id"])
        if food is None:
            # The food has been deactivated, or it is private. Drop the
            # sample rather than guessing a vector for it.
            continue

        snapshot = json.loads(d["profile_snapshot"]) if d["profile_snapshot"] else None
        p_u = list(snapshot["weights"]) if snapshot else [0.0] * space.length
        n_signals = int(snapshot["n_signals"]) if snapshot else 0
        if len(p_u) != space.length:
            raise ValueError(
                f"profile_snapshot has {len(p_u)} dimensions but the current "
                f"feature space has {space.length}. The dataset was built "
                f"with a different feature version — rebuild it with "
                f"`python -m ml.build_dataset`."
            )
        if not any(p_u):
            fs.n_empty_snapshots += 1

        profile = profiles.get(d["user_id"])
        if profile is None:
            profile = UserProfile(is_default=True)
            fs.n_default_profiles += 1

        vector = space.encode(food)
        x = build_feature_row(
            profile,
            p_u,
            vector,
            float(d["popularity_score"]),
            expected_length=len(names),
        )

        label = float(d["label"])
        fs.X.append(x)
        fs.y.append(label)
        fs.y_class.append(1 if label >= LIKE_THRESHOLD else 0)
        fs.sample_weight.append(float(d["sample_weight"]))
        fs.user_id.append(d["user_id"])
        fs.food_id.append(d["food_id"])
        fs.source.append(d["source"])
        fs.fold.append(int(d["fold"]))
        fs.split.append(d["split"])
        fs.p_u.append(p_u)
        fs.n_signals.append(n_signals)
        fs.food_vector.append(vector)
        fs.popularity.append(float(d["popularity_score"]))
        fs.target_macro.append(profile.target_macro)

    return fs


def load_space(cn) -> tuple[FeatureSpace, dict[str, Food]]:
    """Convenience: load the foods and build the feature space, printing no
    report."""
    from .features import load_foods

    foods, _ = load_foods(cn)
    return FeatureSpace.from_foods(foods), {f.id: f for f in foods}


def summary(fs: FeatureSet) -> str:
    by_source: dict[str, int] = {}
    for s in fs.source:
        by_source[s] = by_source.get(s, 0) + 1
    liked = sum(fs.y_class)
    return "\n".join(
        [
            f"{len(fs)} samples - {len(fs.feature_names)} features - "
            f"{len(set(fs.user_id))} users",
            f"  label >= {LIKE_THRESHOLD}: {liked} "
            f"({liked / len(fs):.1%})" if fs else "  (empty set)",
            "  sources: " + " ".join(f"{k}={v}" for k, v in sorted(by_source.items())),
            f"  default health profile: {fs.n_default_profiles} samples",
            f"  empty profile snapshot: {fs.n_empty_snapshots} samples",
        ]
    )
