import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';
import 'package:nutrition_app/data/recommender/menu_builder.dart';
import 'package:nutrition_app/data/recommender/preference_profile.dart';

/// The sample profile: male, 24, 172 cm, 68 kg, moderate activity,
/// maintaining weight.
HealthProfile _sampleProfile() => HealthProfile()
  ..gender = Gender.male
  ..birthday = DateTime(DateTime.now().year - 24, 6, 15)
  ..heightCm = 172
  ..weightKg = 68
  ..goal = HealthGoal.maintain
  ..activity = ActivityLevel.moderate;

void main() {
  final space = FoodVectorSpace.fromFoods(MockFoods.surveyDeck);

  group('The dish feature vector', () {
    test('the dimension count and labels match, and fibre is there', () {
      // These two are kept together: adding a dimension and forgetting its
      // label would make the "why this dish" section annotate the wrong
      // column, with no error reported.
      expect(space.labels.length, equals(space.length));
      expect(space.length, equals(8 + space.categories.length));
      expect(space.labels, contains('Chất xơ'));

      final v = space.encode(MockFoods.surveyDeck.first);
      expect(v.length, equals(space.length));
    });

    test('fibre really does change the vector — not a dead column', () {
      // This check exists because the bug has happened on another
      // dimension: a column present in the schema and in the documentation
      // that no dish carried a value for, so it silently contributed nothing.
      // It is caught here by comparing two dishes that differ only in their
      // fibre.
      final base = MockFoods.surveyDeck.first;
      final low = Food(
        id: '9001', name: 'thử xơ thấp', category: base.category,
        dishRole: base.dishRole, spiceLevel: base.spiceLevel, kcal: base.kcal,
        protein: base.protein, carb: base.carb, fat: base.fat,
        sugar: base.sugar, sodium: base.sodium, fiber: 0,
        servingSizeG: base.servingSizeG,
        emoji: base.emoji, gradient: base.gradient,
      );
      final high = Food(
        id: '9002', name: 'thử xơ cao', category: base.category,
        dishRole: base.dishRole, spiceLevel: base.spiceLevel, kcal: base.kcal,
        protein: base.protein, carb: base.carb, fat: base.fat,
        sugar: base.sugar, sodium: base.sodium, fiber: 12,
        servingSizeG: base.servingSizeG,
        emoji: base.emoji, gradient: base.gradient,
      );

      final spaceWithBoth =
          FoodVectorSpace.fromFoods([...MockFoods.surveyDeck, low, high]);
      final vLow = spaceWithBoth.encode(low);
      final vHigh = spaceWithBoth.encode(high);

      final i = spaceWithBoth.labels.indexOf('Chất xơ');
      expect(vHigh[i], greaterThan(vLow[i]));

      // And the difference has to be in EXACTLY that dimension, not leak
      // into another.
      for (var d = 0; d < spaceWithBoth.length; d++) {
        if (d == i) continue;
        expect(
          vHigh[d],
          equals(vLow[d]),
          reason: 'differs at ${spaceWithBoth.labels[d]}',
        );
      }
    });
  });

  group('Self-stated nutrition goals', () {
    /// Two dishes identical but for their fibre, to separate the goal's
    /// effect from every other feature.
    (Food low, Food high, FoodVectorSpace space) fiberPair() {
      final base = MockFoods.surveyDeck.first;
      Food make(String id, String name, double fiber) => Food(
        id: id, name: name, category: base.category, dishRole: base.dishRole,
        spiceLevel: base.spiceLevel, kcal: base.kcal, protein: base.protein,
        carb: base.carb, fat: base.fat, sugar: base.sugar,
        sodium: base.sodium, fiber: fiber, servingSizeG: base.servingSizeG,
        emoji: base.emoji, gradient: base.gradient,
      );
      final low = make('9101', 'xơ thấp', 0);
      final high = make('9102', 'xơ cao', 12);
      return (
        low, high,
        FoodVectorSpace.fromFoods([...MockFoods.surveyDeck, low, high]),
      );
    }

    test('stating a high-fibre goal scores high-fibre dishes higher', () {
      final (low, high, sp) = fiberPair();
      final neutral = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      final withGoal = neutral.withNutrientGoals({'fiber_g': 0.6});

      // The goal has to CHANGE the ranking, not just the absolute
      // scores.
      expect(
        withGoal.score(high) - withGoal.score(low),
        greaterThan(neutral.score(high) - neutral.score(low)),
      );
    });

    test('a negative sign means wanting less', () {
      final (low, high, sp) = fiberPair();
      final neutral = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      final avoid = neutral.withNutrientGoals({'fiber_g': -0.6});
      expect(avoid.score(high), lessThan(avoid.score(low)));
    });

    test('a goal stated BEFORE any swipe can still rank', () {
      // This case used to be broken: `isEmpty` also consulted
      // `signalCount == 0`, so a goal-only profile returned 0.5 for every
      // dish and the goal the user had just stated was ignored entirely.
      final (low, high, sp) = fiberPair();
      final coldStart =
          PreferenceProfile.empty(sp).withNutrientGoals({'fiber_g': 0.6});

      expect(coldStart.isEmpty, isFalse);
      expect(coldStart.signalCount, equals(0));
      expect(coldStart.score(high), greaterThan(coldStart.score(low)));
    });

    test('a nutrient with no dimension is skipped, not fatal', () {
      final (_, _, sp) = fiberPair();
      final profile = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      // `protein_g` deliberately has NO dimension of its own — the three
      // macro dimensions are shares adding up to 1, so pushing one up pushes
      // the other two down.
      final same = profile.withNutrientGoals({'protein_g': 0.9});
      expect(same.weights, equals(profile.weights));
    });

    test('an empty profile and an all-neutral session are still empty', () {
      // Guards the redefinition of `isEmpty`: loosening it must not change
      // the behaviour of the two earlier cases.
      final sp = FoodVectorSpace.fromFoods(MockFoods.surveyDeck);
      expect(PreferenceProfile.empty(sp).isEmpty, isTrue);
      expect(
        PreferenceProfile.fromSwipes(
          space: sp,
          swipes: [
            for (final f in MockFoods.surveyDeck.take(3))
              (food: f, action: SwipeAction.neutral),
          ],
        ).isEmpty,
        isTrue,
      );
    });
  });

  group('The nutrition requirement module', () {
    test('BMI, BMR and TDEE match the Mifflin-St Jeor formula', () {
      final p = _sampleProfile();

      // BMI = 68 / 1.72² = 22.98
      expect(p.bmi, closeTo(22.99, 0.05));

      // BMR = 10×68 + 6.25×172 − 5×24 + 5 = 680 + 1075 − 120 + 5 = 1640
      expect(p.bmr, closeTo(1640, 1));

      // TDEE = 1640 × 1.55 = 2542
      expect(p.tdee, closeTo(2542, 2));
    });

    test('a weight-loss target never goes below the BMR', () {
      // A small, sedentary person: TDEE − 500 would drop below the BMR
      // without the guard.
      final p = HealthProfile()
        ..gender = Gender.female
        ..birthday = DateTime(DateTime.now().year - 30, 1, 1)
        ..heightCm = 150
        ..weightKg = 45
        ..goal = HealthGoal.loseWeight
        ..activity = ActivityLevel.sedentary;

      expect(p.tdee! - 500, lessThan(p.bmr!));
      expect(p.energyTarget, equals(p.bmr));
    });

    test('the three macronutrients add up to exactly the target', () {
      final p = _sampleProfile();
      final m = p.macroTarget!;
      final kcal = m.protein * 4 + m.carb * 4 + m.fat * 9;

      expect(kcal, closeTo(p.energyTarget!, 1));
    });
  });

  group('The Rocchio preference profile', () {
    test('an "unknown" swipe is dropped from the training set', () {
      final deck = MockFoods.surveyDeck;
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: deck[0], action: SwipeAction.like),
          (food: deck[1], action: SwipeAction.unknown),
          (food: deck[2], action: SwipeAction.unknown),
        ],
      );

      expect(profile.signalCount, equals(1));
    });

    test('a liked dish scores higher than a disliked one', () {
      // The two dishes have to be in different groups, because the food
      // group is the only one-hot axis in the vector — two dishes in the same
      // group leave only the nutrition to tell them apart and the test loses
      // its meaning.
      final deck = MockFoods.surveyDeck;
      final liked = deck.first;
      final hated = deck.firstWhere((f) => f.category != liked.category);

      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: liked, action: SwipeAction.like),
          (food: hated, action: SwipeAction.dislike),
        ],
      );

      expect(profile.score(liked), greaterThan(profile.score(hated)));
    });

    test('an empty profile scores every dish equally', () {
      final profile = PreferenceProfile.empty(space);
      final scores = MockFoods.surveyDeck.map(profile.score).toSet();

      expect(scores.length, equals(1));
      expect(scores.first, equals(0.5));
    });

    test('the jittered vector departs from the original but stays near', () {
      final deck = MockFoods.surveyDeck;
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          for (final f in deck.take(10)) (food: f, action: SwipeAction.like),
        ],
      );

      final jittered = profile.jittered(delta: 0.35, rng: math.Random(42));

      final cos = cosineSimilarity(profile.weights, jittered.weights);

      // Genuinely different — not a copy.
      expect(cos, lessThan(0.999));
      // But still in the same direction, meaning an exploration dish lands
      // in the neighbourhood of the user's taste rather than somewhere absurd
      // as a random ε-greedy pick would.
      expect(cos, greaterThan(0.5));
    });
  });

  group('Plan generation — Step 4', () {
    /// Builds a plan for a profile that has already swiped.
    DailyPlan buildPlan({int seed = 7, double exploration = 0.3}) {
      final deck = MockFoods.surveyDeck;
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          for (var i = 0; i < deck.length; i++)
            (
              food: deck[i],
              action: i % 3 == 0
                  ? SwipeAction.like
                  : i % 3 == 1
                  ? SwipeAction.neutral
                  : SwipeAction.dislike,
            ),
        ],
      );

      final health = _sampleProfile();
      final macro = health.macroTarget!;

      return MenuBuilder(
        candidates: deck,
        profile: profile,
        explorationRatio: exploration,
        rng: math.Random(seed),
      ).build(
        date: DateTime(2026, 9, 15),
        targetKcal: health.energyTarget!,
        targetProtein: macro.protein,
        targetCarb: macro.carb,
        targetFat: macro.fat,
      );
    }

    test('all four meals are present', () {
      final plan = buildPlan();
      expect(plan.slots.map((s) => s.type), equals(MealType.values));
    });

    test('no dish repeats within one day', () {
      final plan = buildPlan();
      final ids = plan.allItems.map((i) => i.food.id).toList();

      expect(ids.toSet().length, equals(ids.length));
    });

    test('each meal has all its required dish roles', () {
      final plan = buildPlan();

      Set<String> rolesOf(MealType type) => plan.slots
          .firstWhere((s) => s.type == type)
          .items
          .map((i) => i.food.dishRole)
          .toSet();

      expect(rolesOf(MealType.breakfast), contains('Món chính'));
      expect(rolesOf(MealType.lunch), containsAll({'Món chính', 'Món mặn'}));
      expect(rolesOf(MealType.dinner), containsAll({'Món chính', 'Món rau'}));
      expect(rolesOf(MealType.snack), contains('Món phụ'));
    });

    test('no two dishes share a role within one meal', () {
      // Step 4's "no two dishes of the same food group in S" constraint —
      // it avoids a lunch of two savoury dishes and nothing else.
      final plan = buildPlan();

      for (final slot in plan.slots) {
        final roles = slot.items.map((i) => i.food.dishRole).toList();
        expect(
          roles.toSet().length,
          equals(roles.length),
          reason: '${slot.type.label} has a repeated dish role: $roles',
        );
      }
    });

    test('the energy deviation does not exceed 10 per cent', () {
      // Run over several different seeds: the thesis proposal's commitment
      // is for every user, not luck on one run.
      for (var seed = 0; seed < 10; seed++) {
        final plan = buildPlan(seed: seed);
        expect(
          plan.deviationPct.abs(),
          lessThanOrEqualTo(10),
          reason:
              'hạt giống $seed lệch ${plan.deviationPct.toStringAsFixed(1)}%',
        );
        expect(plan.withinTolerance, isTrue);
      }
    });

    test('the exploration ratio is hard-capped at 50 per cent', () {
      final plan = buildPlan(exploration: 0.9);
      expect(plan.explorationRatio, lessThanOrEqualTo(0.5));
    });

    test('with exploration off, no serving is an exploration one', () {
      final plan = buildPlan(exploration: 0);
      expect(plan.allItems.any((i) => i.isExploration), isFalse);
    });

    test('with exploration on, the plan is more varied than with it off', () {
      // This is the filter-bubble measurement: run the two configurations
      // side by side and count the distinct dishes appearing across several
      // days.
      Set<String> idsOver(int days, double exploration) {
        final ids = <String>{};
        for (var d = 0; d < days; d++) {
          ids.addAll(
            buildPlan(
              seed: d,
              exploration: exploration,
            ).allItems.map((i) => i.food.id),
          );
        }
        return ids;
      }

      final withExploration = idsOver(14, 0.3);
      final without = idsOver(14, 0);

      expect(withExploration.length, greaterThan(without.length));
    });
  });
}
