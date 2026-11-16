# -*- coding: utf-8 -*-
"""Food popularity — the Wilson lower bound on the share of users who like it.

Two entry points, one formula, differing in **data scope**:

    from_database()  — over every signal. Used when serving:
                       `tools/update_popularity.py` writes the result into
                       `foods.popularity_score`.
    from_samples()   — over the training folds only. Used when evaluating.

## Why the second one has to exist

Found by running `tools/check_ml_e2e.py` with **random** labels: the
`popularity` baseline reached nDCG@5 = 0.796 — near-perfect on data with no
structure at all. And the `ml` model's AUC jumped from 0.48 to 0.67.

One shared cause: `popularity_score` is computed from **every** signal,
including signals from users in the test fold. A food that the very user
being tested liked has already pushed its own popularity up — so "popularity"
carries information about the test set's **labels**. That leak reaches two
places:

1.  the `popularity` baseline, strengthening it unrealistically;
2.  the model's `mon.do_pho_bien` feature, so the model leaks along with it.

When **serving** there is no leak: popularity is computed from the past and
applied to future users. The leak appears only in offline evaluation, where
"past" and "future" are split by user rather than by time. So `from_samples`
exists precisely for `ml/evaluate.py`.

## Definition: count PEOPLE, not events

    n_seen(food)  = distinct users with **any** signal about the food
    n_liked(food) = distinct users with **at least one** positive signal

One enthusiastic user eating the same dish twenty times would single-handedly
push it to the top of the table if events were counted, whereas "popular" has
to mean *many people* like it.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

#: 95% confidence -> z = 1.96.
Z = 1.959963984540054

#: From how many stars a rating counts as a positive signal.
#: 4, not 3: a 3-star rating carries the label 0.500 — exactly the neutral
#: point — so counting it as "liked" would lift every mediocre food.
POSITIVE_STARS = 4

#: Which `meal_plan_items.status` counts as positive. `suggested` is absent:
#: the user has decided nothing. `replaced` and `skipped` are negative
#: signals, so they only enter the denominator.
POSITIVE_STATUSES = ("kept", "eaten")


def wilson_lower_bound(positives: int, total: int, z: float = Z) -> float:
    """The Wilson confidence-interval lower bound for a proportion.

                p + z^2/2n  -  z*sqrt( p(1-p)/n + z^2/4n^2 )
        low =   --------------------------------------------
                               1 + z^2/n

    Why not simply `positives / total`: a food shown to 2 people and liked by
    both scores 1.00 and outranks a food shown to 100 people and liked by 90
    (0.90). That is a wrong conclusion — a sample of 2 proves nothing. The
    Wilson lower bound answers the question actually being asked: *what is
    the lowest this food's true like-rate plausibly is?*

        2/2   -> 0.3424      90/100 -> 0.8256      0/10 -> 0.0000
        1/1   -> 0.2065      9/10   -> 0.5958

    Thinly-sampled foods are pulled toward 0 naturally, with no hand-set
    "minimum N users" threshold anywhere.

    Returns 0 when there is no sample at all. That is a choice, not a fact: 0
    here means "not yet shown to be popular", not "nobody likes it". Giving
    them the catalogue average would **invent** a popularity that nobody ever
    expressed.

    Clamped to [0, 1] because floating-point error can produce -1e-17, and the
    `DECIMAL(5,4)` column rejects a negative value.
    """
    if total <= 0:
        return 0.0
    if positives < 0 or positives > total:
        raise ValueError(f"{positives} positives is invalid for a sample of {total}")

    p = positives / total
    z2 = z * z
    numerator = p + z2 / (2 * total) - z * math.sqrt(
        p * (1 - p) / total + z2 / (4 * total * total)
    )
    denominator = 1 + z2 / total
    return min(1.0, max(0.0, numerator / denominator))


# ── From every signal in the database ─────────────────────────────────

# Each source contributes two user sets: "has seen" and "has shown liking".
# Written with `UNION` so that a user with several signals about one food is
# counted once — `COUNT(DISTINCT user_id)` on the outside does that part.
SQL_COUNTS = f"""
WITH seen AS (
    SELECT food_id, user_id FROM interactions
    UNION
    SELECT food_id, user_id FROM feedbacks
    UNION
    SELECT food_id, user_id FROM food_diary
    UNION
    SELECT mpi.food_id, mp.user_id
    FROM meal_plan_items mpi
    JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
    WHERE mpi.status <> 'suggested'
),
liked AS (
    SELECT food_id, user_id FROM interactions WHERE action = 'like'
    UNION
    SELECT food_id, user_id FROM feedbacks WHERE rating >= {POSITIVE_STARS}
    UNION
    SELECT food_id, user_id FROM food_diary
    UNION
    SELECT mpi.food_id, mp.user_id
    FROM meal_plan_items mpi
    JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
    WHERE mpi.status IN {POSITIVE_STATUSES}
)
SELECT f.id, f.name, f.popularity_score AS previous,
       (SELECT COUNT(DISTINCT user_id) FROM seen  s WHERE s.food_id = f.id)
           AS n_seen,
       (SELECT COUNT(DISTINCT user_id) FROM liked l WHERE l.food_id = f.id)
           AS n_liked
FROM foods f
ORDER BY f.name, f.id
"""


def from_database(cn) -> list[dict[str, Any]]:
    """Count users per food over **every** signal.

    Returns the rows with `n_seen`, `n_liked` and the computed `score`.
    Writes nothing — `tools/update_popularity.py` decides about writing.
    """
    with cn.cursor() as cur:
        cur.execute(SQL_COUNTS)
        rows = cur.fetchall()

    for row in rows:
        row["score"] = wilson_lower_bound(int(row["n_liked"]), int(row["n_seen"]))
    return list(rows)


# ── From the training folds only ──────────────────────────────────────


def from_samples(
    user_id: Sequence[str],
    food_id: Sequence[str],
    label: Sequence[float],
    source: Sequence[str],
    indices: Sequence[int],
    *,
    positive_threshold: float,
    skip_sources: frozenset[str] = frozenset({"random_neg"}),
) -> dict[str, float]:
    """Popularity rebuilt from **only the given samples**.

    `indices` are the positions belonging to the training folds. Every sample
    outside that list is dropped entirely, so the returned scores carry no
    information from the test fold — which is the whole point.

    Rebuilt from `ml_training_samples` rather than reading
    `foods.popularity_score`: the sample table is the only thing
    `ml/evaluate.py` should look at, and it already carries `label`, so
    "positive signal" reduces to `label >= positive_threshold`.

    `random_neg` is excluded from the count. A random negative is a food that
    was **never shown** to that person, so counting it in `n_seen` would claim
    the user saw and rejected a food they were never offered.
    """
    seen: dict[str, set[str]] = {}
    liked: dict[str, set[str]] = {}

    for i in indices:
        if source[i] in skip_sources:
            continue
        food = food_id[i]
        user = user_id[i]
        seen.setdefault(food, set()).add(user)
        if label[i] >= positive_threshold:
            liked.setdefault(food, set()).add(user)

    return {
        food: wilson_lower_bound(len(liked.get(food, ())), len(users))
        for food, users in seen.items()
    }
