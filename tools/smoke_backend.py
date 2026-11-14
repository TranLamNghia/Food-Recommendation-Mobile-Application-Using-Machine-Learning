#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the 9 endpoints of phases 1 and 2, against the real
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
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _env  # noqa: E402

BASE = "http://localhost:5000/api/v1"

_failures: list[str] = []
_checks = 0


def call(method: str, path: str, body=None, token: str | None = None):
    """Call the API; returns `(HTTP status, JSON-decoded body or None)`."""
    url = BASE + path
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
    args = parser.parse_args(argv)

    email = f"smoke-{uuid.uuid4().hex[:12]}@example.test"
    password = "MatKhau123"
    print(f"End-to-end test against {BASE}")
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
    # until the accessToken expired. `TaiKhoanConHoatDongFilter` now blocks at
    # the filter layer, so a new endpoint is protected by default.
    print("\n§4  a disabled account — blocked at every authenticated endpoint")
    status, body = call("POST", "/auth/login",
                        {"email": email, "password": password})
    access = body and body.get("accessToken")
    refresh_token = body and body.get("refreshToken")
    check("got a token before disabling", bool(access))

    sql("UPDATE users SET is_active = 0 WHERE email = %s", (email,))

    for path in ("/auth/me", "/profile", "/profile/nutrition-targets",
                 "/profile/conditions"):
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
    print(f"{_checks}/{_checks} checks passed — 9 endpoints behave per the "
          f"specification against the real database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
