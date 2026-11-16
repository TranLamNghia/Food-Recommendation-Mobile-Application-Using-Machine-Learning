import 'package:flutter/material.dart';

/// The cloche icon covering a dish.
///
/// Redraws the exact path of the `Vector` layer exported from Figma (node
/// 5:11, viewBox 17×13) with a `CustomPainter`, rather than pulling an SVG
/// library into the project. The shape keeps the design's geometry with no
/// new dependency.
class DishIcon extends StatelessWidget {
  const DishIcon({super.key, required this.size, this.color = Colors.white});

  /// The original size in the design, keeping the 17 : 13 ratio.
  static const designSize = Size(17, 13);

  final Size size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size.width,
      height: size.height,
      child: CustomPaint(painter: _DishPainter(color)),
    );
  }
}

class _DishPainter extends CustomPainter {
  const _DishPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final sx = size.width / DishIcon.designSize.width;
    final sy = size.height / DishIcon.designSize.height;

    final path = Path()
      // The dome of the cloche, with its handle on top.
      ..moveTo(7.17188, 0)
      ..cubicTo(6.73027, 0, 6.375, 0.36224, 6.375, 0.8125)
      ..cubicTo(6.375, 1.26276, 6.73027, 1.625, 7.17188, 1.625)
      ..lineTo(7.70312, 1.625)
      ..lineTo(7.70312, 2.75234)
      ..cubicTo(4.14375, 3.13828, 1.33477, 6.08359, 1.08242, 9.75)
      ..lineTo(15.9209, 9.75)
      ..cubicTo(15.6652, 6.08359, 12.8562, 3.13828, 9.29688, 2.75234)
      ..lineTo(9.29688, 1.625)
      ..lineTo(9.82812, 1.625)
      ..cubicTo(10.2697, 1.625, 10.625, 1.26276, 10.625, 0.8125)
      ..cubicTo(10.625, 0.36224, 10.2697, 0, 9.82812, 0)
      ..close()
      // The horizontal base bar.
      ..moveTo(0.796875, 11.375)
      ..cubicTo(0.355273, 11.375, 0, 11.7372, 0, 12.1875)
      ..cubicTo(0, 12.6378, 0.355273, 13, 0.796875, 13)
      ..lineTo(16.2031, 13)
      ..cubicTo(16.6447, 13, 17, 12.6378, 17, 12.1875)
      ..cubicTo(17, 11.7372, 16.6447, 11.375, 16.2031, 11.375)
      ..close();

    canvas.save();
    canvas.scale(sx, sy);
    canvas.drawPath(path, Paint()..color = color);
    canvas.restore();
  }

  @override
  bool shouldRepaint(_DishPainter oldDelegate) => oldDelegate.color != color;
}
