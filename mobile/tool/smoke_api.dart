// ignore_for_file: avoid_print
//
// A command-line check: printing is how it reports.
// Drives the app's own API layer against the real backend, over a real
// socket. Every other test uses a fake transport, so this is the only thing
// that proves the two sides agree.
//
// Needs both services up:
//
//   python tools/run_ml_service.py
//   python tools/run_backend.py
//   cd mobile && dart run tool/smoke_api.dart
//
// It leaves ONE account behind per run, `dart-*@example.test`, because there
// is no endpoint that deletes an account (§7.1 has none and the admin
// screens are not built). Clear them with the Python smoke tool's own
// helper, which is also what cleans up after a crashed run:
//
//   python -c "import sys; sys.path.insert(0, 'tools'); //       from smoke_backend import delete_accounts; //       delete_accounts('dart-xxxx@example.test')"
import 'dart:io';

import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/auth_api.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/api/profile_api.dart';
import 'package:nutrition_app/data/models/health_profile.dart';

const base = 'http://localhost:5055/api/v1';

int checks = 0;
final failures = <String>[];

void check(String label, bool ok, [String detail = '']) {
  checks++;
  if (ok) {
    print('  [ok] $label');
  } else {
    failures.add('$label${detail.isEmpty ? '' : ' — $detail'}');
    print('  [FAIL] $label ${detail.isEmpty ? '' : '— $detail'}');
  }
}

Future<void> main() async {
  final client = ApiClient(baseUrl: base);
  final auth = AuthApi(client);
  final profiles = ProfileApi(client);

  final suffix = DateTime.now().microsecondsSinceEpoch
      .toRadixString(16);
  final email = 'dart-$suffix@example.test';

  print('\n§7.3.1  the public dictionary, with no token');
  final allergies = await profiles.conditionCatalogue(type: 'allergy');
  check('allergies come back without signing in', allergies.isNotEmpty,
      '${allergies.length} rows');
  check('every one is an allergy', allergies.every((c) => c.isAllergy));
  check('the ids are ints, not UUIDs',
      allergies.every((c) => c.id > 0));
  check('the names are already Vietnamese',
      allergies.every((c) => c.nameVi.trim().isNotEmpty),
      allergies.first.nameVi);

  print('\n§7.1.1  register');
  final session = await auth.register(
    email: email,
    password: 'MatKhau123',
    displayName: 'Dart Probe',
  );
  check('the account comes back', session.account.email == email,
      session.account.email);
  check('with a pair of tokens',
      session.accessToken.isNotEmpty && session.refreshToken.isNotEmpty);
  check('and has not finished onboarding',
      !session.account.hasFinishedOnboarding);

  print('\n§7.1.1  the same email twice');
  try {
    await auth.register(
      email: email,
      password: 'MatKhau123',
      displayName: 'Dart Probe',
    );
    check('a duplicate email is refused', false, 'it was accepted');
  } on ApiFailure catch (f) {
    check('a duplicate email is 409 EMAIL_ALREADY_EXISTS',
        f.code == ApiFailure.emailAlreadyExists && f.status == 409,
        '${f.status} ${f.code}');
    check('with a Vietnamese sentence to show', f.message.isNotEmpty,
        f.message);
  }

  print('\n§7.2.1  no profile yet');
  try {
    await profiles.read();
    check('reading a profile that does not exist is refused', false);
  } on ApiFailure catch (f) {
    // §7.2.1 gives this case 404 NOT_FOUND. The 409 PROFILE_REQUIRED
    // belongs to §7.2.3, which cannot compute targets without a profile.
    check('404 NOT_FOUND before the form is sent',
        f.code == ApiFailure.notFound && f.status == 404,
        '${f.status} ${f.code}');
  }

  print('\n§7.2.2  save the profile');
  final profile = HealthProfile()
    ..gender = Gender.male
    ..birthday = DateTime(2004, 11, 4)
    ..heightCm = 172
    ..weightKg = 68.5
    ..activity = ActivityLevel.moderate
    ..goal = HealthGoal.maintain
    ..targetWeightKg = 65;
  final saved = await profiles.save(profile);
  check('the server took it', saved.profile.gender == 'male',
      '${saved.profile.gender}');
  check('and sent back the age it computed', saved.profile.age != null,
      '${saved.profile.age}');
  check('and the BMI', saved.profile.bmi != null, '${saved.profile.bmi}');
  check('and the targets in the same answer, so no second call is needed',
      saved.targets.caloriesKcal > 0, '${saved.targets.caloriesKcal}');
  check('the target weight survived the round trip',
      saved.profile.targetWeightKg == 65, '${saved.profile.targetWeightKg}');

  // It must move nothing: the energy limit comes from the weight the user
  // has now. If a target weight ever reaches the formula, this is where it
  // shows up.
  final withTarget = (await profiles.targets()).caloriesKcal;
  profile.targetWeightKg = 55;
  final moved = (await profiles.save(profile)).targets.caloriesKcal;
  check('and changing it moves no limit at all', withTarget == moved,
      '$withTarget vs $moved');

  profile.targetWeightKg = null;
  final cleared = await profiles.save(profile);
  check('leaving it out clears it, because a PUT replaces the profile',
      cleared.profile.targetWeightKg == null,
      '${cleared.profile.targetWeightKg}');
  profile.targetWeightKg = 65;

  print('\n§7.2.3  the targets the server computed');
  final targets = await profiles.targets();
  check('a BMR came back', targets.bmrKcal > 0, '${targets.bmrKcal}');
  check('a TDEE above the BMR', targets.tdeeKcal > targets.bmrKcal,
      '${targets.tdeeKcal} vs ${targets.bmrKcal}');
  check('and a daily energy target', targets.caloriesKcal > 0,
      '${targets.caloriesKcal}');
  check('the three percentages add up to 100',
      targets.proteinPct + targets.carbsPct + targets.fatPct == 100,
      '${targets.proteinPct}/${targets.carbsPct}/${targets.fatPct}');
  check('the four meals came back',
      targets.mealShare.length == 4, '${targets.mealShare.keys}');

  // The app's own arithmetic against the server's, which is the thing the
  // parity suite pins with fixtures and this pins against a live server.
  targets.applyTo(profile);
  final localBmr = profile.bmr!;
  final localTarget = profile.energyTarget!;
  check('the local BMR matches the server to within a kcal',
      (localBmr - targets.bmrKcal).abs() <= 1,
      'local $localBmr vs server ${targets.bmrKcal}');
  check('and so does the local energy target',
      (localTarget - targets.caloriesKcal).abs() <= 1,
      'local $localTarget vs server ${targets.caloriesKcal}');

  print('\n§7.2.5  declare a condition');
  final seafood = allergies.firstWhere(
    (c) => c.nameVi.toLowerCase().contains('hải sản'),
    orElse: () => allergies.first,
  );
  final declared = await profiles.saveConditions([
    DeclaredCondition(
      conditionId: seafood.id,
      nameVi: seafood.nameVi,
      conditionType: seafood.conditionType,
      severity: 'severe',
    ),
  ]);
  check('the answer is a bare array of what is now declared',
      declared.length == 1 && declared.single.conditionId == seafood.id,
      '${declared.length} rows');
  check('and it reads back the same way',
      (await profiles.conditions()).single.conditionId == seafood.id);

  print('\n§7.2.5  a condition the app has not asked the severity of');
  // `user_conditions.severity` is NOT NULL DEFAULT 'moderate' and §7.2.5
  // refuses a body that leaves it out, so the client sends the column's own
  // default rather than nothing.
  final defaulted = await profiles.saveConditions([
    DeclaredCondition(
      conditionId: seafood.id,
      nameVi: seafood.nameVi,
      conditionType: seafood.conditionType,
    ),
  ]);
  check('is accepted, and lands as the column default',
      defaulted.length == 1 &&
          defaulted.single.severity == DeclaredCondition.defaultSeverity,
      '${defaulted.single.severity}');

  print('\n§7.1.4  which screen to open on');
  final me = await auth.me();
  check('the account now has a health profile', me.hasHealthProfile == true);
  check('and still has not finished onboarding',
      !me.hasFinishedOnboarding);
  check('a preference stage came back', me.preferenceStage != null,
      '${me.preferenceStage}');

  print('\n§7.1.2  log in again and read the profile back');
  final fresh = ApiClient(baseUrl: base);
  final freshAuth = AuthApi(fresh);
  final freshProfiles = ProfileApi(fresh);
  await freshAuth.logIn(email: email, password: 'MatKhau123');
  final reread = HealthProfile();
  (await freshProfiles.read()).applyTo(reread);
  (await freshProfiles.targets()).applyTo(reread);
  check('the returning user keeps their sex', reread.gender == Gender.male);
  check('their height and weight',
      reread.heightCm == 172 && reread.weightKg == 68.5,
      '${reread.heightCm} / ${reread.weightKg}');
  check('their goal and activity level',
      reread.goal == HealthGoal.maintain &&
          reread.activity == ActivityLevel.moderate);
  check('and the same energy target as before',
      (reread.energyTarget! - localTarget).abs() <= 1);

  print('\n§7.1.2  a wrong password');
  try {
    await ApiClient(baseUrl: base).post(
      '/auth/login',
      authenticated: false,
      body: {'email': email, 'password': 'SaiMatKhau9'},
    );
    check('a wrong password is refused', false);
  } on ApiFailure catch (f) {
    check('401 INVALID_CREDENTIALS',
        f.code == ApiFailure.invalidCredentials, '${f.status} ${f.code}');
  }

  print('\n§2.5  a validation error names the field');
  try {
    await fresh.put('/profile', body: {
      'gender': 'male',
      'dateOfBirth': '2004-11-04',
      'heightCm': 10, // chk_height allows 50..250
      'weightKg': 68.5,
      'activityLevel': 'moderate',
      'goal': 'maintain',
    });
    check('an impossible height is refused', false);
  } on ApiFailure catch (f) {
    check('400 VALIDATION_FAILED', f.code == ApiFailure.validationFailed,
        '${f.status} ${f.code}');
    check('and `details` names heightCm', f.forField('heightCm') != null,
        '${f.fields}');
  }

  print('\nno server at all');
  try {
    await ApiClient(
      baseUrl: 'http://localhost:1/api/v1',
      timeout: const Duration(seconds: 2),
    ).getList('/conditions', authenticated: false);
    check('an unreachable server is reported', false);
  } on ApiFailure catch (f) {
    // Either network code, depending on whether the host refuses the
    // connection or drops the packet. Windows drops it, so a dead port times
    // out rather than being refused. What matters is that both are retryable
    // and both carry a sentence, which is all the screen needs.
    check('a network failure the screen can offer to retry',
        (f.code == ApiFailure.unreachable_ || f.code == ApiFailure.timeout) &&
            f.isRetryable,
        f.code);
    check('with something to show the user', f.message.isNotEmpty, f.message);
  }

  client.close();
  fresh.close();

  print('\n${'=' * 68}');
  if (failures.isEmpty) {
    print('$checks/$checks checks passed against the real backend.');
    print('Test account left behind: $email');
    exit(0);
  }
  print('${failures.length}/$checks CHECKS FAILED:');
  for (final f in failures) {
    print('  - $f');
  }
  exit(1);
}
