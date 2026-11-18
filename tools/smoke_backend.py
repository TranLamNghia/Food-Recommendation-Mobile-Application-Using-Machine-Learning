#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the 17 public endpoints built so far, against the real
database.

This is an INTEGRATION test, not a unit test: it makes real HTTP calls, writes
to real MySQL, and reads back. Why both kinds are needed —
`tools/check_be_parity.py` checks Step 1 as pure arithmetic with no server;
this file checks the things that only break once there is a database and a
network: column-name mapping, data types, transactions, error envelopes, the
order of claims in a JWT.

Every run creates a fresh account with a random email and DELETES it at the
end, so repeated runs do not bloat the database. The `ON DELETE CASCADE` on
the 11 foreign keys into `users` clears away the rest.

Run (the backend must be running):
    python tools/run_backend.py          # in another window
    python tools/smoke_backend.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _env  # noqa: E402

BASE = "http://localhost:5000/api/v1"
#: Overridden by `--base`, so the suite can be pointed at a backend started
#: on another port — which is the normal case when something else already
#: holds 5000.
_base = BASE

_failures: list[str] = []
_checks = 0


def call(method: str, path: str, body=None, token: str | None = None):
    """Call the API; returns `(HTTP status, JSON-decoded body or None)`."""
    url = _base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:300]}


def check(label: str, passed: bool, detail: str = "") -> bool:
    global _checks
    _checks += 1
    print(f"  {'[ok]' if passed else '[BAD]'} {label}"
          + (f"  {detail}" if detail and not passed else ""))
    if not passed:
        _failures.append(f"{label} — {detail}" if detail else label)
    return passed


def equals(label: str, got, want) -> bool:
    return check(label, got == want, f"got {got!r}, wanted {want!r}")


def error_code(body) -> str | None:
    if isinstance(body, dict):
        return (body.get("error") or {}).get("code")
    return None


def _connect():
    import pymysql
    return pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=_env.require("MYSQL_DATABASE"),
        charset="utf8mb4",
    )


def sql(statement: str, params=()):
    """Run one SQL statement and return its rows. Used to set up state the
    API does not allow setting up — disabling an account, for instance."""
    cn = _connect()
    try:
        with cn.cursor() as cur:
            cur.execute(statement, params)
            rows = cur.fetchall()
        cn.commit()
        return rows
    finally:
        cn.close()


def delete_accounts(*emails: str) -> None:
    """Clean up the test accounts. `ON DELETE CASCADE` handles the rest."""
    cn = _connect()
    try:
        with cn.cursor() as cur:
            for email in emails:
                cur.execute("DELETE FROM users WHERE email = %s", (email,))
        cn.commit()
    finally:
        cn.close()


def main(argv: list[str] | None = None) -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep", action="store_true",
        help="do not delete the test account, to inspect it in the database",
    )
    parser.add_argument(
        "--base", default=BASE,
        help="the API root, if the backend is not on the default port",
    )
    args = parser.parse_args(argv)

    global _base
    _base = args.base.rstrip("/")

    email = f"smoke-{uuid.uuid4().hex[:12]}@example.test"
    password = "MatKhau123"
    print(f"End-to-end test against {_base}")
    print(f"Test account: {email}")
    print("=" * 72)

    # -- 7.1.1 Register ---------------------------------------------------
    print("\n7.1.1  POST /auth/register")
    status, body = call("POST", "/auth/register", {
        "email": email, "password": password, "displayName": "Smoke Test"})
    equals("201 Created", status, 201)
    if status != 201:
        print(f"\nCould not register, stopping: {body}")
        return 1

    token = body["accessToken"]
    refresh = body["refreshToken"]
    uid = body["user"]["id"]
    equals("tokenType is Bearer", body["tokenType"], "Bearer")
    equals("expiresIn is 3600 seconds (spec §2.4)", body["expiresIn"], 3600)
    check("user.id is a 36-character UUID", len(uid) == 36, f"length {len(uid)}")
    equals("the email was normalised to lower case", body["user"]["email"],
           email)
    equals("onboardingCompletedAt is null",
           body["user"]["onboardingCompletedAt"], None)
    check("avatarUrl is present and null (§2.3: null, not an omitted field)",
          "avatarUrl" in body["user"] and body["user"]["avatarUrl"] is None)

    # `sub` must be a UUID, not an integer — §2.3.
    import base64
    segment = token.split(".")[1]
    segment += "=" * (-len(segment) % 4)
    claims = json.loads(base64.urlsafe_b64decode(segment))
    equals("the JWT `sub` is users.id (a UUID)", claims.get("sub"), uid)
    equals("the JWT `role` is user", claims.get("role"), "user")
    equals("the JWT `onboarded` is false", claims.get("onboarded"), "false")

    # -- Registering a duplicate email ------------------------------------
    print("\n7.1.1  registering the same email again")
    status, body = call("POST", "/auth/register", {
        "email": email.upper(), "password": password, "displayName": "Other"})
    equals("409", status, 409)
    equals("EMAIL_ALREADY_EXISTS (case does not matter)",
           error_code(body), "EMAIL_ALREADY_EXISTS")

    # -- A validation error must use the §2.5 envelope --------------------
    print("\n§2.5  the validation error envelope")
    status, body = call("POST", "/auth/register", {
        "email": "not-an-email", "password": "short", "displayName": "a"})
    equals("400", status, 400)
    equals("VALIDATION_FAILED", error_code(body), "VALIDATION_FAILED")
    details = (body.get("error") or {}).get("details") or []
    fields = {d.get("field") for d in details}
    check("details names each bad field, in camelCase",
          {"email", "password", "displayName"} <= fields, f"saw {fields}")
    check("a traceId is present", bool((body.get("error") or {}).get("traceId")))

    # -- A password over 72 bytes must be REJECTED, not truncated ---------
    #
    # BCrypt uses only the first 72 bytes and silently drops the rest, so
    # without an upper bound two passwords sharing their first 72 bytes can
    # log in as each other. The bound counts BYTES: 30 "ậ" characters are 30
    # characters but 90 UTF-8 bytes, so a `MaxLength(72)` counted in
    # characters would let it through and then truncate it.
    print("\n§7.1.1  the password upper bound counts UTF-8 bytes")
    long_password = "Aa1" + "ậ" * 30          # 33 characters · 93 bytes
    status, body = call("POST", "/auth/register", {
        "email": f"long-{email}", "password": long_password,
        "displayName": "Byte test"})
    equals("400 for 33 characters but 93 bytes", status, 400)
    equals("VALIDATION_FAILED", error_code(body), "VALIDATION_FAILED")
    details = (body.get("error") or {}).get("details") or []
    check("details names the password field and nothing else",
          {d.get("field") for d in details} == {"password"},
          f"saw {[d.get('field') for d in details]}")
    check("93 bytes > 72 — so this really is a meaningful test",
          len(long_password.encode("utf-8")) > 72
          and len(long_password) <= 72,
          f"{len(long_password)} characters / "
          f"{len(long_password.encode('utf-8'))} bytes")

    # Exactly 72 bytes MUST pass — the bound must not overreach.
    status, _ = call("POST", "/auth/register", {
        "email": f"fits-{email}", "password": "Aa1" + "b" * 69,
        "displayName": "Byte test"})
    equals("201 for exactly 72 bytes", status, 201)

    # -- 7.1.2 Log in -----------------------------------------------------
    print("\n7.1.2  POST /auth/login")
    status, body = call("POST", "/auth/login",
                        {"email": email, "password": password})
    equals("200", status, 200)
    check("a new accessToken is returned", bool(body and body.get("accessToken")))

    status, body = call("POST", "/auth/login",
                        {"email": email, "password": "SaiMatKhau9"})
    equals("401 for a wrong password", status, 401)
    equals("INVALID_CREDENTIALS", error_code(body), "INVALID_CREDENTIALS")

    status, body = call("POST", "/auth/login",
                        {"email": "does-not-exist@example.test",
                         "password": password})
    equals("401 for an email that does not exist", status, 401)
    equals("the same error code — no registered email is revealed",
           error_code(body), "INVALID_CREDENTIALS")

    # -- 7.1.4 Account information ----------------------------------------
    print("\n7.1.4  GET /auth/me")
    status, body = call("GET", "/auth/me", token=token)
    equals("200", status, 200)
    equals("hasHealthProfile is false before the profile is filled in",
           body and body.get("hasHealthProfile"), False)
    equals("preferenceStage is cold with no signals yet",
           body and body.get("preferenceStage"), "cold")

    status, body = call("GET", "/auth/me")
    equals("401 without a token", status, 401)
    status, body = call("GET", "/auth/me", token="junk.junk.junk")
    equals("401 TOKEN_INVALID for a malformed token",
           error_code(body), "TOKEN_INVALID")

    # -- 7.2.3 Targets before a profile exists ----------------------------
    print("\n7.2.3  GET /profile/nutrition-targets with no profile")
    status, body = call("GET", "/profile/nutrition-targets", token=token)
    equals("409", status, 409)
    equals("PROFILE_REQUIRED, not 404", error_code(body), "PROFILE_REQUIRED")

    print("\n7.2.1  GET /profile with no profile")
    status, body = call("GET", "/profile", token=token)
    equals("404 NOT_FOUND", (status, error_code(body)), (404, "NOT_FOUND"))

    # -- 7.2.2 Create the profile -----------------------------------------
    print("\n7.2.2  PUT /profile — creating")
    # The date of birth is DERIVED FROM TODAY so the age is always exactly 22,
    # rather than hard-coded as `2004-11-14` the way the specification's
    # example does.
    #
    # The first version of this file hard-coded that date and expected
    # `age: 22`, then reported 12 failing checks while the backend was
    # entirely correct: the run was on 08 Nov, the 14 Nov birthday had not
    # happened, so the age was 21 and the BMR 1660 rather than 1655. A test
    # whose result changes on exactly one day of the year tests nothing.
    today = date.today()
    birth = date(today.year - 22, today.month, today.day)
    profile = {"gender": "male", "dateOfBirth": birth.isoformat(),
               "heightCm": 172.0, "weightKg": 68.5,
               "activityLevel": "moderate", "goal": "maintain"}
    status, body = call("PUT", "/profile", profile, token=token)
    equals("201 Created the first time", status, 201)
    if status not in (200, 201):
        print(f"\nCould not create the profile, stopping: {body}")
        if not args.keep:
            delete_accounts(email)
        return 1

    targets = body["nutritionTargets"]
    # Exactly the numbers of the §7.2.3 example, after the 1660 -> 1655
    # arithmetic fix.
    equals("bmi 23.15", float(targets["bmi"]), 23.15)
    # 23.15 is over the WHO 2004 Asian threshold of 23. On the international
    # 25/30 thresholds it would be `normal` — and that is the figure the old
    # specification carried.
    equals("bmiCategory overweight (Asian thresholds 23/25)",
           targets["bmiCategory"], "overweight")
    equals("bmrKcal 1655 (not 1660 as the old specification said)",
           targets["bmrKcal"], 1655)
    equals("tdeeKcal 2565", targets["tdeeKcal"], 2565)
    equals("activityFactor 1.550", float(targets["activityFactor"]), 1.55)
    equals("dailyCaloriesTarget 2565", targets["dailyCaloriesTarget"], 2565)
    equals("goalAdjustmentKcal 0 for maintain",
           targets["goalAdjustmentKcal"], 0)
    macros = targets["macroTargets"]
    equals("the macro percentages come from the schema default 15/60/25",
           (macros["proteinPct"], macros["carbsPct"], macros["fatPct"]),
           (15, 60, 25))
    equals("proteinG 96.2", float(macros["proteinG"]), 96.2)
    equals("carbsG 384.8", float(macros["carbsG"]), 384.8)
    equals("fatG 71.3", float(macros["fatG"]), 71.3)
    meals = {m["mealType"]: m for m in targets["mealDistribution"]}
    equals("4 meals", sorted(meals),
           ["breakfast", "dinner", "lunch", "snack"])
    equals("the meal shares are the midpoints of the §3.1 ranges",
           [float(meals[k]["pct"]) for k in
            ("breakfast", "lunch", "dinner", "snack")],
           [27.5, 37.5, 27.5, 7.5])
    equals("kcal per meal", [meals[k]["caloriesKcal"] for k in
                             ("breakfast", "lunch", "dinner", "snack")],
           [705, 962, 705, 192])
    check("formula.expression ends with = 1655",
          targets["formula"]["expression"].endswith("= 1655"),
          targets["formula"]["expression"])
    equals("profile.age 22", body["profile"]["age"], 22)

    print("\n7.2.2  PUT /profile — calling again")
    status, body = call("PUT", "/profile", profile, token=token)
    equals("200, not 201", status, 200)

    print("\n7.2.2  PUT /profile — out-of-range numbers")
    status, body = call("PUT", "/profile", {**profile, "heightCm": 300},
                        token=token)
    equals("400 VALIDATION_FAILED", (status, error_code(body)),
           (400, "VALIDATION_FAILED"))
    status, body = call("PUT", "/profile", {**profile, "gender": "nam"},
                        token=token)
    equals("400 for an invalid enum", (status, error_code(body)),
           (400, "VALIDATION_FAILED"))
    status, body = call("PUT", "/profile",
                        {**profile,
                         "dateOfBirth": date(today.year - 5, 1, 1).isoformat()},
                        token=token)
    equals("400 for an age under 13", (status, error_code(body)),
           (400, "VALIDATION_FAILED"))

    # -- The lose_weight goal: the safety floor at BMR --------------------
    print("\n7.2.2  lose_weight — the limit must not fall below BMR")
    status, body = call("PUT", "/profile",
                        {**profile, "goal": "lose_weight",
                         "activityLevel": "sedentary"}, token=token)
    floored = body["nutritionTargets"]
    check("dailyCaloriesTarget >= bmrKcal",
          floored["dailyCaloriesTarget"] >= floored["bmrKcal"],
          f"{floored['dailyCaloriesTarget']} < {floored['bmrKcal']}")
    # BMR 1655 * 1.2 = 1986; 1986 - 500 = 1486 < 1655 -> floored at BMR.
    equals("floored exactly at BMR", floored["dailyCaloriesTarget"], 1655)
    call("PUT", "/profile", profile, token=token)   # back to maintain

    # -- 7.2.1 and 7.2.3 once a profile exists ----------------------------
    print("\n7.2.1 / 7.2.3  once a profile exists")
    status, body = call("GET", "/profile", token=token)
    equals("GET /profile 200", status, 200)
    equals("conditions is an empty array", body and body.get("conditions"), [])
    status, body = call("GET", "/profile/nutrition-targets", token=token)
    equals("GET nutrition-targets 200", status, 200)
    equals("bmrKcal is still 1655", body and body.get("bmrKcal"), 1655)

    status, body = call("GET", "/auth/me", token=token)
    equals("hasHealthProfile is now true",
           body and body.get("hasHealthProfile"), True)

    # -- 7.2.4 and 7.2.5 medical conditions -------------------------------
    print("\n7.2.4 / 7.2.5  medical conditions")
    status, body = call("GET", "/profile/conditions", token=token)
    equals("200, a bare array", (status, body), (200, []))

    status, body = call("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 2, "severity": "mild", "note": None},
        {"conditionId": 6, "severity": "severe", "note": "test"},
    ]}, token=token)
    equals("200", status, 200)
    check("returns 2 conditions with nameVi looked up from the conditions table",
          isinstance(body, list) and len(body) == 2
          and all(x.get("nameVi") for x in body), str(body)[:120])

    status, body = call("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 2, "severity": "mild"},
        {"conditionId": 2, "severity": "severe"},
    ]}, token=token)
    equals("400 for a repeated conditionId", (status, error_code(body)),
           (400, "VALIDATION_FAILED"))

    status, body = call("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 99999, "severity": "mild"}]}, token=token)
    equals("400 for a conditionId that does not exist",
           (status, error_code(body)), (400, "VALIDATION_FAILED"))

    status, body = call("GET", "/profile/conditions", token=token)
    check("a failed request does NOT lose the existing list (transaction)",
          isinstance(body, list) and len(body) == 2, str(body)[:120])

    status, body = call("PUT", "/profile/conditions", {}, token=token)
    equals("400 when the `conditions` field is absent altogether",
           (status, error_code(body)), (400, "VALIDATION_FAILED"))
    status, body = call("GET", "/profile/conditions", token=token)
    check("a {} body does not wipe the conditions",
          isinstance(body, list) and len(body) == 2, str(body)[:120])

    status, body = call("PUT", "/profile/conditions", {"conditions": []},
                        token=token)
    equals("an empty array clears them all", (status, body), (200, []))

    # -- 7.1.3 Token refresh and reuse detection --------------------------
    print("\n7.1.3  POST /auth/refresh")
    status, body = call("POST", "/auth/refresh", {"refreshToken": refresh})
    equals("200", status, 200)
    refresh2 = body and body.get("refreshToken")
    check("the refreshToken is rotated (the new one differs from the old)",
          bool(refresh2) and refresh2 != refresh)
    check("the response does NOT carry `user` (spec §7.1.3)",
          isinstance(body, dict) and "user" not in body)

    status, body = call("POST", "/auth/refresh", {"refreshToken": refresh})
    equals("401 when resubmitting the rotated token", status, 401)
    equals("TOKEN_INVALID", error_code(body), "TOKEN_INVALID")

    status, body = call("POST", "/auth/refresh", {"refreshToken": refresh2})
    equals("the NEW token is revoked too — the whole family is cut on reuse "
           "detection", status, 401)

    status, body = call("POST", "/auth/refresh",
                        {"refreshToken": "does-not-exist"})
    equals("401 for an invented token", (status, error_code(body)),
           (401, "TOKEN_INVALID"))

    # -- 7.1.3  two CONCURRENT refreshes of the same token ----------------
    #
    # The earlier version READ the token row before WRITING, so two parallel
    # requests both saw `revoked_at IS NULL` and both went through: two live
    # tokens in one family, neither counted as reuse, and the reuse detection
    # was merely decorative. Claiming the row is now a SINGLE
    # `UPDATE … WHERE revoked_at IS NULL`, so exactly one statement wins.
    print("\n7.1.3  two concurrent refreshes (a race)")
    status, body = call("POST", "/auth/login",
                        {"email": email, "password": password})
    race_token = body and body.get("refreshToken")
    check("got a token to race with", bool(race_token))

    # EIGHT threads, not two. This check is PROBABILISTIC: it can only tell
    # the old code from the new one when the requests genuinely overlap. With
    # two threads that happen to queue up, the OLD code also returns
    # [200, 401] — the second sees an already-revoked row and reports reuse —
    # so the test would pass against broken code too.
    #
    # Eight threads firing one token makes overlap all but certain, and the
    # invariant to check is: EXACTLY ONE request gets a 200. The old
    # read-then-write code yields several 200s as soon as two overlap.
    import concurrent.futures as cf
    THREADS = 8
    with cf.ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = [f.result() for f in [
            pool.submit(call, "POST", "/auth/refresh",
                        {"refreshToken": race_token})
            for _ in range(THREADS)]]
    statuses = [s for s, _ in results]
    check(f"exactly ONE request got a 200 out of {THREADS} concurrent ones",
          statuses.count(200) == 1, f"statuses: {sorted(statuses)}")
    check("all the others are 401, never 500",
          all(s == 401 for s in statuses if s != 200),
          f"statuses: {sorted(statuses)}")

    # And the token family must be cut: even the winner is unusable, because
    # a loser triggered revocation of the whole chain.
    winner = next((b for s, b in results if s == 200), None)
    status, _ = call("POST", "/auth/refresh",
                     {"refreshToken": (winner or {}).get("refreshToken", "x")})
    equals("the winner's token is revoked along with the family", status, 401)

    # Counted per FAMILY, not per table. This test logs in several times, and
    # each login opens its OWN token family — those staying alive is correct.
    # The first time I wrote this check I counted the whole table and it
    # reported a failure while the code was entirely right.
    #
    # Follow `replaced_by` from the token that was submitted: the whole chain
    # must be dead.
    import hashlib
    token_hash = hashlib.sha256(race_token.encode()).hexdigest()
    family = sql(
        "WITH RECURSIVE chain AS ("
        "  SELECT id, replaced_by, revoked_at FROM refresh_tokens"
        "   WHERE token_hash = %s"
        "  UNION ALL"
        "  SELECT t.id, t.replaced_by, t.revoked_at FROM refresh_tokens t"
        "   JOIN chain c ON t.id = c.replaced_by)"
        " SELECT COUNT(*), SUM(revoked_at IS NULL) FROM chain",
        (token_hash,))[0]
    check("the whole token family is cut, with no link left alive",
          family[0] >= 2 and family[1] == 0,
          f"{family[0]} links in the chain, {family[1]} still alive")

    # -- 7.4 and 7.6: the taste survey and the meal plan -----------------
    #
    # These two groups are the first that need the ML SERVICE as well as the
    # database, so they are skipped rather than failed when it is not
    # running. A skipped section says so loudly; a failed one would send
    # somebody looking for a bug in the backend.
    print("\n§7.4.1  GET /onboarding/survey")
    status, deck = call("GET", "/onboarding/survey?size=30", token=token)
    if status == 503 and error_code(deck) == "ML_UNAVAILABLE":
        print("  [skip] the ML service is not reachable, so §7.4 and §7.6")
        print("         cannot be tested. Start it and run this again:")
        print("           python tools/run_ml_service.py")
    else:
        equals("the deck returns 200", status, 200)
        deck = deck or {}
        items = deck.get("items") or []
        session_id = deck.get("sessionId")
        check("sessionId is a 36-character UUID",
              isinstance(session_id, str) and len(session_id) == 36,
              f"got {session_id!r}")
        equals("totalItems agrees with the list", deck.get("totalItems"),
               len(items))
        check("minRequired never exceeds the deck",
              0 < deck.get("minRequired", 0) <= len(items),
              f"{deck.get('minRequired')} of {len(items)}")
        ids = [i["id"] for i in items]
        check("no food appears twice in the deck",
              len(ids) == len(set(ids)),
              f"{len(ids) - len(set(ids))} repeats")
        check("every card carries what a swipe screen needs",
              all(i.get("name") and i.get("categoryName")
                  and i.get("dishRole") and i.get("caloriesKcal") is not None
                  and i.get("servingSizeG") for i in items))
        check("dishRole is an ENUM code, not a Vietnamese label — the app "
              "translates it",
              all(i["dishRole"] in ("main", "side_protein", "side_veg",
                                    "soup", "snack", "dessert", "drink")
                  for i in items),
              f"got {sorted({i['dishRole'] for i in items})}")

        status, body = call("GET", "/onboarding/survey?size=5", token=token)
        equals("a deck size below 20 is refused with a named field",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        print("\n§7.4.2  POST /onboarding/survey")
        # Too few opinionated swipes. `unknown` deliberately does not count,
        # so three `unknown` on top change nothing.
        short = [{"foodId": i, "action": "like"} for i in ids[:3]]
        short += [{"foodId": i, "action": "unknown"} for i in ids[3:6]]
        status, body = call("POST", "/onboarding/survey",
                            {"sessionId": session_id, "swipes": short},
                            token=token)
        equals("too few opinionated swipes gives 422 ONBOARDING_INSUFFICIENT",
               (status, error_code(body)), (422, "ONBOARDING_INSUFFICIENT"))

        status, body = call(
            "POST", "/onboarding/survey",
            {"sessionId": session_id,
             "swipes": [{"foodId": ids[0], "action": "like"},
                        {"foodId": ids[0], "action": "dislike"}]},
            token=token)
        equals("the same food twice in one session is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, body = call(
            "POST", "/onboarding/survey",
            {"sessionId": session_id,
             "swipes": [{"foodId": "00000000-0000-4000-8000-000000000000",
                         "action": "like"}]},
            token=token)
        equals("a food that does not exist gives 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        status, body = call(
            "POST", "/onboarding/survey",
            {"sessionId": "not-a-uuid",
             "swipes": [{"foodId": ids[0], "action": "like"}]},
            token=token)
        equals("a sessionId that is not a UUID is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        # The real session: a mixed set, with more than the minimum of
        # opinionated swipes.
        actions = ["like", "dislike", "neutral", "like", "unknown"]
        swipes = [{"foodId": fid, "action": actions[n % len(actions)]}
                  for n, fid in enumerate(ids)]
        opinionated = sum(1 for x in swipes if x["action"] != "unknown")
        status, done = call("POST", "/onboarding/survey",
                            {"sessionId": session_id, "swipes": swipes},
                            token=token)
        equals("the session is accepted", status, 200)
        done = done or {}
        equals("every swipe was recorded",
               (done.get("recorded") or {}).get("total"), len(swipes))
        equals("the opinionated ones are counted apart",
               (done.get("recorded") or {}).get("opinionated"), opinionated)
        equals("and the skipped ones",
               (done.get("recorded") or {}).get("skipped"),
               len(swipes) - opinionated)
        check("onboardingCompletedAt is stamped",
              done.get("onboardingCompletedAt") is not None)
        prof = done.get("preferenceProfile") or {}
        check("a preference profile now exists",
              prof.get("stage") in ("cold", "content", "hybrid", "ml")
              and prof.get("nSignals", 0) > 0,
              f"got {prof}")
        check("alpha is inside 0 to 1",
              0.0 <= prof.get("alpha", -1) <= 1.0,
              f"got {prof.get('alpha')}")
        summary = done.get("tasteSummary") or {}
        check("the closing screen gets a readable summary",
              isinstance(summary.get("topLikedCategories"), list)
              and isinstance(summary.get("topLikedTastes"), list),
              f"got {summary}")
        check("spiceTolerance is a level or null, never a label",
              summary.get("spiceTolerance") is None
              or 0 <= summary["spiceTolerance"] <= 3,
              f"got {summary.get('spiceTolerance')}")

        rows = sql("SELECT COUNT(*) FROM interactions WHERE user_id = %s",
                   (uid,))[0][0]
        equals("the swipes reached `interactions`", rows, len(swipes))
        rows = sql("SELECT COUNT(*) FROM user_preference_profiles "
                   "WHERE user_id = %s", (uid,))[0][0]
        equals("and the vector reached `user_preference_profiles`", rows, 1)
        stamped = sql("SELECT onboarding_completed_at FROM users "
                      "WHERE id = %s", (uid,))[0][0]
        check("the stamp is in the database, not only in the response",
              stamped is not None)

        # Re-submitting the same session must not add a second copy of every
        # swipe — it is the retry path when the ML service times out.
        status, body = call("POST", "/onboarding/survey",
                            {"sessionId": session_id, "swipes": swipes},
                            token=token)
        equals("a second submission gives 409 ONBOARDING_ALREADY_COMPLETED",
               (status, error_code(body)),
               (409, "ONBOARDING_ALREADY_COMPLETED"))
        rows = sql("SELECT COUNT(*) FROM interactions WHERE user_id = %s",
                   (uid,))[0][0]
        equals("and stored no extra rows", rows, len(swipes))

        status, body = call("GET", "/onboarding/survey", token=token)
        equals("the deck is refused once onboarding is done",
               (status, error_code(body)),
               (409, "ONBOARDING_ALREADY_COMPLETED"))

        # -- 7.6 the meal plan --
        print("\n§7.6.2  POST /meal-plans")
        today = date.today().isoformat()
        status, plan = call("POST", "/meal-plans", {"planDate": today},
                            token=token)
        equals("201 Created", status, 201)
        plan = plan or {}
        plan_id = plan.get("id")
        meals = plan.get("meals") or []
        equals("the plan has the four meals", len(meals), 4)
        equals("in the order they are eaten",
               [m["mealType"] for m in meals],
               ["breakfast", "lunch", "dinner", "snack"])
        plan_items = [i for m in meals for i in m["items"]]
        check("the plan has dishes", plan_items != [])
        food_ids = [i["food"]["id"] for i in plan_items]
        check("no dish appears twice in a day",
              len(food_ids) == len(set(food_ids)),
              f"{len(food_ids) - len(set(food_ids))} repeats")
        check("the energy deviation is inside the 10 % commitment",
              abs(plan.get("calorieDeviationPct") or 999) <= 10,
              f"got {plan.get('calorieDeviationPct')} %")
        equals("and withinTolerance agrees", plan.get("withinTolerance"),
               True)
        check("the targets of Step 1 are recorded with the plan",
              (plan.get("targets") or {}).get("caloriesKcal", 0) > 0)
        check("generationSource is one of the four the column allows",
              plan.get("generationSource")
              in ("rule_based", "content_based", "ml", "hybrid"),
              f"got {plan.get('generationSource')}")
        check("explorationRatio is inside what chk_expl_ratio allows",
              0.0 <= float(plan.get("explorationRatio") or 0) <= 0.5,
              f"got {plan.get('explorationRatio')}")
        check("every dish starts as 'suggested'",
              all(i["status"] == "suggested" for i in plan_items),
              f"got {sorted({i['status'] for i in plan_items})}")
        check("every dish has a portion in grams",
              all(i["servingSizeG"] > 0 for i in plan_items))
        check("an exploitation serving sends NULL, not 0 — that is how the "
              "70-30 groups are told apart",
              all(i["explorationDelta"] is None or i["explorationDelta"] > 0
                  for i in plan_items))
        check("each meal's target is its share of the day, not the whole day",
              all(0 < m["targetCaloriesKcal"]
                  < (plan.get("targets") or {}).get("caloriesKcal", 0)
                  for m in meals))

        rows = sql("SELECT COUNT(*) FROM meal_plans WHERE user_id = %s",
                   (uid,))[0][0]
        equals("the plan reached `meal_plans`", rows, 1)
        rows = sql("SELECT COUNT(*) FROM meal_plan_items WHERE meal_plan_id "
                   "= %s", (plan_id,))[0][0]
        equals("and every dish reached `meal_plan_items`", rows,
               len(plan_items))

        status, body = call("POST", "/meal-plans", {"planDate": today},
                            token=token)
        equals("a second plan for the same day gives 409 MEAL_PLAN_EXISTS",
               (status, error_code(body)), (409, "MEAL_PLAN_EXISTS"))

        status, body = call(
            "POST", "/meal-plans",
            {"planDate": today, "mealTypes": ["lunch"]}, token=token)
        equals("one meal at a time is refused, because phase 5 repairs the "
               "whole DAY",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        print("\n§7.6.1  GET /meal-plans")
        status, same = call("GET", f"/meal-plans?date={today}", token=token)
        equals("200", status, 200)
        equals("it is the same plan, not a new one",
               (same or {}).get("id"), plan_id)
        check("a stored plan reports no nutrient verdict rather than an "
              "empty one — nobody checked it for THIS response",
              (same or {}).get("nutrientViolations") is None,
              f"got {(same or {}).get('nutrientViolations')!r}")

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        status, body = call(
            f"GET", f"/meal-plans?date={tomorrow}&autoGenerate=false",
            token=token)
        equals("with autoGenerate=false a missing day is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        print("\n§7.6.3  GET /meal-plans/{id}")
        status, byid = call("GET", f"/meal-plans/{plan_id}", token=token)
        equals("200", status, 200)
        equals("the same day comes back", (byid or {}).get("planDate"), today)
        status, body = call(
            "GET", "/meal-plans/00000000-0000-4000-8000-000000000000",
            token=token)
        equals("a plan that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        # -- 7.6.4 alternatives --
        print("\n§7.6.4  GET /meal-plan-items/{id}/alternatives")
        target_item = next(
            (i for m in meals for i in m["items"]
             if m["mealType"] == "lunch"), plan_items[0])
        item_id = target_item["id"]
        status, alts = call(
            f"GET", f"/meal-plan-items/{item_id}/alternatives?limit=5",
            token=token)
        equals("200", status, 200)
        alts = alts or {}
        options = alts.get("alternatives") or []
        check("at most the requested number comes back", len(options) <= 5,
              f"got {len(options)}")
        equals("the dish being replaced is named",
               (alts.get("originalItem") or {}).get("id"), item_id)
        check("every candidate fills the same role — a soup can only be "
              "replaced by a soup",
              all(o["food"]["dishRole"]
                  == (alts.get("originalItem") or {}).get("dishRole")
                  for o in options),
              f"roles {sorted({o['food']['dishRole'] for o in options})}")
        check("no candidate is already in the plan",
              not ({o["food"]["id"] for o in options} & set(food_ids)))
        check("every predictedScore is in [0, 1]",
              all(0.0 <= o["predictedScore"] <= 1.0 for o in options))
        check("the candidates come back best first",
              [o["predictedScore"] for o in options]
              == sorted((o["predictedScore"] for o in options),
                        reverse=True))
        check("each one says whether the day would still fit in 10 %",
              all(isinstance(o["keepsWithinTolerance"], bool)
                  for o in options))

        status, body = call(
            f"GET", f"/meal-plan-items/{item_id}/alternatives?limit=31",
            token=token)
        equals("a limit above 30 is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        # -- 7.6.5 replace --
        if options:
            print("\n§7.6.5  PUT /meal-plan-items/{id}/replace")
            new_food = options[0]["food"]["id"]
            before = plan.get("actuals", {}).get("caloriesKcal")
            status, after = call(
                "PUT", f"/meal-plan-items/{item_id}/replace",
                {"newFoodId": new_food}, token=token)
            equals("200", status, 200)
            after = after or {}
            after_items = [i for m in after.get("meals", [])
                           for i in m["items"]]
            old_row = next((i for i in after_items if i["id"] == item_id),
                           None)
            check("the old dish is now marked 'replaced'",
                  old_row is not None and old_row["status"] == "replaced",
                  f"got {old_row and old_row['status']}")
            check("and records what it became — the signal §4.6 learns from",
                  old_row is not None
                  and (old_row.get("replacedByFood") or {}).get("id")
                  == new_food)
            check("the new dish is in the plan",
                  new_food in {i["food"]["id"] for i in after_items})
            check("the whole plan comes back, because the day's totals moved",
                  (after.get("actuals") or {}).get("caloriesKcal") is not None
                  and after.get("calorieDeviationPct") is not None)
            check("the replaced dish is not counted in the day any more",
                  (after.get("actuals") or {}).get("caloriesKcal") != before
                  or options[0]["calorieDeltaKcal"] == 0,
                  f"{before} -> "
                  f"{(after.get('actuals') or {}).get('caloriesKcal')}")
            new_row = next(
                (i for i in after_items
                 if i["food"]["id"] == new_food
                 and i["status"] == "suggested"), None)
            check("a hand-picked dish is NOT credited to the exploration "
                  "mechanism",
                  new_row is not None and new_row["explorationDelta"] is None,
                  f"got {new_row and new_row['explorationDelta']}")

            status, body = call(
                "PUT", f"/meal-plan-items/{item_id}/replace",
                {"newFoodId": new_food}, token=token)
            equals("replacing an already-replaced dish is refused",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

            status, body = call(
                "PUT", f"/meal-plan-items/{new_row['id']}/replace",
                {"newFoodId": "00000000-0000-4000-8000-000000000000"},
                token=token)
            equals("a food that does not exist is refused",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

            # -- 7.6.6 status --
            print("\n§7.6.6  PATCH /meal-plan-items/{id}/status")
            status, body = call(
                "PATCH", f"/meal-plan-items/{new_row['id']}/status",
                {"status": "suggested"}, token=token)
            equals("a client may not set a status only the system sets",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

            status, kept = call(
                "PATCH", f"/meal-plan-items/{new_row['id']}/status",
                {"status": "kept"}, token=token)
            equals("'kept' is accepted", status, 200)
            equals("and no diary entry is created for it",
                   (kept or {}).get("diaryEntryCreated"), False)

            status, ate = call(
                "PATCH", f"/meal-plan-items/{new_row['id']}/status",
                {"status": "eaten"}, token=token)
            equals("'eaten' is accepted", status, 200)
            ate = ate or {}
            equals("and writes the diary entry, so the user does not enter "
                   "the meal twice", ate.get("diaryEntryCreated"), True)
            diary_id = ate.get("diaryEntryId")
            check("the diary id comes back as a UUID, not an integer",
                  isinstance(diary_id, str) and len(diary_id) == 36,
                  f"got {diary_id!r}")

            status, again2 = call(
                "PATCH", f"/meal-plan-items/{new_row['id']}/status",
                {"status": "eaten"}, token=token)
            equals("marking it eaten twice does not create a second entry",
                   (again2 or {}).get("diaryEntryCreated"), False)
            equals("and points at the entry that exists",
                   (again2 or {}).get("diaryEntryId"), diary_id)
            rows = sql("SELECT COUNT(*) FROM food_diary WHERE user_id = %s",
                       (uid,))[0][0]
            equals("exactly one diary row for one meal eaten once", rows, 1)

        # Regenerating deletes the old plan, which the app should warn about.
        print("\n§7.6.2  regenerate")
        status, fresh = call(
            "POST", "/meal-plans",
            {"planDate": today, "regenerate": True}, token=token)
        equals("201 with regenerate=true", status, 201)
        check("it is a different plan row",
              (fresh or {}).get("id") != plan_id,
              f"got {(fresh or {}).get('id')}")
        rows = sql("SELECT COUNT(*) FROM meal_plans WHERE user_id = %s",
                   (uid,))[0][0]
        equals("and the old one is gone — uq_user_date allows only one", rows,
               1)
        rows = sql("SELECT COUNT(*) FROM meal_plan_items WHERE meal_plan_id "
                   "= %s", (plan_id,))[0][0]
        equals("its dishes went with it (ON DELETE CASCADE)", rows, 0)

    # -- Time zone: DATETIMEs written by the backend must match MySQL's NOW()
    #
    # The backend once wrote `DateTime.UtcNow`, 7 hours off from the schema's
    # 27 `DEFAULT CURRENT_TIMESTAMP` columns and from every `NOW()` in
    # tools/*.py. Sorting by `created_at` then mixed two clocks.
    print("\n§2.3  every DATETIME on one clock: Asia/Ho_Chi_Minh")
    drift = sql(
        "SELECT TIMESTAMPDIFF(MINUTE, created_at, NOW()) FROM users "
        "WHERE email = %s", (email,))[0][0]
    check("users.created_at is within 5 minutes of NOW()",
          drift is not None and abs(drift) < 5,
          f"off by {drift} minutes — 420 means it is still writing UTC")

    # -- A disabled account: the global filter must block EVERY endpoint --
    #
    # `/auth/me` had always checked `is_active`, but `/profile` had not: a
    # disabled account could read and write its profile for up to an hour,
    # until the accessToken expired. `ActiveAccountFilter` now blocks at
    # the filter layer, so a new endpoint is protected by default.
    print("\n§4  a disabled account — blocked at every authenticated endpoint")
    status, body = call("POST", "/auth/login",
                        {"email": email, "password": password})
    access = body and body.get("accessToken")
    refresh_token = body and body.get("refreshToken")
    check("got a token before disabling", bool(access))

    sql("UPDATE users SET is_active = 0 WHERE email = %s", (email,))

    # The newest endpoints are in this list too. They are protected because
    # `ActiveAccountFilter` is global, not because anyone remembered them —
    # which is the property worth checking, since the two endpoint groups
    # added in this wave never mention `is_active` anywhere.
    for path in ("/auth/me", "/profile", "/profile/nutrition-targets",
                 "/profile/conditions", "/onboarding/survey",
                 f"/meal-plans?date={date.today().isoformat()}"):
        status, body = call("GET", path, token=access)
        equals(f"403 ACCOUNT_DISABLED at GET {path}",
               (status, error_code(body)), (403, "ACCOUNT_DISABLED"))

    status, body = call("PUT", "/profile/conditions", {"conditions": []},
                        token=access)
    equals("403 for PUT too, not only GET", (status, error_code(body)),
           (403, "ACCOUNT_DISABLED"))

    # And no more refreshing either — otherwise disabling an account would
    # take effect for at most an hour.
    status, body = call("POST", "/auth/refresh",
                        {"refreshToken": refresh_token})
    equals("401 when refreshing on a disabled account", status, 401)

    status, body = call("POST", "/auth/login",
                        {"email": email, "password": password})
    equals("403 ACCOUNT_DISABLED when logging in again",
           (status, error_code(body)), (403, "ACCOUNT_DISABLED"))

    sql("UPDATE users SET is_active = 1 WHERE email = %s", (email,))

    # -- Clean up ---------------------------------------------------------
    print()
    if args.keep:
        print(f"Keeping the test account {email} (--keep)")
    else:
        # `fits-` is the account from the exactly-72-byte password check;
        # `long-` never creates a row at all but is deleted anyway, so that a
        # later change to the upper bound leaves no litter behind.
        delete_accounts(email, f"fits-{email}", f"long-{email}")
        print("Deleted 2 test accounts; CASCADE cleared the profile and tokens")

    print("=" * 72)
    if _failures:
        print(f"{len(_failures)}/{_checks} CHECKS FAILED:")
        for x in _failures:
            print("  -", x)
        return 1
    print(f"{_checks}/{_checks} checks passed — 17 endpoints behave per the "
          f"specification against the real database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
