# -*- coding: utf-8 -*-
"""Check whether the simulated swipe set **carries a learnable signal**.

This file exists because last time it did not. `f1_user_food_behaviors_50x45.csv`
passed every check that existed — exactly 2250 rows, 45 `ma_mon` matching the
deck, four valid `lua_chon` values, no empty cell — and was still uniform noise.
No check examined the data's **statistical content**, only its form, so a
completely useless dataset still reported green.

The checks below compare the dataset against **itself after shuffling**.
Shuffling each person's ratings across the 45 foods destroys every food-user
relationship, but every marginal quantity — the count per level per person, per
food — is preserved. So the difference between the real value and the shuffled
value is the signal alone, with no marginal component mixed in.

Check 5 is the one only simulated data can do: compare the recovered Rocchio
profile against **the latent taste vector that generated the data**. Real
people's data has no such quantity — nobody knows a person's true vector — so
this is exactly where the simulation earns its keep.

Run
───
    python tools/check_simulation.py                       # the simulated file
    python tools/check_simulation.py --compare-original    # plus the original

Note on language: the `lua_chon` values and the keys of `hanh_vi.csv` and
`khau_vi_that.json` stay as they are — they are the contract with
`tools/gen_taste_vectors.py`, `tools/import_swipes.py` and
`tools/import_simulation.py`.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import use_utf8  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ml.rocchio import WEIGHTS, build_profile  # noqa: E402

DECK = ROOT / "data" / "survey" / "survey_deck.json"
SIMULATED = ROOT / "data" / "survey" / "mo_phong" / "hanh_vi.csv"
GROUND_TRUTH = ROOT / "data" / "survey" / "mo_phong" / "khau_vi_that.json"
ORIGINAL = (
    ROOT / "data" / "survey" / "da_dien"
    / "f1_user_food_behaviors_50x45.csv"
)

#: Form `lua_chon` -> `interactions.action`. Kept in one place, because
#: `survey_deck.json` carries this same mapping and if the two drift the check
#: measures something different from what the importer writes to the database.
TO_ACTION = {
    "thich": "like",
    "khong_thich": "dislike",
    "binh_thuong": "neutral",
    "chua_biet": "unknown",
}

#: How many shuffles to take the noise band from. 40 gives a standard error of
#: the noise mean of about 1/√40 ≈ 16% of its own deviation — enough to say
#: "inside the band" or "outside it" while still running in a few seconds.
SHUFFLE_ROUNDS = 40


class DeckSpace:
    """A thin shim so `ml.rocchio.build_profile` runs on the deck's vectors.

    `build_profile` only calls `space.length` and `space.encode(m)`, so no real
    `FeatureSpace` is needed — which means no database is needed. What is
    **being tested** is still the real Rocchio code: the weight formula, how
    `unknown` is dropped, how a zero denominator is handled. Only the food
    encoding is taken ready-made, and that is tested separately by
    `check_feature_parity.py`.
    """

    def __init__(self, vectors: dict[str, list[float]], d: int) -> None:
        self._vectors = vectors
        self.length = d

    def encode(self, food_id: Any) -> list[float]:
        return self._vectors[food_id]


# -- algebra and statistics ------------------------------------------------


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def mean(v: Sequence[float]) -> float:
    return sum(v) / len(v)


def stdev(v: Sequence[float]) -> float:
    if len(v) < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def auc(positive: Sequence[float], negative: Sequence[float]) -> float:
    """Area under the ROC via the Mann-Whitney statistic, handling ties.

    0.5 is chance. AUC rather than accuracy, because accuracy depends on a
    threshold, and a perfectly ranking model can still show low accuracy if
    the threshold is set wrong — two different things, and only the first is
    what is being measured here.
    """
    if not positive or not negative:
        return float("nan")
    total = 0.0
    for x in positive:
        for y in negative:
            total += 1.0 if x > y else 0.5 if x == y else 0.0
    return total / (len(positive) * len(negative))


# -- loading --------------------------------------------------------------


def load_behaviour(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise SystemExit(
            f"{path} not found.\n"
            "Generate it first: python tools/gen_taste_vectors.py --write"
        )
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    ratings: dict[str, dict[str, str]] = {}
    for row in rows:
        choice = row["lua_chon"].strip()
        if choice not in TO_ACTION:
            raise SystemExit(
                f"`lua_chon` = {choice!r} is not valid in {path.name}"
            )
        ratings.setdefault(row["user_id"], {})[row["ma_mon"]] = choice
    return ratings


# -- the measurements -----------------------------------------------------

SCORE = {
    "thich": 1.0, "binh_thuong": 0.0, "khong_thich": -1.0, "chua_biet": None,
}


def user_user_cosine(
    ratings: dict[str, dict[str, str]], foods: list[str]
) -> float:
    """Mean cosine over every pair of people, on the foods both have rated."""
    users = sorted(ratings)
    values: list[float] = []
    for i, a in enumerate(users):
        for b in users[i + 1:]:
            shared = [
                k
                for k in foods
                if SCORE[ratings[a][k]] is not None
                and SCORE[ratings[b][k]] is not None
            ]
            if len(shared) < 5:
                continue
            x = [SCORE[ratings[a][k]] for k in shared]
            y = [SCORE[ratings[b][k]] for k in shared]
            if any(x) and any(y):
                values.append(cosine(x, y))
    return mean(values) if values else float("nan")


def variance_ratio(
    ratings: dict[str, dict[str, str]], foods: list[str], level: str
) -> float:
    """Variance of the `level` count per food, over the binomial variance.

    1.0 means the foods differ no more than chance would produce — that is,
    no food is liked more than any other.
    """
    n = len(ratings)
    counts = [
        sum(1 for u in ratings if ratings[u][k] == level) for k in foods
    ]
    p = sum(counts) / (len(foods) * n)
    binomial = n * p * (1 - p)
    if binomial == 0:
        return float("nan")
    return (stdev(counts) ** 2) / binomial


def shuffle_within_user(
    ratings: dict[str, dict[str, str]], foods: list[str],
    rnd: random.Random,
) -> dict[str, dict[str, str]]:
    """Shuffle **each person's** ratings across the foods. Marginals preserved."""
    return {
        u: dict(zip(
            foods, rnd.sample([ratings[u][k] for k in foods], len(foods))
        ))
        for u in ratings
    }


def rocchio_auc(
    ratings: dict[str, dict[str, str]],
    vectors: dict[str, list[float]],
    foods: list[str],
    truth: dict[str, Any] | None = None,
) -> tuple[float, int]:
    """AUC of the Rocchio profile, leave-one-out.

    For each rated food, build `p_u` from the **other 44 foods** and then score
    the held-out one. Without leave-one-out the food to be predicted is already
    inside the vector doing the scoring, and the AUC would be high from label
    leakage rather than from the model being right.
    """
    space = DeckSpace(vectors, len(next(iter(vectors.values()))))
    positive: list[float] = []
    negative: list[float] = []
    for u, choices in ratings.items():
        # Drop the foods F1 would not let this person eat, as the real system
        # does. Keeping them inflates the measurement emptily: the preference
        # vector is then contaminated with the same constraint, so it predicts
        # `khong_thich` correctly on exactly those foods while knowing nothing
        # about taste.
        excluded = set(
            ((truth or {}).get("nguoi", {}).get(u) or {}).get("f1_excluded")
            or ()
        )
        rated = [
            k for k in foods
            if choices[k] != "chua_biet" and k not in excluded
        ]
        for held in rated:
            if choices[held] == "binh_thuong":
                continue  # neutral belongs to neither class in this comparison
            swipes = [
                (k, TO_ACTION[choices[k]]) for k in rated if k != held
            ]
            profile = build_profile(space, swipes)
            if profile.is_empty:
                continue
            score = cosine(profile.weights, vectors[held])
            (positive if choices[held] == "thich" else negative).append(score)
    return auc(positive, negative), len(positive) + len(negative)


def latent_recovery(
    ratings: dict[str, dict[str, str]],
    vectors: dict[str, list[float]],
    foods: list[str],
    truth: dict[str, Any],
) -> dict[str, float]:
    """`cos(p_u, t_u)` per person: how well Rocchio recovers the latent vector.

    The vector is built **after F1 filtering**, because that is the vector the
    real system uses: `import_simulation.py` and `import_swipes.py` both run F1
    before calling `build_profile`, so the row in `user_preference_profiles`
    holds the filtered vector. Measuring the unfiltered one would measure a
    quantity that exists nowhere in the system.

    Comparing the two ways of building it is `f1_before_after`'s job (check 7).
    """
    space = DeckSpace(vectors, len(next(iter(vectors.values()))))
    out: dict[str, float] = {}
    for u, choices in ratings.items():
        person = truth["nguoi"].get(u)
        if person is None:
            continue
        excluded = set(person.get("f1_excluded") or ())
        swipes = [
            (k, TO_ACTION[choices[k]]) for k in foods if k not in excluded
        ]
        profile = build_profile(space, swipes)
        if not profile.is_empty:
            out[u] = cosine(profile.weights, person["vector_khau_vi"])
    return out


def f1_before_after(
    ratings: dict[str, dict[str, str]],
    vectors: dict[str, list[float]],
    foods: list[str],
    truth: dict[str, Any],
) -> tuple[list[float], list[float], int]:
    """`cos(p_u, t_u)` **without F1** against **with F1**, for constrained people.

    This is the measurement that justifies the F1 filtering step in
    `import_swipes.py` and `import_simulation.py`, and it is only possible on
    simulated data: it needs `t_u`, the person's **true** taste, which nobody
    knows for real people's data.

    The survey deck is one fixed deck for everyone, so a vegan is forced to
    rate beef pho too and marks it `khong_thich`. The Rocchio profile
    `p_u = Σ w·v / Σ|w|` then subtracts the vectors of the 24 foods they are
    **not allowed to eat**, and the result is a vector pointing away from every
    meat dish — reading as "dislikes meat" rather than "is vegan". Filtering by
    F1 before building the vector removes exactly that part.

    Returns `(cos without filtering, cos with filtering, number of constrained
    people)`, the two lists in the same person order.
    """
    space = DeckSpace(vectors, len(next(iter(vectors.values()))))
    unfiltered: list[float] = []
    filtered: list[float] = []
    for u in sorted(ratings):
        person = truth["nguoi"].get(u) or {}
        excluded = set(person.get("f1_excluded") or ())
        if not excluded:
            continue
        t = person["vector_khau_vi"]
        choices = ratings[u]

        before = build_profile(
            space, [(k, TO_ACTION[choices[k]]) for k in foods]
        )
        after = build_profile(
            space,
            [(k, TO_ACTION[choices[k]]) for k in foods if k not in excluded],
        )
        if before.is_empty or after.is_empty:
            continue
        unfiltered.append(cosine(before.weights, t))
        filtered.append(cosine(after.weights, t))
    return unfiltered, filtered, len(unfiltered)


def within_between_cluster(
    ratings: dict[str, dict[str, str]], foods: list[str],
    truth: dict[str, Any],
) -> tuple[float, float]:
    """Mean cosine for pairs sharing a primary archetype, and for pairs not."""
    users = sorted(ratings)
    same: list[float] = []
    different: list[float] = []
    for i, a in enumerate(users):
        for b in users[i + 1:]:
            shared = [
                k
                for k in foods
                if SCORE[ratings[a][k]] is not None
                and SCORE[ratings[b][k]] is not None
            ]
            x = [SCORE[ratings[a][k]] for k in shared]
            y = [SCORE[ratings[b][k]] for k in shared]
            if not any(x) or not any(y):
                continue
            c = cosine(x, y)
            same_archetype = (
                truth["nguoi"][a]["nguyen_mau"]
                == truth["nguoi"][b]["nguyen_mau"]
            )
            (same if same_archetype else different).append(c)
    return (
        mean(same) if same else float("nan"),
        mean(different) if different else float("nan"),
    )


# -- running --------------------------------------------------------------


def report(
    name: str,
    ratings: dict[str, dict[str, str]],
    vectors: dict[str, list[float]],
    foods: list[str],
    truth: dict[str, Any] | None,
    *,
    seed: int,
) -> list[tuple[bool, str]]:
    """Print the measurements, return a list of (passed, description)."""
    results: list[tuple[bool, str]] = []
    rnd = random.Random(seed)
    print(f"\n-- {name} -- {len(ratings)} people x {len(foods)} foods")

    counts = collections.Counter(
        v for choices in ratings.values() for v in choices.values()
    )
    total = sum(counts.values())
    print(
        "  distribution: "
        + "  ".join(
            f"{k}={counts[k]} ({counts[k]/total:.1%})"
            for k in SCORE if counts[k]
        )
    )

    # 1. user-user cosine against the noise band
    actual = user_user_cosine(ratings, foods)
    null_values = [
        user_user_cosine(shuffle_within_user(ratings, foods, rnd), foods)
        for _ in range(SHUFFLE_ROUNDS)
    ]
    null_mean, null_sd = mean(null_values), stdev(null_values)
    z = (actual - null_mean) / null_sd if null_sd else float("nan")
    print(
        f"  1. user-user cosine        {actual:+.4f}  "
        f"noise {null_mean:+.4f} +/- {null_sd:.4f}  ->  z = {z:+.1f}"
    )
    results.append(
        (z > 3.0, "user-user cosine clears the noise band (z > 3)")
    )

    # 2. per-food variance against the binomial
    for level in ("thich", "khong_thich"):
        ratio = variance_ratio(ratings, foods, level)
        sd_ratio = math.sqrt(2.0 / (len(foods) - 1))
        z2 = (ratio - 1.0) / sd_ratio
        print(
            f"  2. variance `{level}`/binomial  {ratio:.2f}  "
            f"(1.00 = chance, sd {sd_ratio:.2f})  ->  z = {z2:+.1f}"
        )
        results.append(
            (z2 > 3.0, f"the foods really differ on `{level}` (z > 3)")
        )

    # 3. leave-one-out Rocchio AUC
    area, n = rocchio_auc(ratings, vectors, foods, truth)
    print(
        f"  3. Rocchio AUC (leave-1-out) {area:.3f}  "
        f"over {n} like/dislike swipes"
    )
    results.append(
        (area > 0.60, "Rocchio ranks better than chance (AUC > 0.60)")
    )

    # 4. `chua_biet` must not depend on taste
    if truth is not None:
        unknown_sims: list[float] = []
        rated_sims: list[float] = []
        for u, choices in ratings.items():
            t = truth["nguoi"][u]["vector_khau_vi"]
            for k in foods:
                target = (
                    unknown_sims if choices[k] == "chua_biet" else rated_sims
                )
                target.append(cosine(t, vectors[k]))
        drift = mean(unknown_sims) - mean(rated_sims)
        combined_se = (
            stdev(unknown_sims) / math.sqrt(len(unknown_sims))
            + stdev(rated_sims) / math.sqrt(len(rated_sims))
        )
        print(
            f"  4. closeness of `chua_biet` foods differs by {drift:+.4f} "
            f"(+/- {combined_se:.4f}) from rated foods"
        )
        results.append(
            (
                abs(drift) < 3 * combined_se,
                "`chua_biet` is independent of taste (missing at random)",
            )
        )

        # 5. recovering the latent vector
        per_user = latent_recovery(ratings, vectors, foods, truth)
        recovery = sorted(per_user.values())
        print(
            f"  5. cos(p_u, t_u)           mean {mean(recovery):.3f}  "
            f"(lowest {recovery[0]:.3f} · median "
            f"{recovery[len(recovery)//2]:.3f} · highest {recovery[-1]:.3f})"
        )
        results.append(
            (
                mean(recovery) > 0.50,
                "Rocchio recovers the latent vector (> 0.50)",
            )
        )

        # 6. Cluster structure — the quantity collaborative filtering lives on.
        #
        # It has to be measured separately rather than inferred from check 1:
        # the global mean cosine can be high merely because every taste vector
        # leans the same way (when the secondary-archetype λ is large, for
        # instance) while there is no cluster at all. Only the difference
        # between "same archetype" and "different archetype" is structure.
        same, different = within_between_cluster(ratings, foods, truth)
        print(
            f"  6. cosine same archetype   {same:+.4f}  "
            f"against different {different:+.4f}  ->  {same/different:.1f}x"
        )
        results.append(
            (
                same > 2 * different,
                "there is cluster structure for collaborative filtering (> 2x)",
            )
        )

        # Recovery per archetype, with each cluster's food count. Printed
        # because this is the most useful figure for Chapter 3: it shows that
        # Rocchio recovers a taste IN PROPORTION to how well the deck
        # represents that taste.
        print(
            "     recovery per archetype (cluster food count -> mean cos):"
        )
        grouped: dict[int, list[float]] = {}
        for u, c in per_user.items():
            grouped.setdefault(
                truth["nguoi"][u]["nguyen_mau"], []
            ).append(c)
        cluster_size = {
            arch["chi_so"]: arch["so_mon_trong_cum"]
            for arch in truth["nguyen_mau"]
        }
        for j in sorted(grouped, key=lambda k: -cluster_size[k]):
            representative = next(
                arch["mon_dai_dien"][0]
                for arch in truth["nguyen_mau"]
                if arch["chi_so"] == j
            )
            print(
                f"       #{j} · {cluster_size[j]:>2} foods · "
                f"{mean(grouped[j]):.3f}   ({representative}…)"
            )

        # 7. The F1 filter — the measurement that justifies it.
        unfiltered, filtered, n_constrained = f1_before_after(
            ratings, vectors, foods, truth
        )
        if n_constrained == 0:
            print(
                "  7. nobody has a hard constraint — the F1 filter cannot be\n"
                "     measured. Regenerate with a non-zero CONDITION_QUOTA if\n"
                "     Chapter 3 needs this line."
            )
            results.append(
                (False, "somebody carries a hard constraint so F1 is measurable")
            )
        else:
            # Compared pairwise: the same person, two ways of building the
            # vector. Not two independent means, because person-to-person
            # variation is far larger than the difference F1 makes and would
            # drown the comparison.
            deltas = [b - a for a, b in zip(unfiltered, filtered)]
            delta_mean = mean(deltas)
            stderr = (
                stdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1
                else 0.0
            )
            improved = sum(1 for d in deltas if d > 0)
            print(
                f"  7. the F1 filter over {n_constrained} constrained "
                f"people:\n"
                f"     cos(p_u, t_u) unfiltered {mean(unfiltered):.3f}  ->  "
                f"filtered {mean(filtered):.3f}\n"
                f"     per-person difference {delta_mean:+.3f} +/- "
                f"{stderr:.3f}  ·  better for {improved}/{n_constrained} "
                f"people"
            )
            results.append(
                (
                    delta_mean > 2 * stderr and improved > n_constrained / 2,
                    "filtering by F1 before building the vector brings p_u "
                    "closer to t_u",
                )
            )

    return results


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare-original",
        action="store_true",
        dest="compare",
        help="also measure the original survey file, for comparison",
    )
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    deck = json.loads(DECK.read_text(encoding="utf-8"))
    vectors = {m["id"]: m["vector"] for m in deck["mon"]}
    foods = [
        m["id"] for m in sorted(deck["mon"], key=lambda m: m["thu_tu"])
    ]

    if not GROUND_TRUTH.exists():
        raise SystemExit(
            f"{GROUND_TRUTH} not found.\n"
            "Generate it first: python tools/gen_taste_vectors.py --write"
        )
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    if truth.get("feature_version") != deck.get("feature_version"):
        raise SystemExit(
            f"feature version mismatch: the simulation was generated on "
            f"{truth.get('feature_version')}, the deck is now "
            f"{deck.get('feature_version')}.\nRegenerate: "
            "python tools/gen_taste_vectors.py --write"
        )

    ratings = load_behaviour(SIMULATED)
    missing = set(ratings) - set(truth["nguoi"])
    if missing:
        raise SystemExit(
            f"{len(missing)} people in hanh_vi.csv have no latent vector in "
            f"khau_vi_that.json ({', '.join(sorted(missing)[:3])}…) — the two "
            "files are not from the same generation run."
        )

    results = report(
        "SIMULATION", ratings, vectors, foods, truth, seed=args.seed
    )

    if args.compare and ORIGINAL.exists():
        original_results = report(
            "ORIGINAL SURVEY (for comparison)",
            load_behaviour(ORIGINAL), vectors, foods, None, seed=args.seed,
        )
        print(
            "\n  The original file has no latent vector, so checks 4, 5 and 6 "
            "do not apply to it."
        )
        # The negative test, and the most important part of this file. A
        # checker that only reports green on good data has proved nothing: it
        # might report green on anything. The original file is known noise, so
        # it MUST fail — and if it does not, the thresholds are too loose,
        # meaning next time another noise set will slip through exactly as
        # this one did.
        original_failed = sum(1 for ok, _ in original_results if not ok)
        if original_failed >= 3:
            print(
                f"  The negative test PASSED: the noise file fails "
                f"{original_failed}/{len(original_results)} of the applicable "
                f"checks."
            )
        else:
            print(
                f"  The negative test FAILED: the noise file fails only "
                f"{original_failed}/{len(original_results)} checks — the "
                f"thresholds are too loose, tighten them before trusting the "
                f"SIMULATION section above."
            )
            results.append(
                (False, "the negative test on the known noise file")
            )

    print(f"\n{'-' * 62}")
    failed = [m for ok, m in results if not ok]
    for ok, m in results:
        print(f"  {'ok  ' if ok else 'FAIL'}  {m}")
    if failed:
        print(
            f"\n{len(failed)}/{len(results)} checks failed — the simulated set "
            f"is not usable yet."
        )
        print(
            "Raise --beta (a clearer signal) or lower --sigma (archetypes"
        )
        print("further apart) in tools/gen_taste_vectors.py, then regenerate.")
        return 1
    print(
        f"\n{len(results)}/{len(results)} checks passed. The simulated set "
        f"carries a learnable signal."
    )
    print(
        "To repeat: this is SIMULATED data, and must be written up as such in "
        "Chapter 3."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
