#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pick the food deck for a taste survey session, and print the form to fill in.

Item 10 of `ML_PIPELINE.md` §12 — the real bottleneck of the machine-learning
part. The five scripts in `ml/` already run but have produced no number at all,
because all seven signal sources are empty. The only task whose latency is
measured in weeks is **collecting data**, and it needs two things: a deck of
foods to ask about, and a way to enter the answers into the database. This file
does the first; `tools/import_swipes.py` does the second.

## How the foods are picked

`ml.survey.pick_deck` — a farthest-point traversal that covers every category
first. The reasoning, and the reason it is not a random sample, is in that
module's docstring; it moved there with the algorithm when `POST /survey-deck`
needed the same choice made the same way.

## The deck is shared; `--user` makes it personal

By default every respondent is asked about the same foods, which is what the
paragraph above is protecting. `--user` draws the deck from only the foods the
F1 filter lets that person eat, for the in-app flow where someone has already
declared their conditions.

Note what that costs, and what it does not. The decks then differ between
users — but they already did: `tools/import_swipes.py` drops a swipe on a food
the person must not eat, so the SIGNALS behind two preference vectors were
never the same set anyway. `--user` moves the removal earlier, from after the
answer to before the question, and the person stops spending swipes on foods
the system had already ruled out. What it does not change is the feature
space: that is always built from the whole catalogue, never from the filtered
subset — see the note in `main`.

## A known limitation, printed alongside the deck

The **spice level** dimension is nearly impossible to cover: 294 of the 318
foods in the catalogue are at spice level 0, so the preference vector obtained
is **weak in the spice dimension**. `ml.survey.build_deck` reports the same
thing to the API caller; see its docstring.

Run:
    python tools/make_survey_deck.py                      # 45 foods, to screen
    python tools/make_survey_deck.py --count 36 --write   # JSON + CSV form
    python tools/make_survey_deck.py --user <id> --write  # only F1-safe foods

Note on language: the printed form's instructions, its field keys and its CSV
header stay Vietnamese. They are a contract with the forms already collected in
`data/survey/da_dien/`, and with the Vietnamese-speaking people who fill them
in. The same goes for the keys of `survey_deck.json`, which
`tools/check_simulation.py` and `tools/gen_taste_vectors.py` read.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import use_utf8, connect  # noqa: E402
from ml.f1_filter import allowed_foods  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, Food, load_foods  # noqa: E402
# `pick_deck` lives in `ml/survey.py` so that this form and the in-app
# deck of §7.4.1 come from ONE implementation. Re-exported here because
# `tools/check_ml_e2e.py` imports it from this module.
from ml.survey import pick_deck  # noqa: E402,F401

SURVEY_DIR = ROOT / "data" / "survey"
DECK_JSON = SURVEY_DIR / "survey_deck.json"
FORM_CSV = SURVEY_DIR / "phieu_khao_sat.csv"

#: The four choices for one swipe, mapped to `interactions.action`. The keys
#: are what a respondent writes on the form, so they stay Vietnamese.
CHOICES = {
    "thich": "like",
    "khong_thich": "dislike",
    "binh_thuong": "neutral",
    "chua_biet": "unknown",
}


def _summary(deck: list[Food], all_foods: list[Food]) -> list[str]:
    categories: dict[str, int] = {}
    spice: dict[int, int] = {}
    roles: dict[str, int] = {}
    for food in deck:
        categories[food.category] = categories.get(food.category, 0) + 1
        spice[food.spice_level] = spice.get(food.spice_level, 0) + 1
        roles[food.dish_role] = roles.get(food.dish_role, 0) + 1

    spice_all: dict[int, int] = {}
    for food in all_foods:
        spice_all[food.spice_level] = spice_all.get(food.spice_level, 0) + 1

    lines = [
        f"{len(deck)} foods, covering {len(categories)}/"
        f"{len({f.category for f in all_foods})} categories",
        "  category: " + "  ".join(
            f"{k}={v}" for k, v in sorted(categories.items())
        ),
        "  role:     " + "  ".join(
            f"{k}={v}" for k, v in sorted(roles.items())
        ),
        "  spice:    "
        + "  ".join(f"level {k}={v}" for k, v in sorted(spice.items()))
        + "   (catalogue: "
        + " ".join(f"level {k}={v}" for k, v in sorted(spice_all.items()))
        + ")",
    ]
    if spice.get(0, 0) / len(deck) > 0.6:
        lines.append(
            f"  !  {spice.get(0, 0)}/{len(deck)} foods are at spice level 0 — "
            f"the preference vector's spice dimension will be weak. A "
            f"limitation of the data ({spice_all.get(0, 0)}/{len(all_foods)} "
            f"foods in the catalogue are not spicy)."
        )
    return lines


#: The printed form's header. Vietnamese on purpose: the people filling this in
#: are Vietnamese speakers, and the field keys are the contract with the forms
#: already collected and with `tools/import_swipes.py`.
FORM_HEADER = [
    "# PHIẾU KHẢO SÁT KHẨU VỊ",
    "#",
    "# Điền cột `lua_chon` bằng MỘT trong bốn giá trị:",
    "#     thich        — thích món này",
    "#     khong_thich  — không thích",
    "#     binh_thuong  — thấy bình thường",
    "#     chua_biet    — CHƯA TỪNG ĂN món này",
    "#",
    "# `chua_biet` khác `binh_thuong`: lượt `chua_biet` bị loại khỏi phép",
    "# tính vector sở thích, còn `binh_thuong` thì được đếm là một tín hiệu",
    "# trung tính. Chọn `binh_thuong` cho món chưa từng ăn sẽ làm loãng mọi",
    "# sở thích thật — xem ML_PIPELINE.md §5.1.",
    "#",
    "# Điền cả phần thông tin dưới đây rồi nhập bằng:",
    "#     python tools/import_swipes.py --form <tệp này>",
    "#",
    "# ho_ten: ",
    "# email: ",
    "# gioi_tinh: male            # male | female | other",
    "# ngay_sinh: 2004-01-01      # YYYY-MM-DD",
    "# chieu_cao_cm: 170",
    "# can_nang_kg: 60",
    "# muc_van_dong: moderate     # sedentary | light | moderate | active | very_active",
    "# muc_tieu: maintain         # lose_weight | maintain | gain_weight | healthy_eating",
    "# benh_ly:                   # cách nhau bằng dấu ;  để trống nếu không có",
    "#   Phải viết ĐÚNG tên tiếng Việt có dấu, chọn trong danh sách này:",
    "{benh_ly}",
    "# ngay_khao_sat: {ngay}",
    "#",
]


def write_form(deck: list[Food], path: Path,
               condition_names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        # The condition list is read STRAIGHT from the `conditions` table, not
        # typed into the instructions by hand. `import_swipes.py` looks up
        # `condition_names` by exact `conditions.name_vi`, so a hand-copied
        # list would go stale the first time anyone adds a condition to the
        # database — and the person who pays for it is the respondent, after
        # they have finished filling the form and cannot correct it.
        condition_block = "\n".join(f"#     - {x}" for x in condition_names)
        for line in FORM_HEADER:
            if line == "{benh_ly}":
                f.write(condition_block + "\n")
                continue
            f.write(line.format(ngay=date.today().isoformat()) + "\n")
        writer = csv.writer(f)
        writer.writerow(
            ["stt", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon"]
        )
        for i, food in enumerate(deck, start=1):
            writer.writerow(
                [i, food.id, food.name, food.category, food.spice_level, ""]
            )


def write_deck_json(deck: list[Food], space: FeatureSpace,
                    path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "_doc": (
                    "The taste-survey food deck, generated by "
                    "tools/make_survey_deck.py. The order is the order they "
                    "were picked: the first food is nearest the catalogue's "
                    "centroid, the later ones progressively farther."
                ),
                "feature_version": FEATURE_VERSION,
                "sinh_ngay": date.today().isoformat(),
                "n_foods": len(deck),
                "lua_chon": CHOICES,
                "mon": [
                    {
                        "thu_tu": i,
                        "id": food.id,
                        "name": food.name,
                        "category": food.category,
                        "dish_role": food.dish_role,
                        "spice_level": food.spice_level,
                        "kcal": food.kcal,
                        "vector": space.encode(food),
                    }
                    for i, food in enumerate(deck, start=1)
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    # 45, NOT 40 — for the shared PAPER form. A swipe on a food the F1 filter
    # would not let that person eat is dropped at import time (see the F1
    # filtering step in `import_swipes.py`), so someone with hard constraints
    # collects distinctly fewer signals:
    #
    #   deck size   no condition   seafood allergy   gout+hypertension
    #      40         35 ok           27                 27
    #      45         39 ok           30 ok              30 ok
    #
    # The `hybrid` threshold is 30 signals (`ml.rocchio.stage`), the first
    # level at which machine learning has a say. At a size of 40, ANYONE with
    # a hard constraint stops at 27 — exactly 3 short.
    #
    # The default has to be 45 rather than passing `--count 45` once: regene-
    # rating the form with a bare command would change the measuring
    # instrument mid-collection, and mixing two deck sizes makes respondents
    # incomparable.
    #
    # With `--user` the 5 extra foods are no longer a margin for F1 to eat:
    # the deck already holds only foods that person may eat, so all 45 survive
    # the import. 45 is kept anyway, so that a respondent on the paper form
    # and a user in the app answer the same number of questions.
    parser.add_argument("--count", type=int, default=45,
                        help="the number of foods (default 45)")
    parser.add_argument("--db", default=None)
    parser.add_argument("--write", action="store_true",
                        help="write the JSON and the CSV form")
    # The in-app path. Without it, the deck is the shared one for the paper
    # form; with it, the F1 filter runs FIRST and the deck is drawn only from
    # the foods this person may eat.
    #
    # Why that is worth a flag of its own: without it, a gout patient is
    # asked to rate pork trotters, and `import_swipes.py` then throws that
    # answer away. The person spent one of about 35 swipes on a food the
    # system had already decided they must never be served. Filtering here
    # loses nothing that was not already lost — the swipe was being dropped
    # either way — and it stops wasting the question.
    #
    # It does NOT make the paper form per-person. That form is printed once
    # and copied, and `--count` below explains why the instrument must not
    # change mid-collection.
    parser.add_argument("--user", default=None, metavar="USER_ID",
                        help="build the deck from this user's F1-safe foods")
    args = parser.parse_args()

    cn = connect(args.db)
    try:
        foods, report = load_foods(cn)
        # Read this here too, within the same open connection. The list goes
        # into the form's instructions — see `write_form`.
        with cn.cursor() as cur:
            cur.execute("SELECT name_vi FROM conditions ORDER BY id")
            condition_names = [d["name_vi"] for d in cur.fetchall()]

        # `foods` is the WHOLE catalogue and stays that way; the F1-filtered
        # subset is a separate list. Reassigning `foods` here would be a bug
        # with no symptom: `FeatureSpace.from_foods` below derives the
        # category list and every min/max from whatever it is given, so a
        # space built from one user's safe foods normalises differently and
        # may have fewer category dimensions. The vectors written into
        # `survey_deck.json` would then live in a space of their own —
        # incompatible with the trained models and with
        # `mobile/lib/data/recommender/food_vector.dart`, and nothing would
        # raise. `tools/check_feature_parity.py` exists for this class of
        # mistake.
        pool = foods
        if args.user:
            with cn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM users WHERE id = %s", (args.user,)
                )
                if cur.fetchone() is None:
                    print(f"No user {args.user}.", file=sys.stderr)
                    return 2
            safe = {d["id"] for d in allowed_foods(cn, user_id=args.user)}
            pool = [f for f in foods if f.id in safe]
    finally:
        cn.close()

    want = args.count
    if args.user:
        if not pool:
            # The same case the ML service answers `422
            # NO_SCOREABLE_CANDIDATE` for: the safety layer removed
            # everything. Refused loudly rather than printing an empty form,
            # because an empty form looks like a tooling bug and would be
            # reported as one.
            print(
                f"The F1 filter removed all {len(foods)} foods for user "
                f"{args.user} — there is nothing to ask about. Check the "
                "declared conditions and their severity.",
                file=sys.stderr,
            )
            return 1
        if len(pool) < want:
            # Fewer safe foods than the deck size. Shortened rather than
            # raising out of `pick_deck`, but SAID: this person contributes
            # fewer signals than the rest, which is exactly what decides
            # their stage in `ml.rocchio.stage`.
            print(
                f"Only {len(pool)} of {len(foods)} foods are safe for this "
                f"user, fewer than the deck size {want}. Asking about all "
                f"{len(pool)}.",
                file=sys.stderr,
            )
            want = len(pool)
        print(
            f"F1: {len(pool)}/{len(foods)} foods are safe for user "
            f"{args.user}; the deck is drawn from those."
        )

    # The space comes from the whole catalogue, the deck from `pool`. See the
    # note where `pool` is built.
    space = FeatureSpace.from_foods(foods)
    deck = pick_deck(pool, space, want)

    print()
    for line in _summary(deck, foods):
        print(line)
    print()
    print(f"{'#':>3}  {'spice':>5}  food")
    for i, food in enumerate(deck, start=1):
        print(f"{i:>3}  {food.spice_level:>5}  {food.name}  [{food.category}]")

    if not args.write:
        print(
            "\nDry run — nothing written. Add --write to produce the JSON and "
            "the CSV form."
        )
        return 0

    if args.user:
        # A per-user deck goes into the gitignored directory, NOT over the
        # shared `survey_deck.json`. Two reasons, and the second is the one
        # that matters:
        #
        # 1. `tools/check_simulation.py` and `tools/gen_taste_vectors.py`
        #    read `survey_deck.json` as the shared instrument. Overwriting it
        #    with one person's deck would silently re-point both.
        # 2. A deck keyed to a user id is MEDICAL DATA. The foods missing
        #    from it are the foods F1 removed, so the file states by omission
        #    what that person's conditions are — a diff against the shared
        #    deck reads out their diagnosis. This is a public repository, and
        #    `/data/survey/da_dien/` is in `.gitignore` for exactly this kind
        #    of file.
        out_dir = SURVEY_DIR / "da_dien"
        out_dir.mkdir(parents=True, exist_ok=True)
        deck_json = out_dir / f"survey_deck_{args.user}.json"
        form_csv = out_dir / f"phieu_khao_sat_{args.user}.csv"
    else:
        deck_json = DECK_JSON
        form_csv = FORM_CSV

    write_deck_json(deck, space, deck_json)
    write_form(deck, form_csv, condition_names)
    print(f"\nWrote {deck_json.relative_to(ROOT)}")
    print(f"Wrote {form_csv.relative_to(ROOT)}")

    if args.user:
        print(
            f"\nThis deck holds only the {len(deck)} foods user {args.user} "
            f"may eat, so the import drops none of the answers:\n"
            f"    python tools/import_swipes.py --form "
            f"{form_csv.relative_to(ROOT)}\n"
            "\nBoth files stay in data/survey/da_dien/, which .gitignore\n"
            "blocks. WHICH FOODS ARE MISSING from a per-user deck says what\n"
            "that person's medical conditions are, and this is a public\n"
            "repository."
        )
        return 0
    print(
        "\nCopy the form per respondent into data/survey/da_dien/ then "
        "import:\n"
        "    cp data/survey/phieu_khao_sat.csv "
        "data/survey/da_dien/nguoi-01.csv\n"
        "    python tools/import_swipes.py --form "
        "data/survey/da_dien/nguoi-01.csv\n"
        "\nFILLED-IN forms must stay in data/survey/da_dien/ — that directory\n"
        "is blocked by .gitignore. A filled form holds a real person's name,\n"
        "email, date of birth, weight and medical conditions, and this is a\n"
        "public repository."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
