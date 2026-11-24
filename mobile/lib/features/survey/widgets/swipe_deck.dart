import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_motion.dart';
import '../../../data/models/food_brief.dart';
import '../../../data/models/swipe_action.dart';
import 'food_card.dart';
import 'swipe_burst.dart';
import 'swipe_overlay.dart';

/// The four-direction swipe deck.
///
/// This is the most heavily animated component in the app. All of it is built
/// from Flutter's own `GestureDetector` + `AnimationController`, with no
/// external library, so every parameter can be explained in the report.
///
/// This widget **does not hold the position cursor**. It takes [cursor] from
/// the parent screen and reports back through [onSwipe]. That makes undo
/// nothing more than the parent decrementing [cursor]; the deck notices by
/// itself and flies the card back onto the stack.
class SwipeDeck extends StatefulWidget {
  const SwipeDeck({
    super.key,
    required this.foods,
    required this.cursor,
    required this.onSwipe,
    this.undoFrom,
    this.controller,
  });

  final List<FoodBrief> foods;

  /// The index of the card currently on top.
  final int cursor;

  final void Function(FoodBrief food, SwipeAction action) onSwipe;

  /// The direction the just-undone card flew out in — used to fly it back
  /// along the same path rather than having it appear out of nowhere.
  final SwipeAction? undoFrom;

  final SwipeDeckController? controller;

  @override
  State<SwipeDeck> createState() => _SwipeDeckState();
}

/// Lets the parent screen command a swipe from a button, sharing the same
/// motion path as a hand swipe.
class SwipeDeckController {
  _SwipeDeckState? _state;

  /// The direction and progress of the swipe in flight.
  ///
  /// Published as a [ValueNotifier] rather than a callback, so effect layers
  /// such as [SwipeBurst] repaint their own part without dragging the whole
  /// screen into a rebuild every frame.
  final ValueNotifier<SwipeSignal> signal = ValueNotifier(const SwipeSignal());

  void swipe(SwipeAction action) => _state?.commit(action, fromButton: true);

  bool get isBusy => _state?._isAnimating ?? false;

  void dispose() => signal.dispose();
}

class _SwipeDeckState extends State<SwipeDeck> with TickerProviderStateMixin {
  /// The fraction of the card's width the finger has to drag for the
  /// swipe to count.
  static const _thresholdX = 0.26;
  static const _thresholdY = 0.22;

  /// A high enough velocity counts as a decisive swipe, with no need to
  /// reach the distance threshold.
  static const _flingVelocity = 820.0;

  /// The card's maximum tilt at full drag (radians ≈ 16°).
  static const _maxTilt = 0.28;

  /// Each card's fan angle in the stack, in degrees, taken from the Figma
  /// design: the top card upright, the three behind it at 5°, −10° and 10°.
  /// The number of entries also decides how many layers the deck draws.
  static const _restAngles = <double>[0, 5, -10, 10];

  late final AnimationController _exitCtrl;
  late final AnimationController _returnCtrl;
  late final AnimationController _undoCtrl;

  Offset _drag = Offset.zero;
  Offset _animOffset = Offset.zero;
  SwipeAction? _committedAction;
  bool _crossedThreshold = false;
  Size _deckSize = Size.zero;

  bool get _isAnimating =>
      _exitCtrl.isAnimating || _returnCtrl.isAnimating || _undoCtrl.isAnimating;

  /// The top card's actual position in the current frame.
  Offset get _offset => _isAnimating ? _animOffset : _drag;

  /// Pushes the current direction and progress out to the external
  /// effect layers.
  void _publish() {
    final controller = widget.controller;
    if (controller == null) return;
    final offset = _offset;
    controller.signal.value = SwipeSignal(
      action: _committedAction ?? _actionFor(offset),
      progress: _committedAction != null ? 1.0 : _progressFor(offset),
    );
  }

  @override
  void initState() {
    super.initState();
    widget.controller?._state = this;

    _exitCtrl = AnimationController(vsync: this, duration: AppMotion.flyOut);
    _returnCtrl = AnimationController(
      vsync: this,
      duration: AppMotion.snapBack,
    );
    _undoCtrl = AnimationController(vsync: this, duration: AppMotion.undo);
  }

  @override
  void didUpdateWidget(SwipeDeck oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.controller != oldWidget.controller) {
      oldWidget.controller?._state = null;
      widget.controller?._state = this;
    }
    // The cursor moving back means the user has just undone a swipe.
    if (widget.cursor < oldWidget.cursor) _playUndo();
  }

  @override
  void dispose() {
    widget.controller?._state = null;
    _exitCtrl.dispose();
    _returnCtrl.dispose();
    _undoCtrl.dispose();
    super.dispose();
  }

  // ── Deriving the action from the drag ────────────────────────────

  SwipeAction? _actionFor(Offset d) {
    if (d.distance < 6) return null;
    if (d.dx.abs() >= d.dy.abs()) {
      return d.dx > 0 ? SwipeAction.like : SwipeAction.dislike;
    }
    return d.dy < 0 ? SwipeAction.neutral : SwipeAction.unknown;
  }

  double _progressFor(Offset d) {
    if (_deckSize.isEmpty) return 0;
    final action = _actionFor(d);
    if (action == null) return 0;
    final ratio = action.isHorizontal
        ? d.dx.abs() / (_deckSize.width * _thresholdX)
        : d.dy.abs() / (_deckSize.height * _thresholdY);
    return ratio.clamp(0.0, 1.0);
  }

  // ── Gestures ─────────────────────────────────────────────────────

  void _onPanStart(DragStartDetails _) {
    if (_isAnimating) return;
    _exitCtrl.stop();
    _returnCtrl.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_isAnimating) return;
    setState(() => _drag += details.delta);
    _publish();

    // One light haptic tick exactly when the threshold is crossed, so the
    // user can feel the boundary without looking.
    final crossed = _progressFor(_drag) >= 1;
    if (crossed != _crossedThreshold) {
      _crossedThreshold = crossed;
      if (crossed) HapticFeedback.selectionClick();
    }
  }

  void _onPanEnd(DragEndDetails details) {
    if (_isAnimating) return;
    final velocity = details.velocity.pixelsPerSecond;
    final action = _actionFor(_drag);

    if (action != null) {
      final fastEnough = action.isHorizontal
          ? velocity.dx.abs() > _flingVelocity &&
                velocity.dx.sign == _drag.dx.sign
          : velocity.dy.abs() > _flingVelocity &&
                velocity.dy.sign == _drag.dy.sign;

      if (_progressFor(_drag) >= 1 || fastEnough) {
        commit(action, velocity: velocity);
        return;
      }
    }
    _snapBack();
  }

  // ── Motion ───────────────────────────────────────────────────────

  /// The card snaps back when the swipe did not reach the threshold.
  ///
  /// It uses the slight overshoot curve [AppMotion.spring]: the card passes
  /// its origin a little before settling, which feels elastic rather than
  /// lifelessly sliding home.
  void _snapBack() {
    final from = _drag;
    _crossedThreshold = false;

    final anim = _returnCtrl.drive(
      Tween(
        begin: from,
        end: Offset.zero,
      ).chain(CurveTween(curve: AppMotion.spring)),
    );

    void tick() {
      setState(() => _animOffset = anim.value);
      _publish();
    }

    anim.addListener(tick);

    _returnCtrl.forward(from: 0).whenComplete(() {
      anim.removeListener(tick);
      if (!mounted) return;
      setState(() => _drag = _animOffset = Offset.zero);
      _publish();
    });
  }

  /// The card flies off screen and then reports the result to the
  /// parent screen.
  void commit(SwipeAction action, {Offset? velocity, bool fromButton = false}) {
    if (_isAnimating || widget.cursor >= widget.foods.length) return;

    HapticFeedback.mediumImpact();
    final food = widget.foods[widget.cursor];
    final from = fromButton ? Offset.zero : _drag;
    final target = _exitTarget(action, from);

    // The harder the swipe, the faster the card leaves — preserving the
    // gesture's momentum instead of always running at one fixed speed.
    final speed = velocity?.distance ?? 0;
    final ms = (AppMotion.flyOut.inMilliseconds - (speed / 60).clamp(0, 110))
        .round();
    _exitCtrl.duration = Duration(milliseconds: math.max(150, ms));

    setState(() => _committedAction = action);
    _publish();

    final anim = _exitCtrl.drive(
      Tween(begin: from, end: target).chain(CurveTween(curve: AppMotion.eject)),
    );

    void tick() => setState(() => _animOffset = anim.value);
    anim.addListener(tick);

    _exitCtrl.forward(from: 0).whenComplete(() {
      anim.removeListener(tick);
      if (!mounted) return;
      setState(() {
        _drag = _animOffset = Offset.zero;
        _committedAction = null;
        _crossedThreshold = false;
      });
      _publish();
      widget.onSwipe(food, action);
    });
  }

  Offset _exitTarget(SwipeAction action, Offset from) {
    final w = _deckSize.width;
    final h = _deckSize.height;
    return switch (action) {
      // Keep the remaining off-axis offset so the flight path continues
      // the finger's direction instead of snapping to a pure horizontal or
      // vertical one.
      SwipeAction.like => Offset(w * 1.6, from.dy + h * 0.12),
      SwipeAction.dislike => Offset(-w * 1.6, from.dy + h * 0.12),
      SwipeAction.neutral => Offset(from.dx * 0.4, -h * 1.3),
      SwipeAction.unknown => Offset(from.dx * 0.4, h * 1.3),
    };
  }

  /// Undo — the card flies back from off screen onto the deck.
  void _playUndo() {
    final action = widget.undoFrom;
    if (action == null || _deckSize.isEmpty) return;

    final from = _exitTarget(action, Offset.zero);
    // Set the starting position immediately. Without this line the first
    // frame draws the card in the middle of the screen and only then jumps
    // it outside, which reads as a visible stutter.
    _animOffset = from;

    final anim = _undoCtrl.drive(
      Tween(
        begin: from,
        end: Offset.zero,
      ).chain(CurveTween(curve: AppMotion.standard)),
    );

    void tick() => setState(() => _animOffset = anim.value);
    anim.addListener(tick);

    _undoCtrl.forward(from: 0).whenComplete(() {
      anim.removeListener(tick);
      if (mounted) setState(() => _drag = _animOffset = Offset.zero);
    });
  }

  // ── Building the interface ───────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _deckSize = constraints.biggest;

        final offset = _offset;
        final action = _committedAction ?? _actionFor(offset);
        final progress = _committedAction != null ? 1.0 : _progressFor(offset);

        final layers = <Widget>[];
        // Painted from the furthest card inwards, so the layering
        // order is right.
        for (var depth = _restAngles.length - 1; depth >= 1; depth--) {
          final index = widget.cursor + depth;
          if (index < 0 || index >= widget.foods.length) continue;
          layers.add(_buildStackedCard(widget.foods[index], depth, progress));
        }

        layers.add(_buildFog(progress));

        if (widget.cursor >= 0 && widget.cursor < widget.foods.length) {
          layers.add(
            _buildTopCard(
              widget.foods[widget.cursor],
              offset,
              action,
              progress,
            ),
          );
        }

        return Stack(fit: StackFit.expand, children: layers);
      },
    );
  }

  /// Places a card in its slot at the centre of the deck area.
  ///
  /// The card's width takes the design's exact ratio: 198 on a 390 frame,
  /// that is, a little over half the screen width. The height follows from
  /// the 198 : 280 ratio.
  Widget _cardSlot(Widget child) {
    final width = _deckSize.width * (198 / 390);
    return Center(
      child: SizedBox(
        width: width,
        height: width / FoodCard.aspectRatio,
        child: child,
      ),
    );
  }

  /// The cards behind rotate towards upright as the top card progresses —
  /// each one advancing a notch through the design's fan shape.
  Widget _buildStackedCard(FoodBrief food, int depth, double progress) {
    final angle = _lerp(_restAngles[depth], _restAngles[depth - 1], progress);

    return Positioned.fill(
      child: IgnorePointer(
        child: _cardSlot(
          Transform.rotate(
            angle: angle * math.pi / 180,
            child: FoodCard(food: food, elevated: false),
          ),
        ),
      ),
    );
  }

  /// The white fog layer — `Background_FOG` (6:2), covering the cards
  /// behind at 60 % and sitting under the top card, so the card under
  /// consideration stands out.
  ///
  /// The fog thins as the swipe progresses: by the time the next card becomes
  /// the main one the fog has cleared entirely, so there is no sudden jump in
  /// brightness.
  Widget _buildFog(double progress) {
    return Positioned.fill(
      child: IgnorePointer(
        child: ColoredBox(
          color: Colors.white.withValues(alpha: _lerp(0.6, 0, progress)),
        ),
      ),
    );
  }

  Widget _buildTopCard(
    FoodBrief food,
    Offset offset,
    SwipeAction? action,
    double progress,
  ) {
    final tilt = _deckSize.isEmpty
        ? 0.0
        : (offset.dx / _deckSize.width * _maxTilt * 2).clamp(
            -_maxTilt,
            _maxTilt,
          );

    // The normalised drag, passed down to the card so the dish icon shifts
    // the opposite way and creates the depth effect.
    final parallax = _deckSize.isEmpty
        ? Offset.zero
        : Offset(
            (offset.dx / _deckSize.width).clamp(-1.0, 1.0),
            (offset.dy / _deckSize.height).clamp(-1.0, 1.0),
          );

    return Positioned.fill(
      child: Transform.translate(
        offset: offset,
        child: Transform.rotate(
          angle: tilt,
          child: _cardSlot(
            GestureDetector(
              onPanStart: _onPanStart,
              onPanUpdate: _onPanUpdate,
              onPanEnd: _onPanEnd,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  FoodCard(food: food, parallax: parallax),
                  SwipeOverlay(action: action, progress: progress),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Clamped linear interpolation — given its own name so it does not clash
/// with `dart:ui`'s `lerpDouble`.
double _lerp(double a, double b, double t) => a + (b - a) * t.clamp(0.0, 1.0);
