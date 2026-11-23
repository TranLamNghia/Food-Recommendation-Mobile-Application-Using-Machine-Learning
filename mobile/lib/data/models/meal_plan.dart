import 'food.dart';
import '../recommender/nutrient_target.dart';

/// A meal of the day — the `meal_type` enum of API specification §5.4.
///
/// [energyShare] is the meal's share of the whole day's energy, taken as the
/// midpoint of the National Institute of Nutrition's recommended ranges
/// (breakfast 25–30 %, lunch 35–40 %, dinner 25–30 %, snack 5–10 %). The four
/// shares add up to exactly 1.
///
/// Note on language: the `label` of every enum in this file is text shown on
/// screen, so it stays in Vietnamese; `code` is the value sent to the server
/// and matched against the database ENUM, so it stays too.
enum MealType {
  breakfast('breakfast', 'Bữa sáng', 0.275),
  lunch('lunch', 'Bữa trưa', 0.375),
  dinner('dinner', 'Bữa tối', 0.275),
  snack('snack', 'Bữa phụ', 0.075);

  const MealType(this.code, this.label, this.energyShare);

  final String code;
  final String label;
  final double energyShare;
}

/// The status of one dish in a meal plan — the `meal_plan_items.status`
/// column.
///
/// Each status is a **source of training signal** with its own label and
/// sample weight; see the label mapping table in `DATABASE_DESIGN.md` §7.4.
enum MealItemStatus {
  /// Just generated, the user has not touched it.
  ///
  /// Named `suggested`, not `planned`: the column is
  /// `ENUM('suggested','kept','replaced','eaten','skipped')` and MySQL would
  /// refuse the string `planned` outright. The two names drifted apart while
  /// this app had no server to send anything to.
  suggested('suggested', 'Chờ ăn'),

  /// The user looked at it and decided to keep it, before eating it — a
  /// signal of its own, weight 0.6 in §4.6, and the one value that was
  /// missing here entirely.
  kept('kept', 'Đã giữ'),

  /// The user kept it and ate it — a strong signal.
  eaten('eaten', 'Đã ăn'),

  /// The user swapped it for something else — a negative signal.
  replaced('replaced', 'Đã đổi'),

  /// Skipped, not eaten. A weak signal, because the reason may have nothing
  /// to do with taste.
  skipped('skipped', 'Bỏ qua');

  const MealItemStatus(this.code, this.label);

  final String code;
  final String label;
}

/// One serving in a meal plan.
class MealPlanItem {
  MealPlanItem({
    required this.food,
    required this.score,
    this.explorationDelta,
    this.status = MealItemStatus.suggested,
  });

  final Food food;

  /// The suitability score produced by the scoring step, in [0, 1].
  final double score;

  /// The noise amplitude δ if this is an **exploration** serving; `null`
  /// means an **exploitation** serving. Corresponds to the
  /// `meal_plan_items.exploration_delta` column.
  final double? explorationDelta;

  MealItemStatus status;

  bool get isExploration => explorationDelta != null;

  MealPlanItem copyWith({MealItemStatus? status}) => MealPlanItem(
    food: food,
    score: score,
    explorationDelta: explorationDelta,
    status: status ?? this.status,
  );
}

/// One meal of a plan, with that meal's own target.
class MealSlot {
  MealSlot({required this.type, required this.targetKcal, required this.items});

  final MealType type;

  /// This meal's own energy target, equal to `E_target × energyShare`.
  final double targetKcal;

  final List<MealPlanItem> items;

  double get actualKcal =>
      items.fold(0, (sum, i) => sum + i.food.kcal.toDouble());

  double get protein => items.fold(0, (sum, i) => sum + i.food.protein);
  double get carb => items.fold(0, (sum, i) => sum + i.food.carb);
  double get fat => items.fold(0, (sum, i) => sum + i.food.fat);

  /// The deviation from the target as a percentage. Positive means over.
  double get deviationPct =>
      targetKcal <= 0 ? 0 : (actualKcal - targetKcal) / targetKcal * 100;

  /// What is left of this meal once the skipped servings are taken out.
  ///
  /// See [DailyPlan.onPlateKcal] for why this is a second number rather than
  /// a correction to [actualKcal].
  double get onPlateKcal => items.fold(
    0,
    (sum, i) =>
        i.status == MealItemStatus.skipped ? sum : sum + i.food.kcal.toDouble(),
  );

  /// The servings the user took off this meal, and what they came to.
  Iterable<MealPlanItem> get skippedItems =>
      items.where((i) => i.status == MealItemStatus.skipped);
}

/// One day's meal plan — the `meal_plans` table together with its
/// `meal_plan_items` rows.
class DailyPlan {
  DailyPlan({
    required this.date,
    required this.targetKcal,
    required this.targetProtein,
    required this.targetCarb,
    required this.targetFat,
    required this.slots,
    required this.explorationRatio,
    this.nutrientTargets = const [],
  });

  final DateTime date;

  final double targetKcal;
  final double targetProtein;
  final double targetCarb;
  final double targetFat;

  final List<MealSlot> slots;

  /// The plan's **intended** share of exploration servings — the
  /// `meal_plans.exploration_ratio` column. Hard-capped at 50 % by the
  /// `chk_expl_ratio` constraint: if more than half the plan is a trial dish
  /// then it is no longer a personalised recommendation.
  final double explorationRatio;

  /// The day-level micronutrient constraints this plan was built under.
  ///
  /// Kept in the result rather than used and discarded, because the question
  /// "does this plan meet my sodium limit?" has to be answerable both in the
  /// interface and in the report — see [nutrientViolations].
  final List<NutrientTarget> nutrientTargets;

  List<MealPlanItem> get allItems => [for (final s in slots) ...s.items];

  double get actualKcal => slots.fold(0, (sum, s) => sum + s.actualKcal);
  double get actualProtein => slots.fold(0, (sum, s) => sum + s.protein);
  double get actualCarb => slots.fold(0, (sum, s) => sum + s.carb);
  double get actualFat => slots.fold(0, (sum, s) => sum + s.fat);

  /// The energy deviation from the target, as a percentage.
  ///
  /// The thesis proposal commits to keeping this figure within 10 %, so it is
  /// a number that has to be displayable in the interface and quotable in the
  /// report.
  double get deviationPct =>
      targetKcal <= 0 ? 0 : (actualKcal - targetKcal) / targetKcal * 100;

  bool get withinTolerance => deviationPct.abs() <= 10;

  /// The day's energy **once the skipped servings are taken out**.
  ///
  /// A second number and not a correction to [actualKcal], because the two
  /// answer different questions and both are needed:
  ///
  /// - [actualKcal] is the plan **as it was generated**. It is what the ±10 %
  ///   commitment is measured on, what the parity checks compare against the
  ///   Python and C# builders, and the only one of the two that can be
  ///   reproduced from the inputs. Subtracting a user's later skip from it
  ///   would make the guarantee unfalsifiable: a day could pass by having
  ///   enough dishes dropped.
  /// - This one is what the day now comes to, which is the figure a screen
  ///   next to a target has to show. Leaving a skipped dish in it tells the
  ///   user their lunch is 620 kcal when they removed the 320 kcal half of
  ///   it.
  ///
  /// It counts `eaten` servings as well as `suggested` ones: they are part of
  /// the day. What has actually been consumed is a third figure and comes
  /// from the diary — §7.7.5's `consumed` — not from here.
  double get onPlateKcal => slots.fold(0, (sum, s) => sum + s.onPlateKcal);

  /// How much energy the user took off the day by skipping, as a positive
  /// number. `0` when nothing was skipped, which is the usual case.
  double get skippedKcal => actualKcal - onPlateKcal;

  /// Whether the user has taken anything off the day.
  bool get hasSkipped => skippedKcal > 0;

  /// [onPlateKcal] against the target, as a percentage. Positive means over.
  ///
  /// This is the one a screen shows, because it answers the question the user
  /// is asking — *am I on target today* — and [deviationPct] stops answering
  /// it the moment they skip a dish. [deviationPct] remains the figure the
  /// ±10 % commitment is claimed on, and the two are shown side by side when
  /// they differ rather than one of them quietly standing in for the other.
  double get onPlateDeviationPct =>
      targetKcal <= 0 ? 0 : (onPlateKcal - targetKcal) / targetKcal * 100;

  bool get onPlateWithinTolerance => onPlateDeviationPct.abs() <= 10;

  /// The servings the user took off the day, across every meal.
  List<MealPlanItem> get skippedItems => [
    for (final s in slots) ...s.skippedItems,
  ];

  /// The day's total of one nutrient.
  double totalOf(String nutrient) => allItems.fold(
    0,
    (sum, i) => sum + (NutrientTarget.valueOf(i.food, nutrient) ?? 0),
  );

  /// The micronutrient constraints that are **not** satisfied, with the
  /// actual amount.
  ///
  /// Empty is good. Non-empty means phase 5 of Step 4 ran out of usable
  /// swaps — usually because the catalogue holds no dish that would close the
  /// gap, not because the algorithm gave up early. It has to be shown rather
  /// than hidden: a plan that violates a limit while looking perfectly normal
  /// is the most dangerous kind of failure for someone with a condition.
  ///
  /// Only the **enforceable** nutrients are considered — see
  /// [unenforceableTargets].
  List<({NutrientTarget target, double actual})> get nutrientViolations => [
    for (final t in nutrientTargets)
      if (NutrientTarget.supported.contains(t.nutrient) &&
          !t.isSatisfiedBy(totalOf(t.nutrient)))
        (target: t, actual: totalOf(t.nutrient)),
  ];

  /// The constraints the system **cannot enforce** because [Food] does not
  /// carry that nutrient — currently only `purine_mg`.
  ///
  /// These have to be kept apart from [nutrientViolations] rather than folded
  /// in, and must never be quietly treated as satisfied. Folded in,
  /// `atMost('purine_mg', 400)` would report **satisfied** because the total
  /// reads as 0 — a plan whose purine was never checked at all would appear
  /// to meet a gout limit. That is a worse kind of wrong than reporting a
  /// violation.
  List<NutrientTarget> get unenforceableTargets => [
    for (final t in nutrientTargets)
      if (!NutrientTarget.supported.contains(t.nutrient)) t,
  ];

  /// Every enforceable constraint is satisfied, **and** no constraint is left
  /// outside what can be enforced. The second condition is deliberately
  /// strict: do not claim "met" while something could not be checked.
  bool get meetsNutrientTargets =>
      nutrientViolations.isEmpty && unenforceableTargets.isEmpty;

  /// The share of exploration servings **actually** achieved. Much lower than
  /// [explorationRatio] means the combination step could not find enough
  /// exploration dishes that also fit the energy constraint.
  double get actualExplorationRatio {
    final items = allItems;
    if (items.isEmpty) return 0;
    return items.where((i) => i.isExploration).length / items.length;
  }
}
