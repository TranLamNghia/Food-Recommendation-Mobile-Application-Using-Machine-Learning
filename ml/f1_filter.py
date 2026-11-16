# -*- coding: utf-8 -*-
"""The F1 filter — the safety layer, placed **before** any scoring.

Removes from the candidate set every food that violates a hard constraint,
no matter how much the user likes it. The rule set lives **as data** in
`condition_rules`, not hard-coded: adding a medical condition means adding
rows, not editing code.

`tools/check_f1.py` already proved the schema can express F1 in plain SQL.
This file turns that proof into a function usable by all three stages, and
adds two things the proof skipped:

**1. `severity_min` is honoured.** A rule applies only when the user's
severity reaches at least `severity_min`. `check_f1.py` takes a list of
condition names, so it cannot express severity, and therefore applies
**every** rule — stricter than reality. Ignoring this column would cut a
mildly hypertensive user exactly as hard as a severe one, and would make the
schema's `severity_min` column meaningless.

**2. Soft constraints are returned rather than dropped.** `is_hard = 0` means
**penalise** at scoring time; the food stays in the candidate set. If every
constraint were hard the candidate set would shrink until the Step 4
optimiser could not find a combination meeting the energy target — soft
constraints are the room to manoeuvre.

One thing the rules do **not** do here: hard per-day nutrient thresholds
(`scope = 'per_day'`) filter nothing at this point. A salty dish is still
valid if the day's total stays under the limit; the per-day part is enforced
by Step 4 phase 5. `daily_limit_rules` returns exactly those limits for Step 4.

A note on language. Identifiers, comments and developer-facing output in this
file are English. The **data** stays Vietnamese — condition names, tag names,
rule notes — and so do the few strings that the mobile app shows to end
users, because the product is Vietnamese. `EVIDENCE_LABELS` and
`direction_word` are product text, not developer text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: How well-founded a threshold is, from `condition_rules.evidence_level`.
#:
#: The interface uses it to choose its tone: quoting a WHO recommendation and
#: an unverified number in the same voice is dishonest. This used to live in
#: the prose of the `note` column, so filtering meant searching for the
#: string "chưa xác minh" — which breaks the first time anyone edits the
#: wording.
EVIDENCE_LEVELS = ("definitional", "published", "derived", "unsupported")

#: Which level may be quoted as a sourced recommendation.
CITABLE_EVIDENCE = frozenset({"published"})

#: Short phrase for the interface, per level. **Vietnamese on purpose**: this
#: is end-user product text, shown in a Vietnamese app.
EVIDENCE_LABELS = {
    "definitional": "quy tắc định nghĩa",
    "published": "có nguồn công bố",
    "derived": "suy ra kèm giả thiết",
    "unsupported": "không có nguồn đang hiệu lực",
}

#: Severity order. Used both in Python and in SQL via `FIELD()`.
SEVERITY_ORDER = ("mild", "moderate", "severe")


@dataclass(frozen=True)
class Condition:
    """One medical condition / allergy / diet of a user, with its severity."""

    condition_id: int
    severity: str = "moderate"
    name_vi: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            raise ValueError(
                f"severity must be one of {SEVERITY_ORDER}, got {self.severity!r}"
            )


# ── Reading one real user's conditions ────────────────────────────────


def conditions_for_user(cn, user_id: str) -> list[Condition]:
    """Read a user's `user_conditions`, with severity and condition name."""
    sql = """
        SELECT uc.condition_id, uc.severity, co.name_vi
        FROM user_conditions uc
        JOIN conditions co ON co.id = uc.condition_id
        WHERE uc.user_id = %s
        ORDER BY co.name_vi
    """
    with cn.cursor() as cur:
        cur.execute(sql, (user_id,))
        return [
            Condition(int(d["condition_id"]), d["severity"], d["name_vi"])
            for d in cur.fetchall()
        ]


def conditions_by_name(
    cn, names: Sequence[str], severity: str = "severe"
) -> list[Condition]:
    """Look conditions up by `conditions.name_vi` — used for scenario runs.

    Defaults to `severe` so that **every** rule applies, which preserves the
    behaviour of `tools/check_f1.py`: that is the strictest case, and the one
    worth testing, because if a plan can still be built there then every
    milder level can build one too.
    """
    if not names:
        return []
    placeholders = ", ".join(["%s"] * len(names))
    with cn.cursor() as cur:
        cur.execute(
            f"SELECT id, name_vi FROM conditions WHERE name_vi IN ({placeholders})",
            tuple(names),
        )
        found = {d["name_vi"]: int(d["id"]) for d in cur.fetchall()}

    missing = [n for n in names if n not in found]
    if missing:
        raise ValueError(
            "No condition in `conditions` has these names: "
            + ", ".join(repr(n) for n in missing)
        )
    return [Condition(found[n], severity, n) for n in names]


# ── The filter ────────────────────────────────────────────────────────

#: Maps `condition_rules.nutrient` -> a `food_nutrition` column. Written once
#: here rather than as a long `CASE` block inside the SQL: a new nutrient has
#: to be added in exactly one place, and forgetting to add it makes
#: `NUTRIENT_COLUMNS` raise immediately instead of yielding `NULL` and then
#: silently excluding every food.
NUTRIENT_COLUMNS = {
    "calories_kcal": "fn.calories_kcal",
    "protein_g": "fn.protein_g",
    "carbs_g": "fn.carbs_g",
    "fat_g": "fn.fat_g",
    "fiber_g": "fn.fiber_g",
    "sugar_g": "fn.sugar_g",
    "sodium_mg": "fn.sodium_mg",
    "cholesterol_mg": "fn.cholesterol_mg",
    "purine_mg": "fn.purine_mg",
    "calcium_mg": "fn.calcium_mg",
    "iron_mg": "fn.iron_mg",
    "zinc_mg": "fn.zinc_mg",
    "vitamin_a_mcg": "fn.vitamin_a_mcg",
    "vitamin_c_mg": "fn.vitamin_c_mg",
}

_NUTRIENT_CASE = (
    "CASE cr.nutrient\n"
    + "\n".join(
        f"              WHEN '{nutrient}' THEN {column}"
        for nutrient, column in NUTRIENT_COLUMNS.items()
    )
    + "\n            END"
)

#: The severity clause: a rule applies only when the user's level reaches
#: `severity_min`.
_SEVERITY_MET = (
    "FIELD(uc.severity, 'mild', 'moderate', 'severe') >= "
    "FIELD(cr.severity_min, 'mild', 'moderate', 'severe')"
)


def _conditions_cte(conditions: Sequence[Condition]) -> tuple[str, list[Any]]:
    """Build the derived table `uc(condition_id, severity)` from a Python list.

    A derived table rather than `IN (...)` so that each severity travels in
    the same row as its condition id — which is what lets the `severity_min`
    clause compare them pairwise.
    """
    parts = " UNION ALL ".join(
        ["SELECT CAST(%s AS UNSIGNED) AS condition_id, CAST(%s AS CHAR) AS severity"]
        + ["SELECT %s, %s"] * (len(conditions) - 1)
    )
    params: list[Any] = []
    for c in conditions:
        params += [c.condition_id, c.severity]
    return f"WITH uc AS ({parts})", params


def allowed_foods(
    cn,
    *,
    user_id: str | None = None,
    conditions: Sequence[Condition] = (),
    public_only: bool = False,
) -> list[dict[str, Any]]:
    """The set of foods **safe** for this user, with every hard rule applied.

    `user_id` does two different jobs here, do not conflate them:

    - **food scope** — `owner_id IS NULL OR owner_id = user_id`, that is the
      shared catalogue plus this user's own foods;
    - **condition lookup** — when `conditions` is empty, read them from
      `user_conditions`.

    `public_only=True` drops private foods entirely. Set it when building the
    training set for the global model: a private food's nutrition figures are
    self-declared, and letting them into a shared model harms every other
    user.
    """
    if not conditions and user_id is not None:
        conditions = conditions_for_user(cn, user_id)

    scope = (
        "f.owner_id IS NULL"
        if public_only
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    scope_params: list[Any] = [] if public_only else [user_id]

    select = """
SELECT f.id, f.name, f.category_id, f.dish_role, f.spice_level,
       f.popularity_score, f.owner_id
FROM foods f
WHERE f.is_active = 1
  AND {scope}
"""

    if not conditions:
        # No conditions at all: F1 reduces to the scope clause. A separate
        # branch because an empty derived table is invalid SQL.
        sql = select.format(scope=scope) + " ORDER BY f.name, f.id"
        with cn.cursor() as cur:
            cur.execute(sql, tuple(scope_params))
            return list(cur.fetchall())

    cte, cte_params = _conditions_cte(conditions)

    body = (
        select.format(scope=scope)
        + f"""
  -- (1) exclude_tag — drop foods carrying a forbidden tag
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN uc        ON uc.condition_id = cr.condition_id
        JOIN food_tags ft ON ft.tag_id = cr.tag_id
        WHERE cr.rule_type = 'exclude_tag'
          AND cr.is_hard = 1
          AND {_SEVERITY_MET}
          AND ft.food_id = f.id
      )

  -- (2) require_tag — the food must carry EVERY required tag
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN uc ON uc.condition_id = cr.condition_id
        WHERE cr.rule_type = 'require_tag'
          AND cr.is_hard = 1
          AND {_SEVERITY_MET}
          AND NOT EXISTS (
                SELECT 1 FROM food_tags ft
                WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
              )
      )

  -- (3) hard PER-SERVING nutrient_limit. Missing data EXCLUDES, because it
  --     cannot be shown to be safe — letting it through silently is the
  --     dangerous option.
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN uc ON uc.condition_id = cr.condition_id
        JOIN food_nutrition fn ON fn.food_id = f.id
        WHERE cr.rule_type = 'nutrient_limit'
          AND cr.is_hard = 1
          AND cr.scope = 'per_serving'
          AND {_SEVERITY_MET}
          AND (
            {_NUTRIENT_CASE} IS NULL
            OR (cr.comparator = 'lte' AND {_NUTRIENT_CASE} > cr.threshold)
            OR (cr.comparator = 'gte' AND {_NUTRIENT_CASE} < cr.threshold)
          )
      )
ORDER BY f.name, f.id
"""
    )

    with cn.cursor() as cur:
        cur.execute(cte + body, tuple(cte_params + scope_params))
        return list(cur.fetchall())


# ── Soft constraints and per-day limits ───────────────────────────────


def soft_rule_rows(cn, conditions: Sequence[Condition]) -> list[dict[str, Any]]:
    """The active `is_hard = 0` rules with their `penalty`, for scoring.

    F1 does **not** drop foods under these rules; it only hands them back.
    Keeping the two apart is deliberate: excluding a food is a safety
    decision, penalising it is a preference decision, and mixing them makes
    it impossible to untangle when explaining why a food was dropped.
    """
    if not conditions:
        return []
    cte, params = _conditions_cte(conditions)
    sql = (
        cte
        + f"""
SELECT co.name_vi, cr.rule_type, cr.tag_id, t.name_vi AS tag_name,
       cr.nutrient, cr.comparator, cr.threshold, cr.scope, cr.penalty,
       cr.severity_min, cr.evidence_level, cr.note
FROM condition_rules cr
JOIN uc         ON uc.condition_id = cr.condition_id
JOIN conditions co ON co.id = cr.condition_id
LEFT JOIN tags  t  ON t.id = cr.tag_id
WHERE cr.is_hard = 0
  AND {_SEVERITY_MET}
ORDER BY co.name_vi, cr.rule_type, cr.nutrient
"""
    )
    with cn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return list(cur.fetchall())


def daily_limit_rules(
    cn,
    conditions: Sequence[Condition],
    *,
    hard_only: bool = True,
) -> list[dict[str, Any]]:
    """**Per-day** nutrient thresholds — the input to Step 4 phase 5.

    Filters no foods: a salty dish is still valid if the day's total stays
    under the limit. An earlier version put hard thresholds on each serving,
    and a 600 mg sodium limit excluded 58 of 60 foods, leaving Step 4 unable
    to build a plan at all.

    `hard_only=True` (the default, preserving the old behaviour) returns only
    hard thresholds — the ones that **block**. `hard_only=False` also returns
    per-day soft thresholds, which only **penalise**. The caller must be able
    to tell them apart, so every row carries `is_hard` and `penalty`; merging
    them would turn a recommendation into a prohibition.
    """
    if not conditions:
        return []
    cte, params = _conditions_cte(conditions)
    hard_clause = "  AND cr.is_hard = 1\n" if hard_only else ""
    sql = (
        cte
        + f"""
SELECT co.name_vi, cr.nutrient, cr.comparator, cr.threshold,
       cr.is_hard, cr.penalty, cr.severity_min, cr.evidence_level, cr.note
FROM condition_rules cr
JOIN uc         ON uc.condition_id = cr.condition_id
JOIN conditions co ON co.id = cr.condition_id
WHERE cr.rule_type = 'nutrient_limit'
{hard_clause}  AND cr.scope = 'per_day'
  AND {_SEVERITY_MET}
ORDER BY cr.is_hard DESC, co.name_vi, cr.nutrient
"""
    )
    with cn.cursor() as cur:
        cur.execute(sql, tuple(params))
        return list(cur.fetchall())


# ── Soft constraints, typed ────────────────────────────────────────────
#
# `soft_rule_rows` returns raw rows. It stays as it is because `main()` uses
# it, while `SoftRule` is the form the scoring step consumes: typed, with a
# `scope` that must be considered, and no way for a rule to stray outside
# its scope.


@dataclass(frozen=True)
class SoftRule:
    """A soft constraint: exceeding it **penalises**, it does not exclude."""

    condition: str
    severity_min: str
    nutrient: str
    comparator: str
    threshold: float
    #: A **multiplier**, not an amount to subtract. See `scoring.penalty`.
    penalty: float
    scope: str
    note: str = ""
    evidence_level: str = "derived"

    @property
    def is_citable(self) -> bool:
        """Whether this threshold may be quoted as a sourced recommendation."""
        return self.evidence_level in CITABLE_EVIDENCE

    @property
    def evidence_label(self) -> str:
        return EVIDENCE_LABELS.get(self.evidence_level, self.evidence_level)

    def is_violated(self, value: float) -> bool:
        if self.comparator == "lte":
            return value > self.threshold
        return value < self.threshold

    @property
    def direction_word(self) -> str:
        """Which way the threshold runs, so the interface can pick its wording.

        Vietnamese on purpose: this is end-user product text.
        """
        return "vượt" if self.comparator == "lte" else "thiếu"


def soft_rules(cn, conditions: Sequence[Condition]) -> list[SoftRule]:
    """`soft_rule_rows` in typed form, restricted to `nutrient_limit` rules.

    The current rule set has no tag-based soft constraint, but the schema
    allows one. Filtering here rather than leaving the scoring step to guess:
    a soft tag rule has no `nutrient`, so every numeric comparison against it
    is meaningless.
    """
    result: list[SoftRule] = []
    for d in soft_rule_rows(cn, conditions):
        if d["rule_type"] != "nutrient_limit" or d["nutrient"] is None:
            continue
        result.append(
            SoftRule(
                condition=d["name_vi"],
                severity_min=d["severity_min"],
                nutrient=d["nutrient"],
                comparator=d["comparator"],
                threshold=float(d["threshold"]),
                penalty=float(d["penalty"]),
                scope=d["scope"],
                note=d["note"] or "",
                evidence_level=d["evidence_level"],
            )
        )
    return result


#: Which scope has an enforcing layer, and where that layer is.
#:
#: `per_meal` is `None` because **nothing enforces it**. The current rule set
#: has exactly one such rule — diabetes, carbohydrate <= 60 g per meal — and
#: it affects nothing. Stated as data so that `unenforced_rules` can report
#: it, rather than leaving it sitting in the database looking active.
ENFORCED_BY: dict[str, str | None] = {
    "per_serving": "ml/scoring.penalty",
    "per_day": "ml/daily_limits.status",
    "per_meal": None,
}


def unenforced_rules(rules: Sequence[SoftRule]) -> list[SoftRule]:
    """Soft rules whose scope has no enforcing layer.

    This list **must not** be emptied by deleting rules. It empties when, and
    only when, Step 4 takes on the `per_meal` part.
    """
    return [r for r in rules if ENFORCED_BY.get(r.scope) is None]


def soft_rules_by_scope(rules: Sequence[SoftRule]) -> dict[str, list[SoftRule]]:
    """Split soft rules by `scope`, because the three scopes need three
    different amounts of information.

        per_serving — decidable one food at a time, the scoring step does it
        per_meal    — needs the meal total, belongs to Step 4
        per_day     — needs the day's total, belongs to `ml/daily_limits.py`

    Applying a `per_meal` rule per food is wrong in both directions: it misses
    the case where the meal total is exceeded although no single food exceeds
    it, and it wrongly penalises a large food in a meal that still has room.
    So this splits them, each layer receives only what it can decide, and
    `unenforced_rules` says plainly which part nobody has taken on.
    """
    result: dict[str, list[SoftRule]] = {
        "per_serving": [],
        "per_meal": [],
        "per_day": [],
    }
    for r in rules:
        result.setdefault(r.scope, []).append(r)
    return result


# ── The inverse of F1: why a food was excluded ────────────────────────
#
# `allowed_foods` returns what survives. The interface needs the opposite —
# which food was dropped, and by which rule — and that answer CANNOT be
# derived from the surviving set: taking the complement says which foods went
# but not why.
#
# The two functions below rebuild the same three `NOT EXISTS` clauses of
# `allowed_foods` as three `UNION ALL` branches over the same rule set. The
# obvious risk is the two drifting apart after an edit, at which point the
# interface would call a food both safe and excluded. `cross_check_f1` exists
# to catch exactly that.


@dataclass(frozen=True)
class ExclusionReason:
    """One hard rule that a food violates."""

    food_id: str
    name: str
    dish_role: str
    rule_type: str
    condition: str
    severity_min: str
    tag: str | None = None
    nutrient: str | None = None
    comparator: str | None = None
    threshold: float | None = None
    #: The food's measurement. `None` means **no data**, not zero.
    value: float | None = None
    note: str = ""
    evidence_level: str = "derived"

    @property
    def is_citable(self) -> bool:
        """Whether this threshold may be quoted as a sourced recommendation."""
        return self.evidence_level in CITABLE_EVIDENCE

    @property
    def evidence_label(self) -> str:
        return EVIDENCE_LABELS.get(self.evidence_level, self.evidence_level)

    @property
    def missing_data(self) -> bool:
        """Excluded for lack of a measurement, rather than for exceeding one.

        `allowed_foods` excludes foods with no measurement at a per-serving
        threshold — what cannot be shown safe does not pass. That is the right
        call for a safety layer, but telling the user "this food exceeds the
        limit" when the truth is "we do not know" is false, so the two have to
        be separated.

        Note the opposite direction in `ml/daily_limits.py`: a missing measurement
        at a PER-SERVING threshold EXCLUDES, while at a PER-DAY limit it adds
        0 and raises a flag. Two opposite choices for one reason: per serving
        the question is "is this food safe", so not knowing means not passing;
        per day, blocking on not knowing would exclude 248 of 318 foods and
        leave the system useless.
        """
        return self.rule_type == "nutrient_limit" and self.value is None

    @property
    def kind(self) -> str:
        """The class of reason, so the interface can group them.

        - `tag`                — carries a forbidden tag, or lacks a required one
        - `serving_threshold`  — the per-serving measurement exceeds a hard limit
        - `missing_data`       — no measurement, so it does not pass
        """
        if self.rule_type in ("exclude_tag", "require_tag"):
            return "tag"
        return "missing_data" if self.missing_data else "serving_threshold"

    @property
    def excess(self) -> float | None:
        """How far past the threshold. `None` when it cannot be computed."""
        if self.value is None or self.threshold is None:
            return None
        if self.comparator == "lte":
            return self.value - self.threshold
        return self.threshold - self.value


_SELECT_REASON = """
SELECT f.id AS food_id, f.name, f.dish_role,
       {rule_type} AS rule_type,
       co.name_vi AS condition_name, cr.severity_min,
       {tag} AS tag,
       {nutrient} AS nutrient, {comparator} AS comparator,
       {threshold} AS threshold, {value} AS value,
       cr.evidence_level, cr.note
"""


def exclusion_reasons(
    cn,
    *,
    user_id: str | None = None,
    conditions: Sequence[Condition] = (),
    public_only: bool = False,
) -> dict[str, list[ExclusionReason]]:
    """Which foods F1 excluded, and under which rule.

    The parameters mirror `allowed_foods` and must be passed identically —
    same `user_id`, same `conditions`, same `public_only` — otherwise the two
    are talking about different food sets.

    Returns `{food_id: [reason, ...]}`. A food may violate several rules, and
    every violated rule is listed: one reason is not enough for the user to
    understand, because fixing one rule does not make the food acceptable.
    """
    if not conditions and user_id is not None:
        conditions = conditions_for_user(cn, user_id)
    if not conditions:
        # With no conditions, F1 excludes nothing.
        return {}

    scope = (
        "f.owner_id IS NULL"
        if public_only
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    scope_params: list[Any] = [] if public_only else [user_id]

    tag_branch = (
        _SELECT_REASON.format(
            rule_type="'exclude_tag'",
            tag="t.name_vi",
            nutrient="NULL",
            comparator="NULL",
            threshold="NULL",
            value="NULL",
        )
        + f"""
FROM foods f
JOIN food_tags       ft ON ft.food_id = f.id
JOIN condition_rules cr ON cr.tag_id = ft.tag_id
                       AND cr.rule_type = 'exclude_tag'
                       AND cr.is_hard = 1
JOIN uc                 ON uc.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
JOIN tags            t  ON t.id = cr.tag_id
WHERE f.is_active = 1
  AND {scope}
  AND {_SEVERITY_MET}
"""
    )

    required_branch = (
        _SELECT_REASON.format(
            rule_type="'require_tag'",
            tag="t.name_vi",
            nutrient="NULL",
            comparator="NULL",
            threshold="NULL",
            value="NULL",
        )
        + f"""
FROM foods f
JOIN condition_rules cr ON cr.rule_type = 'require_tag' AND cr.is_hard = 1
JOIN uc                 ON uc.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
JOIN tags            t  ON t.id = cr.tag_id
WHERE f.is_active = 1
  AND {scope}
  AND {_SEVERITY_MET}
  AND NOT EXISTS (
        SELECT 1 FROM food_tags ft
        WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
      )
"""
    )

    threshold_branch = (
        _SELECT_REASON.format(
            rule_type="'nutrient_limit'",
            tag="NULL",
            nutrient="cr.nutrient",
            comparator="cr.comparator",
            threshold="cr.threshold",
            value=_NUTRIENT_CASE,
        )
        + f"""
FROM foods f
JOIN food_nutrition  fn ON fn.food_id = f.id
JOIN condition_rules cr ON cr.rule_type = 'nutrient_limit'
                       AND cr.is_hard = 1
                       AND cr.scope = 'per_serving'
JOIN uc                 ON uc.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
WHERE f.is_active = 1
  AND {scope}
  AND {_SEVERITY_MET}
  AND (
        {_NUTRIENT_CASE} IS NULL
        OR (cr.comparator = 'lte' AND {_NUTRIENT_CASE} > cr.threshold)
        OR (cr.comparator = 'gte' AND {_NUTRIENT_CASE} < cr.threshold)
      )
"""
    )

    cte, cte_params = _conditions_cte(conditions)
    sql = (
        cte
        + tag_branch
        + "UNION ALL"
        + required_branch
        + "UNION ALL"
        + threshold_branch
        + "ORDER BY name, food_id, rule_type"
    )
    params = cte_params + scope_params + scope_params + scope_params

    with cn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = list(cur.fetchall())

    result: dict[str, list[ExclusionReason]] = {}
    for d in rows:
        result.setdefault(d["food_id"], []).append(
            ExclusionReason(
                food_id=d["food_id"],
                name=d["name"],
                dish_role=d["dish_role"],
                rule_type=d["rule_type"],
                condition=d["condition_name"],
                severity_min=d["severity_min"],
                tag=d["tag"],
                nutrient=d["nutrient"],
                comparator=d["comparator"],
                threshold=None if d["threshold"] is None else float(d["threshold"]),
                value=None if d["value"] is None else float(d["value"]),
                note=d["note"] or "",
                evidence_level=d["evidence_level"],
            )
        )
    return result


def cross_check_f1(
    cn,
    *,
    user_id: str | None = None,
    conditions: Sequence[Condition] = (),
    public_only: bool = False,
) -> dict[str, list[str]]:
    """Check `exclusion_reasons` agrees with `allowed_foods` — two queries,
    one rule set.

    `allowed_foods` and `exclusion_reasons` read the same `condition_rules`
    through two separately hand-written SQL statements. Editing one and
    forgetting the other would have the interface show a food that is both in
    the plan and on the excluded list, with nothing to report it. This
    compares the two sets:

    - `unexplained` — dropped by `allowed_foods` but `exclusion_reasons`
      offers no reason. The user sees a food vanish with no explanation.
    - `spurious`    — has an exclusion reason yet `allowed_foods` let it
      through. This direction is worse: a food considered in violation still
      reaches the meal plan.

    Both lists empty means the two agree.
    """
    surviving = {
        f["id"]
        for f in allowed_foods(
            cn,
            user_id=user_id,
            conditions=conditions,
            public_only=public_only,
        )
    }
    explained = set(
        exclusion_reasons(
            cn,
            user_id=user_id,
            conditions=conditions,
            public_only=public_only,
        )
    )

    scope = (
        "f.owner_id IS NULL"
        if public_only
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    with cn.cursor() as cur:
        cur.execute(
            f"SELECT f.id FROM foods f WHERE f.is_active = 1 AND {scope}",
            () if public_only else (user_id,),
        )
        every_food = {d["id"] for d in cur.fetchall()}

    return {
        "unexplained": sorted((every_food - surviving) - explained),
        "spurious": sorted(explained & surviving),
    }


# ── Trial run ─────────────────────────────────────────────────────────


def _count_by_role(foods: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in foods:
        counts[f["dish_role"]] = counts.get(f["dish_role"], 0) + 1
    return counts


def main() -> int:
    """Run a few scenarios, two of which differ only in severity."""
    from .db import connect, use_utf8

    use_utf8()
    cn = connect()
    try:
        everything = allowed_foods(cn)
        print(f"No conditions: {len(everything)} foods")

        scenarios = [
            ("Tăng huyết áp", ["Tăng huyết áp"]),
            ("Gút + dị ứng hải sản", ["Gút", "Dị ứng hải sản"]),
            ("Ăn chay + dị ứng đậu nành", ["Ăn chay", "Dị ứng đậu nành"]),
        ]
        for label, names in scenarios:
            for level in ("mild", "severe"):
                conds = conditions_by_name(cn, names, level)
                foods = allowed_foods(cn, conditions=conds)
                by_role = _count_by_role(foods)
                print(
                    f"{label:28} [{level:7}] {len(foods):3} foods  "
                    + " ".join(f"{k}={v}" for k, v in sorted(by_role.items()))
                )

            severe = conditions_by_name(cn, names, "severe")
            soft = soft_rule_rows(cn, severe)
            per_day = daily_limits(cn, severe)
            if soft:
                print(
                    "    soft:    "
                    + "; ".join(
                        f"{r['name_vi']}/{r['rule_type']}"
                        f"{'/' + r['nutrient'] if r['nutrient'] else ''}"
                        f" x{r['penalty']}"
                        for r in soft
                    )
                )
            if per_day:
                print(
                    "    per day: "
                    + "; ".join(
                        f"{r['name_vi']}/{r['nutrient']} "
                        f"{r['comparator']} {r['threshold']:g}"
                        for r in per_day
                    )
                )
    finally:
        cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
