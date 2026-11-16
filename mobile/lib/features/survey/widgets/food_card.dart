import 'package:flutter/material.dart';

import '../../../data/models/food.dart';
import 'dish_icon.dart';

/// The dish card — built from the `Card` node (5:32) in Figma.
///
/// Every measurement in this class is taken straight from the design at its
/// original **198 × 280** size, then multiplied by [_Metrics.scale] for the
/// card's actual width. The original numbers are kept so they can be checked
/// back against Figma when the design changes, rather than being pre-scaled.
class FoodCard extends StatelessWidget {
  const FoodCard({
    super.key,
    required this.food,
    this.parallax = Offset.zero,
    this.elevated = true,
  });

  /// The card's original size in Figma. This ratio is preserved when
  /// scaled up.
  static const designSize = Size(198, 280);
  static const aspectRatio = 198 / 280;

  final Food food;

  /// The normalised drag distance (each axis in [-1, 1]) — the image
  /// shifts slightly against the card to create depth.
  final Offset parallax;

  final bool elevated;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final m = _Metrics(constraints.maxWidth);

        return DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(m.radius),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: elevated ? 0.28 : 0.14),
                blurRadius: m.s(elevated ? 28 : 16),
                offset: Offset(0, m.s(elevated ? 14 : 7)),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(m.radius),
            child: Stack(
              fit: StackFit.expand,
              children: [
                _Image(food: food, parallax: parallax),
                const _BottomGradient(),
                _Content(food: food, m: m),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Converts design measurements into the real on-device ones.
class _Metrics {
  _Metrics(double width) : scale = width / FoodCard.designSize.width;

  final double scale;

  double s(double designValue) => designValue * scale;

  double get radius => s(12);
}

class _Image extends StatelessWidget {
  const _Image({required this.food, required this.parallax});

  final Food food;
  final Offset parallax;

  @override
  Widget build(BuildContext context) {
    final asset = food.imageAsset;

    // The image is scaled up slightly and then shifted with the swipe. The
    // scaling has to come first, or its edge would show as it moves.
    Widget withParallax(Widget child) => Transform.scale(
      scale: 1.06,
      child: Transform.translate(offset: parallax * -10, child: child),
    );

    if (asset == null) {
      // No dish photo yet: fall back to the gradient background with an
      // icon, so the card still reads rather than showing an empty box.
      return withParallax(
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: food.gradient,
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Center(
            child: Text(food.emoji, style: const TextStyle(fontSize: 76)),
          ),
        ),
      );
    }

    return withParallax(
      Image.asset(
        asset,
        fit: BoxFit.cover,
        // The blue background of the `Image` layer in Figma, visible
        // while the photo loads.
        errorBuilder: (context, error, stack) =>
            const ColoredBox(color: Color(0xFF006EFF)),
      ),
    );
  }
}

/// The gradient layer at the bottom of the card — the `Gradient` layer
/// (5:7).
///
/// It starts at 60.53 % of the height and runs from transparent down to
/// `#121212`. This is what keeps the white text readable over any photo.
class _BottomGradient extends StatelessWidget {
  const _BottomGradient();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment(0, 0.2106), // 60.53 % tính từ đỉnh
          end: Alignment.bottomCenter,
          colors: [Color(0x00121212), Color(0xFF121212)],
        ),
      ),
    );
  }
}

/// The text block at the bottom of the card — the `Content` layer
/// (5:9), originally 179 × 58.
class _Content extends StatelessWidget {
  const _Content({required this.food, required this.m});

  final Food food;
  final _Metrics m;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: m.s(11),
      bottom: m.s(23),
      width: m.s(179),
      height: m.s(58),
      child: Stack(
        children: [
          Positioned(
            left: 0,
            top: 0,
            right: m.s(5),
            // The card is only half the screen wide, so a long dish name
            // like "Cơm tấm sườn nướng" does not fit at size 24. The text is
            // allowed to shrink itself rather than being cut with an
            // ellipsis — the dish name is the only thing the user has to
            // decide on, so no part of it may be lost.
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                food.name,
                maxLines: 1,
                style: TextStyle(
                  fontFamily: 'Display',
                  fontVariations: const [FontVariation('wght', 900)],
                  fontSize: m.s(24),
                  height: 34 / 24,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            top: m.s(39),
            child: DishIcon(size: Size(m.s(17), m.s(13))),
          ),
          Positioned(
            left: m.s(25),
            top: m.s(37),
            right: m.s(53),
            child: Text(
              food.category,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: 'Afacad',
                fontVariations: const [FontVariation('wght', 600)],
                fontSize: m.s(12),
                height: 18 / 12,
                letterSpacing: m.s(0.2),
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
