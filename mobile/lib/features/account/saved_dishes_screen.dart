import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../data/models/food.dart';
import '../../data/session.dart';
import '../food/food_detail_screen.dart';

enum SavedKind { loved, neverAgain }

/// The dishes the user hearted, or the ones they ruled out for good.
///
/// Every exclusion has to be visible and reversible somewhere: a dish that
/// silently never comes back looks like a gap in the catalogue.
class SavedDishesScreen extends StatelessWidget {
  const SavedDishesScreen({super.key, required this.kind});

  final SavedKind kind;

  static Future<void> open(BuildContext context, SavedKind kind) =>
      Navigator.of(
        context,
      ).push(MaterialPageRoute(builder: (_) => SavedDishesScreen(kind: kind)));

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final loved = kind == SavedKind.loved;
    final ids = loved ? session.lovedIds : session.neverAgainIds;
    final foods = [
      for (final f in session.candidates)
        if (ids.contains(f.id)) f,
    ];

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        title: Text(
          loved ? 'Món yêu thích' : 'Không gợi ý nữa',
          style: Theme.of(context).textTheme.titleLarge,
        ),
      ),
      body: foods.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(40),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      loved
                          ? Icons.favorite_border_rounded
                          : Icons.block_rounded,
                      size: 44,
                      color: AppColors.textTertiary,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      loved ? 'Chưa có món nào' : 'Chưa loại món nào',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      loved
                          ? 'Chạm vào một món trong thực đơn rồi bấm trái tim '
                                'để lưu lại.'
                          : 'Mở một món và bật "Không gợi ý món này nữa" để '
                                'loại nó khỏi mọi thực đơn sắp tới.',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
              itemCount: foods.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) => _SavedTile(
                food: foods[i],
                removeTooltip: loved ? 'Bỏ yêu thích' : 'Cho gợi ý lại',
                onOpen: () => FoodDetailScreen.open(context, foods[i]),
                onRemove: () => loved
                    ? session.toggleLoved(foods[i])
                    : session.setNeverAgain(foods[i], false),
              ),
            ),
    );
  }
}

class _SavedTile extends StatelessWidget {
  const _SavedTile({
    required this.food,
    required this.removeTooltip,
    required this.onOpen,
    required this.onRemove,
  });

  final Food food;
  final String removeTooltip;
  final VoidCallback onOpen;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 10, 4, 10),
          child: Row(
            children: [
              Container(
                width: 52,
                height: 52,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  gradient: LinearGradient(
                    colors: food.gradient,
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                ),
                child: Text(food.emoji, style: const TextStyle(fontSize: 24)),
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
                        fontSize: 15.5,
                        color: AppColors.textPrimary,
                        fontVariations: [FontVariation('wght', 700)],
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${food.kcal} kcal · ${food.category}',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: removeTooltip,
                onPressed: onRemove,
                icon: const Icon(Icons.close_rounded, size: 20),
                color: AppColors.textSecondary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
