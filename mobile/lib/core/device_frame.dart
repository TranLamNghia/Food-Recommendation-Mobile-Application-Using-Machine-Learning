import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'theme/app_colors.dart';

/// A fake phone frame, **enabled only when running in a browser**.
///
/// This app is designed for a phone screen. When previewing it in Chrome, a
/// window a thousand pixels wide stretches the layout out and does not reflect
/// what a real user would see. This frame forces the content back to the size
/// of a mid-range Android phone so the preview is faithful.
///
/// When compiled for Android, [kIsWeb] is `false` and the widget returns
/// [child] directly — nothing superfluous reaches the real build.
class DeviceFrame extends StatelessWidget {
  const DeviceFrame({super.key, required this.child});

  /// The logical size of a Pixel 7 — a familiar reference for a mid-range
  /// Android phone.
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
