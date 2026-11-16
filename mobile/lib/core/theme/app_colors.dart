import 'package:flutter/material.dart';

/// The system's colour palette.
///
/// The whole interface turns on **three colours**: white for the page
/// background and card surfaces, black for the primary action button and the
/// selected state, and the cyan `#2AD2EE` as the accent for numbers and
/// information that has to stand out. The greys in between are only lightness
/// variants of the white–black pair, not a fourth colour.
///
/// Note on naming: `tools/check_contrast.py` reads the constants below by
/// NAME — its `PAIRS` table lists 20 of them and checks each pair against its
/// WCAG threshold. Renaming one here means renaming it there in the same
/// change, or the checker reports a colour that does not exist.
abstract final class AppColors {
  // ── The three leading colours ────────────────────────────────────
  static const white = Color(0xFFFFFFFF);
  static const ink = Color(0xFF000000);
  static const accent = Color(0xFF2AD2EE);

  /// The primary action button is a solid black block, so `primary` points
  /// straight at [ink].
  static const primary = ink;
  static const primaryDark = ink;

  /// A very pale cyan background for labels and soft accent areas.
  static const accentSoft = Color(0xFFE2F8FD);

  /// The cyan **darkened for use as a text and icon colour**.
  ///
  /// [accent] only reaches 1.82:1 on white and 1.65:1 on [accentSoft] —
  /// below even the 3:1 threshold for a graphical component, so it cannot
  /// carry information on a light background. It remains the brand colour
  /// for large fills and for [accentSoft], but every piece of text, every
  /// icon and every progress-bar fill uses this one: 5.12:1 on white,
  /// 4.65:1 on [accentSoft].
  static const accentInk = Color(0xFF11788E);
  static const primarySoft = accentSoft;

  // ── Backgrounds and surfaces ─────────────────────────────────────
  /// The page background is slightly greyer than a card surface, so a white
  /// card lifts off it without needing a border or a heavy shadow.
  static const background = Color(0xFFF4F5F7);
  static const surface = white;
  static const surfaceMuted = Color(0xFFEDEEF0);
  static const border = Color(0xFFE6E7EA);

  // ── Text ─────────────────────────────────────────────────────────
  static const textPrimary = Color(0xFF0B0B0C);
  static const textSecondary = Color(0xFF6B6C71);
  static const textTertiary = Color(0xFFB4B5BA);
  static const textOnDark = white;

  // ── The four swipe directions ────────────────────────────────────
  //
  // The `burst*` colours are the original ones from the `Left` / `Right` /
  // `Up` / `Down` areas in Figma. They are very vivid and bright, so they are
  // only used for the flying particles and the glow strips at the screen
  // edges. The four colours above are the darkened versions, so text and
  // buttons stay readable on white.
  static const like = Color(0xFF0A7A3C);
  static const dislike = Color(0xFFC62828);
  static const neutral = Color(0xFF3B57E8);
  static const unknown = Color(0xFF7A6000);

  static const burstRight = Color(0xFF5CFF8D);
  static const burstLeft = Color(0xFFFF4646);
  static const burstUp = Color(0xFF5C77FF);
  static const burstDown = Color(0xFFFFFA5C);

  // ── The survey screen's footer area ──────────────────────────────
  /// The bottom of the `Footer_Backgound` gradient (2:15). The gradient runs
  /// from transparent at the top edge down to this colour at the bottom.
  static const footerBottom = Color(0xFF4F4E4E);

  // ── The three energy-bearing macronutrients ──────────────────────
  static const kcal = Color(0xFFB3500F);
  static const protein = Color(0xFFC0392B);
  static const carb = Color(0xFF8A6314);
  static const fat = Color(0xFF2E5FBF);

  // ── Shadows ──────────────────────────────────────────────────────
  static const shadowSoft = Color(0x0F0B0B0C);
  static const shadowLifted = Color(0x1F0B0B0C);
}
