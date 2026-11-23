// OFFLINE: builds the dish feature space on the device — step 3 input.
import 'dart:math' as math;

import '../models/food.dart';

/// Turns a dish into a numeric feature vector.
///
/// This is the **feature extraction** step described in the thesis proposal.
/// Each dish is reduced to a point in a many-dimensional space, so that two
/// "similar" dishes sit close together and the similarity between them can be
/// measured as an angle.
///
/// The vector is four blocks concatenated:
///
/// | Block | Dimensions | Content |
/// |---|---|---|
/// | Nutrition | 4 | the protein – carbohydrate – fat shares, and normalised energy |
/// | Sweetness | 1 | `sugarConcentration` — sugar per gram of dish, **measured** |
/// | Saltiness | 1 | min–max normalised sodium, **measured** |
/// | Fibre | 1 | min–max normalised fibre, **measured** |
/// | Spice level | 1 | `spiceLevel / 3` — **rated by whoever entered it** |
/// | Food group | n | one-hot encoded |
///
/// The food-group block **also carries the cooking method** the proposal
/// mentions: most of the system's food groups ARE a cooking method —
/// `mon_chien` is fried, `mon_nuong` is grilled, `mon_xao` is stir-fried. So
/// there is no separate one-hot block for the cooking method; see the note on
/// `length`.
///
/// The three macro dimensions already lie in [0, 1] and add up to 1, so they
/// need no further normalisation. Energy, though, is in kcal with a range in
/// the hundreds; left as it is, it would swamp every other dimension in a
/// distance calculation — so it has to be brought into [0, 1] by min-max over
/// the dish set itself.
///
/// Note on language: the strings in [labels] are data shared with
/// `ml/features.py`'s `FIXED_LABELS`, and `food_vector_parity_test.dart`
/// compares them dimension by dimension, so they stay in Vietnamese.
class FoodVectorSpace {
  FoodVectorSpace._({
    required this.categories,
    required this.minKcal,
    required this.maxKcal,
    required this.minSugar,
    required this.maxSugar,
    required this.minSodium,
    required this.maxSodium,
    required this.minFiber,
    required this.maxFiber,
  });

  /// Builds the feature space from a set of dishes.
  ///
  /// The catalogue and the cooking methods are **inferred from the data**
  /// rather than listed by hand, so the vector grows by itself as the dish
  /// set grows. Both are sorted so the dimension order is stable between
  /// runs — if the order followed iteration order, a vector stored on one run
  /// could no longer be compared with a vector built on the next.
  factory FoodVectorSpace.fromFoods(List<Food> foods) {
    final categories = foods.map((f) => f.category).toSet().toList()..sort();

    var minKcal = double.infinity;
    var maxKcal = double.negativeInfinity;
    var minSugar = double.infinity;
    var maxSugar = double.negativeInfinity;
    var minSodium = double.infinity;
    var maxSodium = double.negativeInfinity;
    var minFiber = double.infinity;
    var maxFiber = double.negativeInfinity;
    for (final f in foods) {
      final k = f.kcal.toDouble();
      if (k < minKcal) minKcal = k;
      if (k > maxKcal) maxKcal = k;
      final sg = f.sugarConcentration;
      if (sg < minSugar) minSugar = sg;
      if (sg > maxSugar) maxSugar = sg;
      if (f.sodium < minSodium) minSodium = f.sodium;
      if (f.sodium > maxSodium) maxSodium = f.sodium;
      if (f.fiber < minFiber) minFiber = f.fiber;
      if (f.fiber > maxFiber) maxFiber = f.fiber;
    }

    return FoodVectorSpace._(
      categories: categories,
      minKcal: minKcal,
      maxKcal: maxKcal,
      minSugar: minSugar,
      maxSugar: maxSugar,
      minSodium: minSodium,
      maxSodium: maxSodium,
      minFiber: minFiber,
      maxFiber: maxFiber,
    );
  }

  final List<String> categories;
  final double minKcal;
  final double maxKcal;

  /// The sugar-concentration bounds (g of sugar per g of dish) — see
  /// `Food.sugarConcentration`.
  final double minSugar;
  final double maxSugar;
  final double minSodium;
  final double maxSodium;
  final double minFiber;
  final double maxFiber;

  /// The dimension count: 4 nutrition + 1 sweet + 1 salty + 1 fibre + 1 spice
  /// + the group one-hot.
  ///
  /// Sweetness and saltiness come from `sugar_g` and `sodium_mg` — two
  /// quantities that are **in the food composition table**, unlike the spice
  /// level, which is a subjective rating by whoever entered the data. There
  /// is no dimension for sourness or bitterness because no source publishes
  /// them; adding a numeric column for them would manufacture false
  /// precision.
  ///
  /// There is no separate one-hot block for the cooking method, but **that
  /// signal is not lost** — the food group already carries it (a dish in the
  /// `Món chiên` group is fried), so the two one-hot blocks would be almost
  /// identical.
  ///
  /// More importantly, two independent axes would let the data contradict
  /// itself: instant noodles in broth and dry stir-fried instant noodles are
  /// two different dishes with different nutrition, not one dish with two
  /// cooking methods. Kept apart, nothing would stop a dish in the `Món nước`
  /// group from carrying the cooking method `xao`.
  ///
  /// Why there is a fibre dimension. Taste is not the only thing that decides
  /// the quality of a recommendation: a user may **want to eat more fibre**.
  /// Without this dimension that preference cannot be represented in the
  /// Rocchio preference vector, and the recommender would only catch it
  /// indirectly through the food group.
  ///
  /// Measured over 305 real dishes, simulating a user who likes the 10
  /// highest-fibre dishes and then scoring the rest by cosine:
  ///
  /// | Vector | Mean fibre of the top 20 |
  /// |---|---|
  /// | The whole catalogue | 1.75 g |
  /// | Without the fibre dimension | 2.97 g — 41.7 % of the gap closed |
  /// | With the fibre dimension | 3.50 g — 59.7 % closed |
  /// | The ideal reference (the 20 highest-fibre dishes) | 4.67 g |
  ///
  /// A note on scope: this dimension serves a preference **inferred from
  /// behaviour**. A goal the user states themselves — "I need 25 g of fibre a
  /// day" — is a **per-day** quantity and belongs to Step 4, not to the angle
  /// measurement here.
  int get length => 8 + categories.length;

  /// Each dimension's label, used when the recommendation has to be
  /// explained.
  List<String> get labels => [
    'Tỷ lệ đạm',
    'Tỷ lệ bột đường',
    'Tỷ lệ béo',
    'Năng lượng',
    'Vị ngọt',
    'Vị mặn',
    'Chất xơ',
    'Mức cay',
    ...categories.map((c) => 'Nhóm: $c'),
  ];

  /// The dimension matching a single nutrient, or `null` when that nutrient
  /// has no dimension of its own.
  ///
  /// Used when the user **states a goal** — "I want to eat more fibre" — to
  /// embed that goal straight into the preference vector; see
  /// `PreferenceProfile.withNutrientGoals`.
  ///
  /// It looks up by **label** rather than returning a hard-coded index: the
  /// label and the dimension always travel together, so inserting another
  /// dimension in the middle cannot make this function point at the wrong
  /// one.
  ///
  /// Only three nutrients are here. The three macro dimensions are
  /// **deliberately** absent, because they are **shares that add up to 1**:
  /// pushing the protein share up necessarily pushes the carbohydrate and fat
  /// shares down, which is not the same thing as "I want to eat more
  /// protein". A goal about the amount of protein belongs to the per-day
  /// allowance at Step 4.
  int? dimensionOfNutrient(String nutrient) {
    const labelOf = {
      'sugar_g': 'Vị ngọt',
      'sodium_mg': 'Vị mặn',
      'fiber_g': 'Chất xơ',
    };
    final label = labelOf[nutrient];
    if (label == null) return null;
    final i = labels.indexOf(label);
    return i < 0 ? null : i;
  }

  List<double> encode(Food food) {
    final v = List<double>.filled(length, 0);
    final share = food.macroShare;

    v[0] = share.protein;
    v[1] = share.carb;
    v[2] = share.fat;
    v[3] = _normalizeKcal(food.kcal.toDouble());
    v[4] = _normalizeSugar(food.sugarConcentration);
    v[5] = _normalizeSodium(food.sodium);
    v[6] = _normalizeFiber(food.fiber);
    v[7] = food.spiceLevel / 3;

    final ci = categories.indexOf(food.category);
    if (ci >= 0) v[8 + ci] = 1;

    return v;
  }

  /// Min-max normalisation. When the whole set has only one energy value the
  /// denominator is 0, and 0.5 is returned so this dimension does not lean
  /// either way.
  double _normalizeKcal(double kcal) {
    final range = maxKcal - minKcal;
    if (range <= 0) return 0.5;
    return ((kcal - minKcal) / range).clamp(0.0, 1.0);
  }

  /// Normalises the sugar concentration into `[0,1]` by the dish set's
  /// min–max, the same way as sodium: "sweet" is also a relative notion
  /// within the dish set.
  double _normalizeSugar(double conc) {
    if (maxSugar <= minSugar) return 0.5;
    return ((conc - minSugar) / (maxSugar - minSugar)).clamp(0.0, 1.0);
  }

  /// Normalises sodium into `[0,1]` by the dish set's min–max.
  ///
  /// The same approach as for energy rather than a fixed threshold, because
  /// "salty" is a relative notion within the dish set at hand.
  double _normalizeSodium(double sodium) {
    if (maxSodium <= minSodium) return 0.5;
    return ((sodium - minSodium) / (maxSodium - minSodium)).clamp(0.0, 1.0);
  }

  /// Normalises fibre into `[0,1]` by the dish set's min–max, the same way as
  /// sodium: "high fibre" is also a relative notion within the dish set.
  double _normalizeFiber(double fiber) {
    if (maxFiber <= minFiber) return 0.5;
    return ((fiber - minFiber) / (maxFiber - minFiber)).clamp(0.0, 1.0);
  }
}

/// The cosine similarity between two vectors of the same length.
///
/// Returns a value in [-1, 1]. When either vector has length 0 the angle is
/// undefined — 0 is returned so that dish gets a neutral score rather than
/// breaking the division.
double cosineSimilarity(List<double> a, List<double> b) {
  assert(a.length == b.length, 'The two vectors must have the same length');

  var dot = 0.0;
  var normA = 0.0;
  var normB = 0.0;

  for (var i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA == 0 || normB == 0) return 0;
  return dot / (math.sqrt(normA) * math.sqrt(normB));
}
