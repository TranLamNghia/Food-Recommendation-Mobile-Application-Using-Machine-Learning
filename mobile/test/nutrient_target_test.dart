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

/// Hạn mức dùng chung cho mọi phép kiểm trong tệp này.
const _kcal = 2000.0;
const _protein = 100.0;
const _carb = 250.0;
const _fat = 60.0;

/// Danh mục tổng hợp: mỗi vai trò có cả phương án **nhạt/nhiều xơ** và
/// **mặn/ít xơ**, nên mọi ngưỡng trong tệp này đều **khả thi**.
///
/// Phải tự dựng thay vì dùng `MockFoods.surveyDeck`: bộ 30 món mock quá mặn
/// (một ngày ra 5.850 mg natri) nên không ngưỡng natri nào đạt được, và khi
/// đó phép kiểm không phân biệt được "thuật toán sai" với "danh mục không
/// đủ món".
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
    // 200 g là khẩu phần phổ biến nhất của danh mục (48/318 món).
    servingSizeG: 200,
    emoji: '🍚',
    gradient: const [Color(0xFFFFFFFF), Color(0xFF000000)],
  );

  final out = <Food>[];
  // Vai trò đúng theo `_mealStructure` của MenuBuilder.
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
  // Cố ý thích nhóm **mặn, ít xơ**, để ràng buộc phải đi ngược khẩu vị. Nếu
  // khẩu vị vốn đã trùng hướng ràng buộc thì phép kiểm sẽ đạt kể cả khi pha 5
  // không làm gì.
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
  group('NutrientTarget — phép tính vi phạm', () {
    test('sàn và trần tính đúng hướng, quy về tỷ lệ', () {
      const floor = NutrientTarget.atLeast('fiber_g', 25);
      expect(floor.violation(25), equals(0));
      expect(floor.violation(30), equals(0));
      expect(floor.violation(20), closeTo(0.2, 1e-9));

      const ceiling = NutrientTarget.atMost('sodium_mg', 2000);
      expect(ceiling.violation(2000), equals(0));
      expect(ceiling.violation(1500), equals(0));
      expect(ceiling.violation(2400), closeTo(0.2, 1e-9));
    });

    test('dùng tỷ lệ nên so được giữa hai chất khác đơn vị', () {
      // Thiếu 5 g xơ trên ngưỡng 25 g là nặng hơn nhiều so với vượt 5 mg
      // natri trên ngưỡng 2000 mg. Đo bằng lượng tuyệt đối thì hai cái bằng
      // nhau, và pha 5 sẽ đi sửa cái sai.
      const fiber = NutrientTarget.atLeast('fiber_g', 25);
      const sodium = NutrientTarget.atMost('sodium_mg', 2000);
      expect(fiber.violation(20), greaterThan(sodium.violation(2005)));
    });

    test('purine_mg nằm ngoài tầm thi hành', () {
      expect(NutrientTarget.supported.contains('purine_mg'), isFalse);
      expect(NutrientTarget.valueOf(MockFoods.surveyDeck.first, 'purine_mg'),
          isNull);
    });
  });

  group('Bước 4 pha 5 — ràng buộc vi chất cấp ngày', () {
    test('trần natri được thi hành khi danh mục đủ món', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final without = _build(catalog, profile, const []);
      final with_ = _build(
        catalog, profile, const [NutrientTarget.atMost('sodium_mg', 2000)],
      );

      expect(without.totalOf('sodium_mg'), greaterThan(2000),
          reason: 'không có ràng buộc thì phải vi phạm, nếu không phép kiểm vô nghĩa');
      expect(with_.totalOf('sodium_mg'), lessThanOrEqualTo(2000));
      expect(with_.nutrientViolations, isEmpty);
      expect(with_.meetsNutrientTargets, isTrue);
    });

    test('sàn chất xơ được thi hành khi danh mục đủ món', () {
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

    test('không phá ràng buộc đang thỏa để chữa ràng buộc khác', () {
      // Đây là điều kiện dễ sai nhất của pha 5: lấp chất xơ bằng cách nhồi
      // món nhiều natri thì người tăng huyết áp nhận thực đơn đạt xơ mà vi
      // phạm đúng ngưỡng quan trọng với họ.
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

    test('không đẩy độ lệch năng lượng vượt 10 %', () {
      // Thỏa một ràng buộc vi chất bằng cách phá hạn mức năng lượng là chữa
      // một vi phạm bằng cách tạo ra một vi phạm khác.
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      for (var seed = 0; seed < 8; seed++) {
        final plan = _build(catalog, profile, const [
          NutrientTarget.atLeast('fiber_g', 25),
          NutrientTarget.atMost('sodium_mg', 2000),
        ], seed: seed);

        expect(plan.deviationPct.abs(), lessThanOrEqualTo(10.0),
            reason: 'seed $seed lệch ${plan.deviationPct}%');
      }
    });

    test('không sinh ra món trùng trong ngày', () {
      // Cùng loại lỗi đã xảy ra ở pha 3: hoán đổi mà không cập nhật `usedIds`
      // thì một món vào được hai bữa.
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      for (var seed = 0; seed < 8; seed++) {
        final plan = _build(catalog, profile, const [
          NutrientTarget.atLeast('fiber_g', 25),
          NutrientTarget.atMost('sodium_mg', 2000),
        ], seed: seed);

        final ids = plan.allItems.map((i) => i.food.id).toList();
        expect(ids.toSet().length, equals(ids.length),
            reason: 'seed $seed có món trùng');
      }
    });

    test('danh mục không đủ thì BÁO vi phạm, không ỉm đi', () {
      // Bộ 30 món mock quá mặn để đạt 2000 mg. Hành vi đúng là cải thiện
      // hết mức rồi báo ra, chứ không phải trả về thực đơn trông như đã đạt.
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

      expect(with_.totalOf('sodium_mg'), lessThan(without.totalOf('sodium_mg')),
          reason: 'vẫn phải cải thiện hết mức có thể');
      expect(with_.nutrientViolations, hasLength(1));
      expect(with_.nutrientViolations.first.target.nutrient,
          equals('sodium_mg'));
      expect(with_.meetsNutrientTargets, isFalse);
    });

    test('ràng buộc ngoài tầm thi hành không bị coi là đã thỏa', () {
      final catalog = _syntheticCatalog();
      final profile = _profileOver(catalog);

      final plan = _build(
        catalog, profile, const [NutrientTarget.atMost('purine_mg', 400)],
      );

      // Tổng purin đọc ra bằng 0 vì `Food` không mang chất này. Nếu gộp vào
      // `nutrientViolations` thì nó sẽ hiện ra như ĐÃ ĐẠT ngưỡng gút trên một
      // thực đơn chưa từng được kiểm purin.
      expect(plan.nutrientViolations, isEmpty);
      expect(plan.unenforceableTargets, hasLength(1));
      expect(plan.meetsNutrientTargets, isFalse);
    });

    test('AppSession truyền ràng buộc xuống tới thực đơn', () {
      // Nếu đường nối này hỏng thì pha 5 là mã chết: mọi phép kiểm ở trên
      // vẫn xanh vì chúng gọi MenuBuilder trực tiếp.
      final session = AppSession(rng: math.Random(5))
        ..profile.gender = Gender.male
        ..profile.birthday = DateTime(DateTime.now().year - 24, 6, 15)
        ..profile.heightCm = 172
        ..profile.weightKg = 68
        ..profile.goal = HealthGoal.maintain
        ..profile.activity = ActivityLevel.moderate
        ..explorationRatio = 0;

      expect(session.regeneratePlan(), isTrue);
      expect(session.plan!.nutrientTargets, isEmpty);
      final sodiumWithout = session.plan!.totalOf('sodium_mg');

      session.nutrientTargets = const [
        NutrientTarget.atMost('sodium_mg', 2000),
      ];
      expect(session.regeneratePlan(), isTrue);

      expect(session.plan!.nutrientTargets, hasLength(1));
      expect(session.plan!.totalOf('sodium_mg'), lessThan(sodiumWithout));
    });

    test('không có ràng buộc nào thì pha 5 không đổi gì', () {
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
