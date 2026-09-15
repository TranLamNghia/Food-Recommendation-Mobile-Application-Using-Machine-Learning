import 'package:flutter/animation.dart';

/// Các hằng số chuyển động dùng chung.
///
/// Gom về một chỗ để toàn ứng dụng có cùng "nhịp" chuyển động, và để
/// báo cáo có thể trích dẫn được tham số cụ thể thay vì nói chung chung.
abstract final class AppMotion {
  // ── Thời lượng ───────────────────────────────────────────────────
  /// Phản hồi tức thì: đổi màu, hiện nhãn chồng lên thẻ.
  static const instant = Duration(milliseconds: 120);

  /// Chuyển trạng thái nhỏ trong một widget.
  static const quick = Duration(milliseconds: 220);

  /// Thẻ bật về vị trí cũ khi vuốt chưa đủ ngưỡng.
  static const snapBack = Duration(milliseconds: 420);

  /// Thẻ bay ra khỏi màn hình khi vuốt đạt ngưỡng.
  static const flyOut = Duration(milliseconds: 300);

  /// Hoàn tác — thẻ bay ngược trở lại chồng thẻ.
  static const undo = Duration(milliseconds: 380);

  /// Chuyển màn hình.
  static const page = Duration(milliseconds: 480);

  // ── Đường cong ───────────────────────────────────────────────────
  /// Dùng cho phần lớn chuyển động vào/ra: nhanh lúc đầu, dịu lúc cuối.
  static const standard = Curves.easeOutCubic;

  /// Thẻ bật về chỗ cũ — có độ nảy nhẹ để cảm giác đàn hồi.
  static const spring = Curves.easeOutBack;

  /// Thẻ bay ra — tăng tốc dần, mô phỏng quán tính của cú vuốt.
  static const eject = Curves.easeInCubic;

  /// Nhấn mạnh: dùng cho phần tử xuất hiện lần đầu.
  static const emphasized = Cubic(0.2, 0.0, 0.0, 1.0);
}
