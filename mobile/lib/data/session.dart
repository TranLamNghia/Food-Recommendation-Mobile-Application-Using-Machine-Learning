import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'api/api_client.dart';
import 'api/api_config.dart';
import 'api/failure.dart';
import 'api/auth_api.dart';
import 'api/diary_api.dart';
import 'api/feedback_api.dart';
import 'api/food_api.dart';
import 'api/meal_plan_api.dart';
import 'api/profile_api.dart';
import 'api/progress_api.dart';
import 'api/survey_api.dart';
import 'mock/mock_foods.dart';
import 'mock/mock_rules.dart';
import 'models/diary_day.dart';
import 'models/diary_entry.dart';
import 'models/food.dart';
import 'models/candidate_count.dart';
import 'models/food_adapters.dart';
import 'models/food_brief.dart';
import 'models/food_detail.dart';
import 'models/food_query.dart';
import 'models/health_profile.dart';
import 'models/meal_plan.dart';
import 'models/own_dish.dart';
import 'models/progress.dart';
import 'models/swipe_action.dart';
import 'recommender/food_vector.dart';
import 'recommender/menu_builder.dart';
import 'recommender/nutrient_target.dart';
import 'recommender/preference_profile.dart';
import 'rules/day_budget.dart';
import 'rules/dish_screening.dart';

/// The state shared across the whole session.
///
/// In this interface build everything lives in memory and disappears when the
/// app closes — which is exactly what a mock is for. When it is wired to the
/// real server this class keeps its public surface and only its insides
/// change: [completeSurvey] calls `POST /onboarding/survey`,
/// [regeneratePlan] calls `POST /meal-plans`, and [logMeal] calls
/// `POST /diary`.
class AppSession extends ChangeNotifier {
  /// [api] is for tests, which pass a client backed by a fake transport.
  /// Left out, the mode is whatever `--dart-define=API_BASE_URL` said at
  /// compile time — and with no address, offline.
  AppSession({math.Random? rng, ApiClient? api})
    : _rng = rng ?? math.Random(),
      _client = api ?? (ApiConfig.isOnline ? ApiClient() : null) {
    final client = _client;
    if (client != null) {
      _auth = AuthApi(client);
      _profiles = ProfileApi(client);
      _foods = FoodApi(client);
      _surveys = SurveyApi(client);
      _mealPlans = MealPlanApi(client);
      _diary = DiaryApi(client);
      _feedback = FeedbackApi(client);
      _progress = ProgressApi(client);
    }
  }

  final math.Random _rng;

  // ── Which of the two modes ───────────────────────────────────────

  final ApiClient? _client;
  AuthApi? _auth;
  ProfileApi? _profiles;
  FoodApi? _foods;
  SurveyApi? _surveys;
  MealPlanApi? _mealPlans;
  DiaryApi? _diary;
  FeedbackApi? _feedback;
  ProgressApi? _progress;

  /// Whether there is a server behind this session.
  ///
  /// Every method that can do both says which it is doing with a
  /// `// ONLINE:` or `// OFFLINE:` line — see `mobile/README.md`.
  bool get isOnline => _auth != null;

  /// The health profile filled in during the onboarding flow.
  final HealthProfile profile = HealthProfile();

  /// The dish catalogue that has passed the F1 filter. The mock uses the
  /// survey deck directly.
  List<Food> get candidates => MockFoods.surveyDeck;

  late final FoodVectorSpace _space = FoodVectorSpace.fromFoods(candidates);
  FoodVectorSpace get space => _space;

  PreferenceProfile? _preference;

  /// The preference profile. Before any swipe it is the empty profile —
  /// Stage 0, where every dish scores the same and the ordering is decided by
  /// the nutrition constraints.
  PreferenceProfile get preference =>
      _preference ?? PreferenceProfile.empty(_space);

  /// One plan per calendar day, keyed by [_dayKey]. Days are generated the
  /// first time they are opened, so the week strip costs nothing up front.
  final Map<int, DailyPlan> _plans = {};

  DateTime _selectedDay = _dateOnly(DateTime.now());

  static DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);
  static int _dayKey(DateTime d) => d.year * 10000 + d.month * 100 + d.day;

  /// The day the plan screen is showing. Defaults to today.
  DateTime get selectedDay => _selectedDay;

  bool get viewingToday => _dayKey(_selectedDay) == _dayKey(DateTime.now());

  /// Plan of [selectedDay].
  DailyPlan? get plan => _plans[_dayKey(_selectedDay)];

  /// Plan of the real current day, whatever day is on screen.
  DailyPlan? get todayPlan => _plans[_dayKey(DateTime.now())];

  DailyPlan? planOn(DateTime day) => _plans[_dayKey(day)];

  /// Switches the plan screen to [day], and loads that day's plan on first
  /// visit.
  ///
  /// The switch itself is immediate — the week strip must not wait on a
  /// network call to move — and the plan arrives after. A screen draws
  /// [plan] as `null` in between, which is the state it already had to
  /// handle for a day with no targets yet.
  Future<void> selectDay(DateTime day) async {
    _selectedDay = _dateOnly(day);
    notifyListeners();
    if (plan == null) await loadPlan();
  }

  // ONLINE: GET /meal-plans?date=… — §7.6.1, with `autoGenerate` left on, so
  // a day that has no plan gets one built server-side.
  //
  // OFFLINE: the Dart builder, which needs no round trip.
  //
  // The cache is checked first in both modes. §7.6.1 is idempotent and would
  // answer with the stored plan anyway, but asking again on every rebuild of
  // the screen would be a request per frame of the week strip.
  Future<DailyPlan?> loadPlan({DateTime? date}) async {
    final day = _dateOnly(date ?? _selectedDay);
    final cached = _plans[_dayKey(day)];
    if (cached != null) return cached;

    final api = _mealPlans;
    if (api == null) {
      final built = _build(day);
      notifyListeners();
      return built;
    }

    final loaded = await api.forDate(day);
    if (loaded != null) _plans[_dayKey(day)] = loaded;
    notifyListeners();
    return loaded;
  }

  /// Plans for [days] consecutive days starting today, building the missing
  /// ones.
  ///
  /// Does not notify: it is called while building, and the plans it adds do
  /// not change anything already on screen.
  List<DailyPlan> plansForNext(int days) {
    final today = _dateOnly(DateTime.now());
    return [
      for (var i = 0; i < days; i++)
        ?_buildIfAbsent(today.add(Duration(days: i))),
    ];
  }

  DailyPlan? _buildIfAbsent(DateTime day) =>
      _plans[_dayKey(day)] ?? _build(day);

  DailyPlan? _build(DateTime day) {
    final energy = profile.energyTarget;
    final macro = profile.macroTarget;
    if (energy == null || macro == null) return null;

    // Keep yesterday's dishes out so consecutive days differ. Without this
    // the builder, fed the same profile and targets, returns the same
    // top-scoring menu for every day of the week.
    final previous = planOn(day.subtract(const Duration(days: 1)));
    final avoid = {...?previous?.allItems.map((i) => i.food.id)};

    return _plans[_dayKey(day)] = _builder(avoid: avoid).build(
      date: day,
      targetKcal: energy,
      targetProtein: macro.protein,
      targetCarb: macro.carb,
      targetFat: macro.fat,
    );
  }

  final List<DiaryEntry> diary = [];

  /// The exploration ratio in force. The user cannot change it; it lives here
  /// so the experiment screen can change it when two configurations have to
  /// be compared.
  double explorationRatio = 0.3;

  /// The **day**-level micronutrient constraints Step 4 has to satisfy.
  ///
  /// In the real system this list is assembled from two sources — neither of
  /// them a number a developer made up:
  ///
  /// * `condition_rules` with `scope = 'per_day'` and `is_hard = 1`, filtered
  ///   by the conditions the user declared. Currently four rows: sodium
  ///   ≤ 2000 mg (WHO, applied to hypertension and kidney disease), purine
  ///   ≤ 400 mg, protein ≤ 48 g (KDIGO 2024).
  /// * `rda_reference`, looked up by sex and age, for the goals the user
  ///   **states themselves**. Currently fibre ≥ 25 g/day for anyone aged 10
  ///   or over (WHO 2023).
  ///
  /// Empty by default: with no condition and no goal, Step 4 runs exactly as
  /// it did before. The mock has no condition-declaration flow yet, so the
  /// experiment screen assigns to this directly.
  ///
  /// Note that `purine_mg` **cannot** be enforced — see
  /// `NutrientTarget.valueOf`. Passing it in is still valid and it will show
  /// up in `DailyPlan.unenforceableTargets` instead of being quietly treated
  /// as satisfied.
  /// The day-level nutrient constraints step 4's phase 5 repairs a plan
  /// against — sodium for hypertension, purine for gout.
  ///
  /// **Derived, not stored.** It used to be a plain field that nothing ever
  /// assigned outside one test, so the thresholds existed in the rule set,
  /// were shown on the day-budget card, and never reached the builder at
  /// all. Deriving it means it cannot fall out of step with what the user
  /// has declared.
  ///
  /// Hard ceilings only. A soft threshold costs score and does not bind, and
  /// handing one to phase 5 would turn a recommendation into a prohibition —
  /// sugar ≤ 25 g/day is advice, sodium ≤ 2 000 mg is a limit.
  List<NutrientTarget> get nutrientTargets => [
    for (final limit in dayThresholdsFor(userConditions))
      if (limit.isHard) NutrientTarget.atMost(limit.nutrient, limit.amount),
  ];

  // ── Account ──────────────────────────────────────────────────────

  String? _accountEmail;
  String? _displayName;

  /// `null` only before signing in. An account is required: the welcome
  /// screen lets nobody reach the profile questions without one.
  String? get accountEmail => _accountEmail;
  String? get displayName => _displayName;
  bool get isSignedIn => _accountEmail != null;

  /// `null` until the taste survey has been accepted — §7.1.4's
  /// `onboardingCompletedAt`. It decides whether the app opens on the survey
  /// or on the plan.
  DateTime? _onboardingCompletedAt;
  DateTime? get onboardingCompletedAt => _onboardingCompletedAt;
  bool get hasFinishedOnboarding => _onboardingCompletedAt != null;

  // OFFLINE: accepts anything the form already validated, with no server to
  // ask. Logging in passes no [displayName] and keeps the one already known,
  // the way the real account would return it.
  void signIn({required String email, String? displayName}) {
    _accountEmail = email.trim();
    if (displayName != null) _displayName = displayName.trim();
    notifyListeners();
  }

  // ONLINE: POST /auth/register — specification §7.1.1.
  //
  // Throws [ApiFailure]; the screen shows `message` and branches on `code`
  // (`EMAIL_ALREADY_EXISTS` is the one worth its own wording).
  Future<void> register({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final auth = _auth;
    if (auth == null) {
      signIn(email: email, displayName: displayName);
      return;
    }
    final session = await auth.register(
      email: email,
      password: password,
      displayName: displayName,
    );
    _accountEmail = session.account.email;
    _displayName = session.account.displayName;
    _onboardingCompletedAt = session.account.onboardingCompletedAt;
    notifyListeners();
  }

  // ONLINE: POST /auth/login — specification §7.1.2.
  //
  // A returning user keeps the profile they already filled in: after signing
  // in this reads it back from the server rather than asking the questions
  // again. That is the point of having an account at all.
  Future<void> logIn({
    required String email,
    required String password,
  }) async {
    final auth = _auth;
    if (auth == null) {
      signIn(email: email);
      return;
    }
    final session = await auth.logIn(email: email, password: password);
    _accountEmail = session.account.email;
    _displayName = session.account.displayName;
    _onboardingCompletedAt = session.account.onboardingCompletedAt;
    await _pullProfile();
    notifyListeners();
  }

  // ONLINE: GET /auth/me, then §7.2.1 and §7.2.3 if there is a profile.
  //
  // The two lookups are what makes logging in different from registering.
  // `GET /auth/me` is asked first because only it reports
  // `hasHealthProfile`: §7.1.1 and §7.1.2 leave that field out, and reading
  // §7.2.1 without it would mean treating its `404 NOT_FOUND` as control
  // flow.
  Future<void> _pullProfile() async {
    final auth = _auth;
    final api = _profiles;
    if (auth == null || api == null) return;

    final me = await auth.me();
    _onboardingCompletedAt = me.onboardingCompletedAt;
    // Before the `hasHealthProfile` return below: the marks belong to the
    // account, not to the profile, so a user who signed up and bookmarked a
    // dish before answering the questions still has them.
    await _pullMarks();
    if (me.hasHealthProfile != true) return;

    (await api.read()).applyTo(profile);
    // The server's own step 1 output, which overwrites the default
    // 15 / 60 / 25 split so the offline arithmetic agrees with it.
    (await api.targets()).applyTo(profile);
  }

  // ONLINE: PUT /profile — specification §7.2.2.
  //
  // Called when the onboarding questions are done. The `calculating` screen
  // runs this behind its animation, which until now stood in for exactly
  // this round trip.
  Future<void> saveProfile() async {
    final api = _profiles;
    if (api == null) return;
    // One round trip, not two: §7.2.2 recomputes step 1 as it saves and
    // sends the targets back with the profile.
    (await api.save(profile)).targets.applyTo(profile);
    await _saveConditions(api);
    notifyListeners();
  }

  // ONLINE: §7.3.1 to learn the ids, then §7.2.5 to declare.
  //
  // The app ships its own curated list of questions — its own icons, its own
  // wording, its own order — keyed by `conditions.code`. The ids come from
  // the dictionary at run time, because `conditions.id` is `AUTO_INCREMENT`
  // and follows the seed's insert order: a hard-coded `2` would be
  // hypertension on this database and something else on the next, and would
  // declare the wrong illness without any error.
  //
  // **A code the dictionary does not know stops the save.** Dropping it
  // quietly is the one thing that must not happen here: these declarations
  // are what the F1 filter removes dishes by, so a silently lost allergy is
  // a dish the user is allergic to, recommended to them, with nothing
  // reporting it.
  Future<void> _saveConditions(ProfileApi api) async {
    final declared = {...profile.conditions, ...profile.allergies}
      ..remove(HealthProfile.noneCode);
    if (declared.isEmpty) {
      // Still sent: §7.2.5 replaces the whole set, so an empty list is how
      // "I have none" and "I no longer have the one I declared" are stored.
      await api.saveConditions(const []);
      return;
    }

    final catalogue = await api.conditionCatalogue();
    final idOf = {for (final c in catalogue) c.code: c.id};

    final unknown = declared.where((c) => !idOf.containsKey(c)).toList();
    if (unknown.isNotEmpty) {
      throw ApiFailure(
        code: ApiFailure.unexpectedShape,
        message:
            'Không lưu được khai báo sức khỏe: máy chủ không biết '
            '${unknown.join(", ")}. Hãy cập nhật ứng dụng rồi thử lại.',
      );
    }

    await api.saveConditions([
      for (final code in declared)
        DeclaredCondition(
          conditionId: idOf[code]!,
          code: code,
          nameVi: '',
          conditionType: '',
          severity: profile.severityOf(code),
        ),
    ]);
  }

  // ── The filter screen's live count ───────────────────────────────

  /// `conditions.code` -> `conditions.id`, fetched once.
  ///
  /// Cached because the count is asked again on every tick of a checkbox,
  /// and the dictionary cannot change between two of them. `conditions.id`
  /// is `AUTO_INCREMENT`, so it is whatever the seed order made it and
  /// cannot be hard-coded on this side — see [_saveConditions].
  Map<String, int>? _conditionIds;

  // ONLINE: POST /onboarding/candidates/count — §7.4.3.
  //
  // OFFLINE: the Dart copy of the filter, over the mock catalogue. Numbers
  // out of 30 rather than out of 318, which is what the offline catalogue
  // holds — the screen prints whatever [CandidateCount.totalFoods] says
  // rather than a figure of its own, so both modes read correctly.
  //
  // Takes the selection as an argument rather than reading [profile]: the
  // screen asks about what is ticked at this moment, and an empty set has to
  // mean "nothing declared" and not "whatever is on file". Reading the
  // profile would lose that distinction, which is the one the endpoint
  // exists for.
  Future<CandidateCount> countCandidates({
    required Set<String> codes,
    Map<String, String> severities = const {},
  }) async {
    final declared = codes.where((c) => c != HealthProfile.noneCode).toSet();
    final api = _surveys;
    if (api == null) return _countCandidatesOffline(declared);

    if (declared.isEmpty) {
      // No code to look up, so no dictionary to fetch. This is the first
      // view of the screen, which is the one view that must not wait on a
      // round trip it does not need.
      return api.countCandidates(const []);
    }

    final ids = _conditionIds ??= {
      for (final option in await _profiles!.conditionCatalogue())
        option.code: option.id,
    };
    // A code the dictionary does not know stops the count, for the same
    // reason it stops a save: these declarations are what dishes are removed
    // by, so quietly dropping one would show a reassuring number built from
    // an allergy the server never heard about.
    final unknown = declared.where((c) => !ids.containsKey(c)).toList();
    if (unknown.isNotEmpty) {
      throw ApiFailure(
        code: ApiFailure.unexpectedShape,
        message:
            'Không đếm được: máy chủ không biết ${unknown.join(", ")}. '
            'Hãy cập nhật ứng dụng rồi thử lại.',
      );
    }

    return api.countCandidates([
      for (final code in declared)
        (
          conditionId: ids[code]!,
          severity: severities[code] ?? HealthProfile.defaultSeverity,
        ),
    ]);
  }

  // OFFLINE: `rules/dish_screening.dart`, which `step1_parity_test` holds in
  // parity with the Python filter. An empty [DayBudget] on purpose: this
  // count is about the dishes themselves, and a per-day allowance belongs to
  // a day that has not started.
  CandidateCount _countCandidatesOffline(Set<String> codes) {
    final foods = MockFoods.surveyDeck;
    final result = screenDishes(
      foods: foods,
      conditions: conditionsFromCodes(codes),
      budget: const DayBudget(),
    );
    final byRole = <String, int>{};
    for (final food in result.allowed) {
      byRole[food.dishRole] = (byRole[food.dishRole] ?? 0) + 1;
    }
    return CandidateCount(
      totalFoods: foods.length,
      remainingFoods: result.allowed.length,
      byDishRole: byRole,
      // The offline catalogue is 30 dishes, which is the survey's own deck,
      // so "enough for a survey" is the same question as "anything left".
      enoughForSurvey: result.allowed.isNotEmpty,
      surveyDeckSize: result.allowed.length,
    );
  }

  /// Leaves the account but keeps the profile, the plans and the diary: they
  /// belong to the account, and logging back in finds them again.
  void signOut() {
    _accountEmail = null;
    _onboardingCompletedAt = null;
    // The tokens go with the account, or the next request would still be
    // authenticated as the user who just signed out.
    _auth?.logOut();
    notifyListeners();
  }

  // ONLINE: PUT /auth/me — the display name, and nothing else.
  //
  // There used to be a phone number here too. It had no column in `users`
  // and no endpoint, so it was typed, shown, and gone on the next launch —
  // and neither of the two apps this one is modelled on asks for one.
  //
  // OFFLINE: kept in memory, like everything else.
  Future<void> updateAccount({required String displayName}) async {
    final auth = _auth;
    if (auth == null) {
      _displayName = displayName.trim();
      notifyListeners();
      return;
    }
    final account = await auth.updateDisplayName(displayName);
    // The server's own answer, not the typed text: it trimmed it, and it is
    // the authority on what is now stored.
    _displayName = account.displayName;
    notifyListeners();
  }

  // ── Passwords ────────────────────────────────────────────────────
  //
  // OFFLINE: the mock keeps no password at all — `signIn` takes whatever the
  // form validated — so there is nothing to check a code or a current
  // password against. All three succeed, which lets the screens be walked
  // through without a server.

  // ONLINE: POST /auth/forgot-password — §7.1.5. Answers the same for every
  // address, so this returns nothing: there is nothing true to report beyond
  // "if that address is registered, a mail is on its way".
  Future<void> requestPasswordReset(String email) async {
    await _auth?.forgotPassword(email);
  }

  // ONLINE: POST /auth/reset-password — §7.1.6. Ends every session of the
  // account, so the user logs in afterwards; nothing changes in this one.
  Future<void> resetPassword({
    required String code,
    required String newPassword,
  }) async {
    await _auth?.resetPassword(token: code, newPassword: newPassword);
  }

  /// Changes the password of the account signed in. Returns `true` when that
  /// also ended this session, as it does online: §7.1.7 revokes every
  /// refresh token, this device's included, and the app is expected to send
  /// the user back to log in with the new password.
  // ONLINE: PUT /auth/password — §7.1.7.
  Future<bool> changePassword({
    required String current,
    required String next,
  }) async {
    final auth = _auth;
    if (auth == null) return false;
    await auth.changePassword(currentPassword: current, newPassword: next);
    // Signed out locally too, keeping the data — it belongs to the account,
    // and logging back in finds it, exactly as after [signOut].
    signOut();
    return true;
  }

  /// Removes the account and everything stored under it.
  void deleteAccount() {
    _accountEmail = null;
    _displayName = null;
    reset();
  }

  // ── Saved dishes ─────────────────────────────────────────────────
  //
  // One set each, and the two are kept exclusive on this side as well,
  // because `user_food_marks` has one row per (user, food): "saved to try"
  // and "never suggest this" contradict each other, so setting one clears
  // the other. Online these two sets are a cache of that table; offline they
  // are the whole store.

  /// Dishes the user bookmarked.
  ///
  /// Affects nothing that gets computed — not the plan, not the score. It is
  /// a list the user keeps. Said plainly because the icon used to be a heart,
  /// which promised the system was learning from it.
  final Set<String> lovedIds = {};

  /// Dishes the user never wants suggested again. Removed from the candidate
  /// pool before a plan is built, so no score can bring them back.
  final Set<String> neverAgainIds = {};

  /// The dishes behind those two sets, so the saved-dishes screens have
  /// something to draw.
  ///
  /// This is what the empty-list defect was: the screens filtered
  /// `MockFoods` by these ids, and online the ids are the server's UUIDs. No
  /// id matched, so the account screen read "3 món" and the list under it was
  /// blank — the marks were stored and enforced, and unreachable.
  final Map<String, FoodBrief> _markedDishes = {};

  /// The dishes carrying [kind], in the order the server listed them (by
  /// name) or, offline, the order they were marked in.
  List<FoodBrief> savedDishes(String kind) => [
    for (final dish in _markedDishes.values)
      if (dish.mark == kind) dish,
  ];

  // ONLINE: PUT /foods/{id}/mark.
  //
  // OFFLINE: the sets and the map above are the store.
  //
  // The server answers with the state it now holds, and that answer is what
  // is applied — not what was asked for. The two differ exactly when the
  // other mark had to go, which is the case a local toggle would get wrong.
  Future<void> toggleLoved(FoodBrief food) async {
    final wanted = lovedIds.contains(food.id) ? null : FoodMark.loved;
    await _applyMark(food, wanted);
  }

  /// Blocks or unblocks a dish.
  ///
  /// Throws [ApiFailure] with [ApiFailure.blockWouldEmptyMeal] when this is
  /// the last dish left in a role some meal needs. Nothing is changed in that
  /// case, here or on the server, so the caller's switch has to go back.
  ///
  /// **It does not touch today's plan.** Blocking a dish that is already on
  /// the plate leaves it there, and the screen offers to drop or replace it
  /// as a separate action the user can see. The alternative — quietly
  /// skipping or regenerating — would change the day's energy figure from
  /// under a user who only answered a question about future plans.
  Future<void> setNeverAgain(FoodBrief food, bool value) async {
    await _applyMark(food, value ? FoodMark.blocked : null);
  }

  /// The one place any of the three stores is written, so they cannot drift
  /// into disagreeing about what is marked.
  Future<void> _applyMark(FoodBrief food, String? wanted) async {
    final api = _foods;
    final applied = api == null
        ? wanted
        : (await api.setMark(food.id, wanted)).kind;

    lovedIds.remove(food.id);
    neverAgainIds.remove(food.id);
    _markedDishes.remove(food.id);
    switch (applied) {
      case FoodMark.loved:
        lovedIds.add(food.id);
        _markedDishes[food.id] = food.copyWith(mark: FoodMark.loved);
      case FoodMark.blocked:
        neverAgainIds.add(food.id);
        _markedDishes[food.id] = food.copyWith(mark: FoodMark.blocked);
    }
    notifyListeners();
  }

  // ONLINE: GET /foods?mark=… twice, once per list.
  //
  // Read at sign-in rather than when a saved-dishes screen opens: the
  // bookmark is drawn on every dish tile and in the plan, so a list that
  // arrived only on that screen would show every dish unmarked until the
  // user had visited the one screen that fetched it.
  //
  // Twice because `?mark=` takes one value. The alternative — one unfiltered
  // page carrying each row's `mark` — would be four pages of 100 over a
  // 318-dish catalogue, to find what is usually a handful of dishes.
  Future<void> _pullMarks() async {
    final api = _foods;
    if (api == null) return;
    final loved = await api.marked(FoodMark.loved);
    final blocked = await api.marked(FoodMark.blocked);

    lovedIds
      ..clear()
      ..addAll(loved.map((d) => d.id));
    neverAgainIds
      ..clear()
      ..addAll(blocked.map((d) => d.id));
    _markedDishes
      ..clear()
      ..addEntries([
        for (final dish in [...loved, ...blocked]) MapEntry(dish.id, dish),
      ]);
  }

  // ── Settings ─────────────────────────────────────────────────────

  bool _mealReminders = true;
  bool _weeklySummary = false;

  bool get mealReminders => _mealReminders;
  bool get weeklySummary => _weeklySummary;

  set mealReminders(bool value) {
    _mealReminders = value;
    notifyListeners();
  }

  set weeklySummary(bool value) {
    _weeklySummary = value;
    notifyListeners();
  }

  /// Wipes the health profile and everything learned or recorded since, so
  /// the user can answer the questions again. The account itself stays.
  void reset() {
    profile
      ..gender = null
      ..birthday = null
      ..heightCm = null
      ..weightKg = null
      ..targetWeightKg = null
      ..goal = null
      ..activity = null
      ..conditions.clear()
      ..allergies.clear()
      ..severities.clear();
    _preference = null;
    _plans.clear();
    _selectedDay = _dateOnly(DateTime.now());
    diary.clear();
    _weighIns.clear();
    _ownDishes.clear();
    lovedIds.clear();
    neverAgainIds.clear();
    _markedDishes.clear();
    notifyListeners();
  }

  // ── Cold start ───────────────────────────────────────────────────

  SurveyDeck? _surveyDeck;

  /// The deck being swiped, online. `null` offline, and `null` before
  /// [loadSurveyDeck] — the session id in it is what [completeSurvey] needs.
  SurveyDeck? get surveyDeck => _surveyDeck;

  SurveyOutcome? _surveyOutcome;

  /// What the server made of the survey — §7.4.2's answer. `null` offline,
  /// where nothing computes a taste summary.
  SurveyOutcome? get surveyOutcome => _surveyOutcome;

  // ONLINE: GET /onboarding/survey — §7.4.1. The deck is chosen by the ML
  // service: maximum diversity over the feature space, out of the dishes the
  // F1 filter leaves, which is why it cannot be chosen here.
  //
  // OFFLINE: the mock deck, with no session id, because there is nowhere to
  // store a session.
  Future<List<FoodBrief>> loadSurveyDeck() async {
    final api = _surveys;
    if (api == null) {
      _surveyDeck = null;
      return [for (final f in MockFoods.surveyDeck) f.brief];
    }
    final deck = await api.deck();
    _surveyDeck = deck;
    return deck.items;
  }

  /// Takes the swipe session's result and finishes onboarding.
  ///
  // ONLINE: POST /onboarding/survey — §7.4.2. **This is what ends the
  // onboarding flow.** The stamp lives in `users.onboarding_completed_at`
  // and nothing else writes it, so until this call returns, a user who has
  // swiped every card is still a user who has not finished: `welcome_screen`
  // reads that stamp on every launch and would send them back to the survey
  // for good.
  //
  // The preference vector is built server-side by Rocchio (§8.2) and the
  // local [PreferenceProfile] is left alone — it is the offline mode's copy,
  // and two vectors for one user, built from the same swipes by two
  // implementations, is exactly the drift the parity checks exist to stop.
  //
  // OFFLINE: builds that local vector and the first plan, which is the whole
  // cold start when there is no server.
  ///
  /// Throws [ApiFailure] with `ONBOARDING_INSUFFICIENT` when too few swipes
  /// carried an opinion, and `ONBOARDING_ALREADY_COMPLETED` when the account
  /// has already been through this.
  Future<void> completeSurvey(
    List<({FoodBrief food, SwipeAction action})> swipes,
  ) async {
    final api = _surveys;
    final deck = _surveyDeck;
    if (api == null || deck == null) {
      _completeSurveyOffline(swipes);
      return;
    }

    final outcome = await api.submit(
      sessionId: deck.sessionId,
      swipes: [
        for (final s in swipes)
          (foodId: s.food.id, action: s.action.code),
      ],
    );
    _surveyOutcome = outcome;
    _onboardingCompletedAt = outcome.onboardingCompletedAt;
    notifyListeners();
  }

  // OFFLINE: the Dart copy of the cold start — Rocchio over the mock deck,
  // then step 4. Looks each card's dish up again because a card holds no
  // nutrition, and the vector is built from nutrition.
  void _completeSurveyOffline(
    List<({FoodBrief food, SwipeAction action})> swipes,
  ) {
    final byId = {for (final f in MockFoods.surveyDeck) f.id: f};
    final known = <({Food food, SwipeAction action})>[
      for (final s in swipes)
        if (byId[s.food.id] case final dish?) (food: dish, action: s.action),
    ];
    _preference = PreferenceProfile.fromSwipes(space: _space, swipes: known);
    // Offline only — this whole method is — so the builder runs here and
    // now, and the Future it returns is already complete.
    regeneratePlan();
  }

  // ── Meal plan ────────────────────────────────────────────────────

  /// Regenerates the plan for [date], defaulting to the day on screen.
  ///
  /// Returns `false` when the health profile does not hold enough data to
  /// compute the targets — a missing sex, date of birth, height, weight or
  /// activity level.
  // ONLINE: POST /meal-plans with `regenerate: true` — §7.6.2. It DELETES
  // the stored plan for that day and builds a new one, which is why the
  // screen confirms first: a day the user has eaten from would go with it.
  //
  // OFFLINE: the Dart builder, over the same day.
  //
  /// Returns `false` when the health profile does not hold enough data to
  /// compute the targets — a missing sex, date of birth, height, weight or
  /// activity level. Throws [ApiFailure] for anything the server refuses,
  /// including `422 NO_FEASIBLE_PLAN` and `422 RULE_TOO_RESTRICTIVE`: the
  /// two are different answers, and only the second is the user's to change.
  Future<bool> regeneratePlan({DateTime? date}) async {
    final day = _dateOnly(date ?? _selectedDay);
    final api = _mealPlans;
    if (api == null) {
      if (_build(day) == null) return false;
      notifyListeners();
      return true;
    }

    _plans[_dayKey(day)] = await api.generate(day, regenerate: true);
    notifyListeners();
    return true;
  }

  /// Rebuilds one [meal] of the day on screen and keeps the other three.
  ///
  /// Refused while a dish of that meal is marked eaten: it is in the diary,
  /// and replanning around it would delete a record of something that
  /// happened. The screen hides the button then; the check here is for the
  /// offline mode, which has no server to refuse it.
  // ONLINE: POST /meal-plans/{id}/meals/{mealType} — §7.6.2b. The server
  // leaves the meal's current dishes out, so the answer is a different meal
  // and not the same one again, and it answers with the whole day because
  // the day's totals and its ±10 % verdict moved with it.
  //
  // OFFLINE: a fresh day from the Dart builder with every dish already on
  // the plan avoided, of which only this meal is kept. Phase 5 is not rerun
  // over the merged day, so offline the ±10 % is not measured again.
  Future<void> regenerateMeal(MealType meal, {DateTime? date}) async {
    final day = _dateOnly(date ?? _selectedDay);
    final current = _plans[_dayKey(day)];
    if (current == null) return;
    final slot = current.slots.where((s) => s.type == meal).firstOrNull;
    if (slot != null &&
        slot.items.any((i) => i.status == MealItemStatus.eaten)) {
      throw const ApiFailure(
        code: ApiFailure.validationFailed,
        message:
            'Bữa này đã có món được đánh dấu là đã ăn, nên không sinh lại được',
      );
    }

    final api = _mealPlans;
    if (api != null && current.id != null) {
      _plans[_dayKey(day)] = await api.regenerateMeal(current.id!, meal.code);
      notifyListeners();
      return;
    }

    final energy = profile.energyTarget;
    final macro = profile.macroTarget;
    if (energy == null || macro == null || slot == null) return;
    final fresh = _builder(avoid: {for (final i in current.allItems) i.food.id})
        .build(
          date: day,
          targetKcal: energy,
          targetProtein: macro.protein,
          targetCarb: macro.carb,
          targetFat: macro.fat,
        );
    final rebuilt = fresh.slots.where((s) => s.type == meal).firstOrNull;
    if (rebuilt == null) return;
    slot.items
      ..clear()
      ..addAll(rebuilt.items);
    notifyListeners();
  }

  /// Drops the plans that were sized to the old profile and rebuilds the one
  /// on screen. Today is kept once something on it has been eaten: that day
  /// has started, so it stays as built.
  void rebuildUpcomingPlans() {
    final todayKey = _dayKey(DateTime.now());
    final todayStarted =
        todayPlan?.allItems.any((i) => i.status == MealItemStatus.eaten) ??
        false;
    _plans.removeWhere((key, _) => key != todayKey || !todayStarted);
    if (plan == null) _build(_selectedDay);
    notifyListeners();
  }

  /// [avoid] is a soft exclusion for variety: it is dropped when honouring
  /// it would leave too few dishes to fill a day.
  MenuBuilder _builder({Set<String> avoid = const {}}) {
    // The F1 filter, which `MenuBuilder` requires of its caller in so many
    // words: "it has to run **first** and pass in an already-safe dish set".
    // Nothing used to do that. The declared conditions reached the
    // excluded-dishes screen and never the builder, so offline a user with a
    // seafood allergy was served seafood while the card below the plan
    // correctly listed those same dishes as excluded — two screens of one
    // session answering opposite things.
    //
    // An EMPTY day budget on purpose. This filter is about the dishes
    // themselves; a per-day allowance belongs to a day in progress, and
    // reading `dayBudget` here would ask for the plan that is being built.
    // The per-day thresholds reach step 4 through [nutrientTargets] instead,
    // which is phase 5's input — the same split as `ml/f1_filter.py` and
    // `ml/menu_builder.py`.
    final safe = screenDishes(
      foods: candidates,
      conditions: userConditions,
      budget: const DayBudget(),
    ).allowed;
    final allowed = [
      for (final f in safe)
        if (!neverAgainIds.contains(f.id)) f,
    ];
    final varied = [
      for (final f in allowed)
        if (!avoid.contains(f.id)) f,
    ];

    return _builderFor(varied.length >= _minPoolForVariety ? varied : allowed);
  }

  static const _minPoolForVariety = 16;

  MenuBuilder _builderFor(List<Food> pool) => MenuBuilder(
    candidates: pool,
    profile: preference,
    explorationRatio: explorationRatio,
    nutrientTargets: nutrientTargets,
    rng: _rng,
  );

  /// The replacement dishes for one serving, in descending score order.
  // ONLINE: GET /meal-plan-items/{id}/alternatives — §7.6.4. The service
  // scores the candidates and says, for each one, how the day's energy would
  // move and whether it would stay inside ±10 % — figures this side cannot
  // compute, because a serving from §7.6 carries no nutrition.
  //
  // OFFLINE: the Dart builder's own candidate list.
  Future<List<FoodBrief>> alternativesFor(MealPlanItem item) async {
    final api = _mealPlans;
    if (api != null && item.id != null) {
      return [for (final a in await api.alternatives(item.id!)) a.food];
    }

    final plan = this.plan;
    final exclude = plan == null
        ? <String>{}
        : plan.allItems.map((i) => i.food.id).toSet();
    return [
      for (final food in _builder().alternativesFor(item, excludeIds: exclude))
        food.brief,
    ];
  }

  /// What this serving could be swapped for, from whichever side can say.
  ///
  /// One list for one sheet. See [ReplaceOption] for why each source fills a
  /// different half of it and neither half is invented for the other.
  Future<List<ReplaceOption>> replaceOptions(MealPlanItem item) async {
    final api = _mealPlans;
    if (api != null && item.id != null) {
      return [
        for (final a in await api.alternatives(item.id!))
          ReplaceOption(
            food: a.food,
            score: a.predictedScore,
            deltaKcal: a.calorieDeltaKcal,
            keepsWithinTolerance: a.keepsWithinTolerance,
          ),
      ];
    }

    final plan = this.plan;
    final exclude = plan == null
        ? <String>{}
        : plan.allItems.map((i) => i.food.id).toSet();
    return [
      for (final dish in _builder().alternativesFor(item, excludeIds: exclude))
        ReplaceOption(
          food: dish.brief,
          dish: dish,
          score: preference.score(dish),
        ),
    ];
  }

  /// Swaps one serving for another dish.
  ///
  /// This action produces **two** training signals at once: the dropped dish
  /// takes the `plan_replaced` label (0.15), the chosen dish takes
  /// `plan_kept` (0.70). It is the main source of data once the swipe session
  /// is over.
  // ONLINE: PUT /meal-plan-items/{id}/replace — §7.6.5, which answers with
  // the whole day: the swap moves the day's totals and its ±10 % verdict, so
  // a response about one serving would leave this side to recompute figures
  // it cannot.
  //
  // OFFLINE: the swap in memory, keeping the old serving as a `replaced` row
  // for the same reason the server does.
  Future<void> replaceItem(MealPlanItem item, FoodBrief replacement) async {
    final api = _mealPlans;
    if (api != null && item.id != null) {
      final day = _dateOnly(_selectedDay);
      _plans[_dayKey(day)] = await api.replace(item.id!, replacement.id);
      notifyListeners();
      return;
    }
    _replaceItemOffline(item, replacement);
  }

  // OFFLINE: the Dart copy. Looks the dish up again because a brief carries
  // no nutrition, and the local scoring needs it.
  void _replaceItemOffline(MealPlanItem item, FoodBrief replacement) {
    final plan = this.plan;
    if (plan == null) return;
    final dish = MockFoods.surveyDeck
        .where((f) => f.id == replacement.id)
        .firstOrNull;
    if (dish == null) return;

    for (final slot in plan.slots) {
      final index = slot.items.indexOf(item);
      if (index < 0) continue;

      slot.items[index] = item.copyWith(status: MealItemStatus.replaced);
      slot.items.insert(
        index,
        MealPlanItem.offline(
          dish: dish,
          score: preference.score(dish),
          explorationDelta: item.explorationDelta,
        ),
      );
      // The old serving is kept only to record the signal; it is no longer
      // displayed.
      slot.items.removeAt(index + 1);
      notifyListeners();
      return;
    }
  }

  /// Marks a planned item as skipped (eating out, not hungry…), or puts a
  /// skipped one back. A weak training signal: the reason may have nothing to
  /// do with taste.
  // ONLINE: PATCH /meal-plan-items/{id}/status — §7.6.6.
  //
  // OFFLINE: the status on the serving in memory.
  //
  // Putting a skipped serving back sends `kept`, not `suggested`: §7.6.6
  // accepts only the three a CLIENT may set, and `suggested` is what the
  // system writes when it generates a plan. §4.6 reads the difference —
  // `kept` is the user having looked at a suggestion and left it, which is a
  // weak positive, while `suggested` is nobody having said anything yet.
  Future<void> setSkipped(MealPlanItem item, bool skipped) async {
    final to = skipped ? MealItemStatus.skipped : MealItemStatus.kept;
    if (skipped && item.status == MealItemStatus.skipped) return;
    if (!skipped && item.status != MealItemStatus.skipped) return;

    await _setItemStatus(item, to);
  }

  /// Marks a serving as eaten.
  ///
  // ONLINE: PATCH /meal-plan-items/{id}/status with `eaten` — §7.6.6, which
  // writes the `food_diary` entry **in the same request**. Two calls would
  // leave a window where the plan says eaten and the diary does not, and
  // every compliance figure in the report reads both.
  //
  // OFFLINE: [logMeal], which writes the local diary and the status together
  // for the same reason.
  ///
  /// Returns the diary entry's id when the server created one, so a screen
  /// can send the user on to rate the dish. `null` offline, and `null` on a
  /// repeat — the entry already exists, and a second one would count the
  /// meal twice.
  Future<String?> markEaten(MealPlanItem item, MealType meal) async {
    final api = _mealPlans;
    if (api == null || item.id == null) {
      final dish = item.dish;
      if (dish == null) return null;
      logMeal(food: dish, meal: meal);
      return null;
    }

    final result = await api.setStatus(item.id!, MealItemStatus.eaten.code);
    _applyItemStatus(item, MealItemStatus.eaten);
    return result.diaryEntryCreated ? result.diaryEntryId : null;
  }

  Future<void> _setItemStatus(MealPlanItem item, MealItemStatus to) async {
    final api = _mealPlans;
    if (api != null && item.id != null) {
      await api.setStatus(item.id!, to.code);
    }
    _applyItemStatus(item, to);
  }

  /// Writes the status onto the cached serving, after the server agreed to
  /// it — or at once, offline, where this side is the store.
  void _applyItemStatus(MealPlanItem item, MealItemStatus to) {
    for (final slot in plan?.slots ?? const <MealSlot>[]) {
      final index = slot.items.indexOf(item);
      if (index < 0) continue;
      slot.items[index] = item.copyWith(status: to);
      notifyListeners();
      return;
    }
  }

  // ── Browsing the catalogue ───────────────────────────────────────

  List<FoodCategory>? _categories;

  /// The food groups the browse screen filters by.
  // ONLINE: GET /food-categories — §7.3.3, asked once per session: a
  // dictionary that changes only when the catalogue is re-imported.
  //
  // OFFLINE: the groups the mock dishes carry. The mock has no ids, so the
  // name stands in for one and [searchFoods] compares names.
  Future<List<FoodCategory>> foodCategories() async {
    final cached = _categories;
    if (cached != null) return cached;
    final api = _foods;
    final loaded = api != null
        ? await api.categories()
        : [
            for (final name in {for (final f in candidates) f.category})
              FoodCategory(id: name, name: name),
          ];
    loaded.sort((a, b) => a.name.compareTo(b.name));
    return _categories = loaded;
  }

  /// One page of the catalogue matching [query].
  // ONLINE: GET /foods — §7.5.1, all six filters plus `excludeUnsafe`.
  //
  // OFFLINE: the same filters over the mock dishes, in one page. "Fits the
  // meal" is read off the meal structure step 4 builds with, and "safe" off
  // the same F1 screening the plan uses.
  Future<FoodPage> searchFoods(FoodQuery query, {int page = 1}) async {
    final api = _foods;
    if (api != null) {
      return api.search(
        query: query.text,
        categoryId: query.categoryId,
        mealType: query.meal?.code,
        dishRole: query.role?.code,
        maxCalories: query.maxKcal,
        mark: query.mark,
        excludeUnsafe: query.safeOnly,
        page: page,
      );
    }

    final text = foldVietnamese(query.text.trim());
    final roles = query.meal == null ? null : mealRolesOf(query.meal!);
    final safe = {
      for (final f in screenDishes(
        foods: candidates,
        conditions: userConditions,
        budget: const DayBudget(),
      ).allowed)
        f.id,
    };
    final items = <FoodBrief>[];
    for (final f in [...candidates, ..._ownDishes]) {
      final mark = lovedIds.contains(f.id)
          ? FoodMark.loved
          : neverAgainIds.contains(f.id)
          ? FoodMark.blocked
          : null;
      final isSafe = safe.contains(f.id);
      if (text.isNotEmpty && !foldVietnamese(f.name).contains(text)) continue;
      if (query.categoryId != null && f.category != query.categoryId) {
        continue;
      }
      if (roles != null && !roles.contains(f.dishRole)) continue;
      if (query.role != null &&
          f.dishRole != query.role!.code &&
          f.dishRole != query.role!.label) {
        continue;
      }
      if (query.maxKcal != null && f.kcal > query.maxKcal!) continue;
      if (query.mark != null && mark != query.mark) continue;
      if (query.safeOnly && !isSafe) continue;
      items.add(f.brief.copyWith(mark: mark, isSafeForUser: isSafe));
    }
    items.sort((a, b) => a.name.compareTo(b.name));
    return FoodPage(
      items: items,
      page: 1,
      pageSize: items.length,
      totalItems: items.length,
      totalPages: items.isEmpty ? 0 : 1,
    );
  }

  // ── Dishes of one's own ──────────────────────────────────────────

  /// OFFLINE: the dishes added in this session. Searchable and loggable,
  /// never suggested — the offline menu builder draws from [candidates]
  /// only, the way the server's own scale is drawn from the shared catalogue.
  final List<Food> _ownDishes = [];

  List<FoodTag>? _ownDishTags;

  // ONLINE: GET /tags, narrowed to what §7.5.3 accepts.
  //
  // OFFLINE: none — the mock has no tag ids to send.
  /// The allergen and diet tags a dish of one's own may carry.
  Future<List<FoodTag>> ownDishTags() async {
    final cached = _ownDishTags;
    if (cached != null) return cached;
    final api = _foods;
    if (api == null) return _ownDishTags = const [];
    final all = await api.tags();
    return _ownDishTags = [
      for (final t in all)
        if (t.tagType == 'allergen' || t.tagType == 'diet') t,
    ];
  }

  // ONLINE: POST /foods — §7.5.3.
  //
  // OFFLINE: kept in memory. A nutrient left blank is stored as 0 here only
  // because the offline [Food] has no nullable slot for it; it is never
  // screened or suggested, so the 0 is never read as a claim.
  /// Adds a dish only this user sees, and returns it ready to log.
  Future<FoodBrief> addOwnDish(OwnDishDraft draft) async {
    final api = _foods;
    if (api != null) {
      final created = await api.create(draft);
      return created.brief;
    }

    final name = draft.name.trim();
    final taken = _ownDishes.any(
      (f) => foldVietnamese(f.name) == foldVietnamese(name),
    );
    if (taken) {
      throw const ApiFailure(
        status: 409,
        code: ApiFailure.foodAlreadyExists,
        message: 'Bạn đã có một món riêng trùng tên',
      );
    }
    final dish = Food(
      id: 'own-${_ownDishes.length + 1}',
      name: name,
      category: draft.categoryId,
      dishRole: draft.dishRole,
      spiceLevel: draft.spiceLevel,
      kcal: draft.kcal.round(),
      protein: draft.proteinG ?? 0,
      carb: draft.carbsG ?? 0,
      fat: draft.fatG ?? 0,
      sugar: draft.sugarG ?? 0,
      sodium: draft.sodiumMg ?? 0,
      fiber: draft.fiberG ?? 0,
      purine: draft.purineMg,
      servingSizeG: draft.servingSizeG.toDouble(),
      emoji: '🍲',
      gradient: const [Color(0xFFE2F8FD), Color(0xFFB8EEF8)],
    );
    _ownDishes.add(dish);
    notifyListeners();
    return dish.brief.copyWith(isSafeForUser: false);
  }

  // ── The day's allowance, and dish screening ──────────────────────

  /// The conditions the user declared, as a rule set the code understands.
  List<UserCondition> get userConditions =>
      conditionsFromCodes(profile.conditions);

  /// The dishes **already eaten** today — from the diary.
  ///
  /// The diary is the single source for the eaten part. A serving carrying
  /// the `eaten` status is NOT added on top: [logMeal] writes to both places
  /// at once, so counting both would count the same serving twice.
  List<Food> get eatenToday {
    // The day on screen, which is today unless the week strip moved it.
    final today = _selectedDay;
    return [
      for (final e in activeDiary)
        if (e.ateAt.year == today.year &&
            e.ateAt.month == today.month &&
            e.ateAt.day == today.day)
          // `dish` and not `food`: the allowance is arithmetic over whole
          // nutrition rows. Online these lines come from §7.7.1 with none,
          // and the day's figures come from §7.7.5 instead.
          ?e.dish,
    ];
  }

  /// The dishes **in the plan** but not eaten yet.
  ///
  /// Kept apart from [eatenToday] rather than merged: when a dish does not
  /// fit the allowance, the user is choosing between *dropping something
  /// already planned* and *going over*. A single total would make them think
  /// both parts were fixed.
  List<Food> get plannedToday => [
    for (final item in plan?.allItems ?? const <MealPlanItem>[])
      // `dish` and not `food`: the day's allowance is arithmetic over whole
      // nutrition rows, which only an offline serving carries. Online the
      // allowance comes from §7.7.5 and this list is empty.
      if (item.status == MealItemStatus.suggested && item.dish != null)
        item.dish!,
  ];

  // ONLINE: GET /foods/{id} — §7.5.2, the only answer carrying a dish's
  // whole nutrition row.
  //
  // OFFLINE: the mock dish of the same id, adapted. Its micronutrients come
  // back null rather than 0, because the mock does not hold them either.
  //
  // The brief is passed in and not just an id: it is what the list already
  // knew, so the screen can draw the name and the picture while this is in
  // flight instead of showing a spinner over everything.
  Future<FoodDetail> dishDetail(FoodBrief dish) async {
    final api = _foods;
    if (api != null) return api.detail(dish.id);

    for (final food in MockFoods.surveyDeck) {
      if (food.id == dish.id) return food.detail;
    }
    throw ApiFailure(
      code: ApiFailure.notFound,
      message: 'Không tìm thấy món ${dish.name}',
    );
  }

  /// How well a dish fits this user's taste, 0 to 1, or `null` when there is
  /// no answer to give.
  ///
  /// `null` happens in two ways and both are honest. Before any swipe the
  /// vector is empty, so every dish would score the same and a percentage
  /// would be noise dressed as a measurement. And online there is no local
  /// vector at all — Rocchio runs in the ML service and no endpoint scores a
  /// single dish — so the screen drops the figure rather than inventing one.
  // OFFLINE: the Dart copy of step 3, over the mock catalogue.
  double? scoreOf(FoodBrief dish) {
    if (_preference == null) return null;
    for (final food in MockFoods.surveyDeck) {
      if (food.id == dish.id) return _preference!.score(food);
    }
    return null;
  }

  /// The serving of the dish still on the plate for the day on screen, or
  /// `null` if there is none.
  ///
  /// `suggested` only: an `eaten` serving is already in the diary and cannot
  /// be taken back off the day, and a `skipped` one is off it already. Used
  /// by the detail screen to ask what to do with a serving of a dish the
  /// user has just blocked, rather than deciding for them.
  MealPlanItem? plannedTodayItem(FoodBrief dish) {
    for (final item in plan?.allItems ?? const <MealPlanItem>[]) {
      if (item.food.id == dish.id &&
          item.status == MealItemStatus.suggested) {
        return item;
      }
    }
    return null;
  }

  /// Today's allowances, with the used part already subtracted.
  DayBudget get dayBudget => DayBudget.from(
    thresholds: dayThresholdsFor(userConditions),
    eaten: eatenToday,
    planned: plannedToday,
  );

  /// Screens the whole catalogue against the conditions and the remaining
  /// allowance.
  ///
  /// Recomputing on every call is deliberate: the allowance depends on what
  /// has been eaten today, so a remembered result would be wrong immediately
  /// after the next diary entry — and wrong in the direction of being too
  /// permissive.
  ScreeningResult get screening => screenDishes(
    foods: candidates,
    conditions: userConditions,
    budget: dayBudget,
    softRules: softRulesFor(userConditions),
  );

  // ── Diary ────────────────────────────────────────────────────────

  /// Records a dish that was eaten.
  void logMeal({
    required Food food,
    required MealType meal,
    double portion = 1.0,
    DateTime? at,
  }) {
    final ateAt = at ?? DateTime.now();

    // Mark the matching serving in the plan as eaten, if there is one. Joined
    // on the natural key (meal, dish) rather than on a foreign key.
    //
    // Done BEFORE the line is written, because whether a serving was found
    // is what `fromMealPlan` means — and that is what words the undo: "trả
    // về thực đơn" for a serving that came from the plan, "bỏ khỏi nhật ký"
    // for a dish eaten elsewhere. It used to default to false, so every
    // offline line claimed to be the second kind.
    var fromPlan = false;
    final slot = planOn(ateAt)?.slots.where((s) => s.type == meal).firstOrNull;
    if (slot != null) {
      for (var i = 0; i < slot.items.length; i++) {
        if (slot.items[i].food.id == food.id &&
            slot.items[i].status == MealItemStatus.suggested) {
          slot.items[i] = slot.items[i].copyWith(status: MealItemStatus.eaten);
          fromPlan = true;
          break;
        }
      }
    }

    diary.add(
      DiaryEntry.offline(
        dish: food,
        meal: meal,
        ateAt: ateAt,
        portion: portion,
        fromMealPlan: fromPlan,
      ),
    );

    notifyListeners();
  }

  /// The diary entries that still count: everything not undone.
  Iterable<DiaryEntry> get activeDiary => diary.where((e) => !e.isUndone);

  /// Takes back "I ate this": the serving returns to the plan as not eaten
  /// yet, and the entry stops counting towards the day.
  ///
  /// The entry is **kept** in [diary] and only marked — the log is a record
  /// of what the user did, and a mistaken tap is part of that record.
  // ONLINE: DELETE /food-diary/{id} — §7.7.4. **Two deletes in one
  // endpoint, and the server decides which**: it looks up whether the dish
  // was in that day's plan for that meal, and if it was, the serving goes
  // back on the plate as `suggested`. No parameter chooses it, which is
  // right — this side would have to work the answer out from data it does
  // not hold, and two clients could then disagree about what a delete means.
  //
  // `entry.fromMealPlan` is for WORDING the confirmation, not for choosing
  // the behaviour. And §7.7.4 refuses a line a rating has locked, which is
  // why `entry.editable` exists: the screen hides the button rather than
  // letting the user press it and read an error.
  //
  // OFFLINE: the line stays in the log and stops counting. The log is a
  // health record, so nothing is erased from it here.
  Future<void> undoMeal(DiaryEntry entry) async {
    final api = _diary;
    if (api != null && entry.id != null) {
      await api.remove(entry.id!);
      diary.removeWhere((e) => e.id == entry.id);
      // The serving the server just put back, and the day's figures with it.
      _plans.remove(_dayKey(entry.ateAt));
      await loadPlan(date: entry.ateAt);
      notifyListeners();
      return;
    }

    if (entry.isUndone) return;
    entry.undoneAt = DateTime.now();

    // The reverse of the join in [logMeal].
    final slot = planOn(entry.ateAt)?.slots
        .where((s) => s.type == entry.meal)
        .firstOrNull;
    if (slot != null) {
      for (var i = 0; i < slot.items.length; i++) {
        if (slot.items[i].food.id == entry.food.id &&
            slot.items[i].status == MealItemStatus.eaten) {
          slot.items[i] = slot.items[i].copyWith(
            status: MealItemStatus.suggested,
          );
          break;
        }
      }
    }

    notifyListeners();
  }

  /// Rates a dish after eating it — the strongest signal source.
  ///
  // ONLINE: POST /feedbacks — §7.8.1.
  //
  // **It locks the diary line.** From here on §7.7.3 and §7.7.4 refuse the
  // line this rating could be the evidence for, so the whole line is read
  // back afterwards: `editable` has to turn false here, or the screen keeps
  // offering an edit the server will refuse.
  //
  // Rating again is allowed and writes a NEW row rather than overwriting —
  // taste changes, and both answers are kept.
  //
  // OFFLINE: the stars on the line in memory.
  ///
  /// Throws [ApiFailure] with `FEEDBACK_NOT_ALLOWED` when the dish was never
  /// in one of this user's plans **and** in their diary. The screen should
  /// not reach that: a line of the diary satisfies the second half, and the
  /// first is what §7.8.1 checks for a dish logged from outside the plan.
  Future<void> rate(DiaryEntry entry, int stars) async {
    final clamped = stars.clamp(1, 5);
    final api = _feedback;
    if (api == null) {
      entry.rating = clamped;
      notifyListeners();
      return;
    }

    await api.rate(foodId: entry.food.id, rating: clamped);

    // Read the line back rather than patching it here. The rating changed
    // `editable` on the server's side of the rule, and inventing that flag
    // on this side would be a second implementation of the lock.
    await ensureDiaryCovers(entry.ateAt, force: true);
  }

  // ONLINE: GET /food-diary?from=&to= — §7.7.1. Only the days with
  // something in them come back.
  //
  // OFFLINE: the in-memory log is already the answer.
  Future<void> loadDiary({DateTime? from, DateTime? to}) async {
    final api = _diary;
    if (api == null) return;

    final end = _dateOnly(to ?? DateTime.now());
    final start = _dateOnly(from ?? end.subtract(const Duration(days: 29)));
    final days = await api.range(from: start, to: end);
    _diaryFrom = start;

    // Replaced rather than merged: §7.7.1 is the record, and a line deleted
    // on another device has to disappear here too. Merging would keep it.
    diary
      ..clear()
      ..addAll([
        for (final day in days)
          for (final line in day.lines) DiaryEntry.fromLine(line, on: day.date),
      ]);
    notifyListeners();
  }

  // ONLINE: POST /food-diary — §7.7.2, a dish eaten OUTSIDE the plan.
  //
  // The plan is the menu the system proposes and the diary is what the person
  // actually ate, so a dish bought elsewhere belongs here and not in the
  // plan — a diner does not write on the restaurant's menu.
  //
  // The F1 filter is deliberately not applied: a log records what happened,
  // including a dish the user should not have eaten. Refusing it would leave
  // their doctor's figures missing the one meal that mattered.
  //
  // OFFLINE: [logMeal], which is the same act against the in-memory log.
  Future<void> addEaten({
    required FoodBrief food,
    required MealType meal,
    DateTime? ateOn,
    int? servingSizeG,
  }) async {
    final api = _diary;
    final day = _dateOnly(ateOn ?? DateTime.now());
    if (api == null) {
      final dish = [
        ...MockFoods.surveyDeck,
        ..._ownDishes,
      ].where((f) => f.id == food.id).firstOrNull;
      if (dish == null) return;
      // Today keeps the real time; a past day has none to give, and
      // midnight would read as a meal eaten at 00:00.
      final now = DateTime.now();
      logMeal(
        food: dish,
        meal: meal,
        at: _dayKey(day) == _dayKey(now) ? now : day.add(_noon),
        portion: servingSizeG == null || dish.servingSizeG <= 0
            ? 1.0
            : servingSizeG / dish.servingSizeG,
      );
      return;
    }

    final line = await api.add(
      foodId: food.id,
      ateOn: day,
      mealType: meal.code,
      servingSizeG: servingSizeG,
    );
    diary.add(DiaryEntry.fromLine(line, on: day));
    notifyListeners();
  }

  static const _noon = Duration(hours: 12);

  // ONLINE: PUT /food-diary/{id} — §7.7.3. Only the meal and the portion can
  // change: a different dish or a different day is a different eating, and
  // changing those in place would move an existing rating onto a dish the
  // user never said anything about.
  Future<void> editEaten(
    DiaryEntry entry, {
    MealType? meal,
    int? servingSizeG,
  }) async {
    final api = _diary;
    if (api == null || entry.id == null) {
      _editEatenOffline(entry, meal: meal, servingSizeG: servingSizeG);
      return;
    }

    final line = await api.update(
      entry.id!,
      mealType: meal?.code,
      servingSizeG: servingSizeG,
    );
    final index = diary.indexWhere((e) => e.id == entry.id);
    if (index >= 0) diary[index] = DiaryEntry.fromLine(line, on: entry.ateAt);
    // Moving a line to another meal moves which serving of the plan it
    // matches, so the day's plan is read again rather than patched here.
    if (meal != null && meal != entry.meal) {
      _plans.remove(_dayKey(entry.ateAt));
      await loadPlan(date: entry.ateAt);
    }
    notifyListeners();
  }

  /// The offline [editEaten]. The line is replaced, keeping its time and
  /// its rating, and a move to another meal re-runs the plan join of
  /// [logMeal]: the serving it was matched to goes back to waiting, and one
  /// in the new meal is ticked if there is one.
  void _editEatenOffline(
    DiaryEntry entry, {
    MealType? meal,
    int? servingSizeG,
  }) {
    final dish = entry.dish;
    final index = diary.indexOf(entry);
    if (dish == null || index < 0) return;

    final to = meal ?? entry.meal;
    var fromPlan = entry.fromMealPlan;
    if (to != entry.meal) {
      if (entry.fromMealPlan) {
        _moveServing(
          entry.ateAt,
          entry.meal,
          dish.id,
          from: MealItemStatus.eaten,
          to: MealItemStatus.suggested,
        );
      }
      fromPlan = _moveServing(
        entry.ateAt,
        to,
        dish.id,
        from: MealItemStatus.suggested,
        to: MealItemStatus.eaten,
      );
    }

    diary[index] = DiaryEntry.offline(
      dish: dish,
      meal: to,
      ateAt: entry.ateAt,
      portion: servingSizeG == null || dish.servingSizeG <= 0
          ? entry.portion
          : servingSizeG / dish.servingSizeG,
      rating: entry.rating,
      fromMealPlan: fromPlan,
    );
    notifyListeners();
  }

  /// Moves the first serving of [foodId] in [meal] on [day] from one status
  /// to another. Whether one was found.
  bool _moveServing(
    DateTime day,
    MealType meal,
    String foodId, {
    required MealItemStatus from,
    required MealItemStatus to,
  }) {
    final slot = planOn(day)?.slots.where((s) => s.type == meal).firstOrNull;
    if (slot == null) return false;
    for (var i = 0; i < slot.items.length; i++) {
      if (slot.items[i].food.id == foodId && slot.items[i].status == from) {
        slot.items[i] = slot.items[i].copyWith(status: to);
        return true;
      }
    }
    return false;
  }

  /// The first day the diary has been read from, online. `null` before the
  /// first read.
  DateTime? _diaryFrom;

  /// Reads the diary back as far as [day] if it does not reach that far yet.
  ///
  /// [loadDiary] reads the last thirty days, so a day picked further back
  /// from the calendar has to widen the window first. It is widened to
  /// [day] and never narrowed: the screen may step back again a day later.
  /// [force] reloads even when the range already covers [day].
  ///
  /// Needed after a rating: §7.8.1 flips `editable` on the line it locked,
  /// and that flag lives on the server's side of the rule. Without a reload
  /// the screen would keep offering an edit the next request would refuse.
  Future<void> ensureDiaryCovers(DateTime day, {bool force = false}) async {
    if (_diary == null) return;
    final from = _diaryFrom;
    if (!force && from != null && !_dateOnly(day).isBefore(from)) return;
    await loadDiary(from: from != null && from.isBefore(day) ? from : day);
  }

  // ONLINE: GET /food-diary/summary?date= — §7.7.5, the day against the
  // limits that applied ON THAT DAY: the snapshot stored with the plan when
  // there was one, and the profile's columns otherwise. Read, never
  // recomputed — recomputing would invent a new answer for a past day, the
  // day the user weighed three kilograms more.
  //
  // `null` offline, where [dayBudget] is the equivalent and is computed from
  // the dishes in hand.
  Future<DaySummary?> daySummary({DateTime? date}) async {
    final api = _diary;
    if (api == null) return null;
    return api.summary(_dateOnly(date ?? _selectedDay));
  }

  // ── Weight and progress ──────────────────────────────────────────

  /// OFFLINE: the weighings, one per day, keyed like [_plans].
  final Map<int, WeightPoint> _weighIns = {};

  // ONLINE: POST /body-logs — §7.10.1. Then the profile and its targets are
  // read back, because the server recomputes step 1 from the new weight and
  // the app's copy would otherwise go on showing the old limit.
  //
  // OFFLINE: kept in memory. The profile takes the weight only when no later
  // weighing exists, the same rule as the server's: filling in a forgotten
  // day must not set the current weight to last week's.
  //
  // Either way the plans already built keep their targets. Today's plan has
  // been partly eaten from, and §7.10.1 says it does not change.
  /// Records a weighing; [on] defaults to today. Returns whether it became
  /// the current weight.
  Future<bool> logWeight(double kg, {DateTime? on, String? note}) async {
    final day = _dateOnly(on ?? DateTime.now());
    final api = _progress;
    if (api != null) {
      final result = await api.logWeight(kg, on: day, note: note);
      if (result.profileUpdated) {
        final profiles = _profiles!;
        (await profiles.read()).applyTo(profile);
        (await profiles.targets()).applyTo(profile);
      }
      notifyListeners();
      return result.profileUpdated;
    }

    _weighIns[_dayKey(day)] = WeightPoint(date: day, weightKg: kg);
    final latest = _weighIns.values
        .map((w) => w.date)
        .reduce((a, b) => a.isAfter(b) ? a : b);
    final current = !latest.isAfter(day);
    if (current) profile.weightKg = kg;
    notifyListeners();
    return current;
  }

  // ONLINE: GET /stats/progress — §7.9.1.
  //
  // OFFLINE: the same arithmetic over the diary and plans in memory, so the
  // screen can be walked through without a server. Like the server's, the
  // means are over the days something was logged, and compliance is pooled
  // over the servings rather than averaged over the days.
  /// The last [days] days, today included.
  Future<ProgressReport> progress({int days = 7, bool byWeek = false}) async {
    final to = _dateOnly(DateTime.now());
    final from = to.subtract(Duration(days: days - 1));
    final api = _progress;
    if (api != null) {
      return api.progress(from: from, to: to, byWeek: byWeek);
    }
    return _progressOffline(from, to);
  }

  ProgressReport _progressOffline(DateTime from, DateTime to) {
    final series = <ProgressPoint>[];
    var hit = 0;
    var suggested = 0;
    for (var d = from; !d.isAfter(to); d = d.add(const Duration(days: 1))) {
      final day = _dateOnly(d);
      final lines = entriesOn(day);
      final plan = planOn(day);
      if (lines.isEmpty && plan == null) continue;

      final eaten = {for (final e in lines) (e.meal, e.food.id)};
      int? daySuggested;
      var dayHit = 0;
      if (plan != null) {
        daySuggested = 0;
        for (final slot in plan.slots) {
          for (final item in slot.items) {
            daySuggested = daySuggested! + 1;
            if (eaten.contains((slot.type, item.food.id))) dayHit++;
          }
        }
        hit += dayHit;
        suggested += daySuggested!;
      }

      series.add(
        ProgressPoint(
          date: day,
          consumedKcal: lines.fold(0.0, (s, e) => s + e.kcal),
          targetKcal: plan?.targetKcal ?? profile.energyTarget,
          compliancePct: daySuggested == null || daySuggested == 0
              ? null
              : 100 * dayHit / daySuggested,
          loggedMeals: {for (final e in lines) e.meal}.length,
        ),
      );
    }

    final logged = series.where((p) => p.logged).toList();
    final targeted = logged.where((p) => p.targetKcal != null).toList();
    double? mean(Iterable<double> xs) =>
        xs.isEmpty ? null : xs.reduce((a, b) => a + b) / xs.length;
    final eatenMean = mean(targeted.map((p) => p.consumedKcal));
    final targetMean = mean(targeted.map((p) => p.targetKcal!));

    return ProgressReport(
      from: from,
      to: to,
      series: series,
      summary: ProgressSummary(
        daysLogged: logged.length,
        daysInRange: to.difference(from).inDays + 1,
        avgConsumedKcal: mean(logged.map((p) => p.consumedKcal)),
        avgTargetKcal: targetMean,
        avgCompliancePct: suggested == 0 ? null : 100 * hit / suggested,
        avgDeviationPct:
            eatenMean == null || targetMean == null || targetMean <= 0
            ? null
            : 100 * (eatenMean - targetMean) / targetMean,
        // Offline keeps no rating time, so the meal's day stands in for it.
        totalFeedbacks: activeDiary
            .where(
              (e) =>
                  e.rating != null &&
                  !e.ateAt.isBefore(from) &&
                  e.ateAt.isBefore(to.add(const Duration(days: 1))),
            )
            .length,
      ),
      weightTrend:
          _weighIns.values
              .where((w) => !w.date.isBefore(from) && !w.date.isAfter(to))
              .toList()
            ..sort((a, b) => a.date.compareTo(b.date)),
    );
  }

  // ── Aggregate figures ────────────────────────────────────────────

  List<DiaryEntry> entriesOn(DateTime day) => activeDiary
      .where(
        (e) =>
            e.ateAt.year == day.year &&
            e.ateAt.month == day.month &&
            e.ateAt.day == day.day,
      )
      .toList();

  /// The energy taken in on one day.
  double consumedKcalOn(DateTime day) =>
      entriesOn(day).fold(0, (sum, e) => sum + e.kcal);

  /// The plan adherence rate: what share of the suggested servings were
  /// actually eaten.
  ///
  /// This is one of the project's key acceptance figures — however good the
  /// recommendations are, they mean nothing if the user does not eat them.
  double get adherenceRate {
    final plan = todayPlan;
    if (plan == null || plan.allItems.isEmpty) return 0;

    final eaten = plan.allItems
        .where((i) => i.status == MealItemStatus.eaten)
        .length;
    return eaten / plan.allItems.length;
  }

  /// The total number of signals accumulated, used for the blending factor α
  /// between the two stages.
  int get signalCount =>
      preference.signalCount +
      activeDiary.length +
      activeDiary.where((e) => e.rating != null).length;

  /// The blending factor α between the machine learning score and the content
  /// similarity score.
  ///
  /// ```text
  ///       ⎧ 0                                if n < n_min
  ///   α = ⎨ (n − n_min) / (n_max − n_min)    if n_min ≤ n ≤ n_max
  ///       ⎩ 1                                if n > n_max
  /// ```
  ///
  /// The mock has no machine learning model yet, so α is only used to show
  /// the user a progress figure for "how well the system understands you".
  double get mlBlendFactor {
    const nMin = 30;
    const nMax = 100;
    final n = signalCount;
    if (n < nMin) return 0;
    if (n > nMax) return 1;
    return (n - nMin) / (nMax - nMin);
  }
}

/// Supplies [AppSession] to the whole widget tree and rebuilds the dependent
/// parts when it changes. An [InheritedNotifier] rather than another state
/// management package — this app has only one single source of state.
class SessionScope extends InheritedNotifier<AppSession> {
  const SessionScope({
    super.key,
    required AppSession session,
    required super.child,
  }) : super(notifier: session);

  static AppSession of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<SessionScope>();
    assert(scope != null, 'No SessionScope found above this widget');
    return scope!.notifier!;
  }
}
