import 'dart:math' as math;

/// Giới tính — enum `gender` trong đặc tả API mục 5.1.
enum Gender {
  male('male', 'Nam'),
  female('female', 'Nữ');

  const Gender(this.code, this.label);
  final String code;
  final String label;
}

/// Mức vận động và hệ số nhân TDEE tương ứng.
///
/// Hệ số lấy từ `SYSTEM_ARCHITECTURE.md` mục 3.1.
enum ActivityLevel {
  sedentary('sedentary', 'Ít vận động', 'Ngồi nhiều, hầu như không tập', 1.200),
  light('light', 'Vận động nhẹ', 'Tập 1–3 buổi mỗi tuần', 1.375),
  moderate('moderate', 'Vận động vừa', 'Tập 3–5 buổi mỗi tuần', 1.550),
  active('active', 'Vận động nhiều', 'Tập 6–7 buổi mỗi tuần', 1.725),
  veryActive(
    'very_active',
    'Vận động rất nhiều',
    'Lao động nặng hoặc tập hai buổi mỗi ngày',
    1.900,
  );

  const ActivityLevel(this.code, this.label, this.hint, this.factor);
  final String code;
  final String label;
  final String hint;
  final double factor;
}

/// Mục tiêu sức khỏe — quyết định cách điều chỉnh hạn mức năng lượng.
enum HealthGoal {
  loseWeight('lose_weight', 'Giảm cân', 'Ăn ít hơn mức tiêu hao'),
  maintain('maintain', 'Giữ cân', 'Cân bằng năng lượng vào và ra'),
  gainWeight('gain_weight', 'Tăng cân', 'Ăn nhiều hơn mức tiêu hao'),
  healthyEating(
    'healthy_eating',
    'Ăn uống lành mạnh',
    'Không đặt nặng cân nặng',
  );

  const HealthGoal(this.code, this.label, this.hint);
  final String code;
  final String label;
  final String hint;

  /// Chỉ hai mục tiêu này mới cần hỏi cân nặng mục tiêu.
  bool get needsTargetWeight =>
      this == HealthGoal.loseWeight || this == HealthGoal.gainWeight;
}

/// Hồ sơ sức khỏe người dùng khai báo trong luồng mở đầu.
///
/// Các trường đều cho phép `null` vì hồ sơ được điền dần qua từng bước. Khi
/// đi hết luồng thì mọi trường bắt buộc đã có giá trị.
class HealthProfile {
  Gender? gender;
  DateTime? birthday;
  double? heightCm;
  double? weightKg;
  double? targetWeightKg;
  HealthGoal? goal;
  ActivityLevel? activity;

  /// Mã bệnh lý đã chọn, tra theo bảng `conditions`.
  final Set<String> conditions = {};

  /// Mã dị ứng và chế độ ăn bắt buộc.
  final Set<String> allergies = {};

  int? get age {
    final b = birthday;
    if (b == null) return null;
    final now = DateTime.now();
    var years = now.year - b.year;
    if (now.month < b.month || (now.month == b.month && now.day < b.day)) {
      years--;
    }
    return years;
  }

  /// Chỉ số khối cơ thể.
  double? get bmi {
    final h = heightCm;
    final w = weightKg;
    if (h == null || w == null || h <= 0) return null;
    final m = h / 100;
    return w / (m * m);
  }

  /// Chuyển hóa cơ bản theo công thức Mifflin-St Jeor.
  double? get bmr {
    final h = heightCm;
    final w = weightKg;
    final a = age;
    final g = gender;
    if (h == null || w == null || a == null || g == null) return null;
    final base = 10 * w + 6.25 * h - 5 * a;
    return g == Gender.male ? base + 5 : base - 161;
  }

  /// Tổng năng lượng tiêu hao trong ngày.
  double? get tdee {
    final b = bmr;
    final act = activity;
    if (b == null || act == null) return null;
    return b * act.factor;
  }

  /// Hạn mức năng lượng theo mục tiêu.
  ///
  /// Giảm cân trừ 500 kcal nhưng **không bao giờ xuống dưới BMR** — đây là
  /// ràng buộc an toàn nêu trong `SYSTEM_ARCHITECTURE.md` mục 3.1.
  double? get energyTarget {
    final t = tdee;
    final b = bmr;
    final g = goal;
    if (t == null || b == null || g == null) return null;
    return switch (g) {
      HealthGoal.loseWeight => math.max(t - 500, b),
      HealthGoal.gainWeight => t + 500,
      HealthGoal.maintain || HealthGoal.healthyEating => t,
    };
  }

  /// Phân bổ ba chất sinh năng lượng theo gram, lấy điểm giữa của khoảng
  /// khuyến nghị: 60 % bột đường, 17 % đạm, 23 % béo.
  ({double protein, double carb, double fat})? get macroTarget {
    final e = energyTarget;
    if (e == null) return null;
    return (protein: e * 0.17 / 4, carb: e * 0.60 / 4, fat: e * 0.23 / 9);
  }

  /// Chênh lệch giữa cân nặng hiện tại và cân nặng mục tiêu.
  double? get weightDelta {
    final w = weightKg;
    final t = targetWeightKg;
    if (w == null || t == null) return null;
    return t - w;
  }
}
