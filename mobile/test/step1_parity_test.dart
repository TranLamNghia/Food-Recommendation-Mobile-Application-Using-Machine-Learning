import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';

/// The Dart implementation of Step 1 has to match the Python reference,
/// number for number.
///
/// The same case file `backend/Api.Tests/Step1ParityTests.cs` uses, so all
/// three implementations are locked onto ONE set of numbers:
///
///     tools/gen_step1_cases.py                   Python, the reference
///     backend/Api/Nutrition/NutritionTargets.cs  C#, the server
///     mobile/lib/data/models/health_profile.dart Dart, the app  <- here
///
/// Why it is needed. The three run in three layers and never meet, so when
/// they drift **nothing reports it**: the app shows one target, the server
/// generates a plan from a different one, and both numbers look plausible.
/// That has happened — the Dart side once hard-coded a 17/60/23 macro split
/// while the database's `DEFAULT` column and the API specification both said
/// 15/60/25.
void main() {
  final root = _findRepoRoot();
  final file = File('${root.path}/data/step1_cases.json');

  if (!file.existsSync()) {
    test('the case file is missing', () {
      fail('${file.path} is missing\n'
          'Generate it with: python tools/gen_step1_cases.py');
    });
    return;
  }

  final fixture = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
  final cases = (fixture['cases'] as List).cast<Map<String, dynamic>>();

  group('Step 1 — Dart matches the Python reference', () {
    for (final item in cases) {
      final name = item['name'] as String;
      final input = item['input'] as Map<String, dynamic>;
      final expected = item['expected'] as Map<String, dynamic>;

      test(name, () {
        final gender = input['gender'] as String;

        // Dart's `Gender` only has male and female — the app never shows a
        // third option. But the `health_profiles.gender` ENUM does have
        // `other`, and the server has to handle what the schema permits.
        // Those cases are skipped here, NOT made to pass falsely.
        //
        // The wording of this reason is a contract with
        // `tools/check_be_parity.py`: that script greps this line out of the
        // test output to report the gap. Editing the sentence without
        // editing the grep makes the gap silently stop being reported.
        if (gender == 'other') {
          markTestSkipped(
            "Dart's Gender has no 'other'; the C# side handles it with the "
            'midpoint of the two Mifflin constants — see '
            'NutritionTargets.MifflinOther',
          );
          return;
        }

        final profile = HealthProfile()
          ..gender = gender == 'male' ? Gender.male : Gender.female
          ..birthday = DateTime.parse(input['dateOfBirth'] as String)
          ..heightCm = (input['heightCm'] as num).toDouble()
          ..weightKg = (input['weightKg'] as num).toDouble()
          ..activity = ActivityLevel.values.firstWhere(
            (a) => a.code == input['activityLevel'],
          )
          ..goal = HealthGoal.values.firstWhere((g) => g.code == input['goal'])
          ..proteinPct = input['proteinPct'] as int
          ..carbsPct = input['carbsPct'] as int
          ..fatPct = input['fatPct'] as int
          // Pin "today" to the fixture's value. Without this line every case
          // whose age differs from the age computed today would be skipped —
          // that is, nearly all of them, for nearly the whole year, while
          // the suite still reported success.
          ..today = DateTime.parse(input['today'] as String);

        // The age has to match; it is never skipped. This suite used to skip
        // every case whose age was off, because `HealthProfile.age` always
        // read `DateTime.now()`. Now that `HealthProfile.today` takes a
        // reference date, this comparison really compares.
        expect(profile.age, expected['age'], reason: 'age');

        expect(_round(profile.bmi!, 2), expected['bmi'], reason: 'bmi');
        expect(_round(profile.bmr!, 0), expected['bmrKcal'], reason: 'bmrKcal');
        expect(
          _round(profile.tdee!, 0),
          expected['tdeeKcal'],
          reason: 'tdeeKcal',
        );
        expect(
          profile.activity!.factor,
          expected['activityFactor'],
          reason: 'activityFactor',
        );
        expect(
          _round(profile.energyTarget!, 0),
          expected['dailyCaloriesTarget'],
          reason: 'dailyCaloriesTarget',
        );

        final macro = profile.macroTarget!;
        expect(_round(macro.protein, 1), expected['proteinG'],
            reason: 'proteinG');
        expect(_round(macro.carb, 1), expected['carbsG'], reason: 'carbsG');
        expect(_round(macro.fat, 1), expected['fatG'], reason: 'fatG');

        final expectedMeals = expected['mealKcal'] as Map<String, dynamic>;
        for (final m in MealType.values) {
          expect(
            _round(profile.energyTarget! * m.energyShare, 0),
            expectedMeals[m.code],
            reason: 'mealKcal.${m.code}',
          );
        }
      });
    }
  });

  test('MealType meal shares match the fixture, in both directions', () {
    final shares = (fixture['mealShare'] as Map<String, dynamic>);
    expect(
      MealType.values.map((m) => m.code).toList()..sort(),
      shares.keys.toList()..sort(),
    );
    for (final m in MealType.values) {
      expect(m.energyShare, shares[m.code], reason: m.code);
    }
    // The four shares have to add up to exactly 1. A set adding up to 0.95
    // causes no error at all — Step 4 would simply allocate 5 % less energy
    // every day.
    final total = MealType.values.fold<double>(0, (s, m) => s + m.energyShare);
    expect(total, closeTo(1.0, 1e-12));
  });

  test('ActivityLevel factors match the fixture, in both directions', () {
    final factors = (fixture['activityFactor'] as Map<String, dynamic>);
    expect(
      ActivityLevel.values.map((a) => a.code).toList()..sort(),
      factors.keys.toList()..sort(),
    );
    for (final a in ActivityLevel.values) {
      expect(a.factor, factors[a.code], reason: a.code);
    }
  });

  test("the three default macro shares add up to 100 and match the schema's "
      'DEFAULT', () {
    final p = HealthProfile();
    expect(p.proteinPct + p.carbsPct + p.fatPct, 100);
    // Exactly the `DEFAULT` of the three target_*_pct columns in
    // db/schema.sql.
    expect([p.proteinPct, p.carbsPct, p.fatPct], [15, 60, 25]);
  });
}

/// Rounds away from zero, like the Python side and like
/// `MidpointRounding.AwayFromZero`.
///
/// Dart's `double.round()` rounds away from zero on .5, so a multiply and
/// divide is enough to pick the number of decimal places. But a very small
/// epsilon has to be added: multiplying a `double` by 100 can give
/// 2314.9999999999995 instead of 2315, and `.round()` then returns 2314 — off
/// by one in the last digit, exactly the kind of error only a parity suite
/// catches.
num _round(double v, int places) {
  final factor = [1, 10, 100][places];
  final scaled = v * factor;
  final sign = scaled.isNegative ? -1 : 1;
  final rounded = ((scaled.abs() + 1e-9).round()) * sign;
  return places == 0 ? rounded : rounded / factor;
}

/// Walks up from the run directory to the repository root, by the
/// `db/schema.sql` MARKER.
///
/// `flutter test` runs with `mobile/` as the current directory, but the
/// number of levels is not counted: it changes with how the command is
/// invoked.
Directory _findRepoRoot() {
  var d = Directory.current;
  while (!File('${d.path}/db/schema.sql').existsSync()) {
    final parent = d.parent;
    if (parent.path == d.path) {
      throw StateError(
        'Could not find the repository root from ${Directory.current.path}',
      );
    }
    d = parent;
  }
  return d;
}
