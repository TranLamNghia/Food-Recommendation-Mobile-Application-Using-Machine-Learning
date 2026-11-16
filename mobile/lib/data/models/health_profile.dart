import 'dart:math' as math;

/// Gender — the `gender` enum of API specification §5.1.
///
/// Note on language: the `label` of every enum in this file is text shown on
/// screen, so it stays in Vietnamese; `code` is the value sent to the server
/// and matched against the database ENUM, so it stays as it is too.
enum Gender {
  male('male', 'Nam'),
  female('female', 'Nữ');

  const Gender(this.code, this.label);
  final String code;
  final String label;
}

/// The activity levels and their TDEE multipliers.
///
/// The factors come from `SYSTEM_ARCHITECTURE.md` §3.1.
enum ActivityLevel {
  sedentary('sedentary', 'Ít vận động', 'Ngồi nhiều, hầu như không tập', 1.200),
  light('light', 'Vận động nhẹ', 'Tập 1–3 buổi mỗi tuần', 1.375),
  moderate('moderate', 'Vận động vừa', 'Tập 3–5 buổi mỗi tuần', 1.550),
  active('active', 'Vận động nhiều', 'Tập 6–7 buổi mỗi tuần', 1.725),
  veryActive(
    'very_active',
    'Vận động rất nhiều',
    'Lao động nặng hoặc tập hai buổi mỗi ngày',
    1.900,
  );

  const ActivityLevel(this.code, this.label, this.hint, this.factor);
  final String code;
  final String label;
  final String hint;
  final double factor;
}

/// The health goal — it decides how the energy target is adjusted.
enum HealthGoal {
  loseWeight('lose_weight', 'Giảm cân', 'Ăn ít hơn mức tiêu hao'),
  maintain('maintain', 'Giữ cân', 'Cân bằng năng lượng vào và ra'),
  gainWeight('gain_weight', 'Tăng cân', 'Ăn nhiều hơn mức tiêu hao'),
  healthyEating(
    'healthy_eating',
    'Ăn uống lành mạnh',
    'Không đặt nặng cân nặng',
  );

  const HealthGoal(this.code, this.label, this.hint);
  final String code;
  final String label;
  final String hint;

  /// Only these two goals need a target weight to be asked for.
  bool get needsTargetWeight =>
      this == HealthGoal.loseWeight || this == HealthGoal.gainWeight;
}

/// The health profile the user fills in during the onboarding flow.
///
/// Every field is nullable because the profile is filled in step by step. By
/// the end of the flow, all the required fields have a value.
class HealthProfile {
  Gender? gender;
  DateTime? birthday;
  double? heightCm;
  double? weightKg;
  double? targetWeightKg;
  HealthGoal? goal;
  ActivityLevel? activity;

  /// The selected condition codes, looked up in the `conditions` table.
  final Set<String> conditions = {};

  /// The allergy codes and the mandatory diets.
  final Set<String> allergies = {};

  /// The date treated as "today" when computing the age. `null` means use
  /// [DateTime.now].
  ///
  /// The server computes the same thing in the **Asia/Ho_Chi_Minh** time zone
  /// (`backend/Api/Time/Clock.cs`), so for a user in Vietnam [DateTime.now]
  /// here gives the same day. For a user in another time zone the two can be
  /// a day apart, and the server's number is the correct one — it is what
  /// gets written into `health_profiles` and used to generate the meal plan.
  ///
  /// It exists so this can be checked at all. The age depends on the day the
  /// code runs, so a fixed set of cases with fixed dates of birth **cannot**
  /// check this implementation if it always reads the system clock:
  /// `test/step1_parity_test.dart` would have to skip every case whose age
  /// computed today differs from the age in the fixture — that is, skip
  /// nearly all of them, for nearly the whole year, while still reporting
  /// "All tests passed".
  ///
  /// That is exactly the kind of failure the parity suite exists to stop: a
  /// comparison that stops comparing without anyone noticing.
  DateTime? today;

  int? get age {
    final b = birthday;
    if (b == null) return null;
    final now = today ?? DateTime.now();
    var years = now.year - b.year;
    if (now.month < b.month || (now.month == b.month && now.day < b.day)) {
      years--;
    }
    return years;
  }

  /// The body mass index.
  double? get bmi {
    final h = heightCm;
    final w = weightKg;
    if (h == null || w == null || h <= 0) return null;
    final m = h / 100;
    return w / (m * m);
  }

  /// The basal metabolic rate, by the Mifflin-St Jeor formula.
  double? get bmr {
    final h = heightCm;
    final w = weightKg;
    final a = age;
    final g = gender;
    if (h == null || w == null || a == null || g == null) return null;
    final base = 10 * w + 6.25 * h - 5 * a;
    return g == Gender.male ? base + 5 : base - 161;
  }

  /// The total daily energy expenditure.
  double? get tdee {
    final b = bmr;
    final act = activity;
    if (b == null || act == null) return null;
    return b * act.factor;
  }

  /// The energy target for the goal.
  ///
  /// Losing weight subtracts 500 kcal but **never goes below the BMR** — the
  /// safety constraint stated in `SYSTEM_ARCHITECTURE.md` §3.1.
  double? get energyTarget {
    final t = tdee;
    final b = bmr;
    final g = goal;
    if (t == null || b == null || g == null) return null;
    return switch (g) {
      HealthGoal.loseWeight => math.max(t - 500, b),
      HealthGoal.gainWeight => t + 500,
      HealthGoal.maintain || HealthGoal.healthyEating => t,
    };
  }

  /// The percentage of the energy taken by each of the three energy-bearing
  /// macronutrients.
  ///
  /// The default is 15 / 60 / 25 — exactly the `DEFAULT` of the three columns
  /// `health_profiles.target_protein_pct`, `target_carbs_pct` and
  /// `target_fat_pct`. All three sit inside the National Institute of
  /// Nutrition's recommended ranges (`SYSTEM_ARCHITECTURE.md` §3.1: protein
  /// 13–20, carbohydrate 55–65, fat 20–25) and add up to exactly 100.
  ///
  /// An earlier version hard-coded 17 / 60 / 23 — also valid, and with a
  /// better rationale even (those are the midpoints of the three ranges). But
  /// the three columns in the database are **per-user** data: the backend
  /// reads them out and returns them from
  /// `GET /profile/nutrition-targets`, so a different hard-coded triple here
  /// makes the app compute a different target from the one the server just
  /// sent — with nothing to report it. Editing a row in the database would
  /// also have no effect at all.
  ///
  /// These three fields can be overwritten once the profile has been synced
  /// from the server.
  int proteinPct = 15;
  int carbsPct = 60;
  int fatPct = 25;

  /// The three energy-bearing macronutrients split into grams.
  ///
  /// 4 kcal/g for protein and carbohydrate, 9 kcal/g for fat — the Atwater
  /// factors.
  ({double protein, double carb, double fat})? get macroTarget {
    final e = energyTarget;
    if (e == null) return null;
    return (
      protein: e * proteinPct / 100 / 4,
      carb: e * carbsPct / 100 / 4,
      fat: e * fatPct / 100 / 9,
    );
  }

  /// The gap between the current weight and the target weight.
  double? get weightDelta {
    final w = weightKg;
    final t = targetWeightKg;
    if (w == null || t == null) return null;
    return t - w;
  }
}
