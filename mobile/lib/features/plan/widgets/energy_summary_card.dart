import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';
import '../../../data/models/meal_plan.dart';

/// The overview card for the day's energy and three macronutrients.
///
/// The most important number on the card is the **deviation from the
/// target**. The thesis proposal commits to generated plans deviating by no
/// more than 10 %, so that figure has to be immediately visible rather than
/// buried in the statistics.
class EnergySummaryCard extends StatelessWidget {
  const EnergySummaryCard({super.key, required this.plan, this.isToday = true});

  final DailyPlan plan;

  /// `false` when the plan on screen is for another day of the week, so the
  /// headings stop saying "hôm nay".
  final bool isToday;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.border),
        boxShadow: const [
          BoxShadow(
            color: AppColors.shadowSoft,
            blurRadius: 18,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isToday ? 'Năng lượng hôm nay' : 'Năng lượng trong ngày',
                      style: const TextStyle(
                        fontSize: 13.5,
                        color: AppColors.textSecondary,
                        fontVariations: [FontVariation('wght', 600)],
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          formatNumber(plan.actualKcal),
                          style: const TextStyle(
                            fontSize: 34,
                            height: 1,
                            color: AppColors.textPrimary,
                            fontVariations: [FontVariation('wght', 700)],
                          ),
                        ),
                        const SizedBox(width: 6),
                        // Allowed to shrink: a four-digit target plus the
                        // large number to its left can overflow the width on
                        // a narrow device.
                        Flexible(
                          child: Text(
                            '/ ${formatNumber(plan.targetKcal)} kcal',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 15,
                              color: AppColors.textSecondary,
                              fontVariations: [FontVariation('wght', 600)],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              _DeviationBadge(plan: plan),
            ],
          ),
          const SizedBox(height: 18),
          _MacroBars(plan: plan),
        ],
      ),
    );
  }
}

/// The deviation badge. Green within the 10 % threshold, amber past
/// it.
class _DeviationBadge extends StatelessWidget {
  const _DeviationBadge({required this.plan});

  final DailyPlan plan;

  @override
  Widget build(BuildContext context) {
    final ok = plan.withinTolerance;
    final color = ok ? AppColors.like : AppColors.unknown;
    final dev = plan.deviationPct;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            ok ? Icons.check_circle_rounded : Icons.error_outline_rounded,
            size: 15,
            color: color,
          ),
          const SizedBox(width: 5),
          Text(
            '${dev >= 0 ? '+' : '−'}${dev.abs().toStringAsFixed(1)}%',
            style: TextStyle(
              fontSize: 13,
              color: color,
              fontVariations: const [FontVariation('wght', 700)],
            ),
          ),
        ],
      ),
    );
  }
}

/// Three proportion bars for protein, carbohydrate and fat — actual
/// against target.
class _MacroBars extends StatelessWidget {
  const _MacroBars({required this.plan});

  final DailyPlan plan;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _MacroBar(
            label: 'Đạm',
            actual: plan.actualProtein,
            target: plan.targetProtein,
            color: AppColors.protein,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _MacroBar(
            label: 'Bột đường',
            actual: plan.actualCarb,
            target: plan.targetCarb,
            color: AppColors.carb,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _MacroBar(
            label: 'Béo',
            actual: plan.actualFat,
            target: plan.targetFat,
            color: AppColors.fat,
          ),
        ),
      ],
    );
  }
}

class _MacroBar extends StatelessWidget {
  const _MacroBar({
    required this.label,
    required this.actual,
    required this.target,
    required this.color,
  });

  final String label;
  final double actual;
  final double target;
  final Color color;

  @override
  Widget build(BuildContext context) {
    // A bar can exceed 100 %, but the drawing is clipped at 1.0 so it does
    // not spill outside its frame. The number below it is what states the
    // real overshoot.
    final ratio = target <= 0 ? 0.0 : (actual / target).clamp(0.0, 1.0);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.textSecondary,
            fontVariations: [FontVariation('wght', 600)],
          ),
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: ratio),
            duration: AppMotion.page,
            curve: AppMotion.emphasized,
            builder: (context, value, _) => LinearProgressIndicator(
              value: value,
              minHeight: 5,
              backgroundColor: AppColors.surfaceMuted,
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
        ),
        const SizedBox(height: 5),
        Text(
          '${formatNumber(actual)}/${formatNumber(target)}g',
          style: const TextStyle(
            fontSize: 11.5,
            color: AppColors.textTertiary,
            fontVariations: [FontVariation('wght', 600)],
          ),
        ),
      ],
    );
  }
}
