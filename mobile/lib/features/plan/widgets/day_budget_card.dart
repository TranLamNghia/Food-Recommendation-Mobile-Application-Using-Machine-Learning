import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_colors.dart';
import '../../../data/rules/day_budget.dart';

/// Hạn mức còn lại của hôm nay.
///
/// Đặt trên màn thực đơn, **trước** khi nó chặn món nào. Một ràng buộc phụ
/// thuộc trạng thái mà chỉ xuất hiện lúc báo lỗi thì luôn làm người ta bất
/// ngờ: nếu người dùng chỉ thấy "món này bị loại" sau khi đã ăn mặn cả buổi
/// sáng, họ không có cách nào hiểu vì sao.
class DayBudgetCard extends StatelessWidget {
  const DayBudgetCard({super.key, required this.budget});

  final DayBudget budget;

  @override
  Widget build(BuildContext context) {
    final hard = budget.hard;
    final overSoft = budget.overRecommendation;
    if (hard.isEmpty && overSoft.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                hard.isEmpty
                    ? Icons.info_outline_rounded
                    : Icons.schedule_rounded,
                size: 17,
                color: hard.isEmpty ? AppColors.unknown : AppColors.neutral,
              ),
              const SizedBox(width: 8),
              Text(
                // Tiêu đề theo nội dung thật: chỉ có ngưỡng mềm thì không
                // có "hạn mức còn lại" nào, chỉ có khuyến cáo.
                hard.isEmpty ? 'Khuyến cáo hôm nay' : 'Hạn mức còn lại hôm nay',
                style: const TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ],
          ),
          for (final limit in hard) ...[
            const SizedBox(height: 14),
            _LimitBar(limit: limit),
          ],
          for (final limit in overSoft) ...[
            const SizedBox(height: 14),
            _SoftOverRow(limit: limit),
          ],
        ],
      ),
    );
  }
}

class _LimitBar extends StatelessWidget {
  const _LimitBar({required this.limit});

  final DayLimit limit;

  @override
  Widget build(BuildContext context) {
    final sapHet = limit.ratio >= 0.85;
    final mau = limit.exceeded
        ? AppColors.dislike
        : sapHet
        ? AppColors.unknown
        : AppColors.textSecondary;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Text(
                nutrientLabel(limit.nutrient),
                style: const TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w500,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            Text(
              '${formatNumber(limit.used)} / ${formatNumber(limit.amount)} '
              '${limit.unit}',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                color: mau,
              ),
            ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: limit.ratio.clamp(0.0, 1.0),
            minHeight: 7,
            backgroundColor: AppColors.surfaceMuted,
            valueColor: AlwaysStoppedAnimation(mau),
          ),
        ),
        const SizedBox(height: 5),
        Text(
          limit.exceeded
              ? 'Đã vượt ${formatNumber(-limit.remaining)} ${limit.unit} '
                    '— ${limit.condition}'
              : 'Còn ${formatNumber(limit.remaining)} ${limit.unit} '
                    '— ${limit.condition}',
          style: const TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w500,
            color: AppColors.textSecondary,
          ),
        ),
        _EvidenceLine(limit: limit),
        if (!limit.dataComplete) _IncompleteDataLine(limit: limit),
      ],
    );
  }
}

/// Xuất xứ của ngưỡng, kèm dấu phân biệt mức tin cậy.
///
/// Một ứng dụng sức khỏe dẫn khuyến cáo của WHO và một con số chưa ai tra
/// bằng cùng một giọng là không trung thực, nên mức tin cậy phải nhìn thấy
/// được — và không chỉ bằng màu: mỗi mức có **chữ** riêng, vì màu một mình
/// thì người mù màu không đọc được.
class _EvidenceLine extends StatelessWidget {
  const _EvidenceLine({required this.limit});

  final DayLimit limit;

  @override
  Widget build(BuildContext context) {
    final citable = limit.evidence.canCite;
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 4.5, right: 6),
            width: 5,
            height: 5,
            decoration: BoxDecoration(
              color: citable ? AppColors.like : AppColors.unknown,
              shape: BoxShape.circle,
            ),
          ),
          Expanded(
            child: Text(
              '${limit.evidence.label}'
              '${limit.note.isEmpty ? '' : ' — ${limit.note}'}',
              style: const TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w500,
                height: 1.4,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Cảnh báo rằng con số phía trên **nới hơn thực tế**.
///
/// Bảng thành phần chỉ công bố purin cho 70 trong 318 món. Cộng những món
/// khuyết thành 0 rồi hiện một con số trông bình thường sẽ làm trần purin
/// của người gút gần như không bao giờ chạm tới — một tầng an toàn thất bại
/// theo hướng **mở** mà không báo gì.
class _IncompleteDataLine extends StatelessWidget {
  const _IncompleteDataLine({required this.limit});

  final DayLimit limit;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 7),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.help_outline_rounded,
            size: 13,
            color: AppColors.textSecondary,
          ),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              '${limit.missingCount} món không có số liệu '
              '${nutrientLabel(limit.nutrient).toLowerCase()}, nên con số '
              'trên thấp hơn thực tế.',
              style: const TextStyle(
                fontSize: 10.5,
                fontWeight: FontWeight.w500,
                height: 1.45,
                color: AppColors.textSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Hạn mức **mềm** đã bị vượt — "vượt khuyến cáo", không phải "bị loại".
class _SoftOverRow extends StatelessWidget {
  const _SoftOverRow({required this.limit});

  final DayLimit limit;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(
          Icons.info_outline_rounded,
          size: 14,
          color: AppColors.unknown,
        ),
        const SizedBox(width: 7),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Vượt khuyến cáo ${nutrientLabel(limit.nutrient).toLowerCase()}'
                ' — ${formatNumber(limit.used)}/${formatNumber(limit.amount)} '
                '${limit.unit}',
                style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: AppColors.unknown,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'Chỉ là khuyến cáo nên không món nào bị chặn. '
                '${limit.condition}.',
                style: const TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.w500,
                  height: 1.45,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Tên chất để hiện ra, từ tên cột trong CSDL.
String nutrientLabel(String nutrient) => switch (nutrient) {
  'calories_kcal' => 'Năng lượng',
  'protein_g' => 'Đạm',
  'carbs_g' => 'Bột đường',
  'fat_g' => 'Chất béo',
  'sugar_g' => 'Đường',
  'sodium_mg' => 'Natri',
  'fiber_g' => 'Chất xơ',
  'purine_mg' => 'Purin',
  _ => nutrient,
};
