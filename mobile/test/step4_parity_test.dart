import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';
import 'package:nutrition_app/data/recommender/menu_builder.dart';
import 'package:nutrition_app/data/recommender/nutrient_target.dart';
import 'package:nutrition_app/data/recommender/preference_profile.dart';

/// A cross-check: Step 4 in Dart and Step 4 in Python have to build **the
/// same plan**.
///
/// `ml/menu_builder.py` is a port of `menu_builder.dart`, and the Dart one
/// stays — it is what the app falls back to when the ML service cannot be
/// reached. Two implementations of the same five phases is the situation
/// `tools/check_be_parity.py` was written for, after three implementations of
/// Step 1 drifted apart with nothing reporting it. A drift here is just as
/// quiet: both sides return a plan, both plans look like plans, and only the
/// dishes differ.
///
/// The fixture comes from the real catalogue via
/// `python tools/check_step4_parity.py`, and carries the inputs **and** the
/// plan Python built from them, so this test needs no database.
///
/// ## Two things are switched off, on purpose
///
/// **Exploration.** The 70-30 mechanism draws Gaussian noise, and Dart's
/// `math.Random` is not Python's `random`: the same seed gives different
/// numbers, so an exploration serving cannot be compared dish for dish. At
/// `explorationRatio = 0` all five phases are deterministic on both sides.
///
/// **The model score.** This side has no model to consult, so the comparable
/// path is the cosine one; the blend is checked in `tools/check_step4.py`.
///
/// ## The dish roles in the fixture are translated
///
/// `foods.dish_role` in the database is an ENUM of English codes — `main`,
/// `side_protein`, … — while `_mealStructure` in `menu_builder.dart` is keyed
/// on Vietnamese labels that come from `MockFoods`. The fixture writes the
/// labels, so this test compares the two **algorithms**. It does not prove
/// this side works against the database: it cannot, until `Food.dishRole`
/// becomes an enum carrying the schema's codes, the way [MealType] already
/// carries `'breakfast'`. `dishRoleCode` is in the fixture beside each food
/// so that the day that lands, this test needs one line changed.
const double _tolerance = 1e-9;

const _grey = [Color(0xFFCCCCCC), Color(0xFF888888)];

Food _foodFromFixture(Map<String, dynamic> j) => Food(
  id: j['id'] as String,
  name: j['name'] as String,
  category: j['category'] as String,
  dishRole: j['dishRole'] as String,
  spiceLevel: j['spiceLevel'] as int,
  kcal: j['kcal'] as int,
  protein: (j['protein'] as num).toDouble(),
  carb: (j['carb'] as num).toDouble(),
  fat: (j['fat'] as num).toDouble(),
  sugar: (j['sugar'] as num).toDouble(),
  sodium: (j['sodium'] as num).toDouble(),
  fiber: (j['fiber'] as num).toDouble(),
  servingSizeG: (j['servingSizeG'] as num).toDouble(),
  emoji: '🍚',
  gradient: _grey,
);

NutrientTarget _targetFromFixture(Map<String, dynamic> j) {
  final nutrient = j['nutrient'] as String;
  final amount = (j['amount'] as num).toDouble();
  return (j['isFloor'] as bool)
      ? NutrientTarget.atLeast(nutrient, amount)
      : NutrientTarget.atMost(nutrient, amount);
}

void main() {
  final file = File('test/fixtures/step4_parity.json');

  group('Step 4 — the Dart side builds the same plan as the Python side', () {
    setUpAll(() {
      expect(
        file.existsSync(),
        isTrue,
        reason:
            'The fixture ${file.path} is missing. Generate it with: '
            'python tools/check_step4_parity.py --fixture-only',
      );
    });

    final fixture =
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final foods = (fixture['foods'] as List)
        .map((j) => _foodFromFixture(j as Map<String, dynamic>))
        .toList();
    final targets = fixture['targets'] as Map<String, dynamic>;
    final params = fixture['params'] as Map<String, dynamic>;
    final profileJson = fixture['profile'] as Map<String, dynamic>;
    final expected = fixture['expected'] as Map<String, dynamic>;
    final expectedMeals = (expected['meals'] as List)
        .cast<Map<String, dynamic>>();

    final space = FoodVectorSpace.fromFoods(foods);

    DailyPlan buildPlan() {
      final profile = PreferenceProfile(
        space: space,
        weights: (profileJson['weights'] as List)
            .map((x) => (x as num).toDouble())
            .toList(),
        signalCount: profileJson['signalCount'] as int,
      );

      final builder = MenuBuilder(
        candidates: foods,
        profile: profile,
        explorationRatio: (params['explorationRatio'] as num).toDouble(),
        explorationDelta: (params['explorationDelta'] as num).toDouble(),
        energyPenalty: (params['energyPenalty'] as num).toDouble(),
        macroPenalty: (params['macroPenalty'] as num).toDouble(),
        localSearchRounds: params['localSearchRounds'] as int,
        nutrientRepairRounds: params['nutrientRepairRounds'] as int,
        maxEnergyDeviation: (params['maxEnergyDeviation'] as num).toDouble(),
        nutrientTargets: (fixture['nutrientTargets'] as List)
            .map((j) => _targetFromFixture(j as Map<String, dynamic>))
            .toList(),
      );

      return builder.build(
        date: DateTime.parse(fixture['planDate'] as String),
        targetKcal: (targets['kcal'] as num).toDouble(),
        targetProtein: (targets['protein'] as num).toDouble(),
        targetCarb: (targets['carb'] as num).toDouble(),
        targetFat: (targets['fat'] as num).toDouble(),
      );
    }

    test('the fixture holds a catalogue and a plan', () {
      expect(foods, isNotEmpty);
      expect(expectedMeals.length, 4);
      expect(
        expectedMeals.expand((m) => m['items'] as List).length,
        greaterThan(0),
        reason: 'a fixture whose plan is empty would compare nothing',
      );
    });

    test('the feature space agrees — otherwise no score can agree', () {
      // The weights in the fixture were built against the Python space, so a
      // different number of dimensions here means every cosine is computed
      // against a different vector. `tools/check_feature_parity.py` is what
      // guards this in detail; this is the one assertion that keeps a
      // mismatch from being reported as a Step 4 difference.
      expect(
        space.length,
        (profileJson['weights'] as List).length,
        reason:
            'The profile vector has ${(profileJson['weights'] as List).length} '
            'dimensions, this space has ${space.length}. Regenerate the '
            'fixture, then run tools/check_feature_parity.py.',
      );
    });

    test('this side reads the same meal structure', () {
      // Compared through the plan rather than by reading `_mealStructure`,
      // which is private: every required role Python placed has to appear in
      // the same meal here.
      final structure = fixture['mealStructure'] as Map<String, dynamic>;
      final plan = buildPlan();
      for (final slot in plan.slots) {
        final shape = structure[slot.type.code] as Map<String, dynamic>;
        final roles = slot.items.map((i) => i.food.dishRole).toSet();
        for (final role in (shape['required'] as List).cast<String>()) {
          expect(
            roles,
            contains(role),
            reason:
                '${slot.type.code} is missing its required role $role. If '
                'every role is missing, the two sides disagree about the '
                'role vocabulary, not about the algorithm.',
          );
        }
      }
    });

    test('every meal holds the same dishes, in the same order', () {
      final plan = buildPlan();
      expect(
        plan.slots.map((s) => s.type.code).toList(),
        expectedMeals.map((m) => m['mealType'] as String).toList(),
        reason: 'the meals themselves have to come out in the same order',
      );

      for (var i = 0; i < plan.slots.length; i++) {
        final slot = plan.slots[i];
        final want = expectedMeals[i];
        final wantItems = (want['items'] as List).cast<Map<String, dynamic>>();

        expect(
          slot.items.map((it) => it.food.id).toList(),
          wantItems.map((it) => it['foodId'] as String).toList(),
          reason:
              'The dishes of ${slot.type.code} differ. Python picked '
              '${wantItems.map((it) => it['foodId']).join(', ')}; this side '
              'picked ${slot.items.map((it) => it.food.id).join(', ')}.',
        );
        expect(
          slot.items.map((it) => it.food.dishRole).toList(),
          wantItems.map((it) => it['dishRole'] as String).toList(),
          reason: 'and in the same roles',
        );
      }
    });

    test('the preference scores agree', () {
      final plan = buildPlan();
      for (var i = 0; i < plan.slots.length; i++) {
        final slot = plan.slots[i];
        final wantItems =
            (expectedMeals[i]['items'] as List).cast<Map<String, dynamic>>();
        for (var k = 0; k < slot.items.length; k++) {
          expect(
            slot.items[k].score,
            closeTo((wantItems[k]['score'] as num).toDouble(), _tolerance),
            reason:
                'score of ${slot.items[k].food.name} in ${slot.type.code}. '
                'A difference here with the same dishes means the two cosine '
                'implementations disagree, not the two plans.',
          );
        }
      }
    });

    test('the energy and macro totals agree', () {
      final plan = buildPlan();
      expect(
        plan.actualKcal,
        closeTo((expected['actualKcal'] as num).toDouble(), _tolerance),
      );
      expect(
        plan.actualProtein,
        closeTo((expected['actualProtein'] as num).toDouble(), _tolerance),
      );
      expect(
        plan.actualCarb,
        closeTo((expected['actualCarb'] as num).toDouble(), _tolerance),
      );
      expect(
        plan.actualFat,
        closeTo((expected['actualFat'] as num).toDouble(), _tolerance),
      );
      expect(
        plan.deviationPct,
        closeTo((expected['deviationPct'] as num).toDouble(), 1e-6),
      );
      for (var i = 0; i < plan.slots.length; i++) {
        expect(
          plan.slots[i].actualKcal,
          closeTo(
            (expectedMeals[i]['actualKcal'] as num).toDouble(),
            _tolerance,
          ),
          reason: 'per-meal energy for ${plan.slots[i].type.code}',
        );
      }
    });

    test('phase 5 reaches the same verdict on the nutrient targets', () {
      final plan = buildPlan();
      final wantViolations = (expected['nutrientViolations'] as List)
          .cast<Map<String, dynamic>>();
      expect(
        plan.nutrientViolations.map((v) => v.target.nutrient).toList(),
        wantViolations.map((v) => v['nutrient'] as String).toList(),
        reason:
            'The two sides disagree about which day-level thresholds the plan '
            'fails. This is the safety-relevant half of Step 4: a plan that '
            'breaches a limit on one side and not the other is one of them '
            'reporting a plan as safe when it is not.',
      );
      for (final violation in plan.nutrientViolations) {
        final want = wantViolations.firstWhere(
          (v) => v['nutrient'] == violation.target.nutrient,
        );
        expect(
          violation.actual,
          closeTo((want['actual'] as num).toDouble(), _tolerance),
        );
      }
    });

    test('no dish is served twice in one day', () {
      // Not a comparison — a property both sides must hold. It is the
      // `usedIds` bookkeeping between phase 3 and the next meal, and it fails
      // silently: the plan still has the right shape, one dish just appears
      // in two meals.
      final plan = buildPlan();
      final ids = plan.allItems.map((i) => i.food.id).toList();
      expect(ids.toSet().length, ids.length, reason: 'repeated: $ids');
    });

    test('nothing is an exploration serving at ratio 0', () {
      final plan = buildPlan();
      expect(
        plan.allItems.where((i) => i.isExploration),
        isEmpty,
        reason:
            'The comparison is only valid while no serving is drawn with '
            'noise — the two languages do not share a random generator.',
      );
      expect(plan.actualExplorationRatio, 0);
    });
  });
}
