// OFFLINE: per-day nutrient limits checked on the device.
import '../models/food.dart';

/// One micronutrient constraint at the **DAY** level.
///
/// It exists because every medical guideline is stated per day, not per dish.
/// The current schema already follows that principle — `condition_rules`
/// stores hard thresholds with `scope = 'per_day'` — but **Step 4 used not to
/// enforce them**: it only tracked `kcal` and the three energy-bearing
/// macronutrients. Which meant the six hard per-day thresholds of the
/// conditions were checked nowhere in the system, even though the
/// documentation said they were.
///
/// Two directions, because both are genuinely needed:
///
/// | Direction | Example | Source |
/// |---|---|---|
/// | [NutrientTarget.atMost] | sodium ≤ 2000 mg/day | WHO |
/// | [NutrientTarget.atMost] | protein ≤ 48 g/day (kidney disease) | KDIGO 2024 |
/// | [NutrientTarget.atLeast] | fibre ≥ 25 g/day | WHO 2023 |
///
/// A note on how this enters the algorithm: the constraint **repairs an
/// already-built plan**, it does not filter dishes out of the input. Hard
/// filtering on a micronutrient threshold wipes out a whole dish role — a
/// `fiber ≥ 2 g` threshold leaves the `side_protein` role with 0 dishes out
/// of 71, because meat and fish have no fibre — and then no meal can be built
/// at all. Hard filtering is for allergens and tags, not for numeric
/// thresholds.
class NutrientTarget {
  const NutrientTarget._(this.nutrient, this.amount, {required this.isFloor});

  /// A floor: the day has to reach **at least** [amount].
  const NutrientTarget.atLeast(String nutrient, double amount)
    : this._(nutrient, amount, isFloor: true);

  /// A ceiling: the day must not exceed [amount].
  const NutrientTarget.atMost(String nutrient, double amount)
    : this._(nutrient, amount, isFloor: false);

  /// The nutrition column's name, spelled exactly as in the database — see
  /// [valueOf].
  final String nutrient;

  final double amount;

  /// `true` is a floor (`gte`), `false` is a ceiling (`lte`).
  final bool isFloor;

  /// How much is short or over, expressed as a **fraction** of the threshold.
  ///
  /// It has to be a fraction rather than an absolute amount, because the
  /// algorithm has to compare the severity of nutrients measured in different
  /// units: being 5 g short of fibre and being 5 mg over on sodium are two
  /// completely different magnitudes.
  ///
  /// Returns 0 when satisfied.
  double violation(double actual) {
    if (amount <= 0) return 0;
    final short = isFloor ? amount - actual : actual - amount;
    return short <= 0 ? 0 : short / amount;
  }

  bool isSatisfiedBy(double actual) => violation(actual) == 0;

  @override
  String toString() => '$nutrient ${isFloor ? '≥' : '≤'} $amount';

  /// The value of one nutrient in one dish, or `null` when [Food] does not
  /// carry that nutrient.
  ///
  /// **`purine_mg` is deliberately absent here.** The hard rule for gout is
  /// purine ≤ 400 mg/day, but `Food` has no purine field, and the food
  /// composition table only publishes purine for 64 of 305 dishes, so adding
  /// it would cover just 21 % of the catalogue. The protection for gout
  /// therefore still rests on the `exclude_tag 'Giàu purin'` rule running at
  /// Step 2 — that tag covers 91 dishes. This is a real limitation that has
  /// to be stated in the report, not an oversight.
  static double? valueOf(Food food, String nutrient) => switch (nutrient) {
    'calories_kcal' => food.kcal.toDouble(),
    'protein_g' => food.protein,
    'carbs_g' => food.carb,
    'fat_g' => food.fat,
    'sugar_g' => food.sugar,
    'sodium_mg' => food.sodium,
    'fiber_g' => food.fiber,
    _ => null,
  };

  /// Which nutrients Step 4 can enforce at the day level.
  static const Set<String> supported = {
    'calories_kcal',
    'protein_g',
    'carbs_g',
    'fat_g',
    'sugar_g',
    'sodium_mg',
    'fiber_g',
  };
}
