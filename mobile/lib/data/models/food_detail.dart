import 'food_brief.dart';

/// One dish in full — §7.5.2.
///
/// This is the only answer in the API that carries a dish's whole nutrition
/// row, which is why the detail screen fetches rather than reusing whatever
/// the list it was opened from happened to hold. See [FoodBrief] for why a
/// list row cannot stand in.
///
/// Pure Dart, like every model under `data/`: `tool/smoke_api.dart` drives
/// the API layer with `dart run`, and one Flutter type in here would take the
/// whole layer out of its reach.
class FoodDetail {
  const FoodDetail({
    required this.brief,
    required this.nutrition,
    this.description,
    this.categoryId,
    this.warnings = const [],
    this.myFeedback,
  });

  factory FoodDetail.fromJson(Map<String, dynamic> json) {
    final category = json['category'] as Map<String, dynamic>? ?? const {};
    return FoodDetail(
      // The list fields are read through the same parser the browse rows use,
      // so one dish cannot arrive shaped two ways. §7.5.2 nests the category
      // as an object while §7.5.1 flattens it to a name, which is the one
      // difference, handled below.
      brief: FoodBrief.fromJson({
        ...json,
        'categoryName': category['name'],
        'tags': [
          for (final t in (json['tags'] as List? ?? const []))
            (t as Map)['nameVi'],
        ],
      }),
      nutrition: DishNutrition.fromJson(
        json['nutrition'] as Map<String, dynamic>? ?? const {},
      ),
      description: json['description'] as String?,
      categoryId: category['id'] as String?,
      warnings: [
        for (final w in (json['warnings'] as List? ?? const []))
          FoodWarning.fromJson(w as Map<String, dynamic>),
      ],
      myFeedback: switch (json['myFeedback']) {
        final Map<String, dynamic> m => MyFeedback.fromJson(m),
        _ => null,
      },
    );
  }

  /// Everything a card shows, shared with the list rows.
  final FoodBrief brief;

  final DishNutrition nutrition;

  final String? description;
  final String? categoryId;

  /// Every hard **medical** rule this dish breaks for this user, each with a
  /// sentence to show. Empty when the dish is safe to eat — a dish the user
  /// has merely blocked has none, because a preference is not a health
  /// warning; that arrives as [FoodBrief.mark] instead.
  final List<FoodWarning> warnings;

  /// This user's most recent rating, or `null` if they have never rated it.
  final MyFeedback? myFeedback;

  String get id => brief.id;
  String get name => brief.name;
}

/// The `food_nutrition` row, per serving.
///
/// Every field is nullable and `null` is **not** 0. The Vietnamese food
/// composition table publishes purine for 70 of 318 dishes, and leaves gaps
/// in the micronutrients too; showing 0 mg where the answer is "nobody
/// measured it" is a false statement in a health app, and it is the kind that
/// reads as reassuring.
class DishNutrition {
  const DishNutrition({
    required this.servingSizeG,
    required this.caloriesKcal,
    this.proteinG,
    this.carbsG,
    this.fatG,
    this.fiberG,
    this.sugarG,
    this.sodiumMg,
    this.cholesterolMg,
    this.purineMg,
    this.calciumMg,
    this.ironMg,
    this.zincMg,
    this.vitaminAMcg,
    this.vitaminCMg,
  });

  factory DishNutrition.fromJson(Map<String, dynamic> json) => DishNutrition(
    servingSizeG: _num(json['servingSizeG']) ?? 0,
    caloriesKcal: _num(json['caloriesKcal']) ?? 0,
    proteinG: _num(json['proteinG']),
    carbsG: _num(json['carbsG']),
    fatG: _num(json['fatG']),
    fiberG: _num(json['fiberG']),
    sugarG: _num(json['sugarG']),
    sodiumMg: _num(json['sodiumMg']),
    cholesterolMg: _num(json['cholesterolMg']),
    purineMg: _num(json['purineMg']),
    calciumMg: _num(json['calciumMg']),
    ironMg: _num(json['ironMg']),
    zincMg: _num(json['zincMg']),
    vitaminAMcg: _num(json['vitaminAMcg']),
    vitaminCMg: _num(json['vitaminCMg']),
  );

  static double? _num(Object? v) => v is num ? v.toDouble() : null;

  /// The mandatory denominator for every figure above, which are all **per
  /// serving** and not per 100 g.
  final double servingSizeG;
  final double caloriesKcal;

  final double? proteinG;
  final double? carbsG;
  final double? fatG;
  final double? fiberG;
  final double? sugarG;
  final double? sodiumMg;
  final double? cholesterolMg;
  final double? purineMg;
  final double? calciumMg;
  final double? ironMg;
  final double? zincMg;
  final double? vitaminAMcg;
  final double? vitaminCMg;

  /// The share of energy each macronutrient supplies, as fractions summing
  /// to 1 — protein and carbohydrate at 4 kcal/g, fat at 9.
  ///
  /// Computed from the grams rather than from `caloriesKcal`, and normalised
  /// by their own total rather than by it: the two disagree for most dishes,
  /// because the measured energy includes alcohol, organic acids and rounding
  /// that the three macros do not account for. Normalising by the measured
  /// figure would make the bars fail to fill, which reads as missing data
  /// rather than as the arithmetic it is.
  ///
  /// `null` when any of the three is missing: two thirds of a composition is
  /// not a composition, and drawing it as one would overstate whichever
  /// macros happen to be known.
  ({double protein, double carbs, double fat})? get macroShare {
    final p = proteinG, c = carbsG, f = fatG;
    if (p == null || c == null || f == null) return null;
    final total = p * 4 + c * 4 + f * 9;
    if (total <= 0) return null;
    return (protein: p * 4 / total, carbs: c * 4 / total, fat: f * 9 / total);
  }
}

/// One hard medical rule a dish breaks for this user — §7.5.2's `warnings[]`.
class FoodWarning {
  const FoodWarning({
    required this.message,
    required this.conditionName,
    required this.ruleType,
    this.conditionId,
    this.conditionCode,
    this.missingData = false,
  });

  factory FoodWarning.fromJson(Map<String, dynamic> json) => FoodWarning(
    message: json['message'] as String? ?? '',
    conditionName: json['conditionName'] as String? ?? '',
    ruleType: json['ruleType'] as String? ?? '',
    conditionId: (json['conditionId'] as num?)?.toInt(),
    conditionCode: json['conditionCode'] as String?,
    missingData: json['missingData'] as bool? ?? false,
  );

  /// Vietnamese prose, written by the backend. Shown as it arrives: the app
  /// does not compose safety sentences, so there is one wording per rule and
  /// one place it comes from.
  final String message;

  /// `conditions.name_vi` — already Vietnamese.
  final String conditionName;

  /// `exclude_tag` · `require_tag` · `nutrient_limit`.
  final String ruleType;

  /// `conditions.id`, so a screen can open the declaration at the right row.
  final int? conditionId;

  /// `conditions.code` — the stable key, which is what the app's own curated
  /// question list is written in. [conditionId] is `AUTO_INCREMENT`.
  final String? conditionCode;

  /// `true` when the dish was excluded for a **missing** measurement rather
  /// than for exceeding one. The two need different words on screen: "vượt
  /// ngưỡng" against "chưa có số liệu".
  final bool missingData;
}

/// This user's latest rating of a dish — §7.5.2's `myFeedback`.
class MyFeedback {
  const MyFeedback({
    required this.id,
    required this.rating,
    required this.createdAt,
    this.comment,
  });

  factory MyFeedback.fromJson(Map<String, dynamic> json) => MyFeedback(
    id: json['id'] as String,
    rating: (json['rating'] as num).toInt(),
    createdAt: DateTime.parse(json['createdAt'] as String),
    comment: json['comment'] as String?,
  );

  final String id;
  final int rating;
  final DateTime createdAt;
  final String? comment;
}
