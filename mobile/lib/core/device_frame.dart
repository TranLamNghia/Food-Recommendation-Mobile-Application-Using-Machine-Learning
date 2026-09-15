import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'theme/app_colors.dart';

/// Khung điện thoại giả, **chỉ bật khi chạy trên trình duyệt**.
///
/// Ứng dụng này thiết kế cho màn hình điện thoại. Khi xem thử bằng Chrome,
/// cửa sổ rộng cả nghìn pixel làm bố cục giãn ra, không phản ánh đúng những
/// gì người dùng thật sẽ thấy. Khung này ép nội dung về đúng khổ máy Android
/// tầm trung để xem trước cho chuẩn.
///
/// Khi biên dịch cho Android, [kIsWeb] bằng `false` nên widget trả thẳng
/// [child] — không có gì thừa lọt vào bản dựng thật.
class DeviceFrame extends StatelessWidget {
  const DeviceFrame({super.key, required this.child});

  /// Kích thước logic của Pixel 7 — mốc quen thuộc cho máy Android tầm trung.
  static const _size = Size(412, 915);

  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) return child;

    return ColoredBox(
      color: const Color(0xFFDCE3DD),
      child: Center(
        child: ClipRRect(
          borderRadius: BorderRadius.circular(28),
          child: SizedBox(
            width: _size.width,
            height: _size.height,
            child: DecoratedBox(
              decoration: const BoxDecoration(color: AppColors.background),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}
