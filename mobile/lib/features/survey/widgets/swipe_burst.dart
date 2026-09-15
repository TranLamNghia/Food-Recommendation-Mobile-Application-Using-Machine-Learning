import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../data/models/swipe_action.dart';

/// Trạng thái cú vuốt mà chồng thẻ phát ra cho các lớp hiệu ứng nghe.
class SwipeSignal {
  const SwipeSignal({this.action, this.progress = 0});

  /// Hướng đang được nhắm tới, `null` khi thẻ đang đứng yên.
  final SwipeAction? action;

  /// Mức độ hoàn thành cú vuốt trong đoạn [0, 1].
  final double progress;
}

/// Bốn vùng hạt bay ở rìa màn hình.
///
/// Bản Figma thể hiện bốn vùng này bằng bốn hình chữ nhật đặc (`Left`,
/// `Right`, `Up`, `Down` trong `Area_Pick`) vì Figma không diễn tả được hạt
/// chuyển động. Ở đây chúng được dựng lại đúng vị trí và màu đó, nhưng thay
/// mảng đặc bằng **hạt bắn ra ngoài**: vuốt về hướng nào thì vùng hướng đó
/// nở rộng ra, hạt dày lên, bay xa hơn và sáng hơn.
///
/// Cả bốn vùng luôn hiện ở mức rất mờ ngay cả khi chưa vuốt — đó là cách
/// người dùng biết thẻ này vuốt được bốn hướng mà không cần đọc chú thích.
class SwipeBurst extends StatefulWidget {
  const SwipeBurst({super.key, required this.signal});

  final ValueListenable<SwipeSignal> signal;

  @override
  State<SwipeBurst> createState() => _SwipeBurstState();
}

class _SwipeBurstState extends State<SwipeBurst>
    with SingleTickerProviderStateMixin {
  /// Một vòng đời trọn vẹn của hạt: sinh ra ở mép trong, bay ra, tắt dần.
  static const _cycle = Duration(milliseconds: 2600);

  late final AnimationController _time;
  late final List<_Emitter> _emitters;

  @override
  void initState() {
    super.initState();
    _time = AnimationController(vsync: this, duration: _cycle)..repeat();

    // Hạt được sinh một lần rồi tái sử dụng mãi. Nếu sinh ngẫu nhiên lại mỗi
    // khung hình thì hạt sẽ nhấp nháy loạn thay vì bay thành dòng.
    final rng = math.Random(20260909);
    _emitters = [
      for (final action in SwipeAction.values) _Emitter(action, rng),
    ];
  }

  @override
  void dispose() {
    _time.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: RepaintBoundary(
        child: CustomPaint(
          size: Size.infinite,
          painter: _BurstPainter(
            emitters: _emitters,
            time: _time,
            signal: widget.signal,
          ),
        ),
      ),
    );
  }
}

/// Một vùng hạt, gắn với một hướng vuốt.
class _Emitter {
  _Emitter(this.action, math.Random rng)
    : particles = List.generate(_poolSize, (_) => _Particle(rng));

  /// Số hạt dựng sẵn cho mỗi vùng. Lúc chưa vuốt chỉ một phần nhỏ được vẽ.
  static const _poolSize = 44;

  final SwipeAction action;
  final List<_Particle> particles;

  /// Vùng phát hạt, lấy đúng toạ độ trong khung thiết kế 390 × 581 của Figma.
  Rect get designBand => switch (action) {
    SwipeAction.dislike => const Rect.fromLTWH(0, 98, 48, 385), // Left
    SwipeAction.like => const Rect.fromLTWH(342, 98, 48, 385), // Right
    SwipeAction.neutral => const Rect.fromLTWH(55, 0, 280, 43), // Up
    SwipeAction.unknown => const Rect.fromLTWH(55, 538, 280, 43), // Down
  };

  /// Hướng hạt bay ra khỏi màn hình.
  Offset get outward => switch (action) {
    SwipeAction.dislike => const Offset(-1, 0),
    SwipeAction.like => const Offset(1, 0),
    SwipeAction.neutral => const Offset(0, -1),
    SwipeAction.unknown => const Offset(0, 1),
  };

  bool get isHorizontal => action.isHorizontal;
}

class _Particle {
  _Particle(math.Random rng)
    : along = rng.nextDouble(),
      spread = rng.nextDouble(),
      size = rng.nextDouble(),
      phase = rng.nextDouble(),
      speed = 0.7 + rng.nextDouble() * 0.6;

  /// Vị trí dọc theo cạnh dài của vùng, trong đoạn [0, 1].
  final double along;

  /// Độ lệch ngang so với đường bay thẳng, trong đoạn [0, 1].
  final double spread;

  final double size;

  /// Lệch pha để các hạt không cùng sinh ra một lúc.
  final double phase;

  final double speed;
}

class _BurstPainter extends CustomPainter {
  _BurstPainter({
    required this.emitters,
    required this.time,
    required this.signal,
  }) : super(repaint: Listenable.merge([time, signal]));

  /// Mức sáng nền của một vùng khi người dùng chưa vuốt về phía nó.
  static const _idle = 0.13;

  /// Khung thiết kế gốc trong Figma.
  static const _designSize = Size(390, 581);

  final List<_Emitter> emitters;
  final AnimationController time;
  final ValueListenable<SwipeSignal> signal;

  @override
  void paint(Canvas canvas, Size size) {
    final sx = size.width / _designSize.width;
    final sy = size.height / _designSize.height;
    final current = signal.value;

    for (final emitter in emitters) {
      final aimed = current.action == emitter.action;
      final intensity = aimed
          ? math.max(_idle, current.progress.clamp(0.0, 1.0))
          : _idle;

      _paintGlow(canvas, emitter, size, sx, sy, intensity);
      _paintParticles(canvas, emitter, sx, sy, intensity);
    }
  }

  /// Dải sáng mờ ở sát mép, dày lên theo cường độ — phần "vùng nở rộng ra".
  void _paintGlow(
    Canvas canvas,
    _Emitter emitter,
    Size size,
    double sx,
    double sy,
    double intensity,
  ) {
    final band = emitter.designBand;
    final depth =
        (emitter.isHorizontal ? band.width : band.height) *
        (1 + 1.6 * intensity);

    final rect = switch (emitter.action) {
      SwipeAction.dislike => Rect.fromLTWH(
        0,
        band.top * sy,
        depth * sx,
        band.height * sy,
      ),
      SwipeAction.like => Rect.fromLTWH(
        size.width - depth * sx,
        band.top * sy,
        depth * sx,
        band.height * sy,
      ),
      SwipeAction.neutral => Rect.fromLTWH(
        band.left * sx,
        0,
        band.width * sx,
        depth * sy,
      ),
      SwipeAction.unknown => Rect.fromLTWH(
        band.left * sx,
        size.height - depth * sy,
        band.width * sx,
        depth * sy,
      ),
    };

    // Đậm ở mép ngoài, tan dần vào giữa màn hình.
    final begin = switch (emitter.action) {
      SwipeAction.dislike => Alignment.centerLeft,
      SwipeAction.like => Alignment.centerRight,
      SwipeAction.neutral => Alignment.topCenter,
      SwipeAction.unknown => Alignment.bottomCenter,
    };

    // Làm nhoè toàn bộ mép. Nếu vẽ hình chữ nhật sắc cạnh thì hai cạnh bên
    // hiện rõ thành một khối chữ nhật mờ đè lên màn hình, trông như lỗi dựng
    // chứ không ra quầng sáng.
    final blur = 14 + 26 * intensity;

    final paint = Paint()
      ..shader = LinearGradient(
        begin: begin,
        end: -begin,
        colors: [
          emitter.action.burst.withValues(alpha: 0.20 * intensity),
          emitter.action.burst.withValues(alpha: 0),
        ],
      ).createShader(rect)
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, blur);

    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(blur)),
      paint,
    );
  }

  void _paintParticles(
    Canvas canvas,
    _Emitter emitter,
    double sx,
    double sy,
    double intensity,
  ) {
    final band = emitter.designBand;
    final thickness = emitter.isHorizontal ? band.width : band.height;
    final reach = thickness * (1.1 + 2.6 * intensity);

    // Cường độ càng cao thì càng nhiều hạt trong bể được đưa ra vẽ.
    final visible = (emitter.particles.length * (0.2 + 0.8 * intensity))
        .round();

    final paint = Paint()..style = PaintingStyle.fill;

    for (var i = 0; i < visible; i++) {
      final p = emitter.particles[i];
      final t = (time.value * p.speed + p.phase) % 1.0;

      // Hạt sinh ra ở sâu bên trong màn hình rồi bay dần ra mép và biến mất
      // ở đó. Nếu làm ngược lại — sinh ở mép rồi bay tiếp ra ngoài — thì
      // phần lớn quãng đời của hạt nằm ngoài khung nhìn, vùng trông thưa hẳn
      // dù số hạt vẫn nhiều.
      final inward = reach * (1 - t);
      final wobble =
          math.sin((t * 2 + p.phase) * math.pi * 2) *
          10 *
          (p.spread - 0.5) *
          intensity;

      final Offset design;
      if (emitter.isHorizontal) {
        final y = band.top + p.along * band.height + wobble;
        design = emitter.action == SwipeAction.dislike
            ? Offset(inward, y)
            : Offset(_designSize.width - inward, y);
      } else {
        final x = band.left + p.along * band.width + wobble;
        design = emitter.action == SwipeAction.neutral
            ? Offset(x, inward)
            : Offset(x, _designSize.height - inward);
      }

      // Hiện dần rồi tắt dần trong một vòng đời, để hạt không bật tắt đột ngột.
      final fade = math.sin(t * math.pi);
      paint.color = emitter.action.burst.withValues(
        alpha: (0.22 + 0.78 * intensity) * fade,
      );

      final radius = (1.1 + p.size * 2.3) * (0.7 + 0.9 * intensity);
      canvas.drawCircle(Offset(design.dx * sx, design.dy * sy), radius, paint);
    }
  }

  @override
  bool shouldRepaint(_BurstPainter oldDelegate) => false;
}
