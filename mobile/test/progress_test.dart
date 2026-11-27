// ONLINE and offline: §7.9.1 progress and §7.10.1 weighing.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/progress/progress_screen.dart';

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

final _targets = {
  'bmrKcal': 1640,
  'tdeeKcal': 2542,
  'dailyCaloriesTarget': 2542,
  'macroTargets': {
    'proteinPct': 15,
    'proteinG': 95.3,
    'carbsPct': 60,
    'carbsG': 381.3,
    'fatPct': 25,
    'fatG': 70.6,
  },
  'mealDistribution': <dynamic>[],
};

typedef _Seen = ({
  String method,
  String path,
  Map<String, String> query,
  Object? body,
});

AppSession _online(
  List<_Seen> seen,
  http.Response Function(http.Request request) route,
) => AppSession(
  api: ApiClient(
    baseUrl: 'http://localhost:5055/api/v1',
    httpClient: MockClient((request) async {
      final path = request.url.path.replaceFirst('/api/v1', '');
      seen.add((
        method: request.method,
        path: path,
        query: request.url.queryParameters,
        body: request.body.isEmpty ? null : jsonDecode(request.body),
      ));
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
      if (path == '/foods') {
        return _json({
          'items': <dynamic>[],
          'page': 1,
          'pageSize': 20,
          'totalItems': 0,
          'totalPages': 0,
        });
      }
      if (path == '/profile/nutrition-targets') return _json(_targets);
      if (path == '/profile') {
        return _json({
          'gender': 'male',
          'dateOfBirth': '2004-11-04',
          'heightCm': 172.0,
          'weightKg': 67.4,
          'activityLevel': 'moderate',
          'goal': 'maintain',
          'conditions': <dynamic>[],
        });
      }
      return route(request);
    }),
  ),
);

HealthProfile _filled(HealthProfile profile) => profile
  ..gender = Gender.male
  ..birthday = DateTime(2004, 11, 4)
  ..heightCm = 172
  ..weightKg = 68.5
  ..activity = ActivityLevel.moderate
  ..goal = HealthGoal.maintain;

DateTime _today() {
  final now = DateTime.now();
  return DateTime(now.year, now.month, now.day);
}

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

void main() {
  group('offline', () {
    /// Filling in last week's forgotten weighing must not make last week's
    /// weight the current one — the target would move backwards.
    test('only the latest weighing becomes the current weight', () async {
      final session = AppSession();
      _filled(session.profile);
      final today = _today();

      expect(await session.logWeight(67.4), isTrue);
      expect(session.profile.weightKg, 67.4);

      final backDated = await session.logWeight(
        69,
        on: today.subtract(const Duration(days: 3)),
      );
      expect(backDated, isFalse);
      expect(session.profile.weightKg, 67.4);

      // Weighing twice on one day keeps one point.
      await session.logWeight(67.2);
      final report = await session.progress();
      expect(
        [for (final w in report.weightTrend) w.weightKg],
        [69, 67.2],
        reason: 'oldest first, one point a day',
      );
    });

    test('a planned serving eaten counts on the natural key', () async {
      final session = AppSession();
      _filled(session.profile);
      final plan = (await session.loadPlan(date: _today()))!;
      final slot = plan.slots.first;
      final item = slot.items.first;

      session.logMeal(food: item.dish!, meal: slot.type);

      final report = await session.progress();
      final summary = report.summary;
      expect(summary.daysLogged, 1);
      expect(summary.daysInRange, 7);
      expect(
        summary.avgCompliancePct,
        closeTo(100 / plan.allItems.length, 1e-9),
      );
      expect(summary.avgTargetKcal, plan.targetKcal);
      expect(summary.avgConsumedKcal, report.series.single.consumedKcal);
      expect(report.series.single.loggedMeals, 1);
    });

    /// A day with a plan and nothing logged is a day nobody wrote down, not a
    /// day of fasting. It is listed, and left out of the means.
    test('a planned day with no line is not a zero in the means', () async {
      final session = AppSession();
      _filled(session.profile);
      final today = _today();
      await session.loadPlan(date: today.subtract(const Duration(days: 1)));
      final plan = (await session.loadPlan(date: today))!;
      final slot = plan.slots.first;
      session.logMeal(food: slot.items.first.dish!, meal: slot.type);

      final report = await session.progress();

      expect(report.series, hasLength(2));
      expect(report.summary.daysLogged, 1);
      expect(report.summary.avgConsumedKcal, report.series.last.consumedKcal);
      expect(report.series.first.logged, isFalse);
    });
  });

  group('online', () {
    test(
      'progress asks for the last seven days and reads the answer',
      () async {
        final seen = <_Seen>[];
        final session = _online(seen, (request) {
          return _json({
            'from': '2026-11-21',
            'to': '2026-11-27',
            'groupBy': 'day',
            'series': [
              {
                'date': '2026-11-26',
                'caloriesConsumed': 2410.0,
                'caloriesTarget': 2573,
                'compliancePct': 83.3,
                'loggedMeals': 4,
              },
            ],
            'summary': {
              'daysLogged': 1,
              'daysInRange': 7,
              'avgCaloriesConsumed': 2410.0,
              'avgCaloriesTarget': 2573,
              'avgCompliancePct': 83.3,
              'avgCalorieDeviationPct': -6.3,
              'totalFeedbacks': 2,
            },
            'weightTrend': [
              {'date': '2026-11-24', 'weightKg': 69.0},
            ],
          });
        });
        await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

        final report = await session.progress();

        final call = seen.last;
        expect(call.path, '/stats/progress');
        final today = _today();
        final from = today.subtract(const Duration(days: 6));
        expect(call.query['to'], _iso(today));
        expect(call.query['from'], _iso(from));
        expect(call.query.containsKey('groupBy'), isFalse);
        expect(report.summary.avgDeviationPct, -6.3);
        expect(report.series.single.targetKcal, 2573);
        expect(report.weightTrend.single.weightKg, 69);
      },
    );

    /// The server recomputes step 1 from the new weight, so the app reads
    /// the profile and targets back — but only when the weight became the
    /// current one.
    test('a weighing reads the profile back only when it moved it', () async {
      final seen = <_Seen>[];
      var current = true;
      final session = _online(seen, (request) {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        return _json({
          'id': 'b1',
          'loggedOn': body['loggedOn'] ?? '2026-11-27',
          'weightKg': body['weightKg'],
          'bmi': 22.78,
          'bmiCategory': 'normal',
          'note': null,
          'profileUpdated': current,
        }, 201);
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      expect(await session.logWeight(67.4), isTrue);
      final post = seen.firstWhere((s) => s.path == '/body-logs');
      expect(post.method, 'POST');
      expect((post.body! as Map)['weightKg'], 67.4);
      expect((post.body! as Map)['loggedOn'], _iso(_today()));
      expect(session.profile.weightKg, 67.4, reason: 'read back from /profile');
      expect(seen.map((s) => s.path), contains('/profile/nutrition-targets'));

      current = false;
      seen.clear();
      expect(
        await session.logWeight(
          70,
          on: _today().subtract(const Duration(days: 5)),
        ),
        isFalse,
      );
      expect(seen.map((s) => s.path), ['/body-logs']);
      expect(session.profile.weightKg, 67.4);
    });
  });

  group('screen', () {
    testWidgets('weighing from the progress screen', (tester) async {
      final session = AppSession();
      _filled(session.profile);
      await tester.pumpWidget(_app(session, const ProgressScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Cân nặng'), findsOneWidget);
      expect(find.text('68,5'), findsOneWidget);

      await tester.ensureVisible(find.text('Ghi cân nặng'));
      await tester.tap(find.text('Ghi cân nặng'));
      await tester.pumpAndSettle();

      final field = find.byType(TextFormField);
      await tester.enterText(field, '19');
      await tester.tap(find.text('Lưu'));
      await tester.pumpAndSettle();
      expect(find.text('Từ 20 đến 300 kg'), findsOneWidget);

      await tester.enterText(field, '67,5');
      await tester.tap(find.text('Lưu'));
      await tester.pumpAndSettle();

      expect(session.profile.weightKg, 67.5);
      expect(
        find.text('Đã ghi. Hạn mức từ ngày mai tính theo cân nặng mới.'),
        findsOneWidget,
      );
      expect(find.text('67,5'), findsOneWidget);
    });

    /// A phone, with bars and a trend to draw: the layout must not overflow
    /// at 360 dp across, with thirty slots in the chart.
    testWidgets('a filled screen lays out at phone width', (tester) async {
      tester.view.physicalSize = const Size(720, 5000);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      final session = AppSession();
      _filled(session.profile).targetWeightKg = 65;
      final today = _today();
      final plan = (await session.loadPlan(date: today))!;
      for (final slot in plan.slots) {
        session.logMeal(food: slot.items.first.dish!, meal: slot.type);
      }
      await session.logWeight(69, on: today.subtract(const Duration(days: 9)));
      await session.logWeight(68.1);

      await tester.pumpWidget(_app(session, const ProgressScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Số ngày đã ghi'), findsOneWidget);
      expect(find.text('1/7'), findsOneWidget);
      expect(find.text('Mục tiêu 65,0 kg'), findsOneWidget);

      await tester.tap(find.text('30 ngày'));
      await tester.pumpAndSettle();
      expect(find.text('1/30'), findsOneWidget);
      expect(find.text('−0,9 kg'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an empty period says so instead of drawing zeros', (
      tester,
    ) async {
      // Tall enough that the energy card is built: a ListView lays out only
      // what is on screen.
      tester.view.physicalSize = const Size(1080, 4000);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      final session = AppSession();
      _filled(session.profile);
      await tester.pumpWidget(_app(session, const ProgressScreen()));
      await tester.pumpAndSettle();

      expect(
        find.text('Chưa có ngày nào được ghi nhật ký trong khoảng này.'),
        findsOneWidget,
      );
      await tester.tap(find.text('30 ngày'));
      await tester.pumpAndSettle();
      expect(
        find.text('Chưa có ngày nào được ghi nhật ký trong khoảng này.'),
        findsOneWidget,
      );
    });
  });
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';
