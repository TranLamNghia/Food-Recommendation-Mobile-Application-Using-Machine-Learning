import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// Seven day chips starting today; tapping one switches the plan to that day.
///
/// Starts at today rather than at Monday because nothing behind today can
/// still be planned — past days belong to the diary.
class WeekStrip extends StatelessWidget {
  const WeekStrip({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.hasPlan,
  });

  final DateTime selected;
  final ValueChanged<DateTime> onSelected;

  /// Whether a day already has a plan built, shown as a dot under the date.
  final bool Function(DateTime day) hasPlan;

  static const _short = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);

    return Row(
      children: [
        for (var i = 0; i < 7; i++)
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(left: i == 0 ? 0 : 6),
              child: _DayChip(
                day: today.add(Duration(days: i)),
                label: i == 0
                    ? 'Nay'
                    : _short[today.add(Duration(days: i)).weekday - 1],
                selected: _sameDay(today.add(Duration(days: i)), selected),
                planned: hasPlan(today.add(Duration(days: i))),
                onTap: () => onSelected(today.add(Duration(days: i))),
              ),
            ),
          ),
      ],
    );
  }

  static bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;
}

class _DayChip extends StatelessWidget {
  const _DayChip({
    required this.day,
    required this.label,
    required this.selected,
    required this.planned,
    required this.onTap,
  });

  final DateTime day;
  final String label;
  final bool selected;
  final bool planned;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fg = selected ? AppColors.textOnDark : AppColors.textPrimary;

    return Semantics(
      button: true,
      selected: selected,
      // The label already says the date; the chip's own texts would only
      // repeat it as "T3, 17".
      excludeSemantics: true,
      onTap: onTap,
      label: 'Ngày ${day.day} tháng ${day.month}',
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: AppMotion.quick,
          curve: AppMotion.standard,
          padding: const EdgeInsets.symmetric(vertical: 9),
          decoration: BoxDecoration(
            color: selected ? AppColors.ink : AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: selected ? AppColors.ink : AppColors.border,
            ),
          ),
          child: Column(
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 11.5,
                  color: selected
                      ? AppColors.textOnDark.withValues(alpha: 0.7)
                      : AppColors.textSecondary,
                  fontVariations: const [FontVariation('wght', 600)],
                ),
              ),
              const SizedBox(height: 3),
              Text(
                '${day.day}',
                style: TextStyle(
                  fontSize: 17,
                  height: 1.1,
                  color: fg,
                  fontVariations: const [FontVariation('wght', 700)],
                ),
              ),
              const SizedBox(height: 5),
              Container(
                width: 5,
                height: 5,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: !planned
                      ? Colors.transparent
                      : selected
                      ? AppColors.accent
                      : AppColors.accentInk,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
