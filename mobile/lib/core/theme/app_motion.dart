import 'package:flutter/animation.dart';

/// The shared motion constants.
///
/// Gathered in one place so the whole app moves to the same "rhythm", and so
/// the report can quote specific parameters rather than speak in generalities.
abstract final class AppMotion {
  // ── Durations ────────────────────────────────────────────────────
  /// Immediate feedback: a colour change, an overlay label on a card.
  static const instant = Duration(milliseconds: 120);

  /// A small state change within one widget.
  static const quick = Duration(milliseconds: 220);

  /// A card snapping back when the swipe did not reach the threshold.
  static const snapBack = Duration(milliseconds: 420);

  /// A card flying off screen when the swipe did reach the threshold.
  static const flyOut = Duration(milliseconds: 300);

  /// Undo — the card flies back onto the deck.
  static const undo = Duration(milliseconds: 380);

  /// A screen transition.
  static const page = Duration(milliseconds: 480);

  // ── Curves ──────────────────────────────────────────────────────
  /// For most enter/exit motion: fast at the start, gentle at the end.
  static const standard = Curves.easeOutCubic;

  /// A card snapping back — a slight overshoot so it feels elastic.
  static const spring = Curves.easeOutBack;

  /// A card flying off — accelerating, imitating the swipe's momentum.
  static const eject = Curves.easeInCubic;

  /// Emphasis: for an element appearing for the first time.
  static const emphasized = Cubic(0.2, 0.0, 0.0, 1.0);
}
