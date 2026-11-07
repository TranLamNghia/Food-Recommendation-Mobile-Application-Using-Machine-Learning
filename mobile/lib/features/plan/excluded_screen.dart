import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/food.dart';
import '../../data/rules/condition_rule.dart';
import '../../data/rules/dish_screening.dart';
import 'widgets/day_budget_card.dart' show nutrientLabel;

/// Những món bị bỏ khỏi gợi ý, **nhóm theo ba bậc lý do**.
///
/// Bậc giữa là chỗ dễ nói sai nhất, và cũng là lý do màn này tồn tại. Nếu
/// hiện "Phở sốt vang bị loại" giống kiểu "Tôm rang me bị loại", người dùng
/// sẽ tin phở là món cấm với mình — trong khi lý do thật chỉ là sáng nay họ
/// đã ăn mặn. Một món bị chặn vì hạn mức thì **hôm khác vẫn chọn được**, và
/// câu đó phải nằm trên màn hình chứ không nằm trong đầu người viết mã.
class ExcludedScreen extends StatelessWidget {
  const ExcludedScreen({
    super.key,
    required this.screening,
    required this.foods,
  });

  final ScreeningResult screening;

  /// Danh mục để tra tên món theo `id`.
  final List<Food> foods;

  static Future<void> open(
    BuildContext context, {
    required ScreeningResult screening,
    required List<Food> foods,
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ExcludedScreen(screening: screening, foods: foods),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theoBac = screening.byTier;
    final tong = screening.excluded.length;
    final theoId = {for (final f in foods) f.id: f};

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: Text(
          '$tong món bị bỏ qua',
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        children: [
          const Text(
            'Ba lý do khác nhau, và chúng không đổi được như nhau.',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              height: 1.45,
              color: AppColors.textSecondary,
            ),
          ),
          for (final tier in ExclusionTier.values)
            if ((theoBac[tier] ?? const []).isNotEmpty) ...[
              const SizedBox(height: 22),
              _TierSection(
                tier: tier,
                ids: theoBac[tier]!,
                reasons: screening.excluded,
                foodsById: theoId,
              ),
            ],
          const SizedBox(height: 22),
          const _EvidenceLegend(),
        ],
      ),
    );
  }
}

/// Màu và chữ dẫn của mỗi bậc.
///
/// Ba bậc phân biệt bằng **ba kênh** cùng lúc: màu viền, hình biểu tượng, và
/// câu dẫn. Chỉ dùng màu thì người mù màu mất hẳn thông tin, mà đây là thông
/// tin về sức khỏe.
({Color color, IconData icon, String lead}) _tierStyle(ExclusionTier tier) =>
    switch (tier) {
      ExclusionTier.dish => (
        color: AppColors.dislike,
        icon: Icons.cancel_outlined,
        lead:
            'Thuộc tính của chính món ăn. Không phụ thuộc hôm nay bạn đã '
            'ăn gì.',
      ),
      ExclusionTier.dayBudget => (
        color: AppColors.neutral,
        icon: Icons.schedule_rounded,
        lead:
            'Món không có vấn đề gì. Chỉ là hôm nay đã dùng gần hết hạn mức '
            '— hôm khác những món này vẫn hợp.',
      ),
      ExclusionTier.unknown => (
        color: AppColors.unknown,
        icon: Icons.help_outline_rounded,
        lead:
            'Danh mục thiếu số liệu ở chất bị hạn chế, nên hệ thống không '
            'kết luận được. Đây không phải "an toàn".',
      ),
    };

class _TierSection extends StatelessWidget {
  const _TierSection({
    required this.tier,
    required this.ids,
    required this.reasons,
    required this.foodsById,
  });

  final ExclusionTier tier;
  final List<String> ids;
  final Map<String, List<ExclusionReason>> reasons;
  final Map<String, Food> foodsById;

  @override
  Widget build(BuildContext context) {
    final style = _tierStyle(tier);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(style.icon, size: 17, color: style.color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                tier.heading,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            Text(
              '${ids.length} món',
              style: const TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.only(left: 25, top: 4, bottom: 10),
          child: Text(
            style.lead,
            style: const TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w500,
              height: 1.5,
              color: AppColors.textSecondary,
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border(left: BorderSide(color: style.color, width: 3)),
          ),
          child: Column(
            children: [
              for (var i = 0; i < ids.length; i++) ...[
                if (i > 0)
                  const Divider(
                    height: 1,
                    thickness: 1,
                    indent: 14,
                    endIndent: 14,
                    color: AppColors.border,
                  ),
                _ExcludedRow(
                  food: foodsById[ids[i]],
                  reasons: reasons[ids[i]] ?? const [],
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _ExcludedRow extends StatelessWidget {
  const _ExcludedRow({required this.food, required this.reasons});

  final Food? food;
  final List<ExclusionReason> reasons;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 11, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  food?.name ?? 'Món không rõ',
                  style: const TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              if (food != null)
                Text(
                  '${food!.kcal} kcal',
                  style: const TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w500,
                    color: AppColors.textSecondary,
                  ),
                ),
            ],
          ),
          // Mọi lý do đều nêu, không chỉ lý do đầu: sửa được một luật chưa
          // chắc món đó hợp, nên nêu một cái là để người dùng hiểu sai.
          for (final r in reasons) ...[
            const SizedBox(height: 5),
            _ReasonLine(reason: r),
          ],
        ],
      ),
    );
  }
}

class _ReasonLine extends StatelessWidget {
  const _ReasonLine({required this.reason});

  final ExclusionReason reason;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text.rich(
          TextSpan(
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w500,
              height: 1.45,
              color: AppColors.textPrimary,
            ),
            children: _spans(reason),
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 3),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 4, right: 6),
                width: 5,
                height: 5,
                decoration: BoxDecoration(
                  color: reason.evidence.canCite
                      ? AppColors.like
                      : AppColors.unknown,
                  shape: BoxShape.circle,
                ),
              ),
              Expanded(
                child: Text(
                  reason.evidence.label,
                  style: const TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  List<InlineSpan> _spans(ExclusionReason r) {
    const manh = TextStyle(fontWeight: FontWeight.w700);

    if (r.tag != null) {
      return [
        const TextSpan(text: 'Có nhãn '),
        TextSpan(text: r.tag, style: manh),
        TextSpan(text: ' · ${r.condition}'),
      ];
    }

    final ten = nutrientLabel(r.nutrient ?? '').toLowerCase();

    // Thiếu số liệu KHÁC vượt ngưỡng. Nói "món này vượt ngưỡng" khi thật ra
    // là "chúng tôi không biết" là sai sự thật.
    if (r.missingData) {
      return [
        const TextSpan(text: 'Không có số liệu '),
        TextSpan(text: ten, style: manh),
        TextSpan(text: ' nên không đối chiếu được với hạn mức ${r.condition}'),
      ];
    }

    final sodo = formatNumber(r.measured ?? 0);
    if (r.tier == ExclusionTier.dayBudget) {
      final conLai = formatNumber(r.remaining ?? 0);
      return [
        TextSpan(text: '${ten[0].toUpperCase()}${ten.substring(1)} '),
        TextSpan(text: '$sodo ${r.unit}', style: manh),
        TextSpan(text: ', hôm nay còn $conLai ${r.unit}'),
      ];
    }

    return [
      TextSpan(text: '${ten[0].toUpperCase()}${ten.substring(1)} '),
      TextSpan(text: '$sodo ${r.unit}', style: manh),
      TextSpan(text: ', ngưỡng ${formatNumber(r.threshold ?? 0)} ${r.unit}'),
    ];
  }
}

class _EvidenceLegend extends StatelessWidget {
  const _EvidenceLegend();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(13, 11, 13, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.info_outline_rounded,
            size: 14,
            color: AppColors.textSecondary,
          ),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Đốm xanh là luật có nguồn công bố, đốm nâu là ngưỡng do hệ '
              'thống suy ra hoặc chưa có nguồn đang hiệu lực. Hệ thống không '
              'tự ý loại món dựa trên ngưỡng chưa xác minh.',
              style: TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w500,
                height: 1.55,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
