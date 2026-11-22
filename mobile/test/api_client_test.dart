// ONLINE: the transport layer and the §7.1–§7.3 payloads.

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/auth_api.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/api/profile_api.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';

/// A JSON response with the UTF-8 header the backend sends.
http.Response json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

/// The §2.5 envelope.
http.Response envelope(
  int status,
  String code,
  String message, {
  List<Map<String, String>>? details,
}) => json({
  'error': {
    'code': code,
    'message': message,
    'traceId': '0HN7GKLM9QRST:00000073',
    'details': ?details,
  },
}, status);

ApiClient clientFor(
  Future<http.Response> Function(http.Request) handler, {
  void Function()? onSignedOut,
  Duration? timeout,
}) => ApiClient(
  baseUrl: 'http://localhost:5055/api/v1',
  httpClient: MockClient(handler),
  timeout: timeout,
  onSignedOut: onSignedOut,
);

void main() {
  group('the error envelope becomes something to branch on', () {
    test('code, message, traceId and the per-field details all survive',
        () async {
      final client = clientFor(
        (_) async => envelope(
          400,
          'VALIDATION_FAILED',
          'Dữ liệu gửi lên không hợp lệ',
          details: [
            {'field': 'heightCm', 'message': 'Chiều cao phải từ 50 đến 250 cm'},
          ],
        ),
      );

      final failure = await client
          .get('/profile')
          .then<ApiFailure?>((_) => null)
          .catchError((Object e) => e as ApiFailure);

      expect(failure!.code, ApiFailure.validationFailed);
      expect(failure.status, 400);
      expect(failure.message, 'Dữ liệu gửi lên không hợp lệ');
      expect(failure.traceId, isNotNull);
      expect(failure.forField('heightCm'), contains('50 đến 250'));
      expect(failure.forField('weightKg'), isNull);
    });

    /// The app must read `code`, never the prose. This is the test that says
    /// so: the Vietnamese sentence is free to change and nothing branches on
    /// it.
    test('every failure carries a message fit to show the user', () async {
      final cases = <ApiFailure>[
        ApiFailure.timedOut(),
        ApiFailure.unreachable(Exception('no route')),
        ApiFailure.fromEnvelope(409, {
          'error': {'code': 'PROFILE_REQUIRED', 'message': 'Chưa khai báo'},
        }),
        ApiFailure.fromEnvelope(500, {'oops': true}),
      ];

      for (final f in cases) {
        expect(f.code, isNotEmpty, reason: 'a failure with no code');
        expect(f.message, isNotEmpty, reason: '${f.code} has nothing to say');
      }
    });

    test('a JSON body that is not the envelope is reported as such', () async {
      final client = clientFor((_) async => json({'detail': 'nope'}, 500));

      await expectLater(
        client.get('/profile'),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.unexpectedShape,
          ),
        ),
      );
    });

    test('an HTML error page from a proxy keeps its status', () async {
      final client = clientFor(
        (_) async => http.Response('<html>502</html>', 502),
      );

      await expectLater(
        client.get('/profile'),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.code, 'code', ApiFailure.unexpectedShape)
              .having((f) => f.status, 'status', 502),
        ),
      );
    });

    test('no answer at all is one thing from the user side', () async {
      final client = clientFor(
        (_) async => throw http.ClientException('connection refused'),
      );

      await expectLater(
        client.get('/profile'),
        throwsA(
          isA<ApiFailure>()
              .having((f) => f.code, 'code', ApiFailure.unreachable_)
              .having((f) => f.isRetryable, 'isRetryable', true),
        ),
      );
    });

    test('a request that never finishes is a timeout, not a hang', () async {
      final client = clientFor(
        (_) => Completer<http.Response>().future, // never completes
        timeout: const Duration(milliseconds: 50),
      );

      await expectLater(
        client.get('/profile'),
        throwsA(
          isA<ApiFailure>().having((f) => f.code, 'code', ApiFailure.timeout),
        ),
      );
    });

    test('204 No Content is a success, not an unreadable answer', () async {
      final client = clientFor((_) async => http.Response('', 204));

      expect(await client.delete('/food-diary/abc'), isEmpty);
    });

    test('only the failures worth retrying say so', () {
      expect(ApiFailure.timedOut().isRetryable, isTrue);
      expect(ApiFailure.unreachable().isRetryable, isTrue);
      expect(
        const ApiFailure(
          code: ApiFailure.invalidCredentials,
          message: 'Sai mật khẩu',
        ).isRetryable,
        isFalse,
      );
    });
  });

  group('the token', () {
    test('rides on an authenticated request and not on an open one', () async {
      final seen = <String, String?>{};
      final client = clientFor((request) async {
        seen[request.url.path] = request.headers['Authorization'];
        return json(const {});
      });
      client.setTokens(accessToken: 'ACCESS', refreshToken: 'REFRESH');

      await client.get('/profile');
      await client.get('/conditions', authenticated: false);

      expect(seen['/api/v1/profile'], 'Bearer ACCESS');
      expect(seen['/api/v1/conditions'], isNull);
    });

    /// §7.1.3. The access token expiring in the middle of a session is a
    /// thing that happens every hour, and the user should never see it.
    test('an expired access token is refreshed and the call replayed',
        () async {
      final calls = <String>[];
      var refreshed = false;
      final client = clientFor((request) async {
        calls.add('${request.method} ${request.url.path}');
        if (request.url.path.endsWith('/auth/refresh')) {
          refreshed = true;
          return json({
            'accessToken': 'ACCESS2',
            'refreshToken': 'REFRESH2',
          });
        }
        if (!refreshed) {
          return envelope(401, 'TOKEN_EXPIRED', 'Token đã hết hạn');
        }
        expect(request.headers['Authorization'], 'Bearer ACCESS2');
        return json({'gender': 'male'});
      });
      client.setTokens(accessToken: 'ACCESS1', refreshToken: 'REFRESH1');

      final body = await client.get('/profile');

      expect(body['gender'], 'male');
      expect(calls, [
        'GET /api/v1/profile',
        'POST /api/v1/auth/refresh',
        'GET /api/v1/profile',
      ]);
    });

    /// §7.1.3 rotates the refresh token and treats a reused one as theft, so
    /// keeping the old one would invalidate the whole chain on the next
    /// refresh.
    test('the rotated refresh token replaces the old one', () async {
      final sent = <String?>[];
      var refreshes = 0;
      // Whether the access token the client currently holds has expired.
      // A refresh clears it; the test sets it again to stand for the next
      // hour passing.
      var expired = true;
      final client = clientFor((request) async {
        if (request.url.path.endsWith('/auth/refresh')) {
          refreshes++;
          sent.add(
            (jsonDecode(request.body) as Map)['refreshToken'] as String?,
          );
          expired = false;
          return json({
            'accessToken': 'ACCESS$refreshes',
            'refreshToken': 'REFRESH$refreshes',
          });
        }
        if (expired) {
          return envelope(401, 'TOKEN_EXPIRED', 'Token đã hết hạn');
        }
        expect(request.headers['Authorization'], 'Bearer ACCESS$refreshes');
        return json(const {});
      });
      client.setTokens(accessToken: 'OLD', refreshToken: 'REFRESH0');

      await client.get('/profile');
      expired = true; // an hour later
      await client.get('/profile');

      // The second refresh sent the token the first one handed back, not the
      // original. §7.1.3 invalidates the chain if a refresh token is reused.
      expect(sent, ['REFRESH0', 'REFRESH1']);
      expect(refreshes, 2);
    });

    test('a refresh that is refused ends the session once and reports the '
        'original failure', () async {
      var signedOut = 0;
      final calls = <String>[];
      final client = clientFor(
        (request) async {
          calls.add(request.url.path);
          return envelope(401, 'TOKEN_EXPIRED', 'Token đã hết hạn');
        },
        onSignedOut: () => signedOut++,
      );
      client.setTokens(accessToken: 'ACCESS', refreshToken: 'REFRESH');

      await expectLater(
        client.get('/profile'),
        throwsA(
          isA<ApiFailure>().having((f) => f.code, 'code', 'TOKEN_EXPIRED'),
        ),
      );

      // Exactly two: the call, then the one refresh. A server that answers
      // 401 to everything, refresh included, must not become a loop.
      expect(calls, ['/api/v1/profile', '/api/v1/auth/refresh']);
      expect(signedOut, 1);
      expect(client.hasSession, isFalse);
    });

    test('with no refresh token there is nothing to try', () async {
      final calls = <String>[];
      final client = clientFor((request) async {
        calls.add(request.url.path);
        return envelope(401, 'TOKEN_EXPIRED', 'Token đã hết hạn');
      });
      client.setTokens(accessToken: 'ACCESS', refreshToken: 'REFRESH');
      client.clearTokens();

      await expectLater(client.get('/profile'), throwsA(isA<ApiFailure>()));
      expect(calls, ['/api/v1/profile']);
    });
  });

  group('the address', () {
    test('a trailing slash does not double up', () {
      final client = ApiClient(
        baseUrl: 'http://localhost:5055/api/v1/',
        httpClient: MockClient((_) async => json(const {})),
      );

      expect(client.baseUrl, 'http://localhost:5055/api/v1');
    });

    test('a null query parameter is left out rather than sent empty',
        () async {
      Uri? seen;
      final client = clientFor((request) async {
        seen = request.url;
        return json(const []);
      });

      await client.getList(
        '/conditions',
        query: {'type': null, 'other': 'allergy'},
      );

      expect(seen!.queryParameters.containsKey('type'), isFalse);
      expect(seen!.queryParameters['other'], 'allergy');
    });

    test('an object where an array was expected is reported', () async {
      final client = clientFor((_) async => json(const {'a': 1}));

      await expectLater(
        client.getList('/conditions'),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.unexpectedShape,
          ),
        ),
      );
    });
  });

  group('§7.1 the account', () {
    /// The example from the specification, verbatim.
    final registered = {
      'accessToken': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',
      'refreshToken': 'd4f8b1c2-9e7a-4c3d-8b5f-1a2e3d4c5b6a',
      'tokenType': 'Bearer',
      'expiresIn': 3600,
      'user': {
        'id': '00000001-0000-4000-8000-000000000000',
        'email': 'nghia@example.com',
        'displayName': 'Trần Lâm Nghĩa',
        'avatarUrl': null,
        'onboardingCompletedAt': null,
        'createdAt': '2026-11-20T07:15:30Z',
      },
    };

    test('registering keeps the pair of tokens for the next request',
        () async {
      String? authorization;
      final client = clientFor((request) async {
        if (request.url.path.endsWith('/auth/register')) {
          return json(registered, 201);
        }
        authorization = request.headers['Authorization'];
        return json(registered['user']!);
      });
      final auth = AuthApi(client);

      final session = await auth.register(
        email: ' nghia@example.com ',
        password: 'MatKhau123',
        displayName: ' Trần Lâm Nghĩa ',
      );

      expect(session.account.email, 'nghia@example.com');
      expect(session.account.hasFinishedOnboarding, isFalse);
      expect(client.hasSession, isTrue);

      await auth.me();
      expect(authorization, 'Bearer ${session.accessToken}');
    });

    test('the email and the name are trimmed before they are sent', () async {
      Map<String, dynamic>? body;
      final client = clientFor((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return json(registered, 201);
      });

      await AuthApi(client).register(
        email: '  nghia@example.com  ',
        password: 'MatKhau123',
        displayName: '  Nghĩa  ',
      );

      expect(body!['email'], 'nghia@example.com');
      expect(body!['displayName'], 'Nghĩa');
      expect(body!['password'], 'MatKhau123', reason: 'never trimmed');
    });

    test('§7.1.4 answers the question the app asks: which screen to open',
        () async {
      final client = clientFor(
        (_) async => json({
          'id': '00000001-0000-4000-8000-000000000000',
          'email': 'nghia@example.com',
          'displayName': 'Trần Lâm Nghĩa',
          'avatarUrl': null,
          'onboardingCompletedAt': '2026-11-20T08:02:11Z',
          'hasHealthProfile': true,
          'preferenceStage': 'content',
          'createdAt': '2026-11-20T07:15:30Z',
        }),
      );

      final account = await AuthApi(client).me();

      expect(account.hasFinishedOnboarding, isTrue);
      expect(account.hasHealthProfile, isTrue);
      expect(account.preferenceStage, 'content');
    });

    test('signing out drops the tokens', () async {
      final client = clientFor((_) async => json(const {}));
      client.setTokens(accessToken: 'A', refreshToken: 'R');

      AuthApi(client).logOut();

      expect(client.hasSession, isFalse);
    });
  });

  group('§7.2.3 the server targets win over the local arithmetic', () {
    /// The example from the specification, verbatim — including the three
    /// percentages sitting INSIDE `macroTargets`, which is the shape it is
    /// easy to get wrong.
    final payload = {
      'bmi': 23.15,
      'bmiCategory': 'overweight',
      'bmrKcal': 1655,
      'tdeeKcal': 2565,
      'activityFactor': 1.55,
      'dailyCaloriesTarget': 2565,
      'goalAdjustmentKcal': 0,
      'macroTargets': {
        'proteinPct': 15,
        'proteinG': 96.2,
        'carbsPct': 60,
        'carbsG': 384.8,
        'fatPct': 25,
        'fatG': 71.3,
      },
      'mealDistribution': [
        {'mealType': 'breakfast', 'pct': 27.5, 'caloriesKcal': 705},
        {'mealType': 'lunch', 'pct': 37.5, 'caloriesKcal': 962},
        {'mealType': 'dinner', 'pct': 27.5, 'caloriesKcal': 705},
        {'mealType': 'snack', 'pct': 7.5, 'caloriesKcal': 192},
      ],
    };

    test('the percentages are read out of macroTargets', () {
      final targets = ServerTargets.fromJson(payload);

      expect(targets.proteinPct, 15);
      expect(targets.carbsPct, 60);
      expect(targets.fatPct, 25);
      expect(targets.proteinG, closeTo(96.2, 0.01));
      expect(targets.caloriesKcal, 2565);
      expect(targets.bmrKcal, 1655);
    });

    test('the four meals come back keyed by meal_type', () {
      final targets = ServerTargets.fromJson(payload);

      expect(targets.mealShare.keys, containsAll(
        <String>['breakfast', 'lunch', 'dinner', 'snack'],
      ));
      expect(targets.mealShare['lunch'], 962);
    });

    /// The reason `proteinPct` and its two neighbours are writable: without
    /// this, the offline arithmetic keeps splitting the energy 15 / 60 / 25
    /// while the server has just said something else, and the two screens
    /// disagree with nothing to report it.
    test('they overwrite the local split', () {
      final profile = HealthProfile();
      expect(profile.proteinPct, 15);

      ServerTargets.fromJson({
        ...payload,
        'macroTargets': {
          'proteinPct': 20,
          'proteinG': 1,
          'carbsPct': 55,
          'carbsG': 1,
          'fatPct': 25,
          'fatG': 1,
        },
      }).applyTo(profile);

      expect(profile.proteinPct, 20);
      expect(profile.carbsPct, 55);
      expect(profile.fatPct, 25);
    });

    test('a split that does not add up to 100 is refused, not applied', () {
      final profile = HealthProfile();

      ServerTargets.fromJson({
        'macroTargets': {'proteinPct': 20, 'carbsPct': 20, 'fatPct': 20},
      }).applyTo(profile);

      expect(profile.proteinPct, 15, reason: 'the default is kept');
      expect(profile.carbsPct, 60);
      expect(profile.fatPct, 25);
    });
  });

  group('§7.2 the profile', () {
    test('the date of birth goes as a plain date, with no time or zone',
        () async {
      Map<String, dynamic>? body;
      final client = clientFor((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return json(const {
          'profile': {'gender': 'male'},
          'nutritionTargets': <String, dynamic>{},
        });
      });
      final profile = HealthProfile()
        ..gender = Gender.male
        ..birthday = DateTime(2004, 11, 4)
        ..heightCm = 172
        ..weightKg = 68.5
        ..activity = ActivityLevel.moderate
        ..goal = HealthGoal.maintain;

      await ProfileApi(client).save(profile);

      expect(body!['dateOfBirth'], '2004-11-04');
      expect(body!['gender'], 'male');
      expect(body!['activityLevel'], 'moderate');
      expect(body!['goal'], 'maintain');
    });

    /// The app used to ask for a target weight and then lose it: no column,
    /// no endpoint field, gone on restart. Migration 007 gave it a home, so
    /// now it goes with the rest.
    test('the target weight is sent, now that there is a column for it',
        () async {
      Map<String, dynamic>? body;
      final client = clientFor((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return json(const {
          'profile': {'gender': 'female'},
          'nutritionTargets': <String, dynamic>{},
        });
      });
      final profile = HealthProfile()
        ..gender = Gender.female
        ..birthday = DateTime(1999, 7, 2)
        ..heightCm = 160
        ..weightKg = 54
        ..targetWeightKg = 50
        ..activity = ActivityLevel.light
        ..goal = HealthGoal.loseWeight;

      await ProfileApi(client).save(profile);

      expect(body!['targetWeightKg'], 50);
      expect(body!.keys, hasLength(7));
    });

    /// A PUT replaces the whole profile, so leaving the field out is how the
    /// target gets cleared — which is what has to happen when the goal
    /// changes to one with nothing to aim at.
    test('and left out entirely when the goal has no target', () async {
      Map<String, dynamic>? body;
      final client = clientFor((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return json(const {
          'profile': {'gender': 'male'},
          'nutritionTargets': <String, dynamic>{},
        });
      });
      final profile = HealthProfile()
        ..gender = Gender.male
        ..birthday = DateTime(2004, 11, 4)
        ..heightCm = 172
        ..weightKg = 68.5
        ..activity = ActivityLevel.moderate
        ..goal = HealthGoal.maintain;

      await ProfileApi(client).save(profile);

      expect(body!.containsKey('targetWeightKg'), isFalse);
      expect(body!.keys, hasLength(6));
    });

    test('and it comes back on the profile the server sends', () {
      final profile = HealthProfile()..targetWeightKg = 99;

      ServerProfile.fromJson({
        'gender': 'female',
        'weightKg': 54.0,
        'targetWeightKg': 50.0,
      }).applyTo(profile);

      expect(profile.targetWeightKg, 50.0);
      expect(profile.weightDelta, -4.0);
    });

    /// The server clearing it has to reach the app, or a goal changed to
    /// `maintain` would leave a stale target on screen for ever.
    test('a server that cleared it clears it here too', () {
      final profile = HealthProfile()..targetWeightKg = 60;

      ServerProfile.fromJson({'gender': 'male', 'weightKg': 68.5}).applyTo(
        profile,
      );

      expect(profile.targetWeightKg, isNull);
    });

    test('an incomplete profile is not sent at all', () async {
      var called = false;
      final client = clientFor((_) async {
        called = true;
        return json(const {});
      });

      await expectLater(
        ProfileApi(client).save(HealthProfile()..gender = Gender.male),
        throwsA(isA<StateError>()),
      );
      expect(called, isFalse);
    });

    test('what the server sends back lands on the profile', () {
      final profile = HealthProfile()..targetWeightKg = 60;

      ServerProfile.fromJson({
        'gender': 'female',
        'dateOfBirth': '1999-07-02',
        'age': 27,
        'heightCm': 160.0,
        'weightKg': 54.0,
        'bmi': 21.09,
        'bmiCategory': 'normal',
        'activityLevel': 'light',
        'goal': 'lose_weight',
        'conditions': [
          {
            'conditionId': 6,
            'nameVi': 'Dị ứng hải sản',
            'conditionType': 'allergy',
            'severity': 'severe',
            'note': null,
          },
        ],
      }).applyTo(profile);

      expect(profile.gender, Gender.female);
      expect(profile.birthday, DateTime(1999, 7, 2));
      expect(profile.activity, ActivityLevel.light);
      expect(profile.goal, HealthGoal.loseWeight);
      // The payload above carries no target, and a PUT-shaped profile means
      // "no target" rather than "unchanged" — so the stale 60 goes.
      expect(profile.targetWeightKg, isNull);
    });

    /// `other` is in the database ENUM and has no screen. It must not be
    /// silently read as male or female.
    test('a gender the app has no screen for reads as unanswered', () {
      final profile = HealthProfile()..gender = Gender.male;

      ServerProfile.fromJson({'gender': 'other'}).applyTo(profile);

      expect(profile.gender, isNull);
    });

    /// `user_conditions.severity` is `NOT NULL DEFAULT 'moderate'` and
    /// §7.2.5 refuses a body that leaves it out. Sending nothing was the
    /// first guess here and the live server rejected it, so the client sends
    /// the column's own default — and the onboarding screen still owes the
    /// user the question.
    test('a condition with no severity falls back to the column default', () {
      const declared = DeclaredCondition(
        conditionId: 3,
        nameVi: 'Ăn chay',
        conditionType: 'diet',
      );

      expect(declared.toJson(), {'conditionId': 3, 'severity': 'moderate'});
      expect(DeclaredCondition.defaultSeverity, 'moderate');
    });

    test('a severity the user did choose is sent as it is', () {
      const declared = DeclaredCondition(
        conditionId: 6,
        nameVi: 'Dị ứng hải sản',
        conditionType: 'allergy',
        severity: 'severe',
        note: 'Tôm cua',
      );

      expect(declared.toJson(), {
        'conditionId': 6,
        'severity': 'severe',
        'note': 'Tôm cua',
      });
    });

    test('both halves of §7.2.4 and §7.2.5 answer with a bare array',
        () async {
      final rows = [
        {
          'conditionId': 2,
          'nameVi': 'Tăng huyết áp',
          'conditionType': 'disease',
          'severity': 'mild',
          'note': null,
        },
      ];
      Object? sentBody;
      final client = clientFor((request) async {
        if (request.method == 'PUT') {
          sentBody = jsonDecode(request.body);
        }
        return json(rows);
      });
      final api = ProfileApi(client);

      expect((await api.conditions()).single.conditionId, 2);

      final saved = await api.saveConditions(const [
        DeclaredCondition(
          conditionId: 2,
          nameVi: '',
          conditionType: '',
          severity: 'mild',
        ),
      ]);

      expect(saved.single.nameVi, 'Tăng huyết áp');
      expect(
        sentBody,
        {'conditions': [{'conditionId': 2, 'severity': 'mild'}]},
        reason: 'the request is wrapped even though the answer is not',
      );
    });

    test('§7.3.1 is fetched without a token, because onboarding has none yet',
        () async {
      String? authorization;
      final client = clientFor((request) async {
        authorization = request.headers['Authorization'];
        return json([
          {
            'id': 6,
            'nameVi': 'Dị ứng hải sản',
            'conditionType': 'allergy',
            'description': null,
          },
        ]);
      });
      client.setTokens(accessToken: 'ACCESS', refreshToken: 'REFRESH');

      final options = await ProfileApi(
        client,
      ).conditionCatalogue(type: 'allergy');

      expect(authorization, isNull);
      expect(options.single.id, 6);
      expect(options.single.isAllergy, isTrue);
      expect(options.single.isDiet, isFalse);
    });
  });

  group('the enums match the database', () {
    /// The drift this branch was carrying: the column is
    /// `ENUM('suggested','kept','replaced','eaten','skipped')` and Dart had
    /// `planned` — a string MySQL refuses — and no `kept` at all.
    test('every meal item status is one the column accepts', () {
      expect(
        MealItemStatus.values.map((s) => s.code).toSet(),
        {'suggested', 'kept', 'replaced', 'eaten', 'skipped'},
      );
    });

    test('every dish role is one the column accepts', () {
      expect(
        DishRole.values.map((r) => r.code).toSet(),
        {
          'main',
          'side_protein',
          'side_veg',
          'soup',
          'dessert',
          'drink',
          'snack',
        },
      );
    });

    test('every status and role has a Vietnamese label', () {
      for (final s in MealItemStatus.values) {
        expect(s.label, isNotEmpty);
        expect(s.label, isNot(s.code));
      }
      for (final r in DishRole.values) {
        expect(r.label, isNotEmpty);
        expect(r.label, isNot(r.code));
      }
    });

    test('the two roles step 4 never picks are still named', () {
      expect(DishRole.labelOf('dessert'), 'Tráng miệng');
      expect(DishRole.labelOf('drink'), 'Đồ uống');
    });

    /// A role added to the database and not here shows the raw code: ugly on
    /// screen, which is how it gets noticed, and never wrong.
    test('a role this app does not know falls back to its code', () {
      expect(DishRole.tryParse('sauce'), isNull);
      expect(DishRole.labelOf('sauce'), 'sauce');
      expect(DishRole.labelOf(null), '');
    });
  });
}
