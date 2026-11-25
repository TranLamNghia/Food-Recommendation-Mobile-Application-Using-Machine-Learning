// ONLINE: §7.6 the meal plan, and the three endpoints that act on one
// serving of it.

import '../models/food_brief.dart';
import '../models/meal_plan.dart';
import 'api_client.dart';
import 'failure.dart';

/// One serving's new state after §7.6.6.
class ItemStatusResult {
  const ItemStatusResult({
    required this.id,
    required this.status,
    required this.diaryEntryCreated,
    this.diaryEntryId,
  });

  factory ItemStatusResult.fromJson(Map<String, dynamic> json) =>
      ItemStatusResult(
        id: json['id'] as String,
        status: json['status'] as String,
        diaryEntryCreated: json['diaryEntryCreated'] as bool? ?? false,
        diaryEntryId: json['diaryEntryId'] as String?,
      );

  final String id;

  /// `kept` · `eaten` · `skipped` — what the server stored.
  final String status;

  /// Whether **this call** wrote the diary entry.
  ///
  /// `false` on a repeat of `eaten`: the entry already exists, and a second
  /// one would count the same meal twice in every compliance figure the
  /// report quotes. So a screen must not read a `false` as a failure.
  final bool diaryEntryCreated;

  /// `food_diary.id`, so the app can send the user on to rate the dish.
  /// A **UUID string** — §7.6.6's own example shows an integer, and the
  /// column is `CHAR(36)` like every other id in this schema.
  final String? diaryEntryId;
}

/// One candidate for a swap — §7.6.4.
class PlanAlternative {
  const PlanAlternative({
    required this.food,
    required this.servingSizeG,
    required this.predictedScore,
    required this.calorieDeltaKcal,
    required this.keepsWithinTolerance,
  });

  factory PlanAlternative.fromJson(Map<String, dynamic> json) =>
      PlanAlternative(
        food: FoodBrief.fromJson(json['food'] as Map<String, dynamic>),
        servingSizeG: (json['servingSizeG'] as num?)?.toDouble() ?? 0,
        predictedScore: (json['predictedScore'] as num?)?.toDouble() ?? 0,
        calorieDeltaKcal: (json['calorieDeltaKcal'] as num?)?.toDouble() ?? 0,
        keepsWithinTolerance: json['keepsWithinTolerance'] as bool? ?? true,
      );

  final FoodBrief food;
  final double servingSizeG;
  final double predictedScore;

  /// How the day's energy would move, at the portions that would be served.
  final double calorieDeltaKcal;

  /// Whether the day stays inside ±10 % after the swap.
  ///
  /// The screen **dims or warns** on `false` rather than hiding the option: a
  /// user may well prefer a dish that costs them a little accuracy, and that
  /// is their call to make with the cost in front of them.
  final bool keepsWithinTolerance;
}

class MealPlanApi {
  const MealPlanApi(this._client);

  final ApiClient _client;

  /// §7.6.1 — the plan for one day.
  ///
  /// [autoGenerate] left `true` is the server's own default: a day with no
  /// plan is built on the spot. `false` answers `404 NOT_FOUND` instead,
  /// which is what a screen looking **ahead** wants — asking about next
  /// Friday should not commit a plan for it.
  ///
  /// Returns `null` only when [autoGenerate] is `false` and there is no plan.
  Future<DailyPlan?> forDate(DateTime date, {bool autoGenerate = true}) async {
    final Map<String, dynamic> json;
    try {
      json = await _client.get(
        '/meal-plans',
        query: {'date': _day(date), 'autoGenerate': '$autoGenerate'},
      );
    } on ApiFailure catch (failure) {
      // Only this one code, and only when the caller said not to generate.
      // Any other failure is a failure, and a `404` with `autoGenerate` on
      // would mean the server did not do what it says it does.
      if (!autoGenerate && failure.code == ApiFailure.notFound) return null;
      rethrow;
    }
    return parsed(() => planFromJson(json));
  }

  /// §7.6.2 — build a plan for one day.
  ///
  /// [regenerate] `false` (the server's default) answers
  /// `409 MEAL_PLAN_EXISTS` when that day already has one, rather than
  /// replacing it: a plan the user has started eating from must not vanish
  /// because a screen was reopened. `true` deletes it and builds a new one,
  /// which is a thing to confirm with the user first.
  ///
  /// `422 NO_FEASIBLE_PLAN` when no combination meets the targets, and
  /// `422 RULE_TOO_RESTRICTIVE` when the declared conditions leave too few
  /// dishes. The two are different answers: one is about arithmetic, the
  /// other about what the user declared, and only the second is theirs to
  /// change.
  Future<DailyPlan> generate(DateTime date, {bool regenerate = false}) async {
    final json = await _client.post(
      '/meal-plans',
      body: {'planDate': _day(date), 'regenerate': regenerate},
    );
    return parsed(() => planFromJson(json));
  }

  /// Rebuilds **one meal** inside a plan that already exists.
  ///
  /// Not §7.6.2's `mealTypes`, which this API refuses: phase 5 of step 4
  /// repairs a plan at **day** level, so a day is the unit it can work on.
  /// This endpoint rebuilds one meal and then repairs the whole day around
  /// it, which is the thing §7.6.2's field was reaching for.
  Future<DailyPlan> regenerateMeal(String planId, String mealType) async {
    final json = await _client.post('/meal-plans/$planId/meals/$mealType');
    return parsed(() => planFromJson(json));
  }

  /// §7.6.4 — what this serving could be swapped for.
  Future<List<PlanAlternative>> alternatives(String itemId) async {
    final json = await _client.get('/meal-plan-items/$itemId/alternatives');
    return parsed(() => [
      for (final a in (json['alternatives'] as List? ?? const []))
        PlanAlternative.fromJson(a as Map<String, dynamic>),
    ]);
  }

  /// §7.6.5 — swap one serving for another dish.
  ///
  /// Answers with the **whole day**, because the swap moves the day's totals
  /// and its ±10 % verdict; a response about one serving would leave the
  /// screen to recompute figures it cannot.
  ///
  /// This is the action that produces **two** training signals at once: the
  /// dropped dish takes `plan_replaced` (0.150) and the chosen one
  /// `plan_kept` (0.700). It is the main source of preference data once the
  /// swipe session is over, which is why the old serving is kept as a row
  /// rather than deleted.
  Future<DailyPlan> replace(
    String itemId,
    String newFoodId, {
    int? servingSizeG,
  }) async {
    final json = await _client.put(
      '/meal-plan-items/$itemId/replace',
      body: {'newFoodId': newFoodId, 'servingSizeG': ?servingSizeG},
    );
    return parsed(() => planFromJson(json));
  }

  /// §7.6.6 — mark what happened to a serving.
  ///
  /// `kept` · `eaten` · `skipped`, and those three only: `suggested` and
  /// `replaced` are statements about what the **system** did, and §4.6
  /// computes label weights from them. A client able to send `replaced`
  /// could relabel its own training data — mark a dish replaced without
  /// replacing it, and that dish is taught to the model as a rejection.
  ///
  /// `eaten` also writes the diary entry, server-side, in the same request.
  /// That is deliberate: two calls would leave a window where the plan says
  /// eaten and the diary does not, and every compliance figure reads both.
  Future<ItemStatusResult> setStatus(String itemId, String status) async {
    final json = await _client.patch(
      '/meal-plan-items/$itemId/status',
      body: {'status': status},
    );
    return parsed(() => ItemStatusResult.fromJson(json));
  }

  /// `yyyy-MM-dd` in the **local** calendar, which is the one the user is
  /// living in. Not an ISO timestamp and not UTC: a plan belongs to a date,
  /// and converting to UTC moves that date for anyone east of Greenwich —
  /// Vietnam is +07:00, so late-evening requests would ask for tomorrow.
  static String _day(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}
