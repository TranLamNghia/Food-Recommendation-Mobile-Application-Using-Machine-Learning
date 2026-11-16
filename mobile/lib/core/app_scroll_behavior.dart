import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

/// Allows drag-scrolling with a mouse, not only with a finger.
///
/// By default Flutter only accepts drag-scrolling from touch and stylus,
/// because on a desktop people scroll with the wheel and rarely drag. But
/// this app's preview build runs in a browser, where the number wheels and
/// the long lists both have to be draggable with a mouse — without this they
/// sit motionless in Chrome as if broken, while working fine on Android.
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
