import 'food_brief.dart';

/// One line of the diary as §7.7.1 sends it — one dish, eaten once, at one
/// meal.
///
/// Pure Dart like every model under `data/`, so `tool/smoke_api.dart` can
/// drive the API layer with `dart run`.
class DiaryLine {
  const DiaryLine({
    required this.id,
    required this.food,
    required this.mealType,
    required this.servingSizeG,
    required this.actualCaloriesKcal,
    required this.fromMealPlan,
    required this.hasFeedback,
    required this.editable,
    required this.createdAt,
  });

  factory DiaryLine.fromJson(Map<String, dynamic> json) => DiaryLine(
    id: json['id'] as String,
    // The same brief §7.6.1 sends for a dish in a plan, so the diary and the
    // plan show the same card.
    food: FoodBrief.fromJson({
      ...?(json['food'] as Map<String, dynamic>?),
      // The grams belong to the LINE, not to the dish: the column stores a
      // portion multiplier, and the same dish can be eaten at two sizes.
      'servingSizeG': json['servingSizeG'],
    }),
    mealType: json['mealType'] as String? ?? '',
    servingSizeG: (json['servingSizeG'] as num?)?.toDouble() ?? 0,
    actualCaloriesKcal: (json['actualCaloriesKcal'] as num?)?.toDouble() ?? 0,
    fromMealPlan: json['fromMealPlan'] as bool? ?? false,
    hasFeedback: json['hasFeedback'] as bool? ?? false,
    // Absent means editable, which is the state almost every line is in.
    editable: json['editable'] as bool? ?? true,
    createdAt: DateTime.parse(json['createdAt'] as String),
  );

  /// `food_diary.id`.
  final String id;

  final FoodBrief food;

  /// `breakfast` · `lunch` · `dinner` · `snack`.
  final String mealType;

  final double servingSizeG;

  /// Energy at the portion actually eaten, not at one standard serving.
  final double actualCaloriesKcal;

  /// Whether this dish was in the user's own plan for this day and meal.
  ///
  /// **This is what decides which of the two deletes to offer.** `true` means
  /// the user ticked "đã ăn" and is taking it back — the dish goes back on
  /// the plate. `false` means they added a dish they ate elsewhere, and
  /// removing it is removing a line of a health log.
  final bool fromMealPlan;

  /// Whether the user has ever rated this dish.
  final bool hasFeedback;

  /// `false` once a rating exists that this line could be the evidence for,
  /// after which §7.7.3 and §7.7.4 both refuse it.
  ///
  /// Sent so the app can **hide** the buttons rather than let the user press
  /// one and read an error — §7.8.1 asks for exactly that, and the same
  /// argument applies to a delete that is going to be refused. Without it the
  /// app would have to work the rule out from timestamps it is not given.
  final bool editable;

  final DateTime createdAt;
}

/// One day of the diary, with its own total.
class DiaryDay {
  const DiaryDay({
    required this.date,
    required this.totalCaloriesKcal,
    required this.lines,
  });

  factory DiaryDay.fromJson(Map<String, dynamic> json) => DiaryDay(
    date: DateTime.parse(json['date'] as String),
    totalCaloriesKcal: (json['totalCaloriesKcal'] as num?)?.toDouble() ?? 0,
    lines: [
      for (final e in (json['entries'] as List? ?? const []))
        DiaryLine.fromJson(e as Map<String, dynamic>),
    ],
  );

  final DateTime date;

  /// The sum over the day's lines, each at the portion actually eaten. A dish
  /// with no nutrition row contributes nothing and is **not** counted as
  /// zero, which is the same rule the plan's totals follow.
  final double totalCaloriesKcal;

  final List<DiaryLine> lines;
}

/// §7.7.5 — one day measured against the limits that applied **on that day**.
class DaySummary {
  const DaySummary({
    required this.date,
    required this.targets,
    required this.consumed,
    required this.remaining,
    this.byMeal = const [],
    this.micronutrients = const [],
    this.planCompliance,
  });

  factory DaySummary.fromJson(Map<String, dynamic> json) => DaySummary(
    date: DateTime.parse(json['date'] as String),
    targets: DayMacros.fromJson(
      json['targets'] as Map<String, dynamic>? ?? const {},
    ),
    consumed: DayMacros.fromJson(
      json['consumed'] as Map<String, dynamic>? ?? const {},
    ),
    remaining: DayMacros.fromJson(
      json['remaining'] as Map<String, dynamic>? ?? const {},
    ),
    byMeal: [
      for (final m in (json['byMeal'] as List? ?? const []))
        MealEnergy.fromJson(m as Map<String, dynamic>),
    ],
    micronutrients: [
      for (final m in (json['micronutrients'] as List? ?? const []))
        Micronutrient.fromJson(m as Map<String, dynamic>),
    ],
    planCompliance: switch (json['planCompliance']) {
      final Map<String, dynamic> m => PlanCompliance.fromJson(m),
      _ => null,
    },
  );

  final DateTime date;

  /// The limits as they stood **on that day**: the snapshot stored with the
  /// plan when there was one, and the profile's columns otherwise. Read and
  /// never recomputed — recomputing would invent a new answer for a past day,
  /// the day the user weighed three kilograms more.
  final DayMacros targets;

  final DayMacros consumed;

  /// Target minus consumed, and **allowed to be negative**. Clamping it at
  /// zero would hide exactly what this screen exists to show.
  final DayMacros remaining;

  final List<MealEnergy> byMeal;

  /// Only the nutrients with a recommended intake for this user's sex and
  /// age band. Dishes missing a figure are skipped rather than counted as
  /// zero, so every number here is a **lower bound**.
  final List<Micronutrient> micronutrients;

  final PlanCompliance? planCompliance;
}

/// Energy and the three macros of one day.
class DayMacros {
  const DayMacros({
    required this.caloriesKcal,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
  });

  factory DayMacros.fromJson(Map<String, dynamic> json) => DayMacros(
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

/// What one meal of the day came to, against its share of the target.
class MealEnergy {
  const MealEnergy({
    required this.mealType,
    required this.caloriesKcal,
    required this.targetCaloriesKcal,
  });

  factory MealEnergy.fromJson(Map<String, dynamic> json) => MealEnergy(
    mealType: json['mealType'] as String? ?? '',
    caloriesKcal: (json['caloriesKcal'] as num?)?.toDouble() ?? 0,
    targetCaloriesKcal: (json['targetCaloriesKcal'] as num?)?.toDouble() ?? 0,
  );

  final String mealType;
  final double caloriesKcal;
  final double targetCaloriesKcal;
}

/// One micronutrient against its recommended intake.
class Micronutrient {
  const Micronutrient({
    required this.nutrient,
    required this.nameVi,
    required this.consumed,
    required this.rda,
    required this.pct,
    required this.unit,
  });

  factory Micronutrient.fromJson(Map<String, dynamic> json) => Micronutrient(
    nutrient: json['nutrient'] as String? ?? '',
    nameVi: json['nameVi'] as String? ?? '',
    consumed: (json['consumed'] as num?)?.toDouble() ?? 0,
    rda: (json['rda'] as num?)?.toDouble() ?? 0,
    pct: (json['pct'] as num?)?.toDouble() ?? 0,
    unit: json['unit'] as String? ?? '',
  );

  final String nutrient;

  /// Already Vietnamese, from the reference table.
  final String nameVi;

  /// A **lower bound**: dishes with no figure for this nutrient were skipped.
  final double consumed;

  final double rda;
  final double pct;
  final String unit;
}

/// §8.4's figure for one day: how much of what was suggested was eaten.
class PlanCompliance {
  const PlanCompliance({
    required this.plannedDishes,
    required this.eatenFromPlan,
    required this.compliancePct,
  });

  factory PlanCompliance.fromJson(Map<String, dynamic> json) => PlanCompliance(
    plannedDishes: (json['plannedDishes'] as num?)?.toInt() ?? 0,
    eatenFromPlan: (json['eatenFromPlan'] as num?)?.toInt() ?? 0,
    compliancePct: (json['compliancePct'] as num?)?.toDouble() ?? 0,
  );

  /// Every dish in the day's plan, **including** the ones that were
  /// replaced: §8.4 counts them and reports the replacement rate separately,
  /// so narrowing it here would disagree with the figure the report cites.
  final int plannedDishes;

  final int eatenFromPlan;
  final double compliancePct;
}
