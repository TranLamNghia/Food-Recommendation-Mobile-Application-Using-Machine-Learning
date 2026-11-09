import '../models/food.dart';
import 'evidence_level.dart';

/// Hạn mức một chất trong **một ngày**, kèm phần đã dùng của hôm nay.
///
/// Phản chiếu `MotHanMuc` ở `ml/han_muc.py`. Nó khác [NutrientTarget] ở chỗ
/// mang theo **trạng thái**: một ngưỡng thì luôn là 2 000 mg natri, còn hạn
/// mức thì nói hôm nay còn lại bao nhiêu — và phần còn lại phụ thuộc vào
/// việc người dùng đã ăn gì, nên nó là thứ phải hiện trước khi nó chặn món
/// nào. Một ràng buộc phụ thuộc trạng thái mà chỉ xuất hiện lúc báo lỗi thì
/// luôn làm người ta bất ngờ.
///
/// ## Hai cột, không gộp
///
/// [eaten] là đã ăn — không đổi được nữa. [planned] là đang nằm trong thực
/// đơn — còn đổi, còn bỏ được. Cộng chúng thành một con số sẽ mất đúng thông
/// tin người dùng cần: khi một món không vừa, họ đang chọn giữa *bỏ món đã
/// lên kế hoạch* và *chịu vượt ngưỡng*. Nếu chỉ hiện một tổng, họ sẽ tưởng
/// cả hai phần đều đã cố định.
///
/// ## Số liệu khuyết được ĐẾM, không bị bỏ qua
///
/// Bảng thành phần chỉ công bố purin cho 70 trong 318 món. Cộng những món
/// khuyết thành 0 rồi trả về một con số trông bình thường sẽ làm trần purin
/// của người gút gần như không bao giờ chạm tới — một tầng an toàn thất bại
/// theo hướng **mở** mà không báo gì. Nên [missingCount] đi kèm mọi tổng, và
/// [dataComplete] là thứ giao diện buộc phải hiện cạnh con số.
class DayLimit {
  const DayLimit({
    required this.condition,
    required this.nutrient,
    required this.unit,
    required this.amount,
    required this.eaten,
    required this.planned,
    required this.isHard,
    required this.evidence,
    this.penalty,
    this.missingCount = 0,
    this.note = '',
  });

  /// Tên bệnh lý đặt ra hạn mức này.
  final String condition;

  /// Tên cột dinh dưỡng, dùng đúng tên trong CSDL.
  final String nutrient;

  /// Đơn vị để hiện ra — `mg`, `g`.
  final String unit;

  /// Ngưỡng trần của cả ngày.
  final double amount;

  /// Đã ăn — theo `food_diary`. Không đổi được.
  final double eaten;

  /// Đang nằm trong thực đơn hôm nay, chưa ăn. Còn đổi được.
  final double planned;

  /// Cứng thì **chặn** món; mềm thì chỉ **trừ điểm**.
  ///
  /// Gộp hai thứ lại sẽ biến một khuyến cáo thành một lệnh cấm: đường
  /// ≤ 25 g/ngày là khuyến cáo, natri ≤ 2 000 mg là ngưỡng chặn.
  final bool isHard;

  final EvidenceLevel evidence;

  /// Hệ số **nhân** điểm khi vượt, chỉ có ở hạn mức mềm. Nhỏ hơn là phạt
  /// nặng hơn — xem `PenaltyOutcome`.
  final double? penalty;

  /// Số suất tính vào hạn mức này mà **không có số liệu** cho chất đó.
  final int missingCount;

  /// Xuất xứ của ngưỡng, nguyên văn từ `condition_rules.note`.
  final String note;

  /// Phần đã dùng — ăn rồi cộng với đang nằm trong thực đơn.
  double get used => eaten + planned;

  /// Còn ăn thêm được bao nhiêu.
  ///
  /// **Không kẹp về 0.** Số âm nghĩa là đã vượt, và giao diện cần biết vượt
  /// bao nhiêu để nói ra; kẹp về 0 thì câu "vượt 222 mg" không viết được.
  double get remaining => amount - used;

  bool get exceeded => used > amount;

  /// Phần đã dùng trên ngưỡng, để vẽ thanh tiến độ. Không kẹp.
  double get ratio => amount <= 0 ? 0 : used / amount;

  /// Mọi suất tính vào hạn mức này đều có số liệu.
  ///
  /// Sai nghĩa là [used] thấp hơn thực tế, nên [remaining] **cao hơn** thực
  /// tế — hạn mức đang nới ra. Giao diện phải nói điều đó, không được hiện
  /// con số trần trụi.
  bool get dataComplete => missingCount == 0;

  /// Thêm [amount] đơn vị chất này thì còn trong ngưỡng không?
  bool fits(double addition) => used + addition <= amount;

  DayLimit copyWith({double? eaten, double? planned, int? missingCount}) =>
      DayLimit(
        condition: condition,
        nutrient: nutrient,
        unit: unit,
        amount: amount,
        eaten: eaten ?? this.eaten,
        planned: planned ?? this.planned,
        isHard: isHard,
        evidence: evidence,
        penalty: penalty,
        missingCount: missingCount ?? this.missingCount,
        note: note,
      );
}

/// Toàn bộ hạn mức theo ngày của một người trong một ngày.
class DayBudget {
  const DayBudget({this.limits = const []});

  final List<DayLimit> limits;

  bool get isEmpty => limits.isEmpty;

  /// Hạn mức **chặn** món.
  List<DayLimit> get hard => [
    for (final l in limits)
      if (l.isHard) l,
  ];

  /// Hạn mức chỉ **trừ điểm** — khuyến cáo, không phải lệnh cấm.
  List<DayLimit> get soft => [
    for (final l in limits)
      if (!l.isHard) l,
  ];

  /// Hạn mức **mềm** đã bị vượt. Giao diện nói "vượt khuyến cáo", không nói
  /// "bị loại".
  List<DayLimit> get overRecommendation => [
    for (final l in limits)
      if (!l.isHard && l.exceeded) l,
  ];

  /// Hạn mức CỨNG còn ít dư địa nhất cho một chất, `null` nếu không có.
  ///
  /// Trả về danh sách rỗng thì `null`, vì hai bệnh có thể cùng hạn chế một
  /// chất với hai ngưỡng khác nhau — Tăng huyết áp và Bệnh thận đều giới hạn
  /// natri ở 2 000 mg, nhưng phần đã dùng có thể khác nếu ngưỡng khác.
  DayLimit? tightestHardFor(String nutrient) {
    final tran = [
      for (final l in limits)
        if (l.isHard && l.nutrient == nutrient) l,
    ];
    if (tran.isEmpty) return null;
    return tran.reduce((a, b) => a.remaining <= b.remaining ? a : b);
  }

  /// Lượng một chất trong một món, hoặc `null` nếu món không có số liệu.
  ///
  /// `null` là **không biết**, không phải 0 — xem [Food.purine].
  static double? valueOf(Food food, String nutrient) => switch (nutrient) {
    'calories_kcal' => food.kcal.toDouble(),
    'protein_g' => food.protein,
    'carbs_g' => food.carb,
    'fat_g' => food.fat,
    'sugar_g' => food.sugar,
    'sodium_mg' => food.sodium,
    'fiber_g' => food.fiber,
    'purine_mg' => food.purine,
    _ => null,
  };

  /// Dựng hạn mức từ các ngưỡng cùng hai nhóm món: đã ăn và đã lên kế hoạch.
  ///
  /// Mỗi ngưỡng đi vào đây chỉ mang `amount`; phần [DayLimit.eaten],
  /// [DayLimit.planned] và [DayLimit.missingCount] được cộng ở đây để một
  /// chỗ duy nhất chịu trách nhiệm đếm phần khuyết.
  static DayBudget from({
    required List<DayLimit> thresholds,
    required List<Food> eaten,
    required List<Food> planned,
  }) {
    return DayBudget(
      limits: [
        for (final t in thresholds)
          t.copyWith(
            eaten: _sum(eaten, t.nutrient),
            planned: _sum(planned, t.nutrient),
            missingCount:
                _missing(eaten, t.nutrient) + _missing(planned, t.nutrient),
          ),
      ],
    );
  }

  /// Bản sao của hạn mức sau khi **bỏ một món khỏi phần đã lên kế hoạch**.
  ///
  /// Dùng khi người dùng mở bảng đổi món: dư địa cho món thay thế là phần
  /// còn lại cộng với phần món cũ đang chiếm. Không trừ đi thì mọi ứng viên
  /// đều bị so với một hạn mức chặt hơn thực tế, và bảng đổi món sẽ chặn cả
  /// những món đáng ra chọn được — kể cả chính món đang nằm đó.
  ///
  /// Món khuyết số liệu thì trừ 0 **và** giảm [DayLimit.missingCount] đi
  /// một: nó vốn chưa từng được cộng vào tổng, nên chỉ phần đếm khuyết là
  /// thay đổi.
  DayBudget withoutPlanned(Food food) => DayBudget(
    limits: [
      for (final l in limits)
        () {
          final value = valueOf(food, l.nutrient);
          return l.copyWith(
            planned: value == null ? l.planned : l.planned - value,
            missingCount: value == null
                ? (l.missingCount - 1).clamp(0, l.missingCount)
                : l.missingCount,
          );
        }(),
    ],
  );

  static double _sum(List<Food> foods, String nutrient) {
    var tong = 0.0;
    for (final f in foods) {
      tong += valueOf(f, nutrient) ?? 0;
    }
    return tong;
  }

  static int _missing(List<Food> foods, String nutrient) {
    var so = 0;
    for (final f in foods) {
      if (valueOf(f, nutrient) == null) so++;
    }
    return so;
  }
}
