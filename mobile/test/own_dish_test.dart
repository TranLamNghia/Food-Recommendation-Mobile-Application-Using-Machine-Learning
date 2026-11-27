// ONLINE and offline: §7.5.3, a dish of the user's own.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/models/food_query.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/own_dish.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/diary/diary_screen.dart';
import 'package:nutrition_app/features/food/own_dish_screen.dart';

http.Response _json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

final _user = {
  'id': '00000001-0000-4000-8000-000000000000',
  'email': 'nghia@example.com',
  'displayName': 'Nghĩa',
  'avatarUrl': null,
  'onboardingCompletedAt': null,
  'createdAt': '2026-11-20T07:15:30Z',
};

Map<String, Object?> _created(Map<String, dynamic> sent) => {
  'id': 'own-1',
  'ownerId': _user['id'],
  'name': (sent['name'] as String).trim(),
  'description': null,
  'imageUrl': null,
  'category': {'id': sent['categoryId'], 'name': 'Món nước'},
  'spiceLevel': sent['spiceLevel'],
  'dishRole': sent['dishRole'],
  'nutrition': {
    'servingSizeG': sent['servingSizeG'],
    'caloriesKcal': (sent['nutrition'] as Map)['calories'],
    'proteinG': 24.0,
    'carbsG': 0.0,
    'fatG': 0.0,
    'fiberG': null,
    'sugarG': null,
    'sodiumMg': null,
    'purineMg': null,
  },
  'tags': <dynamic>[],
  'isSafeForUser': true,
  'mark': null,
  'warnings': <dynamic>[],
  'myFeedback': null,
};

AppSession _online(
  List<Map<String, dynamic>> posted,
  http.Response Function(Map<String, dynamic> body) onCreate,
) => AppSession(
  api: ApiClient(
    baseUrl: 'http://localhost:5055/api/v1',
    httpClient: MockClient((request) async {
      final path = request.url.path.replaceFirst('/api/v1', '');
      if (path == '/auth/login') {
        return _json({
          'accessToken': 'ACCESS',
          'refreshToken': 'REFRESH',
          'tokenType': 'Bearer',
          'expiresIn': 3600,
          'user': _user,
        });
      }
      if (path == '/auth/me') {
        return _json({..._user, 'hasHealthProfile': false});
      }
      if (path == '/foods' && request.method == 'POST') {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        posted.add(body);
        return onCreate(body);
      }
      if (path == '/foods') {
        return _json({
          'items': <dynamic>[],
          'page': 1,
          'pageSize': 20,
          'totalItems': 0,
          'totalPages': 0,
        });
      }
      return _json(const {});
    }),
  ),
);

const _draft = OwnDishDraft(
  name: '  Bánh canh cua nhà nấu  ',
  categoryId: 'c7',
  dishRole: 'main',
  servingSizeG: 450,
  kcal: 480,
  spiceLevel: 1,
  proteinG: 24,
  tagIds: [6],
);

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

void main() {
  group('online', () {
    /// A figure left blank must reach the server as null. Sent as 0 it is a
    /// claim — "no sodium" — that the safety filter would act on.
    test('blank figures go as null, not 0', () async {
      final posted = <Map<String, dynamic>>[];
      final session = _online(posted, (body) => _json(_created(body), 201));
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final dish = await session.addOwnDish(_draft);

      final sent = posted.single;
      expect(sent['name'], 'Bánh canh cua nhà nấu');
      expect(sent['tagIds'], [6]);
      final nutrition = sent['nutrition'] as Map<String, dynamic>;
      expect(nutrition['calories'], 480);
      expect(nutrition['proteinG'], 24);
      for (final key in ['carbsG', 'fatG', 'sodiumMg', 'purineMg']) {
        expect(nutrition.containsKey(key), isTrue, reason: key);
        expect(nutrition[key], isNull, reason: key);
      }
      expect(dish.id, 'own-1');
      expect(dish.kcal, 480);
      expect(dish.servingSizeG, 450);
    });

    test('a name already taken is a FOOD_ALREADY_EXISTS failure', () async {
      final session = _online(
        [],
        (_) => _json({
          'error': {
            'code': 'FOOD_ALREADY_EXISTS',
            'message': 'Bạn đã có một món riêng trùng tên',
            'details': null,
            'traceId': 'T',
          },
        }, 409),
      );
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      await expectLater(
        session.addOwnDish(_draft),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.foodAlreadyExists,
          ),
        ),
      );
    });
  });

  group('offline', () {
    test('the dish is searchable, loggable, and not suggested', () async {
      final session = AppSession();
      final dish = await session.addOwnDish(_draft);

      final page = await session.searchFoods(
        const FoodQuery(text: 'banh canh cua', safeOnly: false),
      );
      expect(page.items.map((f) => f.id), [dish.id]);

      await session.addEaten(food: dish, meal: MealType.dinner);
      expect(session.activeDiary.single.food.id, dish.id);
      expect(session.activeDiary.single.kcal, 480);

      expect(
        session.candidates.map((f) => f.id),
        isNot(contains(dish.id)),
        reason: 'the menu builder draws from the catalogue only',
      );

      await expectLater(
        session.addOwnDish(_draft),
        throwsA(isA<ApiFailure>()),
        reason: 'the same name twice',
      );
    });
  });

  group('screen', () {
    testWidgets('the form lays out at phone width', (tester) async {
      tester.view.physicalSize = const Size(720, 3200);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        _app(AppSession(), const OwnDishScreen(initialName: 'Canh chua')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Lưu và ghi vào bữa'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('from the diary: not found, added, and logged', (tester) async {
      tester.view.physicalSize = const Size(1080, 4200);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      final session = AppSession();
      await tester.pumpWidget(_app(session, const DiaryScreen()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ghi món đã ăn'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'Bún mẹ nấu');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Không thấy món? Thêm món của bạn'));
      await tester.pumpAndSettle();
      expect(find.text('Thêm món của tôi'), findsOneWidget);
      // The search text carries over as the name.
      expect(find.widgetWithText(TextFormField, 'Bún mẹ nấu'), findsOneWidget);

      await tester.tap(find.text('Lưu và ghi vào bữa'));
      await tester.pumpAndSettle();
      expect(find.text('Nhập số gam'), findsOneWidget);
      expect(find.text('Bắt buộc'), findsOneWidget);

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Một suất'),
        '400',
      );
      await tester.enterText(
        find.widgetWithText(TextFormField, 'Năng lượng'),
        '520',
      );
      await tester.enterText(find.widgetWithText(TextFormField, 'Natri'), '0,');
      await tester.tap(find.text('Lưu và ghi vào bữa'));
      await tester.pumpAndSettle();
      expect(
        find.text('Nhập một con số'),
        findsNothing,
        reason: '"0," reads as 0 — a number',
      );

      expect(find.text('Thêm món của tôi'), findsNothing);
      final line = session.activeDiary.single;
      expect(line.food.name, 'Bún mẹ nấu');
      expect(line.kcal, 520);
      expect(tester.takeException(), isNull);
    });
  });
}
