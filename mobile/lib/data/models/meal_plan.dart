import 'food.dart';
import '../recommender/nutrient_target.dart';

/// Bữa ăn trong ngày — enum `meal_type` trong đặc tả API mục 5.4.
///
/// [energyShare] là tỷ lệ năng lượng của bữa trên tổng cả ngày, lấy điểm
/// giữa khoảng khuyến nghị của Viện Dinh dưỡng Quốc gia (sáng 25–30 %,
/// trưa 35–40 %, tối 25–30 %, phụ 5–10 %). Bốn tỷ lệ cộng lại đúng bằng 1.
enum MealType {
  breakfast('breakfast', 'Bữa sáng', 0.275),
  lunch('lunch', 'Bữa trưa', 0.375),
  dinner('dinner', 'Bữa tối', 0.275),
  snack('snack', 'Bữa phụ', 0.075);

  const MealType(this.code, this.label, this.energyShare);

  final String code;
  final String label;
  final double energyShare;
}

/// Trạng thái của một món trong thực đơn — cột `meal_plan_items.status`.
///
/// Mỗi trạng thái là một **nguồn tín hiệu huấn luyện** với nhãn và trọng số
/// khác nhau, xem bảng quy đổi nhãn trong `DATABASE_DESIGN.md` mục 7.4.
enum MealItemStatus {
  /// Vừa sinh ra, người dùng chưa động tới.
  planned('planned', 'Chờ ăn'),

  /// Người dùng giữ lại và đã ăn — tín hiệu mạnh.
  eaten('eaten', 'Đã ăn'),

  /// Người dùng đổi sang món khác — tín hiệu âm.
  replaced('replaced', 'Đã đổi'),

  /// Bỏ qua, không ăn. Tín hiệu yếu vì lý do có thể không liên quan khẩu vị.
  skipped('skipped', 'Bỏ qua');

  const MealItemStatus(this.code, this.label);

  final String code;
  final String label;
}

/// Một suất trong thực đơn.
class MealPlanItem {
  MealPlanItem({
    required this.food,
    required this.score,
    this.explorationDelta,
    this.status = MealItemStatus.planned,
  });

  final Food food;

  /// Điểm mức độ phù hợp do bước chấm điểm sinh ra, trong đoạn [0, 1].
  final double score;

  /// Biên độ nhiễu δ nếu đây là suất **thăm dò**; `null` nghĩa là suất
  /// **khai thác**. Tương ứng cột `meal_plan_items.exploration_delta`.
  final double? explorationDelta;

  MealItemStatus status;

  bool get isExploration => explorationDelta != null;

  MealPlanItem copyWith({MealItemStatus? status}) => MealPlanItem(
    food: food,
    score: score,
    explorationDelta: explorationDelta,
    status: status ?? this.status,
  );
}

/// Một bữa trong thực đơn, kèm hạn mức riêng của bữa đó.
class MealSlot {
  MealSlot({required this.type, required this.targetKcal, required this.items});

  final MealType type;

  /// Hạn mức năng lượng của riêng bữa này, bằng `E_target × energyShare`.
  final double targetKcal;

  final List<MealPlanItem> items;

  double get actualKcal =>
      items.fold(0, (sum, i) => sum + i.food.kcal.toDouble());

  double get protein => items.fold(0, (sum, i) => sum + i.food.protein);
  double get carb => items.fold(0, (sum, i) => sum + i.food.carb);
  double get fat => items.fold(0, (sum, i) => sum + i.food.fat);

  /// Độ lệch so với hạn mức, tính theo phần trăm. Dương là vượt.
  double get deviationPct =>
      targetKcal <= 0 ? 0 : (actualKcal - targetKcal) / targetKcal * 100;
}

/// Thực đơn một ngày — bảng `meal_plans` cùng các dòng `meal_plan_items`.
class DailyPlan {
  DailyPlan({
    required this.date,
    required this.targetKcal,
    required this.targetProtein,
    required this.targetCarb,
    required this.targetFat,
    required this.slots,
    required this.explorationRatio,
    this.nutrientTargets = const [],
  });

  final DateTime date;

  final double targetKcal;
  final double targetProtein;
  final double targetCarb;
  final double targetFat;

  final List<MealSlot> slots;

  /// Tỷ lệ suất thăm dò **mục tiêu** của thực đơn — cột
  /// `meal_plans.exploration_ratio`. Trần cứng 50 % theo ràng buộc
  /// `chk_expl_ratio`: quá nửa thực đơn là món thử nghiệm thì nó không còn
  /// là gợi ý cá nhân hóa nữa.
  final double explorationRatio;

  /// Ràng buộc vi chất cấp ngày mà thực đơn này được dựng dưới.
  ///
  /// Giữ lại trong kết quả chứ không chỉ dùng xong rồi bỏ, vì phải trả lời
  /// được câu "thực đơn này có thỏa ngưỡng natri của tôi không" ở cả giao
  /// diện và báo cáo — xem [nutrientViolations].
  final List<NutrientTarget> nutrientTargets;

  List<MealPlanItem> get allItems => [for (final s in slots) ...s.items];

  double get actualKcal => slots.fold(0, (sum, s) => sum + s.actualKcal);
  double get actualProtein => slots.fold(0, (sum, s) => sum + s.protein);
  double get actualCarb => slots.fold(0, (sum, s) => sum + s.carb);
  double get actualFat => slots.fold(0, (sum, s) => sum + s.fat);

  /// Độ lệch năng lượng so với hạn mức, theo phần trăm.
  ///
  /// Đề cương cam kết chỉ số này không vượt quá 10 %, nên đây là con số phải
  /// hiển thị được trên giao diện và trích được vào báo cáo.
  double get deviationPct =>
      targetKcal <= 0 ? 0 : (actualKcal - targetKcal) / targetKcal * 100;

  bool get withinTolerance => deviationPct.abs() <= 10;

  /// Tổng một chất trên cả ngày.
  double totalOf(String nutrient) => allItems.fold(
    0,
    (sum, i) => sum + (NutrientTarget.valueOf(i.food, nutrient) ?? 0),
  );

  /// Những ràng buộc vi chất **chưa** thỏa, kèm lượng thực tế.
  ///
  /// Rỗng là tốt. Không rỗng nghĩa là pha 5 của Bước 4 đã hết phép đổi khả
  /// dụng — thường vì danh mục không có món nào đủ để lấp, chứ không phải
  /// thuật toán bỏ cuộc sớm. Phải hiện ra chứ không được ỉm đi: một thực đơn
  /// vi phạm ngưỡng mà trông như bình thường là đúng kiểu lỗi nguy hiểm nhất
  /// với người có bệnh.
  ///
  /// Chỉ xét những chất **thi hành được** — xem [unenforceableTargets].
  List<({NutrientTarget target, double actual})> get nutrientViolations => [
    for (final t in nutrientTargets)
      if (NutrientTarget.supported.contains(t.nutrient) &&
          !t.isSatisfiedBy(totalOf(t.nutrient)))
        (target: t, actual: totalOf(t.nutrient)),
  ];

  /// Ràng buộc mà hệ thống **không thi hành được** vì [Food] không mang chất
  /// đó — hiện chỉ có `purine_mg`.
  ///
  /// Phải tách khỏi [nutrientViolations] chứ không gộp vào, và tuyệt đối
  /// không được lặng lẽ coi là đã thỏa. Nếu gộp chung thì
  /// `atMost('purine_mg', 400)` sẽ báo **thỏa** vì tổng đọc ra bằng 0 — một
  /// thực đơn chưa từng được kiểm purin lại hiện ra như đã đạt ngưỡng gút.
  /// Đó là kiểu sai tệ hơn cả báo vi phạm.
  List<NutrientTarget> get unenforceableTargets => [
    for (final t in nutrientTargets)
      if (!NutrientTarget.supported.contains(t.nutrient)) t,
  ];

  /// Thỏa mọi ràng buộc thi hành được, **và** không còn ràng buộc nào ngoài
  /// tầm thi hành. Điều kiện thứ hai cố ý nghiêm: không khẳng định "đạt" khi
  /// có thứ chưa kiểm được.
  bool get meetsNutrientTargets =>
      nutrientViolations.isEmpty && unenforceableTargets.isEmpty;

  /// Tỷ lệ suất thăm dò **thực tế** đạt được. Thấp hơn nhiều so với
  /// [explorationRatio] nghĩa là bước chọn tổ hợp không tìm đủ món thăm dò
  /// vừa khớp ràng buộc năng lượng.
  double get actualExplorationRatio {
    final items = allItems;
    if (items.isEmpty) return 0;
    return items.where((i) => i.isExploration).length / items.length;
  }
}
