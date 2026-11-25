// ONLINE: the session and the two screens that reach the server.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/models/food_brief.dart';
import 'package:nutrition_app/data/api/food_api.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/food_adapters.dart';
import 'package:nutrition_app/data/mock/mock_foods.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
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

  group('§7.4 the taste survey - what ends onboarding', () {
    Map<String, Object?> deckCard(String id) => {
      'id': id,
      'name': 'Món $id',
      'imageUrl': null,
      'categoryName': 'Món nước',
      'spiceLevel': 1,
      'dishRole': 'main',
      'caloriesKcal': 420,
      'servingSizeG': 300,
      'tags': ['Món nước'],
    };

    Map<String, Object?> deckBody(List<String> ids) => {
      'sessionId': 'a1b2c3d4-0000-4000-8000-000000000000',
      'totalItems': ids.length,
      'minRequired': 20,
      'items': [for (final id in ids) deckCard(id)],
    };

    Map<String, Object?> submitBody(int opinionated) => {
      'sessionId': 'a1b2c3d4-0000-4000-8000-000000000000',
      'onboardingCompletedAt': '2026-11-23T10:30:00+07:00',
      'recorded': {
        'total': opinionated + 1,
        'opinionated': opinionated,
        'skipped': 1,
        'droppedUnsafe': 0,
      },
      'preferenceProfile': {
        'stage': 'content',
        'nSignals': opinionated,
        'alpha': 0.0,
        'featureVersion': 'v2',
      },
      'tasteSummary': {
        'topLikedCategories': ['Món nước'],
        'topLikedTastes': ['salty'],
      },
    };

    /// The defect this whole group exists for. Before the survey reached the
    /// server, `completeSurvey` built a vector locally and returned, so
    /// `onboarding_completed_at` stayed null — and `welcome_screen` reads
    /// that stamp on every launch, which sent the user back to the survey
    /// after they had finished it. For good.
    test('submitting the survey is what sets hasFinishedOnboarding', () async {
      Map<String, dynamic>? posted;
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': true});
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
        if (path.endsWith('/onboarding/survey')) {
          if (request.method == 'POST') {
            posted = jsonDecode(request.body) as Map<String, dynamic>;
            return _json(submitBody(24));
          }
          return _json(deckBody(['f1', 'f2', 'f3']));
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      expect(session.hasFinishedOnboarding, isFalse);

      final deck = await session.loadSurveyDeck();
      expect(deck.map((c) => c.id), ['f1', 'f2', 'f3']);
      expect(session.surveyDeck?.minRequired, 20);

      await session.completeSurvey([
        (food: deck[0], action: SwipeAction.like),
        (food: deck[1], action: SwipeAction.dislike),
        (food: deck[2], action: SwipeAction.unknown),
      ]);

      expect(session.hasFinishedOnboarding, isTrue);
      expect(session.onboardingCompletedAt, isNotNull);
      // The session id handed out by the deck call travels back, which is
      // what makes a retry recognisable as the same event.
      expect(posted!['sessionId'], 'a1b2c3d4-0000-4000-8000-000000000000');
      expect(posted!['swipes'], [
        {'foodId': 'f1', 'action': 'like'},
        {'foodId': 'f2', 'action': 'dislike'},
        {'foodId': 'f3', 'action': 'unknown'},
      ]);
      expect(session.surveyOutcome?.stage, 'content');
      expect(session.surveyOutcome?.nSignals, 24);
      expect(session.surveyOutcome?.topLikedCategories, ['Món nước']);
    });

    /// The request carries ids and codes and nothing else. Rocchio runs in
    /// the ML service, and a second implementation of it on this side would
    /// be the one nothing compares — so the local vector is left alone.
    test('the local preference vector is not built online', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/onboarding/survey')) {
          return request.method == 'POST'
              ? _json(submitBody(24))
              : _json(deckBody(['f1']));
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final deck = await session.loadSurveyDeck();
      await session.completeSurvey([
        (food: deck.single, action: SwipeAction.like),
      ]);

      expect(session.hasFinishedOnboarding, isTrue);
      // Still the empty vector: every weight zero, so no dish outranks
      // another on taste. `session.preference` builds a fresh empty profile
      // on each read while nothing is stored, which is why this asserts the
      // CONTENT rather than the identity.
      expect(session.preference.isEmpty, isTrue);
      // And no plan was built here either. Online the day comes from
      // §7.6, which this branch has not reached; building one locally would
      // put a second, disagreeing plan on screen.
      expect(session.plan, isNull);
    });

    /// `422` when too few swipes carried an opinion. Nothing is stamped, so
    /// the app must not treat the survey as done — the screen offers a fresh
    /// deck instead.
    test('too few opinions leaves onboarding unfinished', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/onboarding/survey')) {
          if (request.method == 'POST') {
            return _envelope(
              422,
              'ONBOARDING_INSUFFICIENT',
              'Cần ít nhất 20 món có ý kiến',
            );
          }
          return _json(deckBody(['f1']));
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final deck = await session.loadSurveyDeck();

      await expectLater(
        session.completeSurvey([
          (food: deck.single, action: SwipeAction.unknown),
        ]),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.onboardingInsufficient,
          ),
        ),
      );
      expect(session.hasFinishedOnboarding, isFalse);
      expect(session.surveyOutcome, isNull);
    });

    test('offline, the deck is the mock one and the cold start is local', () async {
      final session = AppSession();
      _filled(session.profile);

      final deck = await session.loadSurveyDeck();

      expect(deck, isNotEmpty);
      // No session id: there is nowhere to store a session offline, and
      // `completeSurvey` uses its absence to know which path it is on.
      expect(session.surveyDeck, isNull);

      await session.completeSurvey([
        for (final card in deck) (food: card, action: SwipeAction.like),
      ]);

      // Offline nothing stamps the account, and the first plan is built on
      // the spot instead.
      expect(session.hasFinishedOnboarding, isFalse);
      expect(session.surveyOutcome, isNull);
      expect(session.plan, isNotNull);
    });
  });

  group('§7.5 the catalogue - and the empty saved lists it fixes', () {
    /// Server ids, deliberately nothing `MockFoods` holds. That is the whole
    /// defect: the saved screens used to filter the mock deck by these, and
    /// online no id could ever match.
    const lovedId = '7f3a0000-0000-4000-8000-000000000001';
    const blockedId = '7f3a0000-0000-4000-8000-000000000002';

    http.Response markedPage(String mark) => _json({
      'items': [
        {
          'id': mark == 'loved' ? lovedId : blockedId,
          'name': mark == 'loved' ? 'Bún bò Huế' : 'Chè ba màu',
          'categoryName': 'Món nước',
          'dishRole': mark == 'loved' ? 'main' : 'dessert',
          'spiceLevel': 2,
          'caloriesKcal': 480,
          'servingSizeG': 350,
          'isSafeForUser': true,
          'mark': mark,
        },
      ],
      'page': 1,
      'pageSize': 100,
      'totalItems': 1,
      'totalPages': 1,
    });

    AppSession signedIn(List<String>? calls) => _online((request) async {
      final path = request.url.path;
      if (path.endsWith('/auth/login')) return _json(_tokens);
      if (path.endsWith('/auth/me')) {
        return _json({..._user, 'hasHealthProfile': false});
      }
      if (path.endsWith('/foods')) {
        return markedPage(request.url.queryParameters['mark'] ?? 'loved');
      }
      if (path.contains('/foods/')) {
        return _json({
          'id': lovedId,
          'name': 'Bún bò Huế',
          'description': 'Món nước xứ Huế.',
          'imageUrl': null,
          'category': {'id': 'c1', 'name': 'Món nước'},
          'spiceLevel': 2,
          'dishRole': 'main',
          'nutrition': {
            'servingSizeG': 350,
            'caloriesKcal': 480,
            'proteinG': 28.0,
            'carbsG': 55.0,
            'fatG': 14.0,
            'fiberG': 1.2,
            'sugarG': 3.0,
            'sodiumMg': 1600.0,
            // Deliberately absent, as they are for most of the 318 dishes.
            'purineMg': null,
            'calciumMg': null,
          },
          'tags': [
            {'id': 3, 'nameVi': 'Giàu purin', 'tagType': 'nutrition'},
          ],
          'isSafeForUser': false,
          'mark': 'loved',
          'warnings': [
            {
              'conditionId': 5,
              'conditionCode': 'gout',
              'conditionName': 'Gút',
              'ruleType': 'exclude_tag',
              'message': 'Món có nhãn “Giàu purin”, không phù hợp với Gút',
              'isHard': true,
              'missingData': false,
            },
          ],
          'myFeedback': null,
        });
      }
      return _json(const {});
    }, calls: calls);

    /// The defect, stated as a test: the dishes behind the marks have to come
    /// from the server, because their ids are the server's.
    test('signing in brings back the saved dishes, not just their ids',
        () async {
      final session = signedIn(null);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      expect(session.lovedIds, {lovedId});
      expect(session.neverAgainIds, {blockedId});

      final saved = session.savedDishes(FoodMark.loved);
      expect(saved, hasLength(1));
      expect(saved.single.name, 'Bún bò Huế');
      expect(session.savedDishes(FoodMark.blocked).single.name, 'Chè ba màu');

      // And none of it could have come from the mock deck, which is what the
      // old version filtered.
      expect(
        MockFoods.surveyDeck.map((f) => f.id),
        isNot(contains(lovedId)),
        reason: 'the fixture must use ids the mock cannot supply, or this '
            'test would pass against the broken version too',
      );
    });

    test('marking a dish keeps the id, the set and the dish in step',
        () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/mark')) {
          return _json({'foodId': lovedId, 'kind': 'blocked'});
        }
        if (path.endsWith('/foods')) {
          return markedPage(request.url.queryParameters['mark'] ?? 'loved');
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final dish = session.savedDishes(FoodMark.loved).single;

      await session.setNeverAgain(dish, true);

      expect(session.lovedIds, isNot(contains(lovedId)));
      expect(session.neverAgainIds, contains(lovedId));
      expect(session.savedDishes(FoodMark.loved), isEmpty);
      expect(
        session.savedDishes(FoodMark.blocked).map((d) => d.id),
        containsAll([lovedId, blockedId]),
      );
    });

    test('§7.5.2 comes back whole, with the gaps left as gaps', () async {
      final session = signedIn(null);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final detail = await session.dishDetail(
        session.savedDishes(FoodMark.loved).single,
      );

      expect(detail.nutrition.caloriesKcal, 480);
      expect(detail.nutrition.sodiumMg, 1600.0);
      // `null`, not 0. A health app printing "Purin 0 mg" for an unmeasured
      // dish has told a gout patient it is safe.
      expect(detail.nutrition.purineMg, isNull);
      expect(detail.nutrition.calciumMg, isNull);
      // Absent from the answer altogether, which is also not zero.
      expect(detail.nutrition.ironMg, isNull);

      final share = detail.nutrition.macroShare;
      expect(share, isNotNull);
      expect(
        share!.protein + share.carbs + share.fat,
        closeTo(1.0, 1e-9),
        reason: 'the three shares are normalised by their own total',
      );

      expect(detail.warnings, hasLength(1));
      expect(detail.warnings.single.conditionCode, 'gout');
      expect(detail.warnings.single.message, contains('Gút'));
      expect(detail.brief.category, 'Món nước');
      expect(detail.brief.tags, ['Giàu purin']);
      expect(detail.brief.mark, FoodMark.loved);
      expect(detail.myFeedback, isNull);
    });

    /// Online there is no local taste vector and no endpoint that scores one
    /// dish, so the "Hợp gu" tag has to disappear rather than show a number
    /// this side made up.
    test('no taste percentage is invented online', () async {
      final session = signedIn(null);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      expect(session.scoreOf(session.savedDishes(FoodMark.loved).single),
          isNull);
    });

    test('offline, the detail is the mock dish and its gaps are honest',
        () async {
      final session = AppSession();
      final dish = MockFoods.surveyDeck.first;

      final detail = await session.dishDetail(dish.brief);

      expect(detail.nutrition.caloriesKcal, dish.kcal.toDouble());
      expect(detail.nutrition.proteinG, dish.protein);
      // The mock holds no micronutrients, so neither does this.
      expect(detail.nutrition.calciumMg, isNull);
      expect(detail.nutrition.vitaminCMg, isNull);
      // Offline the F1 verdict comes from `rules/dish_screening.dart`, which
      // the screen asks separately; duplicating it here would put the same
      // verdict in two places.
      expect(detail.warnings, isEmpty);
    });

    test('offline, a dish the mock does not hold is a 404, not a crash',
        () async {
      final session = AppSession();

      await expectLater(
        session.dishDetail(const FoodBrief(
          id: 'nope',
          name: 'Món không có',
          category: '',
          dishRole: 'main',
          spiceLevel: 0,
          kcal: 0,
          servingSizeG: 0,
        )),
        throwsA(isA<ApiFailure>()
            .having((f) => f.code, 'code', ApiFailure.notFound)),
      );
    });
  });

  group('§7.4.3 the filter screen\'s live count', () {
    http.Response catalogue() => _json([
      {
        'id': 2,
        'code': 'hypertension',
        'nameVi': 'Tăng huyết áp',
        'conditionType': 'disease',
        'description': null,
      },
      {
        'id': 7,
        'code': 'allergy_seafood',
        'nameVi': 'Dị ứng hải sản',
        'conditionType': 'allergy',
        'description': null,
      },
    ]);

    http.Response countBody({
      int remaining = 227,
      List<String> emptyRoles = const [],
      List<String> notes = const [],
    }) => _json({
      'totalFoods': 318,
      'remainingFoods': remaining,
      'removedFoods': 318 - remaining,
      'byDishRole': {'main': 80, 'soup': 30, 'side_protein': 60},
      'emptyRequiredRoles': emptyRoles,
      'enoughForSurvey': remaining >= 30,
      'surveyDeckSize': remaining >= 30 ? 30 : remaining,
      'notes': notes,
    });

    test('codes are mapped to ids, with the severity each one was given',
        () async {
      Map<String, dynamic>? posted;
      final calls = <String>[];
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/conditions')) return catalogue();
        if (path.endsWith('/candidates/count')) {
          posted = jsonDecode(request.body) as Map<String, dynamic>;
          return countBody();
        }
        return _json(const {});
      }, calls: calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final count = await session.countCandidates(
        codes: {'hypertension', 'allergy_seafood'},
        severities: {'hypertension': 'severe'},
      );

      expect(posted!['conditions'], containsAll([
        {'conditionId': 2, 'severity': 'severe'},
        // No severity was picked for the allergy, so the column's own
        // default travels — every allergy rule applies from `mild` anyway,
        // which is why the screen does not ask.
        {'conditionId': 7, 'severity': 'moderate'},
      ]));
      expect(count.totalFoods, 318);
      expect(count.remainingFoods, 227);
      expect(count.removedFoods, 91);
      expect(count.canBuildAPlan, isTrue);
      expect(count.byDishRole['main'], 80);

      // Asked twice, looked up once: the dictionary cannot change between
      // two ticks of a checkbox, and the count is asked again on every one.
      await session.countCandidates(codes: {'hypertension'});
      expect(
        calls.where((c) => c.endsWith('/conditions')),
        hasLength(1),
        reason: 'the condition dictionary must be cached',
      );
    });

    /// An empty set means "nothing declared", not "whatever is on file".
    /// Getting this wrong shows a filtered number as the catalogue on the
    /// very first view of the screen.
    test('nothing ticked sends an empty list, and asks for no dictionary',
        () async {
      Map<String, dynamic>? posted;
      final calls = <String>[];
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/conditions')) return catalogue();
        if (path.endsWith('/candidates/count')) {
          posted = jsonDecode(request.body) as Map<String, dynamic>;
          return countBody(remaining: 318);
        }
        return _json(const {});
      }, calls: calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final count = await session.countCandidates(
        codes: {HealthProfile.noneCode},
      );

      expect(posted!['conditions'], isEmpty);
      expect(count.removedFoods, 0);
      expect(
        calls.where((c) => c.endsWith('/conditions')),
        isEmpty,
        reason: 'with nothing declared there is no code to look up',
      );
    });

    /// The same stance as saving the declarations: a code the server does not
    /// know stops the count. Dropping it would show a reassuring number built
    /// from an allergy the server never heard about.
    test('a code the dictionary does not know stops the count', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/conditions')) return catalogue();
        return countBody();
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      await expectLater(
        session.countCandidates(codes: {'allergy_pangolin'}),
        throwsA(isA<ApiFailure>().having(
          (f) => f.message,
          'message',
          contains('allergy_pangolin'),
        )),
      );
    });

    /// A healthy total is not enough. One required role with nothing left in
    /// it makes a day unbuildable, whatever the total says.
    test('an empty required role means no plan, however big the total',
        () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/conditions')) return catalogue();
        if (path.endsWith('/candidates/count')) {
          return countBody(
            remaining: 180,
            emptyRoles: ['side_protein'],
            notes: ['Không còn món mặn nào.'],
          );
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final count = await session.countCandidates(codes: {'hypertension'});

      expect(count.remainingFoods, 180);
      expect(count.canBuildAPlan, isFalse);
      expect(count.emptyRequiredRoles, ['side_protein']);
      expect(count.notes, isNotEmpty);
    });

    test('offline, the count comes from the Dart copy of the filter',
        () async {
      final session = AppSession();

      final all = await session.countCandidates(codes: const {});
      expect(all.totalFoods, greaterThan(0));
      expect(
        all.remainingFoods,
        all.totalFoods,
        reason: 'nothing declared removes nothing',
      );
      expect(all.removedFoods, 0);

      // A seafood allergy, which really does exclude dishes in the mock
      // deck: seven of the thirty carry the `Có hải sản` tag.
      final allergic = await session.countCandidates(
        codes: {'allergy_seafood'},
      );
      expect(
        allergic.remainingFoods,
        lessThan(all.totalFoods),
        reason: 'the mock deck has dishes a seafood allergy excludes',
      );
      expect(allergic.byDishRole, isNotEmpty);
      expect(session.isOnline, isFalse);

      // The `require_tag` direction, which the offline copy had no mechanism
      // for at all until this branch: a vegan diet keeps only the dishes
      // CARRYING `Món thuần chay` instead of dropping the ones that carry
      // something. It used to exclude nothing, so a vegetarian offline got a
      // plan with meat in it.
      final vegan = await session.countCandidates(codes: {'vegan'});
      expect(
        vegan.remainingFoods,
        lessThan(all.totalFoods),
        reason: 'a vegan diet has to remove the dishes that are not vegan',
      );
      expect(
        vegan.remainingFoods,
        greaterThan(0),
        reason: 'and it must not remove everything, or no day can be built',
      );
      // The role a day cannot be assembled without, and the reason two
      // dishes were added to the mock deck: none of the original thirty was
      // a vegetarian MAIN course.
      expect(
        vegan.byDishRole['Món chính'] ?? 0,
        greaterThan(0),
        reason: 'a vegetarian needs a main course, or MEAL_STRUCTURE cannot '
            'fill breakfast, lunch or dinner',
      );
      expect(vegan.emptyRequiredRoles, isEmpty);
    });
  });

  group('§7.6 the meal plan, as the server builds it', () {
    Map<String, Object?> item(String id, String foodId, String name, {
      int kcal = 420,
      int grams = 300,
      String role = 'main',
      String status = 'suggested',
      double? delta,
    }) => {
      'id': id,
      'food': {
        'id': foodId,
        'name': name,
        'imageUrl': null,
        'categoryName': 'Món nước',
        'dishRole': role,
        'caloriesKcal': kcal,
      },
      'servingSizeG': grams,
      'predictedScore': 0.72,
      'status': status,
      'replacedByFood': null,
      'explorationDelta': delta,
      'position': 1,
    };

    Map<String, Object?> planBody({Map<String, Object?>? actuals}) => {
      'id': 'p1',
      'planDate': '2026-11-25',
      'status': 'active',
      'generationSource': 'hybrid',
      'modelVersion': 'gb-v1-1',
      'targets': {
        'caloriesKcal': 2542,
        'proteinG': 128,
        'carbsG': 352,
        'fatG': 71,
      },
      'actuals': actuals,
      'calorieDeviationPct': -1.2,
      'withinTolerance': true,
      'totalPreferenceScore': 2.9,
      'explorationRatio': 0.3,
      'meals': [
        {
          'mealType': 'breakfast',
          'targetCaloriesKcal': 699,
          'actualCaloriesKcal': 420,
          'items': [item('i1', 'f1', 'Phở bò')],
        },
        {
          'mealType': 'lunch',
          'targetCaloriesKcal': 953,
          'actualCaloriesKcal': 930,
          'items': [
            item('i2', 'f2', 'Cơm tấm', kcal: 560),
            item('i3', 'f3', 'Canh chua', kcal: 370, role: 'soup',
                delta: 0.35),
          ],
        },
        {
          'mealType': 'dinner',
          'targetCaloriesKcal': 699,
          'actualCaloriesKcal': 690,
          'items': [item('i4', 'f4', 'Cá kho', kcal: 690, role: 'side_protein')],
        },
        {
          'mealType': 'snack',
          'targetCaloriesKcal': 191,
          'actualCaloriesKcal': 190,
          'items': [item('i5', 'f5', 'Chè đậu xanh', kcal: 190, role: 'snack')],
        },
      ],
      'nutrientViolations': <dynamic>[],
      'generatedAt': '2026-11-25T06:30:00+07:00',
    };

    AppSession signedIn(
      List<String>? calls, {
      Future<http.Response> Function(http.Request)? plan,
    }) => _online((request) async {
      final path = request.url.path;
      if (path.endsWith('/auth/login')) return _json(_tokens);
      if (path.endsWith('/auth/me')) {
        return _json({..._user, 'hasHealthProfile': false});
      }
      if (path.endsWith('/foods')) return _foodsPage();
      if (path.endsWith('/meal-plans')) {
        return plan == null ? _json(planBody()) : plan(request);
      }
      return _json(const {});
    }, calls: calls);

    test('the day comes back whole, with each serving addressable', () async {
      final calls = <String>[];
      final session = signedIn(calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final loaded = await session.loadPlan(date: DateTime(2026, 11, 25));

      expect(loaded, isNotNull);
      expect(loaded!.id, 'p1');
      expect(loaded.slots.map((s) => s.type), MealType.values);
      expect(loaded.allItems, hasLength(5));
      // The serving's id, which §7.6.4 to §7.6.6 all act on. Without it the
      // screen could show a plan and change nothing in it.
      expect(loaded.allItems.map((i) => i.id), [
        'i1', 'i2', 'i3', 'i4', 'i5',
      ]);
      expect(loaded.targetKcal, 2542);
      expect(loaded.allItems.first.food.name, 'Phở bò');
      // The grams on the plate belong to the SERVING, not to the food:
      // `portion_multiplier` can make them differ from one standard serving.
      expect(loaded.allItems.first.food.servingSizeG, 300);
      // `exploration_delta IS NOT NULL` is the question, by design — there is
      // no separate flag.
      expect(loaded.allItems[2].isExploration, isTrue);
      expect(loaded.allItems.first.isExploration, isFalse);
    });

    /// Every serving arrives without its whole dish, and the things that
    /// need one have to say so rather than answer 0.
    test('a server plan carries no nutrition, and does not pretend to',
        () async {
      final session = signedIn(null);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      expect(plan.allItems.every((i) => i.dish == null), isTrue);
      expect(plan.totalOf('sodium_mg'), isNull);
      expect(plan.slots.first.protein, isNull);
      // Empty, and that is NOT "the plan is clear": this side has nothing to
      // judge by, so it says nothing. §7.6's own verdict travels with the
      // plan instead.
      expect(plan.nutrientViolations, isEmpty);
      // And the energy, which every serving DOES carry, still adds up.
      expect(plan.actualKcal, 420 + 560 + 370 + 690 + 190);
    });

    test("the day's macros come from the server when it sent them", () async {
      final session = signedIn(null, plan: (_) async => _json(planBody(
        actuals: {
          'caloriesKcal': 2230,
          'proteinG': 119.5,
          'carbsG': 300.0,
          'fatG': 66.0,
        },
      )));
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      expect(plan.actualProtein, 119.5);
      expect(plan.actualCarb, 300.0);
      expect(plan.actualFat, 66.0);
    });

    /// `null` actuals is a real state: §7.6's schema has no `DEFAULT 0` for
    /// them, because a stored 0 would make the deviation read −100 % the
    /// moment the row appeared.
    test('and are unknown, not zero, when it did not', () async {
      final session = signedIn(null);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      expect(plan.serverActuals, isNull);
      expect(plan.actualProtein, isNull);
      expect(plan.actualFat, isNull);
    });

    test('the plan is asked for once, not once per rebuild', () async {
      final calls = <String>[];
      final session = signedIn(calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      await session.loadPlan(date: DateTime(2026, 11, 25));
      await session.loadPlan(date: DateTime(2026, 11, 25));
      await session.loadPlan(date: DateTime(2026, 11, 25));

      expect(
        calls.where((c) => c.endsWith('/meal-plans')),
        hasLength(1),
        reason: 'the week strip rebuilds often; §7.6.1 is not a per-frame call',
      );
    });

    test('regenerating posts regenerate: true', () async {
      Map<String, dynamic>? posted;
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/meal-plans')) {
          if (request.method == 'POST') {
            posted = jsonDecode(request.body) as Map<String, dynamic>;
          }
          return _json(planBody());
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      expect(await session.regeneratePlan(date: DateTime(2026, 11, 25)), isTrue);

      expect(posted!['regenerate'], isTrue);
      // A plain date in the LOCAL calendar. An ISO timestamp converted to UTC
      // would move the date for anyone east of Greenwich, and Vietnam is
      // +07:00 — a late-evening request would ask for tomorrow.
      expect(posted!['planDate'], '2026-11-25');
    });

    /// A day with no plan and `autoGenerate: false` is a 404 that means
    /// "nothing here yet", not a failure. The week strip asks that way about
    /// days ahead: looking at next Friday must not commit a plan for it.
    test('looking ahead without generating gives null, not an error',
        () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/meal-plans')) {
          return _envelope(404, 'NOT_FOUND', 'Chưa có thực đơn cho ngày này');
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      // Through the session's own loader, which asks with autoGenerate ON,
      // the same 404 IS a failure: the server did not do what it says it
      // does, and swallowing it would leave an empty screen with no reason.
      await expectLater(
        session.loadPlan(date: DateTime(2026, 11, 27)),
        throwsA(isA<ApiFailure>()
            .having((f) => f.code, 'code', ApiFailure.notFound)),
      );
    });

    test('offline, the plan is still built on the spot', () async {
      final session = AppSession();
      _filled(session.profile);

      final built = await session.loadPlan();

      expect(built, isNotNull);
      expect(built!.id, isNull, reason: 'an offline plan is stored nowhere');
      expect(built.allItems.every((i) => i.dish != null), isTrue);
      expect(built.allItems.every((i) => i.id == null), isTrue);
      // And the figures this side computes are all there, which is the whole
      // point of keeping the offline mode.
      expect(built.actualProtein, isNotNull);
      expect(built.totalOf('sodium_mg'), isNotNull);
    });
  });

  group('§7.6.4–7.6.6 acting on one serving', () {
    Map<String, Object?> onePlanBody({String status = 'suggested'}) => {
      'id': 'p1',
      'planDate': '2026-11-25',
      'status': 'active',
      'generationSource': 'hybrid',
      'targets': {
        'caloriesKcal': 2542,
        'proteinG': 128,
        'carbsG': 352,
        'fatG': 71,
      },
      'actuals': null,
      'explorationRatio': 0.3,
      'meals': [
        for (final meal in ['breakfast', 'lunch', 'dinner', 'snack'])
          {
            'mealType': meal,
            'targetCaloriesKcal': 699,
            'actualCaloriesKcal': 420,
            'items': meal == 'breakfast'
                ? [
                    {
                      'id': 'i1',
                      'food': {
                        'id': 'f1',
                        'name': 'Phở bò',
                        'imageUrl': null,
                        'categoryName': 'Món nước',
                        'dishRole': 'main',
                        'caloriesKcal': 420,
                      },
                      'servingSizeG': 300,
                      'predictedScore': 0.72,
                      'status': status,
                      'replacedByFood': null,
                      'explorationDelta': null,
                      'position': 1,
                    },
                  ]
                : <dynamic>[],
          },
      ],
      'nutrientViolations': <dynamic>[],
      'generatedAt': '2026-11-25T06:30:00+07:00',
    };

    AppSession signedIn(
      Future<http.Response> Function(http.Request) items, {
      List<String>? calls,
    }) => _online((request) async {
      final path = request.url.path;
      if (path.endsWith('/auth/login')) return _json(_tokens);
      if (path.endsWith('/auth/me')) {
        return _json({..._user, 'hasHealthProfile': false});
      }
      if (path.endsWith('/foods')) return _foodsPage();
      if (path.endsWith('/meal-plans')) return _json(onePlanBody());
      if (path.contains('/meal-plan-items/')) return items(request);
      return _json(const {});
    }, calls: calls);

    /// §7.6.6 writes the diary entry in the SAME request, which is why
    /// `markEaten` must not also write one of its own: two would count the
    /// meal twice in every compliance figure the report quotes.
    test('marking a serving eaten sends one request and returns the entry',
        () async {
      final calls = <String>[];
      Map<String, dynamic>? patched;
      final session = signedIn((request) async {
        patched = jsonDecode(request.body) as Map<String, dynamic>;
        return _json({
          'id': 'i1',
          'status': 'eaten',
          'diaryEntryCreated': true,
          'diaryEntryId': 'd9',
        });
      }, calls: calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;
      final item = plan.allItems.single;

      final entryId = await session.markEaten(item, MealType.breakfast);

      expect(patched, {'status': 'eaten'});
      expect(entryId, 'd9');
      expect(
        session.plan!.allItems.single.status,
        MealItemStatus.eaten,
        reason: 'the cached serving follows what the server stored',
      );
      // No second write of its own.
      expect(session.diary, isEmpty);
      expect(
        calls.where((c) => c.contains('/meal-plan-items/')),
        hasLength(1),
      );
    });

    /// A repeat answers `diaryEntryCreated: false`, and that is not a
    /// failure: the entry already exists. A screen that read it as one would
    /// tell the user their meal was not recorded.
    test('a repeat is not a failure, and creates no second entry', () async {
      final session = signedIn((_) async => _json({
        'id': 'i1',
        'status': 'eaten',
        'diaryEntryCreated': false,
        'diaryEntryId': 'd9',
      }));
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      final entryId = await session.markEaten(
        plan.allItems.single,
        MealType.breakfast,
      );

      expect(entryId, isNull);
      expect(session.plan!.allItems.single.status, MealItemStatus.eaten);
    });

    /// Putting a skipped serving back sends `kept`, not `suggested`: §7.6.6
    /// accepts only the three a client may set, and §4.6 reads `kept` as the
    /// user having looked at a suggestion and left it.
    test('skipping sends skipped, and putting it back sends kept', () async {
      final sent = <String>[];
      final session = signedIn((request) async {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        sent.add(body['status'] as String);
        return _json({
          'id': 'i1',
          'status': body['status'],
          'diaryEntryCreated': false,
          'diaryEntryId': null,
        });
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      await session.setSkipped(plan.allItems.single, true);
      expect(session.plan!.allItems.single.status, MealItemStatus.skipped);
      await session.setSkipped(session.plan!.allItems.single, false);
      expect(session.plan!.allItems.single.status, MealItemStatus.kept);

      expect(sent, ['skipped', 'kept']);
    });

    /// A refusal must leave the cached serving alone. A status applied
    /// locally and refused by the server would have the screen showing a
    /// serving as eaten while the diary has no record of it.
    test('a refused status change does not move the serving', () async {
      final session = signedIn((_) async => _envelope(
        409, 'VALIDATION_FAILED', 'Dòng nhật ký đã bị khóa',
      ));
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      await expectLater(
        session.markEaten(plan.allItems.single, MealType.breakfast),
        throwsA(isA<ApiFailure>()),
      );
      expect(session.plan!.allItems.single.status, MealItemStatus.suggested);
    });

    /// §7.6.4 answers with figures this side cannot compute — the energy the
    /// swap would move, at the portions that would be served, and whether
    /// the day stays inside ±10 %.
    test('the alternatives carry the day-level figures', () async {
      final session = signedIn((request) async {
        if (!request.url.path.endsWith('/alternatives')) {
          return _json(const {});
        }
        return _json({
          'originalItem': {
            'id': 'i1',
            'foodName': 'Phở bò',
            'caloriesKcal': 420,
            'dishRole': 'main',
          },
          'alternatives': [
            {
              'food': {
                'id': 'f9',
                'name': 'Bún chả',
                'imageUrl': null,
                'categoryName': 'Món nước',
                'dishRole': 'main',
                'caloriesKcal': 520,
              },
              'servingSizeG': 320,
              'predictedScore': 0.81,
              'calorieDeltaKcal': 100,
              'keepsWithinTolerance': false,
            },
          ],
        });
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      final options = await session.replaceOptions(plan.allItems.single);

      expect(options, hasLength(1));
      expect(options.single.food.name, 'Bún chả');
      expect(options.single.score, 0.81);
      expect(options.single.deltaKcal, 100);
      // Shown and not acted on: the dish stays selectable, because a user
      // may prefer one that costs them some accuracy.
      expect(options.single.keepsWithinTolerance, isFalse);
      // No whole dish, so the local allowance check cannot run and must not
      // pretend to.
      expect(options.single.dish, isNull);
    });

    /// §7.6.5 answers with the WHOLE day, because the swap moves the day's
    /// totals and its ±10 % verdict.
    test('replacing a serving replaces the cached day', () async {
      Map<String, dynamic>? put;
      final session = signedIn((request) async {
        if (request.method != 'PUT') return _json(const {});
        put = jsonDecode(request.body) as Map<String, dynamic>;
        return _json(onePlanBody(status: 'kept'));
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      final plan = (await session.loadPlan(date: DateTime(2026, 11, 25)))!;

      await session.replaceItem(
        plan.allItems.single,
        const FoodBrief(
          id: 'f9',
          name: 'Bún chả',
          category: 'Món nước',
          dishRole: 'main',
          spiceLevel: 0,
          kcal: 520,
          servingSizeG: 320,
        ),
      );

      expect(put!['newFoodId'], 'f9');
      // The day that came back, not a locally patched one.
      expect(session.plan!.allItems.single.status, MealItemStatus.kept);
    });

    test('offline, all four still work on the plan in memory', () async {
      final session = AppSession();
      _filled(session.profile);
      await session.loadPlan();
      final item = session.plan!.allItems.first;

      await session.markEaten(item, item.food.dishRole == 'Món phụ'
          ? MealType.snack
          : MealType.breakfast);
      expect(session.diary, hasLength(1),
          reason: 'offline the local diary IS the store');

      final other = session.plan!.allItems.last;
      await session.setSkipped(other, true);
      expect(
        session.plan!.allItems.last.status,
        MealItemStatus.skipped,
      );

      final options = await session.replaceOptions(session.plan!.allItems[1]);
      expect(options, isNotEmpty);
      // The whole dish, which is what the local allowance check needs.
      expect(options.first.dish, isNotNull);
      // And no day-level figures, because nothing on this side computed any.
      expect(options.first.deltaKcal, isNull);
      expect(options.first.keepsWithinTolerance, isNull);
    });
  });

  group('§7.8 the rating, and the diary line it locks', () {
    Map<String, Object?> line({
      String id = 'd1',
      bool hasFeedback = false,
      bool editable = true,
    }) => {
      'id': id,
      'food': {
        'id': 'f1',
        'name': 'Phở bò',
        'imageUrl': null,
        'categoryName': 'Món nước',
        'dishRole': 'main',
        'caloriesKcal': 420,
      },
      'mealType': 'breakfast',
      'servingSizeG': 300,
      'actualCaloriesKcal': 420,
      'fromMealPlan': true,
      'hasFeedback': hasFeedback,
      'editable': editable,
      'createdAt': '2026-11-25T07:10:00+07:00',
    };

    Map<String, Object?> diaryBody({bool locked = false}) => {
      'from': '2026-10-27',
      'to': '2026-11-25',
      'days': [
        {
          'date': '2026-11-25',
          'totalCaloriesKcal': 420,
          'entries': [line(hasFeedback: locked, editable: !locked)],
        },
      ],
    };

    /// The rule the whole group exists for: a rating locks the line, and the
    /// flag that says so lives on the SERVER's side of it. So the session
    /// reads the line back instead of flipping a local boolean — a second
    /// implementation of the lock is a second thing that can disagree.
    test('rating a dish reads the line back, now locked', () async {
      final calls = <String>[];
      Map<String, dynamic>? posted;
      var rated = false;
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/food-diary')) return _json(diaryBody(locked: rated));
        if (path.endsWith('/food-diary/summary')) {
          return _envelope(404, 'NOT_FOUND', 'Chưa có dữ liệu');
        }
        if (path.endsWith('/feedbacks')) {
          posted = jsonDecode(request.body) as Map<String, dynamic>;
          rated = true;
          return _json({
            'id': 'fb1',
            'foodId': 'f1',
            'foodName': 'Phở bò',
            'rating': 5,
            'comment': null,
            'createdAt': '2026-11-25T08:00:00+07:00',
            'profileUpdated': true,
          });
        }
        return _json(const {});
      }, calls: calls);
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      await session.loadDiary();

      final before = session.diary.single;
      expect(before.editable, isTrue);
      expect(before.hasRating, isFalse);

      await session.rate(before, 5);

      expect(posted, {'foodId': 'f1', 'rating': 5});
      final after = session.diary.single;
      expect(
        after.editable,
        isFalse,
        reason: 'the lock comes from the server, read back and not invented',
      );
      expect(after.hasRating, isTrue);
      // The stars themselves are §7.5.2's `myFeedback`; §7.7.1 only says
      // THAT it was rated, so no number is shown as if it were known.
      expect(after.stars, isNull);
    });

    /// `profileUpdated: false` means the ML service did not answer, not that
    /// the rating was lost: it is stored either way and §7.8.1 answers 201
    /// either way. Treating it as a failure would tell the user their rating
    /// did not count.
    test('a rating the ML service did not consume is still a rating',
        () async {
      var rated = false;
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/food-diary')) return _json(diaryBody(locked: rated));
        if (path.endsWith('/food-diary/summary')) {
          return _envelope(404, 'NOT_FOUND', 'Chưa có dữ liệu');
        }
        if (path.endsWith('/feedbacks')) {
          rated = true;
          return _json({
            'id': 'fb1',
            'foodId': 'f1',
            'foodName': 'Phở bò',
            'rating': 3,
            'comment': null,
            'createdAt': '2026-11-25T08:00:00+07:00',
            'profileUpdated': false,
          });
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      await session.loadDiary();

      await session.rate(session.diary.single, 3);

      expect(session.diary.single.editable, isFalse);
    });

    /// §7.8.1's two-part rule. The screen should not reach it, but a stale
    /// line can: the dish was logged, the plan it came from was regenerated
    /// away, and the first half no longer holds.
    test('a refused rating leaves the line editable', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/food-diary')) return _json(diaryBody());
        if (path.endsWith('/food-diary/summary')) {
          return _envelope(404, 'NOT_FOUND', 'Chưa có dữ liệu');
        }
        if (path.endsWith('/feedbacks')) {
          return _envelope(
            409,
            'FEEDBACK_NOT_ALLOWED',
            'Món này chưa từng có trong thực đơn của bạn',
          );
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');
      await session.loadDiary();

      await expectLater(
        session.rate(session.diary.single, 4),
        throwsA(isA<ApiFailure>()),
      );
      expect(session.diary.single.editable, isTrue);
    });

    test('offline, the stars go on the line and nothing is locked', () async {
      final session = AppSession();
      _filled(session.profile);
      await session.loadPlan();
      final item = session.plan!.allItems.first;
      await session.markEaten(item, MealType.breakfast);
      final entry = session.diary.single;

      await session.rate(entry, 4);

      expect(entry.stars, 4);
      expect(
        entry.editable,
        isTrue,
        reason: 'the lock is a server rule; offline there is no §7.7.3 to '
            'refuse anything',
      );
    });
  });

  group('§7.7.5 the day as the server measured it', () {
    test('the summary wins over what this side could add up', () async {
      final session = _online((request) async {
        final path = request.url.path;
        if (path.endsWith('/auth/login')) return _json(_tokens);
        if (path.endsWith('/auth/me')) {
          return _json({..._user, 'hasHealthProfile': false});
        }
        if (path.endsWith('/foods')) return _foodsPage();
        if (path.endsWith('/food-diary/summary')) {
          return _json({
            'date': '2026-11-25',
            'targets': {
              'caloriesKcal': 2542,
              'proteinG': 128,
              'carbsG': 352,
              'fatG': 71,
            },
            'consumed': {
              'caloriesKcal': 2700,
              'proteinG': 130,
              'carbsG': 360,
              'fatG': 80,
            },
            // Negative, and sent that way: clamping would hide exactly what
            // the card exists to show.
            'remaining': {
              'caloriesKcal': -158,
              'proteinG': -2,
              'carbsG': -8,
              'fatG': -9,
            },
            'progressPct': {
              'calories': 106.2,
              'protein': 101.6,
              'carbs': 102.3,
              'fat': 112.7,
            },
            'byMeal': [
              {
                'mealType': 'breakfast',
                'caloriesKcal': 700,
                'targetCaloriesKcal': 699,
              },
            ],
            'micronutrients': [
              {
                'nutrient': 'calcium_mg',
                'nameVi': 'Canxi',
                'consumed': 450,
                'rda': 1000,
                'pct': 45,
                'unit': 'mg',
              },
            ],
            'planCompliance': {
              'plannedDishes': 5,
              'eatenFromPlan': 4,
              'compliancePct': 80,
            },
          });
        }
        return _json(const {});
      });
      await session.logIn(email: 'a@b.vn', password: 'MatKhau123');

      final summary = (await session.daySummary(date: DateTime(2026, 11, 25)))!;

      expect(summary.targets.caloriesKcal, 2542);
      expect(summary.consumed.caloriesKcal, 2700);
      expect(
        summary.remaining.caloriesKcal,
        -158,
        reason: 'over the target is the case this figure is for',
      );
      expect(summary.byMeal.single.mealType, 'breakfast');
      // A lower bound: dishes with no figure for the nutrient were skipped,
      // not counted as zero.
      expect(summary.micronutrients.single.pct, 45);
      expect(summary.planCompliance?.compliancePct, 80);
    });

    test('offline there is no such answer, and none is invented', () async {
      final session = AppSession();
      _filled(session.profile);

      expect(await session.daySummary(), isNull);
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

      final dish = MockFoods.surveyDeck.first.brief;
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
      final dish = MockFoods.surveyDeck.first.brief;
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

      final dish = MockFoods.surveyDeck.first.brief;
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
      final dish = MockFoods.surveyDeck.first.brief;

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
