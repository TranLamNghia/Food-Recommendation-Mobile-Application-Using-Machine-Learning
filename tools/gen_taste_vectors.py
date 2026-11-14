# -*- coding: utf-8 -*-
"""Generate simulated swipes from a known latent taste vector.

Why this file exists
────────────────────
The `f1_user_food_behaviors_50x45.csv` dataset carries no signal at all:
user-user cosine is +0.0359 while the same measure after shuffling each user's
ratings gives +0.0328 — the real value lies **inside** the noise band. The
variance of `like` counts per food is only 1.15x the binomial variance (the sd
of that ratio over 45 foods is 0.21). No model can learn anything from it, so
Chapter 3 would only re-measure the 41.0% majority rate.

This file replaces the noise with a **simulation that has ground truth**: each
synthetic person gets a latent taste vector `t_u` in the very 20-dimensional
space the system uses, and their choices are drawn from the closeness between
`t_u` and the food vector. The difference from the old file is not "a stronger
signal" but **knowing the answer in advance**: Chapter 3 can measure
`cos(p_u, t_u)` — how well the Rocchio profile recovers the latent vector —
rather than only accuracy on a test set whose true labels nobody knows.

This is SIMULATED data and must be written up as such in the report. It proves
**the model works** (it recovers what was known), not **what Vietnamese people
eat**. Those are two different claims, and only the first is measurable with
generated data.

The generative model
────────────────────
1.  **5 taste archetypes** `c_1..c_5`: the centres of 5 k-means clusters over
    the 45 food vectors themselves. Taken from the food data rather than
    picked by hand, because the Rocchio profile `p_u = Σ w·v / Σ|w|` is a
    **signed mean of food vectors** — it can only represent directions inside
    the region the food vectors span. A `t_u` drawn uniformly from [0,1]^20
    would lie outside that region, and the recovery cosine would be low for
    geometric reasons, not because the model learns badly.

2.  **Each person's latent vector**: `t_u = c_{z1} + λ·c_{z2} + σ·N(0, I) +
    δ_u`, with `z1` the primary archetype and `z2 ≠ z1` the secondary one.
    `z1` is dealt round-robin so exactly 10 people land on each archetype — a
    multinomial draw can leave an archetype empty at n = 50, and then the
    cluster measurement becomes meaningless.

    **Why two archetypes have to be mixed.** The first version used exactly
    one: `t_u = c_z`. But k-means runs over *foods*, and a cluster of foods is
    not a person's taste. The `Đồ uống` cluster holds only 4 of the 45 foods,
    so the 10 people in that cluster became people who "only like juice and
    dislike 16 main dishes" — no real person is like that. And the measurable
    consequence: `cos(p_u, t_u)` for those 10 people was 0.02-0.37 while
    everyone else reached 0.92-0.95, because the Rocchio profile was then
    dominated by the `dislike` part and pointed **away** from the true taste
    instead of towards it.

    Mixing in a secondary archetype with weight λ = 0.5 is both truer to real
    people — everyone has one main taste plus a side taste — and removes that
    degenerate case, **without** making the problem easier: `z1` is still
    dealt round-robin, so the cluster structure for collaborative filtering
    remains intact.

3.  **`δ_u` — the part where the health profile drives taste.** Only two
    columns of the ObesityDataSet are about *food*, so only those two are
    allowed to act: `FAVC` (frequently eats high-calorie food) pushes the `Tỷ
    lệ béo` and `Năng lượng` dimensions; `FCVC` (vegetable-eating frequency,
    1-3) pushes `Chất xơ`. The remaining columns — `MTRANS`, `TUE`, `SMOKE`…
    — have nothing to do with taste, and wiring them in would manufacture a
    finding that does not exist.

    The amplitude is deliberately small (0.10 by default on a [0,1] scale) so
    the archetype remains dominant. If the profile drove taste, the
    recommendation problem would turn into a regression on the profile and
    Step 2 would become useless — that is, the simulation would have answered
    away the very question the project asks.

4.  **`chua_biet` is independent of taste.** "Never eaten" is a property of
    the *food* — an unusual dish is one many people have not eaten — so each
    food gets a tendency `q_i ~ Beta` with mean 0.16, and each person then
    draws Bernoulli(`q_i`). Making `chua_biet` depend on taste is wrong both
    in meaning and in consequence: it turns the missing data into *missing not
    at random*, and then the Rocchio vector is systematically biased even with
    a correct formula.

5.  **The other three levels are drawn by ordered logit.** `y* = β·z(s) + ε`,
    with `s = cos(t_u, v_i)`, `z` a global standardisation, and
    `ε ~ Logistic(0,1)`. The two cutpoints are taken at the quantiles of `y*`
    matching the original file's marginal shares (`khong_thich` 25.8%,
    `binh_thuong` 33.2%, `thich` 41.0% of the rated swipes), so the marginal
    distribution **matches the original file** and the two are comparable.

    `ε` is the label noise; no separate label-flipping step is needed, as β
    controls the signal-to-noise ratio. Too large a β makes the problem
    perfectly linearly separable and every model reaches ~100% — a result that
    says nothing.

Run
───
    python tools/gen_taste_vectors.py                  # preview, write nothing
    python tools/gen_taste_vectors.py --write
    python tools/check_simulation.py                   # verify real signal

Needs the database — only to read `conditions` and `condition_rules` for the
constraint part in section 6 below. The food vectors are already in
`survey_deck.json`.

6.  **Health constraints, and the confounding they create.** `ObesityDataSet`
    has no medical-condition column, so assigning nothing would make the F1
    filter exclude 0 of 2250 swipes and **the whole system's safety layer
    would have not one line of evidence** in Chapter 3.

    Each person is assigned conditions / allergies / diets per
    `CONDITION_QUOTA`, **entirely independently of `t_u`** — a requirement of
    the measurement, because if the constraints correlated with taste there
    would be no way to separate what F1 removes from the real taste. Then, for
    each food F1 would not let that person eat, the choice is **overwritten to
    `khong_thich`** (with probability 0.85, the rest becoming `chua_biet`).

    That overwrite is exactly **the confounding that F1-at-import exists to
    remove**: a paper form uses one fixed deck, so a vegan is forced to rate
    beef pho too, and the model reads that `khong_thich` as "dislikes pho"
    rather than "is vegan". `t_u` is **unchanged** — it is still the true taste
    vector. That is what lets `check_simulation.py` measure the right
    question: does filtering by F1 before building the vector bring `p_u`
    closer to `t_u`.

Note on language: the output files' column names and JSON keys stay as they
are. `hanh_vi.csv` shares the survey form's contract with
`tools/import_swipes.py`, and `khau_vi_that.json` is read by
`tools/check_simulation.py` and `tools/import_simulation.py`.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import use_utf8  # noqa: E402

from ml.db import connect  # noqa: E402

# `FORM_SEVERITY` must be the **same value** as the severity the importer
# writes into `user_conditions`: the paper form does not ask for severity, so
# if the generator used `mild` while the importer wrote `moderate`, F1 at
# generation time would exclude a different set of foods from F1 at import
# time, for the same person. For `Gút` that difference is 0 foods against 11,
# because `condition_rules.severity_min` gates each rule.
from tools.import_swipes import FORM_SEVERITY  # noqa: E402

DECK = ROOT / "data" / "survey" / "survey_deck.json"
PROFILES_CSV = ROOT / "data" / "survey" / "f1_training_dataset_50_users.csv"
OUT_DIR = ROOT / "data" / "survey" / "mo_phong"
OUT_BEHAVIOUR = OUT_DIR / "hanh_vi.csv"
OUT_GROUND_TRUTH = OUT_DIR / "khau_vi_that.json"

#: The names of the 20 dimensions, in `FeatureSpace.encode` order: 8 fixed
#: dimensions then the category one-hot in `sorted()` order. The one-hot part
#: is **derived from the deck itself** in `dimension_labels()` rather than
#: typed out, because the order depends on the 318 foods in the database —
#: typed out, it stays right until the day somebody adds a category.
#:
#: The labels are Vietnamese: they are the same contract as
#: `ml.features.FIXED_LABELS`, shared with `food_vector.dart`.
FIXED_LABELS = (
    "Tỷ lệ đạm",
    "Tỷ lệ bột đường",
    "Tỷ lệ béo",
    "Năng lượng",
    "Vị ngọt",
    "Vị mặn",
    "Chất xơ",
    "Mức cay",
)

#: The dimensions `FAVC`/`FCVC` are allowed to push. Keyed by dimension NAME,
#: not index: index 2 is `Tỷ lệ béo` today, and will not be if the dimension
#: set changes.
FAVC_DIMENSIONS = ("Tỷ lệ béo", "Năng lượng")
FCVC_DIMENSIONS = ("Chất xơ",)

#: The original file's marginal shares among the **rated** swipes (excluding
#: `chua_biet`): 488 / 628 / 774 out of 1890. Kept so the two files are
#: comparable.
MARGINAL_SHARES = {"khong_thich": 488 / 1890, "binh_thuong": 628 / 1890}

#: The original file's `chua_biet` share: 360 / 2250.
UNKNOWN_SHARE = 360 / 2250

#: The concentration of the `Beta` that generates each food's `chua_biet`
#: tendency. Larger means the foods resemble each other more; 6.0 gives a
#: range of roughly 0.03-0.40, that is, some foods almost everyone has eaten
#: and some more than a third have not.
UNKNOWN_BETA_CONCENTRATION = 6.0

LEVELS = ("khong_thich", "binh_thuong", "thich", "chua_biet")

#: How many of the 50 people are assigned each condition.
#:
#: **This is deliberate STRATIFIED sampling, not epidemiological prevalence.**
#: Real Vietnamese prevalence over 50 people would give 1-2 people with a hard
#: constraint, and with 1-2 people nothing about the F1 filter is measurable —
#: the whole system's safety layer would have not one line of evidence in
#: Chapter 3. So this set is **deliberately enriched**: 20 of 50 people have at
#: least one hard constraint.
#:
#: This MUST be written up in the report exactly as such. It makes the sample
#: unrepresentative of the population in terms of disease prevalence, and any
#: figure of the form "x% of users lose y foods" read off this set is
#: meaningless. What IS measurable is the **mechanism**: when a person has a
#: constraint, does F1 remove exactly the constraint part from their taste.
#:
#: Foods excluded from the 45-food deck, measured with `exclusion_reasons` at
#: `moderate`:
#:
#:     Ăn thuần chay 24 · Ăn chay 24 · Gút 11 · Dị ứng hải sản 11
#:     Dị ứng đậu nành 5 · Dị ứng trứng 3 · Dị ứng đậu phộng 2
#:     Không dung nạp gluten 2
#:     Đái tháo đường 0 · Tăng huyết áp 0 · Bệnh thận 0 · Rối loạn mỡ máu 0
#:
#: The last four exclude **0 foods** because their rules are soft daily
#: thresholds (`scope = 'per_day'`), enforced by Step 4 phase 5 rather than by
#: F1. They are still assigned — they are the most common group and they
#: exercise the soft-rule layer — but the "with F1 / without F1" comparison
#: rests only on the first eight.
CONDITION_QUOTA = {
    # Metabolic conditions: assigned by risk derived from BMI and age, see
    # `assign_conditions`.
    "Tăng huyết áp": 12,
    "Đái tháo đường": 7,
    "Rối loạn mỡ máu": 8,
    # Hard constraints: assigned independently of taste.
    "Gút": 5,
    "Dị ứng hải sản": 5,
    "Dị ứng đậu nành": 3,
    "Dị ứng trứng": 2,
    "Dị ứng đậu phộng": 2,
    "Không dung nạp gluten": 2,
    "Ăn chay": 4,
    "Ăn thuần chay": 2,
}

#: Assigned by a risk score computed from the profile, not drawn uniformly.
#: The value is the weight of (BMI z-score, age z-score, male coefficient).
#:
#: The BMI -> diabetes / hypertension correlation is a **real** one, and
#: putting it in makes this set's health-profile part mean something instead of
#: being decoration. But it is a correlation **I injected**, so it has to be
#: stated: nobody may read this set and conclude "high BMI predisposes to
#: diabetes" as a finding.
RISK_WEIGHTS = {
    "Tăng huyết áp": (1.0, 0.6, 0.0),
    "Đái tháo đường": (1.0, 0.3, 0.0),
    "Rối loạn mỡ máu": (1.0, 0.2, 0.0),
    "Gút": (0.6, 0.2, 1.0),
}

#: The two diets are mutually exclusive: vegan already implies vegetarian, so
#: assigning both is redundant and also makes `user_conditions`
#: self-contradictory.
DIETS = ("Ăn chay", "Ăn thuần chay")

#: The maximum number of HARD constraints on one person. Without a cap, a
#: person could get vegan + seafood + gout and have F1 exclude nearly the whole
#: deck — at which point they contribute no taste signal at all, and the
#: importer stops.
MAX_HARD_CONSTRAINTS = 2

#: A person with hard constraints must still have at least this many usable
#: swipes left after F1 filtering. Below that the deck does not suit them, and
#: keeping them means keeping an incomplete profile.
MIN_USABLE_SWIPES = 15

#: The probability that a respondent marks an F1-excluded food `khong_thich`.
#:
#: This is **the confounding that F1-at-import exists to remove**. A paper form
#: uses one fixed deck for everyone, so a vegan is forced to rate beef pho too
#: — and they mark it `khong_thich`. The model reads that as "dislikes pho"
#: rather than "is vegan".
#:
#: Not 1.0: some of those foods they have never eaten, so they mark
#: `chua_biet`. The remaining `1 − 0.85` goes to `chua_biet`, not to `thich` —
#: a vegan does not mark `thich` for beef pho.
P_EXCLUDED_AS_DISLIKE = 0.85


# -- vector algebra, hand-written so this file needs no numpy ---------------


def vec_add(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def vec_scale(a: Sequence[float], k: float) -> list[float]:
    return [x * k for x in a]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def sq_distance(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# -- loading the inputs ----------------------------------------------------


def load_deck(path: Path) -> list[dict[str, Any]]:
    deck = json.loads(path.read_text(encoding="utf-8"))
    foods = sorted(deck["mon"], key=lambda m: m["thu_tu"])
    if not foods:
        raise SystemExit(f"{path} contains no food.")
    d = len(foods[0]["vector"])
    for food in foods:
        if len(food["vector"]) != d:
            raise SystemExit(
                f"food {food['name']!r} has a {len(food['vector'])}-dimension "
                f"vector while the others have {d} — the deck is corrupt."
            )
    return foods


def dimension_labels(foods: list[dict[str, Any]]) -> list[str]:
    """The names of the 20 dimensions, the one-hot part derived from the deck."""
    d = len(foods[0]["vector"])
    labels = list(FIXED_LABELS) + [
        f"nhóm #{i}" for i in range(len(FIXED_LABELS), d)
    ]
    for food in foods:
        hot = [
            i for i in range(len(FIXED_LABELS), d) if food["vector"][i] == 1.0
        ]
        if len(hot) == 1:
            labels[hot[0]] = f"Nhóm: {food['category']}"
    return labels


def load_profiles(path: Path) -> list[dict[str, str]]:
    """One row per person, taking the first row seen for each `user_id`."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} contains no data row.")
    missing = {"user_id", "FAVC", "FCVC", "source_profile_row"} - set(rows[0])
    if missing:
        raise SystemExit(
            f"{path} is missing columns: {', '.join(sorted(missing))}"
        )
    per_user: dict[str, dict[str, str]] = {}
    for row in rows:
        per_user.setdefault(row["user_id"], row)
    return [per_user[u] for u in sorted(per_user)]


# -- k-means over the food vectors, to obtain the taste archetypes ---------


def kmeans(
    points: list[Sequence[float]], k: int, *, seed: int, restarts: int = 30
) -> tuple[list[list[float]], list[int]]:
    """Lloyd with k-means++ initialisation, restarted and keeping the best.

    Restarting is necessary: Lloyd converges to a local minimum, so a single
    run yields different centres per seed — and then "5 taste archetypes"
    would be a property of the seed rather than of the data.
    """
    rnd = random.Random(seed)
    d = len(points[0])
    best: tuple[float, list[list[float]], list[int]] | None = None

    for _ in range(restarts):
        # k-means++: the first centre uniformly, each later centre by D² to
        # the nearest existing centre.
        centres = [list(points[rnd.randrange(len(points))])]
        while len(centres) < k:
            w = [min(sq_distance(p, c) for c in centres) for p in points]
            total = sum(w)
            if total == 0.0:
                centres.append(list(points[rnd.randrange(len(points))]))
                continue
            target = rnd.random() * total
            acc = 0.0
            for p, wi in zip(points, w):
                acc += wi
                if acc >= target:
                    centres.append(list(p))
                    break

        assign: list[int] = [0] * len(points)
        for step in range(100):
            fresh = [
                min(range(k), key=lambda j: sq_distance(p, centres[j]))
                for p in points
            ]
            if fresh == assign and step:
                break
            assign = fresh
            for j in range(k):
                members = [p for p, g in zip(points, assign) if g == j]
                if members:
                    centres[j] = [
                        sum(p[i] for p in members) / len(members)
                        for i in range(d)
                    ]
                else:
                    # An empty cluster: move its centre to the point farthest
                    # from its own centre, rather than dropping the cluster.
                    # Dropping it makes the real k smaller than the declared k.
                    farthest = max(
                        range(len(points)),
                        key=lambda i: sq_distance(
                            points[i], centres[assign[i]]
                        ),
                    )
                    centres[j] = list(points[farthest])

        sse = sum(
            sq_distance(p, centres[g]) for p, g in zip(points, assign)
        )
        if best is None or sse < best[0]:
            best = (sse, [list(c) for c in centres], list(assign))

    assert best is not None
    return best[1], best[2]


# -- generation -----------------------------------------------------------


def _z(values: list[float]) -> list[float]:
    mean = sum(values) / len(values)
    sd = math.sqrt(
        sum((x - mean) ** 2 for x in values) / max(1, len(values) - 1)
    ) or 1.0
    return [(x - mean) / sd for x in values]


def assign_conditions(
    profiles: list[dict[str, str]], rnd: random.Random
) -> dict[str, list[str]]:
    """Assign conditions / allergies / diets per `CONDITION_QUOTA`.

    Uses **exact quotas** rather than probability draws: with n = 50 and a rate
    of 0.04, a probability draw gives 0, 1, 2 or 4 people depending on the
    seed, and then the number of constrained people is a property of the seed
    rather than of the design. A quota gives the declared number on every run.

    The four conditions in `RISK_WEIGHTS` are assigned to the people with the
    **highest risk score** (BMI, age, gender) plus some noise; the rest are
    assigned entirely independently. The noise is necessary: without it, the
    hypertensive set would be exactly the 12 people with the highest BMI, a
    functional relationship any model learns perfectly and which resembles
    reality in no way at all.

    The constraints are **independent of taste** in every case: the risk score
    reads only the health profile, never `vector_khau_vi`. That is a
    requirement of the whole measurement — if the constraints correlated with
    taste, there would be no way to separate what F1 removes from the real
    taste.
    """
    user_ids = [p["user_id"] for p in profiles]
    bmi = _z([
        float(p["Weight"]) / (float(p["Height"]) ** 2) for p in profiles
    ])
    age = _z([float(p["Age"]) for p in profiles])
    male = [1.0 if p["Gender"] == "Male" else 0.0 for p in profiles]

    out: dict[str, list[str]] = {u: [] for u in user_ids}
    hard_count: dict[str, int] = {u: 0 for u in user_ids}
    has_diet: set[str] = set()

    # Assignment order: the diets first (they exclude 24 of 45 foods, the
    # heaviest), then the other hard constraints, then the metabolic
    # conditions (which exclude 0 foods, so they compete for no slot).
    # Assigning the heaviest first makes `MAX_HARD_CONSTRAINTS` bite where it
    # should; the other way round, someone already carrying two mild allergies
    # would block a vegetarian slot and the diet quota would go unmet.
    assign_order = (
        list(DIETS)
        + [
            k
            for k in CONDITION_QUOTA
            if k not in DIETS and k not in RISK_WEIGHTS
        ]
        + [k for k in RISK_WEIGHTS]
    )

    for name in assign_order:
        quota = CONDITION_QUOTA.get(name, 0)
        if not quota:
            continue
        counts_as_hard = name not in RISK_WEIGHTS or name == "Gút"

        if name in RISK_WEIGHTS:
            w_bmi, w_age, w_male = RISK_WEIGHTS[name]
            score = {
                u: w_bmi * bmi[i]
                + w_age * age[i]
                + w_male * male[i]
                + rnd.gauss(0.0, 1.0)
                for i, u in enumerate(user_ids)
            }
            ranked = sorted(user_ids, key=lambda u: -score[u])
        else:
            ranked = list(user_ids)
            rnd.shuffle(ranked)

        assigned = 0
        for u in ranked:
            if assigned >= quota:
                break
            if name in DIETS and u in has_diet:
                continue
            if counts_as_hard and hard_count[u] >= MAX_HARD_CONSTRAINTS:
                continue
            out[u].append(name)
            assigned += 1
            if counts_as_hard:
                hard_count[u] += 1
            if name in DIETS:
                has_diet.add(u)
        if assigned < quota:
            raise SystemExit(
                f"could not assign {quota} people to {name!r} (only got "
                f"{assigned}) — raise MAX_HARD_CONSTRAINTS or lower the quota "
                f"in CONDITION_QUOTA."
            )

    return {u: sorted(v) for u, v in out.items()}


def f1_exclusions_per_user(
    cn, conditions_by_user: dict[str, list[str]], food_ids: list[str]
) -> dict[str, list[str]]:
    """Per person, the foods the F1 filter would not let them eat.

    Calls `ml.f1_filter` directly — the same function `import_swipes.py`,
    `import_simulation.py` and `ml/serve.py` call. Reimplementing the filter
    here would let the generator and the importer drift apart, and that drift
    would mean the simulated data carries a different constraint from the one
    the system enforces.
    """
    from ml.f1_filter import conditions_by_name, exclusion_reasons

    out: dict[str, list[str]] = {}
    cache: dict[tuple[str, ...], list[str]] = {}
    for u, names in conditions_by_user.items():
        key = tuple(names)
        if key not in cache:
            if not names:
                cache[key] = []
            else:
                conditions = conditions_by_name(
                    cn, list(names), severity=FORM_SEVERITY
                )
                reasons = exclusion_reasons(
                    cn, conditions=conditions, public_only=True
                )
                cache[key] = [f for f in food_ids if reasons.get(f)]
        out[u] = list(cache[key])
    return out


def profile_nudge(
    profile: dict[str, str], labels: list[str], amplitude: float
) -> list[float]:
    """`δ_u` — the part where the health profile nudges the taste vector."""
    delta = [0.0] * len(labels)
    index = {label: i for i, label in enumerate(labels)}

    if (profile.get("FAVC") or "").strip().lower() == "yes":
        for label in FAVC_DIMENSIONS:
            delta[index[label]] += amplitude

    # FCVC runs 1-3, with 2 as the midpoint. The deviation from the midpoint
    # is how far the fibre dimension is pushed — eating few vegetables
    # (FCVC = 1) pushes it down.
    try:
        fcvc = float(profile.get("FCVC") or 2.0)
    except ValueError:
        fcvc = 2.0
    for label in FCVC_DIMENSIONS:
        delta[index[label]] += amplitude * max(-1.0, min(1.0, fcvc - 2.0))

    return delta


def generate(
    *,
    cn,
    foods: list[dict[str, Any]],
    profiles: list[dict[str, str]],
    n_archetypes: int,
    lambda_secondary: float,
    sigma: float,
    beta: float,
    profile_amplitude: float,
    seed: int,
) -> dict[str, Any]:
    labels = dimension_labels(foods)
    vectors = [food["vector"] for food in foods]
    centres, food_assign = kmeans(vectors, n_archetypes, seed=seed)

    # A label for each archetype: the three nearest foods. An archetype
    # nobody can read cannot be written into the report.
    archetype_labels = []
    for j, centre in enumerate(centres):
        nearest = sorted(
            foods, key=lambda m: sq_distance(m["vector"], centre)
        )
        archetype_labels.append(
            {
                "chi_so": j,
                "so_mon_trong_cum": sum(1 for g in food_assign if g == j),
                "mon_dai_dien": [m["name"] for m in nearest[:3]],
                "tam": [round(x, 6) for x in centre],
            }
        )

    rnd = random.Random(seed + 1)

    # Each food's `chua_biet` tendency. Beta(a, b) with
    # a + b = UNKNOWN_BETA_CONCENTRATION and a / (a + b) = UNKNOWN_SHARE.
    a = UNKNOWN_SHARE * UNKNOWN_BETA_CONCENTRATION
    b = UNKNOWN_BETA_CONCENTRATION - a
    q = [rnd.betavariate(a, b) for _ in foods]

    # Dealt round-robin over a shuffled list: perfectly balanced across the
    # archetypes, while still not assigning by `user_id` order.
    order = list(range(len(profiles)))
    rnd.shuffle(order)
    primary = {}
    for position, i in enumerate(order):
        primary[profiles[i]["user_id"]] = position % n_archetypes

    # The health constraints. Assigned BEFORE `t_u` is built and without
    # reading `t_u`, so there is no path by which taste could influence the
    # constraints or the other way round.
    conditions_by_user = assign_conditions(profiles, rnd)
    food_ids = [food["id"] for food in foods]
    f1_excluded = f1_exclusions_per_user(cn, conditions_by_user, food_ids)

    for u, excluded in f1_excluded.items():
        left = len(food_ids) - len(excluded)
        if left < MIN_USABLE_SWIPES:
            raise SystemExit(
                f"F1 excludes {len(excluded)}/{len(food_ids)} foods for {u}, "
                f"leaving only {left} usable swipes (need >= "
                f"{MIN_USABLE_SWIPES}).\n"
                f"Conditions: {', '.join(conditions_by_user[u])}\n"
                f"Lower MAX_HARD_CONSTRAINTS or the quotas in "
                f"CONDITION_QUOTA."
            )

    people: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        u = profile["user_id"]
        secondary = rnd.choice(
            [j for j in range(n_archetypes) if j != primary[u]]
        )
        t = vec_add(
            centres[primary[u]],
            vec_scale(centres[secondary], lambda_secondary),
        )
        t = vec_add(t, [rnd.gauss(0.0, sigma) for _ in labels])
        t = vec_add(t, profile_nudge(profile, labels, profile_amplitude))
        people[u] = {
            "nguyen_mau": primary[u],
            "nguyen_mau_phu": secondary,
            "vector_khau_vi": [round(x, 6) for x in t],
            "condition_names": conditions_by_user[u],
            "severity": FORM_SEVERITY,
            # The foods F1 would not let this person eat. Recorded so that
            # `check_simulation.py` can measure without a database, and so
            # `import_simulation.py` can cross-check against the filtering it
            # runs itself — a mismatch means the data and the system
            # understand the constraints differently.
            "f1_excluded": sorted(f1_excluded[u]),
        }

    # Closeness, then a global standardisation. Global rather than per person:
    # standardising per person would force everyone to the same number of
    # `thich` answers, and lose the difference between a fussy eater and an
    # easy one.
    s: dict[tuple[str, int], float] = {}
    for profile in profiles:
        u = profile["user_id"]
        t = people[u]["vector_khau_vi"]
        for i, food in enumerate(foods):
            s[(u, i)] = cosine(t, food["vector"])
    values = list(s.values())
    mean = sum(values) / len(values)
    sd = math.sqrt(
        sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    ) or 1.0

    # `chua_biet` is drawn first and independently — it must not see `s`.
    unknown = {
        (p["user_id"], i): rnd.random() < q[i]
        for p in profiles for i in range(len(foods))
    }

    # Ordered logit. `ε` is drawn for every pair and the cutpoints taken as
    # quantiles, so the marginal shares match the targets by construction
    # rather than after trying several seeds.
    y: dict[tuple[str, int], float] = {}
    for key, value in s.items():
        if unknown[key]:
            continue
        # Logistic(0, 1) by inverse-CDF transform. `random()` returns [0, 1)
        # so 0 is a possible value; clamp into the open interval so `log` does
        # not blow up.
        p = min(max(rnd.random(), 1e-12), 1.0 - 1e-12)
        y[key] = beta * (value - mean) / sd + math.log(p / (1.0 - p))

    sorted_y = sorted(y.values())
    cut1 = sorted_y[
        int(round(MARGINAL_SHARES["khong_thich"] * len(sorted_y)))
    ]
    cut2 = sorted_y[
        int(round(
            (MARGINAL_SHARES["khong_thich"] + MARGINAL_SHARES["binh_thuong"])
            * len(sorted_y)
        ))
    ]

    rows: list[dict[str, str]] = []
    for profile in profiles:
        u = profile["user_id"]
        # A DIFFERENT ORDER per person, and this is not a presentation matter.
        #
        # With one fixed order for everyone, `nguoi.n_tin_hieu` — the number
        # of signals accumulated at swipe time, which `ml/dataset.py` feeds in
        # as a feature — becomes **an identifier of the food**: swipe number i
        # is always the same food for everyone. Measured on a run with a fixed
        # order: 42 of 43 `n_tin_hieu` levels map to only 1-4 of the 45 foods,
        # and the mean label per level runs from 0.25 to 0.73. All three
        # algorithms leaned on that feature hardest, meaning they were reading
        # the food off the counter rather than off the feature vector — and
        # that advantage **does not carry over to serving time**, where
        # `GET /onboarding/survey` returns a per-person F1-filtered deck so
        # position is no longer the food.
        #
        # Shuffling the order is also standard survey practice (randomise
        # order to avoid order effects), so the paper form for real people
        # should print a different order per person too.
        person_order = list(range(len(foods)))
        rnd.shuffle(person_order)
        excluded = set(f1_excluded[u])
        for i in person_order:
            food = foods[i]
            if unknown[(u, i)]:
                choice = "chua_biet"
            else:
                yv = y[(u, i)]
                choice = (
                    "khong_thich" if yv < cut1
                    else "binh_thuong" if yv < cut2
                    else "thich"
                )
            # The overwrite happens AFTER the taste-based draw, not instead of
            # it: `t_u` and `y` remain the true taste, and only what is
            # **written on the form** carries the constraint. That is exactly
            # the situation a paper form creates, and the one F1-at-import has
            # to undo.
            if food["id"] in excluded:
                choice = (
                    "khong_thich"
                    if rnd.random() < P_EXCLUDED_AS_DISLIKE
                    else "chua_biet"
                )
            rows.append(
                {
                    "user_id": u,
                    "source_profile_row": profile["source_profile_row"],
                    "ma_mon": food["id"],
                    "ten_mon": food["name"],
                    "nhom": food["category"],
                    "muc_cay": str(food["spice_level"]),
                    "lua_chon": choice,
                }
            )

    return {
        "hang": rows,
        "su_that": {
            "_doc": (
                "SIMULATED DATA. `vector_khau_vi` is the latent vector used "
                "to generate the swipes in hanh_vi.csv; Chapter 3 compares "
                "the Rocchio profile recovered from them against it. Not "
                "real people's data."
            ),
            "feature_version": json.loads(DECK.read_text(encoding="utf-8"))[
                "feature_version"
            ],
            "ten_chieu": labels,
            "params": {
                "seed": seed,
                "so_nguyen_mau": n_archetypes,
                "lam_nguyen_mau_phu": lambda_secondary,
                "sigma": sigma,
                "beta": beta,
                "bien_do_ho_so": profile_amplitude,
                "diem_cat": [round(cut1, 6), round(cut2, 6)],
                "ti_le_bien_muc_tieu": MARGINAL_SHARES,
                "ti_le_chua_biet": UNKNOWN_SHARE,
            },
            "nguyen_mau": archetype_labels,
            "nguoi": people,
        },
    }


# -- preview ---------------------------------------------------------------


def preview(result: dict[str, Any], foods: list[dict[str, Any]]) -> None:
    rows = result["hang"]
    truth = result["su_that"]
    print(f"{len(truth['nguoi'])} people x {len(foods)} foods = "
          f"{len(rows)} swipes")

    counts = {k: 0 for k in LEVELS}
    for row in rows:
        counts[row["lua_chon"]] += 1
    print(
        "  distribution:",
        "  ".join(
            f"{k}={counts[k]} ({counts[k]/len(rows):.1%})" for k in LEVELS
        ),
    )

    print(f"\n{len(truth['nguyen_mau'])} taste archetypes:")
    for arch in truth["nguyen_mau"]:
        members = [
            u for u, v in truth["nguoi"].items()
            if v["nguyen_mau"] == arch["chi_so"]
        ]
        print(
            f"  #{arch['chi_so']} · {arch['so_mon_trong_cum']:>2} foods · "
            f"{len(members):>2} people · nearest: "
            f"{', '.join(arch['mon_dai_dien'])}"
        )

    constrained = [
        u for u, v in truth["nguoi"].items() if v["f1_excluded"]
    ]
    print(
        f"\nhealth constraints · {len(constrained)}/{len(truth['nguoi'])} "
        f"people have at least one food excluded by F1:"
    )
    condition_counts: dict[str, int] = {}
    for v in truth["nguoi"].values():
        for name in v["condition_names"]:
            condition_counts[name] = condition_counts.get(name, 0) + 1
    # The range printed is the TOTAL foods excluded for each person carrying
    # that condition, not the foods that condition alone excludes: a person
    # may carry two conditions. A peanut allergy by itself excludes 2 foods;
    # someone carrying it who shows "12" has another constraint as well.
    for name, count in sorted(condition_counts.items(), key=lambda kv: -kv[1]):
        excluded_counts = [
            len(v["f1_excluded"]) for v in truth["nguoi"].values()
            if name in v["condition_names"]
        ]
        print(
            f"  {name:<24} {count:>2} people · total foods excluded for "
            f"them: {min(excluded_counts)}-{max(excluded_counts)}"
        )
    total_excluded = sum(
        len(v["f1_excluded"]) for v in truth["nguoi"].values()
    )
    print(
        f"  -> F1 excludes {total_excluded}/{len(rows)} swipes "
        f"({total_excluded / len(rows):.1%}); these were overwritten to "
        f"`khong_thich`\n     in hanh_vi.csv and the importer will undo them."
    )

    # `thich` counts per person: the simulation must produce both fussy and
    # easy eaters.
    per_user: dict[str, int] = {}
    for row in rows:
        if row["lua_chon"] == "thich":
            per_user[row["user_id"]] = per_user.get(row["user_id"], 0) + 1
    sorted_counts = sorted(per_user.values())
    print(
        f"\n`thich` count per person: {sorted_counts[0]} … "
        f"{sorted_counts[-1]} (median "
        f"{sorted_counts[len(sorted_counts)//2]}) — original file: 10 … 22"
    )


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="write the output files")
    parser.add_argument("--db", default=None,
                        help="a different database name, for trial runs")
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--archetypes", type=int, default=5,
                        dest="n_archetypes")
    parser.add_argument(
        "--secondary-weight", type=float, default=0.5, dest="lambda_secondary",
        help="the secondary archetype's weight λ (0 = one archetype only)",
    )
    parser.add_argument("--sigma", type=float, default=0.12)
    parser.add_argument("--beta", type=float, default=2.2)
    parser.add_argument(
        "--profile-influence", type=float, default=0.10,
        dest="profile_amplitude",
    )
    args = parser.parse_args()

    if args.n_archetypes < 2:
        raise SystemExit("--archetypes must be at least 2.")
    if (args.sigma < 0 or args.beta < 0 or args.profile_amplitude < 0
            or args.lambda_secondary < 0):
        raise SystemExit(
            "--sigma, --beta, --profile-influence and --secondary-weight "
            "must not be negative."
        )

    foods = load_deck(DECK)
    profiles = load_profiles(PROFILES_CSV)
    if args.n_archetypes > len(foods):
        raise SystemExit(
            f"--archetypes must not exceed the food count ({len(foods)})."
        )

    cn = connect(args.db)
    try:
        result = generate(
            cn=cn,
            foods=foods,
            profiles=profiles,
            n_archetypes=args.n_archetypes,
            lambda_secondary=args.lambda_secondary,
            sigma=args.sigma,
            beta=args.beta,
            profile_amplitude=args.profile_amplitude,
            seed=args.seed,
        )
    finally:
        cn.close()
    preview(result, foods)

    if not args.write:
        print("\nPreview only. Add --write to produce:")
        print(f"  {OUT_BEHAVIOUR.relative_to(ROOT)}")
        print(f"  {OUT_GROUND_TRUTH.relative_to(ROOT)}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    columns = (
        "user_id", "source_profile_row", "ma_mon", "ten_mon", "nhom",
        "muc_cay", "lua_chon",
    )
    with OUT_BEHAVIOUR.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(result["hang"])
    OUT_GROUND_TRUTH.write_text(
        json.dumps(result["su_that"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"\nWrote {OUT_BEHAVIOUR.relative_to(ROOT)} and "
        f"{OUT_GROUND_TRUTH.relative_to(ROOT)}."
    )
    print("Verify with: python tools/check_simulation.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
