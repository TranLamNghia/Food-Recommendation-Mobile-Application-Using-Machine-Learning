import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../data/mock/mock_ingredients.dart';
import '../../data/models/food.dart';
import '../../data/session.dart';

/// Everything known about one dish: picture, energy, the nutrients the rules
/// act on, what goes into it, and the two verdicts the user can leave on it.
///
/// Opened by tapping a dish anywhere it appears. Mirrors `GET /foods/{id}`,
/// except for the ingredient block, which has no server source yet.
class FoodDetailScreen extends StatelessWidget {
  const FoodDetailScreen({super.key, required this.food});

  final Food food;

  static Future<void> open(BuildContext context, Food food) => Navigator.of(
    context,
  ).push(MaterialPageRoute(builder: (_) => FoodDetailScreen(food: food)));

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final loved = session.lovedIds.contains(food.id);
    final banned = session.neverAgainIds.contains(food.id);
    final ingredients = MockIngredients.of(food.id);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: 260,
            backgroundColor: AppColors.surface,
            surfaceTintColor: Colors.transparent,
            foregroundColor: AppColors.textPrimary,
            leading: _RoundButton(
              icon: Icons.arrow_back_rounded,
              tooltip: 'Quay lại',
              onTap: () => Navigator.of(context).pop(),
            ),
            actions: [
              _RoundButton(
                icon: loved
                    ? Icons.favorite_rounded
                    : Icons.favorite_border_rounded,
                color: loved ? AppColors.dislike : AppColors.textPrimary,
                tooltip: loved ? 'Bỏ yêu thích' : 'Yêu thích món này',
                onTap: () => session.toggleLoved(food),
              ),
              const SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(background: _Hero(food: food)),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            sliver: SliverList.list(
              children: [
                Text(
                  food.name,
                  style: const TextStyle(
                    fontFamily: AppTheme.fontDisplay,
                    fontSize: 30,
                    height: 1.15,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 800)],
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${food.dishRole} · ${food.category} · '
                  '${formatNumber(food.servingSizeG)} g mỗi suất',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    if (!session.preference.isEmpty)
                      _Tag(
                        'Hợp gu ${(session.preference.score(food) * 100).round()}%',
                        accent: true,
                      ),
                    if (food.spiceLevel > 0)
                      _Tag('Cay ${'🌶' * food.spiceLevel}'),
                    for (final t in food.tags) _Tag(t),
                  ],
                ),
                const SizedBox(height: 18),
                _EnergyCard(food: food),
                const SizedBox(height: 14),
                AppCard(
                  title: 'Trong một suất',
                  child: Column(
                    children: [
                      _Fact('Đường', '${formatNumber(food.sugar, 1)} g'),
                      _Fact('Natri', '${formatNumber(food.sodium)} mg'),
                      _Fact('Chất xơ', '${formatNumber(food.fiber, 1)} g'),
                      // A missing purine figure is "unknown", never zero —
                      // see `Food.purine`.
                      _Fact(
                        'Purin',
                        food.purine == null
                            ? 'Chưa có số liệu'
                            : '${formatNumber(food.purine!)} mg',
                        muted: food.purine == null,
                        last: true,
                      ),
                    ],
                  ),
                ),
                if (ingredients.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  AppCard(
                    title: 'Nguyên liệu cho một suất',
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (var i = 0; i < ingredients.length; i++)
                          _Fact(
                            '${ingredients[i].aisle.emoji}  ${ingredients[i].name}',
                            '${formatNumber(ingredients[i].grams)} g',
                            last: i == ingredients.length - 1,
                          ),
                        const SizedBox(height: 10),
                        const Text(
                          'Khối lượng ước lượng, dùng để lên danh sách đi chợ.',
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.textTertiary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 14),
                _NeverAgainCard(
                  banned: banned,
                  onChanged: (v) {
                    session.setNeverAgain(food, v);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        duration: const Duration(seconds: 2),
                        content: Text(
                          v
                              ? 'Từ thực đơn sau sẽ không còn '
                                    '${food.name.toLowerCase()}'
                              : 'Đã cho ${food.name.toLowerCase()} quay lại',
                        ),
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero({required this.food});

  final Food food;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: food.gradient,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: food.imageAsset == null
          ? Center(
              child: Text(food.emoji, style: const TextStyle(fontSize: 96)),
            )
          : Image.asset(
              food.imageAsset!,
              fit: BoxFit.cover,
              color: food.gradient.last.withValues(alpha: 0.25),
              colorBlendMode: BlendMode.overlay,
            ),
    );
  }
}

/// Circular white button that stays legible over the hero picture.
class _RoundButton extends StatelessWidget {
  const _RoundButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.color = AppColors.textPrimary,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Material(
        color: AppColors.surface,
        shape: const CircleBorder(),
        child: IconButton(
          tooltip: tooltip,
          onPressed: onTap,
          icon: Icon(icon, size: 22, color: color),
          constraints: const BoxConstraints.tightFor(width: 40, height: 40),
          padding: EdgeInsets.zero,
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, {this.accent = false});

  final String text;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: accent ? AppColors.accentSoft : AppColors.surface,
        borderRadius: BorderRadius.circular(999),
        border: accent ? null : Border.all(color: AppColors.border),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 12.5,
          color: accent ? AppColors.accentInk : AppColors.textSecondary,
          fontVariations: const [FontVariation('wght', 600)],
        ),
      ),
    );
  }
}

/// Energy of the serving, and where it comes from.
class _EnergyCard extends StatelessWidget {
  const _EnergyCard({required this.food});

  final Food food;

  @override
  Widget build(BuildContext context) {
    final share = food.macroShare;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                '${food.kcal}',
                style: const TextStyle(
                  fontSize: 40,
                  height: 1,
                  color: AppColors.textPrimary,
                  fontVariations: [FontVariation('wght', 700)],
                ),
              ),
              const SizedBox(width: 6),
              const Text(
                'kcal mỗi suất',
                style: TextStyle(fontSize: 14, color: AppColors.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: SizedBox(
              height: 8,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final part in [
                    (share.protein, AppColors.protein),
                    (share.carb, AppColors.carb),
                    (share.fat, AppColors.fat),
                  ])
                    if (part.$1 > 0)
                      Expanded(
                        flex: (part.$1 * 1000).round().clamp(1, 1000),
                        child: ColoredBox(color: part.$2),
                      ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _Macro('Đạm', food.protein, share.protein, AppColors.protein),
              _Macro('Bột đường', food.carb, share.carb, AppColors.carb),
              _Macro('Béo', food.fat, share.fat, AppColors.fat),
            ],
          ),
        ],
      ),
    );
  }
}

class _Macro extends StatelessWidget {
  const _Macro(this.label, this.grams, this.share, this.color);

  final String label;
  final double grams;
  final double share;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${formatNumber(grams, 1)} g',
            style: const TextStyle(
              fontSize: 16,
              color: AppColors.textPrimary,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
          Text(
            '${(share * 100).round()}% năng lượng',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 11.5,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact(this.label, this.value, {this.muted = false, this.last = false});

  final String label;
  final String value;
  final bool muted;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: last
            ? null
            : const Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 14.5,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 14.5,
              color: muted ? AppColors.textTertiary : AppColors.textPrimary,
              fontVariations: [FontVariation('wght', muted ? 500 : 700)],
            ),
          ),
        ],
      ),
    );
  }
}

/// The hard "never suggest this again" switch.
///
/// Kept apart from swapping a dish out: a swap says *not today*, this says
/// *not ever*, and the dish leaves the candidate pool before scoring.
class _NeverAgainCard extends StatelessWidget {
  const _NeverAgainCard({required this.banned, required this.onChanged});

  final bool banned;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.fromLTRB(20, 14, 12, 14),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Không gợi ý món này nữa',
                  style: TextStyle(
                    fontSize: 15,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  banned
                      ? 'Món này đang bị loại khỏi mọi thực đơn sắp tới.'
                      : 'Món sẽ bị loại khỏi mọi thực đơn sắp tới. Thực đơn '
                            'đã dựng không đổi.',
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.4,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: banned,
            onChanged: onChanged,
            activeTrackColor: AppColors.ink,
          ),
        ],
      ),
    );
  }
}
