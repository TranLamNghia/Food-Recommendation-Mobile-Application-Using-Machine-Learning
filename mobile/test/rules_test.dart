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
  group('EvidenceLevel — mức nào dẫn được nguồn', () {
    test('chỉ `published` dẫn được nguồn', () {
      expect(EvidenceLevel.published.canCite, isTrue);
      expect(
        EvidenceLevel.derived.canCite,
        isFalse,
        reason: 'ngưỡng suy ra kèm giả thiết nên không dẫn như khuyến cáo',
      );
      expect(EvidenceLevel.unsupported.canCite, isFalse);
      expect(
        EvidenceLevel.definitional.canCite,
        isFalse,
        reason: 'quy tắc nhãn không có ngưỡng nào để dẫn nguồn',
      );
    });

    test('mã lạ rơi về `derived`, không phải `published`', () {
      // Trả về `published` khi không nhận ra mã sẽ khiến một giá trị lỗi tự
      // nhận là có nguồn — đúng kiểu hỏng cần tránh nhất ở đây.
      expect(EvidenceLevel.fromCode('gi_do_la'), EvidenceLevel.derived);
      expect(EvidenceLevel.fromCode(null), EvidenceLevel.derived);
      expect(EvidenceLevel.fromCode('gi_do_la').canCite, isFalse);
      expect(EvidenceLevel.fromCode('published'), EvidenceLevel.published);
    });
  });

  group('DayLimit — hai cột, và phần còn lại không bị kẹp', () {
    const natri = DayLimit(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      amount: 2000,
      eaten: 403.95,
      planned: 1442.70,
      isHard: true,
      evidence: EvidenceLevel.published,
    );

    test('đã dùng = đã ăn + đã lên kế hoạch', () {
      expect(natri.used, closeTo(1846.65, 1e-9));
      expect(natri.remaining, closeTo(153.35, 1e-9));
      expect(natri.exceeded, isFalse);
      expect(natri.ratio, closeTo(0.923325, 1e-6));
    });

    test('vượt trần thì `remaining` ÂM, không bị kẹp về 0', () {
      final vuot = natri.copyWith(planned: 2000);
      expect(vuot.exceeded, isTrue);
      expect(
        vuot.remaining,
        lessThan(0),
        reason: 'kẹp về 0 thì câu "vượt 404 mg" không viết được',
      );
      expect(vuot.remaining, closeTo(-403.95, 1e-9));
      expect(vuot.ratio, greaterThan(1.0));
    });

    test('`fits` chặt ở biên', () {
      expect(natri.fits(153.35), isTrue, reason: 'đúng bằng phần còn lại');
      expect(natri.fits(153.36), isFalse, reason: 'hơn 0,01 mg là không vừa');
      expect(natri.fits(14), isTrue);
    });

    test('`dataComplete` sai thì phần còn lại CAO hơn thực tế', () {
      expect(natri.dataComplete, isTrue);
      final thieu = natri.copyWith(missingCount: 4);
      expect(thieu.dataComplete, isFalse);
      expect(
        thieu.remaining,
        natri.remaining,
        reason:
            'con số không đổi — chính vì thế cờ này là chỗ DUY NHẤT nói ra '
            'rằng nó đang nới hơn thực tế',
      );
    });
  });

  group('DayBudget — cộng phần biết, đếm phần không biết', () {
    final mon = [
      _food(id: 'a', name: 'Có purin', sodium: 500, purine: 120),
      _food(id: 'b', name: 'Khuyết purin', sodium: 300),
      _food(id: 'c', name: 'Khuyết purin 2', sodium: 200),
    ];
    final thresholds = dayThresholdsFor(const [
      UserCondition('Tăng huyết áp'),
      UserCondition('Gút'),
    ]);

    test('hai bệnh cho hai ngưỡng cứng theo ngày', () {
      expect(thresholds.length, 2);
      expect(thresholds.every((t) => t.isHard), isTrue);
    });

    test('natri cộng đủ ba món, purin chỉ cộng món có số liệu', () {
      final budget = DayBudget.from(
        thresholds: thresholds,
        eaten: [mon[0]],
        planned: [mon[1], mon[2]],
      );
      final natri = budget.tightestHardFor('sodium_mg')!;
      expect(natri.eaten, 500);
      expect(natri.planned, 500);
      expect(natri.missingCount, 0);
      expect(natri.dataComplete, isTrue);

      final purin = budget.tightestHardFor('purine_mg')!;
      expect(purin.eaten, 120);
      expect(
        purin.planned,
        0,
        reason: 'hai món khuyết purin cộng vào 0 — và đó là lý do phải đếm',
      );
      expect(purin.missingCount, 2);
      expect(
        purin.dataComplete,
        isFalse,
        reason: 'tổng 120 mg thấp hơn thực tế, giao diện phải nói ra',
      );
    });

    test('chất không bị hạn chế trả về null', () {
      final budget = DayBudget.from(
        thresholds: thresholds,
        eaten: mon,
        planned: const [],
      );
      expect(budget.tightestHardFor('calcium_mg'), isNull);
    });

    test('hạn mức mềm KHÔNG nằm trong `hard`', () {
      final ds = dayThresholdsFor(const [
        UserCondition('Tăng huyết áp'),
        UserCondition('Đái tháo đường'),
      ]);
      final budget = DayBudget.from(
        thresholds: ds,
        eaten: const [],
        planned: const [],
      );
      expect(budget.hard.length, 1);
      expect(budget.soft.length, 1);
      expect(
        budget.tightestHardFor('sugar_g'),
        isNull,
        reason: 'đường là khuyến cáo, không phải lệnh cấm',
      );
    });

    test('`severity_min` chặn đúng', () {
      // Luật `Giàu purin` của Gút cần mức vừa.
      final nhe = tagExclusionsFor(
        _food(id: 'x', name: 'Món', tags: const ['Giàu purin']),
        const [UserCondition('Gút', severity: 'mild')],
      );
      final vua = tagExclusionsFor(
        _food(id: 'x', name: 'Món', tags: const ['Giàu purin']),
        const [UserCondition('Gút', severity: 'moderate')],
      );
      expect(nhe, isEmpty, reason: 'mức nhẹ chưa đủ để luật này áp');
      expect(vua.length, 1);
      expect(vua.first.condition, contains('mức vừa'));
    });
  });

  group('PenaltyOutcome — hệ số nhân, cộng theo nhóm', () {
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

    test('hai dải LỒNG NHAU của cùng bệnh → lấy nặng nhất, không nhân đôi', () {
      final r = PenaltyOutcome.of(
        _food(id: 'a', name: 'Mặn', sodium: 800, purine: 10),
        const [thaNhe, thaNang, gut],
      );
      expect(
        r.factor,
        closeTo(0.400, 1e-9),
        reason: 'nhân thẳng sẽ ra 0,240 — đếm đôi một mối lo',
      );
      expect(r.violations.length, 1);
      expect(r.violations.first.rule.threshold, 500);
      expect(r.violations.first.over, closeTo(300, 1e-9));
    });

    test('hai bệnh khác nhau thì NHÂN qua nhóm', () {
      final r = PenaltyOutcome.of(
        _food(id: 'b', name: 'Mặn và purin', sodium: 800, purine: 200),
        const [thaNhe, thaNang, gut],
      );
      expect(r.factor, closeTo(0.200, 1e-9));
      expect(r.violations.length, 2);
      expect(
        r.violations.first.rule.penalty,
        lessThan(r.violations.last.rule.penalty),
        reason: 'xếp mức phạt nặng trước',
      );
    });

    test('không vượt gì thì hệ số 1,0 và không đổi điểm', () {
      final r = PenaltyOutcome.of(
        _food(id: 'c', name: 'Nhạt', sodium: 100, purine: 10),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
      expect(r.penalised, isFalse);
      expect(r.violations, isEmpty);
      expect(r.applyTo(0.78), closeTo(0.78, 1e-9));
    });

    test('đúng bằng ngưỡng thì không vượt', () {
      final r = PenaltyOutcome.of(
        _food(id: 'd', name: 'Biên', sodium: 700, purine: 150),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
    });

    test('thiếu số liệu thì KHÔNG phạt, nhưng được ghi lại', () {
      // Ràng buộc mềm là quyết định về xếp hạng, nên hạ điểm một món vì danh
      // mục thiếu số liệu là phạt sai đối tượng.
      final r = PenaltyOutcome.of(
        _food(id: 'e', name: 'Khuyết purin', sodium: 100),
        const [thaNhe, gut],
      );
      expect(r.factor, 1.0);
      expect(r.missingNutrients, ['purine_mg']);
      expect(r.violations, isEmpty);
    });

    test('áp hệ số vào điểm', () {
      final r = PenaltyOutcome.of(
        _food(id: 'f', name: 'Mặn', sodium: 800, purine: 10),
        const [thaNhe, thaNang, gut],
      );
      expect(r.applyTo(0.78), closeTo(0.312, 1e-9));
    });
  });

  group('matchReasons — câu, không phải số', () {
    final mon = [
      _food(id: 'a', name: 'Canh A', category: 'Món canh', protein: 20, carb: 5),
      _food(id: 'b', name: 'Cơm B', category: 'Cơm', protein: 5, carb: 60),
    ];
    final space = FoodVectorSpace.fromFoods(mon);

    test('mọi chiều đều có mệnh đề', () {
      expect(
        dimensionsWithoutSentence(space),
        isEmpty,
        reason: 'chiều mới thêm mà quên câu thì phép kiểm này sai ngay',
      );
    });

    test('hồ sơ rỗng → không lý do nào', () {
      final rong = PreferenceProfile.empty(space);
      expect(matchReasons(rong, mon[0]), isEmpty);
      expect(matchSentences(rong, mon[0]), isEmpty);
    });

    test('nêu đúng chiều dương, xếp giảm dần, tỷ lệ theo đỉnh của món', () {
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: mon[0], action: SwipeAction.like),
          (food: mon[1], action: SwipeAction.dislike),
        ],
      );
      final rs = matchReasons(profile, mon[0]);
      expect(rs, isNotEmpty);
      expect(rs.every((r) => r.value > 0), isTrue);
      for (var i = 1; i < rs.length; i++) {
        expect(rs[i - 1].value, greaterThanOrEqualTo(rs[i].value));
      }
      expect(rs.first.ratio, closeTo(1.0, 1e-9));
      expect(rs.every((r) => r.ratio > 0 && r.ratio <= 1.0), isTrue);
    });

    test('đóng góp dương ⟹ trọng số hồ sơ dương ⟹ câu là "nhiều X"', () {
      // Mọi chiều vector nằm trong [0, 1], nên dấu của p_u[i]·v[i] là dấu
      // của p_u[i]. Đây là nền tảng của cách đặt câu: không bao giờ "ít X".
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: mon[0], action: SwipeAction.like),
          (food: mon[1], action: SwipeAction.dislike),
        ],
      );
      final v = space.encode(mon[0]);
      expect(v.every((x) => x >= 0 && x <= 1), isTrue);
      for (final r in matchReasons(profile, mon[0])) {
        final i = space.labels.indexOf(r.dimension);
        expect(profile.weights[i], greaterThan(0));
        expect(r.sentence, isNot(contains('ít ')));
      }
    });

    test('câu cho chiều nhóm dựng từ tên nhóm, không cần bảng tra', () {
      expect(sentenceForDimension('Nhóm: Món canh'), 'Bạn thích nhóm Món canh');
      expect(sentenceForDimension('Tỷ lệ đạm'), 'Bạn thường chọn món nhiều đạm');
      expect(
        sentenceForDimension('Chiều chưa đặt tên'),
        isNull,
        reason: 'giao diện bỏ dòng đó, không hiện nhãn kỹ thuật',
      );
    });

    test('không câu nào lọt số thô ra giao diện', () {
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [(food: mon[0], action: SwipeAction.like)],
      );
      for (final c in matchSentences(profile, mon[0])) {
        expect(c, isNot(contains('+')));
        expect(c, isNot(contains('0.')));
      }
    });
  });

  group('screenDishes — ba bậc lý do', () {
    final conditions = const [
      UserCondition('Dị ứng hải sản'),
      UserCondition('Tăng huyết áp'),
      UserCondition('Gút'),
    ];
    final mon = [
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
        foods: mon,
        conditions: conditions,
        budget: budget,
        softRules: softRulesFor(conditions),
      );
    }

    test('món sạch thì được phép và có hệ số phạt', () {
      final r = sang();
      expect(r.allowed.map((f) => f.id), contains('ok'));
      expect(r.penalties['ok']!.factor, 1.0);
    });

    test('nhãn → bậc `dish`, kèm tên nhãn và mức tin cậy định nghĩa', () {
      final r = sang();
      final ly = r.excluded['tag']!;
      expect(ly.first.tier, ExclusionTier.dish);
      expect(ly.first.tag, 'Có hải sản');
      expect(ly.first.evidence, EvidenceLevel.definitional);
      expect(r.byTier[ExclusionTier.dish], contains('tag'));
    });

    test('vượt hạn mức ngày → bậc `dayBudget`, nêu lượng vượt', () {
      final r = sang();
      final ly = r.excluded['man']!;
      expect(ly.first.tier, ExclusionTier.dayBudget);
      expect(ly.first.nutrient, 'sodium_mg');
      expect(ly.first.over, closeTo(9000 - 2000, 1e-9));
      expect(r.byTier[ExclusionTier.dayBudget], contains('man'));
    });

    test('thiếu số liệu → bậc riêng, KHÔNG phải "vừa"', () {
      final r = sang();
      final ly = r.excluded['khuyet']!;
      expect(ly.first.tier, ExclusionTier.unknown);
      expect(ly.first.nutrient, 'purine_mg');
      expect(ly.first.missingData, isTrue);
      expect(
        ly.first.over,
        isNull,
        reason: 'không có số đo thì không bịa ra một lượng vượt',
      );
      expect(r.allowed.map((f) => f.id), isNot(contains('khuyet')));
    });

    test('bậc nghiêm nhất thắng khi một món vướng nhiều lý do', () {
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
      expect(r.excluded['ca']!.length, 2, reason: 'nêu đủ cả hai lý do');
      expect(
        r.byTier[ExclusionTier.dish],
        contains('ca'),
        reason:
            'vướng thuộc tính của chính món thì không còn quan trọng là hôm '
            'nay hết hạn mức hay không',
      );
      expect(r.byTier[ExclusionTier.dayBudget], isNot(contains('ca')));
    });

    test('ăn mặn từ sáng làm thêm món bị chặn — hôm khác thì không', () {
      final rong = sang();
      final day = sang(eatenSodium: 1950);
      expect(rong.allowed.map((f) => f.id), contains('ok'));
      expect(
        day.allowed.map((f) => f.id),
        isNot(contains('ok')),
        reason: 'cùng một món, khác ngày, khác kết luận — đúng bản chất bậc 2',
      );
      expect(day.excluded['ok']!.first.tier, ExclusionTier.dayBudget);
    });
  });
}
