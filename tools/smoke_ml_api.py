#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the ML Service's 6 internal endpoints, against the real
database.

The counterpart of `tools/smoke_backend.py` for the ML layer, and needed for
the same reason: `tools/check_ml.py` checks the formulas as pure arithmetic
with no server, while this file checks the things that **only break once there
is HTTP and a database** — shared-key authentication, error envelopes, the
field-name mapping between Python's `snake_case` and the specification's
`camelCase`, status codes, and the graceful-degradation path.

It creates no new data: it reads a user already in the database and scores
public foods. `POST /profiles/{id}/rebuild` does write — but it writes back
exactly the values `import_swipes` / `import_simulation` already computed, so
repeated runs do not skew the data. One of the checks asserts precisely that.

Run (the ML Service must be running):
    python tools/run_ml_service.py       # in another window
    python tools/smoke_ml_api.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _env  # noqa: E402

from ml.db import connect  # noqa: E402
from ml.features import FEATURE_VERSION  # noqa: E402

BASE = "http://127.0.0.1:8000"
KEY_ENV = "ML_INTERNAL_KEY"

_checks = 0
_failures: list[str] = []


def call(method: str, path: str, body=None, key: str | None = None,
         timeout: int = 30):
    """Call the API; returns `(HTTP status, JSON-decoded body or None)`."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-Internal-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:300]}
    except urllib.error.URLError as e:
        print(
            f"\nCould not reach {BASE} — is the ML Service running?\n"
            f"  {e}\nStart it first: python tools/run_ml_service.py",
            file=sys.stderr,
        )
        raise SystemExit(2)


def check(label: str, passed: bool, detail: str = "") -> bool:
    global _checks
    _checks += 1
    print(
        f"  {'[ok]' if passed else '[BAD]'} {label}"
        + (f"  {detail}" if detail and not passed else "")
    )
    if not passed:
        _failures.append(f"{label} — {detail}" if detail else label)
    return passed


def equals(label: str, got, want) -> bool:
    return check(label, got == want, f"got {got!r}, wanted {want!r}")


def error_code(body) -> str | None:
    if isinstance(body, dict):
        return (body.get("error") or {}).get("code")
    return None


def _models() -> dict[int, dict]:
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT id, version, algorithm, is_active, artifact_path "
                "FROM ml_models"
            )
            return {int(d["id"]): d for d in cur.fetchall()}
    finally:
        cn.close()


def _serving_version() -> str | None:
    for d in _models().values():
        if int(d["is_active"]) == 1:
            return str(d["version"])
    return None


def _wait_for_new_model(before: dict[int, dict], seconds: int) -> dict | None:
    """Wait for a new `ml_models` row to appear, for at most `seconds`."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        for model_id, d in _models().items():
            if model_id not in before:
                return d
        time.sleep(1.0)
    return None


def _delete_model(d: dict) -> bool:
    """Delete an `ml_models` row and its artifact file."""
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute("DELETE FROM ml_models WHERE id = %s", (d["id"],))
            deleted = cur.rowcount
        cn.commit()
    finally:
        cn.close()
    path = ROOT / str(d.get("artifact_path") or "")
    if d.get("artifact_path") and path.exists():
        path.unlink()
    return deleted == 1


def main(argv: list[str] | None = None) -> int:
    global BASE
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE,
                        help="the ML Service address")
    args = parser.parse_args(argv)
    BASE = args.base.rstrip("/")

    key = _env.get(KEY_ENV, "")
    if not key:
        print(
            f"{KEY_ENV} is missing from .env. Run "
            "`python tools/run_ml_service.py` once to have it generated.",
            file=sys.stderr,
        )
        return 1

    # -- Fetch real data to test with --
    cn = connect(None)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT p.user_id, p.n_signals, p.stage, p.sum_abs_weight "
                "FROM user_preference_profiles p "
                "ORDER BY p.n_signals DESC LIMIT 1"
            )
            profile = cur.fetchone()
            cur.execute(
                "SELECT id FROM foods WHERE owner_id IS NULL AND is_active = 1 "
                "ORDER BY id LIMIT 8"
            )
            foods = [d["id"] for d in cur.fetchall()]
            cur.execute(
                "SELECT dataset_version v, COUNT(*) n FROM ml_training_samples "
                "GROUP BY dataset_version ORDER BY n DESC LIMIT 1"
            )
            dataset = cur.fetchone()
    finally:
        cn.close()

    if profile is None or len(foods) < 4:
        print(
            "The database has no preference profile yet, or too few foods.\n"
            "Load first: python tools/import_simulation.py --apply",
            file=sys.stderr,
        )
        return 1

    uid = profile["user_id"]
    print(f"ML Service: {BASE}")
    print(
        f"Test data: user {uid[:8]}… (n_signals={profile['n_signals']}, "
        f"{profile['stage']}) · {len(foods)} foods"
    )

    # -- GET /health --
    print("\n§8.4  GET /health")
    status, body = call("GET", "/health")
    equals("health returns 200", status, 200)
    check(
        "requires no key — an infrastructure liveness probe carries no "
        "application secret",
        status == 200,
    )
    equals("featureVersion matches the source",
           (body or {}).get("featureVersion"), FEATURE_VERSION)
    check(
        "status is one of {healthy, degraded}",
        (body or {}).get("status") in ("healthy", "degraded"),
        f"got {(body or {}).get('status')!r}",
    )
    has_model = (body or {}).get("activeModel") is not None
    if has_model:
        active = body["activeModel"]
        check(
            "activeModel carries a version and an algorithm",
            bool(active.get("version")) and bool(active.get("algorithm")),
            f"got {active!r}",
        )
        equals("status = healthy when a model is present", body["status"],
               "healthy")
    else:
        equals("status = degraded with no model", body["status"], "degraded")
        check("degraded comes with a readable reason",
              bool((body or {}).get("reason")))

    # -- Authentication --
    print("\n§8     Authentication via X-Internal-Key")
    status, body = call("POST", "/predict",
                        {"userId": uid, "candidateFoodIds": foods})
    equals("a missing key gives 401", status, 401)
    equals("the error code is UNAUTHORIZED", error_code(body), "UNAUTHORIZED")
    status, body = call(
        "POST", "/predict", {"userId": uid, "candidateFoodIds": foods},
        key="wrong-key"
    )
    equals("a wrong key gives 401", status, 401)
    check(
        'the error envelope is {"error": {code, message}} as in §2.5',
        isinstance(body, dict) and "error" in body,
        f"got {body!r}",
    )

    # -- POST /predict --
    print("\n§8.1  POST /predict")
    status, body = call(
        "POST",
        "/predict",
        {"userId": uid, "candidateFoodIds": foods,
         "contextMealType": "lunch"},
        key=key,
    )
    equals("predict returns 200", status, 200)
    scores = (body or {}).get("scores") or []
    equals("scores as many foods as were sent", len(scores), len(foods))
    check(
        "every returned foodId was in the list that was sent",
        all(s["foodId"] in foods for s in scores),
    )
    check(
        "the scores are within [0, 1]",
        all(0.0 <= s["score"] <= 1.0 for s in scores),
        f"got {[s['score'] for s in scores][:5]}",
    )
    check(
        "already sorted by score descending",
        all(scores[i]["score"] >= scores[i + 1]["score"]
            for i in range(len(scores) - 1)),
    )
    check(
        "each food carries all three score components, separated so the "
        "result can be traced back",
        all(
            "scoreContent" in s and "scoreRule" in s and "scoreMl" in s
            for s in scores
        ),
    )
    equals("featureVersion in the response", body.get("featureVersion"),
           FEATURE_VERSION)
    check(
        "stage is one of the four stages",
        body.get("stage") in ("cold", "content", "hybrid", "ml"),
        f"got {body.get('stage')!r}",
    )
    check(
        "alpha is within [0, 1]",
        0.0 <= float(body.get("alpha", -1)) <= 1.0,
        f"got {body.get('alpha')!r}",
    )
    check(
        "elapsedMs is present and under the backend's 2-second budget",
        isinstance(body.get("elapsedMs"), int) and body["elapsedMs"] < 2000,
        f"got {body.get('elapsedMs')!r} ms",
    )
    # The `hybrid`/`ml` stages must carry an ML score; `cold`/`content` must
    # not.
    if body.get("stage") in ("hybrid", "ml"):
        check(
            "the hybrid/ml stages have a non-null scoreMl",
            all(s["scoreMl"] is not None for s in scores),
        )
        check("modelVersion is non-null once a model is in use",
              bool(body.get("modelVersion")))
    else:
        check(
            "the cold/content stages leave scoreMl null",
            all(s["scoreMl"] is None for s in scores),
            f"got {[s['scoreMl'] for s in scores][:3]}",
        )

    # -- The default: no candidate list at all --
    #
    # This is how the backend calls it. The ML service reads the catalogue
    # itself, so one layer decides which foods exist: when the backend also
    # assembled a candidate set, a food it forgot to send and a food F1
    # removed were indistinguishable.
    print("\n§8.1  predict — the whole catalogue, with no candidate list")
    status, body = call("POST", "/predict", {"userId": uid}, key=key)
    equals("a request with no candidateFoodIds returns 200", status, 200)
    all_scores = (body or {}).get("scores") or []
    before = (body or {}).get("nFoodsBeforeF1")
    after = (body or {}).get("nFoodsAfterF1")
    check(
        "nFoodsBeforeF1 and nFoodsAfterF1 are reported — the backend cannot "
        "work them out itself any more",
        isinstance(before, int) and isinstance(after, int),
        f"got {before!r} and {after!r}",
    )
    equals("as many scores as foods survived F1", len(all_scores), after)
    check(
        "F1 cannot keep more foods than exist",
        isinstance(before, int) and isinstance(after, int) and after <= before,
        f"{after} of {before}",
    )
    check(
        "nothing was truncated to `recommend`'s default limit of 20",
        len(all_scores) == after,
        f"got {len(all_scores)} scores for {after} safe foods",
    )
    equals(
        "skippedFoodIds is empty when nothing specific was asked for",
        (body or {}).get("skippedFoodIds"), [],
    )

    # -- excludeFoodIds: the one say over the candidate set the backend keeps
    print("\n§8.1  predict — excludeFoodIds")
    status, body = call(
        "POST", "/predict", {"userId": uid, "excludeFoodIds": foods}, key=key
    )
    equals("a request with excludeFoodIds returns 200", status, 200)
    kept = {s["foodId"] for s in ((body or {}).get("scores") or [])}
    scored_before = {s["foodId"] for s in all_scores}
    check(
        "no excluded food comes back scored — a plan must not repeat a dish "
        "already used today",
        not (kept & set(foods)),
        f"{sorted(kept & set(foods))} came back anyway",
    )
    equals(
        "exactly the excluded foods are gone, nothing else",
        len(scored_before) - len(kept),
        len(scored_before & set(foods)),
    )

    print("\n§8.1  predict — the error cases")
    status, body = call("POST", "/predict",
                        {"userId": uid, "candidateFoodIds": []}, key=key)
    equals("an empty candidateFoodIds gives 422", status, 422)
    status, body = call(
        "POST",
        "/predict",
        {"userId": "00000000-0000-4000-8000-000000000000",
         "candidateFoodIds": foods},
        key=key,
    )
    equals("a userId that does not exist gives 404", status, 404)
    equals("the error code is USER_NOT_FOUND", error_code(body),
           "USER_NOT_FOUND")
    status, body = call("POST", "/predict", {"candidateFoodIds": foods},
                        key=key)
    equals("a missing userId gives 422", status, 422)

    print("\n§8.1  predict — F1 still runs FIRST, even though the backend "
          "sent the candidates")
    status, body = call(
        "POST",
        "/predict",
        {
            "userId": uid,
            "candidateFoodIds": foods
            + ["00000000-0000-4000-8000-0000000000ff"],
            "userFeatures": {"gender": "other", "goal": "gain_weight"},
        },
        key=key,
    )
    equals("a nonexistent food does not break the request", status, 200)
    check(
        "the unscorable food appears in skippedFoodIds",
        "00000000-0000-4000-8000-0000000000ff"
        in (body.get("skippedFoodIds") or []),
        f"got {body.get('skippedFoodIds')!r}",
    )
    check(
        "userFeatures differing from the database is reported in warnings, "
        "not silently ignored",
        any("userFeatures" in w for w in (body.get("warnings") or [])),
        f"got {body.get('warnings')!r}",
    )

    # -- POST /profiles/{id}/rebuild --
    # -- POST /plan — Step 4 --
    #
    # The endpoint the backend calls for a day's meal plan. Everything here
    # is checked against the response alone: a plan that looks like a plan
    # but repeats a dish, misses a required role, or quietly breaches a
    # medical threshold is the failure worth a smoke test.
    print("\n§8.5  POST /plan")
    status, body = call(
        "POST", "/plan",
        {"userId": uid, "planDate": "2026-11-18", "seed": 1},
        key=key,
    )
    equals("plan returns 200", status, 200)
    body = body or {}
    meals = body.get("meals") or []
    equals("a plan has the four meals", len(meals), 4)
    equals(
        "in day order",
        [m["mealType"] for m in meals],
        ["breakfast", "lunch", "dinner", "snack"],
    )

    items = [i for m in meals for i in m["items"]]
    check("the plan has servings", items != [])
    ids = [i["foodId"] for i in items]
    check(
        "no food appears twice in a day",
        len(ids) == len(set(ids)),
        f"{len(ids) - len(set(ids))} repeats",
    )
    check(
        "every predictedScore is in [0, 1], the range the column expects",
        all(0.0 <= i["predictedScore"] <= 1.0 for i in items),
    )
    check(
        "every serving carries a position",
        all(i["position"] >= 1 for i in items),
    )
    check(
        "an exploitation serving sends NULL, not 0 — `exploration_delta IS "
        "NOT NULL` is what tells the two groups apart",
        all(
            i["explorationDelta"] is None or i["explorationDelta"] > 0
            for i in items
        ),
    )

    # The required roles of each meal, from `MEAL_STRUCTURE`. Spelled out
    # rather than imported, so this fails if the structure changes without
    # anyone noticing.
    required = {
        "breakfast": {"main"},
        "lunch": {"main", "side_protein"},
        "dinner": {"main", "side_veg"},
        "snack": {"snack"},
    }
    for meal in meals:
        roles = [i["dishRole"] for i in meal["items"]]
        check(
            f"{meal['mealType']} has its required roles",
            required[meal["mealType"]] <= set(roles),
            f"got {sorted(roles)}",
        )
        check(
            f"{meal['mealType']} has no two servings of the same role",
            len(roles) == len(set(roles)),
            f"got {sorted(roles)}",
        )

    # The commitment made in the thesis proposal, measured on real data.
    check(
        "the energy deviation is within 10 %",
        abs(body.get("calorieDeviationPct", 999)) <= 10,
        f"got {body.get('calorieDeviationPct')} %",
    )
    check("and the flag agrees", body.get("withinTolerance") is True)
    summed = sum(i["kcal"] for i in items)
    check(
        "actualCaloriesKcal is the sum of the servings",
        abs(summed - body.get("actualCaloriesKcal", 0)) < 1.0,
        f"got {body.get('actualCaloriesKcal')} against {summed}",
    )
    check(
        "the Step 1 target is echoed back, for the `meal_plans` row to record",
        body.get("targetCaloriesKcal", 0) > 0,
    )
    check(
        "explorationRatio is inside what `chk_expl_ratio` allows",
        0.0 <= body.get("explorationRatio", -1) <= 0.5,
        f"got {body.get('explorationRatio')}",
    )
    check(
        "the plan says which stage scored it",
        body.get("stage") in ("cold", "content", "hybrid", "ml"),
        f"got {body.get('stage')!r}",
    )
    equals(
        "and which feature space", body.get("featureVersion"), FEATURE_VERSION
    )
    check(
        "a whole plan is built inside the backend's 2-second budget",
        isinstance(body.get("elapsedMs"), int) and body["elapsedMs"] < 2000,
        f"got {body.get('elapsedMs')} ms",
    )

    # A violated threshold must be reported, never hidden; an unmeasurable
    # one must not be reported as met.
    check(
        "the plan states which day-level thresholds it failed",
        isinstance(body.get("nutrientViolations"), list),
    )
    if body.get("unenforceableTargets"):
        check(
            "a plan with an unenforceable threshold does NOT claim its "
            "targets are met — purine is never checked, so it cannot be "
            "reported as satisfied",
            body.get("meetsNutrientTargets") is False,
        )

    # The same seed has to give the same plan, or no checker could compare
    # two runs — and `tools/check_step4_parity.py` depends on it.
    status, again = call(
        "POST", "/plan",
        {"userId": uid, "planDate": "2026-11-18", "seed": 1},
        key=key,
    )
    equals("the same request returns 200 again", status, 200)
    equals(
        "the same seed gives the same plan",
        [i["foodId"] for m in (again or {}).get("meals", []) for i in m["items"]],
        ids,
    )

    # excludeFoodIds is the one say over the candidate set the backend keeps.
    dropped = ids[:2]
    status, without = call(
        "POST", "/plan",
        {"userId": uid, "planDate": "2026-11-18", "seed": 1,
         "excludeFoodIds": dropped},
        key=key,
    )
    equals("a plan with excludeFoodIds returns 200", status, 200)
    kept = {
        i["foodId"] for m in (without or {}).get("meals", []) for i in m["items"]
    }
    check(
        "no excluded food comes back in the plan",
        not (kept & set(dropped)),
        f"got {sorted(kept & set(dropped))}",
    )

    print("\n§8.5  plan — the error cases")
    status, body = call("POST", "/plan", {"userId": uid})
    equals("a missing key gives 401", status, 401)
    status, body = call(
        "POST", "/plan",
        {"userId": "00000000-0000-4000-8000-000000000000"}, key=key,
    )
    equals("a userId that does not exist gives 404", status, 404)
    equals("the error code is USER_NOT_FOUND", error_code(body), "USER_NOT_FOUND")
    status, body = call(
        "POST", "/plan", {"userId": uid, "planDate": "18/11/2026"}, key=key,
    )
    equals("a planDate that is not an ISO date gives 400", status, 400)
    status, body = call(
        "POST", "/plan", {"userId": uid, "explorationRatio": 0.9}, key=key,
    )
    equals("an explorationRatio above the 0.5 cap is refused", status, 422)

    # -- POST /survey-deck - the taste survey's deck (§7.4.1) --
    #
    # The deck decides what every new user's preference vector is built
    # from, so the properties worth checking are the ones that make a deck
    # worth swiping: the right size, no repeats, spread across categories,
    # and the same deck twice for the same user.
    print("\n§8.6  POST /survey-deck")
    status, body = call("POST", "/survey-deck", {"userId": uid, "size": 30},
                        key=key)
    equals("survey-deck returns 200", status, 200)
    body = body or {}
    ids = body.get("foodIds") or []
    equals("the deck has the requested size", len(ids), 30)
    equals("totalItems agrees with the list", body.get("totalItems"), 30)
    check(
        "no food appears twice in one deck",
        len(ids) == len(set(ids)),
        f"{len(ids) - len(set(ids))} repeats",
    )
    check(
        "minRequired never exceeds the deck - a minimum nobody can reach "
        "would lock the user out of onboarding",
        0 < body.get("minRequired", 0) <= len(ids),
        f"got {body.get('minRequired')} for {len(ids)} foods",
    )
    check(
        "the deck is drawn from the F1-safe foods only",
        0 < body.get("nFoodsAfterF1", 0) <= body.get("nFoodsBeforeF1", 0),
        f"{body.get('nFoodsAfterF1')} of {body.get('nFoodsBeforeF1')}",
    )
    check(
        "it covers more than one category - a deck from one corner of the "
        "feature space cannot tell two tastes apart",
        body.get("nCategories", 0) > 1,
        f"{body.get('nCategories')} of {body.get('nCategoriesTotal')}",
    )
    equals("and which feature space", body.get("featureVersion"),
           FEATURE_VERSION)
    check(
        "the spice-coverage limitation is reported on every call, not "
        "discovered later by the reader",
        any("spice" in w for w in body.get("warnings", [])),
        f"got {body.get('warnings')}",
    )
    check(
        "a deck is built inside the backend's 2-second budget",
        isinstance(body.get("elapsedMs"), int) and body["elapsedMs"] < 2000,
        f"got {body.get('elapsedMs')} ms",
    )

    # Deterministic: the traversal starts from the catalogue's centroid and
    # breaks ties by name, so two people surveyed on two different days are
    # asked the same questions and their vectors stay comparable.
    status, again = call("POST", "/survey-deck", {"userId": uid, "size": 30},
                         key=key)
    equals("the same user gets the same deck", (again or {}).get("foodIds"),
           ids)

    # The order is the answer, not an accident: the first food is the most
    # typical of the catalogue, so a shortened form is still well spread.
    status, short = call("POST", "/survey-deck", {"userId": uid, "size": 20},
                         key=key)
    equals("a smaller deck returns 200", status, 200)
    equals(
        "a shorter deck is a PREFIX of the longer one",
        (short or {}).get("foodIds"),
        ids[:20],
    )

    print("\n§8.6  survey-deck - the error cases")
    status, body = call("POST", "/survey-deck", {"userId": uid})
    equals("a missing key gives 401", status, 401)
    status, body = call(
        "POST", "/survey-deck",
        {"userId": "00000000-0000-4000-8000-000000000000"}, key=key,
    )
    equals("a userId that does not exist gives 404", status, 404)
    equals("the error code is USER_NOT_FOUND", error_code(body),
           "USER_NOT_FOUND")
    status, body = call("POST", "/survey-deck", {"userId": uid, "size": 19},
                        key=key)
    equals("a deck smaller than 20 is refused", status, 422)
    status, body = call("POST", "/survey-deck", {"userId": uid, "size": 51},
                        key=key)
    equals("a deck larger than 50 is refused", status, 422)

    print("\n§8.2  POST /profiles/{userId}/rebuild")
    status, body = call("POST", f"/profiles/{uid}/rebuild", {}, key=key)
    equals("rebuild returns 200", status, 200)
    equals("the userId comes back correct", (body or {}).get("userId"), uid)
    equals(
        "nSignals matches the value the importer computed",
        (body or {}).get("nSignals"),
        int(profile["n_signals"]),
    )
    check(
        "sumAbsWeight matches the stored value",
        abs(float(body["sumAbsWeight"])
            - float(profile["sum_abs_weight"])) < 1e-6,
        f"got {body['sumAbsWeight']}, stored "
        f"{float(profile['sum_abs_weight'])}",
    )
    equals("stage matches", (body or {}).get("stage"), profile["stage"])
    check(
        "updatedAt carries the +07:00 offset, not UTC",
        "+07:00" in str((body or {}).get("updatedAt")),
        f"got {(body or {}).get('updatedAt')!r}",
    )
    status, body = call(
        "POST", "/profiles/00000000-0000-4000-8000-000000000000/rebuild", {},
        key=key
    )
    equals("a userId that does not exist gives 404", status, 404)
    status, _ = call("POST", f"/profiles/{uid}/rebuild", {})
    equals("rebuild requires the key", status, 401)

    # -- POST /train --
    print("\n§8.3  POST /train")
    status, body = call(
        "POST",
        "/train",
        {"datasetVersion": "does-not-exist-abc",
         "algorithm": "random_forest"},
        key=key,
    )
    equals("a datasetVersion with no samples gives 404", status, 404)
    equals("the error code is DATASET_NOT_FOUND", error_code(body),
           "DATASET_NOT_FOUND")
    status, body = call(
        "POST", "/train",
        {"datasetVersion": "v1", "algorithm": "no-such-algorithm"}, key=key
    )
    equals("an unknown algorithm gives 422", status, 422)
    status, _ = call("POST", "/train", {"datasetVersion": "v1"})
    equals("train requires the key", status, 401)

    if dataset:
        print(
            f"\n§8.3  a real training run on dataset_version = "
            f"{dataset['v']!r} ({dataset['n']} samples)"
        )
        before_train = _models()
        serving_before = _serving_version()
        status, body = call(
            "POST",
            "/train",
            {
                "datasetVersion": dataset["v"],
                "algorithm": "logistic_regression",
                "activate": False,
            },
            key=key,
        )
        equals("train returns 202 Accepted and does not block", status, 202)
        check("a jobId is present", bool((body or {}).get("jobId")),
              f"got {body!r}")
        equals("status = queued", (body or {}).get("status"), "queued")
        check(
            "startedAt carries the +07:00 offset",
            "+07:00" in str((body or {}).get("startedAt")),
            f"got {(body or {}).get('startedAt')!r}",
        )
        # A second run immediately after must be refused: §8.3 says `409`
        # while a run is in progress. This is the test of that very lock —
        # without it, two runs would write `ml_models` at once.
        status2, body2 = call(
            "POST",
            "/train",
            {"datasetVersion": dataset["v"], "algorithm": "random_forest"},
            key=key,
        )
        equals("a second run before the first finishes gives 409", status2, 409)
        equals("the error code is TRAINING_IN_PROGRESS", error_code(body2),
               "TRAINING_IN_PROGRESS")

        # Wait for the training run to finish, then CLEAN UP the model it
        # produced.
        #
        # This has to be checked, because `202 Accepted` only says "received",
        # not "done". A `/train` that accepts the request and then dies
        # quietly in its background thread passes every check above.
        #
        # And it has to be cleaned up, because unlike `smoke_backend.py` —
        # which creates one account and deletes it — a run here adds an
        # `ml_models` row and a `.joblib` file. Ten runs of the checker leave
        # ten junk models, and `load_active_model` refuses to serve when more
        # than one row has `is_active = 1`.
        print("\n§8.3  the training run must really run, then be cleaned up")
        created = _wait_for_new_model(before_train, seconds=90)
        check(
            "a new model appeared in ml_models — the 202 was not an empty "
            "promise",
            created is not None,
            "no new row after 90 seconds",
        )
        if created is not None:
            equals("the algorithm is the one that was requested",
                   created["algorithm"], "logistic_regression")
            equals("activate=false so it must NOT be switched on",
                   int(created["is_active"]), 0)
            check(
                "the model being served did not change",
                _serving_version() == serving_before,
                f"before {serving_before!r}, after {_serving_version()!r}",
            )
            check("the model the checker created was cleaned up",
                  _delete_model(created))
    else:
        print("\n§8.3  skipping the real training run — no ml_training_samples")

    # -- Conclusion --
    print("\n" + "=" * 68)
    if _failures:
        print(f"{len(_failures)}/{_checks} checks FAILED:")
        for x in _failures:
            print("  -", x)
        return 1
    print(f"{_checks}/{_checks} checks passed — the 6 internal endpoints "
          f"behave per the specification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
