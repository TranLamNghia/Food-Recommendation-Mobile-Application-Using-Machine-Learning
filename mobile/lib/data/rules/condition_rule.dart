import '../models/food.dart';
import 'day_budget.dart';
import 'evidence_level.dart';

/// Vì sao một món bị bỏ khỏi gợi ý — **ba bậc, không phải hai**.
///
/// `FeasibilityInfo` của các ứng dụng cùng loại chỉ có khả thi / không khả
/// thi. Dữ liệu ở đây phân biệt được nhiều hơn, và gộp lại là bỏ mất thông
/// tin người dùng cần nhất.
enum ExclusionTier {
  /// Thuộc tính của **chính món ăn** — mang nhãn bị cấm, hoặc thiếu nhãn
  /// bắt buộc, hoặc vượt ngưỡng cứng theo suất. Không bao giờ hợp.
  dish('Không phù hợp với bạn'),

  /// **Hôm nay** hết hạn mức. Món không có vấn đề gì — hôm khác vẫn chọn
  /// được.
  ///
  /// Bậc này là chỗ dễ nói sai nhất. Nếu hiện "Phở sốt vang bị loại" giống
  /// kiểu "Tôm rang me bị loại", người dùng sẽ tin phở là món cấm với mình,
  /// trong khi lý do thật chỉ là sáng nay họ đã ăn mặn.
  dayBudget('Hôm nay hết hạn mức'),

  /// **Không xét được** vì danh mục thiếu số liệu ở chất bị hạn chế.
  ///
  /// Đây KHÔNG phải "vừa". Với purin đó là 248 trong 318 món, nên gộp nhóm
  /// này vào nhóm vừa sẽ làm trần purin của người gút gần như không bao giờ
  /// chạm tới.
  unknown('Chưa xét được');

  const ExclusionTier(this.heading);

  /// Tiêu đề nhóm trên giao diện.
  final String heading;
}

/// Một lý do khiến món bị bỏ.
///
/// Phản chiếu `LyDoLoai` ở `ml/f1_filter.py` cộng `MonVuotHanMuc` ở
/// `ml/han_muc.py` — hai nguồn, một kiểu, vì giao diện xếp chúng cạnh nhau.
class ExclusionReason {
  const ExclusionReason({
    required this.tier,
    required this.condition,
    required this.evidence,
    this.tag,
    this.nutrient,
    this.unit = '',
    this.threshold,
    this.measured,
    this.remaining,
    this.note = '',
  });

  /// Món mang nhãn bị cấm, hoặc thiếu nhãn bắt buộc.
  const ExclusionReason.tagRule({
    required String condition,
    required String tag,
    String note = '',
  }) : this(
         tier: ExclusionTier.dish,
         condition: condition,
         evidence: EvidenceLevel.definitional,
         tag: tag,
         note: note,
       );

  final ExclusionTier tier;
  final String condition;
  final EvidenceLevel evidence;

  /// Tên nhãn, với hai loại quy tắc nhãn.
  final String? tag;

  final String? nutrient;
  final String unit;

  /// Ngưỡng của quy tắc.
  final double? threshold;

  /// Số đo của món. `null` nghĩa là **thiếu số liệu**, không phải 0.
  final double? measured;

  /// Phần hạn mức còn lại, chỉ có ở bậc [ExclusionTier.dayBudget].
  final double? remaining;

  final String note;

  /// Món bị bỏ vì không có số liệu, chứ không vì vượt ngưỡng.
  ///
  /// Nói với người dùng "món này vượt ngưỡng" khi thật ra là "chúng tôi
  /// không biết" là sai sự thật, nên hai thứ phải tách ra.
  bool get missingData => nutrient != null && measured == null;

  /// Vượt bao nhiêu. `null` khi không tính được.
  double? get over {
    if (measured == null) return null;
    final moc = tier == ExclusionTier.dayBudget ? remaining : threshold;
    if (moc == null) return null;
    return measured! - moc;
  }
}

/// Một ràng buộc **mềm** theo suất: vượt thì trừ điểm, không loại món.
class SoftRule {
  const SoftRule({
    required this.condition,
    required this.nutrient,
    required this.unit,
    required this.threshold,
    required this.penalty,
    required this.evidence,
    this.note = '',
  });

  final String condition;
  final String nutrient;
  final String unit;
  final double threshold;

  /// **Hệ số nhân**, không phải lượng trừ.
  ///
  /// Lược đồ chỉ nói `DECIMAL(4,3)`, nhưng chính dữ liệu chỉ ra cách đọc:
  /// Tăng huyết áp có 0,600 ở mức nhẹ và 0,400 ở mức nặng, kèm ghi chú
  /// "phạt nặng hơn cho mức nặng". Đọc theo phép trừ thì 0,400 trừ ÍT hơn,
  /// tức mức nặng bị phạt nhẹ hơn — ngược hẳn ghi chú. Là hệ số nhân thì
  /// ×0,400 nặng hơn ×0,600, khớp; và phép nhân giữ điểm trong [0, 1] còn
  /// trừ 0,750 sẽ đẩy một điểm [0, 1] xuống âm.
  final double penalty;

  final EvidenceLevel evidence;
  final String note;

  bool violatedBy(double value) => value > threshold;
}

/// Một ràng buộc mềm bị món này vượt.
class SoftViolation {
  const SoftViolation({required this.rule, required this.measured});

  final SoftRule rule;
  final double measured;

  double get over => measured - rule.threshold;
}

/// Hệ số phạt của một món, kèm lý do để giao diện nói ra.
class PenaltyOutcome {
  const PenaltyOutcome({
    required this.factor,
    this.violations = const [],
    this.missingNutrients = const [],
  });

  /// Hệ số nhân cuối cùng, trong khoảng (0, 1].
  final double factor;

  final List<SoftViolation> violations;

  /// Chất mà món này không có số đo, nên không xét được luật mềm nào của nó.
  /// Không phạt, nhưng cũng không được coi là đã kiểm.
  final List<String> missingNutrients;

  bool get penalised => factor < 1.0;

  /// Áp hệ số vào một điểm trong [0, 1].
  ///
  /// Giữ điểm gốc ở phía gọi: giao diện cần nói "khớp khẩu vị 0,78, bị trừ
  /// vì mặn" chứ không phải chỉ hiện 0,47 mà không giải thích.
  double applyTo(double score) => score * factor;

  /// Hệ số phạt của một món theo các ràng buộc mềm **theo suất**.
  ///
  /// **Cộng hình phạt theo nhóm, không nhân thẳng.** Hai luật cùng
  /// (bệnh, chất) là hai dải lồng nhau — natri ≤ 700 mg và ≤ 500 mg của cùng
  /// Tăng huyết áp. Một món 800 mg vượt cả hai, nhưng đó là **một** mối lo,
  /// không phải hai: nhân cả hai ra ×0,24 thay vì ×0,40, tức đếm đôi. Nên
  /// trong mỗi nhóm lấy hệ số nặng nhất, rồi nhân qua các nhóm khác nhau.
  ///
  /// Thiếu số liệu thì **không phạt**, nhưng được ghi lại. Ràng buộc mềm là
  /// quyết định về xếp hạng, không phải về an toàn, nên hạ điểm một món vì
  /// danh mục thiếu số liệu là phạt sai đối tượng.
  static PenaltyOutcome of(Food food, List<SoftRule> rules) {
    final nangNhat = <String, SoftViolation>{};
    final thieu = <String>[];

    for (final r in rules) {
      final value = DayBudget.valueOf(food, r.nutrient);
      if (value == null) {
        if (!thieu.contains(r.nutrient)) thieu.add(r.nutrient);
        continue;
      }
      if (!r.violatedBy(value)) continue;
      final khoa = '${r.condition}|${r.nutrient}';
      final cu = nangNhat[khoa];
      if (cu == null || r.penalty < cu.rule.penalty) {
        nangNhat[khoa] = SoftViolation(rule: r, measured: value);
      }
    }

    var heSo = 1.0;
    for (final v in nangNhat.values) {
      heSo *= v.rule.penalty;
    }
    final ds = nangNhat.values.toList()
      ..sort((a, b) => a.rule.penalty.compareTo(b.rule.penalty));
    thieu.sort();

    return PenaltyOutcome(
      factor: heSo,
      violations: ds,
      missingNutrients: thieu,
    );
  }
}
