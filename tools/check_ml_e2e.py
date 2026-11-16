#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end checks for the machine-learning layer — builds its own database
and drops it when done.

`tools/check_ml.py` checks the pure functions with no database. This file
checks the rest: the four scripts that read and write the database, running one
after another exactly as they do for real.

    build_dataset  ->  train  ->  evaluate  ->  serve

Why it builds its own database. All seven signal sources in `nutrition_rec` are
**empty** — there is no real user yet. So there is no way to check these four
scripts against the real database, and writing fake signals into the real one
would dirty the very thing that has to stay clean. This file creates a separate
database, copies the **real food data** across (so the feature vectors are
still the real ones), builds fake users there, runs everything, then drops the
database.

**The labels are assigned at random, and that is deliberate.** Not for
convenience, but because it creates a **data-leakage tripwire**: if the pipeline
does not leak, the model is forced to score around chance. A good number here
is evidence of leakage, not good news. Generating fake profiles with a known
taste and having them "swipe" according to that taste would make the model
relearn the rule just invented, and the tripwire would stop working.

Every number printed here is **not an experimental result** and must not go
into the report. They only prove the pipeline runs correctly.

Run:
    python tools/check_ml_e2e.py
    python tools/check_ml_e2e.py --keep    # keep the database for inspection

Note on language: the survey form's field keys and the `lua_chon` values are
the contract with `tools/import_swipes.py`; the condition names, tag names,
food names and the strings matched against `condition_rules.note` all come from
the database. Those stay as they are.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from ml.build_dataset import main as run_build_dataset  # noqa: E402
from ml.db import connect, use_utf8  # noqa: E402
from ml.evaluate import main as run_evaluate  # noqa: E402
from ml.f1_filter import (  # noqa: E402
    conditions_for_user,
    conditions_by_name,
    cross_check_f1,
    allowed_foods,
    unenforced_rules,
    soft_rules,
    soft_rules_by_scope,
    exclusion_reasons,
)
from ml.scoring import penalty  # noqa: E402
from ml.daily_limits import (  # noqa: E402
    eaten_totals,
    planned_totals,
    check_double_counting,
    classify_foods,
    status,
)
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.rocchio import alpha, build_profile, stage  # noqa: E402
from ml.serve import recommend, load_active_model  # noqa: E402
from ml.train import main as run_train  # noqa: E402
from tools.make_survey_deck import pick_deck  # noqa: E402
from tools.update_popularity import main as _update_popularity  # noqa: E402


def run_import_swipes(argv: list[str]) -> int:
    """`import_swipes.main` reads `sys.argv`, so it has to be swapped out."""
    from tools.import_swipes import main as _import

    saved = sys.argv
    sys.argv = ["import_swipes.py", *argv]
    try:
        return _import()
    finally:
        sys.argv = saved


def run_update_popularity(argv: list[str]) -> int:
    """`update_popularity.main` reads `sys.argv`, so it has to be swapped out."""
    saved = sys.argv
    sys.argv = ["update_popularity.py", *argv]
    try:
        return _update_popularity()
    finally:
        sys.argv = saved


TEST_DATABASE = "zz_check_ml"
SES = "33333333-3333-3333-3333-333333333333"

#: The email of the form-filling user. Declared once because four queries
#: match on it.
FORM_EMAIL = "form-filler@test.test"

#: The note text on the test-only rule section 7 inserts. Declared once
#: because the rule is matched by it and then deleted by it.
TEST_RULE_NOTE = "TEST-ONLY RULE for the checker — not any recommendation"

#: The reference tables copied from the real database, in a foreign-key-safe
#: order.
REFERENCE_TABLES = (
    "food_categories",
    "tags",
    "conditions",
    "condition_rules",
    "rda_reference",
    "foods",
    "food_nutrition",
    "food_tags",
)

#: Each person's swipe count, chosen to cover **all four stages**.
#: `stage`: 0 -> cold, 1-29 -> content, 30-100 -> hybrid, >100 -> ml.
SWIPE_COUNTS = [0, 12, 12, 18, 45, 45, 60, 60, 120, 150, 25, 25]

_passed = 0
_failures: list[str] = []


def check(condition: bool, description: str) -> None:
    global _passed
    if condition:
        _passed += 1
        print(f"  ok   {description}")
    else:
        _failures.append(description)
        print(f"  BAD  {description}")


#: The tolerance when comparing two nutrient totals. `food_nutrition` is
#: `DECIMAL` and the portion is `DECIMAL(4,2)`, so a total summed by MySQL and
#: one summed by Python may differ in the last digit — but only there.
TOTALS_TOLERANCE = 1e-6


def approx(actual: float, expected: float, description: str) -> None:
    check(
        abs(actual - expected) < TOTALS_TOLERANCE,
        f"{description}: got {actual:.4f}, expected {expected:.4f}",
    )


# -- Building the test database ----------------------------------------


def _writable_columns(cn, db: str, table: str) -> list[str]:
    """The writable columns — excluding **generated columns**, because an
    `INSERT` into one is error 3105.

    Filtered on `GENERATION_EXPRESSION`, not on `EXTRA`. My first attempt was
    `EXTRA NOT LIKE '%GENERATED%'`, and it was wrong in a very hard-to-see
    way: MySQL 8 marks **every** column with an expression default as
    `DEFAULT_GENERATED`, so `id CHAR(36) DEFAULT (UUID())` and
    `created_at DATETIME DEFAULT CURRENT_TIMESTAMP` were excluded too.

    The consequence was not a SQL error but **silently wrong data**: the copy
    still inserted every row, but each row got a fresh `UUID()`, so
    `foods.category_id` pointed at `food_categories.id` values that no longer
    existed. The subsequent `JOIN` returned 0 rows, and the only symptom was
    "the food set is empty".
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "  AND (GENERATION_EXPRESSION IS NULL "
            "       OR GENERATION_EXPRESSION = '') "
            "ORDER BY ORDINAL_POSITION",
            (db, table),
        )
        return [d["COLUMN_NAME"] for d in cur.fetchall()]


def build_test_database(source: str, test: str) -> None:
    """Copy every table's schema plus the reference tables' data.

    `CREATE TABLE ... LIKE` copies the generated columns, keys and indexes, so
    the test schema matches the real one in every detail — including
    `uq_sample` and `uq_eval`, the two keys this checker needs in order to
    prove that rerunning does not duplicate data.
    """
    cn = connect(source, dict_cursor=True)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
                (source,),
            )
            all_tables = {d["TABLE_NAME"] for d in cur.fetchall()}

        # Table creation order: a foreign key pointing at a table that does
        # not exist yet is error 1215. Foreign-key checking is turned off
        # during the build and back on after — far cheaper than a topological
        # sort, and the resulting schema still has every constraint.
        with cn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{test}`")
            cur.execute(
                f"CREATE DATABASE `{test}` CHARACTER SET utf8mb4 "
                f"COLLATE utf8mb4_unicode_ci"
            )
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in sorted(all_tables):
                cur.execute(
                    f"CREATE TABLE `{test}`.`{table}` "
                    f"LIKE `{source}`.`{table}`"
                )
            for table in REFERENCE_TABLES:
                columns = _writable_columns(cn, source, table)
                column_list = ", ".join(f"`{c}`" for c in columns)
                cur.execute(
                    f"INSERT INTO `{test}`.`{table}` ({column_list}) "
                    f"SELECT {column_list} FROM `{source}`.`{table}`"
                )
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cn.commit()
    finally:
        cn.close()


def drop_test_database(test: str) -> None:
    cn = connect("information_schema", dict_cursor=True)
    try:
        with cn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{test}`")
        cn.commit()
    finally:
        cn.close()


# -- Building the fake users -------------------------------------------


def build_users(cn) -> dict[str, int]:
    """Create users whose swipe counts cover all four stages.

    Returns `{user_id: the computed signal count}`. The computed count differs
    from the inserted count because `unknown` swipes are not counted — and
    that is itself one of the things to check.
    """
    rng = random.Random(2026)
    foods, _ = load_foods(cn)
    space = FeatureSpace.from_foods(foods)
    foods_by_id = {f.id: f for f in foods}
    food_ids = sorted(foods_by_id)
    base_time = datetime(2026, 9, 1, 8, 0, 0)

    result: dict[str, int] = {}
    with cn.cursor() as cur:
        for u, count in enumerate(SWIPE_COUNTS):
            uid = f"{u:08d}-0000-0000-0000-000000000000"
            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (%s, %s, %s, %s)",
                (
                    uid, f"u{u}@test.test", "x" * 20,
                    f"Test user {u} ({count} swipes)",
                ),
            )
            cur.execute(
                "INSERT INTO health_profiles (id, user_id, gender, "
                "date_of_birth, height_cm, weight_kg, activity_level, goal) "
                "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s)",
                (
                    uid,
                    rng.choice(["male", "female"]),
                    f"{rng.randint(1975, 2005)}-06-15",
                    rng.randint(150, 185),
                    rng.randint(45, 95),
                    rng.choice(["sedentary", "light", "moderate", "active"]),
                    rng.choice(
                        [
                            "lose_weight", "maintain", "gain_weight",
                            "healthy_eating",
                        ]
                    ),
                ),
            )

            pairs = []
            for i, food_id in enumerate(rng.sample(food_ids, count)):
                # A small share are `unknown`, to check that they are excluded
                # from both the Rocchio vector and the training set.
                action = rng.choices(
                    ["like", "dislike", "neutral", "unknown"],
                    weights=[40, 40, 15, 5],
                )[0]
                cur.execute(
                    "INSERT INTO interactions (id, user_id, food_id, action, "
                    "session_id, interacted_at) "
                    "VALUES (UUID(), %s, %s, %s, %s, %s)",
                    (
                        uid, food_id, action, SES,
                        base_time + timedelta(seconds=u * 7200 + i),
                    ),
                )
                pairs.append((foods_by_id[food_id], action))

            # A few signals from other sources, with random labels too.
            for food_id in rng.sample(food_ids, min(4, count) if count else 0):
                cur.execute(
                    "INSERT INTO feedbacks (id, user_id, food_id, rating, "
                    "created_at) VALUES (UUID(), %s, %s, %s, %s)",
                    (
                        uid, food_id, rng.randint(1, 5),
                        base_time + timedelta(days=5, seconds=u * 60),
                    ),
                )

            profile = build_profile(space, pairs)
            cur.execute(
                "INSERT INTO user_preference_profiles (user_id, "
                "feature_version, weights, sum_abs_weight, n_signals, stage, "
                "alpha) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    uid,
                    FEATURE_VERSION,
                    json.dumps(list(profile.weights)),
                    profile.sum_abs_weight,
                    profile.n_signals,
                    stage(profile.n_signals),
                    round(alpha(profile.n_signals), 3),
                ),
            )
            result[uid] = profile.n_signals
    cn.commit()
    return result


# -- The checks --------------------------------------------------------


def check_form_import(db: str) -> str | None:
    """Generate a survey form, fill it in, import it — error paths included.

    The user imported from a form goes on through the rest of the pipeline
    alongside the other fake users, so this check also proves that
    form-collected data is **usable downstream**, not merely written to a
    table.
    """
    print("\n0. Importing a taste survey form")
    rng = random.Random(99)
    # `tempfile` rather than a directory inside the repo: this checker must
    # leave no file in the source tree, not even when it breaks halfway.
    work_dir = Path(tempfile.mkdtemp(prefix="check_ml_form_"))

    cn = connect(db)
    try:
        foods, _ = load_foods(cn)
    finally:
        cn.close()
    space = FeatureSpace.from_foods(foods)
    deck = pick_deck(foods, space, 40)
    check(len(deck) == 40, "a 40-food survey deck was selected")
    check(
        len({f.category for f in deck}) == len({f.category for f in foods}),
        "the deck covers every food category",
    )
    check(
        pick_deck(foods, space, 40) == deck,
        "reselecting gives the same deck — the algorithm is deterministic, "
        "not random",
    )

    def write_form(
        name: str, *, choice_fn=None, extra_info="", n_foods: int = 40
    ) -> Path:
        path = work_dir / name
        with path.open("w", encoding="utf-8", newline="") as f:
            # The `# key: value` block uses the form's own Vietnamese keys —
            # see the note on language at the top of the file.
            f.write("# ho_ten: Form filler\n")
            f.write(f"# email: {FORM_EMAIL}\n")
            f.write("# gioi_tinh: female\n")
            f.write("# ngay_sinh: 1999-04-20\n")
            f.write("# chieu_cao_cm: 162\n")
            f.write("# can_nang_kg: 54\n")
            f.write("# muc_van_dong: light\n")
            f.write("# muc_tieu: healthy_eating\n")
            f.write("# benh_ly: Tăng huyết áp\n")
            f.write("# ngay_khao_sat: 2026-10-20\n")
            f.write(extra_info)
            writer = csv.writer(f)
            writer.writerow(
                ["stt", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon"]
            )
            for i, food in enumerate(deck[:n_foods], start=1):
                choice = (
                    choice_fn(i, food)
                    if choice_fn
                    else rng.choice(
                        [
                            "thich", "thich", "khong_thich", "binh_thuong",
                            "chua_biet",
                        ]
                    )
                )
                writer.writerow(
                    [i, food.id, food.name, food.category, food.spice_level,
                     choice]
                )
        return path

    # -- Error paths: must be refused BEFORE anything is written --
    error_cases = [
        (
            "bad_choice.csv",
            dict(choice_fn=lambda i, f: "maybe_like" if i == 3 else "thich"),
            "an invalid `lua_chon` value",
        ),
        (
            "unfilled.csv",
            dict(choice_fn=lambda i, f: ""),
            "a form with no choice filled in",
        ),
        (
            "missing_info.csv",
            dict(extra_info="# chieu_cao_cm: \n"),
            "a blank in the info block",
        ),
    ]
    for name, kwargs, description in error_cases:
        path = write_form(name, **kwargs)
        if name == "missing_info.csv":
            # Rewrite the whole file with the height removed, because on a
            # duplicate key the later line wins — adding a line does not
            # remove the earlier one.
            content = path.read_text(encoding="utf-8").replace(
                "# chieu_cao_cm: 162\n", ""
            )
            path.write_text(content, encoding="utf-8")
        code = run_import_swipes(["--form", str(path), "--db", db, "--apply"])
        check(code == 1, f"the form is refused: {description}")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM users WHERE email = %s", (FORM_EMAIL,)
            )
            check(
                int(cur.fetchone()["n"]) == 0,
                "a refused form leaves no user behind",
            )
    finally:
        cn.close()

    # A height outside the health_profiles CHECK range.
    path = write_form("absurd_height.csv")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "# chieu_cao_cm: 162", "# chieu_cao_cm: 320"
        ),
        encoding="utf-8",
    )
    check(
        run_import_swipes(["--form", str(path), "--db", db, "--apply"]) == 1,
        "the form is refused: a height outside 50-250",
    )

    # A condition name that does not match `conditions`.
    path = write_form("unknown_condition.csv")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "# benh_ly: Tăng huyết áp", "# benh_ly: Cảm nắng"
        ),
        encoding="utf-8",
    )
    check(
        run_import_swipes(["--form", str(path), "--db", db, "--apply"]) == 1,
        "the form is refused: a condition name not in `conditions`",
    )

    # -- The happy path --
    path = write_form("valid.csv")
    check(
        run_import_swipes(["--form", str(path), "--db", db]) == 0,
        "a dry run of a valid form: exit code 0",
    )
    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM users")
            before = int(cur.fetchone()["n"])
    finally:
        cn.close()

    check(
        run_import_swipes(["--form", str(path), "--db", db, "--apply"]) == 0,
        "importing a valid form: exit code 0",
    )

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM users")
            check(
                int(cur.fetchone()["n"]) == before + 1,
                "the dry run wrote NOTHING",
            )

            cur.execute(
                "SELECT id, password_hash, display_name FROM users "
                "WHERE email = %s",
                (FORM_EMAIL,),
            )
            user = cur.fetchone()
            check(user is not None, "the user was created")
            uid = user["id"]
            check(
                user["password_hash"].startswith("!"),
                "the password is an unusable value (leading `!`)",
            )

            cur.execute(
                "SELECT gender, height_cm, weight_kg, bmi, goal "
                "FROM health_profiles WHERE user_id = %s",
                (uid,),
            )
            health = cur.fetchone()
            check(health is not None, "health_profiles was created")
            check(
                abs(float(health["bmi"]) - 54 / (1.62**2)) < 0.01,
                f"the generated bmi column computes correctly "
                f"({float(health['bmi']):.2f})",
            )

            cur.execute(
                "SELECT co.name_vi FROM user_conditions uc "
                "JOIN conditions co ON co.id = uc.condition_id "
                "WHERE uc.user_id = %s",
                (uid,),
            )
            check(
                [d["name_vi"] for d in cur.fetchall()] == ["Tăng huyết áp"],
                "the condition was recorded",
            )

            cur.execute(
                "SELECT action, COUNT(*) n FROM interactions "
                "WHERE user_id = %s GROUP BY action",
                (uid,),
            )
            counts = {d["action"]: int(d["n"]) for d in cur.fetchall()}
            check(
                sum(counts.values()) == 40,
                f"all 40 swipes were written (got {counts})",
            )

            cur.execute(
                "SELECT COUNT(DISTINCT interacted_at) n FROM interactions "
                "WHERE user_id = %s",
                (uid,),
            )
            check(
                int(cur.fetchone()["n"]) == 40,
                "40 swipes have 40 distinct timestamps — the form's order is "
                "preserved",
            )

            cur.execute(
                "SELECT feature_version, n_signals, stage, "
                "       JSON_LENGTH(weights) n_dimensions "
                "FROM user_preference_profiles WHERE user_id = %s",
                (uid,),
            )
            preference = cur.fetchone()
            check(
                preference is not None,
                "user_preference_profiles was computed",
            )
            check(
                int(preference["n_dimensions"]) == space.length,
                f"the preference vector has all {space.length} dimensions",
            )
            check(
                int(preference["n_signals"])
                == 40 - counts.get("unknown", 0),
                f"n_signals = {preference['n_signals']} after subtracting "
                f"{counts.get('unknown', 0)} `chua_biet` swipes",
            )
            check(
                preference["feature_version"] == FEATURE_VERSION,
                "the profile records the feature version alongside",
            )

        # Importing the same form again: must be refused, the email exists.
        check(
            run_import_swipes(
                ["--form", str(path), "--db", db, "--apply"]
            ) == 1,
            "reimporting the same form is refused — the email already exists",
        )
    finally:
        cn.close()

    shutil.rmtree(work_dir, ignore_errors=True)
    return uid


def check_pipeline(db: str, signal_counts: dict[str, int]) -> None:
    print("\n1. The dataset builder")
    code = run_build_dataset(
        ["--version", "e2e", "--db", db, "--apply", "--random-neg", "8",
         "--folds", "5", "--seed", "7"]
    )
    check(code == 0, "build_dataset finished, exit code 0")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_training_samples")
            n_samples = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples s "
                "JOIN interactions i ON i.user_id = s.user_id "
                "  AND i.food_id = s.food_id "
                "WHERE s.source = 'swipe' AND i.action = 'unknown'"
            )
            n_unknown = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT fold) n FROM ml_training_samples"
            )
            n_folds = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ("
                "  SELECT user_id FROM ml_training_samples "
                "  GROUP BY user_id HAVING COUNT(DISTINCT fold) > 1) x"
            )
            n_split_users = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples "
                "WHERE profile_snapshot IS NULL"
            )
            n_no_snapshot = cur.fetchone()["n"]

        check(n_samples > 0, f"{n_samples} samples produced")
        check(n_unknown == 0, "no `swipe` sample comes from an `unknown` swipe")
        check(n_folds == 5, f"all 5 folds are used (got {n_folds})")
        check(n_split_users == 0, "no user is split across two folds")
        check(n_no_snapshot == 0, "every sample has a profile_snapshot")

        print("\n1b. Popularity — the control variant must stop being degenerate")
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT popularity_score) n FROM foods"
            )
            check(
                cur.fetchone()["n"] == 1,
                "before computing: every food shares one popularity_score "
                "(degenerate)",
            )
        code = run_update_popularity(["--db", db, "--apply"])
        check(code == 0, "update_popularity finished, exit code 0")
        cn.commit()
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT popularity_score) n, "
                "       MIN(popularity_score) lo, MAX(popularity_score) hi, "
                "       SUM(popularity_score > 0) scored "
                "FROM foods"
            )
            popularity = cur.fetchone()
        check(
            int(popularity["n"]) > 1,
            f"after computing: {popularity['n']} distinct scores — no longer "
            f"degenerate",
        )
        check(
            0 <= float(popularity["lo"]) and float(popularity["hi"]) <= 1,
            f"the scores lie within [0, 1]: "
            f"{float(popularity['lo']):.4f}-{float(popularity['hi']):.4f}",
        )
        check(
            int(popularity["scored"]) > 0,
            f"{popularity['scored']} foods score above 0",
        )

        print("\n2. Training")
        code = run_train(
            ["--dataset", "e2e", "--db", db, "--apply",
             "--algorithm", "logistic_regression",
             "--activate", "logistic_regression"]
        )
        check(code == 0, "train finished, exit code 0")

        cn.commit()  # leave the old transaction snapshot to see the new rows
        with cn.cursor() as cur:
            cur.execute(
                "SELECT version, n_train, n_test, is_active, feature_version "
                "FROM ml_models"
            )
            models = cur.fetchall()
        check(len(models) == 1, f"1 model written (got {len(models)})")
        check(
            sum(int(r["is_active"]) for r in models) == 1,
            "exactly one model has is_active = 1",
        )
        check(
            models[0]["feature_version"] == FEATURE_VERSION,
            "the model's feature_version matches the current code",
        )
        check(
            models[0]["n_train"] > 0 and models[0]["n_test"] > 0,
            f"n_train = {models[0]['n_train']}, "
            f"n_test = {models[0]['n_test']}",
        )
        model_version = models[0]["version"]

        print("\n3. Evaluation")
        code = run_evaluate(
            ["--dataset", "e2e", "--model", model_version, "--db", db,
             "--apply"]
        )
        check(code == 0, "evaluate finished, exit code 0")

        cn.commit()
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_evaluations")
            n_rows = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT variant) n FROM ml_evaluations"
            )
            n_variants = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT metric) n FROM ml_evaluations"
            )
            n_metrics = cur.fetchone()["n"]
            cur.execute(
                "SELECT variant, ROUND(AVG(value), 4) v FROM ml_evaluations "
                "WHERE metric = 'auc' GROUP BY variant ORDER BY variant"
            )
            auc = {d["variant"]: float(d["v"]) for d in cur.fetchall()}
        check(n_rows > 0, f"{n_rows} evaluation rows written")
        check(n_variants == 5, f"all 5 control variants (got {n_variants})")
        check(n_metrics == 8, f"all 8 metrics (got {n_metrics})")

        # -- The data-leakage tripwire --
        #
        # The labels are entirely random, so **every** variant must sit at
        # chance. Checked by AUC rather than nDCG: AUC has a definite chance
        # level of 0.5 regardless of the label distribution and regardless of
        # ties, while nDCG@5 does not — its chance level depends on each
        # person's list length and on how many foods tie, so two variants
        # 0.15 apart on nDCG may both still be uninformative.
        #
        # All five variants are checked, not just `ml`: both leaks found so
        # far showed up in `popularity` BEFORE reaching the model.
        for variant in sorted(auc):
            check(
                0.35 <= auc[variant] <= 0.65,
                f"LEAKAGE TRIPWIRE: AUC of `{variant}` = {auc[variant]:.4f}, "
                f"around chance",
            )

        # Rerunning must not duplicate — the two unique keys must block it.
        run_build_dataset(
            ["--version", "e2e", "--db", db, "--apply", "--random-neg", "8",
             "--folds", "5", "--seed", "7"]
        )
        run_evaluate(
            ["--dataset", "e2e", "--model", model_version, "--db", db,
             "--apply"]
        )
        cn.commit()
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_training_samples")
            n_samples2 = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM ml_evaluations")
            n_rows2 = cur.fetchone()["n"]
        check(
            n_samples2 == n_samples,
            f"rerun: {n_samples} -> {n_samples2} samples, no duplication",
        )
        check(
            n_rows2 == n_rows,
            f"rerun: {n_rows} -> {n_rows2} evaluation rows",
        )
    finally:
        cn.close()


def check_serving(db: str, signal_counts: dict[str, int]) -> None:
    print("\n4. The serving layer — the four stages")
    cn = connect(db)
    try:
        by_stage: dict[str, str] = {}
        for uid, n in sorted(signal_counts.items(), key=lambda kv: kv[1]):
            by_stage.setdefault(stage(n), uid)

        check(
            set(by_stage) == {"cold", "content", "hybrid", "ml"},
            f"the test data covers all four stages (got {sorted(by_stage)})",
        )

        expected_source = {
            "cold": "rule_based",
            "content": "content_based",
            "hybrid": "hybrid",
            "ml": "ml",
        }
        for stage_name, uid in sorted(by_stage.items()):
            result = recommend(cn, uid, limit=5)
            check(
                result.stage == stage_name
                and result.generation_source == expected_source[stage_name],
                f"{stage_name}: generation_source = "
                f"{result.generation_source}",
            )
            check(
                len(result.candidates) == 5,
                f"{stage_name}: 5 top candidates returned",
            )
            check(
                all(0.0 <= c.score <= 1.0 for c in result.candidates),
                f"{stage_name}: every score lies within [0, 1]",
            )
            check(
                all(
                    result.candidates[i].score
                    >= result.candidates[i + 1].score
                    for i in range(len(result.candidates) - 1)
                ),
                f"{stage_name}: the list is sorted descending",
            )
            uses_model = stage_name in ("hybrid", "ml")
            check(
                (result.model_id is not None) == uses_model,
                f"{stage_name}: "
                f"{'uses' if uses_model else 'does not use'} a model",
            )
            if stage_name == "cold":
                check(
                    all(c.ml_score is None for c in result.candidates),
                    "cold: the model is not called at all",
                )
            if stage_name == "hybrid":
                check(
                    0 < result.alpha < 1,
                    f"hybrid: 0 < α = {result.alpha:.3f} < 1",
                )
            if stage_name == "ml":
                check(result.alpha == 1.0, "ml: α = 1")

        # -- The F1 filter really does cut candidates --
        uid = by_stage["content"]
        before = recommend(cn, uid, limit=1000).n_foods_after_f1
        conditions = conditions_by_name(
            cn, ["Ăn thuần chay", "Dị ứng đậu nành"], "severe"
        )
        with cn.cursor() as cur:
            for condition in conditions:
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity) VALUES (UUID(), %s, %s, 'severe')",
                    (uid, condition.condition_id),
                )
        cn.commit()
        after = recommend(cn, uid, limit=1000).n_foods_after_f1
        check(
            after < before,
            f"adding conditions makes F1 cut candidates: {before} -> {after} "
            f"foods",
        )

        # Foods already used today are excluded.
        result = recommend(cn, uid, limit=3)
        already_used = [c.food.id for c in result.candidates[:2]]
        result2 = recommend(cn, uid, limit=3, exclude_foods=already_used)
        check(
            all(c.food.id not in already_used for c in result2.candidates),
            "a food already used today does not reappear",
        )

        print("\n5. Announced degradation")
        uid_ml = by_stage["ml"]
        with cn.cursor() as cur:
            cur.execute("UPDATE ml_models SET is_active = 0")
        cn.commit()
        result = recommend(cn, uid_ml, limit=3)
        check(
            result.stage == "content"
            and result.generation_source == "content_based",
            f"with no model it falls back to content_based (got "
            f"{result.stage})",
        )
        check(
            any("falling back to Stage 1" in w for w in result.warnings),
            "the fallback is announced in the warnings",
        )

        # Two models both is_active: it must refuse to pick arbitrarily.
        with cn.cursor() as cur:
            cur.execute(
                "INSERT INTO ml_models (version, algorithm, feature_version, "
                "dataset_version, n_train, n_test, artifact_path, is_active) "
                "SELECT CONCAT(version, '-x'), algorithm, feature_version, "
                "dataset_version, n_train, n_test, artifact_path, 1 "
                "FROM ml_models LIMIT 1"
            )
            cur.execute("UPDATE ml_models SET is_active = 1")
        cn.commit()
        foods, _ = load_foods(cn)
        space = FeatureSpace.from_foods(foods)
        model, reason = load_active_model(cn, space)
        check(
            model is None and reason is not None
            and "share is_active" in reason,
            f"two models both is_active: it refuses to pick arbitrarily "
            f"({reason})",
        )

        # A preference profile on the wrong feature version: skip and announce.
        with cn.cursor() as cur:
            cur.execute("UPDATE ml_models SET is_active = 0")
            cur.execute(
                "UPDATE user_preference_profiles "
                "SET feature_version = 'v0-old' WHERE user_id = %s",
                (uid_ml,),
            )
        cn.commit()
        result = recommend(cn, uid_ml, limit=3)
        check(
            result.stage == "cold" and result.n_signals == 0,
            f"a wrong-version profile falls back to Stage 0 (got "
            f"{result.stage})",
        )
        check(
            any("feature version" in w for w in result.warnings),
            "skipping the profile is announced",
        )

        # A profile with too few dimensions: must also be skipped.
        with cn.cursor() as cur:
            cur.execute(
                "UPDATE user_preference_profiles "
                "SET feature_version = %s, weights = %s WHERE user_id = %s",
                (FEATURE_VERSION, json.dumps([0.1] * 5), uid_ml),
            )
        cn.commit()
        result = recommend(cn, uid_ml, limit=3)
        check(
            result.stage == "cold",
            f"a short-vector profile falls back to Stage 0 (got "
            f"{result.stage})",
        )
        check(
            any("dimensions" in w for w in result.warnings),
            "skipping a short-vector profile is announced",
        )
    finally:
        cn.close()


def check_daily_limits_sql(db: str) -> None:
    """Daily limits against the real database — two sources, and the
    no-double-counting convention.

    This section inserts a real diary and a real meal plan, then compares the
    totals with figures summed by hand straight from `food_nutrition`. It
    checks what the pure-function checks cannot reach: whether the SQL
    multiplies by `portion_multiplier`, whether a `replaced` slot counts the
    **new** food, and whether an `eaten` slot gets counted twice.
    """
    print("\n6. Daily limits — the diary, the meal plan and the counting rules")
    day = date(2026, 10, 15)
    uid = "00000003-0000-0000-0000-000000000000"

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            # Gout at moderate + hypertension at mild: exactly the two
            # conditions with a hard daily threshold in the rule set.
            for condition_id, severity in ((5, "moderate"), (2, "mild")):
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity, created_at) VALUES (UUID(), %s, %s, %s, NOW())",
                    (uid, condition_id, severity),
                )

            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.name IN (%s, %s, %s, %s)",
                (
                    "Bánh cuốn nóng", "Canh chua chay", "Cá chiên xù",
                    "Bắp cải luộc",
                ),
            )
            foods = {d["name"]: d for d in cur.fetchall()}

        check(
            len(foods) == 4,
            f"all 4 anchor foods found in the test database, got {len(foods)}",
        )
        if len(foods) != 4:
            return

        sodium = {k: float(v["sodium_mg"]) for k, v in foods.items()}
        purine = {k: float(v["purine_mg"]) for k, v in foods.items()}

        with cn.cursor() as cur:
            # EATEN: half a serving, to catch a forgotten portion multiplier.
            # That bug produces a SMALLER number than the truth, that is, it
            # loosens a safety limit without reporting anything — exactly the
            # kind of bug that never reveals itself.
            cur.execute(
                "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                "meal_type, portion_multiplier, created_at) "
                "VALUES (UUID(), %s, %s, %s, 'breakfast', 0.50, NOW())",
                (uid, foods["Bánh cuốn nóng"]["id"], day),
            )

            cur.execute(
                "INSERT INTO meal_plans (id, user_id, plan_date, "
                "target_calories_kcal, target_protein_g, target_carbs_g, "
                "target_fat_g, generation_source, status, generated_at) "
                "VALUES (UUID(), %s, %s, 2000, 90, 250, 60, 'rule_based', "
                "'active', NOW())",
                (uid, day),
            )
            cur.execute(
                "SELECT id FROM meal_plans "
                "WHERE user_id = %s AND plan_date = %s",
                (uid, day),
            )
            plan_id = cur.fetchone()["id"]

            slots = (
                # (food, status, portion, replacement food)
                ("Canh chua chay", "kept", 1.00, None),
                ("Cá chiên xù", "suggested", 2.00, None),
                # A replaced slot: must count Bắp cải luộc, NOT Cá chiên xù.
                ("Cá chiên xù", "replaced", 1.00, "Bắp cải luộc"),
                # With a matching diary entry -> the convention is respected.
                ("Bánh cuốn nóng", "eaten", 1.00, None),
                # With NO diary entry -> `check_double_counting` must catch it.
                ("Cá chiên xù", "eaten", 1.00, None),
                ("Bắp cải luộc", "skipped", 1.00, None),
            )
            for name, slot_status, portion, replacement in slots:
                cur.execute(
                    "INSERT INTO meal_plan_items (id, meal_plan_id, food_id, "
                    "meal_type, portion_multiplier, status, "
                    "replaced_by_food_id, created_at) "
                    "VALUES (UUID(), %s, %s, 'lunch', %s, %s, %s, NOW())",
                    (
                        plan_id,
                        foods[name]["id"],
                        portion,
                        slot_status,
                        foods[replacement]["id"] if replacement else None,
                    ),
                )
        cn.commit()

        # -- Each total against the hand-summed figure --
        eaten = eaten_totals(cn, uid, day)
        expected_eaten = sodium["Bánh cuốn nóng"] * 0.5
        approx(
            eaten.totals["sodium_mg"], expected_eaten,
            "eaten: sodium = 0.5 servings of Bánh cuốn nóng",
        )

        planned = planned_totals(cn, uid, day)
        expected_planned = (
            sodium["Canh chua chay"] * 1.0
            + sodium["Cá chiên xù"] * 2.0
            + sodium["Bắp cải luộc"] * 1.0  # a `replaced` slot counts the NEW food
        )
        approx(
            planned.totals["sodium_mg"],
            expected_planned,
            "planned: `kept` + `suggested`x2 + `replaced`->the new food",
        )
        check(
            abs(
                planned.totals["sodium_mg"]
                - (expected_planned + sodium["Bánh cuốn nóng"])
            ) > 1.0,
            "an `eaten` slot is NOT added to the plan — adding it would be "
            "double counting",
        )
        check(
            abs(
                planned.totals["sodium_mg"]
                - (expected_planned + sodium["Bắp cải luộc"])
            ) > 1.0,
            "a `skipped` slot is not added",
        )
        check(
            abs(
                planned.totals["sodium_mg"]
                - (
                    expected_planned - sodium["Bắp cải luộc"]
                    + sodium["Cá chiên xù"]
                )
            ) > 1.0,
            "a `replaced` slot does not count the OLD food",
        )

        # -- The limit status --
        conditions = conditions_for_user(cn, uid)
        check(
            len(conditions) == 2,
            f"both of this person's conditions are read, got {len(conditions)}",
        )
        limit_status = status(cn, uid, conditions=conditions, day=day)
        check(not limit_status.is_empty, "there are hard daily thresholds")
        nutrients = {limit.nutrient for limit in limit_status.limits}
        check(
            nutrients == {"sodium_mg", "purine_mg"},
            f"two thresholds: sodium and purine, got {sorted(nutrients)}",
        )

        sodium_limit = limit_status.tightest_limit("sodium_mg")
        check(sodium_limit is not None, "there is a sodium ceiling")
        if sodium_limit is not None:
            approx(
                sodium_limit.threshold, 2000.0,
                "the sodium threshold is 2000 mg (WHO)",
            )
            approx(sodium_limit.eaten, expected_eaten, "the eaten part matches")
            approx(
                sodium_limit.planned, expected_planned,
                "the planned part matches",
            )
            approx(
                sodium_limit.remaining,
                2000.0 - expected_eaten - expected_planned,
                "remaining = threshold - eaten - planned",
            )

        purine_limit = limit_status.tightest_limit("purine_mg")
        check(purine_limit is not None, "there is a purine ceiling")
        if purine_limit is not None:
            approx(
                purine_limit.threshold, 400.0,
                "the purine threshold is 400 mg",
            )
            expected_purine = (
                purine["Bánh cuốn nóng"] * 0.5
                + purine["Canh chua chay"]
                + purine["Cá chiên xù"] * 2.0
                + purine["Bắp cải luộc"]
            )
            approx(
                purine_limit.used, expected_purine,
                "the purine total matches the hand-summed figure",
            )

        # -- `classify_foods` over the whole real catalogue --
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 ORDER BY f.name"
            )
            catalogue = list(cur.fetchall())

        result = classify_foods(limit_status, catalogue)
        does_not_fit = result.does_not_fit
        if sodium_limit is not None and purine_limit is not None:
            # The hand filter must handle NULL exactly as the code does: a
            # missing cell is undecidable, so it does not join this set.
            def over(row, nutrient, limit):
                value = row[nutrient]
                return value is not None and float(value) > limit.remaining

            by_hand = {
                row["id"]
                for row in catalogue
                if over(row, "sodium_mg", sodium_limit)
                or over(row, "purine_mg", purine_limit)
            }
            check(
                set(does_not_fit) == by_hand,
                f"the non-fitting set matches the hand filter "
                f"({len(does_not_fit)} vs {len(by_hand)} foods)",
            )
            # The undecidable group must match the catalogue's NULL cells.
            undecidable_by_hand = {
                row["id"]
                for row in catalogue
                if row["id"] not in by_hand
                and (row["sodium_mg"] is None or row["purine_mg"] is None)
            }
            check(
                set(result.undecidable) == undecidable_by_hand,
                f"the undecidable group matches the NULL cells "
                f"({len(result.undecidable)} vs "
                f"{len(undecidable_by_hand)} foods)",
            )
            check(
                len(result.undecidable) > 0,
                f"the real catalogue DOES have foods with missing data — "
                f"{len(result.undecidable)} of them; were this 0 the check "
                f"would be meaningless",
            )
            check(
                not any(f in result.undecidable for f in does_not_fit),
                "no food is in both groups at once",
            )
        check(
            all(
                limit.excess > 0
                for reasons in does_not_fit.values()
                for limit in reasons
            ),
            "every reason states a positive excess amount",
        )
        check(
            all(
                limit.nutrient in ("sodium_mg", "purine_mg")
                for reasons in does_not_fit.values()
                for limit in reasons
            ),
            "no reason invokes an unlimited nutrient",
        )

        # -- The data-completeness flag, on the real catalogue --
        if purine_limit is not None:
            check(
                purine_limit.has_full_data,
                "all four anchor foods have purine data, so the flag reports "
                "COMPLETE data",
            )

        # Now insert a food with NO purine figure into the diary. 248 of the
        # 318 active foods are like that, so this is the common case rather
        # than an exception — and the flag must come on.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.purine_mg IS NULL "
                "ORDER BY f.name LIMIT 1"
            )
            no_purine = cur.fetchone()
        check(
            no_purine is not None,
            "the catalogue has a food with no purine_mg",
        )
        if no_purine is not None:
            with cn.cursor() as cur:
                cur.execute(
                    "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                    "meal_type, portion_multiplier, created_at) "
                    "VALUES (UUID(), %s, %s, %s, 'snack', 1.00, NOW())",
                    (uid, no_purine["id"], day),
                )
            cn.commit()

            status2 = status(cn, uid, conditions=conditions, day=day)
            purine2 = status2.tightest_limit("purine_mg")
            check(
                purine2 is not None,
                "the purine threshold is still readable after the insert",
            )
            if purine2 is not None:
                check(
                    not purine2.has_full_data,
                    f"adding 1 food with no purine makes the flag report "
                    f"INCOMPLETE data ({no_purine['name']})",
                )
                approx(
                    float(purine2.n_missing_servings),
                    1.0,
                    "exactly 1 serving with missing purine data is counted",
                )
                approx(
                    purine2.used,
                    purine_limit.used if purine_limit else 0.0,
                    "the purine total is UNCHANGED — the missing food adds 0, "
                    "and that is precisely why the flag exists rather than "
                    "trusting the number",
                )
            sodium2 = status2.tightest_limit("sodium_mg")
            if sodium2 is not None:
                check(
                    sodium2.used
                    > (sodium_limit.used if sodium_limit else 0.0),
                    "that same food's sodium IS added — data is missing per "
                    "nutrient, not per food",
                )

        # -- The double-counting convention --
        flagged = check_double_counting(cn, uid, day)
        check(
            len(flagged) == 1,
            f"exactly 1 `eaten` slot with no diary entry is caught, got "
            f"{len(flagged)}",
        )
        check(
            bool(flagged) and flagged[0]["food_name"] == "Cá chiên xù",
            "the one caught is Cá chiên xù; Bánh cuốn nóng has a diary entry "
            "so it is skipped",
        )
    finally:
        cn.close()


def check_exclusion_reasons_sql(db: str) -> None:
    """`exclusion_reasons` must agree with `allowed_foods` — and the
    per-serving threshold branch must actually run.

    The core check is `cross_check_f1`: two hand-written SQL statements read
    the same rule set, so they can drift apart after one edit, and when they do
    the interface shows a food both in the meal plan and in the excluded list.

    What follows matters just as much: the REAL rule set currently has **no**
    hard per-serving `nutrient_limit` — every per-serving rule is soft. Which
    means the third branch of both statements has never run against real data.
    This section builds such a rule in the test database so that branch is
    exercised, including the missing-data path.
    """
    print(
        "\n7. F1 exclusion reasons — against allowed_foods, and the "
        "per-serving branch"
    )

    cn = connect(db)
    try:
        # -- Cross-check on the real rule set --
        for names, severity in (
            (["Gút"], "moderate"),
            (["Gút", "Tăng huyết áp"], "moderate"),
            (["Ăn chay"], "mild"),
            (["Dị ứng hải sản", "Gút", "Bệnh thận"], "severe"),
            (["Ăn thuần chay", "Dị ứng đậu phộng"], "severe"),
        ):
            conditions = conditions_by_name(cn, names, severity=severity)
            allowed = allowed_foods(cn, conditions=conditions)
            reasons = exclusion_reasons(cn, conditions=conditions)
            cross = cross_check_f1(cn, conditions=conditions)
            label = "+".join(names)
            check(
                not cross["unexplained"],
                f"{label}: every dropped food has a reason "
                f"({len(cross['unexplained'])} foods unexplained)",
            )
            check(
                not cross["spurious"],
                f"{label}: no food is both excluded and allowed "
                f"({len(cross['spurious'])} foods)",
            )
            check(
                len(allowed) + len(reasons) == 318,
                f"{label}: {len(allowed)} allowed + {len(reasons)} excluded "
                f"= 318",
            )

        # -- `severity_min` gates correctly --
        # Gout's `Giàu purin` rule has `severity_min = 'moderate'`.
        gout_mild = conditions_by_name(cn, ["Gút"], severity="mild")
        gout_moderate = conditions_by_name(cn, ["Gút"], severity="moderate")
        check(
            len(exclusion_reasons(cn, conditions=gout_mild)) == 0,
            "gout at MILD: no food excluded — the rule needs moderate",
        )
        check(
            len(exclusion_reasons(cn, conditions=gout_moderate)) == 91,
            "gout at MODERATE: 91 foods excluded by the Giàu purin tag",
        )

        # -- The content of a `require_tag` reason --
        vegetarian = conditions_by_name(cn, ["Ăn chay"], severity="mild")
        vegetarian_reasons = exclusion_reasons(cn, conditions=vegetarian)
        check(
            len(vegetarian_reasons) == 201,
            f"vegetarian: 201 foods excluded, got {len(vegetarian_reasons)}",
        )
        one = next(iter(vegetarian_reasons.values()))[0]
        check(
            one.rule_type == "require_tag" and one.tag == "Món chay",
            "the reason names the right rule type and the missing tag",
        )
        check(
            all(
                r.kind == "tag"
                for reasons in vegetarian_reasons.values()
                for r in reasons
            ),
            "every vegetarian reason is of kind `tag`",
        )

        # -- Foods with several reasons --
        two_conditions = conditions_by_name(
            cn, ["Dị ứng hải sản", "Gút"], severity="severe"
        )
        reasons_two = exclusion_reasons(cn, conditions=two_conditions)
        multiple = [v for v in reasons_two.values() if len(v) >= 2]
        check(
            len(multiple) > 0,
            f"some foods breach several rules at once ({len(multiple)} foods) "
            f"— naming one reason is not enough for the user to understand",
        )
        check(
            any(
                {r.condition for r in v} == {"Gút", "Dị ứng hải sản"}
                for v in multiple
            ),
            "one food names both conditions rather than merging them into one",
        )

        # -- Build a hard per-serving rule so branch 3 is exercised --
        with cn.cursor() as cur:
            cur.execute(
                "INSERT INTO condition_rules (id, condition_id, rule_type, "
                "nutrient, comparator, threshold, scope, severity_min, "
                "is_hard, note) VALUES (UUID(), 2, 'nutrient_limit', "
                "'sodium_mg', 'lte', 500.00, 'per_serving', 'mild', 1, %s)",
                (TEST_RULE_NOTE,),
            )
            cur.execute(
                "SELECT SUM(fn.sodium_mg > 500) AS over_limit, "
                "       SUM(fn.sodium_mg IS NULL) AS no_data "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1"
            )
            row = cur.fetchone()
            n_over, n_no_data = int(row["over_limit"]), int(row["no_data"])
        cn.commit()

        hypertension = conditions_by_name(
            cn, ["Tăng huyết áp"], severity="mild"
        )
        reasons_ht = exclusion_reasons(cn, conditions=hypertension)
        cross_ht = cross_check_f1(cn, conditions=hypertension)
        check(
            not cross_ht["unexplained"] and not cross_ht["spurious"],
            "with a per-serving rule the two SQL statements still agree",
        )

        kinds: dict[str, int] = {}
        for reasons in reasons_ht.values():
            for reason in reasons:
                kinds[reason.kind] = kinds.get(reason.kind, 0) + 1
        check(
            kinds.get("serving_threshold", 0) == n_over,
            f"kind `serving_threshold` counts exactly {n_over} foods over "
            f"500 mg, got {kinds.get('serving_threshold', 0)}",
        )
        check(
            kinds.get("missing_data", 0) == n_no_data,
            f"kind `missing_data` counts exactly {n_no_data} foods with no "
            f"sodium figure, got {kinds.get('missing_data', 0)}",
        )
        check(
            n_no_data > 0,
            f"the real catalogue DOES have foods with no sodium figure "
            f"({n_no_data}) — were it 0 the missing-data path would go "
            f"unchecked",
        )

        # One specific reason, with its measurement compared to the database.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sodium_mg IS NOT NULL "
                "ORDER BY fn.sodium_mg DESC LIMIT 1"
            )
            saltiest = cur.fetchone()
        reasons = reasons_ht.get(saltiest["id"], [])
        threshold_reasons = [
            r for r in reasons if r.kind == "serving_threshold"
        ]
        check(
            len(threshold_reasons) == 1,
            f"{saltiest['name']} has exactly 1 per-serving threshold reason",
        )
        if threshold_reasons:
            reason = threshold_reasons[0]
            approx(
                reason.value or 0.0, float(saltiest["sodium_mg"]),
                "the measurement matches the database",
            )
            approx(reason.threshold or 0.0, 500.0, "the threshold matches the rule")
            approx(
                reason.excess or 0.0,
                float(saltiest["sodium_mg"]) - 500.0,
                "the excess = measurement - threshold",
            )
            check(reason.comparator == "lte", "the comparison direction is kept")
            check(
                TEST_RULE_NOTE[:16] in reason.note,
                "the rule's note travels with the reason — the interface "
                "needs it to state the source of the recommendation",
            )

        # A food with no sodium figure must land in the missing-data kind, NOT
        # over-threshold.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sodium_mg IS NULL "
                "ORDER BY f.name LIMIT 1"
            )
            no_sodium = cur.fetchone()
        if no_sodium is not None:
            reasons2 = reasons_ht.get(no_sodium["id"], [])
            check(
                any(r.kind == "missing_data" for r in reasons2),
                f"{no_sodium['name']}: no sodium figure -> kind "
                f"`missing_data`",
            )
            check(
                all(r.excess is None for r in reasons2 if r.missing_data),
                "no excess amount is invented for a food with no measurement",
            )

        # Clean up the test-only rule. A check that leaves the database
        # modified makes every later check depend on run order — and section 9
        # once counted 21 rules instead of 20 for exactly this reason.
        with cn.cursor() as cur:
            cur.execute(
                "DELETE FROM condition_rules WHERE note = %s",
                (TEST_RULE_NOTE,),
            )
            n_deleted = cur.rowcount
        cn.commit()
        check(
            n_deleted == 1,
            f"the test-only rule was cleaned up, {n_deleted} row deleted",
        )
    finally:
        cn.close()


def check_soft_penalty_sql(db: str) -> None:
    """Soft constraints against the real rule set — and what they must NOT do.

    The most important invariant: a soft constraint must **never** make a food
    leave `allowed_foods`. `is_hard = 0` means a score reduction; if it
    excluded foods, the whole soft layer would lose its reason to exist and
    Step 4 would be back to having no room to manoeuvre, exactly as before the
    layer was added.
    """
    print("\n8. Soft constraints against the real rule set")
    day = date(2026, 10, 20)
    uid = "00000004-0000-0000-0000-000000000000"

    cn = connect(db)
    try:
        four_conditions = [
            "Gút", "Tăng huyết áp", "Đái tháo đường", "Rối loạn mỡ máu",
        ]
        conditions = conditions_by_name(cn, four_conditions, severity="severe")
        rules = soft_rules(cn, conditions)
        check(
            len(rules) == 7,
            f"the four conditions give 7 soft rules, got {len(rules)}",
        )

        by_scope = soft_rules_by_scope(rules)
        check(
            len(by_scope["per_serving"]) == 4,
            f"4 per-serving rules, got {len(by_scope['per_serving'])}",
        )
        check(
            len(by_scope["per_meal"]) == 1,
            f"1 per-meal rule, got {len(by_scope['per_meal'])}",
        )
        check(
            len(by_scope["per_day"]) == 2,
            f"2 per-day rules, got {len(by_scope['per_day'])}",
        )

        unenforced = unenforced_rules(rules)
        check(
            [r.scope for r in unenforced] == ["per_meal"],
            f"exactly 1 rule has no enforcing layer, got "
            f"{[r.scope for r in unenforced]}",
        )
        check(
            unenforced
            and unenforced[0].nutrient == "carbs_g"
            and unenforced[0].condition == "Đái tháo đường",
            "the unenforced rule is diabetes' carbohydrate <= 60 g per meal",
        )

        # `penalty` is a multiplier: the severe level must have the SMALLER
        # coefficient.
        sodium_rules = sorted(
            [r for r in by_scope["per_serving"] if r.nutrient == "sodium_mg"],
            key=lambda r: r.threshold,
        )
        check(
            len(sodium_rules) == 2,
            f"two per-serving sodium bands, got {len(sodium_rules)}",
        )
        if len(sodium_rules) == 2:
            tighter, looser = sodium_rules[0], sodium_rules[1]
            check(
                tighter.threshold < looser.threshold
                and tighter.penalty < looser.penalty,
                f"the tighter band ({tighter.threshold:.0f} mg) has the "
                f"smaller coefficient ({tighter.penalty} < {looser.penalty}) "
                f"— it MULTIPLIES, it is not an amount subtracted",
            )

        # -- Applied to the real catalogue --
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg, fn.fat_g "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 ORDER BY f.name"
            )
            catalogue = list(cur.fetchall())

        n_penalised = 0
        n_missing = 0
        lowest_factor = 1.0
        for row in catalogue:
            measurements = {
                "sodium_mg": row["sodium_mg"],
                "purine_mg": row["purine_mg"],
                "fat_g": row["fat_g"],
            }
            outcome = penalty(measurements, by_scope["per_serving"])
            in_range = 0.0 < outcome.factor <= 1.0
            if not in_range:
                check(
                    False,
                    f"{row['name']}: factor {outcome.factor} is outside (0, 1]",
                )
                return
            if outcome.is_penalised:
                n_penalised += 1
            if outcome.missing_data:
                n_missing += 1
            lowest_factor = min(lowest_factor, outcome.factor)

        check(True, "every factor across the 318 foods lies within (0, 1]")
        check(
            n_penalised > 0,
            f"{n_penalised} foods are penalised by a soft constraint — were "
            f"this 0 the soft layer would be doing nothing",
        )
        check(
            n_missing > 0,
            f"{n_missing} foods lack data on a nutrient with a soft rule — "
            f"not penalised, but recorded",
        )
        check(
            lowest_factor < 0.4,
            f"some food breaches several rule groups, driving the factor to "
            f"{lowest_factor:.3f} — below the harshest single group's 0.400",
        )

        # -- The invariant: soft rules do NOT exclude foods --
        gout_only = conditions_by_name(cn, ["Gút"], severity="mild")
        check(
            len(allowed_foods(cn, conditions=gout_only)) == 318,
            "gout at mild: the soft purine <= 150 mg/serving rule excludes NO "
            "food",
        )
        check(
            len(exclusion_reasons(cn, conditions=gout_only)) == 0,
            "and generates no exclusion reason either",
        )
        four_allowed = allowed_foods(cn, conditions=conditions)
        check(
            len(four_allowed) == len(allowed_foods(
                cn,
                conditions=conditions_by_name(
                    cn, ["Gút", "Tăng huyết áp"], severity="severe"
                ),
            )),
            "adding diabetes and dyslipidaemia — both soft only — does not "
            "shrink the candidate set",
        )

        # -- SOFT daily limits --
        with cn.cursor() as cur:
            cur.execute(
                "SELECT id FROM conditions WHERE name_vi = %s",
                ("Đái tháo đường",),
            )
            condition_id = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO user_conditions (id, user_id, condition_id, "
                "severity, created_at) VALUES (UUID(), %s, %s, %s, NOW())",
                (uid, condition_id, "severe"),
            )
            # A very sweet food, eaten in two servings, to go well past the
            # 25 g/day mark.
            cur.execute(
                "SELECT f.id, f.name, fn.sugar_g FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sugar_g IS NOT NULL "
                "ORDER BY fn.sugar_g DESC LIMIT 1"
            )
            sweetest = cur.fetchone()
            cur.execute(
                "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                "meal_type, portion_multiplier, created_at) "
                "VALUES (UUID(), %s, %s, %s, 'snack', 2.00, NOW())",
                (uid, sweetest["id"], day),
            )
        cn.commit()

        diabetes = conditions_for_user(cn, uid)
        limit_status = status(cn, uid, conditions=diabetes, day=day)
        check(
            len(limit_status.soft_limits()) == 1,
            f"one soft daily threshold, got {len(limit_status.soft_limits())}",
        )
        check(
            len(limit_status.hard_limits()) == 0,
            "diabetes has no HARD daily threshold",
        )

        soft = limit_status.soft_limits()[0]
        approx(soft.threshold, 25.0, "the sugar mark is 25 g/day")
        approx(
            soft.penalty or 0.0, 0.600,
            "the 0.600 penalty coefficient travels with the threshold",
        )
        approx(
            soft.eaten,
            float(sweetest["sugar_g"]) * 2,
            f"2 servings of {sweetest['name']} eaten",
        )
        check(
            soft.is_exceeded,
            f"{soft.used:.1f} g of sugar is over the 25 g mark — it goes into "
            f"`exceeded_recommendations`",
        )
        check(
            [
                limit.nutrient
                for limit in limit_status.exceeded_recommendations()
            ] == ["sugar_g"],
            "`exceeded_recommendations` names the right nutrient",
        )

        # And here is what must hold: exceeding a recommendation blocks NO food.
        result = classify_foods(limit_status, catalogue)
        check(
            result.does_not_fit == {} and result.undecidable == {},
            f"exceeding the soft sugar mark blocks no food "
            f"({len(result.does_not_fit)} blocked) — soft means a score "
            f"reduction, not a prohibition",
        )
        check(
            limit_status.tightest_limit("sugar_g") is None,
            "`tightest_limit` returns HARD thresholds only, so sugar gives "
            "None",
        )
    finally:
        cn.close()


def check_evidence_levels_sql(db: str) -> None:
    """Evidence levels against the real rule set — and the constraint that
    keeps them from being abused.

    What matters most here is not the counts but `chk_rule_evidence`: without
    it, a nutrient threshold could declare itself `definitional` and escape
    every requirement to cite a source.
    """
    print("\n9. Threshold evidence levels against the real rule set")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT evidence_level e, COUNT(*) n FROM condition_rules "
                "GROUP BY e"
            )
            counts = {d["e"]: int(d["n"]) for d in cur.fetchall()}

        check(
            sum(counts.values()) == 20,
            f"20 rules, got {sum(counts.values())}",
        )
        check(
            counts.get("definitional") == 9,
            f"9 tag rules are `definitional`, got {counts.get('definitional')}",
        )
        check(
            counts.get("published") == 3,
            f"3 thresholds taken verbatim from a source, got "
            f"{counts.get('published')}",
        )
        check(
            counts.get("derived") == 6,
            f"6 thresholds derived with assumptions, got "
            f"{counts.get('derived')}",
        )
        check(
            counts.get("unsupported") == 2,
            f"2 thresholds with no source in force, got "
            f"{counts.get('unsupported')}",
        )

        # Every tag rule must be `definitional`, and vice versa.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM condition_rules "
                "WHERE (rule_type IN ('exclude_tag','require_tag') "
                "       AND evidence_level <> 'definitional') "
                "   OR (rule_type = 'nutrient_limit' "
                "       AND evidence_level = 'definitional')"
            )
            mismatched = int(cur.fetchone()["n"])
        check(
            mismatched == 0,
            f"no rule mismatches its type and level, got {mismatched}",
        )

        # The CHECK constraint must really block, not merely document.
        with cn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE condition_rules "
                    "SET evidence_level = 'definitional' "
                    "WHERE rule_type = 'nutrient_limit' LIMIT 1"
                )
                blocked = False
            except pymysql.err.OperationalError:
                blocked = True
            except pymysql.err.IntegrityError:
                blocked = True
        cn.rollback()
        check(
            blocked,
            "`chk_rule_evidence` BLOCKS a threshold declaring itself "
            "`definitional` — without it, that would escape every "
            "source requirement",
        )

        # The three `published` thresholds must be exactly the three with a
        # source in their `note`.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT co.name_vi c, cr.nutrient, cr.threshold, cr.note "
                "FROM condition_rules cr "
                "JOIN conditions co ON co.id = cr.condition_id "
                "WHERE cr.evidence_level = 'published' "
                "ORDER BY co.name_vi, cr.nutrient"
            )
            published = list(cur.fetchall())
        # The matched substrings are the real `condition_rules.note` text.
        check(
            all(
                "WHO" in d["note"]
                or "Nhật Bản" in d["note"]
                or "KDIGO" in d["note"]
                for d in published
            ),
            "every `published` threshold names its source in `note`",
        )
        check(
            all(float(d["threshold"]) in (400.0, 2000.0) for d in published),
            "those three are purine 400 mg and sodium 2000 mg (two conditions)",
        )

        # The two `unsupported` thresholds: `note` must say why.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT cr.note FROM condition_rules cr "
                "WHERE cr.evidence_level = 'unsupported'"
            )
            unsupported = [d["note"] for d in cur.fetchall()]
        check(
            any("BỊ RÚT" in n for n in unsupported),
            "one `unsupported` threshold because it was WITHDRAWN from the "
            "guideline",
        )
        check(
            any("chưa xác minh" in n for n in unsupported),
            "the other because NOBODY has checked it — two different reasons, "
            "one way of presenting them",
        )

        # The level reaches all three classes that read it.
        conditions = conditions_by_name(
            cn, ["Gút", "Tăng huyết áp", "Rối loạn mỡ máu"], severity="severe"
        )
        reasons = exclusion_reasons(cn, conditions=conditions)
        check(
            all(
                r.evidence_level == "definitional"
                for v in reasons.values()
                for r in v
            ),
            "every current exclusion reason comes from a tag rule -> "
            "`definitional`",
        )
        rules = soft_rules(cn, conditions)
        check(
            {r.evidence_level for r in rules} == {"derived", "unsupported"},
            f"the soft rules carry two levels, got "
            f"{sorted({r.evidence_level for r in rules})}",
        )
        limit_status = status(
            cn, "nobody", conditions=conditions, day=date(2026, 11, 7)
        )
        hard = [limit for limit in limit_status.limits if limit.is_hard]
        check(
            hard and all(limit.is_citable for limit in hard),
            "every HARD daily threshold can cite a source — as it must: "
            "blocking a food requires one",
        )
        soft = [limit for limit in limit_status.limits if not limit.is_hard]
        check(
            soft and not any(limit.is_citable for limit in soft),
            "while no SOFT threshold can cite one",
        )
    finally:
        cn.close()


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", default="nutrition_rec",
        help="the source database to copy the foods from",
    )
    parser.add_argument(
        "--db", default=TEST_DATABASE, help="the test database name"
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="do not drop the test database when done",
    )
    args = parser.parse_args()

    if args.db == args.source:
        print(
            "The test database must not be the source database.",
            file=sys.stderr,
        )
        return 1

    print("End-to-end machine-learning checks")
    print("=" * 62)
    print(f"Building the test database {args.db!r} from {args.source!r}…")
    try:
        build_test_database(args.source, args.db)
    except pymysql.Error as e:
        print(f"Could not build the test database: {e}", file=sys.stderr)
        return 1

    try:
        cn = connect(args.db)
        try:
            signal_counts = build_users(cn)
        finally:
            cn.close()
        print(
            f"Built {len(signal_counts)} fake users with RANDOM labels "
            f"(see the top of this file)."
        )

        check_form_import(args.db)
        check_pipeline(args.db, signal_counts)
        check_serving(args.db, signal_counts)
        check_daily_limits_sql(args.db)
        check_exclusion_reasons_sql(args.db)
        check_soft_penalty_sql(args.db)
        check_evidence_levels_sql(args.db)
    finally:
        if args.keep:
            print(f"\nKeeping the database {args.db!r} as --keep asks.")
        else:
            drop_test_database(args.db)
            print(f"\nDropped the test database {args.db!r}.")

    print("=" * 62)
    if _failures:
        print(f"{_passed} checks passed, {len(_failures)} FAILED:")
        for x in _failures:
            print("  -", x)
        return 1
    print(f"All {_passed} checks passed.")
    print(
        "Note: every number above comes from fake data and is NOT an "
        "experimental result."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
