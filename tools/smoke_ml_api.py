#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the ML Service's 4 internal endpoints, against the real
database.

The counterpart of `tools/smoke_backend.py` for the ML layer, and needed for
the same reason: `tools/check_ml.py` checks the formulas as pure arithmetic
with no server, while this file checks the things that **only break once there
is HTTP and a database** — shared-key authentication, error envelopes, the
field-name mapping between Python's `snake_case` and the specification's
`camelCase`, status codes, and the graceful-degradation path.

It creates no new data: it reads a user already in the database and scores
public foods. `POST /profiles/{id}/rebuild` does write — but it writes back
exactly the values `import_swipes` / `import_mo_phong` already computed, so
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
            "Load first: python tools/import_mo_phong.py --apply",
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
    print(f"{_checks}/{_checks} checks passed — the 4 internal endpoints "
          f"behave per the specification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
