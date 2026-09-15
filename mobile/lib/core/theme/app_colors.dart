import 'package:flutter/material.dart';

/// Bảng màu của hệ thống.
///
/// Toàn bộ giao diện xoay quanh **ba màu**: trắng làm nền và mặt thẻ, đen làm
/// nút hành động chính và trạng thái đã chọn, lơ `#2AD2EE` làm màu nhấn cho
/// con số và thông tin cần bật lên. Các sắc xám ở giữa chỉ là biến thể độ
/// sáng của trắng–đen, không phải màu thứ tư.
abstract final class AppColors {
  // ── Ba màu chủ đạo ───────────────────────────────────────────────
  static const white = Color(0xFFFFFFFF);
  static const ink = Color(0xFF000000);
  static const accent = Color(0xFF2AD2EE);

  /// Nút hành động chính là khối đen đặc, nên `primary` trỏ thẳng vào [ink].
  static const primary = ink;
  static const primaryDark = ink;

  /// Nền lơ rất nhạt cho nhãn và vùng nhấn mềm.
  static const accentSoft = Color(0xFFE2F8FD);
  static const primarySoft = accentSoft;

  // ── Nền và bề mặt ────────────────────────────────────────────────
  /// Nền trang hơi xám hơn mặt thẻ một chút, để thẻ trắng nổi lên mà không
  /// cần viền hay đổ bóng nặng.
  static const background = Color(0xFFF4F5F7);
  static const surface = white;
  static const surfaceMuted = Color(0xFFEDEEF0);
  static const border = Color(0xFFE6E7EA);

  // ── Chữ ──────────────────────────────────────────────────────────
  static const textPrimary = Color(0xFF0B0B0C);
  static const textSecondary = Color(0xFF8A8B90);
  static const textTertiary = Color(0xFFB4B5BA);
  static const textOnDark = white;

  // ── Bốn hướng vuốt ───────────────────────────────────────────────
  //
  // `burst*` là màu nguyên bản của bốn vùng `Left` / `Right` / `Up` / `Down`
  // trong Figma. Chúng rất tươi và sáng nên chỉ dùng cho hạt bay và dải sáng
  // ở rìa màn hình. Bốn màu phía trên là bản đã hạ độ sáng để chữ và nút vẫn
  // đọc được trên nền trắng.
  static const like = Color(0xFF12B85C);
  static const dislike = Color(0xFFE63636);
  static const neutral = Color(0xFF3B57E8);
  static const unknown = Color(0xFFB08900);

  static const burstRight = Color(0xFF5CFF8D);
  static const burstLeft = Color(0xFFFF4646);
  static const burstUp = Color(0xFF5C77FF);
  static const burstDown = Color(0xFFFFFA5C);

  // ── Vùng chân màn hình khảo sát ──────────────────────────────────
  /// Đáy của gradient `Footer_Backgound` (2:15). Gradient chạy từ trắng
  /// xuống màu này — vùng chân màn hình **không** trong suốt.
  static const footerBottom = Color(0xFF4F4E4E);

  // ── Ba chất sinh năng lượng ──────────────────────────────────────
  static const kcal = Color(0xFFF0803C);
  static const protein = Color(0xFFE2574C);
  static const carb = Color(0xFFE9A93C);
  static const fat = Color(0xFF5B8FF9);

  // ── Đổ bóng ──────────────────────────────────────────────────────
  static const shadowSoft = Color(0x0F0B0B0C);
  static const shadowLifted = Color(0x1F0B0B0C);
}
