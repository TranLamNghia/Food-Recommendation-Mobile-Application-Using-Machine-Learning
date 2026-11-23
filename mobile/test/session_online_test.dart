// ONLINE: the session and the two screens that reach the server.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/auth/auth_screen.dart';
import 'package:nutrition_app/features/auth/welcome_screen.dart';
import 'package:nutrition_app/features/home/home_shell.dart';
import 'package:nutrition_app/features/onboarding/onboarding_flow.dart';
import 'package:nutrition_app/features/survey/survey_intro_screen.dart';
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

/// One page of §7.5.1, holding [ids] and nothing else.
///
/// Every handler that lets a sign-in through needs this: the session reads
/// the user's marked dishes as part of signing in, so a handler without a
/// `/foods` route fails on a bookmark list rather than on what the test is
/// about.
http.Response _foodsPage([List<String> ids = const []]) => _json({
  'items': [
    for (final id in ids)
      {
        'id': id,
        'name': 'Món $id',
        'categoryName': 'Thử',
        'dishRole': 'main',
        'spiceLevel': 0,
        'caloriesKcal': 500,
        'servingSizeG': 300,
        'isSafeForUser': true,
        'mark': null,
      },
  ],
  'page': 1,
  'pageSize': 100,
  'totalItems': ids.length,
  'totalPages': ids.isEmpty ? 0 : 1,
});

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
        if (path.endsWith('/foods')) return _foodsPage();
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
      // The marked dishes are read between `/auth/me` and `/profile`, and
      // before the `hasHealthProfile` test below: a bookmark belongs to the
      // account, not to the health profile, so a user who signed up and
      // saved a dish before answering the questions still has it. Twice,
      // because `?mark=` takes one value and there are two lists.
      expect(calls, [
        'POST /api/v1/auth/login',
        'GET /api/v1/auth/me',
        'GET /api/v1/foods',
        'GET /api/v1/foods',
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
        if (request.url.path.endsWith('/foods')) return _foodsPage();
        if (request.url.path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        return _envelope(409, 'PROFILE_REQUIRED', 'Chưa khai báo hồ sơ');
      }, calls: calls);

      await session.logIn(email: 'new@example.com', password: 'MatKhau123');

      // No `/profile` — which is the point. The two `/foods` calls are the
      // marked-dish lists, which an account without a profile still has.
      expect(calls, [
        'POST /api/v1/auth/login',
        'GET /api/v1/auth/me',
        'GET /api/v1/foods',
        'GET /api/v1/foods',
      ]);
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
        if (request.url.path.endsWith('/foods')) return _foodsPage();
        if (request.url.path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (request.url.path.endsWith('/profile/conditions')) {
          return _json(const <dynamic>[]);
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
        if (request.url.path.endsWith('/foods')) return _foodsPage();
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
        if (request.url.path.endsWith('/profile/conditions')) {
          return _json(const <dynamic>[]);
        }
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

      // §7.2.2 recomputes step 1 as it saves, so §7.2.3 is never asked
      // again. The declarations follow in their own call, and with none
      // declared it is still sent: §7.2.5 replaces the whole set, so an
      // empty list is how "I have none" is stored.
      expect(calls, [
        'PUT /api/v1/profile',
        'PUT /api/v1/profile/conditions',
      ]);
      expect(sent!['dateOfBirth'], '2004-11-04');
      expect(session.profile.proteinPct, 20, reason: 'the server decides');
    });
  });

  group('§7.2.5 the declarations, matched by code', () {
    /// The ids come from §7.3.1 at run time. `conditions.id` is
    /// `AUTO_INCREMENT` and follows the seed's insert order, so a hard-coded
    /// id would be hypertension on one database and something else on the
    /// next — declaring the wrong illness with no error anywhere.
    final catalogue = [
      {
        'id': 2,
        'code': 'hypertension',
        'nameVi': 'Tăng huyết áp',
        'conditionType': 'disease',
      },
      {
        'id': 5,
        'code': 'gout',
        'nameVi': 'Gút',
        'conditionType': 'disease',
      },
      {
        'id': 9,
        'code': 'allergy_soy',
        'nameVi': 'Dị ứng đậu nành',
        'conditionType': 'allergy',
      },
    ];

    AppSession sessionWith({
      required List<String> conditions,
      required List<String> allergies,
      Map<String, String> severities = const {},
      List<String>? calls,
      void Function(Object body)? onDeclare,
    }) {
      final session = _online((request) async {
        if (request.url.path.endsWith('/profile/conditions')) {
          if (request.method == 'PUT') {
            onDeclare?.call(jsonDecode(request.body) as Object);
          }
          return _json(const <dynamic>[]);
        }
        if (request.url.path.endsWith('/conditions')) {
          return _json(catalogue);
        }
        if (request.method == 'PUT') {
          return _json({
            'profile': const {'gender': 'male'},
            'nutritionTargets': _targets,
          });
        }
        return _json(_targets);
      }, calls: calls);
      _filled(session.profile);
      session.profile.conditions.addAll(conditions);
      session.profile.allergies.addAll(allergies);
      session.profile.severities.addAll(severities);
      return session;
    }

    test('each code becomes the id this database gave it', () async {
      Object? body;
      final session = sessionWith(
        conditions: ['hypertension'],
        allergies: ['allergy_soy'],
        onDeclare: (b) => body = b,
      );

      await session.saveProfile();

      final sent = ((body as Map)['conditions'] as List)
          .cast<Map<String, dynamic>>();
      expect(
        sent.map((c) => c['conditionId']).toSet(),
        {2, 9},
      );
    });

    /// The severity the user picked has to be the severity that is sent, or
    /// the question was for nothing: `condition_rules.severity_min` is what
    /// reads it, and hypertension tightens its sodium limit at `severe`.
    test('the severity the user picked is the severity sent', () async {
      Object? body;
      final session = sessionWith(
        conditions: ['hypertension', 'gout'],
        allergies: const [],
        severities: const {'hypertension': 'severe'},
        onDeclare: (b) => body = b,
      );

      await session.saveProfile();

      final sent = {
        for (final c in ((body as Map)['conditions'] as List)
            .cast<Map<String, dynamic>>())
          c['conditionId'] as int: c['severity'] as String,
      };
      expect(sent[2], 'severe', reason: 'hypertension, as picked');
      // Gout was declared without touching the control, so it carries the
      // column's own default rather than a number this app invented.
      expect(sent[5], 'moderate');
    });

    /// "Tôi không có bệnh lý nào" is a marker, not a row in `conditions`.
    test('the none-of-the-above marker is never sent', () async {
      Object? body;
      final session = sessionWith(
        conditions: [HealthProfile.noneCode],
        allergies: [HealthProfile.noneCode],
        onDeclare: (b) => body = b,
      );

      await session.saveProfile();

      expect((body as Map)['conditions'], isEmpty);
    });

    /// The one thing that must not happen quietly. These declarations are
    /// what F1 removes dishes by, so a dropped allergy is a dish the user is
    /// allergic to, recommended to them, with nothing reporting it.
    test('a code the server does not know stops the save', () async {
      final session = sessionWith(
        conditions: const [],
        allergies: ['allergy_unicorn'],
      );

      await expectLater(
        session.saveProfile(),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.message,
            'message',
            contains('allergy_unicorn'),
          ),
        ),
      );
    });

    /// With nothing declared there is nothing to look up, so §7.3.1 is not
    /// fetched at all — but §7.2.5 still goes out, because it replaces the
    /// whole set and that is how a cleared declaration is stored.
    test('nothing declared still clears the set, without a lookup', () async {
      final calls = <String>[];
      final session = sessionWith(
        conditions: const [],
        allergies: const [],
        calls: calls,
      );

      await session.saveProfile();

      expect(calls, [
        'PUT /api/v1/profile',
        'PUT /api/v1/profile/conditions',
      ]);
    });

    test('offline, none of this reaches a network', () async {
      final session = AppSession();
      _filled(session.profile);
      session.profile.conditions.add('hypertension');

      await session.saveProfile();

      expect(session.isOnline, isFalse);
    });
  });

  group('PUT /foods/{id}/mark - bookmarks and blocked dishes', () {
    /// The answer is applied, not the request. The two differ exactly when
    /// the other mark had to go, which is the case a local toggle gets wrong.
    test('the mark that is stored is the one the server reports', () async {
      final sent = <Map<String, dynamic>>[];
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.contains('/mark')) {
          sent.add(jsonDecode(request.body) as Map<String, dynamic>);
          return _json({
            'foodId': path.split('/')[4],
            // The server answers `blocked` to a request for `loved`, which
            // cannot happen in practice but is exactly what tells the two
            // apart: a session that trusted its own request would now
            // disagree with the database.
            'kind': 'blocked',
            'markedAt': '2026-11-23T10:00:00+07:00',
          });
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final dish = MockFoods.surveyDeck.first;
      await session.toggleLoved(dish);

      expect(sent.single['kind'], 'loved');
      expect(session.neverAgainIds, contains(dish.id));
      expect(session.lovedIds, isNot(contains(dish.id)));
    });

    test('toggling a bookmark off sends a null kind', () async {
      final sent = <Map<String, dynamic>>[];
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) {
          return _foodsPage(
            request.url.queryParameters['mark'] == 'loved'
                ? [MockFoods.surveyDeck.first.id]
                : const [],
          );
        }
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.contains('/mark')) {
          sent.add(jsonDecode(request.body) as Map<String, dynamic>);
          return _json({'foodId': path.split('/')[4], 'kind': null});
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      // Read back at sign-in, so the bookmark is drawn filled before any
      // screen asks for it.
      final dish = MockFoods.surveyDeck.first;
      expect(session.lovedIds, contains(dish.id));

      await session.toggleLoved(dish);

      expect(sent.single.containsKey('kind'), isTrue);
      expect(sent.single['kind'], isNull);
      expect(session.lovedIds, isNot(contains(dish.id)));
    });

    /// The refusal of §7.5: this is the last dish left in a role some meal
    /// needs. Nothing is stored, so nothing may change here either — a
    /// session that applied it locally would filter the dish out of its own
    /// plans while the server kept suggesting it.
    test('a refused block leaves both sets untouched', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.contains('/mark')) {
          return _envelope(
            409,
            'BLOCK_WOULD_EMPTY_MEAL',
            'Đây là món cuối cùng còn lại cho bữa phụ.',
          );
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final dish = MockFoods.surveyDeck.first;
      await expectLater(
        session.setNeverAgain(dish, true),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.blockWouldEmptyMeal,
          ),
        ),
      );
      expect(session.neverAgainIds, isEmpty);
      expect(session.lovedIds, isEmpty);
    });

    test('offline, the two sets are the whole store', () async {
      final session = AppSession();
      final dish = MockFoods.surveyDeck.first;

      await session.toggleLoved(dish);
      expect(session.lovedIds, contains(dish.id));

      await session.setNeverAgain(dish, true);
      expect(session.neverAgainIds, contains(dish.id));
      expect(session.lovedIds, isNot(contains(dish.id)));

      await session.setNeverAgain(dish, false);
      expect(session.neverAgainIds, isEmpty);
      expect(session.isOnline, isFalse);
    });
  });

  group('PUT /auth/me renames the account', () {
    test('online, the name the server stored is the name kept', () async {
      Map<String, dynamic>? sent;
      final session = _online((request) async {
        if (request.method == 'PUT') {
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          // The server trimmed it, and it is the authority on what is now
          // stored — so the app shows its answer, not the typed text.
          return _json({..._user, 'displayName': 'Lâm Nghĩa'});
        }
        return _json(_tokens);
      });

      await session.updateAccount(displayName: '  Lâm Nghĩa  ');

      expect(sent!['displayName'], 'Lâm Nghĩa');
      expect(session.displayName, 'Lâm Nghĩa');
    });

    test('a name the server refuses leaves the old one in place', () async {
      final session = _online((request) async {
        if (request.method == 'PUT') {
          return _envelope(
            400,
            'VALIDATION_FAILED',
            'Tên hiển thị tối thiểu 2 ký tự',
          );
        }
        if (request.url.path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (request.url.path.endsWith('/foods')) return _foodsPage();
        return _json(_tokens);
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final before = session.displayName;

      await expectLater(
        session.updateAccount(displayName: 'N'),
        throwsA(isA<ApiFailure>()),
      );
      expect(session.displayName, before);
    });

    test('offline it is kept in memory, like everything else', () async {
      final session = AppSession()..signIn(email: 'a@b.vn', displayName: 'A');

      await session.updateAccount(displayName: '  B  ');

      expect(session.displayName, 'B');
      expect(session.isOnline, isFalse);
    });
  });

  group('where signing in leads', () {
    /// The point of having an account: someone who answered the questions
    /// last week is not asked them again.
    ///
    /// The routing used to read `todayPlan != null`, which online is always
    /// null until the plan endpoints are wired — so a returning user with a
    /// complete profile was walked through all nine questions again. These
    /// three cases are the three states an account can be in.
    Future<AppSession> signedIn({
      required bool onboarded,
      required bool hasProfile,
    }) async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({
            ..._user,
            'hasHealthProfile': hasProfile,
            'onboardingCompletedAt': onboarded
                ? '2026-11-20T08:02:11Z'
                : null,
          });
        }
        if (path.endsWith('/profile/nutrition-targets')) {
          return _json(_targets);
        }
        if (path.endsWith('/profile')) {
          return _json({
            'gender': 'male',
            'dateOfBirth': '2004-11-04',
            'heightCm': 172.0,
            'weightKg': 68.5,
            'activityLevel': 'moderate',
            'goal': 'maintain',
            'conditions': <dynamic>[],
          });
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      return session;
    }

    test('a finished account goes straight to the app', () async {
      final session = await signedIn(onboarded: true, hasProfile: true);

      expect(session.hasFinishedOnboarding, isTrue);
      expect(session.profile.isComplete, isTrue);
      expect(WelcomeScreen.nextFor(session), isA<HomeShell>());
    });

    test('a profile filled in but no survey yet goes to the survey', () async {
      final session = await signedIn(onboarded: false, hasProfile: true);

      expect(session.hasFinishedOnboarding, isFalse);
      expect(session.profile.isComplete, isTrue);
      expect(WelcomeScreen.nextFor(session), isA<SurveyIntroScreen>());
    });

    test('a brand new account answers the questions', () async {
      final session = await signedIn(onboarded: false, hasProfile: false);

      expect(session.profile.isComplete, isFalse);
      expect(WelcomeScreen.nextFor(session), isA<OnboardingFlow>());
    });

    /// Offline nothing survives a restart, so a plan built this session is
    /// the only evidence the questions were answered — and that rule is
    /// still the right one there.
    test('offline it still goes by whether a plan was built', () {
      expect(WelcomeScreen.nextFor(AppSession()), isA<OnboardingFlow>());
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
