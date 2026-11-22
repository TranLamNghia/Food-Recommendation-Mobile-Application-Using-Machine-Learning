// ONLINE: the session and the two screens that reach the server.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/auth/auth_screen.dart';
import 'package:nutrition_app/features/onboarding/calculating_screen.dart';

http.Response _json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

http.Response _envelope(int status, String code, String message) => _json({
  'error': {'code': code, 'message': message, 'traceId': 'T'},
}, status);

final _user = {
  'id': '00000001-0000-4000-8000-000000000000',
  'email': 'nghia@example.com',
  'displayName': 'Trần Lâm Nghĩa',
  'avatarUrl': null,
  'onboardingCompletedAt': null,
  'createdAt': '2026-11-20T07:15:30Z',
};

final _tokens = {
  'accessToken': 'ACCESS',
  'refreshToken': 'REFRESH',
  'tokenType': 'Bearer',
  'expiresIn': 3600,
  'user': _user,
};

/// A session with a server behind it, backed by [handler].
AppSession _online(
  Future<http.Response> Function(http.Request) handler, {
  List<String>? calls,
}) => AppSession(
  api: ApiClient(
    baseUrl: 'http://localhost:5055/api/v1',
    httpClient: MockClient((request) {
      calls?.add('${request.method} ${request.url.path}');
      return handler(request);
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

final _targets = {
  'bmrKcal': 1655,
  'tdeeKcal': 2565,
  'dailyCaloriesTarget': 2565,
  'macroTargets': {
    'proteinPct': 20,
    'proteinG': 128.2,
    'carbsPct': 55,
    'carbsG': 352.7,
    'fatPct': 25,
    'fatG': 71.3,
  },
  'mealDistribution': [
    {'mealType': 'breakfast', 'pct': 27.5, 'caloriesKcal': 705},
  ],
};

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

void main() {
  group('offline is still the default and still works', () {
    test('a session with no address has no server', () {
      final session = AppSession();

      expect(session.isOnline, isFalse);
    });

    test('signing in needs no network and asks for no password', () {
      final session = AppSession()
        ..signIn(email: ' nghia@example.com ', displayName: ' Nghĩa ');

      expect(session.accountEmail, 'nghia@example.com');
      expect(session.displayName, 'Nghĩa');
      expect(session.isSignedIn, isTrue);
    });

    test('saving the profile does nothing, rather than failing', () async {
      final session = AppSession();
      _filled(session.profile);

      await session.saveProfile();

      expect(session.profile.energyTarget, isNotNull);
    });

    /// Registering and logging in work in both modes, so the screens have one
    /// path to call. Offline they fall through to the mock.
    test('register and logIn fall through to the mock', () async {
      final session = AppSession();

      await session.register(
        email: 'a@b.vn',
        password: 'MatKhau123',
        displayName: 'A',
      );
      expect(session.accountEmail, 'a@b.vn');

      await session.logIn(email: 'c@d.vn', password: 'MatKhau123');
      expect(session.accountEmail, 'c@d.vn');
    });
  });

  group('§7.1 online', () {
    test('registering takes the account from the server, not the form',
        () async {
      final session = _online((_) async => _json(_tokens, 201));

      await session.register(
        email: 'typed@example.com',
        password: 'MatKhau123',
        displayName: 'typed name',
      );

      // The server is the authority on both: a display name it trimmed or
      // an email it normalised is the one the rest of the app should show.
      expect(session.accountEmail, 'nghia@example.com');
      expect(session.displayName, 'Trần Lâm Nghĩa');
      expect(session.isOnline, isTrue);
    });

    /// The behaviour the whole account exists for: a returning user does not
    /// answer the questions again.
    test('logging in reads back the profile that is already there', () async {
      final calls = <String>[];
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({
            ..._user,
            'hasHealthProfile': true,
            'onboardingCompletedAt': '2026-11-20T08:02:11Z',
            'preferenceStage': 'content',
          });
        }
        if (path.endsWith('/profile/nutrition-targets')) {
          return _json(_targets);
        }
        if (path.endsWith('/profile')) {
          return _json({
            'gender': 'female',
            'dateOfBirth': '1999-07-02',
            'heightCm': 160.0,
            'weightKg': 54.0,
            'activityLevel': 'light',
            'goal': 'lose_weight',
            'conditions': <dynamic>[],
          });
        }
        return _json(const {});
      }, calls: calls);

      await session.logIn(email: 'nghia@example.com', password: 'MatKhau123');

      expect(session.profile.gender, Gender.female);
      expect(session.profile.goal, HealthGoal.loseWeight);
      expect(session.profile.heightCm, 160.0);
      expect(session.hasFinishedOnboarding, isTrue);
      // And the server's own macro split replaced the local default.
      expect(session.profile.proteinPct, 20);
      expect(calls, [
        'POST /api/v1/auth/login',
        'GET /api/v1/auth/me',
        'GET /api/v1/profile',
        'GET /api/v1/profile/nutrition-targets',
      ]);
    });

    /// `GET /profile` answers `409 PROFILE_REQUIRED` for an account that has
    /// never filled the form in. Asking `/auth/me` first is what keeps that
    /// 409 from becoming control flow.
    test('a brand new account is not asked for a profile it has not got',
        () async {
      final calls = <String>[];
      final session = _online((request) async {
        if (request.url.path.endsWith('/auth/login')) return _json(_tokens);
        if (request.url.path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        return _envelope(409, 'PROFILE_REQUIRED', 'Chưa khai báo hồ sơ');
      }, calls: calls);

      await session.logIn(email: 'new@example.com', password: 'MatKhau123');

      expect(calls, ['POST /api/v1/auth/login', 'GET /api/v1/auth/me']);
      expect(session.profile.gender, isNull);
      expect(session.hasFinishedOnboarding, isFalse);
    });

    test('signing out drops the token, so the next call is anonymous',
        () async {
      // The header of the LAST request, so the assertion is about the call
      // made after signing out and not about one made before it.
      String? lastAuthorization;
      final session = _online((request) async {
        lastAuthorization = request.headers['Authorization'];
        if (request.url.path.endsWith('/auth/login')) return _json(_tokens);
        if (request.url.path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (request.method == 'PUT') {
          return _json({
            'profile': {'gender': 'male', 'age': 22, 'bmi': 23.15},
            'nutritionTargets': _targets,
          });
        }
        return _json(_targets);
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      expect(lastAuthorization, 'Bearer ACCESS');

      session.signOut();
      // A complete profile, so the call really goes out and there is a
      // header to look at.
      _filled(session.profile);
      await session.saveProfile();

      expect(session.isSignedIn, isFalse);
      expect(session.hasFinishedOnboarding, isFalse);
      expect(lastAuthorization, isNull);
    });
  });

  group('a body the app cannot read is reported, not fatal', () {
    /// A `200` with an unexpected shape used to throw a `TypeError` out of
    /// `fromJson` — an `Error`, which nothing catches, so the app died. The
    /// thesis chose a screen that explains itself over a crash, and that only
    /// holds if parsing cannot crash either.
    test('a missing field becomes UNEXPECTED_RESPONSE', () async {
      final session = _online((request) async {
        if (request.url.path.endsWith('/auth/login')) return _json(_tokens);
        return _json(const {}); // /auth/me with no id, no email
      });

      await expectLater(
        session.logIn(email: 'a@b.vn', password: 'MatKhau123'),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.unexpectedShape,
          ),
        ),
      );
    });

    test('and so does a field of the wrong type', () async {
      final session = _online(
        (_) async => _json({..._tokens, 'accessToken': 42}),
      );

      await expectLater(
        session.register(
          email: 'a@b.vn',
          password: 'MatKhau123',
          displayName: 'A',
        ),
        throwsA(isA<ApiFailure>()),
      );
    });
  });

  group('§7.2.2 online', () {
    test('saving the profile sends it and takes the targets back', () async {
      final calls = <String>[];
      Map<String, dynamic>? sent;
      final session = _online((request) async {
        if (request.method == 'PUT') {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return _json({
            'profile': const {'gender': 'male'},
            'nutritionTargets': _targets,
          }, 201);
        }
        return _json(_targets);
      }, calls: calls);
      _filled(session.profile);

      await session.saveProfile();

      // One round trip. §7.2.2 recomputes step 1 as it saves, so asking
              // §7.2.3 again would be asking a question already answered.
      expect(calls, ['PUT /api/v1/profile']);
      expect(sent!['dateOfBirth'], '2004-11-04');
      expect(session.profile.proteinPct, 20, reason: 'the server decides');
    });
  });

  group('a screen that explains itself', () {
    testWidgets('the login screen shows what the server refused', (
      tester,
    ) async {
      final session = _online(
        (_) async => _envelope(
          401,
          'INVALID_CREDENTIALS',
          'Email hoặc mật khẩu không đúng',
        ),
      );
      await tester.pumpWidget(
        _app(session, const AuthScreen(mode: AuthMode.login)),
      );

      await tester.enterText(
        find.byType(TextFormField).first,
        'nghia@example.com',
      );
      await tester.enterText(find.byType(TextFormField).last, 'MatKhau123');
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();

      expect(find.textContaining('không đúng'), findsOneWidget);
      expect(session.isSignedIn, isFalse);
    });

    testWidgets('an email already taken is told so in our own words', (
      tester,
    ) async {
      final session = _online(
        (_) async => _envelope(409, 'EMAIL_ALREADY_EXISTS', 'Email đã tồn tại'),
      );
      await tester.pumpWidget(
        _app(session, const AuthScreen(mode: AuthMode.register)),
      );

      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'Nghĩa');
      await tester.enterText(fields.at(1), 'nghia@example.com');
      await tester.enterText(fields.at(2), 'MatKhau123');
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();

      expect(find.textContaining('Hãy đăng nhập'), findsOneWidget);
    });

    /// The thesis decision, as a test: the profile is the one thing the rest
    /// of the app cannot do without, so a failure here stops and explains
    /// rather than walking the user into a survey with nowhere to put the
    /// answers.
    testWidgets('a server that will not take the profile stops the flow', (
      tester,
    ) async {
      var attempts = 0;
      final session = _online((request) async {
        if (request.method == 'PUT') {
          attempts++;
          return _envelope(503, 'ML_UNAVAILABLE', 'Máy chủ đang quá tải');
        }
        return _json(_targets);
      });
      _filled(session.profile);

      await tester.pumpWidget(
        _app(session, CalculatingScreen(profile: session.profile)),
      );
      await tester.pump(const Duration(seconds: 6));
      await tester.pump();

      expect(find.text('Chưa dựng được hạn mức'), findsOneWidget);
      expect(find.textContaining('quá tải'), findsOneWidget);
      // `ML_UNAVAILABLE` is retryable, so the one action offered is honest.
      expect(find.text('Thử lại'), findsOneWidget);
      expect(attempts, 1);

      await tester.tap(find.text('Thử lại'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 6));
      await tester.pump();

      expect(attempts, 2);
    });

    testWidgets('a failure that retrying cannot fix offers no retry', (
      tester,
    ) async {
      final session = _online(
        (request) async => request.method == 'PUT'
            ? _envelope(400, 'VALIDATION_FAILED', 'Chiều cao không hợp lệ')
            : _json(_targets),
      );
      _filled(session.profile);

      await tester.pumpWidget(
        _app(session, CalculatingScreen(profile: session.profile)),
      );
      await tester.pump(const Duration(seconds: 6));
      await tester.pump();

      expect(find.text('Thử lại'), findsNothing);
      expect(find.text('Quay lại sửa thông tin'), findsOneWidget);
    });

    testWidgets('offline, the same screen walks straight through', (
      tester,
    ) async {
      final session = AppSession();
      _filled(session.profile);

      await tester.pumpWidget(
        _app(session, CalculatingScreen(profile: session.profile)),
      );
      await tester.pump(const Duration(seconds: 6));
      await tester.pump();

      expect(find.text('Chưa dựng được hạn mức'), findsNothing);
    });
  });
}
