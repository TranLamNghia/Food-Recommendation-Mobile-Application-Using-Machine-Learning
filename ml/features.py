# -*- coding: utf-8 -*-
"""Food feature extraction — **the Python twin of `food_vector.dart`**.

Why this file exists. The Flutter app scores foods with a feature vector
built in `mobile/lib/data/recommender/food_vector.dart`, but model training
has to run in Python. The two implementations **must produce the same
vector**: if they drift, the model learns in one space and infers in another
— a failure that never announces itself, because the model still runs and
still returns numbers. `tools/check_feature_parity.py` compares them
dimension by dimension.

Three traps hit while porting, recorded here because they are invisible in
the code itself:

1.  **`kcal` is an integer on the Dart side** (`Food.kcal` is declared `int`)
    but `DECIMAL(7,2)` in the database. It has to be rounded in exactly one
    place, and rounded **the way Dart does**: Dart's `num.round()` rounds .5
    away from zero, while Python's `round()` rounds to even — `round(2.5)`
    gives 2. Hence `floor(x + 0.5)`; see `round_kcal`.

2.  **The three macro dimensions are shares of *energy*, not of grams**:
    protein and carbohydrate times 4, fat times 9. Porting this as
    `protein / (protein+carb+fat)` yields a very plausible vector that is
    completely wrong.

3.  **Dimension order must be stable**, so the category list is always
    sorted. Dart's `List<String>.sort()` compares UTF-16 code units while
    Python's `sorted()` compares Unicode code points. The two **agree** for
    every character in the Basic Multilingual Plane, and Vietnamese text is
    entirely within it — so this is safe today. It only breaks if a category
    name ever contains an emoji.

The feature version is stamped into `ml_models.feature_version`: changing any
dimension **must** bump it, otherwise an old model gets reloaded against a
different vector and nobody finds out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable, Sequence

#: Bumped whenever the dimension set or the normalisation changes.
#:
#: v1 -> v2: the "sweetness" dimension changed from `sugar_g / carbs_g` to
#: **sugar density** `sugar_g / serving_size_g`, then min-max normalised. The
#: reasoning is in `Food.sugar_density`.
FEATURE_VERSION = "v2"

#: Spice runs 0-3 (`foods.spice_level`); divide by this to land in [0, 1].
MAX_SPICE_LEVEL = 3


# ── Food ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Food:
    """One food, coerced to exactly the types the Dart side sees.

    `imputed` lists the fields that were `NULL` in the database and have been
    **filled in** from a median. Keeping that list instead of silently
    substituting numbers is deliberate: when reporting results you have to be
    able to say how many foods carry an imputed value.
    """

    id: str
    name: str
    category: str
    dish_role: str
    spice_level: int
    kcal: int
    protein: float
    carb: float
    fat: float
    sugar: float
    sodium: float
    fiber: float
    #: Serving weight in grams (`food_nutrition.serving_size_g`). Every
    #: nutrient figure above is **per serving**, not per 100 g.
    serving_size_g: float = 100.0
    imputed: tuple[str, ...] = ()

    # Share of energy from each macronutrient — see trap 2 at the top.
    @property
    def macro_share(self) -> tuple[float, float, float]:
        total = self.protein * 4 + self.carb * 4 + self.fat * 9
        if total <= 0:
            return (0.0, 0.0, 0.0)
        return (
            self.protein * 4 / total,
            self.carb * 4 / total,
            self.fat * 9 / total,
        )

    @property
    def sugar_density(self) -> float:
        """Sugar per gram of food — the measurable stand-in for sweetness.

        Uses **density** rather than raw grams because taste is about the
        *composition* of a dish: a 400 g serving holding 20 g of sugar is not
        as sweet as a 100 g serving holding 15 g.

        **Why the denominator is serving weight, not carbohydrate.** v1 used
        `sugar_g / carbs_g`, and it broke on low-carbohydrate dishes: the
        ratio explodes when the denominator is small. Measured over the 318
        real foods, **46 of them clamped to exactly 1.000** — 14% of the
        catalogue reading as "maximally sweet" — and among them were *boiled
        egg* (0.6 g carbohydrate) and *chive and tofu soup* (2.2 g), sitting
        level with *banana* and *pomegranate juice*. When those cannot be
        told apart on this dimension, Rocchio **cannot learn a sweet
        preference**: it is a noise dimension, not a feature.

        Switching the denominator to `serving_size_g` keeps the original
        intent — still a density, still independent of portion size — but the
        denominator is a whole serving weight, so it is never anomalously
        small. After the change: 1 food of 318 at the maximum, boiled egg
        0.036, chive soup 0.074, watermelon 0.279, banana 1.000.

        Returns the **raw** density; min-max normalisation is done by
        `FeatureSpace`, the same way as sodium and fiber, because "sweet" is
        a relative notion within the catalogue at hand.
        """
        if self.serving_size_g <= 0:
            return 0.0
        return self.sugar / self.serving_size_g


def round_kcal(x: float) -> int:
    """Round energy to an integer **the way Dart's `num.round()` does**.

    Not Python's `round()`: it rounds half to even, so `round(2.5)` gives 2
    where Dart gives 3. See trap 1 at the top of the file.
    """
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp into [low, high] — the equivalent of Dart's `clamp`."""
    return low if x < low else high if x > high else x


# ── Loading foods from the database, with a quality report ───────────


@dataclass
class DataQualityReport:
    """What the data is missing or where it contradicts itself.

    Printed on every load. A handsome evaluation figure built on incomplete
    data that nobody mentions is not defensible.
    """

    n_foods: int = 0
    imputed: dict[str, int] = field(default_factory=dict)
    #: `(food name, g sugar, g carbohydrate, whether sugar was imputed)`
    sugar_over_carbs: list[tuple[str, float, float, bool]] = field(
        default_factory=list
    )
    zero_spice: int = 0

    def print_report(self) -> None:
        print(f"Loaded {self.n_foods} foods.")
        for column, n in sorted(self.imputed.items()):
            print(f"  - {column:12} {n:3} NULL -> replaced by category median")
        # More sugar than total carbohydrate is nutritionally impossible.
        # Since v2 the sweetness dimension no longer divides by `carbs_g`, so
        # these foods **no longer skew the vector** — but they still have to
        # be reported, and split into two groups, because the two groups have
        # different causes:
        #
        #   - measured — `carbs_g` is keyed to the Vietnamese food composition
        #     table while `sugar_g` is borrowed from USDA. Two measurement
        #     definitions, concentrated in fruit and juice. A data-limitation
        #     item for the report, not a code bug.
        #   - imputed  — that food's own `carbs_g` is anomalously low, so any
        #     plausible sugar figure exceeds it. This is a **data error flag
        #     on the carbohydrate column**, the place to re-check during a
        #     catalogue review.
        for group_name, keep in (
            ("measured", lambda imputed: not imputed),
            ("imputed", lambda imputed: imputed),
        ):
            rows = [t for t in self.sugar_over_carbs if keep(t[3])]
            if not rows:
                continue
            name, sugar, carb, _ = max(rows, key=lambda t: t[1] / t[2])
            print(
                f"  - {'sugar>carb':12} {len(rows):3} foods with sugar > total "
                f"carbohydrate ({group_name})"
            )
            print(f"      worst: {name} ({sugar:g} g sugar / {carb:g} g carbohydrate)")
        print(f"  - {'spice_level':12} {self.zero_spice:3} foods at spice level 0")


SQL_FOODS = """
SELECT f.id, f.name, c.name AS category, f.dish_role, f.spice_level,
       n.serving_size_g, n.calories_kcal, n.protein_g, n.carbs_g, n.fat_g,
       n.sugar_g, n.sodium_mg, n.fiber_g
FROM foods f
JOIN food_categories c ON c.id = f.category_id
JOIN food_nutrition  n ON n.food_id = f.id
WHERE (%(active_only)s = 0 OR f.is_active = 1)
ORDER BY f.name, f.id
"""

#: Columns whose `NULL`s may be imputed. `calories_kcal`, `protein_g`,
#: `carbs_g` and `fat_g` are absent because they are `NOT NULL` — a missing
#: value there is a data error, not something to guess at.
IMPUTABLE_COLUMNS = ("sugar_g", "sodium_mg", "fiber_g")

#: `sugar_g` is imputed as a **density**, not as absolute grams.
#:
#: The first implementation used the category's median grams for all three
#: columns, and the count of foods with `sugar > carbohydrate` jumped from 28
#: to 35: imputation **manufactured 7 extra self-contradictory foods**,
#: because a category's median sugar has nothing to do with the serving size
#: of the particular food that is missing one.
#:
#: The denominator must **match the denominator the sweetness dimension
#: uses**, otherwise imputation creates an artefact on that very dimension.
#: While sweetness was `sugar/carbs`, the denominator here was `carbs_g` —
#: and white rice (60 g carbohydrate) was imputed a large amount of sugar,
#: reading as 0.201 on the sweetness scale even though rice is not sweet. Now
#: that sweetness is `sugar/serving_size_g`, the denominator here is
#: `serving_size_g` too, and the artefact is gone.
#:
#: Sodium and fiber are the opposite: they enter the vector as **absolute**
#: min-max normalised values, so a median in grams is the right estimate.
IMPUTE_AS_RATIO = {"sugar_g": "serving_size_g"}


def load_foods(
    cn, *, active_only: bool = True
) -> tuple[list[Food], DataQualityReport]:
    """Load every food with its nutrition, impute missing values, report back.

    **Imputation lives here, not in `FeatureSpace`.** The reason is
    architectural: the Flutter app receives already-clean numbers over the API
    and declares its nutrition fields as non-nullable `double`, so it *cannot*
    know which value was imputed. Imputation therefore has to sit on the
    server, above the vector-building layer — and that is what keeps the two
    vector builders identical dimension for dimension.

    How: **the median of the food's own category**, falling back to the
    catalogue-wide median when the whole category has no value. Not zero: a
    food missing `sodium_mg` that is given 0 becomes the blandest item in the
    catalogue, which is to say an invented extreme. `sugar_g` is imputed as a
    ratio instead — see `IMPUTE_AS_RATIO`.
    """
    with cn.cursor() as cur:
        cur.execute(SQL_FOODS, {"active_only": 1 if active_only else 0})
        rows = cur.fetchall()

    # Per-category median, then overall median, for each imputable column.
    # For a ratio-imputed column, take the median of the ratio itself.
    median_by_category: dict[tuple[str, str], float] = {}
    median_all: dict[str, float] = {}
    for column in IMPUTABLE_COLUMNS:
        denominator = IMPUTE_AS_RATIO.get(column)
        by_category: dict[str, list[float]] = {}
        all_values: list[float] = []
        for row in rows:
            value = row[column]
            if value is None:
                continue
            if denominator is not None:
                divisor = float(row[denominator] or 0)
                if divisor <= 0:
                    continue  # ratio undefined, leave it out of the median
                x = _clamp(float(value) / divisor)
            else:
                x = float(value)
            by_category.setdefault(row["category"], []).append(x)
            all_values.append(x)
        for category, values in by_category.items():
            median_by_category[(column, category)] = float(median(values))
        median_all[column] = float(median(all_values)) if all_values else 0.0

    report = DataQualityReport(n_foods=len(rows))
    foods: list[Food] = []

    for row in rows:
        was_imputed: list[str] = []
        values: dict[str, float] = {}
        for column in IMPUTABLE_COLUMNS:
            value = row[column]
            if value is None:
                estimate = median_by_category.get(
                    (column, row["category"]), median_all[column]
                )
                denominator = IMPUTE_AS_RATIO.get(column)
                # Ratio-imputed column: multiply the median ratio by this
                # food's own denominator, so it can never exceed it.
                values[column] = (
                    estimate * float(row[denominator] or 0)
                    if denominator
                    else estimate
                )
                was_imputed.append(column)
                report.imputed[column] = report.imputed.get(column, 0) + 1
            else:
                values[column] = float(value)

        food = Food(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            dish_role=row["dish_role"],
            spice_level=int(row["spice_level"]),
            kcal=round_kcal(float(row["calories_kcal"])),
            protein=float(row["protein_g"]),
            carb=float(row["carbs_g"]),
            fat=float(row["fat_g"]),
            sugar=values["sugar_g"],
            sodium=values["sodium_mg"],
            fiber=values["fiber_g"],
            serving_size_g=float(row["serving_size_g"]),
            imputed=tuple(was_imputed),
        )
        foods.append(food)

        if food.carb > 0 and food.sugar > food.carb:
            report.sugar_over_carbs.append(
                (food.name, food.sugar, food.carb, "sugar_g" in food.imputed)
            )
        if food.spice_level == 0:
            report.zero_spice += 1

    return foods, report


# ── Feature space ────────────────────────────────────────────────────


#: Dimension labels. **The values stay Vietnamese on purpose.**
#:
#: These strings are a *contract*, not prose: they are written into
#: `ml_models.scaler_params`, they are what `feature_importance` prints, and
#: `mobile/lib/data/recommender/food_vector.dart` carries the identical list.
#: `tools/check_feature_parity.py` compares the two, so renaming them here
#: alone turns that check red. They change in the same commit as the Dart
#: side, not before.
FIXED_LABELS = (
    "Tỷ lệ đạm",
    "Tỷ lệ bột đường",
    "Tỷ lệ béo",
    "Năng lượng",
    "Vị ngọt",
    "Vị mặn",
    "Chất xơ",
    "Mức cay",
)

#: Dimensions that map to a single nutrient, used when the user **states** a
#: goal ("I want more fiber"). The three macro dimensions are deliberately
#: absent: they are shares that sum to 1, so pushing the protein share up
#: necessarily pushes the other two down — which is not the same thing as
#: "I want more protein".
NUTRIENT_LABELS = {
    "sugar_g": "Vị ngọt",
    "sodium_mg": "Vị mặn",
    "fiber_g": "Chất xơ",
}


class FeatureSpace:
    """The food -> numeric vector mapping, fixed once built.

    The dimension count is `8 + number of categories`: 4 nutrition + sweet +
    salty + fiber + spice, then a one-hot block for the category. Category
    **also carries the cooking method** — the `Fried` category is by
    definition fried — so there is no separate one-hot block for method.

    The three min-max parameters (energy, sodium, fiber) are **state of the
    space**, not of a food. They must be stored alongside the model
    (`ml_models.scaler_params`) and reloaded at inference: recomputing
    min-max over new data is a silent error that drifts scores over time.
    """

    def __init__(
        self,
        *,
        categories: Sequence[str],
        min_kcal: float,
        max_kcal: float,
        min_sugar: float,
        max_sugar: float,
        min_sodium: float,
        max_sodium: float,
        min_fiber: float,
        max_fiber: float,
    ) -> None:
        self.categories = list(categories)
        self.min_kcal = min_kcal
        self.max_kcal = max_kcal
        #: Sugar density bounds (g sugar per g of food), see
        #: `Food.sugar_density`.
        self.min_sugar = min_sugar
        self.max_sugar = max_sugar
        self.min_sodium = min_sodium
        self.max_sodium = max_sodium
        self.min_fiber = min_fiber
        self.max_fiber = max_fiber
        self._category_index = {c: i for i, c in enumerate(self.categories)}

    # ── build ──
    @classmethod
    def from_foods(cls, foods: Iterable[Food]) -> "FeatureSpace":
        items = list(foods)
        if not items:
            raise ValueError("Cannot build a feature space from an empty food set.")
        return cls(
            categories=sorted({f.category for f in items}),
            min_kcal=min(f.kcal for f in items),
            max_kcal=max(f.kcal for f in items),
            min_sugar=min(f.sugar_density for f in items),
            max_sugar=max(f.sugar_density for f in items),
            min_sodium=min(f.sodium for f in items),
            max_sodium=max(f.sodium for f in items),
            min_fiber=min(f.fiber for f in items),
            max_fiber=max(f.fiber for f in items),
        )

    # ── store / reload ──
    def params(self) -> dict[str, Any]:
        """JSON form, written into `ml_models.scaler_params`."""
        return {
            "feature_version": FEATURE_VERSION,
            "categories": list(self.categories),
            "min_kcal": self.min_kcal,
            "max_kcal": self.max_kcal,
            "min_sugar": self.min_sugar,
            "max_sugar": self.max_sugar,
            "min_sodium": self.min_sodium,
            "max_sodium": self.max_sodium,
            "min_fiber": self.min_fiber,
            "max_fiber": self.max_fiber,
        }

    @classmethod
    def from_params(cls, d: dict[str, Any]) -> "FeatureSpace":
        version = d.get("feature_version")
        if version != FEATURE_VERSION:
            raise ValueError(
                f"scaler_params belongs to feature version {version!r} but "
                f"the code is at {FEATURE_VERSION!r}. An old model cannot be "
                f"loaded against a new vector — retrain, or use the matching "
                f"code revision."
            )
        return cls(
            categories=d["categories"],
            min_kcal=d["min_kcal"],
            max_kcal=d["max_kcal"],
            min_sugar=d["min_sugar"],
            max_sugar=d["max_sugar"],
            min_sodium=d["min_sodium"],
            max_sodium=d["max_sodium"],
            min_fiber=d["min_fiber"],
            max_fiber=d["max_fiber"],
        )

    # ── description ──
    @property
    def length(self) -> int:
        return len(FIXED_LABELS) + len(self.categories)

    @property
    def labels(self) -> list[str]:
        return [*FIXED_LABELS, *(f"Nhóm: {c}" for c in self.categories)]

    def nutrient_dimension(self, nutrient: str) -> int | None:
        label = NUTRIENT_LABELS.get(nutrient)
        if label is None:
            return None
        all_labels = self.labels
        return all_labels.index(label) if label in all_labels else None

    # ── encode ──
    def encode(self, food: Food) -> list[float]:
        v = [0.0] * self.length
        protein, carb, fat = food.macro_share

        v[0] = protein
        v[1] = carb
        v[2] = fat
        v[3] = self._normalize(float(food.kcal), self.min_kcal, self.max_kcal)
        v[4] = self._normalize(food.sugar_density, self.min_sugar, self.max_sugar)
        v[5] = self._normalize(food.sodium, self.min_sodium, self.max_sodium)
        v[6] = self._normalize(food.fiber, self.min_fiber, self.max_fiber)
        v[7] = food.spice_level / MAX_SPICE_LEVEL

        i = self._category_index.get(food.category)
        if i is not None:
            v[len(FIXED_LABELS) + i] = 1.0

        return v

    @staticmethod
    def _normalize(x: float, low: float, high: float) -> float:
        """Min-max normalisation.

        When the whole set holds a single value the denominator is 0; return
        0.5 then, so this dimension contributes no bias either way. The Dart
        side does exactly the same.
        """
        if high <= low:
            return 0.5
        return _clamp((x - low) / (high - low))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, returning 0 when either vector has zero length."""
    if len(a) != len(b):
        raise ValueError(f"Vectors must have the same length: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
