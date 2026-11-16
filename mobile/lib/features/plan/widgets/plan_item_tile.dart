import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/meal_plan.dart';

/// One dish serving in the plan.
///
/// The tile shows the three things a user needs in order to decide whether to
/// keep it or swap it: what the dish is, how much energy it costs, and why
/// the system thinks they will like it.
class PlanItemTile extends StatelessWidget {
  const PlanItemTile({
    super.key,
    required this.item,
    required this.onReplace,
    required this.onEat,
    this.onOpen,
    this.onSkip,
    this.onRestore,
  });

  final MealPlanItem item;
  final VoidCallback onReplace;

  /// `null` hides the button — a day that has not come yet cannot be eaten.
  final VoidCallback? onEat;

  /// Tapping the tile body opens the dish.
  final VoidCallback? onOpen;

  /// Skip this serving (eating out, not hungry).
  final VoidCallback? onSkip;

  /// Put a skipped serving back.
  final VoidCallback? onRestore;

  @override
  Widget build(BuildContext context) {
    final food = item.food;
    final eaten = item.status == MealItemStatus.eaten;
    final skipped = item.status == MealItemStatus.skipped;

    return Opacity(
      opacity: eaten || skipped ? 0.6 : 1,
      child: GestureDetector(
        onTap: onOpen,
        behavior: HitTestBehavior.opaque,
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: eaten
                  ? AppColors.like.withValues(alpha: 0.4)
                  : AppColors.border,
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Thumbnail(item: item),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              food.name,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 15.5,
                                height: 1.25,
                                color: AppColors.textPrimary,
                                fontVariations: [FontVariation('wght', 700)],
                              ),
                            ),
                          ),
                          if (eaten)
                            const Icon(
                              Icons.check_circle_rounded,
                              size: 18,
                              color: AppColors.like,
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${food.kcal} kcal · ${food.dishRole} · ${food.category}',
                        style: const TextStyle(
                          fontSize: 12.5,
                          color: AppColors.textSecondary,
                          fontVariations: [FontVariation('wght', 500)],
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          // The labels sit in a [Wrap] so they can give
                          // way: with a long dish name or a narrow screen
                          // they move onto another line instead of pushing
                          // the two action buttons out of the tile.
                          Expanded(
                            child: Wrap(
                              spacing: 6,
                              runSpacing: 6,
                              crossAxisAlignment: WrapCrossAlignment.center,
                              children: [
                                if (skipped)
                                  const _SkippedChip()
                                else
                                  _ScoreChip(score: item.score),
                                if (item.isExploration && !skipped)
                                  const _ExplorationChip(),
                              ],
                            ),
                          ),
                          if (skipped && onRestore != null) ...[
                            const SizedBox(width: 8),
                            _MiniButton(
                              icon: Icons.undo_rounded,
                              tooltip: 'Ăn lại suất này',
                              onTap: onRestore!,
                            ),
                          ],
                          if (!eaten && !skipped) ...[
                            if (onSkip != null) ...[
                              const SizedBox(width: 8),
                              _MiniButton(
                                icon: Icons.not_interested_rounded,
                                tooltip: 'Bỏ qua suất này',
                                onTap: onSkip!,
                              ),
                            ],
                            const SizedBox(width: 6),
                            _MiniButton(
                              icon: Icons.swap_horiz_rounded,
                              tooltip: 'Đổi món khác',
                              onTap: onReplace,
                            ),
                            if (onEat != null) ...[
                              const SizedBox(width: 6),
                              _MiniButton(
                                icon: Icons.restaurant_rounded,
                                tooltip: 'Đánh dấu đã ăn',
                                onTap: onEat!,
                                filled: true,
                              ),
                            ],
                          ],
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SkippedChip extends StatelessWidget {
  const _SkippedChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(999),
      ),
      child: const Text(
        'Đã bỏ qua',
        style: TextStyle(
          fontSize: 11.5,
          color: AppColors.textSecondary,
          fontVariations: [FontVariation('wght', 700)],
        ),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.item});

  final MealPlanItem item;

  @override
  Widget build(BuildContext context) {
    final food = item.food;

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: 62,
        height: 62,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: food.gradient,
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: food.imageAsset == null
              ? Center(
                  child: Text(food.emoji, style: const TextStyle(fontSize: 26)),
                )
              : Image.asset(
                  food.imageAsset!,
                  fit: BoxFit.cover,
                  // The placeholder image is shared across several
                  // dishes, so a translucent gradient is laid over it to keep
                  // the tiles distinguishable by colour.
                  color: food.gradient.last.withValues(alpha: 0.25),
                  colorBlendMode: BlendMode.overlay,
                ),
        ),
      ),
    );
  }
}

/// The suitability score produced by the scoring step.
///
/// The number is shown outright rather than hidden: this is the explainable
/// part of the model, and it is also what has to be compared against the
/// nutrition-rules-only variant in the experiment chapter.
class _ScoreChip extends StatelessWidget {
  const _ScoreChip({required this.score});

  final double score;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        'Hợp gu ${(score * 100).round()}%',
        style: const TextStyle(
          fontSize: 11.5,
          color: AppColors.primaryDark,
          fontVariations: [FontVariation('wght', 700)],
        ),
      ),
    );
  }
}

/// The label for an exploration serving of the 70-30 mechanism.
///
/// It tells the user plainly that this is a dish the system wants to try, so
/// they understand why the plan holds something slightly off their taste —
/// and so that swapping it away is considered feedback rather than
/// irritation.
class _ExplorationChip extends StatelessWidget {
  const _ExplorationChip();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.neutral.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.auto_awesome_rounded, size: 11, color: AppColors.neutral),
          SizedBox(width: 4),
          Text(
            'Thử mới',
            style: TextStyle(
              fontSize: 11.5,
              color: AppColors.neutral,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
        ],
      ),
    );
  }
}

class _MiniButton extends StatelessWidget {
  const _MiniButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.filled = false,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          width: 34,
          height: 30,
          decoration: BoxDecoration(
            color: filled ? AppColors.ink : AppColors.surfaceMuted,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(
            icon,
            size: 17,
            color: filled ? AppColors.textOnDark : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}
