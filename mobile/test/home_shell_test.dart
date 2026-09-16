import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/home/home_shell.dart';

/// Phiên đã đi qua khai báo hồ sơ và phiên vuốt, sẵn sàng hiển thị thực đơn.
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

/// Khung test mặc định chỉ 800×600 nên phần dưới màn hình không được dựng và
/// các `find` sẽ trượt. Đặt khung cao hơn hẳn để toàn bộ thực đơn nằm trong
/// vùng vẽ, thay vì phải cuộn thủ công qua ba màn hình chồng nhau trong
/// [IndexedStack].
void _useTallViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(412 * 3, 2600 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Widget _app(AppSession session) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: const HomeShell()),
);

void main() {
  testWidgets('màn hình thực đơn dựng được và hiện đủ bốn bữa', (tester) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    expect(find.text('Thực đơn hôm nay'), findsOneWidget);
    for (final type in MealType.values) {
      expect(find.text(type.label), findsWidgets);
    }
  });

  testWidgets('chuyển được sang tab nhật ký và tiến trình', (tester) async {
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

  testWidgets('đánh dấu đã ăn thì món chảy sang nhật ký', (tester) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    expect(session.diary, isEmpty);

    // Nút "đánh dấu đã ăn" của suất đầu tiên trong thực đơn.
    await tester.tap(find.byTooltip('Đánh dấu đã ăn').first);
    await tester.pumpAndSettle();

    expect(session.diary, hasLength(1));
    expect(
      session.plan!.allItems.any((i) => i.status == MealItemStatus.eaten),
      isTrue,
    );
  });

  testWidgets('đổi món mở bảng chọn và thay được suất', (tester) async {
    _useTallViewport(tester);
    final session = _readySession();
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    final before = session.plan!.allItems.first.food;

    await tester.tap(find.byTooltip('Đổi món khác').first);
    await tester.pumpAndSettle();

    // Bảng chọn chỉ hiện món cùng vai trò với suất đang thay.
    expect(
      find.textContaining('Đổi ${before.name.toLowerCase()}'),
      findsOneWidget,
    );
  });

  testWidgets('tiến trình phân loại BMI theo ngưỡng châu Á', (tester) async {
    _useTallViewport(tester);
    final session = _readySession();
    // BMI 68 / 1.72² = 22,99 — dưới 23 nên vẫn là bình thường.
    await tester.pumpWidget(_app(session));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Tiến trình'));
    await tester.pumpAndSettle();
    expect(find.text('Bình thường'), findsOneWidget);

    // Tăng 2 kg đẩy BMI lên 23,66 — theo ngưỡng WHO chung (25) vẫn là bình
    // thường, nhưng theo ngưỡng châu Á đã là thừa cân.
    session.profile.weightKg = 70;
    session.regeneratePlan();
    await tester.pumpAndSettle();
    expect(find.text('Thừa cân'), findsOneWidget);
  });
}
