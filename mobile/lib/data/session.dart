import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'api/api_client.dart';
import 'api/api_config.dart';
import 'api/failure.dart';
import 'api/auth_api.dart';
import 'api/food_api.dart';
import 'api/profile_api.dart';
import 'api/survey_api.dart';
import 'mock/mock_foods.dart';
import 'mock/mock_rules.dart';
import 'models/diary_entry.dart';
import 'models/food.dart';
import 'models/candidate_count.dart';
import 'models/food_adapters.dart';
import 'models/food_brief.dart';
import 'models/food_detail.dart';
import 'models/health_profile.dart';
import 'models/meal_plan.dart';
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
    }
  }

  final math.Random _rng;

  // ── Which of the two modes ───────────────────────────────────────

  final ApiClient? _client;
  AuthApi? _auth;
  ProfileApi? _profiles;
  FoodApi? _foods;
  SurveyApi? _surveys;

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

  /// Switches the plan screen to [day], building that day's plan on first
  /// visit.
  void selectDay(DateTime day) {
    _selectedDay = _dateOnly(day);
    if (plan == null) _build(_selectedDay);
    notifyListeners();
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
    regeneratePlan();
  }

  // ── Meal plan ────────────────────────────────────────────────────

  /// Regenerates the plan for [date], defaulting to the day on screen.
  ///
  /// Returns `false` when the health profile does not hold enough data to
  /// compute the targets — a missing sex, date of birth, height, weight or
  /// activity level.
  bool regeneratePlan({DateTime? date}) {
    if (_build(_dateOnly(date ?? _selectedDay)) == null) return false;
    notifyListeners();
    return true;
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
  List<Food> alternativesFor(MealPlanItem item) {
    final plan = this.plan;
    final exclude = plan == null
        ? <String>{}
        : plan.allItems.map((i) => i.food.id).toSet();

    return _builder().alternativesFor(item, excludeIds: exclude);
  }

  /// Swaps one serving for another dish.
  ///
  /// This action produces **two** training signals at once: the dropped dish
  /// takes the `plan_replaced` label (0.15), the chosen dish takes
  /// `plan_kept` (0.70). It is the main source of data once the swipe session
  /// is over.
  void replaceItem(MealPlanItem item, Food replacement) {
    final plan = this.plan;
    if (plan == null) return;

    for (final slot in plan.slots) {
      final index = slot.items.indexOf(item);
      if (index < 0) continue;

      slot.items[index] = item.copyWith(status: MealItemStatus.replaced);
      slot.items.insert(
        index,
        MealPlanItem(
          food: replacement,
          score: preference.score(replacement),
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
  void setSkipped(MealPlanItem item, bool skipped) {
    final from = skipped ? MealItemStatus.suggested : MealItemStatus.skipped;
    final to = skipped ? MealItemStatus.skipped : MealItemStatus.suggested;
    if (item.status != from) return;

    for (final slot in plan?.slots ?? const <MealSlot>[]) {
      final index = slot.items.indexOf(item);
      if (index < 0) continue;
      slot.items[index] = item.copyWith(status: to);
      notifyListeners();
      return;
    }
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
          e.food,
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
      if (item.status == MealItemStatus.suggested) item.food,
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
    diary.add(
      DiaryEntry(food: food, meal: meal, ateAt: ateAt, portion: portion),
    );

    // Mark the matching serving in the plan as eaten, if there is one. Joined
    // on the natural key (meal, dish) rather than on a foreign key.
    final slot = planOn(ateAt)?.slots.where((s) => s.type == meal).firstOrNull;
    if (slot != null) {
      for (var i = 0; i < slot.items.length; i++) {
        if (slot.items[i].food.id == food.id &&
            slot.items[i].status == MealItemStatus.suggested) {
          slot.items[i] = slot.items[i].copyWith(status: MealItemStatus.eaten);
          break;
        }
      }
    }

    notifyListeners();
  }

  /// The diary entries that still count: everything not undone.
  Iterable<DiaryEntry> get activeDiary => diary.where((e) => !e.isUndone);

  /// Takes back "I ate this": the serving returns to the plan as not eaten
  /// yet, and the entry stops counting towards the day.
  ///
  /// The entry is **kept** in [diary] and only marked — the log is a record
  /// of what the user did, and a mistaken tap is part of that record.
  void undoMeal(DiaryEntry entry) {
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
  void rate(DiaryEntry entry, int stars) {
    entry.rating = stars.clamp(1, 5);
    notifyListeners();
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
