import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../data/models/swipe_action.dart';

/// The swipe state the deck publishes for the effect layers to listen
/// to.
class SwipeSignal {
  const SwipeSignal({this.action, this.progress = 0});

  /// The direction being aimed at; `null` while the card is still.
  final SwipeAction? action;

  /// How complete the swipe is, in [0, 1].
  final double progress;
}

/// The four particle zones at the screen edges.
///
/// The Figma file represents these four zones as four solid rectangles
/// (`Left`, `Right`, `Up`, `Down` inside `Area_Pick`), because Figma cannot
/// express moving particles. Here they are rebuilt at exactly those positions
/// and colours, but the solid block is replaced by **particles shooting
/// outwards**: whichever direction is swiped, that zone widens, its particles
/// thicken, fly further and glow brighter.
///
/// All four zones are always faintly present even before any swipe — that is
/// how the user knows the card takes four directions without reading an
/// instruction.
class SwipeBurst extends StatefulWidget {
  const SwipeBurst({super.key, required this.signal, this.bottomOverflow = 0});

  final ValueListenable<SwipeSignal> signal;

  /// How far, in logical pixels, the bottom ("Chưa biết") zone reaches past
  /// the lower edge of this widget.
  ///
  /// The survey footer sits right below the deck and is transparent at its
  /// top, so pushing the bottom zone down by this much lets its particles
  /// drift underneath the footer and sink into its grey. The other three
  /// zones are not affected. The widget must not be clipped for this to show.
  final double bottomOverflow;

  @override
  State<SwipeBurst> createState() => _SwipeBurstState();
}

class _SwipeBurstState extends State<SwipeBurst>
    with SingleTickerProviderStateMixin {
  /// One complete particle lifetime: born at the inner edge, flies out,
  /// fades away.
  static const _cycle = Duration(milliseconds: 2600);

  late final AnimationController _time;
  late final List<_Emitter> _emitters;

  @override
  void initState() {
    super.initState();
    _time = AnimationController(vsync: this, duration: _cycle)..repeat();

    // The particles are generated once and then reused forever. Randomising
    // them again every frame would make them flicker chaotically instead of
    // flowing as a stream.
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
            bottomOverflow: widget.bottomOverflow,
          ),
        ),
      ),
    );
  }
}

/// One particle zone, tied to one swipe direction.
class _Emitter {
  _Emitter(this.action, math.Random rng)
    : particles = List.generate(_poolSize, (_) => _Particle(rng));

  /// How many particles are pre-built per zone. Before any swipe only a
  /// small fraction is drawn.
  static const _poolSize = 44;

  final SwipeAction action;
  final List<_Particle> particles;

  /// The emitting area, at exactly its coordinates in Figma's 390 × 581
  /// design frame.
  Rect get designBand => switch (action) {
    SwipeAction.dislike => const Rect.fromLTWH(0, 98, 48, 385), // Left
    SwipeAction.like => const Rect.fromLTWH(342, 98, 48, 385), // Right
    SwipeAction.neutral => const Rect.fromLTWH(55, 0, 280, 43), // Up
    SwipeAction.unknown => const Rect.fromLTWH(55, 538, 280, 43), // Down
  };

  /// The direction the particles fly off screen.
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

  /// The position along the zone's long edge, in [0, 1].
  final double along;

  /// The sideways offset from a straight flight path, in [0, 1].
  final double spread;

  final double size;

  /// A phase offset so the particles are not all born at once.
  final double phase;

  final double speed;
}

class _BurstPainter extends CustomPainter {
  _BurstPainter({
    required this.emitters,
    required this.time,
    required this.signal,
    required this.bottomOverflow,
  }) : super(repaint: Listenable.merge([time, signal]));

  /// A zone's resting brightness while nothing is being swiped towards
  /// it.
  static const _idle = 0.13;

  /// The original design frame in Figma.
  static const _designSize = Size(390, 581);

  final List<_Emitter> emitters;
  final AnimationController time;
  final ValueListenable<SwipeSignal> signal;
  final double bottomOverflow;

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

  /// The faint glow strip along the edge, thickening with the intensity
  /// — the "zone widening" part.
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
        size.height + bottomOverflow - depth * sy,
        band.width * sx,
        depth * sy,
      ),
    };

    // Strong at the outer edge, dissolving towards the centre of the
    // screen.
    final begin = switch (emitter.action) {
      SwipeAction.dislike => Alignment.centerLeft,
      SwipeAction.like => Alignment.centerRight,
      SwipeAction.neutral => Alignment.topCenter,
      SwipeAction.unknown => Alignment.bottomCenter,
    };

    // Blur the whole edge. Drawn as a sharp-edged rectangle, its two sides
    // would read as a translucent box laid over the screen, looking like a
    // rendering bug rather than a glow.
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

    // The higher the intensity, the more of the pool is drawn.
    final visible = (emitter.particles.length * (0.2 + 0.8 * intensity))
        .round();

    final paint = Paint()..style = PaintingStyle.fill;

    for (var i = 0; i < visible; i++) {
      final p = emitter.particles[i];
      final t = (time.value * p.speed + p.phase) % 1.0;

      // A particle is born well inside the screen, flies out towards the
      // edge and vanishes there. The other way round — born at the edge and
      // flying further out — would spend most of its life outside the
      // viewport, leaving the zone looking sparse despite the same count.
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

      // Fade in and then out across one lifetime, so a particle never
      // blinks on and off.
      final fade = math.sin(t * math.pi);
      paint.color = emitter.action.burst.withValues(
        alpha: (0.22 + 0.78 * intensity) * fade,
      );

      final radius = (1.1 + p.size * 2.3) * (0.7 + 0.9 * intensity);
      // Only the bottom zone is shifted: its edge is the one the footer covers.
      final shift = emitter.action == SwipeAction.unknown ? bottomOverflow : 0;
      canvas.drawCircle(
        Offset(design.dx * sx, design.dy * sy + shift),
        radius,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_BurstPainter oldDelegate) =>
      oldDelegate.bottomOverflow != bottomOverflow;
}
