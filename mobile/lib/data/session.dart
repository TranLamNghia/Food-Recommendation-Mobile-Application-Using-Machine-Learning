import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'mock/mock_foods.dart';
import 'mock/mock_rules.dart';
import 'models/diary_entry.dart';
import 'models/food.dart';
import 'models/health_profile.dart';
import 'models/meal_plan.dart';
import 'models/swipe_action.dart';
import 'recommender/food_vector.dart';
import 'recommender/menu_builder.dart';
import 'recommender/nutrient_target.dart';
import 'recommender/preference_profile.dart';
import 'rules/day_budget.dart';
import 'rules/dish_screening.dart';

/// Trạng thái dùng chung của cả phiên sử dụng.
///
/// Ở bản dựng giao diện này, mọi thứ nằm trong bộ nhớ và biến mất khi đóng
/// ứng dụng — đúng vai trò của một bản mô phỏng. Khi nối với máy chủ thật,
/// lớp này giữ nguyên giao diện công khai, chỉ thay phần ruột: [completeSurvey]
/// gọi `POST /onboarding/survey`, [regeneratePlan] gọi `POST /meal-plans`,
/// và [logMeal] gọi `POST /diary`.
class AppSession extends ChangeNotifier {
  AppSession({math.Random? rng}) : _rng = rng ?? math.Random();

  final math.Random _rng;

  /// Hồ sơ sức khỏe khai báo ở luồng mở đầu.
  final HealthProfile profile = HealthProfile();

  /// Kho món đã qua Bộ lọc F1. Bản mock dùng thẳng gói khảo sát.
  List<Food> get candidates => MockFoods.surveyDeck;

  late final FoodVectorSpace _space = FoodVectorSpace.fromFoods(candidates);
  FoodVectorSpace get space => _space;

  PreferenceProfile? _preference;

  /// Hồ sơ sở thích. Trước khi vuốt thì là hồ sơ rỗng — Giai đoạn 0, mọi món
  /// cùng điểm và thứ tự do ràng buộc dinh dưỡng quyết định.
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
  /// ones. Used by the shopping list, which must cover days nobody opened yet.
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

  /// Tỷ lệ thăm dò đang áp dụng. Người dùng không chỉnh được; để ở đây để
  /// màn hình thực nghiệm đổi được khi cần so sánh hai cấu hình.
  double explorationRatio = 0.3;

  /// Ràng buộc vi chất ở cấp **ngày** mà Bước 4 phải thỏa.
  ///
  /// Trong hệ thống thật, danh sách này ghép từ hai nguồn — không có nguồn
  /// nào là do lập trình viên tự đặt:
  ///
  /// * `condition_rules` với `scope = 'per_day'` và `is_hard = 1`, lọc theo
  ///   bệnh lý người dùng đã khai. Hiện là bốn dòng: natri ≤ 2000 mg (WHO,
  ///   áp cho tăng huyết áp và bệnh thận), purin ≤ 400 mg, đạm ≤ 48 g
  ///   (KDIGO 2024).
  /// * `rda_reference`, tra theo giới tính và tuổi, cho những mục tiêu người
  ///   dùng **tự khai**. Hiện là chất xơ ≥ 25 g/ngày với người từ 10 tuổi
  ///   (WHO 2023).
  ///
  /// Mặc định rỗng: không bệnh lý, không mục tiêu thì Bước 4 chạy đúng như
  /// trước. Bản mock chưa có luồng khai bệnh nên màn hình thực nghiệm gán
  /// trực tiếp vào đây.
  ///
  /// Lưu ý `purine_mg` **không** thi hành được — xem
  /// `NutrientTarget.valueOf`. Truyền vào vẫn hợp lệ và sẽ hiện ra ở
  /// `DailyPlan.unenforceableTargets` thay vì bị lặng lẽ coi là đã thỏa.
  List<NutrientTarget> nutrientTargets = const [];

  // ── Account ──────────────────────────────────────────────────────

  String? _accountEmail;
  String? _displayName;

  /// `null` while the user is anonymous: the profile then lives on this
  /// device only.
  String? get accountEmail => _accountEmail;
  String? get displayName => _displayName;
  bool get isSignedIn => _accountEmail != null;

  /// Mock of `POST /auth/login` and `POST /auth/register`: accepts anything
  /// the form already validated.
  void signIn({required String email, String? displayName}) {
    _accountEmail = email.trim();
    _displayName = displayName?.trim();
    notifyListeners();
  }

  void signOut() {
    _accountEmail = null;
    _displayName = null;
    notifyListeners();
  }

  // ── Saved dishes ─────────────────────────────────────────────────

  /// Dishes the user hearted.
  final Set<String> lovedIds = {};

  /// Dishes the user never wants suggested again. Removed from the candidate
  /// pool before a plan is built, so no score can bring them back.
  final Set<String> neverAgainIds = {};

  void toggleLoved(Food food) {
    if (!lovedIds.remove(food.id)) {
      lovedIds.add(food.id);
      neverAgainIds.remove(food.id);
    }
    notifyListeners();
  }

  void setNeverAgain(Food food, bool value) {
    if (value) {
      neverAgainIds.add(food.id);
      lovedIds.remove(food.id);
    } else {
      neverAgainIds.remove(food.id);
    }
    notifyListeners();
  }

  // ── Shopping list ────────────────────────────────────────────────

  /// Names of the shopping rows already in the basket.
  final Set<String> shoppingTicked = {};

  /// Rows the user typed in, outside any dish.
  final List<String> shoppingExtras = [];

  void toggleShoppingTick(String name) {
    if (!shoppingTicked.remove(name)) shoppingTicked.add(name);
    notifyListeners();
  }

  void addShoppingExtra(String name) {
    final clean = name.trim();
    if (clean.isEmpty || shoppingExtras.contains(clean)) return;
    shoppingExtras.add(clean);
    notifyListeners();
  }

  void removeShoppingExtra(String name) {
    shoppingExtras.remove(name);
    shoppingTicked.remove(name);
    notifyListeners();
  }

  void clearShoppingTicks() {
    shoppingTicked.clear();
    notifyListeners();
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

  /// Wipes everything back to a fresh install, account included.
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
      ..allergies.clear();
    _preference = null;
    _plans.clear();
    _selectedDay = _dateOnly(DateTime.now());
    diary.clear();
    lovedIds.clear();
    neverAgainIds.clear();
    shoppingTicked.clear();
    shoppingExtras.clear();
    _accountEmail = null;
    _displayName = null;
    notifyListeners();
  }

  // ── Khởi đầu nguội ───────────────────────────────────────────────

  /// Nhận kết quả phiên vuốt, dựng hồ sơ sở thích rồi sinh thực đơn đầu tiên.
  void completeSurvey(List<({Food food, SwipeAction action})> swipes) {
    _preference = PreferenceProfile.fromSwipes(space: _space, swipes: swipes);
    regeneratePlan();
  }

  // ── Thực đơn ─────────────────────────────────────────────────────

  /// Sinh lại thực đơn cho [date], mặc định là ngày đang xem.
  ///
  /// Trả về `false` khi hồ sơ sức khỏe chưa đủ dữ liệu để tính hạn mức —
  /// thiếu giới tính, ngày sinh, chiều cao, cân nặng hoặc mức vận động.
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
    final allowed = [
      for (final f in candidates)
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

  /// Danh sách món thay thế cho một suất, xếp theo điểm giảm dần.
  List<Food> alternativesFor(MealPlanItem item) {
    final plan = this.plan;
    final exclude = plan == null
        ? <String>{}
        : plan.allItems.map((i) => i.food.id).toSet();

    return _builder().alternativesFor(item, excludeIds: exclude);
  }

  /// Đổi một suất sang món khác.
  ///
  /// Thao tác này sinh ra **hai** tín hiệu huấn luyện cùng lúc: món bị bỏ
  /// nhận nhãn `plan_replaced` (0,15), món được chọn nhận nhãn `plan_kept`
  /// (0,70). Đây là nguồn dữ liệu chính sau khi phiên vuốt kết thúc.
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
      // Suất cũ chỉ giữ lại để ghi nhận tín hiệu, không hiển thị nữa.
      slot.items.removeAt(index + 1);
      notifyListeners();
      return;
    }
  }

  /// Marks a planned item as skipped (eating out, not hungry…), or puts a
  /// skipped one back. A weak training signal: the reason may have nothing to
  /// do with taste.
  void setSkipped(MealPlanItem item, bool skipped) {
    final from = skipped ? MealItemStatus.planned : MealItemStatus.skipped;
    final to = skipped ? MealItemStatus.skipped : MealItemStatus.planned;
    if (item.status != from) return;

    for (final slot in plan?.slots ?? const <MealSlot>[]) {
      final index = slot.items.indexOf(item);
      if (index < 0) continue;
      slot.items[index] = item.copyWith(status: to);
      notifyListeners();
      return;
    }
  }

  // ── Hạn mức theo ngày và sàng món ────────────────────────────────

  /// Bệnh lý người dùng đã khai, ở dạng bộ quy tắc hiểu được.
  List<UserCondition> get userConditions =>
      conditionsFromCodes(profile.conditions);

  /// Món **đã ăn** hôm nay — theo nhật ký.
  ///
  /// Nhật ký là nguồn duy nhất của phần đã ăn. Suất mang trạng thái `eaten`
  /// KHÔNG được cộng thêm: [logMeal] ghi cả hai nơi cùng lúc, nên cộng cả
  /// hai là đếm hai lần cùng một suất.
  List<Food> get eatenToday {
    // The day on screen, which is today unless the week strip moved it.
    final homNay = _selectedDay;
    return [
      for (final e in diary)
        if (e.ateAt.year == homNay.year &&
            e.ateAt.month == homNay.month &&
            e.ateAt.day == homNay.day)
          e.food,
    ];
  }

  /// Món **đang nằm trong thực đơn**, chưa ăn.
  ///
  /// Tách khỏi [eatenToday] chứ không gộp: khi một món không vừa hạn mức,
  /// người dùng đang chọn giữa *bỏ món đã lên kế hoạch* và *chịu vượt*. Một
  /// tổng duy nhất làm họ tưởng cả hai phần đều đã cố định.
  List<Food> get plannedToday => [
    for (final item in plan?.allItems ?? const <MealPlanItem>[])
      if (item.status == MealItemStatus.planned) item.food,
  ];

  /// Hạn mức theo ngày của hôm nay, đã trừ phần đã dùng.
  DayBudget get dayBudget => DayBudget.from(
    thresholds: dayThresholdsFor(userConditions),
    eaten: eatenToday,
    planned: plannedToday,
  );

  /// Sàng toàn bộ danh mục theo bệnh lý và hạn mức còn lại.
  ///
  /// Tính lại mỗi lần gọi là cố ý: hạn mức phụ thuộc vào việc hôm nay đã ăn
  /// gì, nên một kết quả được nhớ lại sẽ sai ngay sau lần ghi nhật ký kế
  /// tiếp — và sai theo hướng nới lỏng.
  ScreeningResult get screening => screenDishes(
    foods: candidates,
    conditions: userConditions,
    budget: dayBudget,
    softRules: softRulesFor(userConditions),
  );

  // ── Nhật ký ──────────────────────────────────────────────────────

  /// Ghi một món đã ăn vào nhật ký.
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

    // Đánh dấu suất tương ứng trong thực đơn là đã ăn, nếu có. Ghép theo
    // khóa tự nhiên (bữa, món) chứ không theo khóa ngoại.
    final slot = planOn(ateAt)?.slots.where((s) => s.type == meal).firstOrNull;
    if (slot != null) {
      for (var i = 0; i < slot.items.length; i++) {
        if (slot.items[i].food.id == food.id &&
            slot.items[i].status == MealItemStatus.planned) {
          slot.items[i] = slot.items[i].copyWith(status: MealItemStatus.eaten);
          break;
        }
      }
    }

    notifyListeners();
  }

  void removeDiaryEntry(DiaryEntry entry) {
    diary.remove(entry);
    notifyListeners();
  }

  /// Chấm điểm một món sau khi ăn — nguồn tín hiệu mạnh nhất.
  void rate(DiaryEntry entry, int stars) {
    entry.rating = stars.clamp(1, 5);
    notifyListeners();
  }

  // ── Số liệu tổng hợp ─────────────────────────────────────────────

  List<DiaryEntry> entriesOn(DateTime day) => diary
      .where(
        (e) =>
            e.ateAt.year == day.year &&
            e.ateAt.month == day.month &&
            e.ateAt.day == day.day,
      )
      .toList();

  /// Năng lượng đã nạp trong ngày.
  double consumedKcalOn(DateTime day) =>
      entriesOn(day).fold(0, (sum, e) => sum + e.kcal);

  /// Tỷ lệ tuân thủ thực đơn: bao nhiêu phần suất được gợi ý đã thật sự ăn.
  ///
  /// Đây là chỉ số nghiệm thu quan trọng của đề tài — gợi ý hay đến đâu mà
  /// người dùng không ăn thì cũng vô nghĩa.
  double get adherenceRate {
    final plan = todayPlan;
    if (plan == null || plan.allItems.isEmpty) return 0;

    final eaten = plan.allItems
        .where((i) => i.status == MealItemStatus.eaten)
        .length;
    return eaten / plan.allItems.length;
  }

  /// Tổng số tín hiệu đã tích lũy, dùng cho hệ số trộn α giữa hai giai đoạn.
  int get signalCount =>
      preference.signalCount +
      diary.length +
      diary.where((e) => e.rating != null).length;

  /// Hệ số trộn α giữa điểm học máy và điểm tương đồng nội dung.
  ///
  /// ```text
  ///       ⎧ 0                                nếu n < n_min
  ///   α = ⎨ (n − n_min) / (n_max − n_min)    nếu n_min ≤ n ≤ n_max
  ///       ⎩ 1                                nếu n > n_max
  /// ```
  ///
  /// Bản mock chưa có mô hình học máy nên α chỉ dùng để hiển thị tiến độ
  /// "hệ thống đã hiểu bạn tới đâu" cho người dùng thấy.
  double get mlBlendFactor {
    const nMin = 30;
    const nMax = 100;
    final n = signalCount;
    if (n < nMin) return 0;
    if (n > nMax) return 1;
    return (n - nMin) / (nMax - nMin);
  }
}

/// Cấp [AppSession] xuống toàn cây widget và dựng lại phần phụ thuộc khi nó
/// đổi. Dùng [InheritedNotifier] thay vì thêm một gói quản lý trạng thái —
/// ứng dụng này chỉ có một nguồn trạng thái duy nhất.
class SessionScope extends InheritedNotifier<AppSession> {
  const SessionScope({
    super.key,
    required AppSession session,
    required super.child,
  }) : super(notifier: session);

  static AppSession of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<SessionScope>();
    assert(scope != null, 'Không tìm thấy SessionScope phía trên widget này');
    return scope!.notifier!;
  }
}
