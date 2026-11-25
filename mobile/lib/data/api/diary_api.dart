// ONLINE: §7.7 the food diary — the health log, and the day measured
// against the limits that applied on it.

import '../models/diary_day.dart';
import 'api_client.dart';
import 'failure.dart';

class DiaryApi {
  const DiaryApi(this._client);

  final ApiClient _client;

  /// §7.7.1 — the diary over a range of days, oldest first.
  ///
  /// Only the days with something in them come back: ninety empty days would
  /// be ninety objects saying nothing, and the app renders a day header from
  /// the date either way.
  Future<List<DiaryDay>> range({
    required DateTime from,
    required DateTime to,
    String? mealType,
  }) async {
    final json = await _client.get(
      '/food-diary',
      query: {'from': _day(from), 'to': _day(to), 'mealType': ?mealType},
    );
    return parsed(
      () => [
        for (final d in (json['days'] as List? ?? const []))
          DiaryDay.fromJson(d as Map<String, dynamic>),
      ],
    );
  }

  /// §7.7.2 — record something eaten.
  ///
  /// This is the endpoint for a dish the user ate **outside** the plan: the
  /// plan is the menu the system proposes, and the diary is what the person
  /// actually ate. Adding a dish to the plan instead would be a diner
  /// writing on the restaurant's menu.
  ///
  /// **The F1 filter is deliberately not applied here.** A log records what
  /// happened, including a dish the user should not have eaten — refusing it
  /// would leave their doctor's figures missing the one meal that mattered.
  ///
  /// [servingSizeG] omitted means one standard serving.
  ///
  /// `409 VALIDATION_FAILED` when the same `(day, meal, dish)` is already
  /// there, with the field named.
  Future<DiaryLine> add({
    required String foodId,
    required DateTime ateOn,
    required String mealType,
    int? servingSizeG,
  }) async {
    final json = await _client.post(
      '/food-diary',
      body: {
        'foodId': foodId,
        'ateOn': _day(ateOn),
        'mealType': mealType,
        'servingSizeG': ?servingSizeG,
      },
    );
    return parsed(() => DiaryLine.fromJson(json));
  }

  /// §7.7.3 — correct a line.
  ///
  /// Only the meal and the portion can change. The dish and the day cannot:
  /// a different dish or a different day is a different eating, and changing
  /// them in place would move an existing rating onto a dish the user never
  /// said anything about.
  ///
  /// `409 VALIDATION_FAILED` once the line is locked — see [DiaryLine.editable],
  /// which is sent so the app can hide the button instead.
  Future<DiaryLine> update(
    String id, {
    String? mealType,
    int? servingSizeG,
  }) async {
    final json = await _client.put(
      '/food-diary/$id',
      body: {'mealType': ?mealType, 'servingSizeG': ?servingSizeG},
    );
    return parsed(() => DiaryLine.fromJson(json));
  }

  /// §7.7.4 — remove a line.
  ///
  /// **Two deletes in one endpoint, and the server decides which.** It looks
  /// up whether the dish was in that day's plan for that meal:
  ///
  /// - it was — the line goes, and the serving returns to the plate as
  ///   `suggested`. This is "I have not eaten it after all", a mis-tap on
  ///   "đã ăn" being taken back.
  /// - it was not — the line simply goes. This is a dish eaten elsewhere
  ///   being removed from the log.
  ///
  /// No parameter decides it, which is right: the app would have to work out
  /// the answer from data it does not hold, and two clients could disagree.
  /// [DiaryLine.fromMealPlan] is sent so the app can **word** the
  /// confirmation correctly, not so it can choose the behaviour.
  ///
  /// `409 VALIDATION_FAILED` once the line is locked by a rating.
  Future<void> remove(String id) => _client.delete('/food-diary/$id');

  /// §7.7.5 — one day against the limits that applied **on that day**.
  Future<DaySummary> summary(DateTime date) async {
    final json = await _client.get(
      '/food-diary/summary',
      query: {'date': _day(date)},
    );
    return parsed(() => DaySummary.fromJson(json));
  }

  /// `yyyy-MM-dd` in the **local** calendar. Not UTC: a meal belongs to a
  /// date, and Vietnam is +07:00 — converting would move a late dinner into
  /// tomorrow's diary.
  static String _day(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}
