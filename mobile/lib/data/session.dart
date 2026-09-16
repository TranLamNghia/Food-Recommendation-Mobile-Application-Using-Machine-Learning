import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'mock/mock_foods.dart';
import 'models/diary_entry.dart';
import 'models/food.dart';
import 'models/health_profile.dart';
import 'models/meal_plan.dart';
import 'models/swipe_action.dart';
import 'recommender/food_vector.dart';
import 'recommender/menu_builder.dart';
import 'recommender/preference_profile.dart';

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

  DailyPlan? _plan;
  DailyPlan? get plan => _plan;

  final List<DiaryEntry> diary = [];

  /// Tỷ lệ thăm dò đang áp dụng. Người dùng không chỉnh được; để ở đây để
  /// màn hình thực nghiệm đổi được khi cần so sánh hai cấu hình.
  double explorationRatio = 0.3;

  // ── Khởi đầu nguội ───────────────────────────────────────────────

  /// Nhận kết quả phiên vuốt, dựng hồ sơ sở thích rồi sinh thực đơn đầu tiên.
  void completeSurvey(List<({Food food, SwipeAction action})> swipes) {
    _preference = PreferenceProfile.fromSwipes(space: _space, swipes: swipes);
    regeneratePlan();
  }

  // ── Thực đơn ─────────────────────────────────────────────────────

  /// Sinh lại thực đơn cho hôm nay.
  ///
  /// Trả về `false` khi hồ sơ sức khỏe chưa đủ dữ liệu để tính hạn mức —
  /// thiếu giới tính, ngày sinh, chiều cao, cân nặng hoặc mức vận động.
  bool regeneratePlan({DateTime? date}) {
    final energy = profile.energyTarget;
    final macro = profile.macroTarget;
    if (energy == null || macro == null) return false;

    _plan = _builder().build(
      date: date ?? DateTime.now(),
      targetKcal: energy,
      targetProtein: macro.protein,
      targetCarb: macro.carb,
      targetFat: macro.fat,
    );
    notifyListeners();
    return true;
  }

  MenuBuilder _builder() => MenuBuilder(
    candidates: candidates,
    profile: preference,
    explorationRatio: explorationRatio,
    rng: _rng,
  );

  /// Danh sách món thay thế cho một suất, xếp theo điểm giảm dần.
  List<Food> alternativesFor(MealPlanItem item) {
    final plan = _plan;
    final exclude = plan == null
        ? <int>{}
        : plan.allItems.map((i) => i.food.id).toSet();

    return _builder().alternativesFor(item, excludeIds: exclude);
  }

  /// Đổi một suất sang món khác.
  ///
  /// Thao tác này sinh ra **hai** tín hiệu huấn luyện cùng lúc: món bị bỏ
  /// nhận nhãn `plan_replaced` (0,15), món được chọn nhận nhãn `plan_kept`
  /// (0,70). Đây là nguồn dữ liệu chính sau khi phiên vuốt kết thúc.
  void replaceItem(MealPlanItem item, Food replacement) {
    final plan = _plan;
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

  // ── Nhật ký ──────────────────────────────────────────────────────

  /// Ghi một món đã ăn vào nhật ký.
  void logMeal({
    required Food food,
    required MealType meal,
    double portion = 1.0,
    DateTime? at,
  }) {
    diary.add(
      DiaryEntry(
        food: food,
        meal: meal,
        ateAt: at ?? DateTime.now(),
        portion: portion,
      ),
    );

    // Đánh dấu suất tương ứng trong thực đơn là đã ăn, nếu có. Ghép theo
    // khóa tự nhiên (bữa, món) chứ không theo khóa ngoại.
    final slot = _plan?.slots.where((s) => s.type == meal).firstOrNull;
    if (slot != null) {
      for (var i = 0; i < slot.items.length; i++) {
        if (slot.items[i].food.id == food.id) {
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
    final plan = _plan;
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
