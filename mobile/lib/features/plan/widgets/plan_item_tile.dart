import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/meal_plan.dart';

/// Một suất món trong thực đơn.
///
/// Thẻ hiển thị ba thứ người dùng cần để quyết định giữ hay đổi: món là gì,
/// nó tốn bao nhiêu năng lượng, và vì sao hệ thống nghĩ họ sẽ thích nó.
class PlanItemTile extends StatelessWidget {
  const PlanItemTile({
    super.key,
    required this.item,
    required this.onReplace,
    required this.onEat,
  });

  final MealPlanItem item;
  final VoidCallback onReplace;
  final VoidCallback onEat;

  @override
  Widget build(BuildContext context) {
    final food = item.food;
    final eaten = item.status == MealItemStatus.eaten;

    return Opacity(
      opacity: eaten ? 0.6 : 1,
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
                      '${food.kcal} kcal · ${food.dishRole} · ${food.cookingMethod}',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                        fontVariations: [FontVariation('wght', 500)],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        // Nhãn nằm trong [Wrap] có thể co lại: tên món dài
                        // hoặc màn hình hẹp thì chúng xuống dòng, thay vì đẩy
                        // hai nút hành động tràn ra khỏi thẻ.
                        Expanded(
                          child: Wrap(
                            spacing: 6,
                            runSpacing: 6,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              _ScoreChip(score: item.score),
                              if (item.isExploration) const _ExplorationChip(),
                            ],
                          ),
                        ),
                        if (!eaten) ...[
                          const SizedBox(width: 8),
                          _MiniButton(
                            icon: Icons.swap_horiz_rounded,
                            tooltip: 'Đổi món khác',
                            onTap: onReplace,
                          ),
                          const SizedBox(width: 6),
                          _MiniButton(
                            icon: Icons.restaurant_rounded,
                            tooltip: 'Đánh dấu đã ăn',
                            onTap: onEat,
                            filled: true,
                          ),
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
                  // Ảnh tạm dùng chung cho nhiều món nên phủ một lớp gradient
                  // mờ để thẻ vẫn phân biệt được bằng màu.
                  color: food.gradient.last.withValues(alpha: 0.25),
                  colorBlendMode: BlendMode.overlay,
                ),
        ),
      ),
    );
  }
}

/// Điểm mức độ phù hợp do bước chấm điểm sinh ra.
///
/// Hiển thị thẳng con số thay vì giấu đi: đây là phần giải thích được của
/// mô hình, và cũng là thứ cần đối chiếu khi so sánh với phương án chỉ dùng
/// quy tắc dinh dưỡng ở chương thực nghiệm.
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

/// Nhãn cho suất thăm dò của cơ chế 70-30.
///
/// Nói thẳng với người dùng rằng đây là món hệ thống muốn thử, để họ hiểu
/// vì sao thực đơn có một món hơi lệch gu — và để khi họ đổi nó đi thì đó
/// là phản hồi có ý thức chứ không phải bực bội.
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
