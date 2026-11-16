#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load the simulated set into the database: 50 people, 2250 swipes, Rocchio
profiles.

The blocker this file opens. `ml/build_dataset.py` returned 0 samples because
the database had no users, so `train.py`, `evaluate.py` and the whole Chapter 3
comparison table could not run. This file is the missing step between the two
CSV files in `data/survey/mo_phong/` and the tables the pipeline reads.

How it differs from `import_swipes.py`: that one imports **one paper form from
one real person**, with a `# key: value` block already stating `ngay_sinh`,
`chieu_cao_cm`, `muc_van_dong` and `muc_tieu`. This one imports **50 machine
profiles** from `ObesityDataSet`, and that source file **has none** of those
four fields — it has a decimal `Age`, a `Height` in metres, a continuous `FAF`
of 0-3 and a `NObeyesdad` of 7 labels. The four conversions below are the whole
of what has to be decided, so each one states its basis and states what it
**cannot** do.

## The four conversions

**1. Decimal `Age` -> `date_of_birth`.** 31 of 50 profiles have a non-integer
age (21.47 · 36.84…) because 75% of `ObesityDataSet` is SMOTE-interpolated
rows. The schema stores a date of birth, not an age — correctly, because age is
a derived quantity that changes by the day. The conversion: round the age, then
place the date of birth 1-300 days **before** this year's birthday, offset by
the person's index so the 50 profiles do not share one birthday. Going back at
least one day is mandatory: landing exactly on the birthday makes `age()`
return `n` or `n − 1` depending on the time of day it runs.

The conversion is self-checked: `age(date_of_birth, load_date) == round(Age)`
is asserted for all 50 rows. Without that self-check, an off-by-one here would
go straight into the BMR of all 50 people and nothing would report it.

**2. `Height` in metres -> `height_cm`.** Multiply by 100.
`health_profiles.bmi` is a `VIRTUAL` column computed from `height_cm`, so after
this multiplication the database produces the correct BMI — roughly 16.2-44.1.
The `BMI` column in `f1_training_dataset_50_users.csv` is wrong by a factor of
10,000 because it applies the cm formula to a value already in metres; this
file **does not read that column**.

**3. `FAF` 0-3 -> a 5-level `activity_level`.** `FAF` is originally a
four-choice question (0 = no exercise · 1 = 1-2 days · 2 = 2-4 days · 3 = 4-5
days per week), and the decimal values are purely an artefact of SMOTE. So the
conversion is to **round to the nearest original answer**, then map to the
level with the same frequency in `SYSTEM_ARCHITECTURE.md` §3.1.

**`very_active` never appears, and that is a property of the source
questionnaire rather than a defect.** `FAF`'s top level is "4-5 days per week",
while `very_active` means "heavy labour or two sessions a day" — the source
scale **does not reach** that level. Assigning `very_active` to `FAF = 3` would
multiply the calorie limit by 1.900 instead of 1.725, that is, add ~10% calories
for a group the data says nothing about.

**4. `NObeyesdad` 7 labels -> a 4-level `goal`.** `Insufficient_Weight` ->
`gain_weight`; `Normal_Weight` -> `maintain`; the two `Overweight` levels and
the three `Obesity` levels -> `lose_weight`.

**`healthy_eating` never appears, and that too is a property of the source.** It
is a **self-declared** user choice ("I am not focused on weight"), and cannot be
inferred from a weight classification label. Inferring it would mean this file
is inventing an intention nobody stated.

## What this file does NOT write, and why

The latent taste vector `t_u` **does not go into the database.** The schema has
no column for it, and adding a column only simulated data uses would make the
schema carry something that does not belong to the product. It stays in
`khau_vi_that.json`, and `tools/check_simulation.py` is what reads it.

## Load it all, then commit

All 50 people are in **one transaction**. A half-finished load — 23 people with
swipes, 27 without — is distinctly worse than no load at all: `build_dataset`
runs straight through it and quietly builds a defective training set.

Run
───
    python tools/import_simulation.py              # preview, write nothing
    python tools/import_simulation.py --apply
    python tools/import_simulation.py --delete     # remove the previous load

Note on language: the email pattern, the UUID namespace URL and the display
name are values already stored in `users` rows, so their literals stay as they
are — changing the namespace URL would change every `user_id`, and with it the
fold assignment in Chapter 3.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import use_utf8, connect  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.rocchio import alpha, build_profile, stage  # noqa: E402

from tools.gen_step1_cases import (  # noqa: E402
    age,
    bmr,
    calorie_limit,
    round_half_up,
    tdee,
)

# Reuse `import_swipes.py`'s set wholesale rather than writing a second one:
# the condition lookup, the severity written into `user_conditions`, the F1
# filtering at import time and the unusable password hash must all be
# **identical** between the two import paths. Two implementations of one filter
# are two places to drift, and drift here means F1 at import excludes a
# different set of foods from F1 at serving time.
from tools.import_swipes import (  # noqa: E402
    UNUSABLE_PASSWORD_HASH,
    FORM_SEVERITY,
    FormError,
    _short_reason,
    filter_by_f1,
    resolve_conditions,
)
from tools.make_survey_deck import CHOICES  # noqa: E402

BEHAVIOUR_CSV = ROOT / "data" / "survey" / "mo_phong" / "hanh_vi.csv"
GROUND_TRUTH = ROOT / "data" / "survey" / "mo_phong" / "khau_vi_that.json"
PROFILES_CSV = (
    ROOT / "data" / "survey" / "f1_training_dataset_50_users.csv"
)

#: The `.invalid` TLD is reserved by RFC 2606 and never resolves. The prefix
#: differs from `import_swipes.py`'s `khaosat-` on purpose: the two loads must
#: be distinguishable, because `--delete` below removes rows matching exactly
#: this pattern and a shared prefix would delete the real people's forms too.
EMAIL_TEMPLATE = "mophong-{}@local.invalid"
EMAIL_LIKE = "mophong-%@local.invalid"

#: Rounded `FAF` -> `activity_level`. See conversion 3 at the top of the file.
FAF_TO_ACTIVITY = {
    0: "sedentary",   # no exercise
    1: "light",       # 1-2 days per week
    2: "moderate",    # 2-4 days
    3: "active",      # 4-5 days
}

#: `NObeyesdad` -> `goal`. See conversion 4 at the top of the file.
LABEL_TO_GOAL = {
    "Insufficient_Weight": "gain_weight",
    "Normal_Weight": "maintain",
    "Overweight_Level_I": "lose_weight",
    "Overweight_Level_II": "lose_weight",
    "Obesity_Type_I": "lose_weight",
    "Obesity_Type_II": "lose_weight",
    "Obesity_Type_III": "lose_weight",
}

GENDER = {"Male": "male", "Female": "female"}

#: How far the date of birth may be spread around the birthday; see conversion 1.
BIRTH_DATE_SPREAD = 300

#: The namespace for generating `users.id` and `interactions.session_id` as
#: UUID v5.
#:
#: **It must be UUID v5, never `uuid4()`,** and this is not a matter of taste.
#: `ml/build_dataset.py` assigns folds with
#: `sorted(people, key=sha256(f"{seed}:{user_id}"))` and draws `random_neg`
#: samples with `random.Random(f"{seed}:{user_id}")`. Both are keyed on
#: `user_id`, so with `uuid4()` **every reload produces a different fold split
#: and a different negative sample** — meaning every number in Chapter 3's
#: comparison table changes after each run, with nobody having changed
#: anything.
#:
#: UUID v5 is a SHA-1 hash of (namespace, name), so `U001` always yields
#: exactly one `user_id`. The whole chain `--delete` -> `--apply` ->
#: `build_dataset` -> `train` -> `evaluate` is therefore reproducible digit for
#: digit.
#:
#: `uuid.NAMESPACE_URL` with a `.invalid` URL rather than a hand-picked UUID:
#: that TLD is reserved by RFC 2606, so it collides with nobody's namespace.
#: The URL string is load-bearing — see the note on language above.
UUID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://mophong.local.invalid/"
)


class LoadError(Exception):
    """The input is not usable. The message must say exactly what to fix."""


# -- reading and converting ------------------------------------------------


def years_back(anchor: date, years: int) -> date:
    """`anchor` minus `years`. 29 Feb falls back to 28 Feb, as the target year
    may not be a leap year."""
    try:
        return anchor.replace(year=anchor.year - years)
    except ValueError:
        return anchor.replace(year=anchor.year - years, day=28)


def birth_date_for_age(years: int, index: int, today: date) -> date:
    """A date of birth that yields exactly `years` of age on `today`."""
    anchor = years_back(today, years)
    birth = anchor - timedelta(days=1 + (index * 7) % BIRTH_DATE_SPREAD)
    if age(birth, today) != years:
        raise LoadError(
            f"date-of-birth conversion is wrong: {birth} yields "
            f"{age(birth, today)} years, {years} needed. See "
            f"`birth_date_for_age`."
        )
    return birth


def convert_profile(
    row: dict[str, str], index: int, today: date
) -> dict[str, Any]:
    """One `ObesityDataSet` row -> the fields of `health_profiles`."""
    key = row["user_id"]

    if row["Gender"] not in GENDER:
        raise LoadError(
            f"{key}: `Gender` = {row['Gender']!r}, only Male/Female accepted"
        )
    if row["NObeyesdad"] not in LABEL_TO_GOAL:
        raise LoadError(
            f"{key}: `NObeyesdad` = {row['NObeyesdad']!r} is not in the "
            f"conversion table. The seven known labels: "
            f"{', '.join(sorted(LABEL_TO_GOAL))}"
        )

    try:
        raw_age = float(row["Age"])
        height_m = float(row["Height"])
        weight = float(row["Weight"])
        faf = float(row["FAF"])
    except ValueError as e:
        raise LoadError(f"{key}: unreadable number — {e}") from e

    faf_rounded = int(round(faf))
    if faf_rounded not in FAF_TO_ACTIVITY:
        raise LoadError(
            f"{key}: `FAF` = {faf} rounds to {faf_rounded}, outside 0-3"
        )

    age_years = int(round(raw_age))
    height_cm = round(height_m * 100, 2)
    # DECIMAL(5,2) holds at most 999.99. A height in metres with the x100
    # forgotten would pass every other check and yield a BMI 10,000 times too
    # large — exactly the defect present in the source file's `BMI` column.
    if not 100.0 <= height_cm <= 250.0:
        raise LoadError(
            f"{key}: height converts to {height_cm} cm, outside 100-250. "
            f"`Height` in the source file must be in METRES."
        )
    if not 20.0 <= weight <= 300.0:
        raise LoadError(f"{key}: weight {weight} kg is outside 20-300")
    if not 1 <= age_years <= 120:
        raise LoadError(
            f"{key}: age converts to {age_years}, outside 1-120"
        )

    gender = GENDER[row["Gender"]]
    activity = FAF_TO_ACTIVITY[faf_rounded]
    goal = LABEL_TO_GOAL[row["NObeyesdad"]]
    birth = birth_date_for_age(age_years, index, today)

    # Step 1 comes from `gen_step1_cases` — the Python reference that
    # `check_be_parity.py` has already compared against the C# and the Dart.
    # Rewriting it here would be a fourth copy of one formula, that is, a
    # fourth place to drift.
    d_weight = Decimal(str(weight))
    d_height = Decimal(str(height_cm))
    bmr_value = bmr(gender, d_weight, d_height, age_years)
    tdee_value = tdee(bmr_value, activity)
    limit = calorie_limit(tdee_value, bmr_value, goal)

    return {
        "user_id": key,
        "gender": gender,
        "date_of_birth": birth,
        "height_cm": height_cm,
        "weight_kg": weight,
        "activity_level": activity,
        "goal": goal,
        "bmr_kcal": round_half_up(bmr_value),
        "tdee_kcal": round_half_up(tdee_value),
        "daily_calories_target": round_half_up(limit),
        "_age": age_years,
        "_weight_label": row["NObeyesdad"],
        "_faf": faf,
    }


def read_profiles(today: date) -> list[dict[str, Any]]:
    if not PROFILES_CSV.exists():
        raise LoadError(f"{PROFILES_CSV} not found")
    with PROFILES_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise LoadError(f"{PROFILES_CSV} contains no data row")
    needed = {
        "user_id", "Gender", "Age", "Height", "Weight", "FAF", "NObeyesdad",
    }
    missing = needed - set(rows[0])
    if missing:
        raise LoadError(
            f"{PROFILES_CSV.name} is missing columns: "
            f"{', '.join(sorted(missing))}"
        )

    first_seen: dict[str, dict[str, str]] = {}
    for row in rows:
        first_seen.setdefault(row["user_id"], row)
    return [
        convert_profile(first_seen[u], i, today)
        for i, u in enumerate(sorted(first_seen))
    ]


def read_behaviour(
    foods_by_id: dict[str, Any]
) -> dict[str, list[tuple[str, str]]]:
    """`user_id` -> a list of `(food_id, action)` in the file's own order."""
    if not BEHAVIOUR_CSV.exists():
        raise LoadError(
            f"{BEHAVIOUR_CSV} not found.\n"
            "Generate it first: python tools/gen_taste_vectors.py --write"
        )
    with BEHAVIOUR_CSV.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = (
            {"user_id", "ma_mon", "lua_chon"} - set(reader.fieldnames or ())
        )
        if missing:
            raise LoadError(
                f"{BEHAVIOUR_CSV.name} is missing columns: "
                f"{', '.join(sorted(missing))}"
            )
        swipes: dict[str, list[tuple[str, str]]] = {}
        seen: dict[str, set[str]] = {}
        for line_no, row in enumerate(reader, start=2):
            user = row["user_id"].strip()
            food_id = row["ma_mon"].strip()
            choice = row["lua_chon"].strip().lower()
            if choice not in CHOICES:
                raise LoadError(
                    f"  line {line_no}: `lua_chon` = {choice!r} is not valid; "
                    f"it must be one of: {', '.join(CHOICES)}"
                )
            if food_id not in foods_by_id:
                raise LoadError(
                    f"  line {line_no}: `ma_mon` = {food_id} is not an active "
                    f"row in `foods`. The deck has changed — regenerate the "
                    f"deck and the data."
                )
            if food_id in seen.setdefault(user, set()):
                raise LoadError(
                    f"  line {line_no}: {user} has two rows for the same food "
                    f"{food_id}"
                )
            seen[user].add(food_id)
            swipes.setdefault(user, []).append((food_id, CHOICES[choice]))
    if not swipes:
        raise LoadError(f"{BEHAVIOUR_CSV.name} contains no swipe")
    return swipes


def read_ground_truth() -> dict[str, Any]:
    if not GROUND_TRUTH.exists():
        raise LoadError(
            f"{GROUND_TRUTH} not found.\n"
            "Generate it first: python tools/gen_taste_vectors.py --write"
        )
    return json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))


# -- The F1 filter ---------------------------------------------------------


def allowed_foods(
    cn,
    truth: dict[str, Any],
    swipes: dict[str, list[tuple[str, str]]],
    foods_by_id: dict[str, Any],
) -> tuple[
    dict[str, list[tuple[str, str]]],
    dict[str, list[tuple[str, str, list[str]]]],
    dict[str, list[int]],
]:
    """Drop the swipes violating a hard constraint, per person's conditions.

    Runs **before** the preference vector is built, not merely before
    `interactions` is written: filtering afterwards leaves the vector carrying
    the whole constraint-disguised-as-taste part, and `n_signals` still counts
    those swipes so the stage is wrong too.

    It goes through **exactly** the path `import_swipes.py` goes through, so the
    two import routes cannot drift apart.

    Returns `(kept, dropped, condition ids per person)`.
    """
    every_name = sorted(
        {
            name
            for u in swipes
            for name in (
                truth["nguoi"].get(u, {}).get("condition_names") or []
            )
        }
    )
    # Resolve every name once, in the validate phase: 50 profiles sharing one
    # wrong template must fail once before anything is written, not at the
    # thirtieth profile.
    resolve_conditions(cn, every_name)

    kept: dict[str, list[tuple[str, str]]] = {}
    dropped: dict[str, list[tuple[str, str, list[str]]]] = {}
    condition_ids: dict[str, list[int]] = {}

    for u, person_swipes in swipes.items():
        names = truth["nguoi"].get(u, {}).get("condition_names") or []
        condition_ids[u] = resolve_conditions(cn, names)
        remaining, excluded = filter_by_f1(
            cn, names, person_swipes, foods_by_id
        )
        if not remaining:
            raise LoadError(
                f"{u}: the F1 filter excluded all {len(person_swipes)} swipes "
                f"— every food in the survey deck violates one of this "
                f"person's hard constraints. This case needs a different deck."
            )
        # Cross-check against the list the generator wrote into
        # `khau_vi_that.json`.
        #
        # Both sides run the same `exclusion_reasons` but at different times,
        # so a mismatch means `condition_rules` changed after the data was
        # generated — and then the data carries a different constraint from the
        # one the system enforces. It breaks nothing anywhere: the importer
        # still finishes, `build_dataset` still runs, and the F1 measurement in
        # `check_simulation.py` still prints a number — a number for the old
        # rule set.
        recorded = set(truth["nguoi"].get(u, {}).get("f1_excluded") or ())
        just_computed = {f for f, _action, _reasons in excluded}
        if recorded != just_computed:
            raise LoadError(
                f"{u}: the F1 filter just computed {len(just_computed)} "
                f"excluded foods, but khau_vi_that.json records "
                f"{len(recorded)}.\n"
                f"`condition_rules` changed after the data was generated. "
                f"Regenerate: python tools/gen_taste_vectors.py --write"
            )

        kept[u] = remaining
        if excluded:
            dropped[u] = excluded
    return kept, dropped, condition_ids


# -- writing --------------------------------------------------------------


def count_loaded(cn) -> int:
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) n FROM users WHERE email LIKE %s", (EMAIL_LIKE,)
        )
        return int(cur.fetchone()["n"])


def delete_loaded(cn) -> int:
    """Delete the previous load's users. `ON DELETE CASCADE` clears the rest."""
    with cn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email LIKE %s", (EMAIL_LIKE,))
        n = cur.rowcount
    cn.commit()
    return n


def write(
    cn,
    profiles: list[dict[str, Any]],
    swipes: dict[str, list[tuple[str, str]]],
    space: FeatureSpace,
    foods_by_id: dict[str, Any],
    condition_ids: dict[str, list[int]],
    load_date: date,
) -> list[dict[str, Any]]:
    """Write all 50 people in ONE transaction."""
    base_time = datetime.combine(
        load_date, datetime.min.time()
    ).replace(hour=9)
    out: list[dict[str, Any]] = []

    with cn.cursor() as cur:
        for i, profile in enumerate(profiles):
            key = profile["user_id"]
            user_id = str(uuid.uuid5(UUID_NAMESPACE, f"user:{key}"))
            session_id = str(uuid.uuid5(UUID_NAMESPACE, f"session:{key}"))
            email = EMAIL_TEMPLATE.format(key)

            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name, "
                "onboarding_completed_at) VALUES (%s, %s, %s, %s, %s)",
                (
                    user_id,
                    email,
                    UNUSABLE_PASSWORD_HASH,
                    # The display name is a stored, user-facing value; the 50
                    # existing rows carry this exact form.
                    f"Mô phỏng {key}",
                    datetime.combine(load_date, datetime.min.time()),
                ),
            )
            cur.execute(
                "INSERT INTO health_profiles (id, user_id, gender, "
                "date_of_birth, height_cm, weight_kg, activity_level, goal, "
                "bmr_kcal, tdee_kcal, daily_calories_target) "
                "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    profile["gender"],
                    profile["date_of_birth"],
                    profile["height_cm"],
                    profile["weight_kg"],
                    profile["activity_level"],
                    profile["goal"],
                    profile["bmr_kcal"],
                    profile["tdee_kcal"],
                    profile["daily_calories_target"],
                ),
            )

            for condition_id in condition_ids.get(key, []):
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity) VALUES (UUID(), %s, %s, %s)",
                    (user_id, condition_id, FORM_SEVERITY),
                )

            # One session per person, the sessions one minute apart, and within
            # a session the swipes one second apart keeping the file's order:
            # `profile_snapshot` replays the history chronologically when the
            # training set is built, so this order is data, not a presentation
            # detail.
            session_start = base_time + timedelta(minutes=i)
            for j, (food_id, action) in enumerate(swipes[key]):
                cur.execute(
                    "INSERT INTO interactions (id, user_id, food_id, action, "
                    "session_id, interacted_at) "
                    "VALUES (UUID(), %s, %s, %s, %s, %s)",
                    (
                        user_id,
                        food_id,
                        action,
                        session_id,
                        session_start + timedelta(seconds=j),
                    ),
                )

            preference = build_profile(
                space, [(foods_by_id[f], a) for f, a in swipes[key]]
            )
            # `alpha` records the real `alpha(n_signals)`, not 0. `ml/serve.py`
            # recomputes α at serving time so a 0 breaks nothing at runtime,
            # but this column is what Chapter 3's statistical queries read —
            # leaving it 0 makes the α table in the report all zeros while the
            # system does not run on zero.
            cur.execute(
                "INSERT INTO user_preference_profiles (user_id, "
                "feature_version, weights, sum_abs_weight, n_signals, stage, "
                "alpha) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    FEATURE_VERSION,
                    json.dumps(list(preference.weights)),
                    preference.sum_abs_weight,
                    preference.n_signals,
                    stage(preference.n_signals),
                    round(alpha(preference.n_signals), 3),
                ),
            )
            out.append(
                {
                    "key": key,
                    "user_id": user_id,
                    "email": email,
                    "n_signals": preference.n_signals,
                    "stage": stage(preference.n_signals),
                    "alpha": alpha(preference.n_signals),
                }
            )

    cn.commit()
    return out


# -- reporting ------------------------------------------------------------


def preview(
    profiles: list[dict[str, Any]],
    swipes: dict[str, list[tuple[str, str]]],
    space: FeatureSpace,
    foods_by_id: dict[str, Any],
) -> None:
    print(
        f"{len(profiles)} profiles · "
        f"{sum(len(v) for v in swipes.values())} swipes"
    )

    for label, field in (
        ("gender", "gender"),
        ("activity level", "activity_level"),
        ("goal", "goal"),
    ):
        counts = collections.Counter(p[field] for p in profiles)
        print(
            f"  {label:<15} "
            + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )

    bmi = sorted(
        p["weight_kg"] / (p["height_cm"] / 100) ** 2 for p in profiles
    )
    limits = sorted(p["daily_calories_target"] for p in profiles)
    ages = sorted(p["_age"] for p in profiles)
    print(
        f"  age             {ages[0]}-{ages[-1]} "
        f"(median {ages[len(ages)//2]})\n"
        f"  BMI             {bmi[0]:.1f}-{bmi[-1]:.1f} "
        f"(median {bmi[len(bmi)//2]:.1f})\n"
        f"  kcal limit      {limits[0]}-{limits[-1]} "
        f"(median {limits[len(limits)//2]})"
    )

    stages = collections.Counter()
    for profile in profiles:
        preference = build_profile(
            space,
            [(foods_by_id[f], a) for f, a in swipes[profile["user_id"]]],
        )
        stages[stage(preference.n_signals)] += 1
    print(
        "  stage           "
        + "  ".join(f"{k}={v}" for k, v in sorted(stages.items()))
    )

    # Two levels the source scale cannot reach — stated outright rather than
    # leaving a reader of the table above to guess why they are absent.
    print(
        "\n  `very_active` and `healthy_eating` are absent by design: the "
        "`FAF`\n  scale does not reach the top level, and `healthy_eating` is "
        "a user's\n  self-declared choice, not something inferred from a "
        "weight label. See\n  the top of this file."
    )


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--apply", action="store_true",
                        help="write to the database")
    parser.add_argument(
        "--delete", action="store_true",
        help="remove the previous load, then stop",
    )
    args = parser.parse_args()

    cn = connect(args.db)
    try:
        if args.delete:
            n = delete_loaded(cn)
            print(
                f"Deleted {n} simulated users (and every dependent row)."
            )
            return 0

        foods, _ = load_foods(cn)
        space = FeatureSpace.from_foods(foods)
        foods_by_id = {f.id: f for f in foods}
        load_date = date.today()

        try:
            truth = read_ground_truth()
            if truth.get("feature_version") != FEATURE_VERSION:
                raise LoadError(
                    f"feature version mismatch: the simulated data was "
                    f"generated on {truth.get('feature_version')}, the code is "
                    f"now {FEATURE_VERSION}.\nRegenerate: "
                    "python tools/gen_taste_vectors.py --write"
                )
            profiles = read_profiles(load_date)
            swipes = read_behaviour(foods_by_id)

            without_swipes = [
                p["user_id"] for p in profiles if p["user_id"] not in swipes
            ]
            if without_swipes:
                raise LoadError(
                    f"{len(without_swipes)} people have a profile but no "
                    f"swipes: {', '.join(without_swipes[:5])}"
                )
            without_profile = set(swipes) - {p["user_id"] for p in profiles}
            if without_profile:
                raise LoadError(
                    f"{len(without_profile)} people have swipes but no "
                    f"profile: {', '.join(sorted(without_profile)[:5])}"
                )
            swipes, dropped, condition_ids = allowed_foods(
                cn, truth, swipes, foods_by_id
            )
        except (LoadError, FormError) as e:
            print(f"Could not load.\n{e}", file=sys.stderr)
            return 1

        already = count_loaded(cn)
        if already:
            print(
                f"{already} simulated users are already in the database. Not "
                "loading on top.\nDelete first, then reload: "
                "python tools/import_simulation.py --delete",
                file=sys.stderr,
            )
            return 1

        print(f"Source: {BEHAVIOUR_CSV.relative_to(ROOT)}")
        print(
            f"        {PROFILES_CSV.relative_to(ROOT)}  (profile columns only)"
        )
        print(
            f"        {GROUND_TRUTH.relative_to(ROOT)}  "
            f"seed {truth['params']['seed']}"
        )
        print()
        preview(profiles, swipes, space, foods_by_id)
        n_dropped = sum(len(v) for v in dropped.values())
        n_kept = sum(len(v) for v in swipes.values())
        if n_dropped:
            # Grouped by reason, not listed food by food: a vegan loses 22
            # foods to EXACTLY ONE rule, and printing 22 identical lines hides
            # that.
            by_reason: collections.Counter[str] = collections.Counter()
            for person_dropped in dropped.values():
                for _food, _action, reasons in person_dropped:
                    by_reason[reasons[0]] += 1
            print(
                f"\n  The F1 filter excluded {n_dropped}/"
                f"{n_dropped + n_kept} swipes across {len(dropped)} people:"
            )
            for reason, count in by_reason.most_common():
                print(f"      {reason} -> {count} swipes")
            print(
                "    These swipes are NOT written and do NOT enter the "
                "preference\n    vector: they are a constraint, not a taste."
            )
        else:
            print(
                f"\n  The F1 filter excluded 0/{n_kept} swipes — nobody in "
                "this set\n  carries a hard constraint."
            )

        if not args.apply:
            print("\nPreview. Add --apply to write to the database.")
            return 0

        written = write(
            cn, profiles, swipes, space, foods_by_id, condition_ids, load_date
        )
        n_swipes = sum(len(v) for v in swipes.values())
        print(
            f"\nWrote {len(written)} people · {n_swipes} `interactions` rows · "
            f"{len(written)} `health_profiles` and "
            f"`user_preference_profiles` rows."
        )
        print("Next: python -m ml.build_dataset --version v1")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
