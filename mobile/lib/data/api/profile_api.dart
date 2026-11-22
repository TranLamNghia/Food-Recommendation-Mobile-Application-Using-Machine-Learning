// ONLINE: §7.2 the health profile, and §7.3 the lookup dictionaries.

import '../models/health_profile.dart';
import 'api_client.dart';
import 'failure.dart';
import 'auth_api.dart';

/// One row of `conditions` — §7.3.1.
///
/// The id is an **`int`**, not a UUID: `conditions.id` is
/// `INT UNSIGNED AUTO_INCREMENT`, unlike `foods.id`. Worth stating because
/// the two live side by side in the same request bodies.
class ConditionOption {
  const ConditionOption({
    required this.id,
    required this.nameVi,
    required this.conditionType,
    this.description,
  });

  factory ConditionOption.fromJson(Map<String, dynamic> json) =>
      ConditionOption(
        id: (json['id'] as num).toInt(),
        nameVi: json['nameVi'] as String,
        conditionType: json['conditionType'] as String,
        description: json['description'] as String?,
      );

  final int id;

  /// Already Vietnamese in the database, so it is shown as it arrives.
  final String nameVi;

  /// `allergy` · `disease` · `diet` — the `condition_type` ENUM.
  final String conditionType;

  final String? description;

  bool get isAllergy => conditionType == 'allergy';
  bool get isDiet => conditionType == 'diet';
  bool get isDisease => conditionType == 'disease';
}

/// A condition the user declared, with how badly — §7.2.4.
class DeclaredCondition {
  const DeclaredCondition({
    required this.conditionId,
    required this.nameVi,
    required this.conditionType,
    this.severity,
    this.note,
  });

  factory DeclaredCondition.fromJson(Map<String, dynamic> json) =>
      DeclaredCondition(
        conditionId: (json['conditionId'] as num).toInt(),
        nameVi: json['nameVi'] as String? ?? '',
        conditionType: json['conditionType'] as String? ?? '',
        severity: json['severity'] as String?,
        note: json['note'] as String?,
      );

  final int conditionId;
  final String nameVi;
  final String conditionType;

  /// `mild` · `moderate` · `severe`.
  ///
  /// Nullable here because a condition can be built before the user has
  /// said how badly. It is **not** optional on the wire: the column is
  /// `NOT NULL DEFAULT 'moderate'` and §7.2.5 refuses a body without it, so
  /// [toJson] falls back to [defaultSeverity].
  final String? severity;

  /// The column's own default, used when the app has not asked.
  ///
  /// The onboarding questions do not ask how severe a condition is yet, and
  /// severity is what `condition_rules.severity_min` compares against — so
  /// until that screen exists, a user who declares gout gets the rules
  /// written for a moderate case. Worth asking properly rather than leaving
  /// to a default; recorded so it is not mistaken for a decision.
  static const String defaultSeverity = 'moderate';

  final String? note;

  Map<String, dynamic> toJson() => {
    'conditionId': conditionId,
    'severity': severity ?? defaultSeverity,
    'note': ?note,
  };
}

/// What §7.2.1 sends back.
class ServerProfile {
  const ServerProfile({
    required this.gender,
    required this.dateOfBirth,
    required this.heightCm,
    required this.weightKg,
    this.targetWeightKg,
    required this.activityLevel,
    required this.goal,
    this.age,
    this.bmi,
    this.bmiCategory,
    this.conditions = const [],
  });

  factory ServerProfile.fromJson(Map<String, dynamic> json) => ServerProfile(
    gender: json['gender'] as String?,
    dateOfBirth: json['dateOfBirth'] is String
        ? DateTime.tryParse(json['dateOfBirth'] as String)
        : null,
    heightCm: _num(json['heightCm']),
    weightKg: _num(json['weightKg']),
    targetWeightKg: _num(json['targetWeightKg']),
    activityLevel: json['activityLevel'] as String?,
    goal: json['goal'] as String?,
    age: json['age'] is num ? (json['age'] as num).toInt() : null,
    bmi: _num(json['bmi']),
    bmiCategory: json['bmiCategory'] as String?,
    conditions: [
      for (final c in (json['conditions'] as List? ?? const []))
        if (c is Map<String, dynamic>) DeclaredCondition.fromJson(c),
    ],
  );

  static double? _num(Object? v) => v is num ? v.toDouble() : null;

  final String? gender;
  final DateTime? dateOfBirth;
  final double? heightCm;
  final double? weightKg;
  final double? targetWeightKg;
  final String? activityLevel;
  final String? goal;
  final int? age;
  final double? bmi;
  final String? bmiCategory;
  final List<DeclaredCondition> conditions;

  /// Fills a [HealthProfile] from the server's answer.
  ///
  /// `targetWeightKg` is among them since migration 007: it used to be the
  /// one thing the app asked for and then lost on restart, because no column
  /// and no endpoint carried it. It still takes no part in Step 1 — the
  /// energy limit comes from the weight the user has now — so it arrives
  /// here as data to show, not as an input to anything.
  void applyTo(HealthProfile profile) {
    profile
      ..gender = _genderOf(gender)
      ..birthday = dateOfBirth
      ..heightCm = heightCm
      ..weightKg = weightKg
      // Assigned straight through, null included: the server clearing the
      // target because the goal no longer needs one has to reach the app.
      ..targetWeightKg = targetWeightKg
      ..activity = activityLevel == null
          ? profile.activity
          : _activityOf(activityLevel!)
      ..goal = goal == null ? profile.goal : _goalOf(goal!);
  }

  static Gender? _genderOf(String? code) {
    for (final g in Gender.values) {
      if (g.code == code) return g;
    }
    // `other` is in the database ENUM and has no screen for it, so it comes
    // back as "not answered" rather than as a wrong answer.
    return null;
  }

  static ActivityLevel? _activityOf(String code) {
    for (final a in ActivityLevel.values) {
      if (a.code == code) return a;
    }
    return null;
  }

  static HealthGoal? _goalOf(String code) {
    for (final g in HealthGoal.values) {
      if (g.code == code) return g;
    }
    return null;
  }
}

class ProfileApi {
  const ProfileApi(this._client);

  final ApiClient _client;

  /// §7.2.1. `409 PROFILE_REQUIRED` before the form has ever been sent.
  Future<ServerProfile> read() async {
    final json = await _client.get('/profile');
    return parsed(() => ServerProfile.fromJson(json));
  }

  /// §7.2.2 — creates or replaces the whole profile.
  ///
  /// Sends only what the server has a column for. The date goes as
  /// `yyyy-MM-dd` with no time and no zone: it is a `DATE`, and the age
  /// computed from it is what moves the BMR by 5 kcal a year.
  ///
  /// The answer carries **both** halves — `{"profile": …,
  /// "nutritionTargets": …}` — because saving the profile recomputes step 1.
  /// So there is no second call to [targets] to make here, and reading this
  /// as a bare profile is how the wrapper gets missed: every field comes
  /// back null and nothing complains.
  Future<({ServerProfile profile, ServerTargets targets})> save(
    HealthProfile profile,
  ) async {
    final gender = profile.gender;
    final activity = profile.activity;
    final goal = profile.goal;
    final birthday = profile.birthday;
    final height = profile.heightCm;
    final weight = profile.weightKg;
    if (gender == null ||
        activity == null ||
        goal == null ||
        birthday == null ||
        height == null ||
        weight == null) {
      throw StateError(
        'the profile is incomplete, so there is nothing to save yet',
      );
    }
    final json = await _client.put(
      '/profile',
      body: {
        'gender': gender.code,
        'dateOfBirth': _date(birthday),
        'heightCm': height,
        'weightKg': weight,
        // Left out when there is none, which is how §7.2.2 clears it: a PUT
        // replaces the whole profile. `maintain` and `healthy_eating` have
        // nothing to aim at, so the app never asks and never sends.
        'targetWeightKg': ?profile.targetWeightKg,
        'activityLevel': activity.code,
        'goal': goal.code,
      },
    );
    return parsed(
      () => (
        profile: ServerProfile.fromJson(
          json['profile'] as Map<String, dynamic>,
        ),
        targets: ServerTargets.fromJson(
          json['nutritionTargets'] as Map<String, dynamic>,
        ),
      ),
    );
  }

  /// §7.2.3 — step 1's output, as the server computed it.
  Future<ServerTargets> targets() async {
    final json = await _client.get('/profile/nutrition-targets');
    return parsed(() => ServerTargets.fromJson(json));
  }

  /// §7.2.4 — answers with a **bare array**, not an object.
  Future<List<DeclaredCondition>> conditions() async =>
      _declared(await _client.getList('/profile/conditions'));

  /// §7.2.5 — replaces the whole set, so an empty list clears it.
  ///
  /// The request body is wrapped in `{"conditions": [...]}` while the answer
  /// is a bare array. The asymmetry is the specification's, not a slip here.
  Future<List<DeclaredCondition>> saveConditions(
    List<DeclaredCondition> declared,
  ) async => _declared(
    await _client.sendList(
      'PUT',
      '/profile/conditions',
      body: {'conditions': [for (final c in declared) c.toJson()]},
    ),
  );

  static List<DeclaredCondition> _declared(List<dynamic> rows) => parsed(
    () => [
      for (final c in rows)
        if (c is Map<String, dynamic>) DeclaredCondition.fromJson(c),
    ],
  );

  /// §7.3.1 — the dictionary the onboarding questions are drawn from.
  ///
  /// **No token needed.** The registration flow asks about allergies before
  /// an account exists, which is why §7.3 is public.
  Future<List<ConditionOption>> conditionCatalogue({String? type}) async {
    final rows = await _client.getList(
      '/conditions',
      query: {'type': type},
      authenticated: false,
    );
    return parsed(
      () => [
        for (final r in rows)
          if (r is Map<String, dynamic>) ConditionOption.fromJson(r),
      ],
    );
  }

  static String _date(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}
