import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/dish_look.dart';
import '../../data/api/failure.dart';
import '../../data/api/food_api.dart';
import '../../data/models/food_brief.dart';
import '../../data/session.dart';
import '../food/food_detail_screen.dart';

enum SavedKind { loved, neverAgain }

/// The dishes the user bookmarked, or the ones they ruled out for good.
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
    // The dishes the session holds for this mark, not the catalogue filtered
    // by their ids. That is what the old version did, and online the ids are
    // the server's UUIDs while `candidates` is the mock deck: nothing
    // matched, so the account screen read "3 mon" and this list under it was
    // blank — the marks stored, enforced, and unreachable.
    final foods = session.savedDishes(
      loved ? FoodMark.loved : FoodMark.blocked,
    );

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        title: Text(
          loved ? 'Món đã lưu' : 'Không gợi ý nữa',
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
                          ? Icons.bookmark_border_rounded
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
                          ? 'Chạm vào một món trong thực đơn rồi bấm dấu '
                                'trang để lưu lại.'
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
                removeTooltip: loved
                    ? 'Bỏ khỏi món đã lưu'
                    : 'Cho gợi ý lại',
                onOpen: () => FoodDetailScreen.open(context, foods[i]),
                // Neither of these two can be refused — only ADDING a block
                // can be, when it would empty a meal — so the only thing
                // that can go wrong here is the network, and it still has to
                // be said rather than leaving the row sitting there.
                onRemove: () async {
                  try {
                    if (loved) {
                      await session.toggleLoved(foods[i]);
                    } else {
                      await session.setNeverAgain(foods[i], false);
                    }
                  } on ApiFailure catch (failure) {
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(failure.message),
                        duration: const Duration(seconds: 3),
                      ),
                    );
                  }
                },
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

  final FoodBrief food;
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
