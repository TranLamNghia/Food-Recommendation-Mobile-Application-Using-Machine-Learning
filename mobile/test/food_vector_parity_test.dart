import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';

/// A cross-check: the Dart and the Python implementation have to produce
/// **the same vector**.
///
/// The machine learning model is trained with `ml/features.py` on the server,
/// but at serving time the score is computed by `FoodVectorSpace` here. The
/// two differing by even one dimension means the model learns in one space
/// and infers in another — and **nothing reports an error**: the model still
/// runs, still returns numbers, they are simply wrong. So this comparison has
/// to be a test, not a look by eye.
///
/// The fixture is generated from the real database by
/// `python tools/check_feature_parity.py`: it holds both the input (the
/// dishes) and the expected output (the Python vectors). That lets this test
/// run with no database at all.
///
/// The tolerance is 1e-12 rather than exact equality: the two sides run **the
/// same sequence of operations** so in principle they agree bit for bit, but
/// the values pass through a JSON round trip, so a small gap is left for
/// rounding at the text layer. That gap is smaller than any algorithmic
/// divergence could be.
const double _tolerance = 1e-12;

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
  // Two fields used only by the interface; they do not enter the
  // vector.
  emoji: '🍚',
  gradient: _grey,
);

void main() {
  final file = File('test/fixtures/food_vector_parity.json');

  group('Feature extraction — the Dart side matches the Python side', () {
    setUpAll(() {
      expect(
        file.existsSync(),
        isTrue,
        reason:
            'The fixture ${file.path} is missing. '
            'Generate it with: '
            'python tools/check_feature_parity.py --fixture-only',
      );
    });

    final fixture =
        jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final foods = (fixture['foods'] as List)
        .map((j) => _foodFromFixture(j as Map<String, dynamic>))
        .toList();
    final expectedVectors = (fixture['vectors'] as List)
        .map((v) => (v as List).map((x) => (x as num).toDouble()).toList())
        .toList();
    final scaler = fixture['scaler'] as Map<String, dynamic>;

    final space = FoodVectorSpace.fromFoods(foods);

    test('the sample dish set is not empty', () {
      expect(foods, isNotEmpty);
      expect(expectedVectors.length, foods.length);
    });

    test('the food group list and the dimension count match', () {
      expect(
        space.categories,
        (scaler['categories'] as List).cast<String>(),
        reason: 'The food group order decides the one-hot dimension '
            'order. '
            'A different order means the whole tail of the vector '
            'differs.',
      );
      expect(space.length, fixture['length'] as int);
      expect(space.labels.length, space.length);
    });

    test('the eight min-max normalisation parameters match', () {
      // This is the space's state, not a dish's. The two sides compute it
      // independently from the same dish set, so a difference here means one
      // of them filtered or imputed differently from the other.
      expect(space.minKcal, closeTo(
          (scaler['min_kcal'] as num).toDouble(), _tolerance));
      expect(space.maxKcal, closeTo(
          (scaler['max_kcal'] as num).toDouble(), _tolerance));
      expect(space.minSugar, closeTo(
          (scaler['min_sugar'] as num).toDouble(), _tolerance));
      expect(space.maxSugar, closeTo(
          (scaler['max_sugar'] as num).toDouble(), _tolerance));
      expect(space.minSodium, closeTo(
          (scaler['min_sodium'] as num).toDouble(), _tolerance));
      expect(space.maxSodium, closeTo(
          (scaler['max_sodium'] as num).toDouble(), _tolerance));
      expect(space.minFiber, closeTo(
          (scaler['min_fiber'] as num).toDouble(), _tolerance));
      expect(space.maxFiber, closeTo(
          (scaler['max_fiber'] as num).toDouble(), _tolerance));
    });

    test('every dimension of every dish matches', () {
      var worstDelta = 0.0;
      String? worstAt;

      for (var i = 0; i < foods.length; i++) {
        final actual = space.encode(foods[i]);
        final expected = expectedVectors[i];

        expect(
          actual.length,
          expected.length,
          reason: 'Dimension count differs for dish ${foods[i].name}',
        );

        for (var d = 0; d < actual.length; d++) {
          final delta = (actual[d] - expected[d]).abs();
          if (delta > worstDelta) {
            worstDelta = delta;
            worstAt =
                '${foods[i].name} · dimension $d (${space.labels[d]})';
          }
        }
      }

      expect(
        worstDelta,
        lessThan(_tolerance),
        reason: 'Largest difference $worstDelta at $worstAt',
      );
    });

    test('each dish sets exactly one group one-hot dimension', () {
      // If a dish belongs to a group the space does not hold, the whole
      // one-hot block is 0 and that dish silently loses its group
      // information.
      final firstOneHot = space.length - space.categories.length;
      for (final m in foods) {
        final v = space.encode(m);
        final oneHotSum =
            v.skip(firstOneHot).fold<double>(0, (a, b) => a + b);
        expect(
          oneHotSum,
          closeTo(1.0, _tolerance),
          reason:
              'Dish ${m.name} (group ${m.category}) sets no dimension',
        );
      }
    });

    test('every dimension lies in [0, 1]', () {
      for (final m in foods) {
        for (final (d, x) in space.encode(m).indexed) {
          expect(
            x,
            inInclusiveRange(0.0, 1.0),
            reason:
                'Dish ${m.name}, dimension $d (${space.labels[d]}) = $x',
          );
        }
      }
    });
  });
}
