// OFFLINE: the F1 filter reaching the plan, which it did not used to.

import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/session.dart';

AppSession _ready({Iterable<String> conditions = const []}) {
  final session = AppSession(rng: math.Random(7))
    ..profile.gender = Gender.male
    ..profile.birthday = DateTime(DateTime.now().year - 24, 6, 15)
    ..profile.heightCm = 172
    ..profile.weightKg = 68
    ..profile.goal = HealthGoal.maintain
    ..profile.activity = ActivityLevel.moderate;
  session.profile.conditions.addAll(conditions);
  return session;
}

void main() {
  group('the declared conditions reach the offline plan', () {
    /// The defect this file exists for.
    ///
    /// `MenuBuilder`'s own documentation requires it of its caller — "the F1
    /// filter has to run **first** and pass in an already-safe dish set as
    /// `candidates`" — and nothing did. The conditions reached
    /// `session.screening`, which the excluded-dishes card reads, and never
    /// the builder. So one session showed a plan containing seafood and, in
    /// the card underneath it, those same dishes listed as excluded.
    test('a seafood allergy keeps seafood out of the plan', () {
      final allergic = _ready(conditions: ['allergy_seafood']);

      expect(allergic.regeneratePlan(), isTrue);
      final plan = allergic.plan!;

      expect(plan.allItems, isNotEmpty);
      expect(
        plan.allItems.where((i) => i.food.tags.contains('Có hải sản')),
        isEmpty,
        reason: 'the mock deck has seven seafood dishes and none may be here',
      );
      // And the two views of the same session now agree, which is the part
      // that was visibly wrong before.
      final excluded = allergic.screening.excluded.keys.toSet();
      expect(
        plan.allItems.map((i) => i.food.id).where(excluded.contains),
        isEmpty,
        reason: 'no dish may be in the plan and on the excluded list at once',
      );
    });

    /// The `require_tag` direction, which the offline copy had no mechanism
    /// for: a vegan diet keeps only the dishes that carry the tag instead of
    /// dropping the ones that do.
    test('a vegan diet leaves only vegan dishes, and still builds a day', () {
      final vegan = _ready(conditions: ['vegan']);

      expect(vegan.regeneratePlan(), isTrue);
      final plan = vegan.plan!;

      expect(plan.allItems, isNotEmpty);
      expect(
        plan.allItems.every((i) => i.food.tags.contains('Món thuần chay')),
        isTrue,
        reason: 'got ${plan.allItems.map((i) => i.food.name).toList()}',
      );
      // Breakfast, lunch and dinner each need a `Món chính`, and none of the
      // original thirty mock dishes was a vegetarian one — which is why the
      // deck gained two.
      expect(
        plan.allItems.where((i) => i.food.dishRole == 'Món chính'),
        isNotEmpty,
      );
    });

    test('with nothing declared the whole deck is still available', () {
      final plain = _ready();

      expect(plain.regeneratePlan(), isTrue);
      expect(plain.screening.excluded, isEmpty);
      expect(plain.plan!.allItems, isNotEmpty);
    });

    /// A blocked dish and a medically excluded one are different reasons that
    /// have to compose: the filter runs first, and the block is subtracted
    /// from what it leaves.
    test('a block and an allergy both apply', () async {
      final session = _ready(conditions: ['allergy_seafood']);
      expect(session.regeneratePlan(), isTrue);
      final onThePlate = session.plan!.allItems.first.food;

      await session.setNeverAgain(onThePlate, true);
      expect(session.regeneratePlan(), isTrue);

      final ids = session.plan!.allItems.map((i) => i.food.id).toSet();
      expect(ids, isNot(contains(onThePlate.id)));
      expect(
        session.plan!.allItems.where((i) => i.food.tags.contains('Có hải sản')),
        isEmpty,
      );
    });
  });

  group('the per-day thresholds reach step 4', () {
    /// `nutrientTargets` used to be a plain field that nothing assigned
    /// outside one test. The 2 000 mg sodium ceiling existed in the rule
    /// set, was drawn on the day-budget card, and never reached phase 5.
    test('declaring hypertension gives the plan a sodium ceiling', () {
      final plain = _ready();
      expect(plain.regeneratePlan(), isTrue);
      expect(plain.plan!.nutrientTargets, isEmpty);

      final hypertensive = _ready(conditions: ['hypertension']);
      expect(hypertensive.regeneratePlan(), isTrue);

      final targets = hypertensive.plan!.nutrientTargets;
      expect(targets, hasLength(1));
      expect(targets.single.nutrient, 'sodium_mg');
      expect(targets.single.amount, 2000);
      expect(targets.single.isFloor, isFalse);
    });

    /// Only the hard ones. Sugar ≤ 25 g/day is advice and costs score;
    /// handing it to phase 5 would turn a recommendation into a prohibition.
    test('a soft threshold is not handed to phase 5', () {
      final diabetic = _ready(conditions: ['diabetes']);

      expect(diabetic.regeneratePlan(), isTrue);
      expect(
        diabetic.plan!.nutrientTargets,
        isEmpty,
        reason: "diabetes' only day threshold is the soft sugar one",
      );
    });

    test('the catalogue itself is unchanged by any of this', () {
      // 32 dishes, two of them added for the vegetarian main course the deck
      // did not have. Pinned so that a change to the deck is a decision
      // rather than a surprise in some other test's numbers.
      expect(MockFoods.surveyDeck, hasLength(32));
      expect(
        MockFoods.surveyDeck.map((f) => f.id).toSet(),
        hasLength(32),
        reason: 'two dishes sharing an id would silently shadow each other',
      );
    });
  });
}
