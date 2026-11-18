# -*- coding: utf-8 -*-
"""ML Service — the internal endpoints of `API_SPECIFICATION.md` §8.

Before this file, `ml/serve.py` was a **Python library**: runnable from the
command line, but with no way for a C# backend to reach it. That was one of
the two missing seams between the system's three layers, and it blocked
backend waves 4, 5 and 6 — taste survey, meal plan, recommendations — rather
than any shortage of public endpoints.

    POST /predict                     Step 3 — score the catalogue
    POST /plan                        Step 4 — assemble one day's plan
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

## Degradation happens INSIDE this service, not in the backend

`serve.recommend` falls back by itself: with no active model it drops to
Stage 1 and still returns content-based scores, as a `200` carrying `stage`
and `warnings`. So this service answers `503` only when **nothing can be
scored at all**, and a missing model alone is not that case.

The distinction matters: answering `503` whenever a model is missing would
make the caller drop Stage 1 as well — dropping the personalisation that
**does** work. Measured on the simulated set, that is the difference between
0.862 and 0.694 nDCG@5.

What the backend does when it cannot reach this service at all is a separate
decision, and it is **not** soft degradation: the backend shows the user an
error and asks them to try again, rather than quietly serving a plan built
from the rules alone. Specification §8.1 describes the older, softer
behaviour; `backend/Api/Ml/MlResult.cs` is where the current rule lives, and
`db/schema.sql` still accepts `generation_source = 'rule_based'` for it.

The one case the backend must NOT treat as "the ML service is down" is
`422 NO_SCOREABLE_CANDIDATE`. That answer means the F1 safety layer removed
every food — retrying cannot help, and scoring the foods anyway is the
safety layer failing open.
"""

from __future__ import annotations

import hmac
import os
import sys
import threading
import time
from datetime import date as dt_date
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import connect  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.plan import PlanInputError, build_daily_plan  # noqa: E402
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
    """The `/predict` body.

    ## Why `candidateFoodIds` is optional

    It used to be required, and the backend was expected to assemble a
    candidate set and ask for scores on it. That put the catalogue behind two
    gatekeepers: the backend decided which foods were even considered, and
    this service decided which of those were safe. Two layers choosing foods
    means two places to disagree about the catalogue, and the disagreement is
    invisible — a food the backend forgot to send is indistinguishable from a
    food the F1 filter removed.

    So the default is now **the whole catalogue**: omit `candidateFoodIds`
    and this service reads every active food itself, applies F1, and scores
    what remains. The backend keeps exactly one say in the candidate set,
    `excludeFoodIds`, which is information this service does not have.
    """

    userId: str = Field(min_length=1)

    #: Omit it — or send `null` — to score the entire active catalogue, which
    #: is what the backend does. A list restricts scoring to those foods, for
    #: debugging and for the command line; an **empty** list is rejected,
    #: because "score nothing" is never a question worth asking and is far
    #: more likely to be a bug upstream.
    candidateFoodIds: list[str] | None = Field(default=None, min_length=1)

    #: The foods already used today, so a plan does not repeat a dish. This
    #: is the one part of the candidate set the backend knows and this
    #: service does not.
    excludeFoodIds: list[str] = Field(default_factory=list)

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

    #: Candidates that were asked for and came back unscored. Empty when no
    #: `candidateFoodIds` was sent, because then nothing specific was asked
    #: for — use the two counts below instead.
    skippedFoodIds: list[str]

    #: How many active foods existed before F1, and how many survived it.
    #:
    #: Sent because the backend can no longer work this out for itself: it
    #: does not assemble the candidate set any more. The pair is what a
    #: `422 RULE_TOO_RESTRICTIVE` answer to the user is built from — "318
    #: foods, 2 left" is an explanation, while "no feasible plan" is not. It
    #: is NOT the per-role breakdown of §7.6 (`foodsRemaining`); Step 4 knows
    #: the roles, this service does not.
    nFoodsBeforeF1: int
    nFoodsAfterF1: int

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


# ── Step 4 — POST /plan ───────────────────────────────────────────────


class PlanRequest(BaseModel):
    """What the backend has to supply for one day's plan.

    Deliberately short. Everything else — the catalogue, the F1 filter, the
    preference vector, the per-day thresholds, the energy target — this
    service reads for itself, for the same reason `/predict` no longer takes
    a candidate set: two layers deciding the same thing is two places to
    disagree, and the disagreement is invisible.
    """

    userId: str = Field(min_length=1)

    #: The day the plan is for. Omitted means today in Asia/Ho_Chi_Minh —
    #: `meal_plans.plan_date` is a DATE, and the one clock of this system is
    #: Vietnamese local time.
    planDate: str | None = None

    #: Foods not to use: what the user has already eaten today, so the plan
    #: does not repeat a dish.
    excludeFoodIds: list[str] = Field(default_factory=list)

    #: The 70-30 mechanism's target share. `chk_expl_ratio` caps it at 0.5
    #: in the database and `MenuBuilder` caps it again, because more than
    #: half the plan being a trial dish is not a personalised recommendation.
    explorationRatio: float = Field(default=0.3, ge=0.0, le=0.5)

    #: Fixes the exploration draw, so a checker can compare two runs. A real
    #: request leaves it out and gets a fresh plan.
    seed: int | None = None


class PlanItemOut(BaseModel):
    foodId: str
    foodName: str
    dishRole: str
    mealType: str
    kcal: int
    predictedScore: float
    #: `null` is an EXPLOITATION serving, a number is an exploration one —
    #: exactly what `meal_plan_items.exploration_delta` means, which is why
    #: there is no `isExploration` flag beside it.
    explorationDelta: float | None
    position: int


class PlanMealOut(BaseModel):
    mealType: str
    targetKcal: float
    actualKcal: float
    deviationPct: float
    items: list[PlanItemOut]


class NutrientCheckOut(BaseModel):
    nutrient: str
    comparator: str
    threshold: float
    actual: float
    condition: str


class PlanResponse(BaseModel):
    userId: str
    planDate: str

    #: Step 1's numbers, echoed back. The backend writes them into the
    #: `meal_plans` row beside the result, so the plan records the target it
    #: was built against rather than one recomputed later.
    targetCaloriesKcal: float
    targetProteinG: float
    targetCarbsG: float
    targetFatG: float

    actualCaloriesKcal: float
    actualProteinG: float
    actualCarbsG: float
    actualFatG: float
    #: What `meal_plans.calorie_deviation_pct` will compute. Sent so the
    #: caller can check the proposal's 10 % commitment without waiting for
    #: the row to exist.
    calorieDeviationPct: float
    withinTolerance: bool

    totalPreferenceScore: float
    explorationRatio: float
    actualExplorationRatio: float

    stage: str
    alpha: float
    generationSource: str
    modelVersion: str | None
    featureVersion: str
    nFoodsBeforeF1: int
    nFoodsAfterF1: int

    meals: list[PlanMealOut]

    #: Day-level thresholds phase 5 could not satisfy. Empty is good; a
    #: non-empty list must reach the user rather than being hidden behind a
    #: plan that looks ordinary.
    nutrientViolations: list[NutrientCheckOut]
    #: Thresholds on a nutrient the catalogue cannot measure — today only
    #: `purine_mg`. Kept apart from the violations so an unchecked plan is
    #: never reported as satisfying them.
    unenforceableTargets: list[str]
    meetsNutrientTargets: bool

    warnings: list[str]
    elapsedMs: int


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

        # `limit` must never truncate. With a candidate list it equals the
        # number sent; without one it is `None`, meaning the whole catalogue.
        # `recommend` defaults to 20, and leaving that would return 20 scores
        # for 318 foods with the other 298 treated as if they did not exist —
        # a silent truncation in the middle of Step 3.
        result = recommend(
            cn,
            request.userId,
            limit=(
                None
                if request.candidateFoodIds is None
                else len(request.candidateFoodIds)
            ),
            exclude_foods=request.excludeFoodIds,
            only_candidates=request.candidateFoodIds,
        )

        scored = {c.food.id for c in result.candidates}
        skipped = [
            f for f in (request.candidateFoodIds or []) if f not in scored
        ]

        if not result.candidates:
            # Still a `422`, and still NOT something the backend may fall
            # back from: F1 is the safety layer, and an empty result is it
            # saying this person may eat none of these foods. Now that the
            # default is the whole catalogue, the message has to say which
            # case it is — "all 12 foods you asked about" and "all 318 foods
            # that exist" lead to very different answers to the user.
            asked = (
                f"the {len(request.candidateFoodIds)} foods sent"
                if request.candidateFoodIds is not None
                else f"all {result.n_foods_before_f1} active foods"
            )
            excluded_today = (
                ""
                if not request.excludeFoodIds
                else (
                    f" {len(request.excludeFoodIds)} food(s) were also "
                    "excluded as already used today."
                )
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NO_SCOREABLE_CANDIDATE",
                    "message": (
                        f"The F1 filter removed {asked} — this user may eat "
                        f"none of them.{excluded_today}"
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
            nFoodsBeforeF1=result.n_foods_before_f1,
            nFoodsAfterF1=result.n_foods_after_f1,
            warnings=warnings + list(result.warnings),
            elapsedMs=int((time.perf_counter() - started) * 1000),
        )
    finally:
        cn.close()


@app.post("/plan", response_model=PlanResponse, dependencies=[Depends(check_key)])
def plan(request: PlanRequest) -> PlanResponse:
    """Step 4 — assemble one day's plan.

    Returns the plan; it writes nothing. `meal_plans` has one owner for
    writes and that is the backend, which holds the `409 MEAL_PLAN_EXISTS`
    rule and the ownership check that belong with a user's own data.

    The status codes follow §8.1's shape:

    * `404 USER_NOT_FOUND`
    * `422` with the code from `PlanInputError` — `PROFILE_REQUIRED` when
      Step 1 has never run for this user, `ONBOARDING_REQUIRED` when the
      profile exists but carries no energy target. Neither is "the ML
      service is unavailable", and the backend must not retry them.
    * `422 NO_SCOREABLE_CANDIDATE` when the F1 filter leaves nothing. Same
      meaning as in `/predict`: the safety layer removed everything, and
      scoring the foods anyway would be it failing open.
    """
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

        if request.planDate is None:
            day = now_vn().date()
        else:
            try:
                day = dt_date.fromisoformat(request.planDate)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "VALIDATION_FAILED",
                        "message": (
                            f"planDate {request.planDate!r} is not an "
                            "ISO date (YYYY-MM-DD)."
                        ),
                    },
                )

        try:
            result = build_daily_plan(
                cn,
                request.userId,
                plan_date=day,
                exclude_food_ids=request.excludeFoodIds,
                exploration_ratio=request.explorationRatio,
                seed=request.seed,
            )
        except PlanInputError as e:
            # Not a malfunction: the user has not supplied something. The
            # code is the stable string the backend branches on.
            raise HTTPException(
                status_code=422,
                detail={"code": e.code, "message": e.message},
            )

        built = result.plan
        if not built.items:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "NO_SCOREABLE_CANDIDATE",
                    "message": (
                        f"The F1 filter left nothing to build a plan from: "
                        f"{result.n_foods_after_f1} of "
                        f"{result.n_foods_before_f1} active foods are safe "
                        f"for this user."
                    ),
                },
            )

        meals = [
            PlanMealOut(
                mealType=slot.meal_type,
                targetKcal=round(slot.target_kcal, 2),
                actualKcal=round(slot.actual_kcal, 2),
                deviationPct=round(slot.deviation_pct, 2),
                items=[
                    PlanItemOut(
                        foodId=item.food.id,
                        foodName=item.food.name,
                        dishRole=item.food.dish_role,
                        mealType=slot.meal_type,
                        kcal=int(item.food.kcal),
                        predictedScore=round(item.score, 4),
                        explorationDelta=(
                            None if item.exploration_delta is None
                            else round(item.exploration_delta, 3)
                        ),
                        position=position,
                    )
                    for position, item in enumerate(slot.items, start=1)
                ],
            )
            for slot in built.slots
        ]

        return PlanResponse(
            userId=request.userId,
            planDate=day.isoformat(),
            targetCaloriesKcal=round(result.targets.kcal, 2),
            targetProteinG=round(result.targets.protein_g, 2),
            targetCarbsG=round(result.targets.carb_g, 2),
            targetFatG=round(result.targets.fat_g, 2),
            actualCaloriesKcal=round(built.actual_kcal, 2),
            actualProteinG=round(built.actual_protein, 2),
            actualCarbsG=round(built.actual_carb, 2),
            actualFatG=round(built.actual_fat, 2),
            calorieDeviationPct=round(built.deviation_pct, 2),
            withinTolerance=built.within_tolerance,
            totalPreferenceScore=round(built.total_preference_score, 4),
            explorationRatio=round(built.exploration_ratio, 3),
            actualExplorationRatio=round(built.actual_exploration_ratio, 3),
            stage=result.stage,
            alpha=result.alpha,
            generationSource=result.generation_source,
            modelVersion=result.model_version,
            featureVersion=result.feature_version,
            nFoodsBeforeF1=result.n_foods_before_f1,
            nFoodsAfterF1=result.n_foods_after_f1,
            meals=meals,
            nutrientViolations=[
                NutrientCheckOut(
                    nutrient=target.nutrient,
                    comparator="gte" if target.is_floor else "lte",
                    threshold=target.amount,
                    actual=round(actual, 2),
                    condition=target.condition,
                )
                for target, actual in built.nutrient_violations
            ],
            unenforceableTargets=[
                t.nutrient for t in built.unenforceable_targets
            ],
            meetsNutrientTargets=built.meets_nutrient_targets,
            warnings=list(result.warnings),
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
