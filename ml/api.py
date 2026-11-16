# -*- coding: utf-8 -*-
"""ML Service — the four internal endpoints of `API_SPECIFICATION.md` §8.

Before this file, `ml/serve.py` was a **Python library**: runnable from the
command line, but with no way for a C# backend to reach it. That was one of
the two missing seams between the system's three layers, and it blocked
backend waves 4, 5 and 6 — taste survey, meal plan, recommendations — rather
than any shortage of public endpoints.

    POST /predict                     Step 3 — score a candidate set
    POST /profiles/{userId}/rebuild   rebuild the preference vector
    POST /train                       retrain, asynchronously
    GET  /health                      which model is serving

Run:   python tools/run_ml_service.py        -> http://localhost:8000
Check: python tools/smoke_ml_api.py

## Shared-secret authentication, and why there is no default

Every endpoint requires an `X-Internal-Key` header matching the
`ML_INTERNAL_KEY` environment variable. Missing or wrong gives `401`.

**There is deliberately no default key in the source** — the same reasoning
as the backend's `JWT_SIGNING_KEY`: this is a public repository, and a key
committed to a file lets anyone who can read the repo call this service. And
this service reads the database directly, including the `users` table.

The server **stops at startup** if the key is missing, rather than running
wide open. Running wide open looks completely normal until somebody tries.

## One connection per request

The endpoints are plain `def`, not `async`, so FastAPI runs them in a thread
pool. A PyMySQL connection is **not thread-safe**, so each request opens and
closes its own. A single global connection produces "Packet sequence number
wrong" under load — a failure that only appears with concurrent requests,
which is to say never during manual testing.

## Graceful degradation is a contract, not an accident

`/predict` returns `503` when no model is `is_active = 1`, and specification
§8.1 says the backend then **still builds a meal plan** from the rules and
sets `generationSource = "rule_based"`. But `serve.recommend` goes further:
it falls back to Stage 1 by itself and still returns content-based scores. So
`503` here is reserved for the case where **nothing can be scored at all**;
degradation returns `200` with `stage` and `warnings` so the backend knows
which layer the scores came from.

The distinction matters: returning `503` whenever a model is missing would
make the backend drop Stage 1 as well — dropping the personalisation that
**does** work — and fall back to ranking by popularity. Measured on the
simulated set, that is the difference between 0.862 and 0.694 nDCG@5.
"""

from __future__ import annotations

import hmac
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import connect  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.rocchio import alpha, stage as stage_for  # noqa: E402
from ml.serve import load_active_model, rebuild_profile, recommend  # noqa: E402
from ml.time_vn import now_vn  # noqa: E402

KEY_ENV = "ML_INTERNAL_KEY"

#: The algorithms accepted by `POST /train`, exactly the three `ml/train.py`
#: implements.
ALGORITHMS = ("logistic_regression", "random_forest", "gradient_boosting")


# ── Authentication ────────────────────────────────────────────────────


def require_key() -> str:
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"{KEY_ENV} is missing. This service reads the database directly, "
            f"so it does not run wide open.\nSet {KEY_ENV} in .env and start "
            "it with python tools/run_ml_service.py"
        )
    return key


def check_key(x_internal_key: str | None = Header(default=None)) -> None:
    """The shared dependency for every endpoint. Returns `401` in the §2.5
    error envelope."""
    expected = os.environ.get(KEY_ENV, "")
    # Constant-time comparison: `!=` leaks the length of the matching prefix
    # through response time.
    if not x_internal_key or not hmac.compare_digest(x_internal_key, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing or incorrect X-Internal-Key header.",
            },
        )


# ── Request and response schemas ──────────────────────────────────────


class UserFeatures(BaseModel):
    """The `userFeatures` block from §8.1.

    **Accepted but not used for scoring, deliberately.** This service reads
    the health profile straight from `health_profiles` — the same database
    the backend writes — so the data in the request body is a copy of
    something already available. Scoring from the copy means that when the
    two drift apart, the scores and the profile shown to the user no longer
    describe the same person, and nothing reports it.

    Kept in the schema to match the specification and to spare the backend a
    change, but `/predict` **cross-checks** it against the database and
    returns any mismatch in `warnings` instead of ignoring it silently.
    """

    age: int | None = None
    gender: str | None = None
    bmi: float | None = None
    activityLevel: str | None = None
    goal: str | None = None
    remainingCaloriesKcal: float | None = None


class PredictRequest(BaseModel):
    userId: str = Field(min_length=1)
    candidateFoodIds: list[str] = Field(min_length=1)
    contextMealType: Literal["breakfast", "lunch", "dinner", "snack"] | None = None
    userFeatures: UserFeatures | None = None


class FoodScore(BaseModel):
    foodId: str
    score: float
    scoreContent: float
    scoreMl: float | None
    scoreRule: float


class PredictResponse(BaseModel):
    modelVersion: str | None
    featureVersion: str
    stage: str
    alpha: float
    generationSource: str
    scores: list[FoodScore]
    skippedFoodIds: list[str]
    warnings: list[str]
    elapsedMs: int


class RebuildResponse(BaseModel):
    userId: str
    featureVersion: str
    nSignals: int
    sumAbsWeight: float
    stage: str
    alpha: float
    updatedAt: str


class TrainRequest(BaseModel):
    datasetVersion: str = Field(min_length=1)
    algorithm: Literal[
        "logistic_regression", "random_forest", "gradient_boosting"
    ] = "gradient_boosting"
    activate: bool = False


class TrainResponse(BaseModel):
    jobId: str
    status: str
    startedAt: str


class HealthModel(BaseModel):
    version: str
    algorithm: str
    trainedAt: str | None


class HealthResponse(BaseModel):
    status: str
    activeModel: HealthModel | None
    featureVersion: str
    reason: str | None = None


# ── The training job ──────────────────────────────────────────────────


class TrainingRegistry:
    """Training job state. One at a time, per §8.3 (`409`).

    Guarded by a `threading.Lock` rather than a boolean flag: two
    simultaneous `POST /train` requests would both read the flag as `False`
    and both set it, and two training runs would then write `ml_models` at
    once — the kind of bug that only appears under load.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running: dict[str, Any] | None = None

    def acquire(self, job_id: str, started_at: str) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        self.running = {"jobId": job_id, "startedAt": started_at}
        return True

    def release(self) -> None:
        self.running = None
        try:
            self._lock.release()
        except RuntimeError:
            pass


training = TrainingRegistry()


def _run_training(job_id: str, request: TrainRequest) -> None:
    """Run `ml.train` on a background thread. Errors are logged, not fatal."""
    try:
        from ml import train as train_module

        args = [
            "--dataset",
            request.datasetVersion,
            "--algorithm",
            request.algorithm,
            "--apply",
        ]
        if request.activate:
            args += ["--activate", request.algorithm]
        code = train_module.main(args)
        print(f"[train {job_id}] finished, exit code {code}", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[train {job_id}] ERROR: {type(e).__name__}: {e}", flush=True)
    finally:
        training.release()


# ── The application ───────────────────────────────────────────────────

app = FastAPI(
    title="ML Service — internal",
    description=__doc__,
    version=FEATURE_VERSION,
)


@app.exception_handler(HTTPException)
def error_envelope(_request: Request, e: HTTPException) -> JSONResponse:
    """The `{"error": {...}}` envelope from §2.5 of the specification."""
    detail = e.detail
    if not isinstance(detail, dict):
        detail = {"code": "ERROR", "message": str(detail)}
    return JSONResponse(status_code=e.status_code, content={"error": detail})


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """No key required: `/health` is what an orchestrator calls, not the
    backend.

    It also reveals nothing beyond a model version name. Requiring the key
    here would force every infrastructure liveness probe to carry an
    application secret.
    """
    cn = connect(None)
    try:
        foods, _ = load_foods(cn)
        space = FeatureSpace.from_foods(foods)
        model, reason = load_active_model(cn, space)
        if model is None:
            return HealthResponse(
                status="degraded",
                activeModel=None,
                featureVersion=FEATURE_VERSION,
                reason=reason,
            )
        with cn.cursor() as cur:
            cur.execute(
                "SELECT trained_at FROM ml_models WHERE id = %s", (model.model_id,)
            )
            row = cur.fetchone()
        return HealthResponse(
            status="healthy",
            activeModel=HealthModel(
                version=model.version,
                algorithm=model.algorithm,
                trainedAt=(
                    row["trained_at"].isoformat()
                    if row and row.get("trained_at")
                    else None
                ),
            ),
            featureVersion=FEATURE_VERSION,
        )
    finally:
        cn.close()


def _cross_check_features(cn, user_id: str, sent: UserFeatures | None) -> list[str]:
    """Compare the `userFeatures` the backend sent against `health_profiles`."""
    if sent is None:
        return []
    with cn.cursor() as cur:
        cur.execute(
            "SELECT gender, activity_level, goal, bmi FROM health_profiles "
            "WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    if row is None:
        return ["userFeatures was sent but the user has no health_profiles row"]

    mismatches: list[str] = []
    for name, sent_value, stored in (
        ("gender", sent.gender, row["gender"]),
        ("activityLevel", sent.activityLevel, row["activity_level"]),
        ("goal", sent.goal, row["goal"]),
    ):
        if sent_value is not None and sent_value != stored:
            mismatches.append(
                f"userFeatures.{name} = {sent_value!r} but the database holds "
                f"{stored!r}"
            )
    if sent.bmi is not None and row["bmi"] is not None:
        if abs(float(sent.bmi) - float(row["bmi"])) > 0.05:
            mismatches.append(
                f"userFeatures.bmi = {sent.bmi} but the database computes "
                f"{float(row['bmi'])}"
            )
    return mismatches


@app.post("/predict", response_model=PredictResponse, dependencies=[Depends(check_key)])
def predict(request: PredictRequest) -> PredictResponse:
    started = time.perf_counter()
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (request.userId,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "USER_NOT_FOUND",
                        "message": f"No user {request.userId}.",
                    },
                )

        warnings = _cross_check_features(cn, request.userId, request.userFeatures)

        # `limit` must equal the number of candidates sent. `recommend`
        # defaults to 20: leaving that would have the backend send 50 foods
        # and receive 20 scores, with the other 30 treated as if they did not
        # exist — a silent truncation in the middle of Step 3.
        result = recommend(
            cn,
            request.userId,
            limit=len(request.candidateFoodIds),
            only_candidates=request.candidateFoodIds,
        )

        scored = {c.food.id for c in result.candidates}
        skipped = [f for f in request.candidateFoodIds if f not in scored]

        if not result.candidates:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NO_SCOREABLE_CANDIDATE",
                    "message": (
                        "The F1 filter removed all "
                        f"{len(request.candidateFoodIds)} foods sent — this "
                        "user may eat none of them."
                    ),
                },
            )

        return PredictResponse(
            modelVersion=result.model_version,
            featureVersion=FEATURE_VERSION,
            stage=result.stage,
            alpha=round(result.alpha, 3),
            generationSource=result.generation_source,
            scores=[
                FoodScore(
                    foodId=c.food.id,
                    score=round(c.score, 4),
                    scoreContent=round(c.content_score, 4),
                    scoreMl=(None if c.ml_score is None else round(c.ml_score, 4)),
                    scoreRule=round(c.rule_score, 4),
                )
                for c in result.candidates
            ],
            skippedFoodIds=skipped,
            warnings=warnings + list(result.warnings),
            elapsedMs=int((time.perf_counter() - started) * 1000),
        )
    finally:
        cn.close()


@app.post(
    "/profiles/{user_id}/rebuild",
    response_model=RebuildResponse,
    dependencies=[Depends(check_key)],
)
def rebuild(user_id: str) -> RebuildResponse:
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "USER_NOT_FOUND",
                        "message": f"No user {user_id}.",
                    },
                )

        profile = rebuild_profile(cn, user_id)
        if profile.n_signals == 0:
            # `422` per §8.2. The empty vector is still stored: Stage 0 works
            # with it, and an empty row is very different from a missing one
            # — a missing row leaves `serve` unable to tell whether the
            # profile was ever built.
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INSUFFICIENT_SIGNALS",
                    "message": (
                        "This user has no usable swipe left after the F1 "
                        "filter — no preference vector could be built."
                    ),
                },
            )
        return RebuildResponse(
            userId=user_id,
            featureVersion=FEATURE_VERSION,
            nSignals=profile.n_signals,
            sumAbsWeight=float(profile.sum_abs_weight),
            stage=stage_for(profile.n_signals),
            alpha=round(alpha(profile.n_signals), 3),
            updatedAt=now_vn().isoformat(),
        )
    finally:
        cn.close()


@app.post(
    "/train",
    response_model=TrainResponse,
    status_code=202,
    dependencies=[Depends(check_key)],
)
def train(request: TrainRequest) -> TrainResponse:
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples "
                "WHERE dataset_version = %s",
                (request.datasetVersion,),
            )
            n = int(cur.fetchone()["n"])
        if n == 0:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "DATASET_NOT_FOUND",
                    "message": (
                        f"No sample has dataset_version = "
                        f"{request.datasetVersion!r}. Build it first with "
                        f"`python -m ml.build_dataset --version "
                        f"{request.datasetVersion} --apply`."
                    ),
                },
            )
    finally:
        cn.close()

    now = now_vn()
    job_id = f"train-{now:%Y%m%d-%H%M%S}"
    if not training.acquire(job_id, now.isoformat()):
        current = training.running or {}
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRAINING_IN_PROGRESS",
                "message": (
                    f"A training run is already in progress "
                    f"({current.get('jobId')}, started "
                    f"{current.get('startedAt')})."
                ),
            },
        )

    threading.Thread(
        target=_run_training, args=(job_id, request), name=job_id, daemon=True
    ).start()
    return TrainResponse(jobId=job_id, status="queued", startedAt=now.isoformat())
