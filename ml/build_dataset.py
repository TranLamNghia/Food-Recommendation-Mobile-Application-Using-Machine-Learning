#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dataset builder — seven signal sources -> `ml_training_samples`.

`docs/ML_PIPELINE.md` section 9 is the specification. Each source yields a
**label** and a **weight**, and those two columns answer different questions:

    label          — how much does the user like this food?
    sample_weight  — how much do we trust that number?

A 5-star rating after eating (weight 1.0) is far more trustworthy than a
skipped serving (0.3): skipping is an **ambiguous** signal — it might be
dislike, or it might be that there was no time to cook that day.

Three things this file does that reading the SQL will not show:

**1. `profile_snapshot` prevents data leakage.** The cross feature
`cos(p_u, v_i)` is a model input. Using the *current* `p_u` — a vector
already updated by the very signal being labelled — would put label
information into the feature, and the evaluation would look excellent while
being useless in production. So the Rocchio profile is **replayed in
chronological order** per user, and a sample's snapshot contains only the
swipes that came **before** it.

**2. The split is by USER, not by sample.** If one person appears in both the
training and the test set, the model has already seen their taste and the
evaluation figure is inflated.

**3. Private foods stay out.** Their nutrition figures are self-declared;
letting them into a shared model harms every other user
(`ML_PIPELINE.md` section 4.2).

Run:
    python -m ml.build_dataset --version d1              # dry run
    python -m ml.build_dataset --version d1 --apply      # write to the database
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from .db import connect, use_utf8
from .f1_filter import conditions_for_user, exclusion_reasons
from .features import FeatureSpace, Food, load_foods
from .rocchio import build_profile, empty_profile

#: Label and weight per source. `feedback` is absent because its label is
#: derived from the star rating — see `label_from_rating`.
LABEL_BY_SOURCE: dict[str, tuple[float, float]] = {
    #  source           label  weight
    "diary": (0.800, 0.900),
    "plan_kept": (0.700, 0.600),
    "plan_replaced": (0.150, 0.600),
    "plan_skipped": (0.300, 0.300),
    "random_neg": (0.100, 0.200),
}

#: Label per swipe action. `unknown` is **absent** — it is dropped from the
#: dataset rather than labelled 0.5, because labelling it 0.5 invents a label
#: the user never gave and then trains a model on the invention
#: (`ML_PIPELINE.md` section 9.2).
SWIPE_LABEL: dict[str, float] = {"like": 0.900, "neutral": 0.500, "dislike": 0.000}
SWIPE_WEIGHT = 0.700

#: `meal_plan_items.status` -> source. `suggested` is absent: the user has
#: decided nothing about that serving, so it is not a signal. `eaten` folds
#: into `plan_kept` — having eaten it is a form of keeping it, only stronger.
SOURCE_BY_STATUS = {
    "kept": "plan_kept",
    "eaten": "plan_kept",
    "replaced": "plan_replaced",
    "skipped": "plan_skipped",
}


def label_from_rating(rating: int) -> float:
    """5 stars -> 1.000 - 4 -> 0.750 - 3 -> 0.500 - 2 -> 0.250 - 1 -> 0.000."""
    if not 1 <= rating <= 5:
        raise ValueError(f"rating must be 1-5, got {rating}")
    return round((rating - 1) / 4, 3)


@dataclass
class Sample:
    """One `ml_training_samples` row, before fold and snapshot are assigned."""

    user_id: str
    food_id: str
    source: str
    label: float
    sample_weight: float
    collected_at: datetime
    context_meal_type: str | None = None
    #: The id of the originating row. Used only for `swipe`, to exclude
    #: **this sample's own** swipe from the profile snapshot while keeping
    #: the other swipes from the same second.
    source_id: str | None = None
    #: The verbatim `interactions.action`, present only on `swipe` samples.
    #: Kept separately because Rocchio needs the *action*, whereas `label` is
    #: already converted — deriving the action back from the label is a
    #: fragile lookup that breaks whenever the labels change.
    action: str | None = None


# ── Collecting signals per source ─────────────────────────────────────
#
# Every query carries `f.owner_id IS NULL`: private foods do not enter the
# global model's training set.

_PUBLIC_FOOD_JOIN = (
    "JOIN foods f ON f.id = {column} AND f.owner_id IS NULL AND f.is_active = 1"
)


def from_feedback(cn) -> list[Sample]:
    """`feedbacks` — the most trustworthy signal, weight 1.0.

    A person may rate the same food several times. Keep the **most recent**:
    their latest opinion is their current one.
    """
    sql = f"""
        SELECT fb.id, fb.user_id, fb.food_id, fb.rating, fb.created_at
        FROM feedbacks fb
        {_PUBLIC_FOOD_JOIN.format(column="fb.food_id")}
        ORDER BY fb.created_at, fb.id
    """
    with cn.cursor() as cur:
        cur.execute(sql)
        return [
            Sample(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="feedback",
                label=label_from_rating(int(d["rating"])),
                sample_weight=1.000,
                collected_at=d["created_at"],
                source_id=d["id"],
            )
            for d in cur.fetchall()
        ]


def from_swipes(cn) -> list[Sample]:
    """`interactions` — the swipes. `unknown` is dropped in the SQL itself."""
    placeholders = ", ".join(["%s"] * len(SWIPE_LABEL))
    sql = f"""
        SELECT i.id, i.user_id, i.food_id, i.action, i.interacted_at
        FROM interactions i
        {_PUBLIC_FOOD_JOIN.format(column="i.food_id")}
        WHERE i.action IN ({placeholders})
        ORDER BY i.interacted_at, i.id
    """
    with cn.cursor() as cur:
        cur.execute(sql, tuple(SWIPE_LABEL))
        return [
            Sample(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="swipe",
                label=SWIPE_LABEL[d["action"]],
                sample_weight=SWIPE_WEIGHT,
                collected_at=d["interacted_at"],
                source_id=d["id"],
                action=d["action"],
            )
            for d in cur.fetchall()
        ]


def from_diary(cn) -> list[Sample]:
    """`food_diary` — actually eaten.

    A known limitation: eating something repeatedly is a **stronger** signal
    than eating it once, but the schema has no repeat-count column, and
    section 9.1 rules that `sample_weight` encodes **confidence**, not degree
    of liking. So only the most recent entry is kept and the repetition is
    discarded. Using it would require a new column, not an invented
    weight-multiplication formula.
    """
    label, weight = LABEL_BY_SOURCE["diary"]
    sql = f"""
        SELECT fd.id, fd.user_id, fd.food_id, fd.meal_type,
               fd.created_at, fd.ate_on
        FROM food_diary fd
        {_PUBLIC_FOOD_JOIN.format(column="fd.food_id")}
        ORDER BY fd.ate_on, fd.created_at, fd.id
    """
    with cn.cursor() as cur:
        cur.execute(sql)
        return [
            Sample(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="diary",
                label=label,
                sample_weight=weight,
                collected_at=d["created_at"],
                context_meal_type=d["meal_type"],
                source_id=d["id"],
            )
            for d in cur.fetchall()
        ]


def from_meal_plans(cn) -> list[Sample]:
    """`meal_plan_items` — kept, replaced, skipped.

    Three different sources, so one (person, food) pair can legitimately
    produce three rows: they kept the serving today and replaced it another
    day. Those genuinely are three independent signals, which is why
    `uq_sample` includes `source` in its key.
    """
    placeholders = ", ".join(["%s"] * len(SOURCE_BY_STATUS))
    sql = f"""
        SELECT mpi.id, mp.user_id, mpi.food_id, mpi.meal_type, mpi.status,
               COALESCE(mpi.replaced_at, mpi.created_at) AS at_time
        FROM meal_plan_items mpi
        JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
        {_PUBLIC_FOOD_JOIN.format(column="mpi.food_id")}
        WHERE mpi.status IN ({placeholders})
        ORDER BY at_time, mpi.id
    """
    with cn.cursor() as cur:
        cur.execute(sql, tuple(SOURCE_BY_STATUS))
        result: list[Sample] = []
        for d in cur.fetchall():
            source = SOURCE_BY_STATUS[d["status"]]
            label, weight = LABEL_BY_SOURCE[source]
            result.append(
                Sample(
                    user_id=d["user_id"],
                    food_id=d["food_id"],
                    source=source,
                    label=label,
                    sample_weight=weight,
                    collected_at=d["at_time"],
                    context_meal_type=d["meal_type"],
                    source_id=d["id"],
                )
            )
        return result


def random_negatives(
    cn,
    *,
    already_shown: dict[str, set[str]],
    fixed_count: int | None,
    ratio: float,
    seed: int,
    latest_signal_at: dict[str, datetime],
) -> list[Sample]:
    """`random_neg` — foods **never shown** to that person.

    Why they are needed. Without negative samples the model only ever sees
    foods the system chose to display, and it learns to reproduce the
    system's own filter rather than learning taste. Label 0.100 at weight
    0.200: this is a **guess** that a user is not especially fond of a
    randomly chosen food, and the low weight says not to trust the guess too
    far.

    Drawn only from public, active foods. Generated through
    `random.Random(seed)` so a rerun produces the same set — a dataset that
    cannot be reproduced cannot be used to compare two models.

    ## The negative count must be PROPORTIONAL to the signal count

    The first version took a fixed number (20) for everybody. That created a
    spurious correlation that all three algorithms latched onto on the first
    run with real data: `user.n_signals` became the **strongest feature** of
    all three.

    The mechanism: with a fixed negative count, a person's share of
    zero-label samples is `20 / (20 + n)` — a **monotonically decreasing**
    function of their signal count. Measured over the 50 simulated users, the
    `random_neg` share ran from 0.370 at `n = 34` down to 0.318 at `n = 43`,
    and `corr(n_signals, label)` was +0.215 within the `swipe` group but
    +0.000 within `random_neg` — the signature of a correlation that lives in
    the **mixing ratio between two sources**, not in any signal.

    Only the `ml` variant reads features, so only it benefited, and that
    benefit **does not transfer to serving**, where no negatives are drawn at
    all. In other words it raised the `ml` row of the Chapter 3 comparison
    above its true value, in precisely the column the whole project has to
    demonstrate.

    Drawing proportionally makes `negatives / (negatives + n) = ratio /
    (1 + ratio)` — a constant, no longer a function of `n`. `ratio = 0.5`
    preserves roughly the previous label balance (49.1% positive with 20
    fixed negatives over about 39 signals).

    Passing `fixed_count` returns to a fixed number. That path is kept
    because `tools/check_ml_e2e.py` needs a sample set it can count in
    advance, and a check whose sample count varies with the synthetic data's
    signal count cannot assert anything.

    ## Negatives must not be drawn from foods F1 already blocks

    `ml/serve.py` runs F1 before any scoring, so a blocked food is never a
    candidate at serving time. Training on them trains on a distribution the
    model will never meet — and they are **far too easy** negatives: for a
    vegan every meat dish is label 0, predictable without knowing anything
    about taste. Measured before the fix: **82 of 880 negatives (9.3%)** were
    foods F1 had already excluded for that very person.

    It is also a question of responsibility: section 4 says F1 is the safety
    layer, placed **before** every model. Having the model re-learn the same
    exclusion makes it do another layer's job by a softer mechanism, in
    exchange for an evaluation figure higher than the truth.
    """
    if fixed_count is None and ratio <= 0:
        raise ValueError("either `fixed_count` or a positive `ratio` is required")

    label, weight = LABEL_BY_SOURCE["random_neg"]
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id FROM foods WHERE owner_id IS NULL AND is_active = 1 "
            "ORDER BY id"
        )
        every_food = [d["id"] for d in cur.fetchall()]

    result: list[Sample] = []
    # Cached per condition set, not per user: 50 users usually share only a
    # handful of distinct condition sets, and `exclusion_reasons` scans
    # `condition_rules` x `foods`.
    blocked_cache: dict[tuple[tuple[int, str], ...], frozenset[str]] = {}
    for user_id in sorted(already_shown):
        conditions = conditions_for_user(cn, user_id)
        key = tuple(sorted((c.condition_id, c.severity) for c in conditions))
        if key not in blocked_cache:
            blocked_cache[key] = (
                frozenset(
                    exclusion_reasons(cn, conditions=conditions, public_only=True)
                )
                if conditions
                else frozenset()
            )
        blocked = blocked_cache[key]

        # The seed mixes in the user id: two different people get two
        # different negative sets, but a rerun still gives each person their
        # own set even if the number of users changed.
        rng = random.Random(f"{seed}:{user_id}")
        remaining = [
            f
            for f in every_food
            if f not in already_shown[user_id] and f not in blocked
        ]
        rng.shuffle(remaining)
        # At least 1: a person with a single signal still needs a negative,
        # otherwise every sample they have carries the same label.
        take = (
            fixed_count
            if fixed_count is not None
            else max(1, round(ratio * len(already_shown[user_id])))
        )
        for food_id in remaining[:take]:
            result.append(
                Sample(
                    user_id=user_id,
                    food_id=food_id,
                    source="random_neg",
                    label=label,
                    sample_weight=weight,
                    collected_at=latest_signal_at[user_id],
                )
            )
    return result


# ── Merge, deduplicate ────────────────────────────────────────────────


def deduplicate(samples: Iterable[Sample]) -> tuple[list[Sample], int]:
    """Keep **one** row per `(user_id, food_id, source)` — the newest.

    `uq_sample (dataset_version, user_id, food_id, source)` is the matching
    schema constraint. Without it, every rebuild of a dataset would duplicate
    every sample and the model would train on duplicated data unnoticed.
    Deduplicating here as well lets the script report **how many were
    merged** instead of leaving the database to raise error 1062 and stop.
    """
    kept: dict[tuple[str, str, str], Sample] = {}
    dropped = 0
    for sample in samples:
        key = (sample.user_id, sample.food_id, sample.source)
        current = kept.get(key)
        if current is None:
            kept[key] = sample
        else:
            dropped += 1
            if sample.collected_at >= current.collected_at:
                kept[key] = sample
    return list(kept.values()), dropped


# ── Profile snapshots, leakage prevention ─────────────────────────────


def build_snapshots(
    samples: Sequence[Sample],
    swipes: Sequence[Sample],
    space: FeatureSpace,
    foods_by_id: dict[str, Food],
) -> dict[str, dict[str, Any]]:
    """Compute `profile_snapshot` per sample — the profile **before** that
    signal.

    Replays each person's swipe history chronologically and, for each sample,
    takes the profile built from the swipes preceding it.

    The subtle part: MySQL `DATETIME` has second resolution, and an
    onboarding swipe session produces dozens of swipes within a few seconds.
    Cutting at `time < sample_time` would wrongly cut every swipe from the
    **same second**; cutting at `<=` would let the sample's own swipe into
    its snapshot — exactly the leak being avoided. So:

    - `swipe` samples — cut at `<=` then **remove that one row** by
      `source_id`, which keeps the same-second swipes;
    - other sources — cut at `<=`, because a swipe in the same second is a
      *different* signal, not the label under consideration.
    """
    swipes_by_user: dict[str, list[Sample]] = {}
    for swipe in swipes:
        swipes_by_user.setdefault(swipe.user_id, []).append(swipe)
    for items in swipes_by_user.values():
        items.sort(key=lambda s: (s.collected_at, s.source_id or ""))

    snapshots: dict[str, dict[str, Any]] = {}

    for user_id, user_samples in _group_by_user(samples).items():
        user_swipes = swipes_by_user.get(user_id, [])
        user_samples.sort(key=lambda s: (s.collected_at, s.source_id or ""))

        # A growing prefix: the swipes up to the moment under consideration.
        # Rebuilding the profile from scratch each time is O(n^2) per person;
        # at around 30 swipes that is not worth optimising further, and
        # rebuilding from scratch is guaranteed to match the Dart version.
        i = 0
        prefix: list[Sample] = []
        for sample in user_samples:
            while (
                i < len(user_swipes)
                and user_swipes[i].collected_at <= sample.collected_at
            ):
                prefix.append(user_swipes[i])
                i += 1

            # Remove **the originating row** of this sample by id, not by
            # food or by time: that keeps same-second swipes, and a person
            # who swipes the same food twice is not wrongly cut either.
            skip_id = sample.source_id if sample.source == "swipe" else None
            pairs = [
                (foods_by_id[s.food_id], s.action or "neutral")
                for s in prefix
                if s.source_id != skip_id and s.food_id in foods_by_id
            ]

            profile = build_profile(space, pairs) if pairs else empty_profile(space)
            snapshots[_key(sample)] = profile.to_json()

    return snapshots


def _group_by_user(samples: Sequence[Sample]) -> dict[str, list[Sample]]:
    grouped: dict[str, list[Sample]] = {}
    for sample in samples:
        grouped.setdefault(sample.user_id, []).append(sample)
    return grouped


def _key(sample: Sample) -> str:
    return f"{sample.user_id}|{sample.food_id}|{sample.source}"


# ── Splitting folds by user ───────────────────────────────────────────


def assign_folds(users: Sequence[str], n_folds: int, seed: int) -> dict[str, int]:
    """Assign each **user** to a fold.

    Split by person, not by sample: if the same person appears in both the
    training and the test set, the model has already seen their taste and the
    evaluation figure is inflated.

    How: **order users by hash, then deal them out round-robin.** The hash
    gives a deterministic order independent of the row order the database
    returns; dealing round-robin guarantees the folds differ by at most one
    person.

    The first version took `hash % n_folds` directly, because adding a new
    user then leaves existing users' folds untouched. But it is **not
    balanced**: with 10 users over 5 folds an actual run put 5 people in fold
    0 and **nobody in fold 4** — an empty test set and nothing to train on.
    That stability is not worth as much as every fold having people in it,
    and it is not needed anyway: the fold is **stored on each row** per
    `dataset_version`, so rebuilding over the same set of people reproduces
    the same assignment, and a different set of people is a different dataset
    version regardless.
    """
    if n_folds < 2:
        raise ValueError("there must be at least 2 folds")
    if len(users) < n_folds:
        print(
            f"  Note: only {len(users)} users for {n_folds} folds — "
            f"{n_folds - len(users)} folds will be empty. Lower --folds or "
            f"collect more data."
        )
    by_hash = sorted(
        users, key=lambda u: hashlib.sha256(f"{seed}:{u}".encode()).hexdigest()
    )
    return {u: i % n_folds for i, u in enumerate(by_hash)}


def split_label(fold: int, n_folds: int) -> str:
    """A fold's role in the **reference split**.

    The `split` column records a default split so a quick training run has
    train/val/test ready without splitting anything itself. The
    cross-validation in `ml/evaluate.py` rotates the folds and ignores this
    column.

    With exactly 2 folds there is no room for `val`: split into train/test
    and drop `val`. Reserving a fold for `val` would leave **no fold as
    train**, and the reference split would become useless with no warning.
    """
    if fold == n_folds - 1:
        return "test"
    if n_folds >= 3 and fold == n_folds - 2:
        return "val"
    return "train"


# ── Writing to the database ───────────────────────────────────────────

SQL_DELETE = "DELETE FROM ml_training_samples WHERE dataset_version = %s"

SQL_INSERT = """
INSERT INTO ml_training_samples
    (dataset_version, user_id, food_id, label, sample_weight, source,
     context_meal_type, split, fold, collected_at, profile_snapshot)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def write_samples(
    cn,
    version: str,
    samples: Sequence[Sample],
    fold_by_user: dict[str, int],
    n_folds: int,
    snapshots: dict[str, dict[str, Any]],
) -> int:
    """Delete the old version, then insert everything. One transaction.

    Deleting first is deliberate: rebuilding the same `dataset_version` means
    "rebuild this dataset", so the result has to be **exactly** the new set,
    not the new set mixed with leftovers from the previous run.
    """
    rows = [
        (
            version,
            s.user_id,
            s.food_id,
            s.label,
            s.sample_weight,
            s.source,
            s.context_meal_type,
            split_label(fold_by_user[s.user_id], n_folds),
            fold_by_user[s.user_id],
            s.collected_at,
            json.dumps(snapshots.get(_key(s)), ensure_ascii=False),
        )
        for s in samples
    ]
    with cn.cursor() as cur:
        cur.execute(SQL_DELETE, (version,))
        deleted = cur.rowcount
        if rows:
            cur.executemany(SQL_INSERT, rows)
    cn.commit()
    if deleted:
        print(f"Deleted {deleted} rows of the previous {version!r} version.")
    return len(rows)


# ── Orchestration ─────────────────────────────────────────────────────


def build(
    cn,
    *,
    version: str,
    fixed_negatives: int | None,
    negative_ratio: float,
    n_folds: int,
    seed: int,
    apply: bool,
) -> int:
    foods, report = load_foods(cn)
    report.print_report()
    space = FeatureSpace.from_foods(foods)
    foods_by_id = {f.id: f for f in foods}
    print()

    feedback = from_feedback(cn)
    swipes = from_swipes(cn)
    diary = from_diary(cn)
    plans = from_meal_plans(cn)

    # Foods "shown" to the user: everything they ever swiped, ate, rated or
    # received in a plan. Random negatives must lie outside that set.
    already_shown: dict[str, set[str]] = {}
    latest_signal_at: dict[str, datetime] = {}
    for sample in (*feedback, *swipes, *diary, *plans):
        already_shown.setdefault(sample.user_id, set()).add(sample.food_id)
        current = latest_signal_at.get(sample.user_id)
        if current is None or sample.collected_at > current:
            latest_signal_at[sample.user_id] = sample.collected_at

    negatives = random_negatives(
        cn,
        already_shown=already_shown,
        fixed_count=fixed_negatives,
        ratio=negative_ratio,
        seed=seed,
        latest_signal_at=latest_signal_at,
    )

    everything = [*feedback, *swipes, *diary, *plans, *negatives]
    everything, merged = deduplicate(everything)
    everything.sort(key=lambda s: (s.user_id, s.source, s.food_id))

    print("Signals by source:")
    counts: dict[str, int] = {}
    for sample in everything:
        counts[sample.source] = counts.get(sample.source, 0) + 1
    for source in (
        "feedback",
        "swipe",
        "diary",
        "plan_kept",
        "plan_replaced",
        "plan_skipped",
        "random_neg",
    ):
        print(f"  {source:14} {counts.get(source, 0):6}")
    print(f"  {'-' * 14} {'-' * 6}")
    print(f"  {'total':14} {len(everything):6}")
    if merged:
        print(f"  (merged {merged} rows duplicating a person-food-source triple)")

    if not everything:
        print(
            "\nNo signals in the database — nothing to build.\n"
            "The machine learning part is waiting on data collected from real "
            "users; see docs/ML_PIPELINE.md section 11.3."
        )
        return 0

    users = sorted({s.user_id for s in everything})
    fold_by_user = assign_folds(users, n_folds, seed)
    print(f"\n{len(users)} users, split into {n_folds} folds by person:")
    for fold in range(n_folds):
        in_fold = [u for u in users if fold_by_user[u] == fold]
        n_samples = sum(1 for s in everything if fold_by_user[s.user_id] == fold)
        print(
            f"  fold {fold} [{split_label(fold, n_folds):5}] "
            f"{len(in_fold):3} users, {n_samples:6} samples"
        )

    snapshots = build_snapshots(everything, swipes, space, foods_by_id)
    with_vector = sum(1 for v in snapshots.values() if any(v["weights"]))
    print(
        f"\nProfile snapshots: {len(snapshots)} samples, "
        f"{with_vector} with a non-empty vector "
        f"({len(snapshots) - with_vector} with no preceding swipe)"
    )

    if not apply:
        print(
            f"\nDry run — nothing written. Add --apply to write "
            f"{len(everything)} rows to ml_training_samples."
        )
        return 0

    n = write_samples(cn, version, everything, fold_by_user, n_folds, snapshots)
    print(f"\nWrote {n} rows to ml_training_samples, version {version!r}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="the value for dataset_version"
    )
    parser.add_argument(
        "--db", default=None, help="another database name, for trial runs"
    )
    parser.add_argument(
        "--random-neg",
        type=int,
        default=None,
        help="a FIXED number of negatives per user; omit to use the ratio",
    )
    parser.add_argument(
        "--random-neg-ratio",
        type=float,
        default=0.5,
        dest="negative_ratio",
        help="negatives = this ratio x that person's signal count (default 0.5)",
    )
    parser.add_argument("--folds", type=int, default=5, help="fold count (default 5)")
    parser.add_argument("--seed", type=int, default=42, help="seed (default 42)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to the database; dry run by default",
    )
    t = parser.parse_args(argv)

    if len(t.version) > 20:
        print("dataset_version is limited to 20 characters.", file=sys.stderr)
        return 1

    cn = connect(t.db)
    try:
        return build(
            cn,
            version=t.version,
            fixed_negatives=t.random_neg,
            negative_ratio=t.negative_ratio,
            n_folds=t.folds,
            seed=t.seed,
            apply=t.apply,
        )
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
