import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// The four swipe actions of the taste survey session.
///
/// The `label` value is the preference label mapped onto [0, 1] for training.
/// [unknown] alone has no label — that sample is dropped from the training
/// set.
///
/// Note on language: `title` and `hint` are text shown on screen, so they
/// stay in Vietnamese; `code` is the value sent to the server, so it stays
/// too.
enum SwipeAction {
  like(
    code: 'like',
    title: 'Thích',
    hint: 'Vuốt phải',
    icon: Icons.favorite_rounded,
    color: AppColors.like,
    burst: AppColors.burstRight,
    label: 0.9,
  ),
  dislike(
    code: 'dislike',
    title: 'Không thích',
    hint: 'Vuốt trái',
    icon: Icons.close_rounded,
    color: AppColors.dislike,
    burst: AppColors.burstLeft,
    label: 0.0,
  ),
  neutral(
    code: 'neutral',
    title: 'Bình thường',
    hint: 'Vuốt lên',
    icon: Icons.remove_rounded,
    color: AppColors.neutral,
    burst: AppColors.burstUp,
    label: 0.5,
  ),
  unknown(
    code: 'unknown',
    title: 'Chưa biết',
    hint: 'Vuốt xuống',
    icon: Icons.help_outline_rounded,
    color: AppColors.unknown,
    burst: AppColors.burstDown,
    label: null,
  );

  const SwipeAction({
    required this.code,
    required this.title,
    required this.hint,
    required this.icon,
    required this.color,
    required this.burst,
    required this.label,
  });

  /// The code sent to the server — matches the enum in API specification
  /// §5.3.
  final String code;
  final String title;
  final String hint;
  final IconData icon;

  /// The colour used for text and buttons — adjusted to stay readable on a
  /// light background.
  final Color color;

  /// The original colour of the direction area in Figma, used for the flying
  /// particles and the edge glow. These are very vivid, so they suit effects
  /// only, not text.
  final Color burst;

  /// The preference label in [0, 1]; `null` means drop from the training set.
  final double? label;

  bool get isHorizontal =>
      this == SwipeAction.like || this == SwipeAction.dislike;
}
