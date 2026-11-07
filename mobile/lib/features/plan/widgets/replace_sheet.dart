import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/food.dart';
import '../../../core/format.dart';
import '../../../data/models/meal_plan.dart';
import '../../../data/rules/day_budget.dart';
import 'day_budget_card.dart' show nutrientLabel;

/// Bảng chọn món thay thế, mở từ nút đổi món trên một suất.
///
/// Danh sách xếp theo điểm ưa thích giảm dần và chỉ gồm món **cùng vai trò**
/// với suất đang thay — đổi món canh phải ra món canh, nếu không cấu trúc
/// bữa ăn sẽ vỡ ngay sau một thao tác của người dùng.
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

  /// Hạn mức còn lại **sau khi bỏ món đang thay ra**.
  ///
  /// Phải là hạn mức đã trừ món cũ, không phải hạn mức hiện tại: dư địa cho
  /// món thay thế gồm cả phần món cũ đang chiếm. Dùng hạn mức chưa trừ thì
  /// bảng này chặn cả những món đáng ra chọn được — kể cả chính món đang
  /// nằm trong thực đơn.
  final DayBudget budgetAfterRemoval;

  /// Mở bảng và trả về món người dùng chọn, `null` nếu họ đóng bảng.
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

  /// Hạn mức CỨNG đầu tiên mà [food] không vừa, `null` nếu vừa hết.
  ///
  /// Món thiếu số liệu ở một chất bị hạn chế trả về `null` — nó không bị
  /// chặn, nhưng [_AlternativeTile] hiện ghi chú riêng. Chặn một món vì danh
  /// mục thiếu số liệu là phạt sai đối tượng; im lặng cho qua thì lại nới
  /// hạn mức. Nên: cho qua, và nói ra.
  DayLimit? _blockingLimit(Food food) {
    for (final l in budgetAfterRemoval.hard) {
      final value = DayBudget.valueOf(food, l.nutrient);
      if (value == null) continue;
      if (!l.fits(value)) return l;
    }
    return null;
  }

  /// Ứng viên vừa hạn mức xếp trước, trong mỗi nhóm giữ thứ tự điểm đã có.
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
                      // Món không vừa hạn mức thì KHÔNG bấm được, nhưng vẫn
                      // hiện kèm lý do: ẩn nó đi thì người dùng không bao giờ
                      // biết món mình muốn vẫn chọn được vào hôm khác.
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

  /// Hạn mức khiến món này không chọn được hôm nay, `null` nếu chọn được.
  final DayLimit? blocking;

  final DayBudget budget;

  /// `null` nghĩa là không bấm được.
  final VoidCallback? onTap;

  /// Chất bị hạn chế mà món này không có số liệu.
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
        // Mờ đi chứ không ẩn: ẩn món không vừa thì người dùng không bao giờ
        // biết món mình muốn vẫn chọn được vào hôm khác.
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
                    // Chênh lệch năng lượng so với món đang thay là thứ quyết
                    // định thực đơn có còn khớp hạn mức sau khi đổi hay không.
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

/// Dải hạn mức còn lại cho món thay thế.
///
/// Hiện **mọi** hạn mức cứng cạnh nhau, không chỉ cái chặt nhất: một món có
/// thể rất tốt ở chất đang thiếu mà vẫn bị chặn bởi chất khác. Đậu phụ hấp
/// có natri 14 mg — thấp nhất danh mục — nhưng purin 136 mg thì vượt phần
/// purin còn lại của người gút. Xếp hạng theo một chất rồi kết luận là sai.
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
          // `Wrap` chứ không `Row`: hai cột "1.200 mg / natri · Tăng huyết
          // áp" tràn 24 px ở bề ngang 412. Bản mockup HTML không lộ ra lỗi
          // này vì nó được vẽ ở đúng một bề ngang.
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
