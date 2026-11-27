// ONLINE: §7.9.1 progress and §7.10.1 weighing.

import '../models/progress.dart';
import 'api_client.dart';
import 'failure.dart';

class ProgressApi {
  const ProgressApi(this._client);

  final ApiClient _client;

  /// §7.9.1 — the range measured day by day, or week by week.
  ///
  /// Each day's target is the one that applied on it (its plan's snapshot),
  /// so last month is not re-measured against this month's weight.
  Future<ProgressReport> progress({
    required DateTime from,
    required DateTime to,
    bool byWeek = false,
  }) async {
    final json = await _client.get(
      '/stats/progress',
      query: {
        'from': _day(from),
        'to': _day(to),
        if (byWeek) 'groupBy': 'week',
      },
    );
    return parsed(() => ProgressReport.fromJson(json));
  }

  /// §7.10.1 — one weighing. A second one on the same day replaces it.
  ///
  /// `409 PROFILE_REQUIRED` without a profile: the BMI needs a height.
  Future<WeighIn> logWeight(
    double weightKg, {
    DateTime? on,
    String? note,
  }) async {
    final json = await _client.post(
      '/body-logs',
      body: {
        'weightKg': weightKg,
        if (on != null) 'loggedOn': _day(on),
        if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
      },
    );
    return parsed(() => WeighIn.fromJson(json));
  }

  /// `yyyy-MM-dd` in the local calendar — see `DiaryApi._day`.
  static String _day(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}
