/// §7.9.1 — health progress over a range of days, and §7.10.1's weighing.
library;

/// One day, or one week when grouped by week.
class ProgressPoint {
  const ProgressPoint({
    required this.date,
    required this.consumedKcal,
    required this.loggedMeals,
    this.targetKcal,
    this.compliancePct,
  });

  factory ProgressPoint.fromJson(Map<String, dynamic> json) => ProgressPoint(
    date: DateTime.parse(json['date'] as String),
    consumedKcal: (json['caloriesConsumed'] as num).toDouble(),
    targetKcal: (json['caloriesTarget'] as num?)?.toDouble(),
    compliancePct: (json['compliancePct'] as num?)?.toDouble(),
    loggedMeals: (json['loggedMeals'] as num).toInt(),
  );

  final DateTime date;

  /// `0` with [loggedMeals] `0` means nothing was written down — not that
  /// nothing was eaten. A chart must not draw it as a zero bar.
  final double consumedKcal;

  final double? targetKcal;

  /// `null` for a day without a plan.
  final double? compliancePct;

  final int loggedMeals;

  bool get logged => loggedMeals > 0;
}

class ProgressSummary {
  const ProgressSummary({
    required this.daysLogged,
    required this.daysInRange,
    required this.totalFeedbacks,
    this.avgConsumedKcal,
    this.avgTargetKcal,
    this.avgCompliancePct,
    this.avgDeviationPct,
  });

  factory ProgressSummary.fromJson(Map<String, dynamic> json) =>
      ProgressSummary(
        daysLogged: (json['daysLogged'] as num).toInt(),
        daysInRange: (json['daysInRange'] as num).toInt(),
        avgConsumedKcal: (json['avgCaloriesConsumed'] as num?)?.toDouble(),
        avgTargetKcal: (json['avgCaloriesTarget'] as num?)?.toDouble(),
        avgCompliancePct: (json['avgCompliancePct'] as num?)?.toDouble(),
        avgDeviationPct: (json['avgCalorieDeviationPct'] as num?)?.toDouble(),
        totalFeedbacks: (json['totalFeedbacks'] as num).toInt(),
      );

  final int daysLogged;
  final int daysInRange;

  /// Means over the logged days only, `null` when none was.
  final double? avgConsumedKcal;
  final double? avgTargetKcal;
  final double? avgCompliancePct;
  final double? avgDeviationPct;
  final int totalFeedbacks;
}

class WeightPoint {
  const WeightPoint({required this.date, required this.weightKg});

  factory WeightPoint.fromJson(Map<String, dynamic> json) => WeightPoint(
    date: DateTime.parse(json['date'] as String),
    weightKg: (json['weightKg'] as num).toDouble(),
  );

  final DateTime date;
  final double weightKg;
}

class ProgressReport {
  const ProgressReport({
    required this.from,
    required this.to,
    required this.series,
    required this.summary,
    required this.weightTrend,
  });

  factory ProgressReport.fromJson(Map<String, dynamic> json) => ProgressReport(
    from: DateTime.parse(json['from'] as String),
    to: DateTime.parse(json['to'] as String),
    series: [
      for (final p in (json['series'] as List? ?? const []))
        ProgressPoint.fromJson(p as Map<String, dynamic>),
    ],
    summary: ProgressSummary.fromJson(json['summary'] as Map<String, dynamic>),
    weightTrend: [
      for (final w in (json['weightTrend'] as List? ?? const []))
        WeightPoint.fromJson(w as Map<String, dynamic>),
    ],
  );

  final DateTime from;
  final DateTime to;
  final List<ProgressPoint> series;
  final ProgressSummary summary;

  /// At most one point a day, oldest first.
  final List<WeightPoint> weightTrend;
}

/// What §7.10.1 answered.
class WeighIn {
  const WeighIn({
    required this.loggedOn,
    required this.weightKg,
    required this.bmi,
    required this.profileUpdated,
    this.note,
  });

  factory WeighIn.fromJson(Map<String, dynamic> json) => WeighIn(
    loggedOn: DateTime.parse(json['loggedOn'] as String),
    weightKg: (json['weightKg'] as num).toDouble(),
    bmi: (json['bmi'] as num).toDouble(),
    note: json['note'] as String?,
    profileUpdated: json['profileUpdated'] as bool? ?? false,
  );

  final DateTime loggedOn;
  final double weightKg;
  final double bmi;
  final String? note;

  /// Whether this became the current weight. `false` for a day older than
  /// the latest weighing — filling in a forgotten entry does not move the
  /// energy target backwards.
  final bool profileUpdated;
}
