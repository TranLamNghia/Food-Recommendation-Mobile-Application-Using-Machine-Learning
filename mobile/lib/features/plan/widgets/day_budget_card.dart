import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_colors.dart';
import '../../../data/rules/day_budget.dart';

/// What is left of today's allowances.
///
/// Placed on the plan screen **before** it blocks anything. A state-dependent
/// constraint that only appears at the moment it rejects something always
/// takes people by surprise: a user who only sees "this dish was dropped"
/// after a salty morning has no way of understanding why.
class DayBudgetCard extends StatelessWidget {
  const DayBudgetCard({super.key, required this.budget, this.isToday = true});

  final DayBudget budget;

  /// `false` when the plan on screen is for another day of the week, so the
  /// headings stop saying "hôm nay".
  final bool isToday;

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
                // The heading follows the real content: with only soft
                // thresholds there is no "allowance left" at all, only a
                // recommendation.
                hard.isEmpty
                    ? (isToday ? 'Khuyến cáo hôm nay' : 'Khuyến cáo trong ngày')
                    : (isToday
                          ? 'Hạn mức còn lại hôm nay'
                          : 'Hạn mức còn lại trong ngày'),
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

/// The threshold's provenance, with a marker for its evidence level.
///
/// A health app quoting a WHO recommendation and a number nobody has checked
/// in the same voice is not honest, so the evidence level has to be visible —
/// and not through colour alone: each level has its own **wording**, because
/// colour by itself is unreadable to a colour-blind user.
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

/// Warns that the number above is **more permissive than reality**.
///
/// The composition table only publishes purine for 70 of 318 dishes. Adding
/// the ones with no data up as 0 and showing a normal-looking number would
/// mean a gout patient's purine ceiling is almost never reached — a safety
/// layer failing **open** with no warning.
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

/// A **soft** allowance already exceeded — "over the recommendation",
/// not "excluded".
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

/// The nutrient's display name, from its column name in the database.
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
