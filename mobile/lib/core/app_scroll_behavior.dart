import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// Cho phép kéo cuộn bằng chuột, không chỉ bằng ngón tay.
///
/// Mặc định Flutter chỉ nhận kéo cuộn từ cảm ứng và bút, vì trên máy tính
/// người ta cuộn bằng con lăn chứ hiếm khi kéo. Nhưng bản xem thử của ứng
/// dụng này chạy trên trình duyệt, nơi bánh xe chọn số và danh sách dài đều
/// phải kéo được bằng chuột — nếu không thì trên Chrome chúng đứng im như bị
/// hỏng, dù trên Android vẫn chạy bình thường.
class AppScrollBehavior extends MaterialScrollBehavior {
  const AppScrollBehavior();

  @override
  Set<PointerDeviceKind> get dragDevices => const {
    PointerDeviceKind.touch,
    PointerDeviceKind.stylus,
    PointerDeviceKind.invertedStylus,
    PointerDeviceKind.mouse,
    PointerDeviceKind.trackpad,
  };
}
