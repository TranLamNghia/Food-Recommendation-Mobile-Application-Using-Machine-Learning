/// How much of the catalogue is left after what the user has declared so
/// far — §7.4.3.
///
/// The screen that asks about diseases and allergies shows this live, and the
/// reason it is a server call rather than a local sum is that the answer is
/// the **F1 filter's**: the rule set lives in `condition_rules` as data, and
/// a second implementation of it in the app would be the one nothing
/// compares. Offline there is such a copy — `rules/dish_screening.dart`, held
/// in parity with Python by `step1_parity_test` — and it fills this same
/// shape, so the screen has one path.
class CandidateCount {
  const CandidateCount({
    required this.totalFoods,
    required this.remainingFoods,
    required this.byDishRole,
    this.emptyRequiredRoles = const [],
    this.enoughForSurvey = true,
    this.surveyDeckSize = 0,
    this.notes = const [],
  });

  factory CandidateCount.fromJson(Map<String, dynamic> json) => CandidateCount(
    totalFoods: (json['totalFoods'] as num?)?.toInt() ?? 0,
    remainingFoods: (json['remainingFoods'] as num?)?.toInt() ?? 0,
    byDishRole: {
      for (final e in (json['byDishRole'] as Map? ?? const {}).entries)
        e.key.toString(): (e.value as num).toInt(),
    },
    emptyRequiredRoles: [
      for (final r in (json['emptyRequiredRoles'] as List? ?? const []))
        r.toString(),
    ],
    enoughForSurvey: json['enoughForSurvey'] as bool? ?? true,
    surveyDeckSize: (json['surveyDeckSize'] as num?)?.toInt() ?? 0,
    notes: [
      for (final n in (json['notes'] as List? ?? const [])) n.toString(),
    ],
  );

  /// Active dishes before anything was declared.
  final int totalFoods;

  /// What is left that this user may eat.
  final int remainingFoods;

  /// The remainder by `dish_role`, in ENUM codes.
  ///
  /// Reported and deliberately not used to refuse anything: the filtering
  /// goes by the declared conditions alone. It is here because the total is
  /// not the figure that binds — 102 dishes with 2 of them in the
  /// `side_protein` role still builds a lunch, with no alternative to offer
  /// and nothing for the exploration mechanism to draw from.
  final Map<String, int> byDishRole;

  /// Roles a day cannot be assembled without that have nothing left in them.
  /// Non-empty means **no meal plan is possible**, whatever the total says.
  final List<String> emptyRequiredRoles;

  /// Whether a full-size taste survey can still be drawn.
  final bool enoughForSurvey;
  final int surveyDeckSize;

  /// Vietnamese sentences for the screen, when there is something worth
  /// saying. Empty is the normal case, and that is the point: the screen
  /// shows them only when they exist rather than always having a line.
  final List<String> notes;

  /// How many dishes the declarations removed.
  ///
  /// Computed here rather than read off the answer's own `removedFoods`: the
  /// two agree, and deriving it means the figure on screen cannot drift from
  /// the two figures beside it.
  int get removedFoods => totalFoods - remainingFoods;

  /// Whether a plan can be built at all. The total being healthy is not
  /// enough — one empty required role is sufficient to make a day
  /// unbuildable.
  bool get canBuildAPlan => remainingFoods > 0 && emptyRequiredRoles.isEmpty;
}
