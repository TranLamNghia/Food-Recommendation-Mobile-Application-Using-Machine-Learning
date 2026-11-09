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

/// Hồ sơ mẫu: nam 24 tuổi, 1m72, 68 kg, vận động vừa, mục tiêu giữ cân.
HealthProfile _sampleProfile() => HealthProfile()
  ..gender = Gender.male
  ..birthday = DateTime(DateTime.now().year - 24, 6, 15)
  ..heightCm = 172
  ..weightKg = 68
  ..goal = HealthGoal.maintain
  ..activity = ActivityLevel.moderate;

void main() {
  final space = FoodVectorSpace.fromFoods(MockFoods.surveyDeck);

  group('Vector đặc trưng món ăn', () {
    test('số chiều và nhãn khớp nhau, và có chiều chất xơ', () {
      // Giữ hai thứ này đi cùng nhau: thêm một chiều mà quên thêm nhãn thì
      // phần "vì sao món này được gợi ý" sẽ chú thích lệch cột, không báo lỗi.
      expect(space.labels.length, equals(space.length));
      expect(space.length, equals(8 + space.categories.length));
      expect(space.labels, contains('Chất xơ'));

      final v = space.encode(MockFoods.surveyDeck.first);
      expect(v.length, equals(space.length));
    });

    test('chất xơ thật sự đổi được vector — chiều này không phải cột chết', () {
      // Phép kiểm này tồn tại vì lỗi đã từng xảy ra ở chiều khác: một cột có
      // mặt trong lược đồ và trong tài liệu nhưng không món nào mang giá trị,
      // nên nó im lặng không đóng góp gì. Ở đây bắt bằng cách so hai món chỉ
      // khác nhau đúng lượng chất xơ.
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

      // Và khác biệt phải nằm ĐÚNG ở chiều đó, không rò sang chiều khác.
      for (var d = 0; d < spaceWithBoth.length; d++) {
        if (d == i) continue;
        expect(vHigh[d], equals(vLow[d]), reason: 'lệch ở ${spaceWithBoth.labels[d]}');
      }
    });
  });

  group('Mục tiêu dinh dưỡng tự khai', () {
    /// Hai món giống hệt nhau trừ chất xơ, để tách hiệu ứng của mục tiêu ra
    /// khỏi mọi đặc trưng khác.
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

    test('khai mục tiêu nhiều xơ thì món nhiều xơ được chấm cao hơn', () {
      final (low, high, sp) = fiberPair();
      final neutral = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      final withGoal = neutral.withNutrientGoals({'fiber_g': 0.6});

      // Mục tiêu phải LÀM ĐỔI thứ hạng, không chỉ đổi điểm tuyệt đối.
      expect(
        withGoal.score(high) - withGoal.score(low),
        greaterThan(neutral.score(high) - neutral.score(low)),
      );
    });

    test('dấu âm nghĩa là muốn ít hơn', () {
      final (low, high, sp) = fiberPair();
      final neutral = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      final avoid = neutral.withNutrientGoals({'fiber_g': -0.6});
      expect(avoid.score(high), lessThan(avoid.score(low)));
    });

    test('khai mục tiêu TRƯỚC khi vuốt lượt nào vẫn xếp hạng được', () {
      // Trường hợp này trước đây hỏng: `isEmpty` còn xét `signalCount == 0`
      // nên hồ sơ chỉ-có-mục-tiêu trả về 0,5 cho mọi món, và mục tiêu người
      // dùng vừa khai bị bỏ qua hoàn toàn.
      final (low, high, sp) = fiberPair();
      final coldStart =
          PreferenceProfile.empty(sp).withNutrientGoals({'fiber_g': 0.6});

      expect(coldStart.isEmpty, isFalse);
      expect(coldStart.signalCount, equals(0));
      expect(coldStart.score(high), greaterThan(coldStart.score(low)));
    });

    test('chất không có chiều riêng thì bỏ qua, không làm hỏng hồ sơ', () {
      final (_, _, sp) = fiberPair();
      final profile = PreferenceProfile.fromSwipes(
        space: sp,
        swipes: [(food: MockFoods.surveyDeck[1], action: SwipeAction.like)],
      );

      // `protein_g` cố ý KHÔNG có chiều riêng — ba chiều macro là tỷ lệ cộng
      // lại bằng 1, đẩy một cái lên là dìm hai cái kia xuống.
      final same = profile.withNutrientGoals({'protein_g': 0.9});
      expect(same.weights, equals(profile.weights));
    });

    test('hồ sơ rỗng và phiên toàn neutral vẫn được coi là rỗng', () {
      // Bảo vệ phần đổi nghĩa của `isEmpty`: nới nó ra không được làm hai
      // trường hợp cũ đổi hành vi.
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

  group('Mô-đun tính nhu cầu dinh dưỡng', () {
    test('BMI, BMR và TDEE khớp công thức Mifflin-St Jeor', () {
      final p = _sampleProfile();

      // BMI = 68 / 1.72² = 22.98
      expect(p.bmi, closeTo(22.99, 0.05));

      // BMR = 10×68 + 6.25×172 − 5×24 + 5 = 680 + 1075 − 120 + 5 = 1640
      expect(p.bmr, closeTo(1640, 1));

      // TDEE = 1640 × 1.55 = 2542
      expect(p.tdee, closeTo(2542, 2));
    });

    test('hạn mức giảm cân không bao giờ xuống dưới BMR', () {
      // Người nhỏ con, ít vận động: TDEE − 500 sẽ tụt dưới BMR nếu không chặn.
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

    test('ba chất sinh năng lượng cộng lại đúng bằng hạn mức', () {
      final p = _sampleProfile();
      final m = p.macroTarget!;
      final kcal = m.protein * 4 + m.carb * 4 + m.fat * 9;

      expect(kcal, closeTo(p.energyTarget!, 1));
    });
  });

  group('Hồ sơ sở thích theo Rocchio', () {
    test('lượt vuốt "chưa biết" bị loại khỏi tập huấn luyện', () {
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

    test('món được thích ăn điểm cao hơn món bị ghét', () {
      // Hai món phải khác nhóm, vì nhóm món là trục one-hot duy nhất trong
      // vector — chọn hai món cùng nhóm thì chỉ còn dinh dưỡng phân biệt
      // chúng và phép thử mất ý nghĩa.
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

    test('hồ sơ rỗng chấm mọi món bằng nhau', () {
      final profile = PreferenceProfile.empty(space);
      final scores = MockFoods.surveyDeck.map(profile.score).toSet();

      expect(scores.length, equals(1));
      expect(scores.first, equals(0.5));
    });

    test('vector đã làm nhiễu lệch khỏi vector gốc nhưng vẫn lân cận', () {
      final deck = MockFoods.surveyDeck;
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          for (final f in deck.take(10)) (food: f, action: SwipeAction.like),
        ],
      );

      final jittered = profile.jittered(delta: 0.35, rng: math.Random(42));

      final cos = cosineSimilarity(profile.weights, jittered.weights);

      // Lệch thật — không phải bản sao.
      expect(cos, lessThan(0.999));
      // Nhưng vẫn cùng hướng, tức món thăm dò nằm ở vùng lân cận khẩu vị
      // chứ không rơi ra chỗ vô lý như ε-greedy ngẫu nhiên.
      expect(cos, greaterThan(0.5));
    });
  });

  group('Sinh thực đơn — Bước 4', () {
    /// Dựng thực đơn cho một hồ sơ đã vuốt sẵn.
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

    test('đủ bốn bữa', () {
      final plan = buildPlan();
      expect(plan.slots.map((s) => s.type), equals(MealType.values));
    });

    test('không lặp món trong cùng một ngày', () {
      final plan = buildPlan();
      final ids = plan.allItems.map((i) => i.food.id).toList();

      expect(ids.toSet().length, equals(ids.length));
    });

    test('mỗi bữa có đủ vai trò món bắt buộc', () {
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

    test('không có hai món cùng vai trò trong một bữa', () {
      // Ràng buộc "không hai món cùng nhóm thực phẩm trong S" của Bước 4 —
      // tránh bữa trưa gồm hai món mặn và không có gì khác.
      final plan = buildPlan();

      for (final slot in plan.slots) {
        final roles = slot.items.map((i) => i.food.dishRole).toList();
        expect(
          roles.toSet().length,
          equals(roles.length),
          reason: '${slot.type.label} có vai trò món lặp: $roles',
        );
      }
    });

    test('độ lệch năng lượng không vượt 10 phần trăm', () {
      // Chạy nhiều hạt giống khác nhau: cam kết trong đề cương là với mọi
      // người dùng, không phải may mắn ở một lần chạy.
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

    test('tỷ lệ thăm dò bị chặn cứng ở 50 phần trăm', () {
      final plan = buildPlan(exploration: 0.9);
      expect(plan.explorationRatio, lessThanOrEqualTo(0.5));
    });

    test('tắt thăm dò thì không suất nào là thăm dò', () {
      final plan = buildPlan(exploration: 0);
      expect(plan.allItems.any((i) => i.isExploration), isFalse);
    });

    test('bật thăm dò thì thực đơn đa dạng hơn khi tắt', () {
      // Đây chính là phép đo bong bóng lọc: chạy song song hai cấu hình rồi
      // đếm số món khác nhau xuất hiện qua nhiều ngày.
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
