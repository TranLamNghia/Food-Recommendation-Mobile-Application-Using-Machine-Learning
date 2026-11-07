import '../mock/mock_rules.dart';
import '../models/food.dart';
import 'condition_rule.dart';
import 'day_budget.dart';

/// Kết quả sàng một tập món theo bệnh lý và hạn mức còn lại của hôm nay.
///
/// Phản chiếu `loc_f1` + `ly_do_loai` + `mon_khong_vua` ở phía Python. Điểm
/// quan trọng là nó trả về **lý do**, không chỉ trả về tập còn lại: lấy phần
/// bù chỉ cho biết món nào biến mất, không cho biết tại sao, và câu "vì sao"
/// là thứ duy nhất làm người dùng tin được một gợi ý về sức khỏe.
class ScreeningResult {
  const ScreeningResult({
    required this.allowed,
    required this.excluded,
    required this.penalties,
  });

  /// Món đi qua mọi ràng buộc cứng **và** mọi chất bị hạn chế đều có số liệu.
  final List<Food> allowed;

  /// Món bị bỏ, kèm mọi lý do. Một món có thể vướng nhiều luật cùng lúc, và
  /// mọi luật bị vướng đều được nêu: sửa được một luật chưa chắc món đó hợp.
  final Map<String, List<ExclusionReason>> excluded;

  /// Hệ số phạt mềm của **món được phép**, khóa theo `food.id`.
  ///
  /// Chỉ của món được phép: phạt mềm là chuyện xếp hạng, nên tính nó cho một
  /// món đã bị loại là vô nghĩa.
  final Map<String, PenaltyOutcome> penalties;

  /// Món bị bỏ, nhóm theo bậc lý do.
  ///
  /// Một món thuộc bậc **nghiêm nhất** trong các lý do của nó: vướng một
  /// thuộc tính của chính món thì không còn quan trọng là hôm nay hết hạn
  /// mức hay không.
  Map<ExclusionTier, List<String>> get byTier {
    final ra = <ExclusionTier, List<String>>{
      ExclusionTier.dish: [],
      ExclusionTier.dayBudget: [],
      ExclusionTier.unknown: [],
    };
    for (final e in excluded.entries) {
      final bac = e.value
          .map((r) => r.tier)
          .reduce((a, b) => a.index <= b.index ? a : b);
      ra[bac]!.add(e.key);
    }
    return ra;
  }
}

/// Sàng [foods] cho một người: ba bậc lý do, không phải hai.
///
/// Thứ tự xét là có chủ ý và không đổi được:
///
/// 1. **Nhãn** — thuộc tính của chính món, không phụ thuộc hôm nay ăn gì.
/// 2. **Hạn mức ngày** — món không có vấn đề gì, chỉ là hôm nay đã dùng gần
///    hết. Hôm khác vẫn chọn được, và giao diện phải nói ra điều đó.
/// 3. **Thiếu số liệu** — không kết luận được. Đây KHÔNG phải "vừa": với
///    purin đó là 20 trong 30 món mẫu, nên gộp vào nhóm vừa sẽ làm trần
///    purin của người gút gần như không bao giờ chạm tới.
///
/// Vướng một ngưỡng **đã biết** thì kết luận được ngay, kể cả khi một ngưỡng
/// khác thiếu số liệu — đã chắc chắn không vừa.
ScreeningResult screenDishes({
  required List<Food> foods,
  required List<UserCondition> conditions,
  required DayBudget budget,
  List<SoftRule> softRules = const [],
}) {
  final allowed = <Food>[];
  final excluded = <String, List<ExclusionReason>>{};
  final penalties = <String, PenaltyOutcome>{};

  final hardLimits = budget.hard;

  for (final food in foods) {
    final lyDo = <ExclusionReason>[];

    // ── 1. Nhãn ──
    lyDo.addAll(tagExclusionsFor(food, conditions));

    // ── 2 & 3. Hạn mức theo ngày ──
    final thieu = <ExclusionReason>[];
    for (final limit in hardLimits) {
      final value = DayBudget.valueOf(food, limit.nutrient);
      if (value == null) {
        thieu.add(
          ExclusionReason(
            tier: ExclusionTier.unknown,
            condition: limit.condition,
            evidence: limit.evidence,
            nutrient: limit.nutrient,
            unit: limit.unit,
            threshold: limit.amount,
            remaining: limit.remaining,
            note: limit.note,
          ),
        );
        continue;
      }
      if (!limit.fits(value)) {
        lyDo.add(
          ExclusionReason(
            tier: ExclusionTier.dayBudget,
            condition: limit.condition,
            evidence: limit.evidence,
            nutrient: limit.nutrient,
            unit: limit.unit,
            threshold: limit.amount,
            measured: value,
            remaining: limit.remaining,
            note: limit.note,
          ),
        );
      }
    }

    if (lyDo.isNotEmpty) {
      excluded[food.id] = lyDo;
      continue;
    }
    if (thieu.isNotEmpty) {
      excluded[food.id] = thieu;
      continue;
    }

    allowed.add(food);
    penalties[food.id] = PenaltyOutcome.of(food, softRules);
  }

  return ScreeningResult(
    allowed: allowed,
    excluded: excluded,
    penalties: penalties,
  );
}
