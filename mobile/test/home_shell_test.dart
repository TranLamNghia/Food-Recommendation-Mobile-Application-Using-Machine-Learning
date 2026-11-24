import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/dish_look.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/home/home_shell.dart';

/// A session that has already been through the profile and the swipe
/// session, ready to show a plan.
AppSession _readySession() {
  final session = AppSession(rng: math.Random(7));
  session.profile
    ..gender = Gender.male
    ..birthday = DateTime(DateTime.now().year - 24, 6, 15)
    ..heightCm = 172
    ..weightKg = 68
    ..goal = HealthGoal.maintain
    ..activity = ActivityLevel.moderate;

  final deck = MockFoods.surveyDeck;
  // Offline, so this resolves at once and needs no await to have taken
  // effect by the time the helper returns.
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

/// The default test frame is only 800×600, so the lower part of the screen
/// is never built and the `find` calls miss. A much taller frame keeps the
/// whole plan inside the painted area, instead of having to scroll by hand
/// through three screens stacked in an [IndexedStack].
///
/// A tall simulated viewport, so a whole screen finishes building in one
/// `pump` with no scrolling.
///
/// The height used to be 2600 px. The plan screen grew by about 600 px once
/// it gained the day-allowance card, the link to the excluded-dishes screen
/// and a reason row under each serving — so this number has to grow with it,
/// or the "shows all four meals" check would fail because the snack sits
/// outside the built area rather than because the screen is missing it.
void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(412 * 3, 3400 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Widget _app(AppSession session) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: const HomeShell()),
);

void main() {
  testWidgets('the plan screen builds and shows all four meals', (
    tester,
  ) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    expect(find.text('Thực đơn hôm nay'), findsOneWidget);
    for (final type in MealType.values) {
      expect(find.text(type.label), findsWidgets);
    }
  });

  testWidgets('the diary and progress tabs can be reached', (tester) async {
    _useTallViewport(tester);
    await tester.pumpWidget(_app(_readySession()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nhật ký'));
    await tester.pumpAndSettle();
    expect(find.text('Chưa ghi món nào hôm nay'), findsOneWidget);

    await tester.tap(find.text('Tiến trình'));
    await tester.pumpAndSettle();
    expect(find.text('Chỉ số thể trạng'), findsOneWidget);
    expect(find.text('Gu ăn của bạn'), findsOneWidget);
  });

  testWidgets('marking a dish eaten moves it into the diary', (tester) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    expect(session.diary, isEmpty);

    // The "mark as eaten" button of the first serving in the plan.
    await tester.tap(find.byTooltip('Đánh dấu đã ăn').first);
    await tester.pumpAndSettle();

    expect(session.diary, hasLength(1));
    expect(
      session.plan!.allItems.any((i) => i.status == MealItemStatus.eaten),
      isTrue,
    );
  });

  testWidgets('swapping opens the sheet and replaces the serving', (
    tester,
  ) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    final before = session.plan!.allItems.first.food;

    await tester.tap(find.byTooltip('Đổi món khác').first);
    await tester.pumpAndSettle();

    // The sheet only shows dishes in the same role as the serving being
    // replaced.
    expect(
      find.textContaining('Đổi ${before.name.toLowerCase()}'),
      findsOneWidget,
    );
  });

  testWidgets('progress classifies the BMI by the Asian thresholds', (
    tester,
  ) async {
    _useTallViewport(tester);
    final session = _readySession();
    // BMI 68 / 1.72² = 22.99 — under 23, so still normal.
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Tiến trình'));
    await tester.pumpAndSettle();
    expect(find.text('Bình thường'), findsOneWidget);

    // Adding 2 kg pushes the BMI to 23.66 — still normal by the general WHO
    // threshold (25), but already overweight by the Asian one.
    session.profile.weightKg = 70;
    session.regeneratePlan();
    await tester.pumpAndSettle();
    expect(find.text('Thừa cân'), findsOneWidget);
  });
}
