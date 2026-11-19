# -*- coding: utf-8 -*-
"""The taste-survey deck — which foods to ask a new user about.

Specification §7.4.1 calls for "maximum diversity": a pack of 20 to 50 foods,
already past the F1 filter, chosen so that every swipe carries as much
information as possible.

    pick_deck         the pure algorithm: foods, a feature space, a count
    build_deck        the database wiring, for one user
    candidate_counts  how many foods a set of conditions would leave

## Why this file exists at all

The algorithm was written in `tools/make_survey_deck.py`, a command-line
script that prints a paper form. The in-app flow needs the same choice made
the same way, and the one thing this repository has learned the hard way is
what happens when the same arithmetic lives in two files:
`tools/check_be_parity.py` exists because three implementations of Step 1
drifted apart with nothing reporting it. So the algorithm moved here and the
script imports it. There is one implementation, and the script's `--user`
path and `POST /survey-deck` cannot disagree.

## How the foods are picked, and why not at random

Each person only swipes about 30 foods, so every swipe has to carry as much
information as possible. Rocchio builds the preference vector as a signed
mean of the food vectors, so if the deck clusters in one corner of the
feature space, every preference vector obtained also sits around that corner
— and the system cannot tell two people with different tastes apart.

The algorithm is a **farthest-point traversal** (greedy k-center): each step
adds the food whose **minimum distance to the already-picked set is
largest**. It gives a 2-approximation guarantee for the k-center problem,
and, more to the point here, it spreads the foods across the space instead of
clustering them.

Two adjustments to the plain algorithm:

**Cover every category first.** The first round picks exactly one food from
each category. Left to itself the traversal skips the categories sitting in
the middle of the space (`Cơm`, for instance) and piles up on the ones at the
edges — while a user needs to be asked about `Cơm` too, because that is what
they eat every day.

**Start from the food closest to the catalogue's centroid**, not at random. A
farthest-point traversal depends on its starting point, so a random choice
yields a different deck on every run, and two people surveyed with two
different decks have vectors that are harder to compare with each other.

## The feature space is always built from the whole catalogue

`build_deck` filters the **pool** by F1 but builds the space from every food.
Building it from the filtered subset would give each user a different space —
different min/max per dimension, different category dimensions — and then two
users' preference vectors would not be comparable, and neither would be
comparable with the model's feature rows. This is the same trap as in
`ml/plan.py`; it is why `pool` and `foods` are separate variables here.

## A known limitation, reported rather than hidden

The **spice level** dimension is nearly impossible to cover: 294 of the 318
foods in the catalogue sit at spice level 0. The traversal picks up the few
spicy ones because they sit far away, but the deck still leans heavily
towards not-spicy, so the preference vector obtained is **weak in the spice
dimension**. `DeckResult.warnings` says so on every call, in English, for the
log and the report — it is a limitation of the data, not of the algorithm.

## Note on language

Identifiers, comments and the strings in `DeckResult.warnings` are English:
they are developer-facing. Nothing here is shown to a user — the backend
reads the food ids and builds the Vietnamese response from its own tables.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from ml.f1_filter import Condition, allowed_foods
from ml.features import FeatureSpace, Food, load_foods
from ml.menu_builder import MEAL_STRUCTURE

#: The deck size range of §7.4.1, and its default. The lower bound is also
#: what `minRequired` is measured against: fewer than 20 opinionated swipes
#: and `ml.rocchio` has too little to build a direction from.
DECK_MIN = 20
DECK_MAX = 50
DECK_DEFAULT = 30


#: The roles a day's plan cannot be assembled without — the `required` of
#: every meal in `MEAL_STRUCTURE`, deduplicated. Derived rather than written
#: out, so adding a required role to a meal cannot leave this list behind.
REQUIRED_ROLES: tuple[str, ...] = tuple(sorted({
    role for shape in MEAL_STRUCTURE.values() for role in shape.required
}))


@dataclass(frozen=True)
class CandidateCounts:
    """What a set of declared conditions would leave to choose from.

    This is the answer the onboarding filter screen shows while the user is
    still answering: "318 → 228 → 116". Nothing is written, and the
    conditions are **hypothetical** — they have not been saved yet, which is
    the whole point of the screen.
    """

    #: Active foods visible to this user, before any condition applies.
    n_foods_total: int
    #: What is left after the hard rules of the conditions supplied.
    n_foods: int

    #: The remainder broken down by `dish_role`.
    #:
    #: Reported, and deliberately **not** used to refuse anything: the
    #: filtering itself goes by the hard rules alone. The breakdown is here
    #: because the total is not the number that binds. A pool of 102 foods
    #: with 2 dishes in the `side_protein` role still builds a lunch, but
    #: there is no choice left in it — the 70-30 exploration has nowhere to
    #: go, and if the user has already eaten those two today, Step 4 answers
    #: `NO_FEASIBLE_PLAN`. The screen can warn; this function only counts.
    by_role: dict[str, int]

    #: Required roles of `MEAL_STRUCTURE` that the remainder has none of.
    #: Non-empty means no plan can be assembled at all, whatever the total.
    empty_required_roles: tuple[str, ...]

    #: Whether a full-size deck can still be drawn.
    enough_for_deck: bool

    warnings: tuple[str, ...] = field(default_factory=tuple)


def candidate_counts(
    cn,
    *,
    conditions: Sequence[Condition] = (),
    user_id: str | None = None,
) -> CandidateCounts:
    """How many foods the hard rules of `conditions` would leave.

    `conditions` is what the user has ticked **so far** on the filter screen,
    not what is stored for them. An empty list therefore means no restriction
    at all, which is why `allowed_foods` is called with
    `use_saved_conditions=False`: with the default, an empty list for a user
    who already has conditions on file would silently answer with those
    instead, and the first screen of the flow would show a filtered number
    as if it were the catalogue.

    Only **hard** rules narrow this count — `exclude_tag`, `require_tag` and
    hard per-serving limits, which is exactly what F1 removes. The soft rules
    (a penalty on salty dishes for hypertension, for one) do not: they lower
    a food's score and leave it eligible, so counting them here would promise
    the user that a food is gone when the plan can still contain it.

    Two things this count cannot tell the user, and both are reported next to
    it rather than left to be discovered: a condition whose tag is on no food
    removes nothing (`Không dung nạp lactose` is in that state today), and a
    condition that has only soft or per-day rules removes nothing by design
    (hypertension, diabetes, kidney disease, dyslipidaemia).
    """
    visible = allowed_foods(
        cn, user_id=user_id, use_saved_conditions=False
    )
    remaining = allowed_foods(
        cn,
        user_id=user_id,
        conditions=conditions,
        use_saved_conditions=False,
    )

    by_role: dict[str, int] = {}
    for row in remaining:
        role = row["dish_role"]
        by_role[role] = by_role.get(role, 0) + 1

    empty = tuple(r for r in REQUIRED_ROLES if by_role.get(r, 0) == 0)

    warnings: list[str] = []
    if len(remaining) == len(visible) and conditions:
        warnings.append(
            f"The {len(conditions)} condition(s) declared remove no food at "
            "all. Either their rules are soft or per-day — which narrow a "
            "score, not the catalogue — or the tag they exclude is on no "
            "food yet."
        )
    if empty:
        warnings.append(
            "No food is left in the role(s) "
            + ", ".join(empty)
            + ", so no plan can be assembled: MEAL_STRUCTURE needs one of "
            "each for the meals that require it."
        )
    thin = sorted(
        r for r in REQUIRED_ROLES if 0 < by_role.get(r, 0) <= 2
    )
    if thin:
        warnings.append(
            "Only one or two foods remain in the role(s) "
            + ", ".join(thin)
            + ": a plan can still be built, but with no alternative to "
            "offer and nothing for the exploration mechanism to draw."
        )

    return CandidateCounts(
        n_foods_total=len(visible),
        n_foods=len(remaining),
        by_role=by_role,
        empty_required_roles=empty,
        enough_for_deck=len(remaining) >= DECK_DEFAULT,
        warnings=tuple(warnings),
    )


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Euclidean distance. Plain, because the vectors are already scaled."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def pick_deck(
    foods: list[Food], space: FeatureSpace, want: int
) -> list[Food]:
    """Farthest-point traversal, with category coverage in the first round.

    Returns the foods in **the order they were picked**: the first is the one
    closest to the catalogue's centroid, the later ones progressively
    farther. That order is useful when the form has to be shortened — taking
    the first 20 foods is still a well-spread deck.
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
            key=lambda f: (distance(vectors[f.id], group_centroid), f.name),
        )
        picked.append(best)
        remaining.pop(best.id, None)
        if len(picked) >= want:
            return picked

    # Re-sort round 1 by distance to the catalogue's centroid, so the first
    # food on the form is the most "typical" one.
    picked.sort(key=lambda f: (distance(vectors[f.id], centroid), f.name))

    # -- Round 2: the farthest-point traversal --
    nearest = {
        fid: min(distance(vectors[fid], vectors[f.id]) for f in picked)
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
            d = distance(vectors[fid], vectors[food.id])
            if d < nearest[fid]:
                nearest[fid] = d

    return picked


@dataclass(frozen=True)
class DeckResult:
    """One deck, plus what the caller has to be told about it."""

    #: The chosen foods, **in the order picked** — the order the app should
    #: show them in. Only the ids: the backend builds the user-facing fields
    #: (name, image, category label, tags) from its own tables, so there is
    #: one source of truth for what a food looks like on screen.
    food_ids: tuple[str, ...]

    #: Active foods in the catalogue, before F1.
    n_foods_before_f1: int
    #: How many of them this user may eat. `len(food_ids)` is at most this.
    n_foods_after_f1: int

    #: How many distinct categories the deck covers, out of how many exist.
    #: A deck that covers 11 of 12 is fine; one that covers 3 means the F1
    #: filter has cut the catalogue down to a corner of it, and the
    #: preference vector built from the result will be lopsided.
    n_categories: int = 0
    n_categories_total: int = 0

    warnings: tuple[str, ...] = field(default_factory=tuple)


def build_deck(
    cn, user_id: str, *, size: int = DECK_DEFAULT
) -> DeckResult:
    """Pick this user's deck: the F1-safe foods, spread across the space.

    Raises `ValueError` when `size` is outside §7.4.1's 20-50. Returns a
    `DeckResult` with an empty `food_ids` when the F1 filter leaves nothing —
    the caller decides what that means, because "this person may eat none of
    the 318 foods" is a different answer to the user than "the service is
    down", and only the caller knows which screen to show.
    """
    if not DECK_MIN <= size <= DECK_MAX:
        raise ValueError(
            f"deck size {size} is outside the {DECK_MIN}-{DECK_MAX} range of "
            "specification §7.4.1"
        )

    foods, _ = load_foods(cn)
    safe = {row["id"] for row in allowed_foods(cn, user_id=user_id)}
    # `pool` for the deck, `foods` for the space. See the note at the top.
    pool = [f for f in foods if f.id in safe]

    categories_total = len({f.category for f in foods})

    if not pool:
        return DeckResult(
            food_ids=(),
            n_foods_before_f1=len(foods),
            n_foods_after_f1=0,
            n_categories_total=categories_total,
            warnings=(
                f"The F1 filter removed all {len(foods)} active foods for "
                f"user {user_id}: there is nothing to ask about. Check the "
                "declared conditions and their severity.",
            ),
        )

    warnings: list[str] = []
    want = size
    if len(pool) < want:
        # Shortened rather than letting `pick_deck` raise, but SAID: this
        # person contributes fewer signals than the rest, and the signal
        # count is exactly what decides their stage in `ml.rocchio.stage`.
        warnings.append(
            f"Only {len(pool)} of {len(foods)} foods are safe for this user, "
            f"fewer than the requested deck size {size}. Asking about all "
            f"{len(pool)}."
        )
        want = len(pool)

    space = FeatureSpace.from_foods(foods)
    deck = pick_deck(pool, space, want)

    covered = {f.category for f in deck}
    if len(covered) < categories_total:
        missing = sorted({f.category for f in foods} - covered)
        warnings.append(
            f"The deck covers {len(covered)} of {categories_total} "
            f"categories; not represented: {', '.join(missing)}."
        )

    # Always reported, on every call. See "A known limitation" at the top:
    # it is a property of the catalogue, so it is true of every deck, and a
    # warning that only appears sometimes is one nobody learns to read.
    bland = sum(1 for f in deck if f.spice_level == 0)
    warnings.append(
        f"{bland} of {len(deck)} foods in this deck are at spice level 0, so "
        "the preference vector it produces is weak in the spice dimension. "
        "This is a limitation of the catalogue, not of the selection."
    )

    return DeckResult(
        food_ids=tuple(f.id for f in deck),
        n_foods_before_f1=len(foods),
        n_foods_after_f1=len(pool),
        n_categories=len(covered),
        n_categories_total=categories_total,
        warnings=tuple(warnings),
    )
