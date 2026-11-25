import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/api/food_api.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/food_adapters.dart';
import 'package:nutrition_app/data/models/food_query.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/recommender/menu_builder.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/diary/diary_screen.dart';
import 'package:nutrition_app/features/food/food_browse_screen.dart';
import 'package:nutrition_app/features/home/home_shell.dart';

AppSession _readySession() {
  final session = AppSession(rng: math.Random(7))
    ..signIn(email: 'nghia@example.com', displayName: 'Nghĩa');
  session.profile
    ..gender = Gender.male
    ..birthday = DateTime(DateTime.now().year - 24, 6, 15)
    ..heightCm = 172
    ..weightKg = 68
    ..goal = HealthGoal.maintain
    ..activity = ActivityLevel.moderate;

  final deck = MockFoods.surveyDeck;
  session.completeSurvey([
    for (var i = 0; i < deck.length; i++)
      (
        food: deck[i].brief,
        action: i % 3 == 0
            ? SwipeAction.like
            : i % 3 == 1
            ? SwipeAction.neutral
            : SwipeAction.dislike,
      ),
  ]);
  return session;
}

void _tall(WidgetTester tester) {
  tester.view.physicalSize = const Size(412, 4200) * 3;
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

DateTime _today() {
  final now = DateTime.now();
  return DateTime(now.year, now.month, now.day);
}

void main() {
  group('catalogue search, offline', () {
    test('matches a name typed without its marks', () async {
      final session = _readySession();
      final page = await session.searchFoods(const FoodQuery(text: 'pho bo'));
      expect(page.items.map((f) => f.name), contains('Phở bò tái'));
      expect(page.totalItems, page.items.length);
    });

    test('each filter narrows to what it names', () async {
      final session = _readySession();

      final light = await session.searchFoods(const FoodQuery(maxKcal: 250));
      expect(light.items, isNotEmpty);
      expect(light.items.every((f) => f.kcal <= 250), isTrue);

      final soups = await session.searchFoods(
        const FoodQuery(role: DishRole.soup),
      );
      expect(soups.items, isNotEmpty);
      expect(soups.items.every((f) => f.dishRole == 'Món canh'), isTrue);

      final breakfast = await session.searchFoods(
        const FoodQuery(meal: MealType.breakfast),
      );
      final roles = mealRolesOf(MealType.breakfast);
      expect(breakfast.items.every((f) => roles.contains(f.dishRole)), isTrue);

      final groups = await session.foodCategories();
      final group = groups.first;
      final ofGroup = await session.searchFoods(
        FoodQuery(categoryId: group.id, categoryName: group.name),
      );
      expect(ofGroup.items.every((f) => f.category == group.name), isTrue);
    });

    test('the mark filter returns the marked dishes only', () async {
      final session = _readySession();
      final dish = MockFoods.surveyDeck.first.brief;
      await session.toggleLoved(dish);

      final loved = await session.searchFoods(
        const FoodQuery(mark: FoodMark.loved),
      );
      expect(loved.items.map((f) => f.id), [dish.id]);
      expect(loved.items.single.isLoved, isTrue);
    });

    test('turning safety off shows unsafe dishes, flagged', () async {
      final session = _readySession();
      session.profile.conditions.add('allergy_seafood');
      final safe = await session.searchFoods(const FoodQuery());
      final all = await session.searchFoods(const FoodQuery(safeOnly: false));

      expect(all.items.length, greaterThan(safe.items.length));
      expect(all.items.where((f) => !f.isSafeForUser), isNotEmpty);
      expect(safe.items.every((f) => f.isSafeForUser), isTrue);
    });
  });

  group('one meal, offline', () {
    test('rebuilding dinner changes dinner and nothing else', () async {
      final session = _readySession();
      final plan = session.plan!;
      ids(MealType t) => [
        for (final i in plan.slots.firstWhere((s) => s.type == t).items)
          i.food.id,
      ];
      final before = {for (final t in MealType.values) t: ids(t)};

      await session.regenerateMeal(MealType.dinner);

      expect(ids(MealType.dinner), isNotEmpty);
      expect(ids(MealType.dinner), isNot(before[MealType.dinner]));
      for (final t in [MealType.breakfast, MealType.lunch, MealType.snack]) {
        expect(ids(t), before[t], reason: t.label);
      }
    });

    test('a meal with an eaten dish is refused', () async {
      final session = _readySession();
      final slot = session.plan!.slots.firstWhere(
        (s) => s.type == MealType.lunch,
      );
      session.logMeal(food: slot.items.first.dish!, meal: MealType.lunch);

      expect(
        () => session.regenerateMeal(MealType.lunch),
        throwsA(isA<ApiFailure>()),
      );
    });
  });

  group('diary corrections, offline', () {
    test('grams change the portion and the energy', () async {
      final session = _readySession();
      final dish = MockFoods.surveyDeck.first;
      session.logMeal(food: dish, meal: MealType.snack);
      final entry = session.diary.single;
      expect(entry.grams, dish.servingSizeG);

      final half = (dish.servingSizeG / 2).round();
      await session.editEaten(entry, servingSizeG: half);

      final edited = session.diary.single;
      expect(edited.grams, closeTo(half, 0.01));
      expect(edited.kcal, closeTo(dish.kcal * half / dish.servingSizeG, 0.01));
      expect(edited.ateAt, entry.ateAt);
    });

    test('moving a planned dish to another meal moves the serving', () async {
      final session = _readySession();
      final lunch = session.plan!.slots.firstWhere(
        (s) => s.type == MealType.lunch,
      );
      final dish = lunch.items.first.dish!;
      session.logMeal(food: dish, meal: MealType.lunch);
      expect(lunch.items.first.status, MealItemStatus.eaten);

      await session.editEaten(session.diary.single, meal: MealType.snack);

      expect(lunch.items.first.status, MealItemStatus.suggested);
      expect(session.diary.single.meal, MealType.snack);
    });

    test('a dish logged on a past day lands on that day', () async {
      final session = _readySession();
      final yesterday = _today().subtract(const Duration(days: 1));
      await session.addEaten(
        food: MockFoods.surveyDeck.first.brief,
        meal: MealType.dinner,
        ateOn: yesterday,
      );

      expect(session.entriesOn(yesterday), hasLength(1));
      expect(session.entriesOn(_today()), isEmpty);
      expect(session.entriesOn(yesterday).single.ateAt.hour, 12);
    });
  });

  group('screens', () {
    testWidgets('the plan header opens the catalogue, and filters apply', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Tìm món'));
      await tester.pumpAndSettle();
      expect(find.byType(FoodBrowseScreen), findsOneWidget);

      await tester.tap(find.text('Vai trò'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Món canh').last);
      await tester.pumpAndSettle();

      final soups = await session.searchFoods(
        const FoodQuery(role: DishRole.soup),
      );
      expect(find.text('${soups.totalItems} món'), findsOneWidget);
      expect(find.text('Bỏ lọc (1)'), findsOneWidget);

      await tester.enterText(find.byType(TextField), 'canh chua');
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(find.text('Canh chua cá lóc'), findsOneWidget);
      expect(find.text('1 món'), findsOneWidget);
    });

    testWidgets('a meal can be rebuilt from its own header', (tester) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      final before = [
        for (final i in session.plan!.slots
            .firstWhere((s) => s.type == MealType.dinner)
            .items)
          i.food.id,
      ];
      await tester.tap(find.byTooltip('Đổi bữa tối'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Đổi bữa'));
      await tester.pumpAndSettle();

      expect(find.text('Đã đổi bữa tối sang món khác'), findsOneWidget);
      final after = [
        for (final i in session.plan!.slots
            .firstWhere((s) => s.type == MealType.dinner)
            .items)
          i.food.id,
      ];
      expect(after, isNot(before));
    });

    testWidgets('the diary steps back a week and returns to today', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      final dish = MockFoods.surveyDeck.first;
      final lastWeek = _today().subtract(const Duration(days: 7));
      session.logMeal(food: dish, meal: MealType.lunch, at: lastWeek);

      await tester.pumpWidget(_app(session, const DiaryScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Nhật ký hôm nay'), findsOneWidget);

      await tester.tap(find.byTooltip('Tuần trước'));
      await tester.pumpAndSettle();
      expect(find.text('Nhật ký hôm nay'), findsNothing);
      expect(find.text(dish.name), findsOneWidget);

      await tester.tap(find.text('Về hôm nay'));
      await tester.pumpAndSettle();
      expect(find.text('Nhật ký hôm nay'), findsOneWidget);
      expect(find.text(dish.name), findsNothing);
    });

    testWidgets('the calendar opens a past day and refuses a future one', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const DiaryScreen()));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Chọn ngày'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Tháng trước'));
      await tester.pumpAndSettle();
      // The 15th exists in every month.
      await tester.tap(find.text('15').last);
      await tester.pumpAndSettle();

      expect(find.text('Ngày này chưa ghi món nào'), findsOneWidget);
      expect(find.text('Về hôm nay'), findsOneWidget);
    });

    testWidgets('a diary line is corrected from its sheet', (tester) async {
      _tall(tester);
      final session = _readySession();
      final dish = MockFoods.surveyDeck.first;
      session.logMeal(food: dish, meal: MealType.snack);

      await tester.pumpWidget(_app(session, const DiaryScreen()));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Sửa bữa hoặc khối lượng'));
      await tester.pumpAndSettle();
      expect(find.text('Lưu thay đổi'), findsOneWidget);

      await tester.tap(find.text('Bữa tối').last);
      await tester.tap(find.text('½ suất'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Lưu thay đổi'));
      await tester.pumpAndSettle();

      final entry = session.diary.single;
      expect(entry.meal, MealType.dinner);
      expect(entry.grams, closeTo((dish.servingSizeG / 2).round(), 0.01));
      expect(find.text('Đã sửa ${dish.name}'), findsOneWidget);
    });
  });
}
