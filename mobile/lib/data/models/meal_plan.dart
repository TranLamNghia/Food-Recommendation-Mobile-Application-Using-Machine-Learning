import '../api/failure.dart';
import 'food.dart';
import 'food_adapters.dart';
import 'food_brief.dart';
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
    this.id,
    this.dish,
    this.explorationDelta,
    this.status = MealItemStatus.suggested,
  });

  /// A serving built by the offline builder, which has the whole dish in
  /// hand and passes both views of it.
  MealPlanItem.offline({
    required Food dish,
    required double score,
    double? explorationDelta,
    MealItemStatus status = MealItemStatus.suggested,
  }) : this(
         food: dish.brief,
         dish: dish,
         score: score,
         explorationDelta: explorationDelta,
         status: status,
       );

  /// `meal_plan_items.id`, for the endpoints that act on one serving —
  /// §7.6.4 to §7.6.6. `null` on an offline plan, which is stored nowhere
  /// and has nothing to address.
  final String? id;

  /// What a tile draws. A **brief** and not a [Food]: §7.6.1's `items[].food`
  /// carries id, name, picture, group, role and the energy of one serving,
  /// and no macros at all — the plan's own totals are computed by the server
  /// and sent with it. Pouring that into a [Food] would mean inventing the
  /// numbers it does not carry.
  final FoodBrief food;

  /// The whole dish, **offline only**.
  ///
  /// The Dart builder has it, so the things that need per-dish nutrition —
  /// the day's allowance card, the "why this dish" reasons, the local
  /// alternatives — keep working in that mode. Online it is `null` and those
  /// answers come from the server, which is the one place that has the
  /// numbers to produce them.
  final Food? dish;

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
    dish: dish,
    id: id,
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

  /// This meal's macros, or `null` when the servings do not carry them.
  ///
  /// Only an offline serving holds the whole dish; §7.6.1 sends the energy of
  /// each serving and the macros of the **day**, computed server-side. So
  /// these three are an offline answer, and [DailyPlan.actualProtein] and its
  /// neighbours prefer the server's figures when there are any — rather than
  /// summing a column that is not there and calling the result 0.
  double? get protein => _macro((f) => f.protein);
  double? get carb => _macro((f) => f.carb);
  double? get fat => _macro((f) => f.fat);

  double? _macro(double Function(Food) of) {
    var sum = 0.0;
    for (final item in items) {
      final dish = item.dish;
      if (dish == null) return null;
      sum += of(dish);
    }
    return sum;
  }

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
    this.id,
    required this.targetKcal,
    required this.targetProtein,
    required this.targetCarb,
    required this.targetFat,
    required this.slots,
    required this.explorationRatio,
    this.nutrientTargets = const [],
  });

  /// `meal_plans.id`, for §7.6.3 and for rebuilding one meal. `null` on an
  /// offline plan, which is stored nowhere and has nothing to address.
  final String? id;

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

  /// The macros §7.6 computed for this day, when the plan came from there.
  ///
  /// `null` on an offline plan, where the figures are summed from the dishes
  /// instead. Kept apart from the summed ones rather than merged, because
  /// only one of the two can be reproduced from the inputs on this side.
  MacroTotals? serverActuals;

  /// The day-level micronutrient constraints this plan was built under.
  ///
  /// Kept in the result rather than used and discarded, because the question
  /// "does this plan meet my sodium limit?" has to be answerable both in the
  /// interface and in the report — see [nutrientViolations].
  final List<NutrientTarget> nutrientTargets;

  List<MealPlanItem> get allItems => [for (final s in slots) ...s.items];

  double get actualKcal => slots.fold(0, (sum, s) => sum + s.actualKcal);

  /// What the day adds up to in macros, or `null` when nobody can say.
  ///
  /// Online that is [serverActuals], because §7.6 computed it from the whole
  /// `food_nutrition` rows and this side has only each serving's energy.
  /// Offline it is summed from the dishes. `null` would mean neither — a
  /// state the macro bars have to draw as unknown rather than as zero.
  double? get actualProtein => serverActuals?.proteinG ?? _sum((s) => s.protein);
  double? get actualCarb => serverActuals?.carbsG ?? _sum((s) => s.carb);
  double? get actualFat => serverActuals?.fatG ?? _sum((s) => s.fat);

  double? _sum(double? Function(MealSlot) of) {
    var total = 0.0;
    for (final slot in slots) {
      final value = of(slot);
      if (value == null) return null;
      total += value;
    }
    return total;
  }

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

  /// The day's total of one nutrient, or `null` when it cannot be worked out.
  ///
  /// It needs whole nutrition rows, which only an offline serving carries.
  /// Online the equivalent answer is §7.6's own `nutrientViolations`,
  /// computed where the numbers are — see [nutrientViolations].
  double? totalOf(String nutrient) {
    var sum = 0.0;
    for (final item in allItems) {
      final dish = item.dish;
      if (dish == null) return null;
      sum += NutrientTarget.valueOf(dish, nutrient) ?? 0;
    }
    return sum;
  }

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
  /// Empty on a plan from §7.6, whatever its state: [totalOf] cannot answer
  /// without whole nutrition rows, so this side has nothing to judge by and
  /// says nothing rather than reporting a clear plan it never checked. The
  /// server's own verdict travels with the plan instead.
  List<({NutrientTarget target, double actual})> get nutrientViolations => [
    for (final t in nutrientTargets)
      if (NutrientTarget.supported.contains(t.nutrient))
        if (totalOf(t.nutrient) case final actual?)
          if (!t.isSatisfiedBy(actual)) (target: t, actual: actual),
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

/// Energy and the three macros of a whole day, as §7.6 reports them.
class MacroTotals {
  const MacroTotals({
    required this.caloriesKcal,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
  });

  factory MacroTotals.fromJson(Map<String, dynamic> json) => MacroTotals(
    caloriesKcal: _n(json['caloriesKcal']),
    proteinG: _n(json['proteinG']),
    carbsG: _n(json['carbsG']),
    fatG: _n(json['fatG']),
  );

  static double _n(Object? v) => v is num ? v.toDouble() : 0;

  final double caloriesKcal;
  final double proteinG;
  final double carbsG;
  final double fatG;
}

// ── Reading a plan the server built — §7.6 ───────────────────────────
//
// Kept beside the models rather than in `data/api/`, because this is where
// the shape being built is declared: a parser that drifts from its model is
// a parser nobody notices has drifted.

/// §7.6.1's body as a [DailyPlan].
///
/// Every serving comes back with `dish` **null**: the answer carries each
/// one's energy and no macros, so there is no whole dish to put there. What
/// the day adds up to arrives separately, in `actuals`, computed where the
/// nutrition rows are.
DailyPlan planFromJson(Map<String, dynamic> json) {
  final targets = json['targets'] as Map<String, dynamic>? ?? const {};
  final targetKcal = MacroTotals.fromJson(targets);
  final actuals = json['actuals'];

  return DailyPlan(
    id: json['id'] as String?,
    date: DateTime.parse(json['planDate'] as String),
    targetKcal: targetKcal.caloriesKcal,
    targetProtein: targetKcal.proteinG,
    targetCarb: targetKcal.carbsG,
    targetFat: targetKcal.fatG,
    slots: [
      for (final meal in (json['meals'] as List? ?? const []))
        _slotFromJson(meal as Map<String, dynamic>),
    ],
    explorationRatio: (json['explorationRatio'] as num?)?.toDouble() ?? 0,
  )..serverActuals = switch (actuals) {
    final Map<String, dynamic> m => MacroTotals.fromJson(m),
    // `null` on a plan whose step 4 has not finished. The schema has no
    // `DEFAULT 0` for exactly this reason: a stored 0 would make
    // `calorie_deviation_pct` read −100 % the moment the row appeared.
    _ => null,
  };
}

MealSlot _slotFromJson(Map<String, dynamic> json) {
  final code = json['mealType'] as String?;
  return MealSlot(
    type: MealType.values.firstWhere(
      (t) => t.code == code,
      // A meal type this app does not know cannot be shown, and guessing
      // which of the four it is would put dishes in the wrong meal.
      orElse: () => throw ApiFailure(
        code: ApiFailure.unexpectedShape,
        message: 'Máy chủ gửi bữa ăn lạ: $code',
      ),
    ),
    targetKcal: (json['targetCaloriesKcal'] as num?)?.toDouble() ?? 0,
    items: [
      for (final item in (json['items'] as List? ?? const []))
        _itemFromJson(item as Map<String, dynamic>),
    ],
  );
}

MealPlanItem _itemFromJson(Map<String, dynamic> json) => MealPlanItem(
  id: json['id'] as String?,
  food: FoodBrief.fromJson({
    ...?(json['food'] as Map<String, dynamic>?),
    // §7.6.1's `items[].food` has no serving weight of its own — the grams
    // on the plate belong to the SERVING, because `portion_multiplier` can
    // make them differ from one standard serving.
    'servingSizeG': json['servingSizeG'],
  }),
  score: (json['predictedScore'] as num?)?.toDouble() ?? 0,
  explorationDelta: (json['explorationDelta'] as num?)?.toDouble(),
  status: _statusFromCode(json['status'] as String?),
);

/// A status the app does not know becomes [MealItemStatus.suggested].
///
/// The safe direction of the two: an unknown status read as `eaten` would
/// put a dish in the day's consumed figures that nobody ate, while read as
/// `suggested` it merely shows as still on the plate.
MealItemStatus _statusFromCode(String? code) {
  for (final status in MealItemStatus.values) {
    if (status.code == code) return status;
  }
  return MealItemStatus.suggested;
}

/// One dish a serving could be swapped for, from whichever side produced it.
///
/// The two sources answer different halves, and the sheet shows whichever it
/// is given rather than computing what it lacks:
///
/// - **§7.6.4** scores the candidate and says how the day's energy would
///   move and whether the day would still be inside ±10 %. It cannot send
///   nutrition, so [dish] is `null` and the local allowance check cannot run.
/// - **the Dart builder** hands over the whole dish, so the allowance check
///   runs, but nothing has computed what the swap would do to the day.
///
/// Neither half is invented for the other. A sheet that filled in a missing
/// `keepsWithinTolerance` with `true` would be promising something nobody
/// checked.
class ReplaceOption {
  const ReplaceOption({
    required this.food,
    required this.score,
    this.dish,
    this.deltaKcal,
    this.keepsWithinTolerance,
  });

  final FoodBrief food;

  /// The suitability score, in [0, 1].
  final double score;

  /// The whole dish — **offline only**, and what the day's allowance check
  /// needs.
  final Food? dish;

  /// How the day's energy would move, at the portions that would be served.
  /// `null` offline, where nobody computed it.
  final double? deltaKcal;

  /// Whether the day would still be inside ±10 % after the swap. `null`
  /// offline. The sheet **dims or warns** on `false` rather than hiding the
  /// option: a user may well prefer a dish that costs them some accuracy,
  /// and that is their call to make with the cost in front of them.
  final bool? keepsWithinTolerance;
}
