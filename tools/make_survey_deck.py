#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pick the food deck for a taste survey session, and print the form to fill in.

Item 10 of `ML_PIPELINE.md` §12 — the real bottleneck of the machine-learning
part. The five scripts in `ml/` already run but have produced no number at all,
because all seven signal sources are empty. The only task whose latency is
measured in weeks is **collecting data**, and it needs two things: a deck of
foods to ask about, and a way to enter the answers into the database. This file
does the first; `tools/import_swipes.py` does the second.

## How the foods are picked, and why not at random

Each person only swipes about 30-40 foods, so every swipe has to carry as much
information as possible. Rocchio builds the preference vector as a signed mean
of the food vectors, so if the deck clusters in one corner of the feature
space, every preference vector obtained also sits around that corner — and the
system cannot tell two people with different tastes apart.

The algorithm is a **farthest-point traversal** (also called greedy k-center):
each step adds the food whose **minimum distance to the already-picked set is
largest**. It gives a 2-approximation guarantee for the k-center problem, and
more importantly for this task: it spreads the foods across the space instead
of clustering them.

Two adjustments to the plain algorithm:

**Cover every category first.** The first round picks exactly one food from
each of the 12 categories. Left to itself the algorithm skips the categories
sitting in the middle of the space (`Cơm`, for instance) and piles up on the
ones at the edges — while a user needs to be asked about `Cơm` too, because
that is what they eat every day.

**Start from the food closest to the catalogue's centroid**, not at random. A
farthest-point traversal depends on its starting point, so a random choice
yields a different deck on every run, and two people surveyed with two
different decks have vectors that cannot be compared with each other.

## A known limitation, printed alongside the deck

The **spice level** dimension is nearly impossible to cover: 294 of the 318
foods in the catalogue are at spice level 0. The algorithm will pick up all the
few spicy ones because they sit far away, but the deck still leans heavily
towards not-spicy — so the preference vector obtained will be **weak in the
spice dimension**. This is a limitation of the data, not of the algorithm, and
it has to go into the report rather than being left for the reader to discover.

Run:
    python tools/make_survey_deck.py                      # 45 foods, to screen
    python tools/make_survey_deck.py --count 36 --write   # JSON + CSV form

Note on language: the printed form's instructions, its field keys and its CSV
header stay Vietnamese. They are a contract with the forms already collected in
`data/survey/da_dien/`, and with the Vietnamese-speaking people who fill them
in. The same goes for the keys of `survey_deck.json`, which
`tools/check_mo_phong.py` and `tools/sinh_khau_vi.py` read.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import use_utf8, connect  # noqa: E402
from ml.features import FEATURE_VERSION, FeatureSpace, Food, load_foods  # noqa: E402

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


def _distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def pick_deck(
    foods: list[Food], space: FeatureSpace, want: int
) -> list[Food]:
    """Farthest-point traversal, with category coverage in the first round.

    Returns the foods in **the order they were picked**: the first is the one
    closest to the catalogue's centroid, the later ones progressively farther.
    That order is useful when the form has to be shortened — taking the first
    20 foods is still a well-spread deck.
    """
    if want < 1:
        raise ValueError("the food count must be at least 1")
    if want > len(foods):
        raise ValueError(f"only {len(foods)} foods exist, cannot pick {want}")

    vectors = {f.id: space.encode(f) for f in foods}

    # The catalogue's centroid, to have a deterministic starting point.
    centroid = [
        sum(vectors[f.id][i] for f in foods) / len(foods)
        for i in range(space.length)
    ]
    by_category: dict[str, list[Food]] = {}
    for food in foods:
        by_category.setdefault(food.category, []).append(food)

    picked: list[Food] = []
    remaining = {f.id: f for f in foods}

    # -- Round 1: one food per category, the one nearest that category's
    #    centroid.
    #
    # The nearest rather than the farthest: the goal in this round is to
    # REPRESENT the category, not to find an extreme. A category's extreme is
    # easily an unusual dish, and asking a user about an unusual dish gets
    # mostly "never eaten" answers — a swipe carrying no taste information at
    # all.
    for category in sorted(by_category):
        group = by_category[category]
        group_centroid = [
            sum(vectors[f.id][i] for f in group) / len(group)
            for i in range(space.length)
        ]
        best = min(
            group,
            key=lambda f: (_distance(vectors[f.id], group_centroid), f.name),
        )
        picked.append(best)
        remaining.pop(best.id, None)
        if len(picked) >= want:
            return picked

    # Re-sort round 1 by distance to the catalogue's centroid, so the first
    # food on the form is the most "typical" one.
    picked.sort(key=lambda f: (_distance(vectors[f.id], centroid), f.name))

    # -- Round 2: the farthest-point traversal --
    nearest = {
        fid: min(_distance(vectors[fid], vectors[f.id]) for f in picked)
        for fid in remaining
    }
    while len(picked) < want and remaining:
        # Ties broken by food name, so the result is reproducible.
        choice = max(
            remaining,
            key=lambda fid: (nearest[fid], remaining[fid].name),
        )
        food = remaining.pop(choice)
        picked.append(food)
        del nearest[choice]
        for fid in remaining:
            d = _distance(vectors[fid], vectors[food.id])
            if d < nearest[fid]:
                nearest[fid] = d

    return picked


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
    "#     python tools/import_swipes.py --phieu <tệp này>",
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
    # 45, NOT 40. A swipe on a food the F1 filter would not let that person eat
    # is dropped at import time (see the F1 filtering step in
    # `import_swipes.py`), so someone with hard constraints collects
    # distinctly fewer signals:
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
    parser.add_argument("--count", type=int, default=45,
                        help="the number of foods (default 45)")
    parser.add_argument("--db", default=None)
    parser.add_argument("--write", action="store_true",
                        help="write the JSON and the CSV form")
    args = parser.parse_args()

    cn = connect(args.db)
    try:
        foods, report = load_foods(cn)
        # Read this here too, within the same open connection. The list goes
        # into the form's instructions — see `write_form`.
        with cn.cursor() as cur:
            cur.execute("SELECT name_vi FROM conditions ORDER BY id")
            condition_names = [d["name_vi"] for d in cur.fetchall()]
    finally:
        cn.close()

    space = FeatureSpace.from_foods(foods)
    deck = pick_deck(foods, space, args.count)

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

    write_deck_json(deck, space, DECK_JSON)
    write_form(deck, FORM_CSV, condition_names)
    print(f"\nWrote {DECK_JSON.relative_to(ROOT)}")
    print(f"Wrote {FORM_CSV.relative_to(ROOT)}")
    print(
        "\nCopy the form per respondent into data/survey/da_dien/ then "
        "import:\n"
        "    cp data/survey/phieu_khao_sat.csv "
        "data/survey/da_dien/nguoi-01.csv\n"
        "    python tools/import_swipes.py --phieu "
        "data/survey/da_dien/nguoi-01.csv\n"
        "\nFILLED-IN forms must stay in data/survey/da_dien/ — that directory\n"
        "is blocked by .gitignore. A filled form holds a real person's name,\n"
        "email, date of birth, weight and medical conditions, and this is a\n"
        "public repository."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
