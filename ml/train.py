#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Train the global model — three algorithms, written to `ml_models`.

The three algorithms of `ML_PIPELINE.md` section 6.2 and the role each plays:

| Algorithm | Role |
|---|---|
| `logistic_regression` | Linear baseline. Explainable via coefficients, hard to overfit |
| `random_forest` | Captures non-linear interactions. Provides `feature_importance` |
| `gradient_boosting` | Usually best on tabular data, needs more careful tuning |

**The problem is framed as classification, not regression** — worth stating
plainly at the defence. The label is a real number in [0, 1], so regression
looks more natural. But `logistic_regression` is a classifier, and all three
algorithms have to score **on one scale** to be comparable with each other
and with Rocchio. Hence:

- train binary classification on `label >= 0.5` (see
  `dataset.LIKE_THRESHOLD`);
- **the preference score is `predict_proba[:, 1]`** — the probability of the
  "liked" class, already in [0, 1], the same scale as Stage 1's
  `(1 + cos) / 2`.

Framing it this way still allows `mae` and `rmse` to be measured by comparing
the probability against the *continuous* label, while `f1` and `auc` are
measured against the binary one. All eight `ml_evaluations` metrics are
usable without training two models.

**Two things that must be stored, not optional:**

`scaler_params` — a model trained on standardised data must be standardised
with **exactly those parameters** at inference. Recomputing the mean and
scale over new data is a silent error that drifts scores over time. Here
`scaler_params` holds both the `StandardScaler` parameters **and** the six
min-max parameters of the food feature space, because without the latter the
food vector itself is already different.

`feature_version` — changing a dimension of the vector without bumping this
means an old model gets reloaded against a different vector, and nobody finds
out.

Run:
    python -m ml.train --dataset d1                 # dry run, writes nothing
    python -m ml.train --dataset d1 --apply         # train all three, store
    python -m ml.train --dataset d1 --apply --activate gradient_boosting
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .dataset import (
    LIKE_THRESHOLD,
    FeatureSet,
    load_feature_set,
    load_space,
    summary,
)
from .db import connect, use_utf8
from .features import FEATURE_VERSION

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "ml" / "artifacts"

#: Hyperparameters. Kept modest and fixed rather than grid-searched: at this
#: project's sample size a hyperparameter search would fit the test set
#: itself and the reported numbers would lose their meaning. With more data,
#: add the `val` set here — the `split` column already reserves room for it.
HYPERPARAMS: dict[str, dict[str, Any]] = {
    "logistic_regression": {
        "max_iter": 2000,
        "C": 1.0,
        "solver": "lbfgs",
    },
    "random_forest": {
        "n_estimators": 300,
        # Cap the depth and require at least 2 samples per leaf: with a few
        # thousand samples over 52 features, unbounded trees memorise
        # individual samples.
        "max_depth": 12,
        "min_samples_leaf": 2,
        "n_jobs": -1,
    },
    "gradient_boosting": {
        "n_estimators": 200,
        "learning_rate": 0.05,
        "max_depth": 3,
        "subsample": 0.9,
    },
}

#: Short codes used to build `ml_models.version` — the column allows only 20
#: characters.
SHORT_CODE = {
    "logistic_regression": "lr",
    "random_forest": "rf",
    "gradient_boosting": "gb",
}


def _classifier(algorithm: str, seed: int):
    params = dict(HYPERPARAMS[algorithm])
    if algorithm == "logistic_regression":
        return LogisticRegression(random_state=seed, **params)
    if algorithm == "random_forest":
        return RandomForestClassifier(random_state=seed, **params)
    if algorithm == "gradient_boosting":
        return GradientBoostingClassifier(random_state=seed, **params)
    raise ValueError(f"unknown algorithm: {algorithm!r}")


@dataclass
class TrainResult:
    algorithm: str
    version: str
    n_train: int
    n_test: int
    artifact_path: Path
    feature_importance: dict[str, float]
    scaler_params: dict[str, Any]
    #: A few numbers for a quick look. The official figures are written to
    #: `ml_evaluations` by `ml/evaluate.py`, alongside the four baselines.
    quick_metrics: dict[str, float]


def _next_version(cn, algorithm: str, dataset: str) -> str:
    """`lr-d1-1`, `lr-d1-2`, ... — unique, and readable at a glance."""
    prefix = f"{SHORT_CODE[algorithm]}-{dataset}-"
    with cn.cursor() as cur:
        cur.execute(
            "SELECT version FROM ml_models WHERE version LIKE %s", (prefix + "%",)
        )
        existing = {d["version"] for d in cur.fetchall()}
    i = 1
    while f"{prefix}{i}" in existing:
        i += 1
        if len(f"{prefix}{i}") > 20:
            raise RuntimeError(
                f"Out of room for a version with prefix {prefix!r} "
                f"(the column holds only 20 characters)."
            )
    return f"{prefix}{i}"


def _split_indices(fs: FeatureSet) -> tuple[list[int], list[int]]:
    """Training and test indices taken from the `split` column.

    Uses the `split` column rather than re-splitting: that split was recorded
    with the dataset and is **split by user**. Re-splitting here risks
    cutting one person in half, and the evaluation figure would then be
    inflated because the model has already seen the tested person's taste.

    `val` is folded into the training set because this version performs **no
    hyperparameter search** and therefore needs no separate validation set.
    Stated explicitly so nobody assumes it was used.
    """
    train = [i for i, s in enumerate(fs.split) if s in ("train", "val")]
    test = [i for i, s in enumerate(fs.split) if s == "test"]
    return train, test


def _importances(model, names: Sequence[str]) -> dict[str, float]:
    """`feature_importance` — coefficients for linear models, importances for
    trees.

    For a linear model the **sign** is kept: a negative coefficient means the
    feature pushes toward "not liked", and that is information the
    explanation layer needs. Tree importances have no sign to begin with.
    """
    if hasattr(model, "coef_"):
        values = model.coef_[0]
    elif hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:  # pragma: no cover
        return {}
    pairs = {name: float(v) for name, v in zip(names, values)}
    return dict(sorted(pairs.items(), key=lambda kv: -abs(kv[1])))


def train_one(
    fs: FeatureSet,
    algorithm: str,
    *,
    dataset: str,
    version: str,
    seed: int,
    space_params: dict[str, Any],
    write_file: bool,
) -> TrainResult:
    train, test = _split_indices(fs)
    if not train or not test:
        raise RuntimeError(
            f"The reference split left one side empty "
            f"(train={len(train)}, test={len(test)}). "
            f"The dataset has too few users — at least one per fold is needed."
        )

    X = np.asarray(fs.X, dtype=float)
    y_class = np.asarray(fs.y_class, dtype=int)
    y = np.asarray(fs.y, dtype=float)
    w = np.asarray(fs.sample_weight, dtype=float)

    if len(set(y_class[train].tolist())) < 2:
        raise RuntimeError(
            "The training set holds a single class — a classifier cannot be "
            "trained. Both liked and disliked signals are needed."
        )

    # The scaler is **fitted on the training set only**. Fitting over
    # everything leaks: the mean and scale would then carry information about
    # the test set.
    scaler = StandardScaler().fit(X[train])
    Xs = scaler.transform(X)

    model = _classifier(algorithm, seed)
    model.fit(Xs[train], y_class[train], sample_weight=w[train])

    p_test = model.predict_proba(Xs[test])[:, 1]
    quick_metrics = {
        "mae": float(np.average(np.abs(p_test - y[test]), weights=w[test])),
        "rmse": float(
            np.sqrt(np.average((p_test - y[test]) ** 2, weights=w[test]))
        ),
        "test_like_rate": float(y_class[test].mean()),
    }

    scaler_params = {
        "feature_version": FEATURE_VERSION,
        "kind": "StandardScaler",
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "feature_names": list(fs.feature_names),
        "feature_space": space_params,
        "like_threshold": LIKE_THRESHOLD,
    }

    path = ARTIFACT_DIR / f"{version}.joblib"
    if write_file:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "version": version,
                "algorithm": algorithm,
                "feature_version": FEATURE_VERSION,
                "dataset_version": dataset,
                "scaler": scaler,
                "model": model,
                "feature_names": list(fs.feature_names),
                "feature_space": space_params,
            },
            path,
        )

    return TrainResult(
        algorithm=algorithm,
        version=version,
        n_train=len(train),
        n_test=len(test),
        artifact_path=path,
        feature_importance=_importances(model, fs.feature_names),
        scaler_params=scaler_params,
        quick_metrics=quick_metrics,
    )


SQL_INSERT = """
INSERT INTO ml_models
    (version, algorithm, feature_version, dataset_version, hyperparams,
     scaler_params, feature_importance, n_train, n_test, artifact_path,
     is_active, note)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def write_model(cn, result: TrainResult, dataset: str, activate: bool) -> int:
    with cn.cursor() as cur:
        if activate:
            # Exactly one model serves. Clear the flag on every other model
            # inside the same transaction, otherwise two models end up
            # `is_active` and which one gets picked becomes a matter of row
            # order.
            cur.execute("UPDATE ml_models SET is_active = 0 WHERE is_active = 1")
        cur.execute(
            SQL_INSERT,
            (
                result.version,
                result.algorithm,
                FEATURE_VERSION,
                dataset,
                json.dumps(HYPERPARAMS[result.algorithm], ensure_ascii=False),
                json.dumps(result.scaler_params, ensure_ascii=False),
                json.dumps(result.feature_importance, ensure_ascii=False),
                result.n_train,
                result.n_test,
                str(result.artifact_path.relative_to(ROOT)).replace("\\", "/"),
                1 if activate else 0,
                f"Trained from dataset {dataset}, split by user.",
            ),
        )
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        return int(cur.fetchone()["id"])


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="the dataset_version to use")
    parser.add_argument(
        "--db", default=None, help="another database name, for trial runs"
    )
    parser.add_argument(
        "--algorithm",
        default="all",
        choices=["all", *HYPERPARAMS],
        help="trains all three by default",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to ml_models and save the model file",
    )
    parser.add_argument(
        "--activate",
        default=None,
        choices=list(HYPERPARAMS),
        help="set is_active = 1 for this algorithm (only with --apply)",
    )
    t = parser.parse_args(argv)

    if t.activate and not t.apply:
        print("--activate can only be used together with --apply.", file=sys.stderr)
        return 1

    cn = connect(t.db)
    try:
        space, foods_by_id = load_space(cn)
        fs = load_feature_set(
            cn, dataset_version=t.dataset, space=space, foods_by_id=foods_by_id
        )
        if not len(fs):
            print(
                f"Dataset {t.dataset!r} holds no samples.\n"
                f"Build it first: python -m ml.build_dataset "
                f"--version {t.dataset} --apply"
            )
            return 1

        print(summary(fs))
        train, test = _split_indices(fs)
        print(
            f"  reference split: train+val {len(train)} samples / "
            f"test {len(test)} samples"
        )
        print()

        algorithms = list(HYPERPARAMS) if t.algorithm == "all" else [t.algorithm]
        for algorithm in algorithms:
            version = (
                _next_version(cn, algorithm, t.dataset)
                if t.apply
                else f"{SHORT_CODE[algorithm]}-dry"
            )
            result = train_one(
                fs,
                algorithm,
                dataset=t.dataset,
                version=version,
                seed=t.seed,
                space_params=space.params(),
                write_file=t.apply,
            )
            print(f"{algorithm}  ({result.version})")
            print(
                f"  n_train={result.n_train}  n_test={result.n_test}  "
                f"mae={result.quick_metrics['mae']:.4f}  "
                f"rmse={result.quick_metrics['rmse']:.4f}"
            )
            top = list(result.feature_importance.items())[:5]
            print(
                "  strongest features: "
                + ", ".join(f"{k} {v:+.3f}" for k, v in top)
            )

            if t.apply:
                model_id = write_model(
                    cn, result, t.dataset, activate=(t.activate == algorithm)
                )
                cn.commit()
                path = str(result.artifact_path.relative_to(ROOT)).replace(
                    "\\", "/"
                )
                print(
                    f"  wrote ml_models.id={model_id}, file {path}"
                    + ("  [is_active = 1]" if t.activate == algorithm else "")
                )
            print()

        if not t.apply:
            print("Dry run — nothing written. Add --apply to store the models.")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
