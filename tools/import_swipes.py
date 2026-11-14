#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import one filled-in taste survey form into the database.

The second half of item 10. `tools/make_survey_deck.py` produces the form;
this file reads a filled-in one and writes into `users`, `health_profiles`,
`user_conditions` and `interactions`, then computes
`user_preference_profiles` with Rocchio.

## Validate everything, then write

Every check runs **before** the first `INSERT`, and the whole import is **one
transaction**. A half-imported form — a user with no swipes, or swipes with no
preference profile — is distinctly worse than an un-imported one: it still
passes through every downstream script and quietly contributes a defective
user to the training set.

## Two placeholder values, and why they are safe

`users.password_hash` is `NOT NULL`, but a paper-form respondent has no
account to log in with. It is set to `!khong-tag-dang-nhap`: the leading `!`
makes the string **not** a valid hash for any algorithm, so every login
comparison fails. This is Django's convention for an "unusable password", and
it is distinctly safer than a real hash of some default password — which would
be an open door of an account.

`users.email` is `UNIQUE NOT NULL`, but not everyone gives an email. When it is
blank, `khaosat-<n>@local.invalid` is generated: the `.invalid` TLD is reserved
by RFC 2606 and **never** resolves, so there is no risk of mailing a real
address belonging to somebody else.

Note on language: the form's field keys, the `lua_chon` values and the two
placeholder literals stay as they are. The field keys are the contract with
the forms already collected in `data/survey/da_dien/`, and the two literals
are values already stored in `users` rows.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import use_utf8, connect  # noqa: E402
from ml.f1_filter import conditions_by_name, exclusion_reasons  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.rocchio import alpha, build_profile, stage  # noqa: E402

from tools.make_survey_deck import CHOICES  # noqa: E402

#: The unusable hash — see the notes at the top of this file. The literal is a
#: value already stored in 50 `users` rows, so it stays as it is.
UNUSABLE_PASSWORD_HASH = "!khong-tag-dang-nhap"

#: The generated-email pattern, and the pattern used to count them. The two
#: must agree, or the counter would not see the rows it is counting.
EMAIL_TEMPLATE = "khaosat-{}@local.invalid"
EMAIL_LIKE = "khaosat-%@local.invalid"

#: The severity written into `user_conditions.severity`, AND the severity used
#: when running the F1 filter at import time. One constant for both, on
#: purpose: the paper form does not ask for a severity, so if the two places
#: used different values, F1 at import would exclude a different set of foods
#: from F1 at serving time, for the same person.
#:
#: That difference is NOT theoretical: for `Gút`, F1 excludes 0 foods at `mild`
#: but 9 at `moderate`, because `condition_rules.severity_min` gates each rule.
FORM_SEVERITY = "moderate"

#: The form's own field keys — Vietnamese, see the note on language above.
REQUIRED_FIELDS = (
    "gioi_tinh",
    "ngay_sinh",
    "chieu_cao_cm",
    "can_nang_kg",
    "muc_van_dong",
    "muc_tieu",
)

ALLOWED_VALUES = {
    "gioi_tinh": ("male", "female", "other"),
    "muc_van_dong": ("sedentary", "light", "moderate", "active", "very_active"),
    "muc_tieu": ("lose_weight", "maintain", "gain_weight", "healthy_eating"),
}


class FormError(Exception):
    """The form is invalid. The message must say which line to fix."""


def read_form(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Split the info block (`# key: value`) from the table."""
    if not path.exists():
        raise FormError(f"file {path} not found")

    info: dict[str, str] = {}
    table_lines: list[str] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            # Drop the trailing comment after a second `#` on the same line.
            if ":" in body:
                key, _, value = body.partition(":")
                value = value.split("#")[0].strip()
                key = key.strip()
                if key and " " not in key:
                    info[key] = value
            continue
        table_lines.append(raw)

    if not table_lines:
        raise FormError("the form has no data row")

    reader = csv.DictReader(table_lines)
    rows = [d for d in reader]
    missing_columns = (
        {"ma_mon", "ten_mon", "lua_chon"} - set(reader.fieldnames or ())
    )
    if missing_columns:
        raise FormError(
            f"the form is missing columns: {', '.join(sorted(missing_columns))}"
        )
    return info, rows


def validate_info(info: dict[str, str]) -> dict[str, Any]:
    """Validate and convert the info block. Raises `FormError` saying what to fix."""
    missing = [k for k in REQUIRED_FIELDS if not info.get(k)]
    if missing:
        raise FormError(
            "the info block still has blanks: "
            + ", ".join(missing)
            + "\nFill in the `# <key>: <value>` lines at the top of the form."
        )

    for key, allowed in ALLOWED_VALUES.items():
        if info[key] not in allowed:
            raise FormError(
                f"`{key}` = {info[key]!r} is not valid; "
                f"it must be one of: {', '.join(allowed)}"
            )

    try:
        birth = date.fromisoformat(info["ngay_sinh"])
    except ValueError as e:
        raise FormError(f"`ngay_sinh` must be YYYY-MM-DD: {e}") from e
    if not date(1900, 1, 1) <= birth <= date.today():
        raise FormError(
            f"`ngay_sinh` = {birth} is outside the plausible range"
        )

    try:
        height = float(info["chieu_cao_cm"])
        weight = float(info["can_nang_kg"])
    except ValueError as e:
        raise FormError(f"height and weight must be numbers: {e}") from e
    # Exactly the two CHECK constraints on `health_profiles`, validated here so
    # the error is readable rather than MySQL's cryptic error 3819.
    if not 50 <= height <= 250:
        raise FormError(
            f"`chieu_cao_cm` = {height:g} must be within 50-250"
        )
    if not 20 <= weight <= 300:
        raise FormError(f"`can_nang_kg` = {weight:g} must be within 20-300")

    survey_raw = info.get("ngay_khao_sat", "")
    try:
        survey_date = (
            date.fromisoformat(survey_raw) if survey_raw else date.today()
        )
    except ValueError as e:
        raise FormError(f"`ngay_khao_sat` must be YYYY-MM-DD: {e}") from e

    condition_names = [
        c.strip() for c in info.get("benh_ly", "").split(";") if c.strip()
    ]

    return {
        "ho_ten": info.get("ho_ten", "").strip(),
        "email": info.get("email", "").strip(),
        "gioi_tinh": info["gioi_tinh"],
        "ngay_sinh": birth,
        "chieu_cao_cm": height,
        "can_nang_kg": weight,
        "muc_van_dong": info["muc_van_dong"],
        "muc_tieu": info["muc_tieu"],
        "condition_names": condition_names,
        "ngay_khao_sat": survey_date,
    }


def validate_swipes(
    rows: list[dict[str, str]], foods_by_id: dict[str, Any]
) -> list[tuple[str, str]]:
    """Validate the table. Returns `[(food_id, action)]` in form order."""
    result: list[tuple[str, str]] = []
    errors: list[str] = []
    seen: set[str] = set()

    for i, row in enumerate(rows, start=1):
        row_no = (row.get("stt") or str(i)).strip()
        food_id = (row.get("ma_mon") or "").strip()
        choice = (row.get("lua_chon") or "").strip().lower()

        if not choice:
            continue  # left blank: the respondent did not answer, not an error
        if choice not in CHOICES:
            errors.append(
                f"  row {row_no}: `lua_chon` = {choice!r} is not valid; "
                f"it must be {' | '.join(CHOICES)}"
            )
            continue
        if food_id not in foods_by_id:
            errors.append(
                f"  row {row_no}: `ma_mon` = {food_id!r} is not in the food "
                f"catalogue"
            )
            continue
        if food_id in seen:
            errors.append(
                f"  row {row_no}: food {foods_by_id[food_id].name!r} appears "
                f"twice"
            )
            continue

        seen.add(food_id)
        result.append((food_id, CHOICES[choice]))

    if errors:
        raise FormError("the form has errors:\n" + "\n".join(errors))
    if not result:
        raise FormError("no choice has been filled in the `lua_chon` column")
    return result


def resolve_conditions(cn, names: list[str]) -> list[int]:
    """Resolve `condition_names` to `conditions.id`. Raises on an unknown name.

    Runs in the VALIDATE phase, not the write phase. This lookup used to live
    in `write()`, so a form saying `benh_ly: tieu_duong` passed the dry run and
    only broke at `--apply`. For one form that is annoying; for twenty-five
    forms handed out with the same wrong template it is twenty-five failures at
    once, after the respondents have finished filling them in and can no longer
    correct them.
    """
    if not names:
        return []
    with cn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(names))
        cur.execute(
            f"SELECT id, name_vi FROM conditions "
            f"WHERE name_vi IN ({placeholders})",
            tuple(names),
        )
        found = {d["name_vi"]: int(d["id"]) for d in cur.fetchall()}
        missing = [n for n in names if n not in found]
        if missing:
            cur.execute("SELECT name_vi FROM conditions ORDER BY id")
            available = ", ".join(d["name_vi"] for d in cur.fetchall())
            raise FormError(
                "`benh_ly` holds names that do not match `conditions`: "
                + ", ".join(repr(x) for x in missing)
                + f"\nThey must be the exact Vietnamese names with diacritics. "
                f"Available: {available}"
            )
    return [found[n] for n in names]


def filter_by_f1(
    cn,
    condition_names: list[str],
    swipes: list[tuple[str, str]],
    foods_by_id: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str, list[str]]]]:
    """Drop swipes on foods the F1 filter would not let this person eat.

    ## Why it is needed, and why it happens HERE

    The paper form uses **one fixed deck for everyone**, because printing a
    per-person form is impossible — and because only a fixed deck gives enough
    observations per food to compute popularity (25 people x 40 foods = ~25
    swipes/food; personalised, 1000 swipes spread over 318 foods leaves ~3
    swipes/food, and a Wilson lower bound on 3 observations is useless).

    But a fixed deck forces respondents to rate foods they **cannot eat**.
    Measured on the form's actual 40-food deck:

        Seafood allergy         excludes  9/40  (22%)
        Vegan                   excludes 22/40  (55%)
        Gout + hypertension     excludes  9/40  (22%)

    A vegan will mark `khong_thich` for 22 foods, and the model reads that as
    "dislikes pho, dislikes fish" rather than "is vegan" — 55% of their signal
    is **a constraint disguised as taste**. Worse, it poisons GLOBAL popularity
    too: five vegans out of twenty-five give beef pho five dislikes that have
    nothing to do with pho being bad.

    In the app this does not happen — `GET /onboarding/survey` runs F1 **before
    asking** (spec §7.4.1). A paper form cannot do that, so it runs F1 **after
    asking, before writing**. A different moment, but what reaches the database
    is the same.

    Dropped outright rather than recorded as `unknown`: F1 would never have
    recommended those foods to this person anyway, so their taste on them is
    used nowhere — while `unknown` has its own meaning, "never eaten", not
    "not allowed to eat".

    Returns `(kept_swipes, [(food_id, action, [reasons...])])`.
    """
    if not condition_names:
        return swipes, []

    # The same `severity` as the row that will be written into
    # `user_conditions` — see `FORM_SEVERITY`.
    conditions = conditions_by_name(
        cn, condition_names, severity=FORM_SEVERITY
    )

    # `public_only=True`: a paper-form respondent has no foods of their own,
    # and the whole survey deck is shared foods.
    reasons_by_food = exclusion_reasons(
        cn, conditions=conditions, public_only=True
    )

    kept: list[tuple[str, str]] = []
    dropped: list[tuple[str, str, list[str]]] = []
    for food_id, action in swipes:
        reasons = reasons_by_food.get(food_id)
        if reasons:
            dropped.append(
                (food_id, action, [_short_reason(r) for r in reasons])
            )
        else:
            kept.append((food_id, action))
    return kept, dropped


def _short_reason(reason: Any) -> str:
    """One readable line out of an `ExclusionReason`.

    `ExclusionReason` is a thirteen-field dataclass; its `str()` dumps all of
    them and makes the report unreadable. `note` is the sentence already
    written for a human reader.
    """
    condition = getattr(reason, "condition", None) or "?"
    note = getattr(reason, "note", None)
    if note:
        return f"{condition}: {note}"
    rule_type = getattr(reason, "rule_type", None) or "?"
    tag = (
        getattr(reason, "tag", None)
        or getattr(reason, "nutrient", None)
        or ""
    )
    return f"{condition}: {rule_type} {tag}".strip()


# -- Writing ----------------------------------------------------------


def _next_email(cn, given: str) -> str:
    if given:
        return given
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) n FROM users WHERE email LIKE %s", (EMAIL_LIKE,)
        )
        n = int(cur.fetchone()["n"])
    return EMAIL_TEMPLATE.format(n + 1)


def write(
    cn,
    info: dict[str, Any],
    swipes: list[tuple[str, str]],
    space: FeatureSpace,
    foods_by_id: dict[str, Any],
) -> dict[str, Any]:
    """Write the whole form in one transaction. Returns details for reporting."""
    email = _next_email(cn, info["email"])
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    with cn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone() is not None:
            raise FormError(
                f"a user with email {email!r} already exists. This form may "
                f"already have been imported; change the email or delete the "
                f"old user first."
            )

        # The conditions were already resolved by `resolve_conditions` in the
        # validate phase; resolved again here so `write()` does not depend on
        # the caller having validated.
        condition_ids: list[int] = resolve_conditions(
            cn, info["condition_names"]
        )

        cur.execute(
            "INSERT INTO users (id, email, password_hash, display_name, "
            "onboarding_completed_at) VALUES (%s, %s, %s, %s, %s)",
            (
                user_id,
                email,
                UNUSABLE_PASSWORD_HASH,
                # The display name is shown to users, so the fallback stays
                # Vietnamese.
                info["ho_ten"] or "Người khảo sát",
                datetime.combine(
                    info["ngay_khao_sat"], datetime.min.time()
                ),
            ),
        )
        cur.execute(
            "INSERT INTO health_profiles (id, user_id, gender, date_of_birth, "
            "height_cm, weight_kg, activity_level, goal) "
            "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                info["gioi_tinh"],
                info["ngay_sinh"],
                info["chieu_cao_cm"],
                info["can_nang_kg"],
                info["muc_van_dong"],
                info["muc_tieu"],
            ),
        )
        for condition_id in condition_ids:
            cur.execute(
                "INSERT INTO user_conditions (id, user_id, condition_id, "
                "severity) VALUES (UUID(), %s, %s, %s)",
                (user_id, condition_id, FORM_SEVERITY),
            )

        # Spread the timestamps one second apart within the survey day. The
        # order follows the form's order, because `profile_snapshot` replays
        # chronologically when the training set is built.
        base_time = datetime.combine(
            info["ngay_khao_sat"], datetime.min.time()
        ).replace(hour=9)
        for i, (food_id, action) in enumerate(swipes):
            cur.execute(
                "INSERT INTO interactions (id, user_id, food_id, action, "
                "session_id, interacted_at) "
                "VALUES (UUID(), %s, %s, %s, %s, %s)",
                (
                    user_id, food_id, action, session_id,
                    base_time + timedelta(seconds=i),
                ),
            )

        profile = build_profile(
            space, [(foods_by_id[f], a) for f, a in swipes]
        )
        cur.execute(
            "INSERT INTO user_preference_profiles (user_id, feature_version, "
            "weights, sum_abs_weight, n_signals, stage, alpha) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                FEATURE_VERSION,
                json.dumps(list(profile.weights)),
                profile.sum_abs_weight,
                profile.n_signals,
                stage(profile.n_signals),
                round(alpha(profile.n_signals), 3),
            ),
        )

    cn.commit()
    return {
        "user_id": user_id,
        "email": email,
        "n_signals": profile.n_signals,
        "stage": stage(profile.n_signals),
        "profile": profile,
    }


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--form", required=True, type=Path,
                        help="the filled-in form file")
    parser.add_argument("--db", default=None)
    parser.add_argument("--apply", action="store_true",
                        help="write to the database")
    args = parser.parse_args()

    cn = connect(args.db)
    try:
        foods, _ = load_foods(cn)
        space = FeatureSpace.from_foods(foods)
        foods_by_id = {f.id: f for f in foods}

        try:
            raw_info, rows = read_form(args.form)
            info = validate_info(raw_info)
            swipes = validate_swipes(rows, foods_by_id)
            resolve_conditions(cn, info["condition_names"])
        except FormError as e:
            print(f"The form is not usable.\n{e}", file=sys.stderr)
            return 1

        # The F1 filter runs BEFORE the preference vector is built, not merely
        # before `interactions` is written. Filtering after building leaves
        # the vector carrying the whole constraint-disguised-as-taste part, and
        # `n_signals` still counts those swipes so the stage is wrong too.
        raw_swipes = swipes
        swipes, dropped = filter_by_f1(
            cn, info["condition_names"], swipes, foods_by_id
        )
        if not swipes:
            print(
                "The form is not usable.\nThe F1 filter excluded all "
                f"{len(raw_swipes)} filled-in swipes — every food on the form "
                "violates one of this person's hard constraints. This case "
                "needs a different deck.",
                file=sys.stderr,
            )
            return 1

        counts: dict[str, int] = {}
        for _, action in swipes:
            counts[action] = counts.get(action, 0) + 1
        profile = build_profile(
            space, [(foods_by_id[f], a) for f, a in swipes]
        )

        print(f"Form: {args.form}")
        print(
            f"  {info['ho_ten'] or '(no name given)'} · {info['gioi_tinh']} · "
            f"born {info['ngay_sinh']} · {info['chieu_cao_cm']:g} cm / "
            f"{info['can_nang_kg']:g} kg"
        )
        print(
            f"  goal {info['muc_tieu']} · activity {info['muc_van_dong']}"
        )
        print(
            f"  conditions: "
            f"{', '.join(info['condition_names']) or '(none)'}"
        )

        if dropped:
            print(
                f"  The F1 filter excluded {len(dropped)}/{len(raw_swipes)} "
                f"swipes ({len(dropped) / len(raw_swipes) * 100:.0f}%) — "
                f"foods this person may not eat:"
            )
            # Grouped by reason, not listed food by food: a vegan loses 22
            # foods to EXACTLY ONE rule, and printing 22 identical lines
            # hides that.
            by_reason: dict[str, list[str]] = {}
            for food_id, action, reasons in dropped:
                name = getattr(foods_by_id[food_id], "name", food_id)
                by_reason.setdefault(reasons[0], []).append(
                    f"{name}[{action}]"
                )
            for reason, food_names in sorted(by_reason.items()):
                print(f"      {reason} -> {len(food_names)} foods")
                head = ", ".join(food_names[:3])
                more = (
                    f", … and {len(food_names) - 3} more"
                    if len(food_names) > 3 else ""
                )
                print(f"        {head}{more}")
            print(
                "    These swipes are NOT written and do NOT enter the "
                "preference vector: they are a constraint, not a taste."
            )

        print(
            f"  {len(swipes)} usable swipes: "
            + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
        print(
            f"  -> n_signals = {profile.n_signals} "
            f"(`unknown` swipes are not counted) · "
            f"stage {stage(profile.n_signals)}"
        )

        # The strongest dimensions, so whoever imports can see for themselves
        # whether the vector looks sensible.
        strongest = sorted(
            zip(profile.weights, space.labels), key=lambda pair: -abs(pair[0])
        )[:4]
        print(
            "  strongest dimensions: "
            + ", ".join(f"{label} {w:+.3f}" for w, label in strongest)
        )

        if not args.apply:
            print(
                "\nDry run — nothing written. Add --apply to import into the "
                "database."
            )
            return 0

        try:
            result = write(cn, info, swipes, space, foods_by_id)
        except FormError as e:
            cn.rollback()
            print(f"Could not import.\n{e}", file=sys.stderr)
            return 1

        print(
            f"\nImported: user_id = {result['user_id']}, "
            f"email = {result['email']}"
        )
        print(
            "Next steps, once enough people have been imported:\n"
            "    python tools/update_popularity.py --apply\n"
            "    python -m ml.build_dataset --version d1 --apply\n"
            "    python -m ml.train --dataset d1 --apply\n"
            "    python -m ml.evaluate --dataset d1 --model <version> --apply"
        )
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
