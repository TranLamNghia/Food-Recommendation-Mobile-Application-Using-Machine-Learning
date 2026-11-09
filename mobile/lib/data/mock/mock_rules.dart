import '../models/food.dart';
import '../rules/condition_rule.dart';
import '../rules/day_budget.dart';
import '../rules/evidence_level.dart';

/// Bộ quy tắc bệnh lý dùng khi chạy ngoại tuyến — phản chiếu
/// `condition_rules` trong CSDL.
///
/// Mọi ngưỡng, hệ số phạt và mức tin cậy ở đây **lấy nguyên** từ 20 dòng
/// thật trong `nutrition_rec`, kể cả phần `note` ghi xuất xứ. Không có con
/// số nào tự đặt: nếu giao diện hiện "WHO: dưới 2 000 mg natri/ngày" thì câu
/// đó phải truy được về một dòng dữ liệu, không phải một chuỗi viết tay
/// trong widget.
///
/// Khi có máy chủ thật, tệp này được thay bằng lời gọi
/// `GET /conditions/rules` và các kiểu dữ liệu ở `lib/data/rules/` giữ
/// nguyên.

/// Một bệnh lý người dùng khai, kèm mức độ.
class UserCondition {
  const UserCondition(this.name, {this.severity = 'moderate'});

  final String name;

  /// `mild` · `moderate` · `severe` — cột `user_conditions.severity`.
  final String severity;

  /// Mức của người dùng đạt tối thiểu [min] hay chưa.
  ///
  /// Quy tắc chỉ áp khi đạt `severity_min`. Bỏ qua cột này thì một người
  /// tăng huyết áp mức nhẹ bị cắt đúng bằng một người mức nặng.
  bool atLeast(String min) {
    const thuTu = ['mild', 'moderate', 'severe'];
    return thuTu.indexOf(severity) >= thuTu.indexOf(min);
  }
}

/// Ngưỡng **cứng theo ngày** của từng bệnh. Chỉ `amount`; phần đã dùng do
/// [DayBudget.from] cộng.
const List<({String condition, DayLimit limit, String severityMin})>
_dayThresholds = [
  (
    condition: 'Tăng huyết áp',
    severityMin: 'mild',
    limit: DayLimit(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      amount: 2000,
      eaten: 0,
      planned: 0,
      isHard: true,
      evidence: EvidenceLevel.published,
      note: 'WHO: người lớn dưới 2000 mg natri/ngày (tương đương 5 g muối)',
    ),
  ),
  (
    condition: 'Gút',
    severityMin: 'mild',
    limit: DayLimit(
      condition: 'Gút',
      nutrient: 'purine_mg',
      unit: 'mg',
      amount: 400,
      eaten: 0,
      planned: 0,
      isHard: true,
      evidence: EvidenceLevel.published,
      note:
          'Hướng dẫn tăng acid uric máu và gút của Nhật Bản: '
          'dưới 400 mg purin/ngày',
    ),
  ),
  (
    condition: 'Bệnh thận',
    severityMin: 'mild',
    limit: DayLimit(
      condition: 'Bệnh thận',
      nutrient: 'protein_g',
      unit: 'g',
      amount: 48,
      eaten: 0,
      planned: 0,
      isHard: true,
      evidence: EvidenceLevel.derived,
      note: 'KDIGO 2024: 0,8 g đạm/kg/ngày. 48 g cho người 60 kg',
    ),
  ),
  (
    condition: 'Đái tháo đường',
    severityMin: 'mild',
    limit: DayLimit(
      condition: 'Đái tháo đường',
      nutrient: 'sugar_g',
      unit: 'g',
      amount: 25,
      eaten: 0,
      planned: 0,
      isHard: false,
      evidence: EvidenceLevel.derived,
      penalty: 0.600,
      note:
          'Ràng buộc MỀM. WHO khuyến cáo đường tự do dưới 10 % năng lượng, '
          'lý tưởng dưới 5 % (~25 g với khẩu phần 2000 kcal)',
    ),
  ),
];

/// Ràng buộc **mềm theo suất**. Vượt thì trừ điểm, không loại món.
const List<({SoftRule rule, String severityMin})> _softRules = [
  (
    severityMin: 'mild',
    rule: SoftRule(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      threshold: 700,
      penalty: 0.600,
      evidence: EvidenceLevel.derived,
      note:
          '2000 mg/ngày chia theo tỷ lệ năng lượng bữa lớn nhất; '
          'không phải ngưỡng của hướng dẫn nào',
    ),
  ),
  (
    severityMin: 'severe',
    rule: SoftRule(
      condition: 'Tăng huyết áp',
      nutrient: 'sodium_mg',
      unit: 'mg',
      threshold: 500,
      penalty: 0.400,
      evidence: EvidenceLevel.unsupported,
      note:
          'Phạt nặng hơn cho mức nặng. Ngưỡng theo ngày cho mức nặng '
          'CẦN TRA AHA/ESC — chưa xác minh',
    ),
  ),
  (
    severityMin: 'mild',
    rule: SoftRule(
      condition: 'Gút',
      nutrient: 'purine_mg',
      unit: 'mg',
      threshold: 150,
      penalty: 0.500,
      evidence: EvidenceLevel.derived,
      note:
          '400 mg/ngày chia cho 3 bữa chính; là suy diễn, '
          'không phải ngưỡng công bố',
    ),
  ),
  (
    severityMin: 'mild',
    rule: SoftRule(
      condition: 'Rối loạn mỡ máu',
      nutrient: 'fat_g',
      unit: 'g',
      threshold: 25,
      penalty: 0.750,
      evidence: EvidenceLevel.derived,
      note:
          'Mục tiêu THẬT của AHA là béo BÃO HÒA dưới 10 % năng lượng, nhưng '
          'bảng thành phần thực phẩm không tách béo bão hòa nên dùng béo tổng',
    ),
  ),
];

/// Quy tắc **nhãn**: loại mọi món mang nhãn này.
///
/// Mức tin cậy luôn là [EvidenceLevel.definitional] — "dị ứng hải sản thì
/// loại món có hải sản" không cần tổ chức nào công bố.
const List<({String condition, String tag, String severityMin})> _tagRules = [
  (condition: 'Dị ứng hải sản', tag: 'Có hải sản', severityMin: 'mild'),
  (condition: 'Dị ứng đậu phộng', tag: 'Có đậu phộng', severityMin: 'mild'),
  (condition: 'Dị ứng trứng', tag: 'Có trứng', severityMin: 'mild'),
  (condition: 'Gút', tag: 'Giàu purin', severityMin: 'moderate'),
];

/// Ngưỡng cứng **và mềm** theo ngày đang áp cho người này.
///
/// Trả về cả hai loại, phân biệt bằng [DayLimit.isHard]: gộp chúng lại sẽ
/// biến một khuyến cáo thành một lệnh cấm.
List<DayLimit> dayThresholdsFor(List<UserCondition> conditions) => [
  for (final t in _dayThresholds)
    for (final c in conditions)
      if (c.name == t.condition && c.atLeast(t.severityMin)) t.limit,
];

/// Ràng buộc mềm theo suất đang áp cho người này.
List<SoftRule> softRulesFor(List<UserCondition> conditions) => [
  for (final s in _softRules)
    for (final c in conditions)
      if (c.name == s.rule.condition && c.atLeast(s.severityMin)) s.rule,
];

/// Lý do món bị loại vì **nhãn** — bậc [ExclusionTier.dish].
List<ExclusionReason> tagExclusionsFor(
  Food food,
  List<UserCondition> conditions,
) => [
  for (final r in _tagRules)
    for (final c in conditions)
      if (c.name == r.condition &&
          c.atLeast(r.severityMin) &&
          food.tags.contains(r.tag))
        ExclusionReason.tagRule(
          condition: '${r.condition}${_severitySuffix(c.severity)}',
          tag: r.tag,
          note: 'Loại mọi món có nhãn ${r.tag}',
        ),
];

String _severitySuffix(String severity) => switch (severity) {
  'mild' => ' mức nhẹ',
  'moderate' => ' mức vừa',
  'severe' => ' mức nặng',
  _ => '',
};

/// Mã bệnh lý trong [HealthProfile.conditions] → tên trong `conditions`.
///
/// Hai cách gọi cùng tồn tại: bước khai hồ sơ dùng mã không dấu, còn bộ quy
/// tắc khóa theo `conditions.name_vi` vì đó là thứ hiện cho người dùng. Ánh
/// xạ ở đúng một chỗ, và mã lạ bị bỏ qua chứ không dựng ra một bệnh rỗng.
const Map<String, String> conditionNameByCode = {
  'diabetes': 'Đái tháo đường',
  'hypertension': 'Tăng huyết áp',
  'dyslipidemia': 'Rối loạn mỡ máu',
  'kidney_disease': 'Bệnh thận',
  'gout': 'Gút',
  'allergy_seafood': 'Dị ứng hải sản',
  'allergy_peanut': 'Dị ứng đậu phộng',
  'allergy_egg': 'Dị ứng trứng',
  'lactose_intolerance': 'Không dung nạp lactose',
  'gluten_intolerance': 'Không dung nạp gluten',
  'vegetarian': 'Ăn chay',
  'vegan': 'Ăn thuần chay',
};

/// Dựng danh sách bệnh lý từ các mã người dùng đã khai.
///
/// Mức độ mặc định là `moderate` vì bước khai hồ sơ hiện **chưa hỏi mức**.
/// Đây là giả định có hậu quả đo được: với Gút, mức `mild` không kích hoạt
/// luật `Giàu purin` còn `moderate` thì loại 91 món. Chọn `moderate` là
/// chọn phía an toàn hơn, và đó là lựa chọn phải nêu ra chứ không được để
/// ngầm — khi bước khai hồ sơ có câu hỏi mức độ thì bỏ tham số này đi.
List<UserCondition> conditionsFromCodes(
  Iterable<String> codes, {
  String severity = 'moderate',
}) => [
  for (final c in codes)
    if (conditionNameByCode[c] != null)
      UserCondition(conditionNameByCode[c]!, severity: severity),
];
