import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';
import 'package:nutrition_app/data/recommender/menu_builder.dart';
import 'package:nutrition_app/data/recommender/nutrient_target.dart';
import 'package:nutrition_app/data/recommender/preference_profile.dart';
import 'package:nutrition_app/data/session.dart';

/// The allowance shared by every check in this file.
const _kcal = 2000.0;
const _protein = 100.0;
const _carb = 250.0;
const _fat = 60.0;

/// A synthetic catalogue: every role has both a **mild / high-fibre** and a
/// **salty / low-fibre** option, so every threshold in this file is
/// **satisfiable**.
///
/// It has to be built by hand rather than using `MockFoods.surveyDeck`: the
/// 30-dish mock set is too salty (5,850 mg of sodium in a day) for any sodium
/// threshold to be reachable, and the checks could then not tell "the
/// algorithm is wrong" from "the catalogue has too few dishes".
List<Food> _syntheticCatalog() {
  var id = 1;
  Food make({
    required String role,
    required int kcal,
    required double sodium,
    required double fiber,
    required String name,
  }) => Food(
    id: '${id++}',
    name: name,
    category: 'Món nước',
    dishRole: role,
    spiceLevel: 0,
    kcal: kcal,
    protein: kcal * 0.05,
    carb: kcal * 0.1,
    fat: kcal * 0.02,
    sugar: 2,
    sodium: sodium,
    fiber: fiber,
    // 200 g is the catalogue's most common serving (48 of 318 dishes).
    servingSizeG: 200,
    emoji: '🍚',
    gradient: const [Color(0xFFFFFFFF), Color(0xFF000000)],
  );

  final out = <Food>[];
  // The roles follow MenuBuilder's `_mealStructure`.
  for (final role in ['Món chính', 'Món phụ', 'Món canh', 'Món mặn', 'Món rau']) {
    for (var k = 0; k < 4; k++) {
      final kcal = 200 + k * 120;
      out.add(make(
        role: role, kcal: kcal, sodium: 60, fiber: 7,
        name: '$role nhạt nhiều xơ $k',
      ));
      out.add(make(
        role: role, kcal: kcal, sodium: 900, fiber: 0.2,
        name: '$role mặn ít xơ $k',
      ));
    }
  }
  return out;
}

PreferenceProfile _profileOver(List<Food> catalog, {bool likeSalty = true}) {
  final space = FoodVectorSpace.fromFoods(catalog);
  // Deliberately prefers the **salty, low-fibre** group, so the constraint
  // has to work against the taste. Were the taste already aligned with the
  // constraint, the check would pass even if phase 5 did nothing at all.
  final liked = catalog.where(
    (f) => likeSalty ? f.sodium > 500 : f.sodium < 500,
  );
  return PreferenceProfile.fromSwipes(
    space: space,
    swipes: [for (final f in liked) (food: f, action: SwipeAction.like)],
  );
}

DailyPlan _build(
  List<Food> catalog,
  PreferenceProfile profile,
  List<NutrientTarget> targets, {
  int seed = 3,
}) => MenuBuilder(
  candidates: catalog,
  profile: profile,
  explorationRatio: 0,
  nutrientTargets: targets,
  rng: math.Random(seed),
).build(
  date: DateTime(2026, 10, 14),
  targetKcal: _kcal,
  targetProtein: _protein,
  targetCarb: _carb,
  targetFat: _fat,
);

void main() {
  group('NutrientTarget — the violation arithmetic', () {
    test('floor and ceiling point the right way, as a fraction', () {
      const floor = NutrientTarget.atLeast('fiber_g', 25);
      expect(floor.violation(25), equals(0));
      expect(floor.violation(30), equals(0));
      expect(floor.violation(20), closeTo(0.2, 1e-9));

      const ceiling = NutrientTarget.atMost('sodium_mg', 2000);
      expect(ceiling.violation(2000), equals(0));
      expect(ceiling.violation(1500), equals(0));
      expect(ceiling.violation(2400), closeTo(0.2, 1e-9));
    });

    test('a fraction makes two nutrients in different units comparable', () {
      // Being 5 g short of a 25 g fibre floor is far more serious than
      // being 5 mg over a 2000 mg sodium ceiling. Measured in absolute
      // amounts the two are equal, and phase 5 would go and fix the wrong
      // one.
      const fiber = NutrientTarget.atLeast('fiber_g', 25);
      const sodium = NutrientTarget.atMost('sodium_mg', 2000);
      expect(fiber.violation(20), greaterThan(sodium.violation(2005)));
    });

    test('purine_mg is outside what can be enforced', () {
      expect(NutrientTarget.supported.contains('purine_mg'), isFalse);
      expect(NutrientTarget.valueOf(MockFoods.surveyDeck.first, 'purine_mg'),
          isNull);
    });
  });

  group('Step 4 phase 5 — the day-level micronutrient constraints', () {
    test('the sodium ceiling is enforced when the catalogue allows', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final without = _build(catalog, profile, const []);
      final with_ = _build(
        catalog, profile, const [NutrientTarget.atMost('sodium_mg', 2000)],
      );

      expect(without.totalOf('sodium_mg'), greaterThan(2000),
          reason: 'with no constraint it must be violated, otherwise '
              'the check is meaningless');
      expect(with_.totalOf('sodium_mg'), lessThanOrEqualTo(2000));
      expect(with_.nutrientViolations, isEmpty);
      expect(with_.meetsNutrientTargets, isTrue);
    });

    test('the fibre floor is enforced when the catalogue allows', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final without = _build(catalog, profile, const []);
      final with_ = _build(
        catalog, profile, const [NutrientTarget.atLeast('fiber_g', 25)],
      );

      expect(without.totalOf('fiber_g'), lessThan(25));
      expect(with_.totalOf('fiber_g'), greaterThanOrEqualTo(25));
      expect(with_.nutrientViolations, isEmpty);
    });

    test('a satisfied constraint is not broken to fix another', () {
      // This is phase 5's easiest condition to get wrong: closing a fibre
      // gap by stuffing in high-sodium dishes gives someone with
      // hypertension a plan that meets its fibre goal while breaching the
      // very threshold that matters to them.
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final plan = _build(catalog, profile, const [
        NutrientTarget.atLeast('fiber_g', 25),
        NutrientTarget.atMost('sodium_mg', 2000),
      ]);

      expect(plan.totalOf('fiber_g'), greaterThanOrEqualTo(25));
      expect(plan.totalOf('sodium_mg'), lessThanOrEqualTo(2000));
      expect(plan.nutrientViolations, isEmpty);
    });

    test('the energy deviation is never pushed past 10 %', () {
      // Satisfying a micronutrient constraint by breaking the energy target
      // is curing one violation by creating another.
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      for (var seed = 0; seed < 8; seed++) {
        final plan = _build(catalog, profile, const [
          NutrientTarget.atLeast('fiber_g', 25),
          NutrientTarget.atMost('sodium_mg', 2000),
        ], seed: seed);

        expect(plan.deviationPct.abs(), lessThanOrEqualTo(10.0),
            reason: 'seed $seed deviates by ${plan.deviationPct}%');
      }
    });

    test('no duplicate dish is produced within a day', () {
      // The same class of bug already happened in phase 3: swapping without
      // updating `usedIds` lets one dish land in two meals.
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      for (var seed = 0; seed < 8; seed++) {
        final plan = _build(catalog, profile, const [
          NutrientTarget.atLeast('fiber_g', 25),
          NutrientTarget.atMost('sodium_mg', 2000),
        ], seed: seed);

        final ids = plan.allItems.map((i) => i.food.id).toList();
        expect(ids.toSet().length, equals(ids.length),
            reason: 'seed $seed has a duplicate dish');
      }
    });

    test('too thin a catalogue REPORTS the violation, never hides it', () {
      // The 30-dish mock set is too salty to reach 2000 mg. The right
      // behaviour is to improve as far as possible and then say so, not to
      // return a plan that looks as if it met the limit.
      final deck = MockFoods.surveyDeck;
      final space = FoodVectorSpace.fromFoods(deck);
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          for (var i = 0; i < deck.length; i++)
            (
              food: deck[i],
              action: i % 3 == 0 ? SwipeAction.like : SwipeAction.neutral,
            ),
        ],
      );

      final without = _build(deck, profile, const []);
      final with_ = _build(
        deck, profile, const [NutrientTarget.atMost('sodium_mg', 2000)],
      );

      expect(with_.totalOf('sodium_mg')!, lessThan(without.totalOf('sodium_mg')!),
          reason: 'it still has to improve as far as it can');
      expect(with_.nutrientViolations, hasLength(1));
      expect(with_.nutrientViolations.first.target.nutrient,
          equals('sodium_mg'));
      expect(with_.meetsNutrientTargets, isFalse);
    });

    test('an unenforceable constraint is not treated as satisfied', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final plan = _build(
        catalog, profile, const [NutrientTarget.atMost('purine_mg', 400)],
      );

      // The purine total reads as 0 because `Food` does not carry it. Folded
      // into `nutrientViolations` it would appear to have MET the gout limit
      // on a plan whose purine was never checked at all.
      expect(plan.nutrientViolations, isEmpty);
      expect(plan.unenforceableTargets, hasLength(1));
      expect(plan.meetsNutrientTargets, isFalse);
    });

    test('AppSession passes the constraints down to the plan', () async {
      // If this wiring breaks, phase 5 is dead code: every check above
      // would still be green, because they call MenuBuilder directly.
      final session = AppSession(rng: math.Random(5))
        ..profile.gender = Gender.male
        ..profile.birthday = DateTime(DateTime.now().year - 24, 6, 15)
        ..profile.heightCm = 172
        ..profile.weightKg = 68
        ..profile.goal = HealthGoal.maintain
        ..profile.activity = ActivityLevel.moderate
        ..explorationRatio = 0;

      expect(await session.regeneratePlan(), isTrue);
      expect(session.plan!.nutrientTargets, isEmpty);
      final sodiumWithout = session.plan!.totalOf('sodium_mg');

      // Through the DECLARATION, not by setting the thresholds directly.
      // `nutrientTargets` used to be a plain field that only this test ever
      // assigned, which is how the whole chain stayed broken while the test
      // stayed green: the rule set had the 2 000 mg ceiling, the day-budget
      // card showed it, and the builder never saw it. Declaring the
      // condition is the path a user actually takes.
      session.profile.conditions.add('hypertension');
      expect(await session.regeneratePlan(), isTrue);

      expect(session.plan!.nutrientTargets, hasLength(1));
      expect(
        session.plan!.nutrientTargets.single.amount,
        2000,
        reason: 'the ceiling comes from `mock_rules._dayThresholds`',
      );
      expect(session.plan!.totalOf('sodium_mg')!, lessThan(sodiumWithout!));
    });

    test('with no constraint at all, phase 5 changes nothing', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final a = _build(catalog, profile, const []);
      final b = _build(catalog, profile, const [
        NutrientTarget.atMost('purine_mg', 400), // ngoài tầm → bỏ qua
      ]);

      expect(
        b.allItems.map((i) => i.food.id).toList(),
        equals(a.allItems.map((i) => i.food.id).toList()),
      );
    });
  });
}
