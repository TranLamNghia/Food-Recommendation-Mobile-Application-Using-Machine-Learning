import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/food.dart';
import '../../../core/format.dart';
import '../../../data/models/meal_plan.dart';
import '../../../data/rules/day_budget.dart';
import 'day_budget_card.dart' show nutrientLabel;

/// The replacement sheet, opened from the swap button on a serving.
///
/// The list is ordered by descending preference score and holds only dishes
/// in the **same role** as the serving being replaced — a soup has to be
/// swapped for a soup, or the meal's structure breaks after a single user
/// action.
class ReplaceSheet extends StatelessWidget {
  const ReplaceSheet({
    super.key,
    required this.item,
    required this.alternatives,
    required this.scoreOf,
    this.budgetAfterRemoval = const DayBudget(),
  });

  final MealPlanItem item;
  final List<Food> alternatives;
  final double Function(Food) scoreOf;

  /// The allowance left **after the dish being replaced is taken out**.
  ///
  /// It has to be the allowance with the old dish subtracted, not the current
  /// one: the room for a replacement includes what the old dish takes up.
  /// With the unsubtracted allowance this sheet blocks dishes that ought to
  /// be selectable — including the very dish sitting in the plan.
  final DayBudget budgetAfterRemoval;

  /// Opens the sheet and returns the dish the user chose, or `null` if
  /// they dismissed it.
  static Future<Food?> show(
    BuildContext context, {
    required MealPlanItem item,
    required List<Food> alternatives,
    required double Function(Food) scoreOf,
    DayBudget budgetAfterRemoval = const DayBudget(),
  }) {
    return showModalBottomSheet<Food>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => ReplaceSheet(
        item: item,
        alternatives: alternatives,
        scoreOf: scoreOf,
        budgetAfterRemoval: budgetAfterRemoval,
      ),
    );
  }

  /// The first HARD allowance [food] does not fit, or `null` if it fits
  /// them all.
  ///
  /// A dish with no measurement for a restricted nutrient returns `null` — it
  /// is not blocked, but [_AlternativeTile] shows a note of its own. Blocking
  /// a dish because the catalogue is incomplete penalises the wrong party;
  /// letting it through in silence loosens the allowance. So: let it through,
  /// and say so.
  DayLimit? _blockingLimit(Food food) {
    for (final l in budgetAfterRemoval.hard) {
      final value = DayBudget.valueOf(food, l.nutrient);
      if (value == null) continue;
      if (!l.fits(value)) return l;
    }
    return null;
  }

  /// Candidates that fit come first; within each group the existing
  /// score order is kept.
  List<Food> get _ordered {
    final vua = <Food>[];
    final khong = <Food>[];
    for (final f in alternatives) {
      (_blockingLimit(f) == null ? vua : khong).add(f);
    }
    return [...vua, ...khong];
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.72,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 10),
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.border,
                borderRadius: BorderRadius.circular(999),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Đổi ${item.food.name.toLowerCase()}',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Chỉ hiện món cùng vai trò "${item.food.dishRole.toLowerCase()}" '
                    'để bữa ăn giữ nguyên cấu trúc. Xếp theo mức hợp gu của bạn.',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
            if (budgetAfterRemoval.hard.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                child: _BudgetStrip(budget: budgetAfterRemoval),
              ),
            if (alternatives.isEmpty)
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 28, 20, 34),
                child: Text(
                  'Kho món hiện chưa còn lựa chọn nào khác cùng vai trò. '
                  'Khi tập dữ liệu mở rộng lên 300–500 món thì mục này sẽ '
                  'luôn có phương án thay thế.',
                  style: TextStyle(
                    fontSize: 14,
                    height: 1.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              )
            else
              Flexible(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
                  itemCount: _ordered.length,
                  itemBuilder: (context, i) {
                    final food = _ordered[i];
                    final chan = _blockingLimit(food);
                    return _AlternativeTile(
                      food: food,
                      score: scoreOf(food),
                      deltaKcal: food.kcal - item.food.kcal,
                      blocking: chan,
                      budget: budgetAfterRemoval,
                      // A dish that does not fit is NOT tappable, but it
                      // is still shown with its reason: hidden, the user
                      // would never learn that the dish they wanted is
                      // selectable on another day.
                      onTap: chan == null
                          ? () => Navigator.of(context).pop(food)
                          : null,
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _AlternativeTile extends StatelessWidget {
  const _AlternativeTile({
    required this.food,
    required this.score,
    required this.deltaKcal,
    required this.blocking,
    required this.budget,
    required this.onTap,
  });

  final Food food;
  final double score;
  final int deltaKcal;

  /// The allowance that makes this dish unselectable today, or `null`
  /// if it is selectable.
  final DayLimit? blocking;

  final DayBudget budget;

  /// `null` means not tappable.
  final VoidCallback? onTap;

  /// The restricted nutrients this dish has no measurement for.
  List<String> get _missing => [
    for (final l in budget.hard)
      if (DayBudget.valueOf(food, l.nutrient) == null) l.nutrient,
  ];

  @override
  Widget build(BuildContext context) {
    final chan = blocking;
    final mo = chan != null;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Opacity(
        // Dimmed rather than hidden: hiding a dish that does not fit means
        // the user never learns it is selectable on another day.
        opacity: mo ? 0.55 : 1,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 6),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(11),
                child: Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: food.gradient,
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                  alignment: Alignment.center,
                  child: Text(food.emoji, style: const TextStyle(fontSize: 21)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      food.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        color: AppColors.textPrimary,
                        fontVariations: [FontVariation('wght', 700)],
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      // The energy difference against the dish being
                      // replaced is what decides whether the plan still
                      // meets its target after the swap.
                      '${food.kcal} kcal · '
                      '${deltaKcal >= 0 ? '+' : '−'}${deltaKcal.abs()} so với món cũ',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    if (chan != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Text(
                          '${nutrientLabel(chan.nutrient)} '
                          '${formatNumber(DayBudget.valueOf(food, chan.nutrient) ?? 0)} '
                          '${chan.unit}, vượt phần còn lại '
                          '${formatNumber((DayBudget.valueOf(food, chan.nutrient) ?? 0) - chan.remaining)} '
                          '${chan.unit} — hôm khác chọn được',
                          style: const TextStyle(
                            fontSize: 11.5,
                            height: 1.4,
                            fontWeight: FontWeight.w600,
                            color: AppColors.neutral,
                          ),
                        ),
                      )
                    else if (_missing.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Text(
                          'Chưa có số liệu '
                          '${_missing.map((n) => nutrientLabel(n).toLowerCase()).join(', ')}'
                          ' — không đối chiếu được hạn mức',
                          style: const TextStyle(
                            fontSize: 11.5,
                            height: 1.4,
                            fontWeight: FontWeight.w500,
                            color: AppColors.unknown,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              if (mo)
                const Icon(
                  Icons.schedule_rounded,
                  size: 17,
                  color: AppColors.neutral,
                )
              else
                Text(
                  '${(score * 100).round()}%',
                  style: const TextStyle(
                    fontSize: 14,
                    color: AppColors.primaryDark,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The strip of remaining allowances for a replacement dish.
///
/// It shows **every** hard allowance side by side, not just the tightest one:
/// a dish can be excellent on the nutrient that is short and still be blocked
/// by another. Steamed tofu has 14 mg of sodium — the lowest in the catalogue
/// — but its 136 mg of purine exceeds what a gout patient has left. Ranking
/// by one nutrient and concluding from that is wrong.
class _BudgetStrip extends StatelessWidget {
  const _BudgetStrip({required this.budget});

  final DayBudget budget;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 11),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Bỏ món cũ ra, món thay thế được dùng:',
            style: TextStyle(
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 7),
          // `Wrap` rather than `Row`: the two columns "1.200 mg / natri ·
          // Tăng huyết áp" overflow by 24 px at a width of 412. The HTML
          // mock-up never exposed this, because it was only ever drawn at one
          // single width.
          Wrap(
            spacing: 18,
            runSpacing: 8,
            children: [
              for (final l in budget.hard)
                Padding(
                  padding: EdgeInsets.zero,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${formatNumber(l.remaining)} ${l.unit}',
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      Text(
                        '${nutrientLabel(l.nutrient).toLowerCase()} · '
                        '${l.condition}',
                        style: const TextStyle(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w500,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          if (budget.hard.length > 1)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                'Món phải vừa cả hai — vừa một bên là chưa đủ.',
                style: TextStyle(
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
