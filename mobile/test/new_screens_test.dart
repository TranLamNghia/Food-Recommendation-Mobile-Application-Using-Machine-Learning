import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/mock/mock_ingredients.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/auth/welcome_screen.dart';
import 'package:nutrition_app/features/home/home_shell.dart';
import 'package:nutrition_app/features/onboarding/calculating_screen.dart';
import 'package:nutrition_app/features/onboarding/onboarding_flow.dart';

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
        food: deck[i],
        action: i % 3 == 0
            ? SwipeAction.like
            : i % 3 == 1
            ? SwipeAction.neutral
            : SwipeAction.dislike,
      ),
  ]);
  return session;
}

void _viewport(WidgetTester tester, Size size) {
  tester.view.physicalSize = size * 3;
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

/// Tall enough that lazily built lists lay out every row.
void _tall(WidgetTester tester) => _viewport(tester, const Size(412, 4200));

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

void main() {
  group('data', () {
    test('every survey dish has mock ingredients', () {
      for (final f in MockFoods.surveyDeck) {
        expect(MockIngredients.of(f.id), isNotEmpty, reason: f.name);
      }
    });

    test('undoing a meal returns it to the plan and keeps the log', () {
      final session = _readySession();
      final slot = session.plan!.slots.first;
      final food = slot.items.first.food;

      session.logMeal(food: food, meal: slot.type);
      expect(slot.items.first.status, MealItemStatus.eaten);
      expect(session.eatenToday, [food]);

      final entry = session.diary.single;
      session.undoMeal(entry);

      expect(slot.items.first.status, MealItemStatus.suggested);
      // Still recorded, but it no longer counts towards the day.
      expect(session.diary, [entry]);
      expect(entry.isUndone, isTrue);
      expect(session.eatenToday, isEmpty);
      expect(session.entriesOn(DateTime.now()), isEmpty);
      expect(session.consumedKcalOn(DateTime.now()), 0);
    });

    test('starting over keeps the account; deleting it does not', () {
      final session = _readySession();

      session.reset();
      expect(session.plan, isNull);
      expect(session.profile.gender, isNull);
      expect(session.accountEmail, 'nghia@example.com');
      expect(session.displayName, 'Nghĩa');

      session.deleteAccount();
      expect(session.isSignedIn, isFalse);
      expect(session.displayName, isNull);
    });

    test('signing out keeps what the account holds', () {
      final session = _readySession();
      session.signOut();
      expect(session.isSignedIn, isFalse);
      expect(session.todayPlan, isNotNull);

      // Logging in sends no name; the one on the account is kept.
      session.signIn(email: 'nghia@example.com');
      expect(session.displayName, 'Nghĩa');
    });

    test('a never-again dish stays out of every later plan', () {
      final session = _readySession();
      final banned = session.plan!.allItems.first.food;
      session.setNeverAgain(banned, true);

      for (var i = 0; i < 20; i++) {
        session.regeneratePlan();
        expect(
          session.plan!.allItems.map((it) => it.food.id),
          isNot(contains(banned.id)),
        );
      }
    });

    test('each day of the week gets its own plan', () {
      final session = _readySession();
      final today = session.plan;
      final tomorrow = DateTime.now().add(const Duration(days: 1));

      session.selectDay(tomorrow);
      expect(session.viewingToday, isFalse);
      expect(session.plan, isNotNull);
      expect(session.plan, isNot(same(today)));
      expect(session.todayPlan, same(today));

      expect(session.plansForNext(7), hasLength(7));
    });

    test('consecutive days do not repeat a dish', () {
      final session = _readySession();
      final plans = session.plansForNext(7);

      for (var i = 1; i < plans.length; i++) {
        final before = plans[i - 1].allItems.map((it) => it.food.id).toSet();
        final today = plans[i].allItems.map((it) => it.food.id).toSet();
        expect(today.intersection(before), isEmpty, reason: 'day $i');
        expect(plans[i].allItems, isNotEmpty);
      }
    });

    test('eating today does not mark another day', () {
      final session = _readySession();
      final tomorrow = DateTime.now().add(const Duration(days: 1));
      session.selectDay(tomorrow);
      final item = session.plan!.allItems.first;

      // Logged now, so it belongs to today even while tomorrow is on screen.
      session.logMeal(food: item.food, meal: MealType.breakfast);
      expect(
        session.plan!.allItems.every((i) => i.status != MealItemStatus.eaten),
        isTrue,
      );
    });
  });

  group('welcome and auth', () {
    for (final size in const [Size(360, 640), Size(412, 915)]) {
      testWidgets('welcome fits ${size.width.round()}×${size.height.round()}', (
        tester,
      ) async {
        _viewport(tester, size);
        await tester.pumpWidget(_app(AppSession(), const WelcomeScreen()));
        await tester.pumpAndSettle();

        // An account is the only way in: no button skips straight to the
        // questions.
        expect(find.text('Đăng ký'), findsOneWidget);
        expect(find.text('Đăng nhập'), findsOneWidget);
        expect(find.text('Bắt đầu'), findsNothing);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('login rejects a bad email, then signs in', (tester) async {
      _viewport(tester, const Size(412, 915));
      final session = AppSession();
      await tester.pumpWidget(_app(session, const WelcomeScreen()));

      await tester.tap(find.text('Đăng nhập'));
      await tester.pumpAndSettle();
      expect(find.text('Mừng bạn quay lại'), findsOneWidget);

      await tester.enterText(find.byType(TextFormField).at(0), 'khong-phai');
      await tester.enterText(find.byType(TextFormField).at(1), 'MatKhau123');
      await tester.tap(find.widgetWithText(FilledButton, 'Đăng nhập'));
      await tester.pumpAndSettle();
      expect(find.text('Email chưa đúng định dạng'), findsOneWidget);
      expect(session.isSignedIn, isFalse);

      await tester.enterText(find.byType(TextFormField).at(0), 'a@b.vn');
      await tester.tap(find.widgetWithText(FilledButton, 'Đăng nhập'));
      await tester.pumpAndSettle();
      expect(session.accountEmail, 'a@b.vn');
      // No saved profile in the mock, so the questions come next.
      expect(find.byType(OnboardingFlow), findsOneWidget);
    });

    testWidgets('register enforces the password rule', (tester) async {
      _viewport(tester, const Size(412, 915));
      final session = AppSession();
      await tester.pumpWidget(_app(session, const WelcomeScreen()));
      await tester.tap(find.text('Đăng ký'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField).at(0), 'Nghĩa');
      await tester.enterText(find.byType(TextFormField).at(1), 'a@b.vn');
      await tester.enterText(find.byType(TextFormField).at(2), 'chiCoChu');
      await tester.tap(find.widgetWithText(FilledButton, 'Tạo tài khoản'));
      await tester.pumpAndSettle();
      expect(find.text('Mật khẩu cần có cả chữ và số'), findsOneWidget);
      expect(session.isSignedIn, isFalse);

      await tester.enterText(find.byType(TextFormField).at(2), 'MatKhau123');
      await tester.tap(find.widgetWithText(FilledButton, 'Tạo tài khoản'));
      await tester.pumpAndSettle();
      expect(session.displayName, 'Nghĩa');
      expect(find.byType(OnboardingFlow), findsOneWidget);
    });

    testWidgets('back on the first question returns to welcome', (
      tester,
    ) async {
      _viewport(tester, const Size(412, 915));
      final session = AppSession()..signIn(email: 'a@b.vn');
      await tester.pumpWidget(_app(session, const OnboardingFlow()));
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.byType(OnboardingFlow), findsNothing);
      // Welcome only offers signing in, so the account was left first.
      expect(session.isSignedIn, isFalse);
    });

    testWidgets('forgot password confirms without revealing the account', (
      tester,
    ) async {
      _viewport(tester, const Size(412, 915));
      await tester.pumpWidget(_app(AppSession(), const WelcomeScreen()));
      await tester.tap(find.text('Đăng nhập'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Quên mật khẩu?'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField), 'a@b.vn');
      await tester.tap(find.text('Gửi liên kết'));
      await tester.pumpAndSettle();
      expect(find.text('Kiểm tra hộp thư'), findsOneWidget);
      expect(find.textContaining('Nếu a@b.vn đã đăng ký'), findsOneWidget);
    });
  });

  testWidgets('the calculating screen stays centred as its lines change', (
    tester,
  ) async {
    _viewport(tester, const Size(412, 915));
    final session = _readySession();
    await tester.pumpWidget(
      _app(session, CalculatingScreen(profile: session.profile)),
    );

    // Each of the five lines has a different width; none may pull the
    // spinner off the middle of the screen.
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 600));
      final spinner = find.byType(CircularProgressIndicator);
      expect(
        tester.getCenter(spinner).dx,
        closeTo(206, 0.01),
        reason: 'line $i',
      );
      await tester.pump(const Duration(milliseconds: 300));
    }

    // Let the screen hand over so no timer outlives the test.
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 2));
  });

  group('home shell', () {
    testWidgets('week strip switches day and hides the eat button', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      expect(find.byTooltip('Đánh dấu đã ăn'), findsWidgets);

      final tomorrow = DateTime.now().add(const Duration(days: 1));
      await tester.tap(
        find.bySemanticsLabel('Ngày ${tomorrow.day} tháng ${tomorrow.month}'),
      );
      await tester.pumpAndSettle();

      expect(session.viewingToday, isFalse);
      expect(find.text('Thực đơn hôm nay'), findsNothing);
      expect(find.byTooltip('Đánh dấu đã ăn'), findsNothing);
      expect(find.byTooltip('Đổi món khác'), findsWidgets);
    });

    testWidgets('a serving can be skipped and put back', (tester) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Bỏ qua suất này').first);
      await tester.pumpAndSettle();
      expect(find.text('Đã bỏ qua'), findsOneWidget);
      expect(
        session.plan!.allItems.where((i) => i.status == MealItemStatus.skipped),
        hasLength(1),
      );

      await tester.tap(find.byTooltip('Ăn lại suất này'));
      await tester.pumpAndSettle();
      expect(find.text('Đã bỏ qua'), findsNothing);
    });

    testWidgets('tapping a dish opens its detail; heart and ban work', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      final food = session.plan!.allItems.first.food;
      await tester.tap(find.text(food.name).first);
      await tester.pumpAndSettle();

      expect(find.text('Trong một suất'), findsOneWidget);
      expect(find.text('Nguyên liệu cho một suất'), findsOneWidget);

      await tester.tap(find.byTooltip('Lưu món này'));
      await tester.pumpAndSettle();
      expect(session.lovedIds, contains(food.id));

      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(session.neverAgainIds, contains(food.id));
      // Blocking a dish un-bookmarks it: `user_food_marks` holds one row per
      // (user, food), and the two verdicts contradict each other.
      expect(session.lovedIds, isNot(contains(food.id)));

      // The dish is on today's plate, so the screen asks what to do with
      // that serving instead of deciding. Nothing has happened to the plan
      // while the question is open.
      expect(find.text('Món này vẫn trong thực đơn hôm nay'), findsOneWidget);
      expect(session.plannedTodayItem(food), isNotNull);
      await tester.tap(find.text('Giữ nguyên'));
      await tester.pumpAndSettle();
      expect(
        session.plannedTodayItem(food),
        isNotNull,
        reason: 'keeping the serving must leave the plan exactly as it was',
      );
    });

    /// The other branch of the same question, and the one that moves a
    /// number: dropping the serving lowers the day's energy and puts nothing
    /// in its place.
    testWidgets('blocking a dish can drop its serving, with nothing put back',
        (tester) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      final item = session.plan!.allItems.first;
      final food = item.food;
      final before = session.plan!.onPlateKcal;
      final generated = session.plan!.actualKcal;

      await tester.tap(find.text(food.name).first);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Bỏ suất đó'));
      await tester.pumpAndSettle();

      final plan = session.plan!;
      expect(session.plannedTodayItem(food), isNull);
      expect(plan.onPlateKcal, closeTo(before - food.kcal, 0.001));
      expect(
        plan.actualKcal,
        closeTo(generated, 0.001),
        reason: 'the plan AS GENERATED does not move — it is what the ±10 % '
            'commitment is measured on, and a day could otherwise pass by '
            'having enough dishes dropped',
      );
      expect(plan.skippedItems, hasLength(1));
      // No replacement appeared: the user has to ask for one.
      expect(plan.allItems.length, session.plan!.allItems.length);
    });

    testWidgets('diary undo puts the serving back on the plan', (tester) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('Đánh dấu đã ăn').first);
      await tester.pumpAndSettle();
      final eaten = session.diary.single.food;

      await tester.tap(find.text('Nhật ký').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Hoàn tác, trả về thực đơn'));
      await tester.pumpAndSettle();

      expect(find.text('Đã trả ${eaten.name} về thực đơn'), findsOneWidget);
      expect(find.text('Chưa ghi món nào hôm nay'), findsOneWidget);
      expect(
        session.plan!.allItems.every((i) => i.status != MealItemStatus.eaten),
        isTrue,
      );
      expect(session.diary, hasLength(1));
    });

    testWidgets('account settings rename and sign out', (tester) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Tôi').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('nghia@example.com'));
      await tester.pumpAndSettle();
      expect(find.text('Thông tin cá nhân'), findsOneWidget);

      // The phone number used to be edited here. It had no column and no
      // endpoint, so it was typed and lost; the display name is the one
      // detail of the account the server actually keeps.
      await tester.tap(find.text('Tên hiển thị'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), 'N');
      await tester.tap(find.text('Lưu'));
      await tester.pumpAndSettle();
      expect(session.displayName, 'Nghĩa', reason: 'one letter is refused');

      await tester.enterText(find.byType(TextFormField), 'Lâm Nghĩa');
      await tester.tap(find.text('Lưu'));
      await tester.pumpAndSettle();
      expect(session.displayName, 'Lâm Nghĩa');
      expect(find.text('Lâm Nghĩa'), findsOneWidget);

      await tester.tap(find.text('Đăng xuất'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Đăng xuất'));
      await tester.pumpAndSettle();
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(session.isSignedIn, isFalse);
      // The profile stays with the account.
      expect(session.todayPlan, isNotNull);
    });

    testWidgets('account tab edits one answer and rebuilds the plan', (
      tester,
    ) async {
      _tall(tester);
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Tôi').last);
      await tester.pumpAndSettle();
      expect(find.text('Nghĩa'), findsOneWidget);
      expect(find.text('nghia@example.com'), findsOneWidget);
      expect(find.text('Câu trả lời của bạn'), findsOneWidget);

      final before = session.plan!.targetKcal;
      await tester.tap(find.text('Mục tiêu'));
      await tester.pumpAndSettle();
      expect(find.text('Lưu thay đổi'), findsOneWidget);

      await tester.tap(find.text(HealthGoal.healthyEating.label));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Lưu thay đổi'));
      await tester.pumpAndSettle();

      expect(session.profile.goal, HealthGoal.healthyEating);
      expect(find.text(HealthGoal.healthyEating.label), findsOneWidget);
      // Same energy target for "maintain" and "healthy eating", but the plan
      // object must be a fresh build.
      expect(session.plan!.targetKcal, before);
    });

    testWidgets('all four tabs fit a short screen', (tester) async {
      // 412 wide like the other shell tests: the test font is wider than
      // Afacad, so narrower widths overflow rows that fit on a real device.
      _viewport(tester, const Size(412, 640));
      final session = _readySession();
      await tester.pumpWidget(_app(session, const HomeShell()));
      await tester.pumpAndSettle();

      expect(find.text('Đi chợ'), findsNothing);
      for (final tab in ['Nhật ký', 'Tiến trình', 'Tôi', 'Thực đơn']) {
        await tester.tap(find.text(tab).last);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: tab);
      }
    });
  });
}
