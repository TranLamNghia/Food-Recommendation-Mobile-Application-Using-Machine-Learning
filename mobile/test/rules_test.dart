import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/mock/mock_rules.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';
import 'package:nutrition_app/data/recommender/match_reason.dart';
import 'package:nutrition_app/data/recommender/preference_profile.dart';
import 'package:nutrition_app/data/rules/condition_rule.dart';
import 'package:nutrition_app/data/rules/day_budget.dart';
import 'package:nutrition_app/data/rules/dish_screening.dart';
import 'package:nutrition_app/data/rules/evidence_level.dart';

const _grey = [Color(0xFFCCCCCC), Color(0xFF888888)];

Food _food({
  required String id,
  required String name,
  String category = 'Món canh',
  double protein = 10,
  double carb = 10,
  double fat = 5,
  double sugar = 2,
  double sodium = 100,
  double fiber = 2,
  double? purine,
  int kcal = 200,
  List<String> tags = const [],
}) => Food(
  id: id,
  name: name,
  category: category,
  dishRole: 'Món chính',
  spiceLevel: 0,
  kcal: kcal,
  protein: protein,
  carb: carb,
  fat: fat,
  sugar: sugar,
  sodium: sodium,
  fiber: fiber,
  servingSizeG: 200,
  purine: purine,
  emoji: '🍚',
  gradient: _grey,
  tags: tags,
);

void main() {
  group('EvidenceLevel — which levels may be cited', () {
    test('only `published` may be cited', () {
      expect(EvidenceLevel.published.canCite, isTrue);
      expect(
        EvidenceLevel.derived.canCite,
        isFalse,
        reason: 'a derived threshold carries an assumption, so it is not '
            'quoted as a recommendation',
      );
      expect(EvidenceLevel.unsupported.canCite, isFalse);
      expect(
        EvidenceLevel.definitional.canCite,
        isFalse,
        reason: 'a tag rule has no threshold to cite',
      );
    });

    test('an unknown code falls back to `derived`, not `published`', () {
      // Returning `published` for an unrecognised code would let a bad
      // value claim to have a source — exactly the failure to avoid here.
      expect(EvidenceLevel.fromCode('gi_do_la'), EvidenceLevel.derived);
      expect(EvidenceLevel.fromCode(null), EvidenceLevel.derived);
      expect(EvidenceLevel.fromCode('gi_do_la').canCite, isFalse);
      expect(EvidenceLevel.fromCode('published'), EvidenceLevel.published);
    });
  });

  group('DayLimit — two columns, and the remainder is not clamped', () {
    const sodium = DayLimit(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      amount: 2000,
      eaten: 403.95,
      planned: 1442.70,
      isHard: true,
      evidence: EvidenceLevel.published,
    );

    test('used = eaten + planned', () {
      expect(sodium.used, closeTo(1846.65, 1e-9));
      expect(sodium.remaining, closeTo(153.35, 1e-9));
      expect(sodium.exceeded, isFalse);
      expect(sodium.ratio, closeTo(0.923325, 1e-6));
    });

    test('over the ceiling `remaining` is NEGATIVE, not clamped to 0', () {
      final vuot = sodium.copyWith(planned: 2000);
      expect(vuot.exceeded, isTrue);
      expect(
        vuot.remaining,
        lessThan(0),
        reason: 'clamped at 0, the sentence "404 mg over" could not be '
            'written',
      );
      expect(vuot.remaining, closeTo(-403.95, 1e-9));
      expect(vuot.ratio, greaterThan(1.0));
    });

    test('`fits` is strict at the boundary', () {
      expect(sodium.fits(153.35), isTrue, reason: 'exactly the remainder');
      expect(
        sodium.fits(153.36),
        isFalse,
        reason: '0.01 mg more does not fit',
      );
      expect(sodium.fits(14), isTrue);
    });

    test('when `dataComplete` is false the remainder is TOO HIGH', () {
      expect(sodium.dataComplete, isTrue);
      final missing = sodium.copyWith(missingCount: 4);
      expect(missing.dataComplete, isFalse);
      expect(
        missing.remaining,
        sodium.remaining,
        reason:
            'con số không đổi — chính vì thế cờ này là chỗ DUY NHẤT nói ra '
            'rằng nó đang nới hơn thực tế',
      );
    });
  });

  group('DayBudget — sum what is known, count what is not', () {
    final food = [
      _food(id: 'a', name: 'Có purin', sodium: 500, purine: 120),
      _food(id: 'b', name: 'Khuyết purin', sodium: 300),
      _food(id: 'c', name: 'Khuyết purin 2', sodium: 200),
    ];
    final thresholds = dayThresholdsFor(const [
      UserCondition('Tăng huyết áp'),
      UserCondition('Gút'),
    ]);

    test('two conditions give two hard per-day thresholds', () {
      expect(thresholds.length, 2);
      expect(thresholds.every((t) => t.isHard), isTrue);
    });

    test('sodium sums all three dishes, purine only those measured', () {
      final budget = DayBudget.from(
        thresholds: thresholds,
        eaten: [food[0]],
        planned: [food[1], food[2]],
      );
      final sodium = budget.tightestHardFor('sodium_mg')!;
      expect(sodium.eaten, 500);
      expect(sodium.planned, 500);
      expect(sodium.missingCount, 0);
      expect(sodium.dataComplete, isTrue);

      final purin = budget.tightestHardFor('purine_mg')!;
      expect(purin.eaten, 120);
      expect(
        purin.planned,
        0,
        reason: 'the two dishes with no purine add 0 — which is exactly '
            'why they have to be counted',
      );
      expect(purin.missingCount, 2);
      expect(
        purin.dataComplete,
        isFalse,
        reason: 'the 120 mg total is lower than reality, and the '
            'interface has to say so',
      );
    });

    test('an unrestricted nutrient returns null', () {
      final budget = DayBudget.from(
        thresholds: thresholds,
        eaten: food,
        planned: const [],
      );
      expect(budget.tightestHardFor('calcium_mg'), isNull);
    });

    test('a soft allowance is NOT in `hard`', () {
      final list = dayThresholdsFor(const [
        UserCondition('Tăng huyết áp'),
        UserCondition('Đái tháo đường'),
      ]);
      final budget = DayBudget.from(
        thresholds: list,
        eaten: const [],
        planned: const [],
      );
      expect(budget.hard.length, 1);
      expect(budget.soft.length, 1);
      expect(
        budget.tightestHardFor('sugar_g'),
        isNull,
        reason: 'sugar is a recommendation, not a prohibition',
      );
    });

    test('`severity_min` gates correctly', () {
      // Gout's `Giàu purin` rule needs the moderate level.
      final mild = tagExclusionsFor(
        _food(id: 'x', name: 'Món', tags: const ['Giàu purin']),
        const [UserCondition('Gút', severity: 'mild')],
      );
      final vua = tagExclusionsFor(
        _food(id: 'x', name: 'Món', tags: const ['Giàu purin']),
        const [UserCondition('Gút', severity: 'moderate')],
      );
      expect(
        mild,
        isEmpty,
        reason: 'the mild level is not enough for this rule to apply',
      );
      expect(vua.length, 1);
      expect(vua.first.condition, contains('mức vừa'));
    });
  });

  group('PenaltyOutcome — a multiplier, combined per group', () {
    const thaNhe = SoftRule(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      threshold: 700,
      penalty: 0.600,
      evidence: EvidenceLevel.derived,
    );
    const thaNang = SoftRule(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      threshold: 500,
      penalty: 0.400,
      evidence: EvidenceLevel.unsupported,
    );
    const gut = SoftRule(
      condition: 'Gút',
      nutrient: 'purine_mg',
      unit: 'mg',
      threshold: 150,
      penalty: 0.500,
      evidence: EvidenceLevel.derived,
    );

    test('two NESTED bands of one condition → harshest wins, no double count', () {
      final r = PenaltyOutcome.of(
        _food(id: 'a', name: 'Mặn', sodium: 800, purine: 10),
        const [thaNhe, thaNang, gut],
      );
      expect(
        r.factor,
        closeTo(0.400, 1e-9),
        reason: 'multiplying straight through gives 0.240 — double '
            'counting one concern',
      );
      expect(r.violations.length, 1);
      expect(r.violations.first.rule.threshold, 500);
      expect(r.violations.first.over, closeTo(300, 1e-9));
    });

    test('two different conditions DO multiply across groups', () {
      final r = PenaltyOutcome.of(
        _food(id: 'b', name: 'Mặn và purin', sodium: 800, purine: 200),
        const [thaNhe, thaNang, gut],
      );
      expect(r.factor, closeTo(0.200, 1e-9));
      expect(r.violations.length, 2);
      expect(
        r.violations.first.rule.penalty,
        lessThan(r.violations.last.rule.penalty),
        reason: 'the harsher penalty comes first',
      );
    });

    test('exceeding nothing gives a factor of 1.0 and no score change', () {
      final r = PenaltyOutcome.of(
        _food(id: 'c', name: 'Nhạt', sodium: 100, purine: 10),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
      expect(r.penalised, isFalse);
      expect(r.violations, isEmpty);
      expect(r.applyTo(0.78), closeTo(0.78, 1e-9));
    });

    test('exactly at the threshold is not over it', () {
      final r = PenaltyOutcome.of(
        _food(id: 'd', name: 'Biên', sodium: 700, purine: 150),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
    });

    test('missing data is NOT penalised, but it is recorded', () {
      // A soft constraint is a ranking decision, so lowering a dish's score
      // because the catalogue is incomplete penalises the wrong party.
      final r = PenaltyOutcome.of(
        _food(id: 'e', name: 'Khuyết purin', sodium: 100),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
      expect(r.missingNutrients, ['purine_mg']);
      expect(r.violations, isEmpty);
    });

    test('the factor is applied to the score', () {
      final r = PenaltyOutcome.of(
        _food(id: 'f', name: 'Mặn', sodium: 800, purine: 10),
        const [thaNhe, thaNang, gut],
      );
      expect(r.applyTo(0.78), closeTo(0.312, 1e-9));
    });
  });

  group('matchReasons — sentences, not numbers', () {
    final food = [
      _food(id: 'a', name: 'Canh A', category: 'Món canh', protein: 20, carb: 5),
      _food(id: 'b', name: 'Cơm B', category: 'Cơm', protein: 5, carb: 60),
    ];
    final space = FoodVectorSpace.fromFoods(food);

    test('every dimension has a clause', () {
      expect(
        dimensionsWithoutSentence(space),
        isEmpty,
        reason: 'a newly added dimension with a forgotten clause fails '
            'this check immediately',
      );
    });

    test('an empty profile → no reasons at all', () {
      final rong = PreferenceProfile.empty(space);
      expect(matchReasons(rong, food[0]), isEmpty);
      expect(matchSentences(rong, food[0]), isEmpty);
    });

    test('positive dimensions only, descending, ratio against the peak', () {
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: food[0], action: SwipeAction.like),
          (food: food[1], action: SwipeAction.dislike),
        ],
      );
      final rs = matchReasons(profile, food[0]);
      expect(rs, isNotEmpty);
      expect(rs.every((r) => r.value > 0), isTrue);
      for (var i = 1; i < rs.length; i++) {
        expect(rs[i - 1].value, greaterThanOrEqualTo(rs[i].value));
      }
      expect(rs.first.ratio, closeTo(1.0, 1e-9));
      expect(rs.every((r) => r.ratio > 0 && r.ratio <= 1.0), isTrue);
    });

    test('positive contribution ⟹ positive weight ⟹ the clause is "more X"', () {
      // Every vector dimension lies in [0, 1], so the sign of p_u[i]·v[i]
      // is the sign of p_u[i]. That is the basis of the wording: never
      // "less X".
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: food[0], action: SwipeAction.like),
          (food: food[1], action: SwipeAction.dislike),
        ],
      );
      final v = space.encode(food[0]);
      expect(v.every((x) => x >= 0 && x <= 1), isTrue);
      for (final r in matchReasons(profile, food[0])) {
        final i = space.labels.indexOf(r.dimension);
        expect(profile.weights[i], greaterThan(0));
        expect(r.sentence, isNot(contains('ít ')));
      }
    });

    test('a group clause is built from the group name, with no lookup', () {
      expect(sentenceForDimension('Nhóm: Món canh'), 'Bạn thích nhóm Món canh');
      expect(sentenceForDimension('Tỷ lệ đạm'), 'Bạn thường chọn món nhiều đạm');
      expect(
        sentenceForDimension('Chiều chưa đặt tên'),
        isNull,
        reason: 'the interface drops that line rather than showing a '
            'technical label',
      );
    });

    test('no clause leaks a raw number into the interface', () {
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [(food: food[0], action: SwipeAction.like)],
      );
      for (final c in matchSentences(profile, food[0])) {
        expect(c, isNot(contains('+')));
        expect(c, isNot(contains('0.')));
      }
    });
  });

  group('screenDishes — the three reason tiers', () {
    final conditions = const [
      UserCondition('Dị ứng hải sản'),
      UserCondition('Tăng huyết áp'),
      UserCondition('Gút'),
    ];
    final food = [
      _food(id: 'ok', name: 'Canh nhạt', sodium: 100, purine: 30),
      _food(
        id: 'tag',
        name: 'Tôm hấp',
        sodium: 100,
        purine: 30,
        tags: const ['Có hải sản'],
      ),
      _food(id: 'man', name: 'Bún mặn', sodium: 9000, purine: 30),
      _food(id: 'khuyet', name: 'Món lạ', sodium: 100),
    ];

    ScreeningResult sang({double eatenSodium = 0}) {
      final budget = DayBudget.from(
        thresholds: dayThresholdsFor(conditions),
        eaten: eatenSodium == 0
            ? const []
            : [_food(id: 'da_an', name: 'Đã ăn', sodium: eatenSodium, purine: 0)],
        planned: const [],
      );
      return screenDishes(
        foods: food,
        conditions: conditions,
        budget: budget,
        softRules: softRulesFor(conditions),
      );
    }

    test('a clean dish is allowed and carries a penalty factor', () {
      final r = sang();
      expect(r.allowed.map((f) => f.id), contains('ok'));
      expect(r.penalties['ok']!.factor, 1.0);
    });

    test('a tag → the `dish` tier, with the tag name and definitional '
        'evidence', () {
      final r = sang();
      final ly = r.excluded['tag']!;
      expect(ly.first.tier, ExclusionTier.dish);
      expect(ly.first.tag, 'Có hải sản');
      expect(ly.first.evidence, EvidenceLevel.definitional);
      expect(r.byTier[ExclusionTier.dish], contains('tag'));
    });

    test('over the day allowance → the `dayBudget` tier, stating by how '
        'much', () {
      final r = sang();
      final ly = r.excluded['man']!;
      expect(ly.first.tier, ExclusionTier.dayBudget);
      expect(ly.first.nutrient, 'sodium_mg');
      expect(ly.first.over, closeTo(9000 - 2000, 1e-9));
      expect(r.byTier[ExclusionTier.dayBudget], contains('man'));
    });

    test('missing data → its own tier, NOT "fits"', () {
      final r = sang();
      final ly = r.excluded['khuyet']!;
      expect(ly.first.tier, ExclusionTier.unknown);
      expect(ly.first.nutrient, 'purine_mg');
      expect(ly.first.missingData, isTrue);
      expect(
        ly.first.over,
        isNull,
        reason: 'with no measurement, no overshoot is invented',
      );
      expect(r.allowed.map((f) => f.id), isNot(contains('khuyet')));
    });

    test('the most serious tier wins when a dish breaches several', () {
      final r = screenDishes(
        foods: [
          _food(
            id: 'ca',
            name: 'Tôm rang mặn',
            sodium: 9000,
            purine: 30,
            tags: const ['Có hải sản'],
          ),
        ],
        conditions: conditions,
        budget: DayBudget.from(
          thresholds: dayThresholdsFor(conditions),
          eaten: const [],
          planned: const [],
        ),
      );
      expect(r.excluded['ca']!.length, 2, reason: 'both reasons listed');
      expect(
        r.byTier[ExclusionTier.dish],
        contains('ca'),
        reason:
            'vướng thuộc tính của chính món thì không còn quan trọng là hôm '
            'nay hết hạn mức hay không',
      );
      expect(r.byTier[ExclusionTier.dayBudget], isNot(contains('ca')));
    });

    test('a salty morning blocks one more dish — another day it would '
        'not', () {
      final rong = sang();
      final day = sang(eatenSodium: 1950);
      expect(rong.allowed.map((f) => f.id), contains('ok'));
      expect(
        day.allowed.map((f) => f.id),
        isNot(contains('ok')),
        reason: 'the same dish, a different day, a different conclusion '
            '— exactly what tier 2 is',
      );
      expect(day.excluded['ok']!.first.tier, ExclusionTier.dayBudget);
    });
  });
}
