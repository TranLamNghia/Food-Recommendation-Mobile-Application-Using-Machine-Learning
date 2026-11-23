// OFFLINE: the Dart copy of step 1, held in parity with ml/limits.py.
import '../models/food.dart';
import 'evidence_level.dart';

/// A nutrient's allowance for **one day**, together with how much of today's
/// has been used.
///
/// Mirrors `DailyLimit` in `ml/daily_limits.py`. It differs from
/// [NutrientTarget] in carrying **state**: a threshold is always 2 000 mg of
/// sodium, while an allowance says how much is left today — and what is left
/// depends on what the user has eaten, so it is something that has to be
/// shown before it blocks any dish. A state-dependent constraint that only
/// appears at the moment it rejects something always takes people by
/// surprise.
///
/// ## Two columns, not merged
///
/// [eaten] is already eaten — no longer changeable. [planned] is still in the
/// plan — swappable, droppable. Adding them into one number loses exactly the
/// information the user needs: when a dish does not fit, they are choosing
/// between *dropping something already planned* and *going over the limit*.
/// Shown a single total, they would assume both parts were fixed.
///
/// ## Missing data is COUNTED, not ignored
///
/// The composition table only publishes purine for 70 of 318 dishes. Adding
/// the ones with no data up as 0 and returning a normal-looking number would
/// mean a gout patient's purine ceiling is almost never reached — a safety
/// layer failing **open** with no warning. So [missingCount] travels with
/// every total, and [dataComplete] is something the interface is obliged to
/// show next to the number.
class DayLimit {
  const DayLimit({
    required this.condition,
    required this.nutrient,
    required this.unit,
    required this.amount,
    required this.eaten,
    required this.planned,
    required this.isHard,
    required this.evidence,
    this.penalty,
    this.missingCount = 0,
    this.note = '',
  });

  /// The name of the condition that sets this allowance.
  final String condition;

  /// The nutrition column's name, spelled exactly as in the database.
  final String nutrient;

  /// The unit to display — `mg`, `g`.
  final String unit;

  /// The ceiling for the whole day.
  final double amount;

  /// Already eaten — from `food_diary`. Not changeable.
  final double eaten;

  /// In today's plan but not eaten yet. Still swappable.
  final double planned;

  /// A hard limit **blocks** a dish; a soft one only **costs score**.
  ///
  /// Merging the two turns a recommendation into a prohibition: sugar
  /// ≤ 25 g/day is a recommendation, sodium ≤ 2 000 mg is a blocking
  /// threshold.
  final bool isHard;

  final EvidenceLevel evidence;

  /// The factor the score is **multiplied** by when exceeded; present only on
  /// a soft limit. Smaller is a harsher penalty — see `PenaltyOutcome`.
  final double? penalty;

  /// How many servings counted towards this allowance have **no measurement**
  /// for that nutrient.
  final int missingCount;

  /// The threshold's provenance, verbatim from `condition_rules.note`.
  final String note;

  /// The amount used — eaten plus what is in the plan.
  double get used => eaten + planned;

  /// How much more can still be eaten.
  ///
  /// **Not clamped at 0.** A negative number means the limit is already
  /// exceeded, and the interface needs to know by how much in order to say
  /// so; clamped at 0, the sentence "222 mg over" could not be written.
  double get remaining => amount - used;

  bool get exceeded => used > amount;

  /// The used amount as a fraction of the threshold, for drawing a progress
  /// bar. Not clamped.
  double get ratio => amount <= 0 ? 0 : used / amount;

  /// Every serving counted towards this allowance has a measurement.
  ///
  /// When false, [used] is lower than reality, so [remaining] is **higher**
  /// than reality — the allowance is being loosened. The interface has to say
  /// that, not show the bare number.
  bool get dataComplete => missingCount == 0;

  /// Would adding [addition] units of this nutrient stay within the limit?
  bool fits(double addition) => used + addition <= amount;

  DayLimit copyWith({double? eaten, double? planned, int? missingCount}) =>
      DayLimit(
        condition: condition,
        nutrient: nutrient,
        unit: unit,
        amount: amount,
        eaten: eaten ?? this.eaten,
        planned: planned ?? this.planned,
        isHard: isHard,
        evidence: evidence,
        penalty: penalty,
        missingCount: missingCount ?? this.missingCount,
        note: note,
      );
}

/// All of one person's daily allowances for one day.
class DayBudget {
  const DayBudget({this.limits = const []});

  final List<DayLimit> limits;

  bool get isEmpty => limits.isEmpty;

  /// The allowances that **block** a dish.
  List<DayLimit> get hard => [
    for (final l in limits)
      if (l.isHard) l,
  ];

  /// The allowances that only **cost score** — recommendations, not
  /// prohibitions.
  List<DayLimit> get soft => [
    for (final l in limits)
      if (!l.isHard) l,
  ];

  /// The **soft** allowances already exceeded. The interface says "over the
  /// recommendation", not "excluded".
  List<DayLimit> get overRecommendation => [
    for (final l in limits)
      if (!l.isHard && l.exceeded) l,
  ];

  /// The HARD allowance with the least room left for one nutrient, or `null`
  /// when there is none.
  ///
  /// It returns `null` for an empty list, because two conditions can restrict
  /// the same nutrient with two different thresholds — hypertension and
  /// kidney disease both cap sodium at 2 000 mg, but the amount used can
  /// differ when the thresholds differ.
  DayLimit? tightestHardFor(String nutrient) {
    final ceilings = [
      for (final l in limits)
        if (l.isHard && l.nutrient == nutrient) l,
    ];
    if (ceilings.isEmpty) return null;
    return ceilings.reduce((a, b) => a.remaining <= b.remaining ? a : b);
  }

  /// The amount of one nutrient in one dish, or `null` when the dish has no
  /// measurement.
  ///
  /// `null` means **unknown**, not 0 — see [Food.purine].
  static double? valueOf(Food food, String nutrient) => switch (nutrient) {
    'calories_kcal' => food.kcal.toDouble(),
    'protein_g' => food.protein,
    'carbs_g' => food.carb,
    'fat_g' => food.fat,
    'sugar_g' => food.sugar,
    'sodium_mg' => food.sodium,
    'fiber_g' => food.fiber,
    'purine_mg' => food.purine,
    _ => null,
  };

  /// Builds the allowances from the thresholds plus the two groups of dishes:
  /// already eaten and planned.
  ///
  /// Each threshold arrives carrying only its `amount`; [DayLimit.eaten],
  /// [DayLimit.planned] and [DayLimit.missingCount] are summed here so that
  /// one single place is responsible for counting what is missing.
  static DayBudget from({
    required List<DayLimit> thresholds,
    required List<Food> eaten,
    required List<Food> planned,
  }) {
    return DayBudget(
      limits: [
        for (final t in thresholds)
          t.copyWith(
            eaten: _sum(eaten, t.nutrient),
            planned: _sum(planned, t.nutrient),
            missingCount:
                _missing(eaten, t.nutrient) + _missing(planned, t.nutrient),
          ),
      ],
    );
  }

  /// A copy of the allowances with **one dish removed from the planned
  /// part**.
  ///
  /// Used when the user opens the swap sheet: the room available to a
  /// replacement is what is left plus what the old dish is taking up. Without
  /// subtracting it, every candidate is compared against a tighter allowance
  /// than the real one, and the swap sheet blocks dishes that ought to be
  /// selectable — including the very dish sitting there.
  ///
  /// A dish with no measurement subtracts 0 **and** decreases
  /// [DayLimit.missingCount] by one: it was never added to the total in the
  /// first place, so only the missing count changes.
  DayBudget withoutPlanned(Food food) => DayBudget(
    limits: [
      for (final l in limits)
        () {
          final value = valueOf(food, l.nutrient);
          return l.copyWith(
            planned: value == null ? l.planned : l.planned - value,
            missingCount: value == null
                ? (l.missingCount - 1).clamp(0, l.missingCount)
                : l.missingCount,
          );
        }(),
    ],
  );

  static double _sum(List<Food> foods, String nutrient) {
    var total = 0.0;
    for (final f in foods) {
      total += valueOf(f, nutrient) ?? 0;
    }
    return total;
  }

  static int _missing(List<Food> foods, String nutrient) {
    var count = 0;
    for (final f in foods) {
      if (valueOf(f, nutrient) == null) count++;
    }
    return count;
  }
}
