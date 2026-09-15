import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// Bốn hành động vuốt trong phiên khảo sát khẩu vị.
///
/// Giá trị `label` là nhãn ưa thích quy về đoạn [0, 1] dùng cho huấn luyện.
/// Riêng [unknown] không có nhãn — mẫu này bị loại khỏi tập huấn luyện.
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

  /// Mã gửi lên máy chủ — trùng với enum trong đặc tả API mục 5.3.
  final String code;
  final String title;
  final String hint;
  final IconData icon;

  /// Màu dùng cho chữ và nút — đã chỉnh cho đọc được trên nền sáng.
  final Color color;

  /// Màu nguyên bản của vùng hướng trong Figma, dùng cho hạt bay và dải sáng
  /// ở rìa. Mấy màu này rất tươi nên chỉ hợp làm hiệu ứng, không hợp làm chữ.
  final Color burst;

  /// Nhãn ưa thích trong đoạn [0, 1]; `null` nghĩa là loại khỏi tập huấn luyện.
  final double? label;

  bool get isHorizontal =>
      this == SwipeAction.like || this == SwipeAction.dislike;
}
