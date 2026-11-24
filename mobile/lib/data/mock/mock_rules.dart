// OFFLINE: stand-in F1 rules, used when there is no server.
import '../models/food.dart';
import '../rules/condition_rule.dart';
import '../rules/day_budget.dart';
import '../rules/evidence_level.dart';

/// The condition rule set used when running offline — a mirror of
/// `condition_rules` in the database.
///
/// Every threshold, penalty factor and evidence level here is **taken
/// verbatim** from the 20 real rows in `nutrition_rec`, the `note` recording
/// the provenance included. No number is made up: if the interface shows
/// "WHO: under 2,000 mg of sodium a day", that sentence has to be traceable
/// to a row of data, not to a string typed into a widget.
///
/// Once there is a real server this file is replaced by a
/// `GET /conditions/rules` call, and the types in `lib/data/rules/` stay as
/// they are.
///
/// Note on language: every condition name, tag name and `note` below is data
/// — the condition names key against `conditions.name_vi`, the tag names
/// against `tags.name_vi`, and the notes are the verbatim text of
/// `condition_rules.note`. The severity suffixes and the exclusion notes are
/// shown to the user. All of them stay in Vietnamese.

/// One condition the user declared, with its severity.
class UserCondition {
  const UserCondition(this.name, {this.severity = 'moderate'});

  final String name;

  /// `mild` · `moderate` · `severe` — the `user_conditions.severity`
  /// column.
  final String severity;

  /// Whether the user's severity reaches at least [min].
  ///
  /// A rule only applies once `severity_min` is reached. Ignoring this column
  /// would cut someone with mild hypertension exactly as much as someone with
  /// the severe form.
  bool atLeast(String min) {
    const order = ['mild', 'moderate', 'severe'];
    return order.indexOf(severity) >= order.indexOf(min);
  }
}

/// Each condition's **hard per-day** threshold. `amount` only; the used part
/// is summed by [DayBudget.from].
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

/// The **soft per-serving** constraints. Exceeding one costs score; it does
/// not drop the dish.
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

/// The **tag** rules: drop every dish carrying this tag.
///
/// The evidence level is always [EvidenceLevel.definitional] — "if you are
/// allergic to seafood, drop dishes containing seafood" needs no organisation
/// to publish it.
const List<({String condition, String tag, String severityMin})> _tagRules = [
  (condition: 'Dị ứng hải sản', tag: 'Có hải sản', severityMin: 'mild'),
  (condition: 'Dị ứng đậu phộng', tag: 'Có đậu phộng', severityMin: 'mild'),
  (condition: 'Dị ứng trứng', tag: 'Có trứng', severityMin: 'mild'),
  (condition: 'Gút', tag: 'Giàu purin', severityMin: 'moderate'),
  // These three were missing, and the gap was invisible: a user who declared
  // a soy allergy, gluten or lactose intolerance offline had no dish removed
  // and nothing said so. `condition_rules` has had all seven of these rows
  // since the schema was seeded.
  (condition: 'Dị ứng đậu nành', tag: 'Có đậu nành', severityMin: 'mild'),
  (condition: 'Không dung nạp gluten', tag: 'Có gluten', severityMin: 'mild'),
  (
    condition: 'Không dung nạp lactose',
    tag: 'Có sữa / chế phẩm sữa',
    severityMin: 'mild',
  ),
];

/// The **`require_tag`** rules: drop every dish that does **not** carry this
/// tag.
///
/// The opposite direction from [_tagRules], and the offline copy had no
/// mechanism for it at all — so `Ăn chay` and `Ăn thuần chay`, the two rules
/// in `condition_rules` that work this way, removed nothing. A vegetarian got
/// a plan with meat in it, and the only screen that disagreed was the
/// excluded-dishes list.
///
/// Both sit at `mild`: a diet is not a thing one has mildly.
const List<({String condition, String tag, String severityMin})>
_requireTagRules = [
  (condition: 'Ăn chay', tag: 'Món chay', severityMin: 'mild'),
  (condition: 'Ăn thuần chay', tag: 'Món thuần chay', severityMin: 'mild'),
];

/// The per-day thresholds, hard **and** soft, that apply to this person.
///
/// Both kinds are returned, told apart by [DayLimit.isHard]: merging them
/// would turn a recommendation into a prohibition.
List<DayLimit> dayThresholdsFor(List<UserCondition> conditions) => [
  for (final t in _dayThresholds)
    for (final c in conditions)
      if (c.name == t.condition && c.atLeast(t.severityMin)) t.limit,
];

/// The per-serving soft constraints that apply to this person.
List<SoftRule> softRulesFor(List<UserCondition> conditions) => [
  for (final s in _softRules)
    for (final c in conditions)
      if (c.name == s.rule.condition && c.atLeast(s.severityMin)) s.rule,
];

/// The reason a dish is dropped over a **tag** — the [ExclusionTier.dish]
/// tier.
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
  // `require_tag`, which reads the other way: the dish is dropped for what
  // it does NOT carry. The sentence has to say that, or a vegetarian reading
  // "Loại mọi món có nhãn Món chay" would be told the opposite of the truth.
  for (final r in _requireTagRules)
    for (final c in conditions)
      if (c.name == r.condition &&
          c.atLeast(r.severityMin) &&
          !food.tags.contains(r.tag))
        ExclusionReason.tagRule(
          condition: '${r.condition}${_severitySuffix(c.severity)}',
          tag: r.tag,
          note: 'Chỉ giữ món có nhãn ${r.tag}',
        ),
];

String _severitySuffix(String severity) => switch (severity) {
  'mild' => ' mức nhẹ',
  'moderate' => ' mức vừa',
  'severe' => ' mức nặng',
  _ => '',
};

/// A condition code in [HealthProfile.conditions] → its name in
/// `conditions`.
///
/// Two naming schemes coexist: the profile step uses unaccented codes, while
/// the rule set is keyed on `conditions.name_vi` because that is what gets
/// shown to the user. The mapping lives in exactly one place, and an
/// unrecognised code is skipped rather than conjuring up an empty
/// condition.
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

/// Builds the condition list from the codes the user declared.
///
/// The severity defaults to `moderate` because the profile step **does not
/// ask for a severity yet**. This is an assumption with a measurable
/// consequence: for gout, `mild` does not trigger the `Giàu purin` rule while
/// `moderate` drops 91 dishes. Choosing `moderate` is choosing the safer
/// side, and that is a choice that has to be stated rather than left
/// implicit — once the profile step asks for a severity, drop this
/// parameter.
List<UserCondition> conditionsFromCodes(
  Iterable<String> codes, {
  String severity = 'moderate',
}) => [
  for (final c in codes)
    if (conditionNameByCode[c] != null)
      UserCondition(conditionNameByCode[c]!, severity: severity),
];
