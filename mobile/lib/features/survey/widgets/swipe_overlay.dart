import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../data/models/swipe_action.dart';

/// The overlay that appears over the card while it is being swiped.
///
/// Three things run at once, all driven by [progress] rather than by time —
/// which is what makes the card respond instantly to the finger and shows
/// exactly when the swipe has reached its threshold:
/// 1. a thin colour wash over the whole card,
/// 2. a glowing border that thickens,
/// 3. the stamp (icon + text) scaling up and rotating gently into place.
class SwipeOverlay extends StatelessWidget {
  const SwipeOverlay({super.key, required this.action, required this.progress});

  final SwipeAction? action;

  /// How complete the swipe is, in [0, 1]; 1 means the threshold is
  /// reached.
  final double progress;

  @override
  Widget build(BuildContext context) {
    final act = action;
    if (act == null || progress <= 0.01) return const SizedBox.shrink();

    final t = progress.clamp(0.0, 1.0);
    // The stamp appears a little later than the colour wash, so it does
    // not cover the card too early.
    final stampT = ((t - 0.12) / 0.55).clamp(0.0, 1.0);

    return IgnorePointer(
      child: LayoutBuilder(
        builder: (context, constraints) {
          // The corner radius tracks the card: 12 on the design's
          // original 198 width.
          final radius = constraints.maxWidth / 198 * 12;
          // The stamp scales with the card too; otherwise it would spill
          // over the edge when the card is only half the screen wide, as in
          // the design.
          final scale = constraints.maxWidth / 198;

          return Stack(
            fit: StackFit.expand,
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: act.color.withValues(alpha: 0.16 * t),
                  borderRadius: BorderRadius.circular(radius),
                  border: Border.all(
                    color: act.color.withValues(alpha: t),
                    width: 3.5 * t,
                  ),
                ),
              ),
              Align(
                alignment: _stampAlignment(act),
                child: Padding(
                  padding: EdgeInsets.all(12 * scale),
                  child: Transform.rotate(
                    angle: _stampAngle(act) * (1.6 - 0.6 * stampT),
                    child: Transform.scale(
                      scale: 0.55 + 0.45 * Curves.easeOutBack.transform(stampT),
                      child: Opacity(
                        opacity: stampT,
                        child: _Stamp(
                          action: act,
                          filled: t >= 0.999,
                          scale: scale,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  /// The stamp always sits on the side of the card **opposite the swipe**,
  /// because that is the part still in view once the card has travelled:
  /// swipe right and the left edge is still visible, swipe up and the bottom
  /// edge is. Placed on the swipe side, the deck's clip would hide it exactly
  /// when the user most needs to read it.
  Alignment _stampAlignment(SwipeAction action) => switch (action) {
    SwipeAction.like => Alignment.topLeft,
    SwipeAction.dislike => Alignment.topRight,
    // Sits a little above the card's bottom: the dish-name block takes the
    // lowest 29 %, and pinning the stamp to the bottom would hide the name
    // exactly while the user is weighing it up.
    SwipeAction.neutral => const Alignment(0, 0.28),
    SwipeAction.unknown => Alignment.topCenter,
  };

  double _stampAngle(SwipeAction action) => switch (action) {
    SwipeAction.like => -12 * math.pi / 180,
    SwipeAction.dislike => 12 * math.pi / 180,
    SwipeAction.neutral => -4 * math.pi / 180,
    SwipeAction.unknown => 4 * math.pi / 180,
  };
}

class _Stamp extends StatelessWidget {
  const _Stamp({
    required this.action,
    required this.filled,
    required this.scale,
  });

  final SwipeAction action;

  /// The scale factor against the card's original 198 width in Figma.
  final double scale;

  /// Once the swipe is past the threshold the stamp switches to a solid
  /// background — the visual signal that letting go will register.
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      padding: EdgeInsets.symmetric(
        horizontal: 10 * scale,
        vertical: 6 * scale,
      ),
      decoration: BoxDecoration(
        color: filled ? action.color : Colors.white.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(9 * scale),
        border: Border.all(color: action.color, width: 2 * scale),
        boxShadow: [
          if (filled)
            BoxShadow(
              color: action.color.withValues(alpha: 0.45),
              blurRadius: 14 * scale,
              offset: Offset(0, 4 * scale),
            ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            action.icon,
            size: 14 * scale,
            color: filled ? Colors.white : action.color,
          ),
          SizedBox(width: 6 * scale),
          Text(
            action.title.toUpperCase(),
            style: TextStyle(
              fontSize: 11.5 * scale,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.8 * scale,
              color: filled ? Colors.white : action.color,
            ),
          ),
        ],
      ),
    );
  }
}
