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
import 'package:nutrition_app/data/api/food_api.dart';
import 'package:nutrition_app/data/api/profile_api.dart';
import 'package:nutrition_app/data/api/survey_api.dart';
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
  // The stable key. `id` is AUTO_INCREMENT, so the app keys its own curated
  // question list by `code` and looks the ids up here.
  check('every one carries a code',
      allergies.every((c) => c.code.isNotEmpty),
      allergies.map((c) => c.code).join(' '));
  check('and the codes are unique',
      allergies.map((c) => c.code).toSet().length == allergies.length);
  check('soy allergy is declarable',
      allergies.any((c) => c.code == 'allergy_soy'),
      allergies.map((c) => c.code).join(' '));
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
  final readBack = (await profiles.conditions()).single;
  check('and it reads back the same way',
      readBack.conditionId == seafood.id);
  check('with its code, so the app recognises it without a table of ids',
      readBack.code == seafood.code, readBack.code);
  // What the severity question is for: `condition_rules.severity_min` reads
  // this, and hypertension tightens its sodium limit at `severe`.
  check('and the severity that was sent, not the column default',
      readBack.severity == 'severe', '${readBack.severity}');

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

  // PUT /auth/me, which the specification has no slot for: the app has a
  // settings screen for the display name and there was nowhere to send it.
  final renamed = await auth.updateDisplayName('  Ten Da Sua  ');
  check('the display name can be changed, and comes back trimmed',
      renamed.displayName == 'Ten Da Sua', renamed.displayName);
  check('and it was stored, not just echoed',
      (await auth.me()).displayName == 'Ten Da Sua');
  try {
    await auth.updateDisplayName(' N ');
    check('a one-letter name is refused', false, 'it was accepted');
  } on ApiFailure catch (f) {
    check('a one-letter name is 400 VALIDATION_FAILED',
        f.code == ApiFailure.validationFailed, '${f.status} ${f.code}');
    check('and `details` names displayName',
        f.forField('displayName') != null, '${f.fields}');
  }

  print('\n§7.4  the taste survey — the one thing that ends onboarding');
  final surveys = SurveyApi(client);
  final deck = await surveys.deck();
  check('the deck comes back with a session id', deck.sessionId.isNotEmpty);
  check('and 30 cards, the size §7.4.1 settles on', deck.items.length == 30,
      '${deck.items.length} cards');
  check('totalItems agrees with what arrived',
      deck.totalItems == deck.items.length,
      '${deck.totalItems} against ${deck.items.length}');
  check('minRequired is the 20 opinionated swipes §7.4.2 asks for',
      deck.minRequired == 20, '${deck.minRequired}');
  check('every card has what a swipe card draws',
      deck.items.every((c) =>
          c.name.isNotEmpty && c.category.isNotEmpty && c.kcal > 0),
      'one card was incomplete');
  check('no card repeats — a deck with a dish twice wastes a swipe',
      deck.items.map((c) => c.id).toSet().length == deck.items.length);
  // Every one of the 318 rows has `image_url` null, so a card has nothing to
  // draw but what `core/dish_look.dart` derives from `dish_role`. The look
  // itself cannot be checked here — it is a Flutter `Color`, and this tool
  // runs on plain Dart — so what is checked is the input it needs: a role
  // this app recognises. An unknown one falls back to a plate icon, which is
  // not wrong, only anonymous.
  const knownRoles = {
    'main', 'side_protein', 'side_veg', 'soup', 'dessert', 'drink', 'snack',
  };
  check('every card names a dish_role this app has a look for',
      deck.items.every((c) => knownRoles.contains(c.dishRole)),
      '${deck.items.map((c) => c.dishRole).toSet()}');
  check('and none of them carries a photo, so the fallback is the only path',
      deck.items.every((c) => c.imageUrl == null));

  // 28 opinions and 2 "chưa từng ăn", which is over `minRequired` and still
  // exercises the `unknown` path that is stored but left out of the vector.
  final swipes = <SurveySwipe>[
    for (var i = 0; i < deck.items.length; i++)
      (
        foodId: deck.items[i].id,
        action: i >= deck.items.length - 2
            ? 'unknown'
            : (i % 3 == 0 ? 'like' : (i % 3 == 1 ? 'neutral' : 'dislike')),
      ),
  ];
  final outcome =
      await surveys.submit(sessionId: deck.sessionId, swipes: swipes);
  check('the submission answers with the same session id',
      outcome.sessionId == deck.sessionId);
  check('every swipe was stored', outcome.total == swipes.length,
      '${outcome.total} of ${swipes.length}');
  check('the two `unknown` swipes are counted as skipped, not as opinions',
      outcome.skipped == 2 && outcome.opinionated == swipes.length - 2,
      '${outcome.opinionated} opinions, ${outcome.skipped} skipped');
  check('a preference stage came back', outcome.stage.isNotEmpty,
      outcome.stage);
  check('with signals behind it', outcome.nSignals > 0, '${outcome.nSignals}');
  check('nSignals never exceeds the opinions sent — F1 can only remove',
      outcome.nSignals <= outcome.opinionated,
      '${outcome.nSignals} against ${outcome.opinionated}');

  // THE POINT OF THIS SECTION. Before the survey reached the server the app
  // built a vector locally and moved on, so this stamp stayed null — and
  // `welcome_screen` reads it on every launch, which sent a user who had
  // just swiped thirty cards straight back to the survey, for good.
  final after = await auth.me();
  check('and NOW the account has finished onboarding',
      after.hasFinishedOnboarding, '${after.onboardingCompletedAt}');
  // Within a second, not identical. `users.onboarding_completed_at` is a
  // DATETIME with no fractional seconds, so MySQL rounds on store and the
  // POST's answer carries the value from before that rounding. Only the
  // presence of the stamp is meaningful, and nothing in the app compares the
  // two.
  check('and reports it within a second of the value POST returned',
      after.onboardingCompletedAt != null &&
          after.onboardingCompletedAt!
                  .difference(outcome.onboardingCompletedAt)
                  .abs() <
              const Duration(seconds: 1),
      '${after.onboardingCompletedAt} against '
      '${outcome.onboardingCompletedAt}');

  // Re-sending the SAME session is the retry the app's button makes, for the
  // one failure it is there for: the request arrived, the account was
  // stamped, and the answer was lost coming back. It does NOT replay as a
  // second survey — the server checks the stamp BEFORE it looks at the
  // session id — so the retry answers 409, and the caller has to read that
  // as success. The app does: `survey_screen._explain` sends the user on.
  try {
    await surveys.submit(sessionId: deck.sessionId, swipes: swipes);
    check('re-submitting the same session is refused once the account is '
        'stamped', false, 'it was accepted a second time');
  } on ApiFailure catch (f) {
    check('re-submitting the same session answers 409, not a second survey',
        f.code == ApiFailure.onboardingAlreadyCompleted,
        '${f.status} ${f.code}');
  }

  try {
    await surveys.deck();
    check('the deck is refused once the survey is done', false,
        'it was handed out again');
  } on ApiFailure catch (f) {
    check('409 ONBOARDING_ALREADY_COMPLETED',
        f.code == ApiFailure.onboardingAlreadyCompleted,
        '${f.status} ${f.code}');
  }


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

  final foods = FoodApi(fresh);

  print('\n§7.3.2 · §7.3.3  the dictionaries the browse screen filters by');
  final categories = await foods.categories();
  check('the food groups come back', categories.isNotEmpty,
      '${categories.length} groups');
  check('each one has a Vietnamese name',
      categories.every((c) => c.name.trim().isNotEmpty));
  // §7.5.1's parameter table says `int` for categoryId while the JSON
  // example beside it shows a UUID. The schema is the side that is right,
  // and a client that parsed an int here would fail on every row.
  check('and a CHAR(36) id, not an int as §7.5.1 claims',
      categories.every((c) => c.id.length == 36 && c.id.contains('-')),
      categories.first.id);

  final allTags = await foods.tags();
  check('the tags come back', allTags.isNotEmpty, '${allTags.length} tags');
  check('with int ids, unlike the dishes and the groups',
      allTags.every((t) => t.id > 0));
  check('and only the three types the schema kept — no `taste`',
      allTags.map((t) => t.tagType).toSet().every(
          (t) => const {'allergen', 'diet', 'nutrition'}.contains(t)),
      '${allTags.map((t) => t.tagType).toSet()}');
  final allergens = await foods.tags(type: 'allergen');
  check('?type= narrows to one tag_type',
      allergens.isNotEmpty && allergens.every((t) => t.tagType == 'allergen'),
      '${allergens.length} allergen tags');

  print('\n§7.5.1  browse the catalogue');
  final firstPage = await foods.search(pageSize: 10);
  check('a page of ten comes back', firstPage.items.length == 10,
      '${firstPage.items.length}');
  check('the whole catalogue is bigger than one page',
      firstPage.totalItems > 10, '${firstPage.totalItems}');
  check('totalPages is the ceiling, not the floor',
      firstPage.totalPages == (firstPage.totalItems + 9) ~/ 10,
      '${firstPage.totalPages} for ${firstPage.totalItems}');
  check('hasMore agrees with the page it is on', firstPage.hasMore);
  check('every row carries what a list tile draws',
      firstPage.items.every((f) =>
          f.name.isNotEmpty && f.category.isNotEmpty && f.kcal > 0 &&
          f.servingSizeG > 0),
      'one row was incomplete');

  final secondPage = await foods.search(pageSize: 10, page: 2);
  check('page 2 shares no row with page 1 — an unstable sort would hide a '
      'dish from every page',
      firstPage.items
          .map((f) => f.id)
          .toSet()
          .intersection(secondPage.items.map((f) => f.id).toSet())
          .isEmpty);

  final soups = await foods.search(dishRole: 'soup', pageSize: 100);
  check('dishRole really filters',
      soups.items.isNotEmpty &&
          soups.items.every((f) => f.dishRole == 'soup'),
      '${soups.items.length} soups');
  final lunch = await foods.search(mealType: 'lunch', pageSize: 100);
  check('mealType returns exactly the roles a lunch can hold',
      lunch.items.map((f) => f.dishRole).toSet().difference(
          const {'main', 'side_protein', 'soup'}).isEmpty,
      '${lunch.items.map((f) => f.dishRole).toSet()}');
  final light = await foods.search(maxCalories: 100, pageSize: 100);
  check('maxCalories is a ceiling per serving',
      light.items.every((f) => f.kcal <= 100));
  final byGroup = await foods.search(
      categoryId: categories.first.id, pageSize: 100);
  check('categoryId filters by the UUID the dictionary gave',
      byGroup.items.isNotEmpty &&
          byGroup.items.every((f) => f.category == categories.first.name),
      '${byGroup.items.length} dishes in ${categories.first.name}');

  print('\n§7.5.2  one dish in full');
  final subject = firstPage.items.first;
  final full = await foods.detail(subject.id);
  check('it is the dish asked for', full.id == subject.id);
  check('the list row and the detail agree on the name',
      full.name == subject.name, '${full.name} against ${subject.name}');
  check('a serving weight and an energy figure came back',
      full.nutrition.servingSizeG > 0 && full.nutrition.caloriesKcal > 0);
  check('and the three macros, which is what the bars need',
      full.nutrition.macroShare != null,
      'protein=${full.nutrition.proteinG} carbs=${full.nutrition.carbsG} '
      'fat=${full.nutrition.fatG}');
  final share = full.nutrition.macroShare;
  check('the three shares are normalised by their own total',
      share == null ||
          (share.protein + share.carbs + share.fat - 1).abs() < 1e-9);
  check('the detail carries the group as an object with a name',
      full.brief.category.isNotEmpty, full.brief.category);
  check('and this user has no mark on it yet', full.brief.mark == null,
      '${full.brief.mark}');

  // The catalogue publishes purine for 70 of its 318 dishes. Over a page of
  // ten there is almost certainly at least one gap, and a gap has to arrive
  // as `null` — a 0 would read as "contains no purine", which is a different
  // and reassuring claim.
  var withGaps = 0;
  for (final row in firstPage.items) {
    final detail = await foods.detail(row.id);
    if (detail.nutrition.purineMg == null) withGaps++;
  }
  check('an unmeasured nutrient arrives as null, never as 0',
      withGaps > 0,
      'all ten dishes had a purine figure, so the null path went unchecked');

  try {
    await foods.detail('00000000-0000-4000-8000-000000000000');
    check('a dish that does not exist is refused', false);
  } on ApiFailure catch (f) {
    check('404 NOT_FOUND for a dish that is not there',
        f.code == ApiFailure.notFound, '${f.status} ${f.code}');
  }


  print('\nPUT /foods/{id}/mark  bookmarks and blocked dishes');
  final page = await fresh.get('/foods', query: {'pageSize': '3'});
  final dishIds = [
    for (final item in page['items'] as List) (item as Map)['id'] as String,
  ];
  check('the catalogue answers with dishes to mark', dishIds.length == 3,
      '${dishIds.length} dishes');

  final dish = dishIds.first;
  final loved = await foods.setMark(dish, FoodMark.loved);
  check('bookmarking answers with the mark it stored',
      loved.kind == FoodMark.loved && loved.foodId == dish, '${loved.kind}');
  check('and says when', loved.markedAt != null);
  check('the bookmark is in the saved list',
      (await foods.marked(FoodMark.loved)).any((d) => d.id == dish));

  final again = await foods.setMark(dish, FoodMark.loved);
  check('sending the same mark twice is idempotent',
      again.kind == FoodMark.loved);

  final blocked = await foods.setMark(dish, FoodMark.blocked);
  check('switching to blocked answers blocked',
      blocked.kind == FoodMark.blocked, '${blocked.kind}');
  check('and the bookmark is gone - one row per (user, food)',
      !(await foods.marked(FoodMark.loved)).any((d) => d.id == dish));
  check('while the blocked list has it',
      (await foods.marked(FoodMark.blocked)).any((d) => d.id == dish));

  // The behaviour the F1 change could have broken: a blocked dish must stay
  // findable, because the only screen that unblocks it is reached by finding
  // it. `excludeUnsafe` defaults to true, so this is the default path.
  final searched = await fresh.get('/foods', query: {'pageSize': '100'});
  final visible = [
    for (final item in searched['items'] as List)
      if ((item as Map)['id'] == dish) item,
  ];
  check('a blocked dish is still findable with excludeUnsafe=true',
      visible.length == 1);
  check('and still reported safe to EAT - a block is about being suggested',
      visible.isEmpty || visible.single['isSafeForUser'] == true);
  check('with the block carried as a mark',
      visible.isEmpty || visible.single['mark'] == FoodMark.blocked);

  final unmarked = await foods.setMark(dish, null);
  check('a null kind clears the mark', unmarked.kind == null);
  check('and leaves the account with no marks at all',
      (await foods.marked(FoodMark.loved)).isEmpty &&
          (await foods.marked(FoodMark.blocked)).isEmpty);

  try {
    await foods.setMark(
        '00000000-0000-4000-8000-000000000000', FoodMark.loved);
    check('a dish that does not exist is refused', false);
  } on ApiFailure catch (f) {
    check('404 NOT_FOUND', f.code == ApiFailure.notFound,
        '${f.status} ${f.code}');
  }

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
