import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/food.dart';
import '../../../data/models/meal_plan.dart';

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
  });

  final MealPlanItem item;
  final List<Food> alternatives;
  final double Function(Food) scoreOf;

  /// Mở bảng và trả về món người dùng chọn, `null` nếu họ đóng bảng.
  static Future<Food?> show(
    BuildContext context, {
    required MealPlanItem item,
    required List<Food> alternatives,
    required double Function(Food) scoreOf,
  }) {
    return showModalBottomSheet<Food>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => ReplaceSheet(
        item: item,
        alternatives: alternatives,
        scoreOf: scoreOf,
      ),
    );
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
                  itemCount: alternatives.length,
                  itemBuilder: (context, i) {
                    final food = alternatives[i];
                    return _AlternativeTile(
                      food: food,
                      score: scoreOf(food),
                      deltaKcal: food.kcal - item.food.kcal,
                      onTap: () => Navigator.of(context).pop(food),
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
    required this.onTap,
  });

  final Food food;
  final double score;
  final int deltaKcal;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
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
                ],
              ),
            ),
            const SizedBox(width: 10),
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
    );
  }
}
