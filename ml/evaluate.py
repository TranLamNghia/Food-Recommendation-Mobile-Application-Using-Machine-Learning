#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evaluation — five variants, eight metrics, cross-validation by user.

`ml_evaluations` is the most important table of the machine learning part,
and the reason it exists is the `variant` column: the table is designed to
**compare against baselines**, not merely to report one number.

    Not  "the model reaches nDCG@10 = 0.72"
    but  "the model reaches 0.72 against 0.51 for ranking by popularity"

The five variants, ordered by how hard they are to beat:

| `variant` | Scored by |
|---|---|
| `popularity` | `foods.popularity_score` — no personalisation at all |
| `rule_based` | Stage 0 — popularity blended with target macro fit |
| `content_based` | Stage 1 — `(1 + cos(p_u, v_i)) / 2` |
| `hybrid` | `alpha*ML + (1-alpha)*cosine`, alpha from `n_signals` |
| `ml` | Stage 2 — the global model's `predict_proba` |

`popularity` is the trivial baseline that **must** be beaten: if ranking by
popularity performs just as well, there is nothing to report.

**Cross-validation retrains per fold.** The model in `ml_models` was trained
on **one** split. Evaluating it over all five folds would mean four of them
were in its own training set, and the figure would be inflated. So here, for
each fold, the model is **retrained from scratch** on the remaining folds.
The result row's `model_id` therefore identifies the **configuration**
(algorithm, feature version, dataset version, hyperparameters) rather than a
particular `.joblib` file.

**The split is by user.** The proposal's commitment is effectiveness for
*every* user, not luck on one split. `fold` stores each fold's result so the
report can give mean +/- standard deviation. `build_dataset` already assigns
folds by person, so one person is never on both sides.

**Ranking metrics are computed per user, then averaged.** Pooling every
sample from every user into one list and computing `precision@5` is wrong:
the user never sees such a mixed list. `k_value` exists because they only
see 4-6 servings a day; `precision` over all 318 foods says nothing.

Run:
    python -m ml.evaluate --dataset d1 --model gb-d1-1            # dry run
    python -m ml.evaluate --dataset d1 --model gb-d1-1 --apply
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from . import popularity, scoring
from .dataset import (
    LIKE_THRESHOLD,
    FeatureSet,
    load_feature_set,
    load_space,
    summary,
)
from .db import connect, use_utf8
from .rocchio import alpha
from .train import HYPERPARAMS, _classifier

VARIANTS = ("popularity", "rule_based", "content_based", "hybrid", "ml")

#: The reported k values. 5 because the user sees 4-6 servings a day; 10 to
#: show how the metric moves when the list is widened.
K_VALUES = (5, 10)


# ── Scoring each variant ──────────────────────────────────────────────


#
# The four functions below **implement no formula**: they only call
# `ml/scoring.py` for each sample. That is deliberate — `ml/serve.py` calls
# the same functions when serving real users, so the numbers reported in
# Chapter 3 and the scores users actually receive come from the same code. If
# each side reimplemented the formula they could drift apart unnoticed: both
# would run, both would return numbers in [0, 1], they would simply describe
# two different systems.


def _popularity_scores(
    fs: FeatureSet, indices: Sequence[int], popularity_by_food: dict[str, float]
) -> np.ndarray:
    return np.asarray(
        [
            scoring.popularity_score(popularity_by_food.get(fs.food_id[i], 0.0))
            for i in indices
        ],
        dtype=float,
    )


def _rule_scores(
    fs: FeatureSet, indices: Sequence[int], popularity_by_food: dict[str, float]
) -> np.ndarray:
    return np.asarray(
        [
            scoring.rule_score(
                fs.food_vector[i],
                fs.target_macro[i],
                popularity_by_food.get(fs.food_id[i], 0.0),
            )
            for i in indices
        ],
        dtype=float,
    )


def _content_scores(fs: FeatureSet, indices: Sequence[int]) -> np.ndarray:
    """Stage 1, with `p_u` taken from the **snapshot**, not the current
    vector."""
    return np.asarray(
        [scoring.content_score(fs.p_u[i], fs.food_vector[i]) for i in indices],
        dtype=float,
    )


def _blended_scores(
    ml_scores: np.ndarray,
    content: np.ndarray,
    fs: FeatureSet,
    indices: Sequence[int],
) -> np.ndarray:
    """`alpha*ML + (1-alpha)*cosine`, alpha from **each sample's** `n_signals`.

    Alpha per sample, not per person: a snapshot's `n_signals` grows over
    time, so an early signal from the same person has to be blended more
    lightly than a later one. Blending per person applies the future's alpha
    to the past.
    """
    return np.asarray(
        [
            scoring.blend(float(ml), float(c), fs.n_signals[i])
            for ml, c, i in zip(ml_scores, content, indices)
        ],
        dtype=float,
    )


# ── Metrics ───────────────────────────────────────────────────────────


def _dcg(gains: Sequence[float]) -> float:
    return sum(g / math.log2(j + 2) for j, g in enumerate(gains))


@dataclass
class RankingMetrics:
    precision: float
    recall: float
    ndcg: float
    #: How many users actually contributed to the average — users with
    #: nothing worth recommending are skipped, and how many were skipped has
    #: to be stated.
    n_users: int


def ranking_metrics(
    scores: np.ndarray,
    continuous_labels: np.ndarray,
    class_labels: np.ndarray,
    users: Sequence[str],
    k: int,
) -> RankingMetrics:
    """`precision@k`, `recall@k`, `ndcg@k` — per user, then averaged.

    A user with **no** food at `label >= 0.5` is dropped from all three
    metrics: their `recall` is an undefined 0/0, and their `precision` is
    always 0 however the model ranks — including them would make every
    variant worse by the same amount and distinguish nothing.

    `ndcg` uses **graded gain** from the continuous label rather than the
    binary one: a 5-star rating (1.000) deserves to rank above a kept serving
    (0.700), and binary nDCG treats the two as equal.
    """
    by_user: dict[str, list[int]] = defaultdict(list)
    for i, user in enumerate(users):
        by_user[user].append(i)

    precisions, recalls, ndcgs = [], [], []
    for _user, indices in by_user.items():
        if not any(class_labels[i] for i in indices):
            continue
        # Sort by descending score. Ties break on index so the result does
        # not depend on iteration order — `popularity` ties a great deal.
        ranked = sorted(indices, key=lambda i: (-scores[i], i))
        top = ranked[:k]

        hits = sum(int(class_labels[i]) for i in top)
        total_relevant = sum(int(class_labels[i]) for i in indices)

        precisions.append(hits / min(k, len(indices)))
        recalls.append(hits / total_relevant)

        ideal = sorted(
            (float(continuous_labels[i]) for i in indices), reverse=True
        )[:k]
        idcg = _dcg(ideal)
        dcg = _dcg([float(continuous_labels[i]) for i in top])
        ndcgs.append(dcg / idcg if idcg > 0 else 0.0)

    if not precisions:
        return RankingMetrics(0.0, 0.0, 0.0, 0)
    return RankingMetrics(
        float(np.mean(precisions)),
        float(np.mean(recalls)),
        float(np.mean(ndcgs)),
        len(precisions),
    )


def mean_average_precision(
    scores: np.ndarray, class_labels: np.ndarray, users: Sequence[str]
) -> tuple[float, int]:
    """`MAP` — average precision over each user's **whole** list.

    No `k`, because MAP runs to every position: it penalises a relevant food
    pushed to the bottom, which `precision@5` never sees.
    """
    by_user: dict[str, list[int]] = defaultdict(list)
    for i, user in enumerate(users):
        by_user[user].append(i)

    per_user = []
    for indices in by_user.values():
        total_relevant = sum(int(class_labels[i]) for i in indices)
        if total_relevant == 0:
            continue
        ranked = sorted(indices, key=lambda i: (-scores[i], i))
        hits = 0
        running = 0.0
        for position, i in enumerate(ranked, start=1):
            if class_labels[i]:
                hits += 1
                running += hits / position
        per_user.append(running / total_relevant)

    return (float(np.mean(per_user)) if per_user else 0.0), len(per_user)


def regression_metrics(
    scores: np.ndarray, labels: np.ndarray, weights: np.ndarray
) -> tuple[float, float]:
    """`mae`, `rmse` — weighted by `sample_weight`.

    Weighted because `sample_weight` encodes the label's **confidence**:
    being 0.3 out on a 5-star rating is more serious than being 0.3 out on a
    skipped serving, where the label was itself a guess.
    """
    mae = float(np.average(np.abs(scores - labels), weights=weights))
    rmse = float(np.sqrt(np.average((scores - labels) ** 2, weights=weights)))
    return mae, rmse


def classification_metrics(
    scores: np.ndarray, class_labels: np.ndarray
) -> tuple[float, float]:
    """`f1`, `auc`.

    `f1` needs a threshold; `LIKE_THRESHOLD` is used so it matches how the
    labels were made. Note that `popularity` and `rule_based` score within a
    narrow band and may fall entirely on one side of the threshold — their
    `f1` then degenerates, while `auc` still measures something because it
    only looks at **order**. That is why both are reported.
    """
    predictions = (scores >= LIKE_THRESHOLD).astype(int)
    f1 = float(f1_score(class_labels, predictions, zero_division=0))
    auc = (
        float(roc_auc_score(class_labels, scores))
        if len(set(class_labels.tolist())) > 1
        else float("nan")
    )
    return f1, auc


# ── Running one fold ──────────────────────────────────────────────────


def _train_fold(
    fs: FeatureSet, algorithm: str, train: Sequence[int], seed: int, X: np.ndarray
):
    y_class = np.asarray(fs.y_class, dtype=int)
    w = np.asarray(fs.sample_weight, dtype=float)

    if len({int(y_class[i]) for i in train}) < 2:
        return None, None

    scaler = StandardScaler().fit(X[train])
    model = _classifier(algorithm, seed)
    model.fit(scaler.transform(X[train]), y_class[train], sample_weight=w[train])
    return model, scaler


def _popularity_column(fs: FeatureSet) -> int:
    """The position of the `food.popularity` column in the feature matrix.

    Looked up **by name** rather than counted by hand: adding a dimension to
    the food vector shifts this column, and a hard-coded index would silently
    overwrite a different feature.
    """
    return fs.feature_names.index("food.popularity")


def evaluate_fold(
    fs: FeatureSet, algorithm: str, fold: int, seed: int
) -> dict[tuple[str, str, int], float]:
    """Return `{(variant, metric, k): value}` for one fold."""
    train = [i for i, f in enumerate(fs.fold) if f != fold]
    # `random_neg` is **for training only, never for evaluation.**
    #
    # A random negative is a food that was **never shown** to that person, so
    # it is not an observed preference but a guess — section 9 gives it
    # weight 0.200, the lowest of the seven sources, for that reason.
    #
    # Keeping it in the evaluation set would also break the comparison: a
    # food nobody has seen has popularity 0, so **any** variant that uses
    # popularity can separate the random negatives from the real signals
    # without knowing anything about taste. The leak canary caught this:
    # after the per-fold popularity fix, `popularity` still reached
    # nDCG@5 = 0.549 on entirely random labels, purely by telling "shown"
    # from "not shown" apart.
    #
    # The negatives stay in the **training** set: without them the model only
    # sees foods the system chose to display and learns to reproduce the
    # system's own filter instead of learning taste.
    test = [
        i
        for i, f in enumerate(fs.fold)
        if f == fold and fs.source[i] != "random_neg"
    ]
    if not test or not train:
        return {}

    # ── Popularity rebuilt from the TRAINING folds alone ──
    #
    # Not `foods.popularity_score`: that column is computed from every
    # signal, including signals from users in the test fold. A food that the
    # tested user liked has already pushed its own popularity up, so
    # "popularity" would carry information about the test set's labels. The
    # leak canary caught exactly this: on entirely random labels,
    # `popularity` still reached nDCG@5 = 0.796 and the model's AUC jumped
    # from 0.48 to 0.67.
    #
    # It is also written over the matrix's `food.popularity` column, because
    # the model uses that feature and leaks along with it.
    popularity_by_food = popularity.from_samples(
        fs.user_id,
        fs.food_id,
        fs.y,
        fs.source,
        train,
        positive_threshold=LIKE_THRESHOLD,
    )
    X = np.asarray(fs.X, dtype=float)
    X[:, _popularity_column(fs)] = [
        popularity_by_food.get(f, 0.0) for f in fs.food_id
    ]

    model, scaler = _train_fold(fs, algorithm, train, seed, X)

    y = np.asarray([fs.y[i] for i in test], dtype=float)
    y_class = np.asarray([fs.y_class[i] for i in test], dtype=int)
    w = np.asarray([fs.sample_weight[i] for i in test], dtype=float)
    users = [fs.user_id[i] for i in test]

    content = _content_scores(fs, test)
    ml_scores = (
        model.predict_proba(scaler.transform(X[test]))[:, 1]
        if model is not None
        # This fold's training set holds a single class, so there is no
        # model. Give the neutral score rather than dropping the whole fold:
        # the baselines are still measurable, and the `ml` row shows up as
        # meaningless instead of disappearing.
        else np.full(len(test), 0.5)
    )

    scores = {
        "popularity": _popularity_scores(fs, test, popularity_by_food),
        "rule_based": _rule_scores(fs, test, popularity_by_food),
        "content_based": content,
        "hybrid": _blended_scores(ml_scores, content, fs, test),
        "ml": ml_scores,
    }

    result: dict[tuple[str, str, int], float] = {}
    for variant in VARIANTS:
        s = scores[variant]
        mae, rmse = regression_metrics(s, y, w)
        f1, auc = classification_metrics(s, y_class)
        map_value, _ = mean_average_precision(s, y_class, users)

        result[(variant, "mae", 0)] = mae
        result[(variant, "rmse", 0)] = rmse
        result[(variant, "f1", 0)] = f1
        if not math.isnan(auc):
            result[(variant, "auc", 0)] = auc
        result[(variant, "map", 0)] = map_value

        for k in K_VALUES:
            metrics = ranking_metrics(s, y, y_class, users, k)
            result[(variant, "precision", k)] = metrics.precision
            result[(variant, "recall", k)] = metrics.recall
            result[(variant, "ndcg", k)] = metrics.ndcg

    return result


# ── Writing and presenting ────────────────────────────────────────────

SQL_DELETE = "DELETE FROM ml_evaluations WHERE model_id = %s"
SQL_INSERT = """
INSERT INTO ml_evaluations (model_id, variant, metric, k_value, value, fold)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def write_evaluations(
    cn, model_id: int, by_fold: dict[int, dict[tuple[str, str, int], float]]
) -> int:
    rows = [
        (model_id, variant, metric, k, round(value, 5), fold)
        for fold, table in sorted(by_fold.items())
        for (variant, metric, k), value in sorted(table.items())
    ]
    with cn.cursor() as cur:
        cur.execute(SQL_DELETE, (model_id,))
        deleted = cur.rowcount
        if rows:
            cur.executemany(SQL_INSERT, rows)
    cn.commit()
    if deleted:
        print(f"Deleted {deleted} previous evaluation rows for this model.")
    return len(rows)


def results_table(
    by_fold: dict[int, dict[tuple[str, str, int], float]]
) -> str:
    """Mean +/- standard deviation across folds, one row per variant."""
    gathered: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for table in by_fold.values():
        for key, value in table.items():
            gathered[key].append(value)

    columns = [
        ("ndcg", 5), ("ndcg", 10), ("precision", 5), ("recall", 5),
        ("map", 0), ("auc", 0), ("f1", 0), ("mae", 0), ("rmse", 0),
    ]
    header = "  ".join(
        f"{(metric + ('@' + str(k) if k else '')):>12}" for metric, k in columns
    )
    lines = [f"{'variant':<14}{header}"]
    for variant in VARIANTS:
        cells = []
        for metric, k in columns:
            values = gathered.get((variant, metric, k))
            if not values:
                cells.append(f"{'-':>12}")
            elif len(values) > 1:
                cells.append(
                    f"{np.mean(values):.3f}+-{np.std(values):.3f}".rjust(12)
                )
            else:
                cells.append(f"{values[0]:.3f}".rjust(12))
        lines.append(f"{variant:<14}" + "  ".join(cells))
    return "\n".join(lines)


def degeneracy_warnings(fs: FeatureSet) -> list[str]:
    """Detect a baseline that **cannot rank anything**.

    Why it has to be reported. If `popularity_score` is equal across every
    food, the `popularity` variant imposes no order at all: every food ties,
    and the resulting `precision@5` reflects only **how ties are broken** —
    here by row index, which is to say randomly. It still prints a
    normal-looking number, and that is the dangerous part: section 10.1 makes
    `popularity` the baseline that *must* be beaten, so a degenerate
    `popularity` turns the core research question into a comparison against
    noise.

    Likewise, `hybrid` coincides exactly with `content_based` when every
    sample has `n_signals < 30` — alpha is then 0 by the formula. That is not
    a bug, but it has to be said, otherwise two identical rows in the results
    table read as a copy-paste error.
    """
    warnings: list[str] = []

    # Checked against popularity **rebuilt from the sample set**, not against
    # the `foods.popularity_score` column: that is what the evaluation
    # actually uses, and an already-written column can still be degenerate
    # within this particular sample set.
    rebuilt = popularity.from_samples(
        fs.user_id,
        fs.food_id,
        fs.y,
        fs.source,
        range(len(fs)),
        positive_threshold=LIKE_THRESHOLD,
    )
    levels = set(rebuilt.values())
    if len(levels) <= 1:
        value = next(iter(levels), 0.0)
        warnings.append(
            f"`popularity` is DEGENERATE: every food in the sample set has "
            f"popularity {value:g}. The variant currently ranks nothing — all "
            f"of its metrics are just tie-breaking, so comparing against it "
            f"carries no weight."
        )

    alphas = [alpha(n) for n in fs.n_signals]
    if max(alphas) == 0:
        warnings.append(
            f"`hybrid` coincides exactly with `content_based`: every sample "
            f"has n_signals < 30 so alpha = 0 (the largest is "
            f"{max(fs.n_signals)} signals). Correct per the formula, not a "
            f"bug."
        )
    elif min(alphas) == 1:
        warnings.append(
            "`hybrid` coincides exactly with `ml`: every sample has "
            "n_signals > 100 so alpha = 1."
        )

    return warnings


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--model",
        required=True,
        help="the `ml_models.version` of the configuration to evaluate",
    )
    parser.add_argument("--db", default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--apply", action="store_true")
    t = parser.parse_args(argv)

    cn = connect(t.db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT id, algorithm, dataset_version, feature_version "
                "FROM ml_models WHERE version = %s",
                (t.model,),
            )
            model_row = cur.fetchone()
        if model_row is None:
            print(f"No model has version = {t.model!r}.", file=sys.stderr)
            return 1
        if model_row["algorithm"] not in HYPERPARAMS:
            print(f"Unknown algorithm: {model_row['algorithm']!r}", file=sys.stderr)
            return 1
        if model_row["dataset_version"] != t.dataset:
            print(
                f"Note: model {t.model!r} was trained on dataset "
                f"{model_row['dataset_version']!r} but is being evaluated on "
                f"{t.dataset!r}."
            )

        space, foods_by_id = load_space(cn)
        fs = load_feature_set(
            cn, dataset_version=t.dataset, space=space, foods_by_id=foods_by_id
        )
        if not len(fs):
            print(f"Dataset {t.dataset!r} holds no samples.")
            return 1

        print(summary(fs))
        folds = sorted(set(fs.fold))
        print(f"  {len(folds)}-fold cross-validation, retraining each fold")

        warnings = degeneracy_warnings(fs)
        if warnings:
            print()
            for warning in warnings:
                print("  ! " + warning)
        print()

        by_fold: dict[int, dict[tuple[str, str, int], float]] = {}
        for fold in folds:
            table = evaluate_fold(fs, model_row["algorithm"], fold, t.seed)
            if not table:
                print(f"  fold {fold}: skipped (one side empty)")
                continue
            by_fold[fold] = table
            print(
                f"  fold {fold}: nDCG@5  "
                + "  ".join(
                    f"{variant}={table[(variant, 'ndcg', 5)]:.3f}"
                    for variant in VARIANTS
                )
            )

        if not by_fold:
            print("\nNo fold could be evaluated.")
            return 1

        print()
        print(results_table(by_fold))
        print()

        content = float(
            np.mean(
                [t[("content_based", "ndcg", 5)] for t in by_fold.values()]
            )
        )
        popular = float(
            np.mean([t[("popularity", "ndcg", 5)] for t in by_fold.values()])
        )
        print(
            f"The core research question — does content-based recommendation "
            f"beat popularity?\n"
            f"  nDCG@5: content_based {content:.3f} against popularity "
            f"{popular:.3f} ({content - popular:+.3f})"
        )
        if any("DEGENERATE" in w for w in warnings):
            print(
                "  -> This comparison carries NO weight yet: the "
                "`popularity` baseline is degenerate (see the warning above)."
            )

        if not t.apply:
            total = sum(len(table) for table in by_fold.values())
            print(
                f"\nDry run — nothing written. Add --apply to write {total} "
                f"rows to ml_evaluations."
            )
            return 0

        n = write_evaluations(cn, int(model_row["id"]), by_fold)
        print(
            f"\nWrote {n} rows to ml_evaluations for model_id="
            f"{model_row['id']}."
        )
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
