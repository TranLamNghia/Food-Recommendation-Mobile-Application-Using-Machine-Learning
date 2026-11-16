import 'package:flutter/material.dart';

/// A dish — mirrors the main columns of the `foods` + `food_nutrition`
/// tables.
///
/// While the interface is being built, a dish photo is stood in for by a pair
/// of gradient colours and an icon, so the app runs entirely offline. Once
/// there are real photos, all it takes is an `imageUrl` field and a change to
/// the card's background.
class Food {
  const Food({
    required this.id,
    required this.name,
    required this.category,
    required this.dishRole,
    required this.spiceLevel,
    required this.kcal,
    required this.protein,
    required this.carb,
    required this.fat,
    required this.sugar,
    required this.sodium,
    required this.fiber,
    required this.servingSizeG,
    this.purine,
    required this.emoji,
    required this.gradient,
    this.imageAsset,
    this.tags = const [],
  });

  final String id;
  final String name;

  /// The food group — the `food_categories` table.
  final String category;

  /// The role in a meal — the `foods.dish_role` column.
  final String dishRole;

  /// Spice level 0–3 — the `foods.spice_level` column.
  final int spiceLevel;

  final int kcal;
  final double protein;
  final double carb;
  final double fat;

  /// Sugar in grams per serving. Source: `food_nutrition.sugar_g`.
  final double sugar;

  /// Sodium in milligrams per serving. Source: `food_nutrition.sodium_mg`.
  final double sodium;

  /// Fibre in grams per serving. Source: `food_nutrition.fiber_g`.
  ///
  /// It is here because **taste is not the only thing that decides the
  /// quality of a recommendation**. A user may want to eat more fibre, and if
  /// fibre is not in the feature vector then that preference cannot be
  /// represented: the recommender would only catch it indirectly, through the
  /// food group.
  ///
  /// Measured over 305 real dishes: for someone who likes high-fibre dishes,
  /// a vector without this dimension closes 41.7 % of the distance to the 20
  /// highest-fibre dishes; adding the dimension takes that to 59.7 %.
  final double fiber;

  /// Purine in milligrams per serving, **possibly absent**.
  ///
  /// The `double?` type is deliberate, and `null` is NOT 0. The food
  /// composition table only publishes purine for 70 of 318 dishes, so for the
  /// other 248 the right answer is "unknown", not "contains no purine".
  ///
  /// This field used to be left out altogether, for the reason recorded in
  /// `NutrientTarget.valueOf`: adding it while treating absence as 0 would
  /// make a plan whose purine was never checked appear to meet a gout limit —
  /// a worse kind of wrong than reporting a violation. It can be here now
  /// because [DayBudget] **counts the dishes with missing data** and says so,
  /// instead of adding them up as 0 and staying quiet.
  final double? purine;

  /// The mass of one serving, in grams. Source:
  /// `food_nutrition.serving_size_g`.
  ///
  /// Every nutrition figure above is **per serving**, not per 100 g. So this
  /// field is the mandatory denominator whenever a **concentration** is
  /// needed — see [sugarConcentration].
  final double servingSizeG;

  final String emoji;
  final List<Color> gradient;

  /// The dish photo. When `null`, the card falls back to the gradient
  /// background with an icon.
  final String? imageAsset;
  final List<String> tags;

  /// Sugar per gram of dish — a **measurable** quantity for sweetness.
  ///
  /// A **concentration** rather than a plain gram figure, for the same reason
  /// as `macroShare`: taste is about the *composition* of a dish, not about
  /// its mass. A 400 g serving holding 20 g of sugar is not as sweet as a
  /// 100 g serving holding 15 g.
  ///
  /// **Why the denominator is [servingSizeG] and not [carb].** An earlier
  /// version used `sugar / carb`, and it broke on low-carbohydrate dishes:
  /// the ratio explodes when the denominator is small. Measured over 318 real
  /// dishes, **46 of them were clamped to exactly 1.0** — 14 % of the
  /// catalogue reading as "maximally sweet" — among them *boiled egg* (0.6 g
  /// of carbohydrate) and *chive and tofu soup* (2.2 g) sitting level with
  /// *sugar banana* and *pomegranate juice*. If those cannot be told apart on
  /// this dimension then Rocchio **cannot learn a preference for sweetness**:
  /// it is a dimension full of noise, not a feature.
  ///
  /// After changing the denominator: 1 of 318 dishes at the maximum, boiled
  /// egg 0.048, chive soup 0.099, watermelon 0.374, sugar banana 0.564,
  /// pomegranate juice 1.000.
  ///
  /// Returns the **raw** concentration; the min-max normalisation is done by
  /// `FoodVectorSpace`, the same way as for sodium and fibre.
  double get sugarConcentration => servingSizeG <= 0 ? 0 : sugar / servingSizeG;

  /// The share of the energy coming from each macronutrient, used to draw the
  /// macro bar on a card.
  ({double protein, double carb, double fat}) get macroShare {
    final total = protein * 4 + carb * 4 + fat * 9;
    if (total <= 0) return (protein: 0, carb: 0, fat: 0);
    return (
      protein: protein * 4 / total,
      carb: carb * 4 / total,
      fat: fat * 9 / total,
    );
  }
}
