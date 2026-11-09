import '../models/food.dart';

/// Một ràng buộc vi chất ở cấp **NGÀY**.
///
/// Tồn tại vì mọi hướng dẫn y khoa đều phát biểu theo ngày, không theo món.
/// Bản lược đồ hiện tại đã theo đúng nguyên tắc đó — `condition_rules` lưu
/// ngưỡng cứng với `scope = 'per_day'` — nhưng **Bước 4 trước đây không thi
/// hành chúng**: nó chỉ bám `kcal` và ba chất sinh năng lượng. Nghĩa là sáu
/// ngưỡng cứng theo ngày của bệnh lý không được kiểm ở bất cứ đâu trong hệ
/// thống, dù tài liệu nói là có.
///
/// Hai hướng, vì nhu cầu thật có cả hai:
///
/// | Hướng | Ví dụ | Nguồn |
/// |---|---|---|
/// | [NutrientTarget.atMost] | natri ≤ 2000 mg/ngày | WHO |
/// | [NutrientTarget.atMost] | đạm ≤ 48 g/ngày (bệnh thận) | KDIGO 2024 |
/// | [NutrientTarget.atLeast] | chất xơ ≥ 25 g/ngày | WHO 2023 |
///
/// Lưu ý về cách đưa vào thuật toán: ràng buộc này **sửa thực đơn đã dựng**,
/// không lọc bỏ món ở đầu vào. Lọc cứng theo ngưỡng vi chất sẽ xóa sạch cả
/// một vai trò món — ngưỡng `fiber ≥ 2 g` làm vai trò `side_protein` còn 0
/// món trong 71, vì thịt cá vốn không có chất xơ — và khi đó không dựng nổi
/// bữa ăn. Lọc cứng dành cho dị nguyên và nhãn, không dành cho ngưỡng số.
class NutrientTarget {
  const NutrientTarget._(this.nutrient, this.amount, {required this.isFloor});

  /// Sàn: cả ngày phải đạt **ít nhất** [amount].
  const NutrientTarget.atLeast(String nutrient, double amount)
    : this._(nutrient, amount, isFloor: true);

  /// Trần: cả ngày không được vượt [amount].
  const NutrientTarget.atMost(String nutrient, double amount)
    : this._(nutrient, amount, isFloor: false);

  /// Tên cột dinh dưỡng, dùng đúng tên trong CSDL — xem [valueOf].
  final String nutrient;

  final double amount;

  /// `true` là sàn (`gte`), `false` là trần (`lte`).
  final bool isFloor;

  /// Lượng còn thiếu hoặc vượt, đưa về **tỷ lệ** trên ngưỡng.
  ///
  /// Phải là tỷ lệ chứ không phải lượng tuyệt đối, vì thuật toán cần so mức
  /// nghiêm trọng giữa những chất khác đơn vị nhau: thiếu 5 g chất xơ so với
  /// vượt 5 mg natri là hai chuyện hoàn toàn khác cỡ.
  ///
  /// Trả về 0 khi đã thỏa.
  double violation(double actual) {
    if (amount <= 0) return 0;
    final short = isFloor ? amount - actual : actual - amount;
    return short <= 0 ? 0 : short / amount;
  }

  bool isSatisfiedBy(double actual) => violation(actual) == 0;

  @override
  String toString() =>
      '$nutrient ${isFloor ? '≥' : '≤'} $amount';

  /// Giá trị của một chất trong một món, hoặc `null` nếu [Food] không mang
  /// chất đó.
  ///
  /// **`purine_mg` cố ý không có ở đây.** Quy tắc cứng cho bệnh gút là
  /// purin ≤ 400 mg/ngày, nhưng `Food` không có trường purin, và bảng thành
  /// phần thực phẩm chỉ công bố purin cho 64/305 món nên thêm vào cũng chỉ
  /// phủ 21 % danh mục. Phần bảo vệ cho bệnh gút vì vậy vẫn dựa vào quy tắc
  /// `exclude_tag 'Giàu purin'` chạy ở Bước 2 — nhãn đó phủ 91 món. Đây là
  /// hạn chế có thật, phải nêu trong báo cáo, chứ không phải chỗ bỏ sót.
  static double? valueOf(Food food, String nutrient) => switch (nutrient) {
    'calories_kcal' => food.kcal.toDouble(),
    'protein_g' => food.protein,
    'carbs_g' => food.carb,
    'fat_g' => food.fat,
    'sugar_g' => food.sugar,
    'sodium_mg' => food.sodium,
    'fiber_g' => food.fiber,
    _ => null,
  };

  /// Chất nào Bước 4 thi hành được ở cấp ngày.
  static const Set<String> supported = {
    'calories_kcal',
    'protein_g',
    'carbs_g',
    'fat_g',
    'sugar_g',
    'sodium_mg',
    'fiber_g',
  };
}
