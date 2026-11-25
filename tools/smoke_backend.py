#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the 32 public endpoints built so far, against the real
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
    equals("targetWeightKg is null for a 'maintain' goal",
           (body or {}).get("targetWeightKg"), None)

    # -- 7.2.2 the target weight, added by migration 007 -------------------
    #
    # The app asks for it, shows it, and used to lose it on restart: there
    # was no column and no field for it. It takes no part in Step 1 — the
    # energy limit comes from the weight the user has NOW — so the checks
    # below are both halves of that: it survives the round trip, AND it moves
    # nothing.
    print("\n7.2.2  the target weight")
    losing = dict(profile, goal="lose_weight", targetWeightKg=62.5)
    status, body = call("PUT", "/profile", losing, token=token)
    equals("200 with a target weight", status, 200)
    equals("it comes straight back",
           float((body or {})["profile"]["targetWeightKg"]), 62.5)
    status, body = call("GET", "/profile", token=token)
    equals("and it is stored, not just echoed",
           float((body or {})["targetWeightKg"]), 62.5)

    status, body = call("GET", "/profile/nutrition-targets", token=token)
    bmr_with_target = (body or {}).get("bmrKcal")
    equals("the BMR did NOT move — the target is not an input to step 1",
           bmr_with_target, 1655)

    for bad, label in ((19.9, "under 20 kg"), (300.1, "over 300 kg")):
        status, body = call("PUT", "/profile",
                            dict(losing, targetWeightKg=bad), token=token)
        equals(f"a target {label} is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

    # A PUT replaces the whole profile, so leaving the field out clears it.
    # That is how the app drops the target when the goal stops needing one.
    status, body = call("PUT", "/profile", profile, token=token)
    equals("omitting it clears it, because PUT replaces the profile",
           (body or {})["profile"].get("targetWeightKg"), None)
    status, body = call("GET", "/profile", token=token)
    equals("and the clearing was stored too",
           (body or {}).get("targetWeightKg"), None)
    status, body = call("GET", "/profile/nutrition-targets", token=token)
    equals("GET nutrition-targets 200", status, 200)
    equals("bmrKcal is still 1655", body and body.get("bmrKcal"), 1655)

    status, body = call("GET", "/auth/me", token=token)
    equals("hasHealthProfile is now true",
           body and body.get("hasHealthProfile"), True)

    # -- PUT /auth/me: renaming the account --------------------------------
    #
    # Not in the specification. SS6 lists seven authentication endpoints and
    # none of them edits the account's own details, while the app has a
    # settings screen for the display name -- so the name was typed, shown,
    # and gone on the next launch.
    print("\n§7.1.4b  PUT /auth/me")
    status, body = call("PUT", "/auth/me",
                        {"displayName": "  Ten Moi  "}, token=token)
    equals("200", status, 200)
    equals("the name comes back trimmed",
           (body or {}).get("displayName"), "Ten Moi")
    check("and the answer is the same shape as GET /auth/me",
          all(k in (body or {}) for k in
              ("id", "email", "displayName", "hasHealthProfile",
               "preferenceStage")),
          str(sorted((body or {}).keys())))

    status, body = call("GET", "/auth/me", token=token)
    equals("it was stored, not just echoed",
           (body or {}).get("displayName"), "Ten Moi")

    for bad, label in ((" N ", "one letter once trimmed"),
                       ("", "an empty name"),
                       ("x" * 101, "101 characters")):
        status, body = call("PUT", "/auth/me", {"displayName": bad},
                            token=token)
        equals(f"400 VALIDATION_FAILED for {label}",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))
        details = ((body or {}).get("error") or {}).get("details") or []
        check("and the field named is displayName",
              {d.get("field") for d in details} == {"displayName"},
              str([d.get("field") for d in details]))

    status, body = call("PUT", "/auth/me", {"displayName": "Smoke Test"},
                        token=token)
    equals("the original name goes back", status, 200)

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
    # The code comes back too, so the app can recognise what it declared
    # without carrying a table of ids.
    check("each declared condition carries its code",
          isinstance(body, list) and all(x.get("code") for x in body),
          str([x.get("code") for x in (body or [])]))
    by_id = {x["conditionId"]: x for x in (body or [])}
    check("and the severity that was sent",
          by_id.get(2, {}).get("severity") == "mild"
          and by_id.get(6, {}).get("severity") == "severe",
          str({k: v.get("severity") for k, v in by_id.items()}))

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
    # -- 7.3 the lookup dictionaries --
    #
    # Public (no token), and the reason they exist now: the onboarding
    # filter screen takes conditionIds and had no endpoint to get them from.
    print("\n§7.3  GET /conditions · /food-categories · /tags")
    status, conditions = call("GET", "/conditions")
    equals("the condition dictionary is public - no token", status, 200)
    conditions = conditions or []
    check("it is not empty", len(conditions) > 0, f"got {len(conditions)}")
    check(
        "every row carries what the declaration screen needs",
        all(c.get("id") and c.get("nameVi") and c.get("conditionType")
            for c in conditions),
    )
    check(
        "conditionType is an ENUM code, translated by the app",
        all(c["conditionType"] in
            ("disease", "allergy", "intolerance", "diet")
            for c in conditions),
        f"got {sorted({c['conditionType'] for c in conditions})}",
    )
    check(
        "the ids are what POST /onboarding/candidates/count takes",
        all(isinstance(c["id"], int) and c["id"] > 0 for c in conditions),
    )

    # The stable key, added by migration 008. `id` is AUTO_INCREMENT and
    # follows the seed's insert order, so a client cannot hard-code it: the
    # same number means a different illness on a database built in another
    # order. The app ships its own curated question list keyed by `code` and
    # looks the ids up here.
    codes = [c.get("code") for c in conditions]
    check("every condition carries a code", all(codes), f"got {codes}")
    check("and the codes are unique", len(set(codes)) == len(codes))
    check(
        "the code is the one the app and §7.5.2's example use",
        "hypertension" in codes,
        f"got {sorted(c for c in codes if c)}",
    )
    # The allergy the app's list used to be missing while F1 had a working
    # rule for it over 20 dishes.
    check("soy allergy is declarable", "allergy_soy" in codes)

    status, diets = call("GET", "/conditions?type=diet")
    equals("filtering by type returns 200", status, 200)
    check(
        "and really filters",
        diets and all(c["conditionType"] == "diet" for c in diets)
        and len(diets) < len(conditions),
        f"{len(diets or [])} of {len(conditions)}",
    )
    status, body = call("GET", "/conditions?type=nope")
    equals("an invalid type is refused with a named field",
           (status, error_code(body)), (400, "VALIDATION_FAILED"))

    status, categories = call("GET", "/food-categories")
    equals("the category list is public", status, 200)
    check(
        "every category has an id and a Vietnamese name",
        categories and all(c.get("id") and c.get("name") for c in categories),
        f"got {len(categories or [])}",
    )

    status, tags = call("GET", "/tags")
    equals("the tag dictionary is public", status, 200)
    check(
        "every tag has a type the schema declares",
        tags and all(t["tagType"] in ("allergen", "diet", "nutrition")
                     for t in tags),
    )
    check(
        "there is no `taste` tag type - salty and sweet are measured "
        "dimensions, not hand-written labels",
        all(t["tagType"] != "taste" for t in (tags or [])),
    )
    status, body = call("GET", "/tags?type=nope")
    equals("an invalid tag type is refused",
           (status, error_code(body)), (400, "VALIDATION_FAILED"))

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

        # -- 7.4 the onboarding filter screen --
        #
        # In the app this comes BEFORE the deck: the user declares their
        # conditions while watching the catalogue narrow, so the thirty cards
        # drawn afterwards satisfy every one of them. Here the deck call had
        # to come first, because it is what tells us whether the ML service
        # is reachable at all.
        print("\n§7.4  POST /onboarding/candidates/count")
        status, none_yet = call("POST", "/onboarding/candidates/count",
                                {"conditions": []}, token=token)
        equals("200 with nothing declared", status, 200)
        none_yet = none_yet or {}
        catalogue = none_yet.get("totalFoods", 0)
        check("the catalogue is not empty", catalogue > 0,
              f"got {catalogue}")
        equals("nothing declared removes nothing",
               none_yet.get("remainingFoods"), catalogue)
        equals("and removedFoods says so", none_yet.get("removedFoods"), 0)
        check("the roles add up to the remainder",
              sum(none_yet.get("byDishRole", {}).values())
              == none_yet.get("remainingFoods"),
              f"{sum(none_yet.get('byDishRole', {}).values())} against "
              f"{none_yet.get('remainingFoods')}")
        equals("no required role is empty",
               none_yet.get("emptyRequiredRoles"), [])
        equals("and a full survey can be drawn",
               none_yet.get("enoughForSurvey"), True)
        check("dishRole keys are ENUM codes, translated by the app",
              all(r in ("main", "side_protein", "side_veg", "soup",
                        "snack", "dessert", "drink")
                  for r in none_yet.get("byDishRole", {})),
              f"got {sorted(none_yet.get('byDishRole', {}))}")

        # A diet condition is the one kind that really narrows the catalogue:
        # `require_tag` keeps only the foods carrying the tag.
        diet = sql(
            "SELECT c.id FROM conditions c "
            "JOIN condition_rules cr ON cr.condition_id = c.id "
            "WHERE cr.rule_type = 'require_tag' AND cr.is_hard = 1 "
            "LIMIT 1")
        if diet:
            status, narrowed = call(
                "POST", "/onboarding/candidates/count",
                {"conditions": [{"conditionId": int(diet[0][0]),
                                 "severity": "severe"}]},
                token=token)
            equals("200 with one condition declared", status, 200)
            narrowed = narrowed or {}
            check("a require_tag condition really does narrow the catalogue",
                  0 < narrowed.get("remainingFoods", 0) < catalogue,
                  f"{catalogue} -> {narrowed.get('remainingFoods')}")
            equals("and removedFoods is the difference",
                   narrowed.get("removedFoods"),
                   catalogue - narrowed.get("remainingFoods", 0))
            equals("the catalogue total does not move",
                   narrowed.get("totalFoods"), catalogue)

        # The saved conditions must not leak into the answer. The account has
        # none at this point, so the check is that declaring something and
        # then declaring nothing returns to the full catalogue — the screen
        # has to be able to go backwards.
        status, back = call("POST", "/onboarding/candidates/count",
                            {"conditions": []}, token=token)
        equals("un-ticking everything returns to the whole catalogue",
               (back or {}).get("remainingFoods"), catalogue)

        status, body = call(
            "POST", "/onboarding/candidates/count",
            {"conditions": [{"conditionId": 1, "severity": "mild"},
                            {"conditionId": 1, "severity": "severe"}]},
            token=token)
        equals("the same condition twice is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, body = call(
            "POST", "/onboarding/candidates/count",
            {"conditions": [{"conditionId": 999999, "severity": "mild"}]},
            token=token)
        equals("a condition that does not exist is a named field, not a 500",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, body = call(
            "POST", "/onboarding/candidates/count",
            {"conditions": [{"conditionId": 1, "severity": "enormous"}]},
            token=token)
        equals("an invalid severity is refused",
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

        # -- 7.5 the food catalogue --
        #
        # Both endpoints ask the ML service which dishes are safe, so they
        # are in this block. The browse list's own rule is the one worth
        # checking: a page that cannot say which dish is unsafe must not
        # pretend to be filtered.
        print("\n§7.5.1  GET /foods")
        status, page1 = call("GET", "/foods?pageSize=10", token=token)
        equals("200", status, 200)
        page1 = page1 or {}
        equals("the page holds what was asked for",
               len(page1.get("items", [])), 10)
        equals("page is echoed back", page1.get("page"), 1)
        check("totalItems counts the whole catalogue",
              page1.get("totalItems", 0) > 10,
              f"got {page1.get('totalItems')}")
        check(
            "totalPages is the ceiling, not the floor",
            page1.get("totalPages")
            == -(-page1.get("totalItems", 0) // 10),
            f"got {page1.get('totalPages')} for "
            f"{page1.get('totalItems')} items",
        )
        check(
            "with excludeUnsafe defaulting to true, every row is safe",
            all(i["isSafeForUser"] for i in page1.get("items", [])),
        )
        check(
            "every row carries what a list tile needs",
            all(i.get("name") and i.get("categoryName") and i.get("dishRole")
                and i.get("caloriesKcal") is not None and i.get("servingSizeG")
                for i in page1.get("items", [])),
        )

        status, page2 = call("GET", "/foods?pageSize=10&page=2", token=token)
        equals("page 2 returns 200", status, 200)
        check(
            "page 2 shares no row with page 1 - an unstable sort would hide "
            "a food from every page",
            not ({i["id"] for i in page1.get("items", [])}
                 & {i["id"] for i in (page2 or {}).get("items", [])}),
        )

        status, soups = call(
            "GET", "/foods?dishRole=soup&pageSize=100", token=token)
        check(
            "dishRole really filters",
            soups and all(i["dishRole"] == "soup"
                          for i in soups.get("items", [])),
        )

        status, lunch = call(
            "GET", "/foods?mealType=lunch&pageSize=100", token=token)
        equals(
            "mealType returns exactly the roles a lunch can hold",
            sorted({i["dishRole"] for i in (lunch or {}).get("items", [])}),
            ["main", "side_protein", "soup"],
        )

        status, light = call(
            "GET", "/foods?maxCalories=100&pageSize=100", token=token)
        check(
            "maxCalories is a ceiling per serving",
            light and all(i["caloriesKcal"] <= 100
                          for i in light.get("items", [])),
        )

        for query, label in (
            ("page=0", "page 0"),
            ("pageSize=200", "pageSize above the cap"),
            ("dishRole=nope", "an invalid dishRole"),
            ("mealType=brunch", "an invalid mealType"),
            ("maxCalories=0", "a maxCalories of 0"),
        ):
            status, body = call(
                "GET", f"/foods?{query}", token=token)
            equals(f"{label} is refused",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

        print("\n§7.5.2  GET /foods/{id}")
        sample = page1["items"][0]["id"]
        status, detail = call("GET", f"/foods/{sample}", token=token)
        equals("200", status, 200)
        detail = detail or {}
        equals("it is the food asked for", detail.get("id"), sample)
        check("the category comes back as an object with a name",
              (detail.get("category") or {}).get("name"))
        check("nutrition carries the three macros and the serving weight",
              all((detail.get("nutrition") or {}).get(k) is not None
                  for k in ("servingSizeG", "caloriesKcal", "proteinG",
                            "carbsG", "fatG")))
        # A real 0 is a valid measurement — a savoury dish has 0 g of sugar
        # — so "every value is above 0" is the wrong assertion and was one
        # here at first. What has to hold is the other direction: a column
        # that is NULL in the database arrives as null and not as 0. The F1
        # filter EXCLUDES an unmeasured food at a per-serving threshold, so
        # a 0 would say the opposite of what the filter concluded.
        gap = sql(
            "SELECT n.food_id FROM food_nutrition n "
            "JOIN foods f ON f.id = n.food_id "
            "WHERE f.is_active = 1 AND f.owner_id IS NULL "
            "  AND n.purine_mg IS NULL LIMIT 1")
        if gap:
            status, unmeasured = call(
                "GET", f"/foods/{gap[0][0]}", token=token)
            equals("a food with an unmeasured nutrient returns 200",
                   status, 200)
            equals(
                "and that nutrient comes back null, not 0",
                (unmeasured or {}).get("nutrition", {}).get("purineMg"),
                None,
            )
        equals("a safe food has no warnings", detail.get("warnings"), [])
        equals("and says so", detail.get("isSafeForUser"), True)
        equals("myFeedback is null before any rating",
               detail.get("myFeedback"), None)

        status, body = call(
            "GET", "/foods/00000000-0000-4000-8000-000000000000", token=token)
        equals("a food that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        # Declaring a condition has to change both endpoints at once.
        allergy = next(
            (c for c in conditions
             if c["conditionType"] == "allergy"), None)
        if allergy:
            status, _ = call(
                "PUT", "/profile/conditions",
                {"conditions": [{"conditionId": allergy["id"],
                                 "severity": "severe"}]},
                token=token)
            equals("declaring an allergy returns 200", status, 200)

            status, filtered = call(
                "GET", "/foods?pageSize=100", token=token)
            status, everything = call(
                "GET", "/foods?pageSize=100&excludeUnsafe=false", token=token)
            check(
                "excludeUnsafe=true now returns fewer foods than the whole "
                "catalogue",
                (filtered or {}).get("totalItems", 0)
                < (everything or {}).get("totalItems", 0),
                f"{(filtered or {}).get('totalItems')} against "
                f"{(everything or {}).get('totalItems')}",
            )
            flagged = [i for i in (everything or {}).get("items", [])
                       if not i["isSafeForUser"]]
            check(
                "and excludeUnsafe=false shows them flagged instead of "
                "hiding them - a user may still look a dish up",
                flagged != [],
                "no row was flagged unsafe",
            )

            if flagged:
                status, unsafe_detail = call(
                    "GET", f"/foods/{flagged[0]['id']}", token=token)
                equals("the detail of an unsafe food returns 200", status, 200)
                unsafe_detail = unsafe_detail or {}
                equals("it says the food is not safe",
                       unsafe_detail.get("isSafeForUser"), False)
                warnings = unsafe_detail.get("warnings") or []
                check("and gives at least one warning", warnings != [])
                check(
                    "every warning has a Vietnamese sentence and names the "
                    "condition",
                    all(w.get("message") and w.get("conditionName")
                        for w in warnings),
                )
                check(
                    "and points at a condition id the app can act on",
                    all(w.get("conditionId") for w in warnings),
                    f"got {[w.get('conditionId') for w in warnings]}",
                )
                # The field §7.5.2's own example shows. Before migration 008
                # there was no `conditions.code`, so the id went out in its
                # place and the specification said one thing while the API
                # said another.
                check(
                    "and the conditionCode the specification promises",
                    all(w.get("conditionCode") for w in warnings),
                    f"got {[w.get('conditionCode') for w in warnings]}",
                )
                check(
                    "which is a code, not a number",
                    all(isinstance(w.get("conditionCode"), str)
                        and not w["conditionCode"].isdigit()
                        for w in warnings),
                )

            # Put the account back, so the later sections see a clean user.
            call("PUT", "/profile/conditions", {"conditions": []},
                 token=token)

        # -- Bookmarks and blocked dishes --
        #
        # Not in §6's seven. §7.8.1 refuses a rating of a dish that was never
        # in a plan AND never in the diary, deliberately, so there is no
        # table in the specification that accepts an opinion about a dish the
        # user has not eaten. The bookmark and the "không gợi ý món này nữa"
        # switch are exactly that, so they have a table and an endpoint of
        # their own.
        print("\nPUT /foods/{id}/mark")
        marked = page1["items"][0]["id"]
        status, body = call(
            "PUT", f"/foods/{marked}/mark", {"kind": "loved"}, token=token)
        equals("bookmarking a dish returns 200", status, 200)
        body = body or {}
        equals("the mark comes back as set", body.get("kind"), "loved")
        equals("about the food asked for", body.get("foodId"), marked)
        check("and says when it was made", body.get("markedAt"))

        status, again = call(
            "PUT", f"/foods/{marked}/mark", {"kind": "loved"}, token=token)
        equals(
            "sending the same mark twice is idempotent, so a toggle may "
            "re-send rather than track what it sent",
            (status, (again or {}).get("kind")), (200, "loved"))

        status, saved = call("GET", "/foods?mark=loved&pageSize=100",
                             token=token)
        equals("?mark=loved returns 200", status, 200)
        equals("and lists exactly the bookmarked dish",
               [i["id"] for i in (saved or {}).get("items", [])], [marked])
        status, detail_marked = call("GET", f"/foods/{marked}", token=token)
        equals("the detail screen sees the bookmark",
               (detail_marked or {}).get("mark"), "loved")

        status, body = call(
            "PUT", f"/foods/{marked}/mark", {"kind": "blocked"}, token=token)
        equals("switching to blocked returns 200", status, 200)
        equals("and the mark is now blocked", (body or {}).get("kind"),
               "blocked")
        status, saved = call("GET", "/foods?mark=loved&pageSize=100",
                             token=token)
        equals(
            "the bookmark is gone - one row per (user, food), so `saved to "
            "try` and `never suggest this` cannot both be true",
            (saved or {}).get("totalItems"), 0)
        status, blocked_list = call("GET", "/foods?mark=blocked&pageSize=100",
                                    token=token)
        equals("and ?mark=blocked finds it",
               [i["id"] for i in (blocked_list or {}).get("items", [])],
               [marked])

        # The behaviour that matters most here, and the one the F1 change
        # could easily have broken: F1 now subtracts blocked dishes, so a
        # browse list built on "what F1 allows" would delete the dish from
        # search - and the screen that unblocks it is the one it disappeared
        # from. A block is about being SUGGESTED, not about being safe.
        status, searched = call("GET", "/foods?pageSize=100", token=token)
        check(
            "a blocked dish is still findable with excludeUnsafe=true - the "
            "only screen that can unblock it is reached by finding it",
            marked in {i["id"] for i in (searched or {}).get("items", [])},
        )
        blocked_row = next(
            (i for i in (searched or {}).get("items", [])
             if i["id"] == marked),
            None)
        equals("and it is still reported safe to EAT",
               (blocked_row or {}).get("isSafeForUser"), True)
        equals("with the block carried as a mark, not as a warning",
               (blocked_row or {}).get("mark"), "blocked")
        status, detail_blocked = call("GET", f"/foods/{marked}", token=token)
        detail_blocked = detail_blocked or {}
        equals("the detail screen agrees it is safe",
               detail_blocked.get("isSafeForUser"), True)
        equals("and gives no health warning for a preference",
               detail_blocked.get("warnings"), [])

        status, body = call(
            "PUT", f"/foods/{marked}/mark", {"kind": None}, token=token)
        equals("clearing the mark returns 200", status, 200)
        equals("and the mark is gone", (body or {}).get("kind"), None)
        status, body = call(
            "PUT", f"/foods/{marked}/mark", {"kind": None}, token=token)
        equals("clearing a mark that is not there is not an error", status,
               200)

        for payload, label in (
            ({"kind": "hated"}, "a kind outside the ENUM"),
            ({"kind": ""}, "an empty kind"),
        ):
            status, body = call(
                "PUT", f"/foods/{marked}/mark", payload, token=token)
            equals(f"{label} is refused",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))
        status, body = call(
            "PUT", "/foods/00000000-0000-4000-8000-000000000000/mark",
            {"kind": "loved"}, token=token)
        equals("a dish that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        # -- Blocking the last dish of a role a meal needs --
        #
        # The refusal exists because a block is a HARD filter: it sits in the
        # same layer as an allergy, so emptying a required role leaves a day
        # that cannot be assembled at all, not merely a thinner one. The
        # state is built in SQL because building it through the API means
        # blocking a hundred dishes one at a time.
        print("\nPUT /foods/{id}/mark - the last dish of a meal")
        snacks = [r[0] for r in sql(
            "SELECT id FROM foods WHERE is_active = 1 AND owner_id IS NULL "
            "AND dish_role = 'snack' ORDER BY id")]
        check(
            "the catalogue has snack dishes to work with",
            len(snacks) >= 2, f"got {len(snacks)}")
        if len(snacks) >= 2:
            last, rest = snacks[0], snacks[1:]
            sql(
                "INSERT INTO user_food_marks (user_id, food_id, kind) VALUES "
                + ", ".join(["(%s, %s, 'blocked')"] * len(rest)),
                tuple(x for food_id in rest for x in (uid, food_id)))
            status, body = call(
                "PUT", f"/foods/{last}/mark", {"kind": "blocked"}, token=token)
            equals(
                f"blocking the last of {len(snacks)} snack dishes is refused",
                (status, error_code(body)),
                (409, "BLOCK_WOULD_EMPTY_MEAL"))
            message = ((body or {}).get("error") or {}).get("message") or ""
            check(
                "and the refusal names the meal that would break, so the "
                "user knows what the choice costs",
                "bữa phụ" in message, f"got {message!r}")
            rows = sql(
                "SELECT COUNT(*) FROM user_food_marks WHERE user_id = %s "
                "AND food_id = %s", (uid, last))[0][0]
            equals("and nothing was written - a refusal must not half-apply",
                   rows, 0)

            # One left in the role is enough: the refusal is about zero, not
            # about few. Losing a dish is the user's choice to make; losing a
            # meal is not a choice, it is a plan that cannot be built.
            sql(
                "DELETE FROM user_food_marks WHERE user_id = %s AND food_id "
                "= %s", (uid, rest[0]))
            status, body = call(
                "PUT", f"/foods/{last}/mark", {"kind": "blocked"}, token=token)
            equals(
                "with one dish left in the role it goes through - the "
                "threshold is zero left, not few left",
                (status, (body or {}).get("kind")), (200, "blocked"))

            sql("DELETE FROM user_food_marks WHERE user_id = %s", (uid,))
            rows = sql(
                "SELECT COUNT(*) FROM user_food_marks WHERE user_id = %s",
                (uid,))[0][0]
            equals("the marks were cleared before the plan sections", rows, 0)

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

        # -- 7.6.2b rebuild one meal of the day --
        #
        # The feature §7.6.2's `mealTypes` was asking for, as its own
        # endpoint. What is being checked is the property that makes it safe
        # to have: the plan row stays the DAY's row, so the figure in
        # `calorie_deviation_pct` is still a deviation over a day.
        print("\n§7.6.2b  POST /meal-plans/{id}/meals/{mealType}")
        status, day_before = call(
            "GET", f"/meal-plans/{plan_id}", token=token)
        before_by_meal = {
            m["mealType"]: [i["food"]["id"] for i in m["items"]]
            for m in (day_before or {}).get("meals", [])
        }

        status, rolled = call(
            "POST", f"/meal-plans/{plan_id}/meals/snack", token=token)
        equals("200", status, 200)
        rolled = rolled or {}
        equals("it is the SAME plan row, not a new one",
               rolled.get("id"), plan_id)
        equals("and still the same day", rolled.get("planDate"),
               (day_before or {}).get("planDate"))
        after_by_meal = {
            m["mealType"]: [i["food"]["id"] for i in m["items"]]
            for m in rolled.get("meals", [])
        }
        for meal in ("breakfast", "lunch", "dinner"):
            equals(f"{meal} is untouched", after_by_meal.get(meal),
                   before_by_meal.get(meal))
        check("the snack really changed — re-rolling a meal that returns the "
              "same dish would look broken",
              after_by_meal.get("snack") != before_by_meal.get("snack")
              or before_by_meal.get("snack") == [],
              f"{before_by_meal.get('snack')} -> "
              f"{after_by_meal.get('snack')}")
        check("the day's energy is recomputed over all four meals",
              (rolled.get("actuals") or {}).get("caloriesKcal") is not None
              and rolled.get("calorieDeviationPct") is not None)
        check("and the deviation is still a figure about a DAY: the target "
              "did not shrink to one meal's share",
              (rolled.get("targets") or {}).get("caloriesKcal")
              == (day_before or {}).get("targets", {}).get("caloriesKcal"))
        ids_after = [i["food"]["id"] for m in rolled.get("meals", [])
                     for i in m["items"]
                     if i["status"] != "replaced"]
        check("no dish is served twice after the rebuild",
              len(ids_after) == len(set(ids_after)),
              f"repeats: {len(ids_after) - len(set(ids_after))}")

        rows = sql("SELECT COUNT(*) FROM meal_plans WHERE user_id = %s",
                   (uid,))[0][0]
        equals("there is still exactly one plan for the day", rows, 1)

        status, body = call(
            "POST", f"/meal-plans/{plan_id}/meals/brunch", token=token)
        equals("a meal that is not one of the four is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, body = call(
            "POST",
            "/meal-plans/00000000-0000-4000-8000-000000000000/meals/snack",
            token=token)
        equals("a plan that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        # The lunch holds the dish marked `eaten` a moment ago. A meal that
        # has been eaten cannot be re-planned: that dish is in the food diary
        # and is a preference signal of weight 0.9.
        status, body = call(
            "POST", f"/meal-plans/{plan_id}/meals/lunch", token=token)
        equals("a meal with a dish already eaten cannot be rebuilt",
               (status, error_code(body)), (409, "VALIDATION_FAILED"))

        # -- 7.7 the food diary, and 7.8 the ratings --
        #
        # Inside the ML-dependent section because both rest on a plan: the
        # undo of §7.7.4 hands a dish back to it, and the first condition of
        # §7.8.1 is that the dish was suggested at all. One diary row exists
        # at this point, written by the `eaten` of §7.6.6 above.
        #
        # `plan` is the response from when the plan was first generated, and
        # since then §7.6.5 replaced a dish and §7.6.2b rewrote a whole meal.
        # Its item ids and food ids are stale, so read the plan as it stands.
        status, plan_now = call("GET", f"/meal-plans?date={today}",
                                token=token)
        equals("the plan as it stands now reads back", status, 200)
        plan_now = plan_now or {}

        print("\n§7.7.1  GET /food-diary")
        status, diary = call(
            "GET", f"/food-diary?from={today}&to={today}", token=token)
        equals("200", status, 200)
        diary = diary or {}
        days = diary.get("days") or []
        equals("one day has entries", len(days), 1)
        entries = (days[0] if days else {}).get("entries") or []
        equals("and it holds the one dish marked eaten", len(entries), 1)
        planned_entry = entries[0] if entries else {}
        equals("which came from the plan", planned_entry.get("fromMealPlan"),
               True)
        equals("has not been rated yet", planned_entry.get("hasFeedback"),
               False)
        equals("so it can still be corrected or taken back",
               planned_entry.get("editable"), True)
        check("the portion is reported in grams",
              (planned_entry.get("servingSizeG") or 0) > 0,
              f"got {planned_entry.get('servingSizeG')}")
        check("and the energy of that portion, not of one serving",
              (planned_entry.get("actualCaloriesKcal") or 0) > 0,
              f"got {planned_entry.get('actualCaloriesKcal')}")
        equals("the day's total matches its entries",
               (days[0] if days else {}).get("totalCaloriesKcal"),
               planned_entry.get("actualCaloriesKcal"))

        for query, label in (
                ("", "no from and no to"),
                (f"?from={today}", "a from with no to"),
                (f"?from={today}&to=2099-12-31", "a range over 90 days"),
                (f"?from={today}&to=2000-01-01", "a to before the from"),
                (f"?from={today}&to={today}&mealType=brunch",
                 "a meal that does not exist")):
            status, body = call("GET", f"/food-diary{query}", token=token)
            equals(f"400 VALIDATION_FAILED for {label}",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

        eaten_meal = planned_entry.get("mealType")
        status, filtered = call(
            "GET", f"/food-diary?from={today}&to={today}"
                   f"&mealType={eaten_meal}", token=token)
        equals("filtering by the meal it was eaten at keeps it",
               len(((filtered or {}).get("days") or [{}])[0]
                   .get("entries") or []), 1)
        other_meal = next(m for m in ("breakfast", "lunch", "dinner", "snack")
                          if m != eaten_meal)
        status, filtered = call(
            "GET", f"/food-diary?from={today}&to={today}"
                   f"&mealType={other_meal}", token=token)
        equals("filtering by another meal leaves nothing",
               len((filtered or {}).get("days") or []), 0)

        # -- 7.7.2 record something eaten --
        print("\n§7.7.2  POST /food-diary")
        status, catalogue = call(
            "GET", "/foods?excludeUnsafe=false&pageSize=100", token=token)
        in_plan = {i["food"]["id"] for m in (plan_now.get("meals") or [])
                   for i in m["items"]}
        outside = next(
            (f for f in (catalogue or {}).get("items") or []
             if f["id"] not in in_plan), None)
        check("the catalogue has a dish that is not in today's plan",
              outside is not None)

        status, added = call(
            "POST", "/food-diary",
            {"foodId": outside["id"], "ateOn": today, "mealType": "snack",
             "servingSizeG": 100}, token=token)
        equals("201 for a dish bought outside the plan", status, 201)
        added = added or {}
        equals("and it is NOT marked as coming from the plan",
               added.get("fromMealPlan"), False)
        own_entry_id = added.get("id")

        status, body = call(
            "POST", "/food-diary",
            {"foodId": outside["id"], "ateOn": today, "mealType": "snack"},
            token=token)
        equals("the same dish twice in one meal is 409, because §8.4 "
               "joins on those four columns",
               (status, error_code(body)), (409, "VALIDATION_FAILED"))

        status, body = call(
            "POST", "/food-diary",
            {"foodId": outside["id"], "ateOn": "2099-01-01",
             "mealType": "snack"}, token=token)
        equals("a day that has not come yet is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, body = call(
            "POST", "/food-diary",
            {"foodId": "00000000-0000-4000-8000-000000000000",
             "ateOn": today, "mealType": "snack"}, token=token)
        equals("a dish that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        status, body = call(
            "POST", "/food-diary",
            {"foodId": outside["id"], "ateOn": today, "mealType": "dinner",
             "servingSizeG": 1}, token=token)
        equals("1 gram is under chk_diary_portion's tenth of a serving",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        # The property of §7.7.2 that matters most: the diary does NOT apply
        # the F1 filter. A user records what they actually ate, including a
        # dish their own condition makes unsafe — refusing it would make the
        # diary a record of what the system approves of rather than of what
        # happened, and would lose the 0.9-weight label with it.
        #
        # §7.5 cleared the account's conditions so that the plan section saw
        # a clean user, so the allergy is declared again here and cleared
        # again afterwards. Without it nothing in the catalogue is unsafe and
        # there is no way to show the property at all.
        allergy_again = next(
            (c for c in conditions if c["conditionType"] == "allergy"), None)
        check("there is an allergy to declare", allergy_again is not None)
        call("PUT", "/profile/conditions",
             {"conditions": [{"conditionId": allergy_again["id"],
                              "severity": "severe"}]}, token=token)
        status, flagged_page = call(
            "GET", "/foods?excludeUnsafe=false&pageSize=100", token=token)
        unsafe = next(
            (f for f in (flagged_page or {}).get("items") or []
             if not f.get("isSafeForUser") and f["id"] != outside["id"]),
            None)
        check("declaring it makes some dish unsafe", unsafe is not None,
              "nothing was flagged, so the property cannot be shown")
        status, recorded = call(
            "POST", "/food-diary",
            {"foodId": unsafe["id"], "ateOn": today,
             "mealType": "breakfast"}, token=token)
        equals("a dish that F1 excludes is still recorded — the diary is "
               "not filtered", status, 201)
        equals("and §7.5 would have hidden that same dish",
               unsafe.get("isSafeForUser"), False)
        sql("DELETE FROM food_diary WHERE id = %s",
            ((recorded or {}).get("id"),))
        call("PUT", "/profile/conditions", {"conditions": []}, token=token)

        # -- 7.7.3 correct a line --
        print("\n§7.7.3  PUT /food-diary/{id}")
        status, edited = call(
            "PUT", f"/food-diary/{own_entry_id}",
            {"servingSizeG": 50}, token=token)
        equals("200 when only the portion is sent", status, 200)
        check("the portion came down",
              (edited or {}).get("servingSizeG", 999)
              < added.get("servingSizeG", 0),
              f"{added.get('servingSizeG')} -> "
              f"{(edited or {}).get('servingSizeG')}")
        check("and so did the energy",
              (edited or {}).get("actualCaloriesKcal", 1e9)
              < added.get("actualCaloriesKcal", 0))

        different = next(f["id"] for f in (catalogue or {}).get("items") or []
                         if f["id"] != outside["id"])
        status, body = call(
            "PUT", f"/food-diary/{own_entry_id}",
            {"foodId": different}, token=token)
        equals("the dish of a line cannot be swapped — a rating would "
               "follow it across",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))
        status, body = call(
            "PUT", f"/food-diary/{own_entry_id}",
            {"ateOn": "2026-01-01"}, token=token)
        equals("nor can the day, whose plan and limits are different ones",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))
        status, body = call(
            "PUT", "/food-diary/00000000-0000-4000-8000-000000000000",
            {"servingSizeG": 100}, token=token)
        equals("a line that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        # -- 7.7.5 the day against its limits --
        print("\n§7.7.5  GET /food-diary/summary")
        status, summary = call(
            "GET", f"/food-diary/summary?date={today}", token=token)
        equals("200", status, 200)
        summary = summary or {}

        # The trap this endpoint exists to avoid. Step 1 already has three
        # implementations held in parity; the summary must READ the limits the
        # day was planned against, not work them out again.
        equals("the targets are the plan's own snapshot, not a fresh "
               "calculation",
               (summary.get("targets") or {}).get("caloriesKcal"),
               (plan_now.get("targets") or {}).get("caloriesKcal"))
        for macro in ("proteinG", "carbsG", "fatG"):
            equals(f"and the same for {macro}",
                   (summary.get("targets") or {}).get(macro),
                   (plan_now.get("targets") or {}).get(macro))

        status, after_edit = call(
            "GET", f"/food-diary?from={today}&to={today}", token=token)
        all_entries = [e for d in ((after_edit or {}).get("days") or [])
                       for e in d["entries"]]
        equals("consumed is the sum of the day's entries",
               (summary.get("consumed") or {}).get("caloriesKcal"),
               round(sum(e["actualCaloriesKcal"] for e in all_entries), 2))

        by_meal = summary.get("byMeal") or []
        equals("byMeal covers all four meals in the order of the day",
               [m["mealType"] for m in by_meal],
               ["breakfast", "lunch", "dinner", "snack"])
        equals("and its energy adds up to what was consumed",
               round(sum(m["caloriesKcal"] for m in by_meal), 2),
               (summary.get("consumed") or {}).get("caloriesKcal"))
        day_target = (summary.get("targets") or {}).get("caloriesKcal") or 0
        check("the four meal targets add up to the day's, give or take "
              "rounding",
              abs(sum(m["targetCaloriesKcal"] for m in by_meal)
                  - day_target) <= 2,
              f"{sum(m['targetCaloriesKcal'] for m in by_meal)} vs "
              f"{day_target}")

        remaining = summary.get("remaining") or {}
        equals("remaining is the target less what was eaten",
               remaining.get("caloriesKcal"),
               round(day_target
                     - ((summary.get("consumed") or {})
                        .get("caloriesKcal") or 0), 2))

        for micro in summary.get("micronutrients") or []:
            check(f"{micro['nutrient']} has a Vietnamese name, not a column "
                  "name",
                  micro["nameVi"] != micro["nutrient"],
                  f"got {micro['nameVi']!r}")
            check(f"{micro['nutrient']} has a unit", bool(micro["unit"]))
            check(f"{micro['nutrient']}'s percentage matches its two "
                  "figures",
                  micro["rda"] <= 0
                  or abs(micro["pct"]
                         - round(100 * micro["consumed"] / micro["rda"], 1))
                  <= 0.1,
                  f"{micro['consumed']}/{micro['rda']} != {micro['pct']}%")
        check("no macronutrient appears among the micronutrients, which "
              "would send the same figure twice",
              not ({m["nutrient"] for m in
                    summary.get("micronutrients") or []}
                   & {"calories_kcal", "protein_g", "carbs_g", "fat_g"}))

        compliance = summary.get("planCompliance") or {}
        plan_items = sum(
            len(m["items"]) for m in (plan_now.get("meals") or []))
        check("suggestedItems counts every dish of the plan, as §8.4 "
              "does",
              compliance.get("suggestedItems", 0) >= plan_items,
              f"{compliance.get('suggestedItems')} vs {plan_items} seen "
              "in the response")
        check("eatenItems never exceeds what was suggested",
              compliance.get("eatenItems", 0)
              <= compliance.get("suggestedItems", 0))
        check("and the percentage agrees with the two counts",
              compliance.get("suggestedItems") == 0
              or abs((compliance.get("compliancePct") or 0)
                     - round(100 * compliance["eatenItems"]
                             / compliance["suggestedItems"], 2)) <= 0.01,
              f"{compliance}")

        status, body = call("GET", "/food-diary/summary", token=token)
        equals("a summary with no date is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        # An account with no health profile has no limits to be measured
        # against — the same 409 §7.2.3 gives, and the same screen to send
        # the user to.
        status, spare = call("POST", "/auth/login",
                             {"email": f"fits-{email}",
                              "password": "Aa1" + "b" * 69})
        spare_token = (spare or {}).get("accessToken")
        if spare_token:
            status, body = call(
                "GET", f"/food-diary/summary?date={today}",
                token=spare_token)
            equals("409 PROFILE_REQUIRED without a health profile",
                   (status, error_code(body)), (409, "PROFILE_REQUIRED"))
            status, body = call(
                "DELETE", f"/food-diary/{own_entry_id}", token=spare_token)
            equals("403 FORBIDDEN deleting someone else's line",
                   (status, error_code(body)), (403, "FORBIDDEN"))
            status, body = call(
                "PUT", f"/food-diary/{own_entry_id}",
                {"servingSizeG": 100}, token=spare_token)
            equals("403 FORBIDDEN editing someone else's line",
                   (status, error_code(body)), (403, "FORBIDDEN"))

        # -- 7.8.1 the two conditions --
        print("\n§7.8.1  POST /feedbacks")
        eaten_food = (planned_entry.get("food") or {}).get("id")
        never_suggested = next(
            f["id"] for f in (catalogue or {}).get("items") or []
            if f["id"] not in in_plan and f["id"] != outside["id"])
        status, body = call(
            "POST", "/feedbacks", {"foodId": never_suggested, "rating": 5},
            token=token)
        equals("a dish never suggested cannot be rated — condition ①",
               (status, error_code(body)), (409, "FEEDBACK_NOT_ALLOWED"))

        not_eaten = next(
            (i["food"]["id"] for m in (plan_now.get("meals") or [])
             for i in m["items"] if i["food"]["id"] != eaten_food), None)
        if not_eaten:
            status, body = call(
                "POST", "/feedbacks", {"foodId": not_eaten, "rating": 4},
                token=token)
            equals("a dish suggested but not eaten cannot be rated — "
                   "condition ②",
                   (status, error_code(body)), (409, "FEEDBACK_NOT_ALLOWED"))

        status, body = call(
            "POST", "/feedbacks", {"foodId": outside["id"], "rating": 4},
            token=token)
        equals("a dish eaten but never suggested cannot be rated either",
               (status, error_code(body)), (409, "FEEDBACK_NOT_ALLOWED"))

        status, body = call(
            "POST", "/feedbacks",
            {"foodId": "00000000-0000-4000-8000-000000000000", "rating": 4},
            token=token)
        equals("a dish that does not exist is 404",
               (status, error_code(body)), (404, "NOT_FOUND"))

        for rating in (0, 6):
            status, body = call(
                "POST", "/feedbacks",
                {"foodId": eaten_food, "rating": rating}, token=token)
            equals(f"{rating} stars is outside chk_rating",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))
        status, body = call(
            "POST", "/feedbacks",
            {"foodId": eaten_food, "rating": 3, "comment": "x" * 1001},
            token=token)
        equals("a comment over 1000 characters is refused",
               (status, error_code(body)), (400, "VALIDATION_FAILED"))

        status, rated = call(
            "POST", "/feedbacks",
            {"foodId": eaten_food, "rating": 5, "comment": "Ngon"},
            token=token)
        equals("201 for the dish that was both suggested and eaten", status,
               201)
        rated = rated or {}
        equals("the response names the dish", rated.get("foodId"),
               eaten_food)
        equals("and reports that the preference vector was rebuilt from it",
               rated.get("profileUpdated"), True)

        # Taste changes, and §7.8.1 says so: a second rating is a new row,
        # not an overwrite. `idx_user_food_time` is what makes the latest one
        # cheap to find, and the dataset step takes the latest as of its own
        # cut-off.
        status, again3 = call(
            "POST", "/feedbacks",
            {"foodId": eaten_food, "rating": 2, "comment": "Ăn lại "
             "thấy dở"}, token=token)
        equals("201 rating the same dish a second time", status, 201)
        check("it is a new row, not an overwrite",
              (again3 or {}).get("id") != rated.get("id"))
        rows = sql("SELECT COUNT(*) FROM feedbacks WHERE user_id = %s AND "
                   "food_id = %s", (uid, eaten_food))[0][0]
        equals("so both ratings are kept", rows, 2)

        # -- the lock --
        #
        # A rating is the system's most trusted label, and §7.8.1 requires a
        # diary line behind it. Once rated, the line that could be that
        # evidence stops being editable: "I have not eaten this" and "it was
        # worth five stars" cannot both be true.
        print("\n§7.7.3/§7.7.4  a rated line is locked")
        status, locked_view = call(
            "GET", f"/food-diary?from={today}&to={today}", token=token)
        rated_line = next(
            (e for d in ((locked_view or {}).get("days") or [])
             for e in d["entries"]
             if e["food"]["id"] == eaten_food), None)
        check("the rated line is still in the diary", rated_line is not None)
        equals("it reports the rating", (rated_line or {}).get("hasFeedback"),
               True)
        equals("and reports that it can no longer be changed",
               (rated_line or {}).get("editable"), False)

        status, body = call(
            "DELETE", f"/food-diary/{(rated_line or {}).get('id')}",
            token=token)
        equals("409 deleting a rated line",
               (status, error_code(body)), (409, "VALIDATION_FAILED"))
        status, body = call(
            "PUT", f"/food-diary/{(rated_line or {}).get('id')}",
            {"servingSizeG": 120}, token=token)
        equals("409 editing one too — otherwise the rating could be moved "
               "to another dish",
               (status, error_code(body)), (409, "VALIDATION_FAILED"))

        # -- 7.7.4 the two deletes --
        #
        # A line the user typed in is removed. A line that exists only
        # because they tapped "eaten" on a planned dish is UNDONE: the dish
        # goes back to the plan as `suggested` and shows up on the plan
        # screen again. Only something that never happened can be taken
        # away.
        print("\n§7.7.4  DELETE /food-diary/{id}")
        status, _ = call("DELETE", f"/food-diary/{own_entry_id}",
                         token=token)
        equals("204 deleting the line the user typed in", status, 204)
        rows = sql("SELECT COUNT(*) FROM food_diary WHERE id = %s",
                   (own_entry_id,))[0][0]
        equals("and it is gone", rows, 0)

        undo_item = next(
            (i for m in (plan_now.get("meals") or []) for i in m["items"]
             if i["food"]["id"] != eaten_food), None)
        if undo_item:
            status, marked = call(
                "PATCH", f"/meal-plan-items/{undo_item['id']}/status",
                {"status": "eaten"}, token=token)
            equals("a second planned dish is marked eaten", status, 200)
            undo_entry = (marked or {}).get("diaryEntryId")
            status, _ = call("DELETE", f"/food-diary/{undo_entry}",
                             token=token)
            equals("204 taking that tap back", status, 204)
            rows = sql("SELECT status FROM meal_plan_items WHERE id = %s",
                       (undo_item["id"],))
            equals("and the dish is back on the plan as 'suggested', not "
                   "deleted", rows and rows[0][0], "suggested")
            rows = sql("SELECT COUNT(*) FROM food_diary WHERE id = %s",
                       (undo_entry,))[0][0]
            equals("while the diary line it came from is gone", rows, 0)

        # -- 7.8.2 my ratings --
        print("\n§7.8.2  GET /feedbacks")
        status, mine = call("GET", "/feedbacks", token=token)
        equals("200", status, 200)
        mine = mine or {}
        equals("both ratings are listed", mine.get("totalItems"), 2)
        equals("one page of them", mine.get("totalPages"), 1)
        items = mine.get("items") or []
        # Not "the 2-star one is on top". `feedbacks.created_at` is a
        # DATETIME, so it stores whole seconds — and these two ratings were
        # sent within one second of each other, which means the data simply
        # does not record which came later. Asserting an order the column
        # cannot express is a check that passes or fails on timing.
        #
        # What the endpoint does promise, and what the app shows, is that the
        # list runs newest to oldest. That is checkable.
        stamps = [i.get("createdAt") for i in items]
        check("the list runs newest to oldest",
              stamps == sorted(stamps, reverse=True), str(stamps))
        check("and both ratings are in it",
              {i.get("rating") for i in items} == {5, 2},
              str([i.get("rating") for i in items]))
        check("each row carries the dish it is about",
              all((i.get("food") or {}).get("name") for i in items))

        status, one = call(
            "GET", f"/feedbacks?foodId={eaten_food}", token=token)
        equals("filtering by dish finds both of them",
               (one or {}).get("totalItems"), 2)
        status, none_of = call(
            "GET", f"/feedbacks?foodId={never_suggested}", token=token)
        equals("and finds none for a dish never rated",
               (none_of or {}).get("totalItems"), 0)

        status, p1 = call("GET", "/feedbacks?page=1&pageSize=1", token=token)
        status, p2 = call("GET", "/feedbacks?page=2&pageSize=1", token=token)
        equals("two pages of one", (p1 or {}).get("totalPages"), 2)
        check("and the two pages hold different ratings",
              ((p1 or {}).get("items") or [{}])[0].get("id")
              != ((p2 or {}).get("items") or [{}])[0].get("id"))

        for query, label in (("?page=0", "page 0"),
                             ("?pageSize=0", "pageSize 0"),
                             ("?pageSize=500", "pageSize 500")):
            status, body = call("GET", f"/feedbacks{query}",
                                token=token)
            equals(f"400 VALIDATION_FAILED for {label}",
                   (status, error_code(body)), (400, "VALIDATION_FAILED"))

        # Regenerating an UNTOUCHED day deletes the old plan and builds
        # another, which the app should warn about. The day has to be clean
        # for that: once anything has been eaten the scope narrows to the
        # meals that have not, which the next section is about. Earlier
        # sections eat dishes, so the state is reset here rather than
        # assumed.
        print("\n§7.6.2  regenerate an untouched day")
        sql("DELETE FROM food_diary WHERE user_id = %s", (uid,))
        sql("DELETE FROM meal_plans WHERE user_id = %s", (uid,))
        status, before_regen = call(
            "POST", "/meal-plans", {"planDate": today}, token=token)
        equals("a clean day to regenerate", status, 201)
        plan_id = (before_regen or {}).get("id")

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

        # -- Regenerating after the day has been eaten --
        #
        # The hole this closes, in one sentence: regenerating used to build a
        # fresh day at the FULL energy target whatever had been eaten from
        # the old one. The eaten dishes were excluded from the candidate set,
        # so the new day did not repeat them, but nothing subtracted their
        # energy and nothing added the diary to the plan. Eat your 2 542 kcal
        # day, press the button, and the answer was a second whole day
        # reporting itself at about -1 % of target.
        #
        # The scope now follows the state of the day, and the request body is
        # unchanged - one call still replaces a whole untouched day.
        print("\n§7.6.2  regenerate after eating part of the day")

        def energy_of(p):
            return sum(float(i["food"]["caloriesKcal"])
                       for m in (p or {}).get("meals", [])
                       for i in m["items"] if i["status"] != "replaced")

        # From a known state: earlier sections eat dishes, and this block is
        # about what regenerating does to a day that has been eaten from, so
        # it has to choose how much of it has.
        sql("DELETE FROM food_diary WHERE user_id = %s", (uid,))
        sql("DELETE FROM meal_plans WHERE user_id = %s", (uid,))
        status, base_plan = call(
            "POST", "/meal-plans", {"planDate": today}, token=token)
        equals("a fresh day to work from", status, 201)
        target_kcal = float((base_plan["targets"] or {})["caloriesKcal"])
        whole_day = energy_of(base_plan)
        by_meal = {m["mealType"]: m["items"] for m in base_plan["meals"]}

        # Eat the whole of breakfast, and nothing else.
        eaten_kcal = 0.0
        for item in by_meal["breakfast"]:
            st, _ = call("PATCH", f"/meal-plan-items/{item['id']}/status",
                         {"status": "eaten"}, token=token)
            equals("a dish is marked eaten", st, 200)
            eaten_kcal += float(item["food"]["caloriesKcal"])

        status, partial = call(
            "POST", "/meal-plans",
            {"planDate": today, "regenerate": True}, token=token)
        check("regenerating is still one request",
              status in (200, 201), f"got {status}")
        partial = partial or {}
        kept = [i for m in partial.get("meals", [])
                if m["mealType"] == "breakfast" for i in m["items"]]
        check(
            "the eaten breakfast is STILL THERE - a regenerate must not "
            "delete a serving the diary already records",
            all(i["status"] == "eaten" for i in kept) and kept != [],
            f"{[i['status'] for i in kept]}",
        )
        equals("and it is the same plan row, not a replacement",
               partial.get("id"), base_plan.get("id"))
        rows = sql("SELECT COUNT(*) FROM meal_plans WHERE user_id = %s",
                   (uid,))[0][0]
        equals("so there is still exactly one plan for the day", rows, 1)

        # The decisive figure. The day is measured around what was eaten, so
        # the new plan is NOT another whole day.
        new_day = energy_of(partial)
        check(
            "the day did not become a second whole day",
            new_day < whole_day * 1.5,
            f"{new_day:.0f} kcal against a {target_kcal:.0f} kcal target, "
            f"{eaten_kcal:.0f} of it already eaten",
        )
        check(
            "and it is still measured against the day's own target, within "
            "the ±10 % the proposal commits to",
            abs(partial.get("calorieDeviationPct") or 999) <= 10,
            f"got {partial.get('calorieDeviationPct')} %",
        )
        check(
            "the dishes already eaten are not suggested again",
            len({i["food"]["id"] for m in partial.get("meals", [])
                 for i in m["items"] if i["status"] != "replaced"}) ==
            len([i for m in partial.get("meals", [])
                 for i in m["items"] if i["status"] != "replaced"]),
        )

        # -- And when the whole day has been eaten --
        for meal in ("lunch", "dinner", "snack"):
            items = [i for m in partial.get("meals", [])
                     if m["mealType"] == meal for i in m["items"]
                     if i["status"] == "suggested"]
            for item in items[:1]:
                call("PATCH", f"/meal-plan-items/{item['id']}/status",
                     {"status": "eaten"}, token=token)

        status, refused = call(
            "POST", "/meal-plans",
            {"planDate": today, "regenerate": True}, token=token)
        equals(
            "with something eaten in all four meals there is nothing left to "
            "plan, so it is refused rather than answered with another day",
            (status, error_code(refused)), (409, "VALIDATION_FAILED"))
        message = ((refused or {}).get("error") or {}).get("message") or ""
        check("and the refusal says why", "đã ăn" in message, f"{message!r}")
        details = ((refused or {}).get("error") or {}).get("details") or []
        check("naming the field, and what to do instead",
              any(d.get("field") == "regenerate" for d in details),
              f"{details}")

        # Put the day back for the sections that follow.
        sql("DELETE FROM food_diary WHERE user_id = %s", (uid,))
        sql("DELETE FROM meal_plans WHERE user_id = %s", (uid,))
        status, restored = call(
            "POST", "/meal-plans", {"planDate": today}, token=token)
        equals("a clean day for the rest of the suite", status, 201)
        plan_id = (restored or {}).get("id")



        # -- A blocked dish must not come back in a new plan --
        #
        # The decisive check for the whole feature, and the only one that
        # crosses all three layers: the app's PUT writes a row, the ML
        # service's F1 filter subtracts it before anything is scored, and the
        # plan the backend stores is built from what is left. Every ML signal
        # is soft - a label of 0.0 lowers a score and leaves the dish
        # eligible - so this is the one place a rejected dish could reappear.
        print("\nPUT /foods/{id}/mark - and the next plan")
        fresh_items = [i for m in (fresh or {}).get("meals") or []
                       for i in m["items"]]
        # A dish whose role has alternatives, so the refusal is not what is
        # being measured here.
        chosen = next(
            (i["food"]["id"] for i in fresh_items
             if i["food"]["dishRole"] in ("main", "soup")),
            fresh_items[0]["food"]["id"] if fresh_items else None)
        if chosen is not None:
            status, body = call(
                "PUT", f"/foods/{chosen}/mark", {"kind": "blocked"},
                token=token)
            equals("blocking a dish the plan just used returns 200",
                   (status, (body or {}).get("kind")), (200, "blocked"))

            status, after = call(
                "POST", "/meal-plans",
                {"planDate": today, "regenerate": True}, token=token)
            equals("regenerating returns 201", status, 201)
            after_ids = {i["food"]["id"]
                         for m in (after or {}).get("meals") or []
                         for i in m["items"]}
            check(
                "the blocked dish is NOT in the new plan - F1 runs before "
                "scoring, so no score can bring it back",
                chosen not in after_ids,
                f"{len(after_ids)} dishes, blocked dish present",
            )
            check("and the plan is still a whole day",
                  len((after or {}).get("meals") or []) == 4
                  and len(after_ids) > 0)
            check(
                "still inside the 10 % commitment, so losing a dish cost "
                "accuracy and not the guarantee",
                abs((after or {}).get("calorieDeviationPct") or 999) <= 10,
                f"got {(after or {}).get('calorieDeviationPct')} %",
            )

            status, body = call(
                "PUT", f"/foods/{chosen}/mark", {"kind": None}, token=token)
            equals("unblocking returns 200", status, 200)
            rows = sql(
                "SELECT COUNT(*) FROM user_food_marks WHERE user_id = %s",
                (uid,))[0][0]
            equals("and leaves no mark behind", rows, 0)

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
                 f"/meal-plans?date={date.today().isoformat()}",
                 "/foods", "/feedbacks",
                 f"/food-diary?from={date.today().isoformat()}"
                 f"&to={date.today().isoformat()}",
                 f"/food-diary/summary?date={date.today().isoformat()}"):
        status, body = call("GET", path, token=access)
        equals(f"403 ACCOUNT_DISABLED at GET {path}",
               (status, error_code(body)), (403, "ACCOUNT_DISABLED"))

    status, body = call("PUT", "/profile/conditions", {"conditions": []},
                        token=access)
    equals("403 for PUT too, not only GET", (status, error_code(body)),
           (403, "ACCOUNT_DISABLED"))

    # The GET loop above cannot reach the two endpoints added last, because
    # both are POSTs. The plan id below does not exist, deliberately: a 403
    # for it proves the filter answers BEFORE the action looks anything up,
    # which is what makes it protection rather than a check the endpoint
    # happens to do first.
    missing_plan = "00000000-0000-4000-8000-000000000000"
    for method, path, payload in (
        ("POST", "/onboarding/candidates/count", {"conditions": []}),
        ("POST", f"/meal-plans/{missing_plan}/meals/snack", None),
        ("POST", "/meal-plans", {"planDate": date.today().isoformat()}),
        ("POST", "/food-diary",
         {"foodId": missing_plan, "ateOn": date.today().isoformat(),
          "mealType": "snack"}),
        ("PUT", f"/food-diary/{missing_plan}", {"servingSizeG": 100}),
        ("DELETE", f"/food-diary/{missing_plan}", None),
        ("POST", "/feedbacks", {"foodId": missing_plan, "rating": 5}),
        ("PUT", "/auth/me", {"displayName": "Blocked"}),
        ("PUT", f"/foods/{missing_plan}/mark", {"kind": "loved"}),
    ):
        status, body = call(method, path, payload, token=access)
        equals(f"403 ACCOUNT_DISABLED at {method} {path}",
               (status, error_code(body)), (403, "ACCOUNT_DISABLED"))

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
    print(f"{_checks}/{_checks} checks passed — 33 endpoints behave per the "
          f"specification against the real database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
