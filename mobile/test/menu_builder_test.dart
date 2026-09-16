import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
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
      final deck = MockFoods.surveyDeck;
      final liked = deck.firstWhere((f) => f.cookingMethod == 'Nướng');
      final hated = deck.firstWhere((f) => f.cookingMethod == 'Luộc');

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
      Set<int> idsOver(int days, double exploration) {
        final ids = <int>{};
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
