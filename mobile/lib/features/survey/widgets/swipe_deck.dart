import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_motion.dart';
import '../../../data/models/food.dart';
import '../../../data/models/swipe_action.dart';
import 'food_card.dart';
import 'swipe_burst.dart';
import 'swipe_overlay.dart';

/// Chồng thẻ vuốt bốn hướng.
///
/// Đây là thành phần có nhiều chuyển động nhất trong ứng dụng. Toàn bộ được
/// dựng bằng `GestureDetector` + `AnimationController` của Flutter, không
/// dùng thư viện ngoài, để mọi tham số đều giải thích được trong báo cáo.
///
/// Widget này **không tự giữ con trỏ vị trí**. Nó nhận [cursor] từ màn hình
/// cha và báo ngược lên qua [onSwipe]. Nhờ vậy thao tác hoàn tác chỉ là việc
/// màn hình cha giảm [cursor] đi một; deck tự nhận ra và cho thẻ bay ngược
/// trở lại chồng.
class SwipeDeck extends StatefulWidget {
  const SwipeDeck({
    super.key,
    required this.foods,
    required this.cursor,
    required this.onSwipe,
    this.undoFrom,
    this.controller,
  });

  final List<Food> foods;

  /// Chỉ số của thẻ đang nằm trên cùng.
  final int cursor;

  final void Function(Food food, SwipeAction action) onSwipe;

  /// Hướng mà thẻ vừa bị hoàn tác đã bay ra — dùng để cho nó bay ngược lại
  /// đúng đường cũ, thay vì xuất hiện đột ngột.
  final SwipeAction? undoFrom;

  final SwipeDeckController? controller;

  @override
  State<SwipeDeck> createState() => _SwipeDeckState();
}

/// Cho phép màn hình cha ra lệnh vuốt bằng nút bấm, dùng chung một đường
/// chuyển động với cú vuốt bằng tay.
class SwipeDeckController {
  _SwipeDeckState? _state;

  /// Hướng và tiến độ của cú vuốt đang diễn ra.
  ///
  /// Phát ra dưới dạng [ValueNotifier] chứ không phải callback, để các lớp
  /// hiệu ứng như [SwipeBurst] tự vẽ lại phần của mình mà không kéo theo cả
  /// màn hình dựng lại mỗi khung hình.
  final ValueNotifier<SwipeSignal> signal = ValueNotifier(const SwipeSignal());

  void swipe(SwipeAction action) => _state?.commit(action, fromButton: true);

  bool get isBusy => _state?._isAnimating ?? false;

  void dispose() => signal.dispose();
}

class _SwipeDeckState extends State<SwipeDeck> with TickerProviderStateMixin {
  /// Tỷ lệ bề rộng thẻ mà ngón tay phải kéo qua để cú vuốt được tính.
  static const _thresholdX = 0.26;
  static const _thresholdY = 0.22;

  /// Vận tốc đủ lớn thì tính là vuốt dứt khoát, không cần kéo đủ ngưỡng.
  static const _flingVelocity = 820.0;

  /// Góc nghiêng tối đa của thẻ khi kéo hết biên (radian ≈ 16°).
  static const _maxTilt = 0.28;

  /// Góc xoè của từng thẻ trong chồng, tính bằng độ, lấy từ bản thiết kế
  /// Figma: thẻ trên cùng thẳng đứng, ba thẻ sau nghiêng 5°, −10° và 10°.
  /// Số lượng phần tử cũng quyết định chồng thẻ vẽ bao nhiêu lớp.
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

  /// Vị trí thực tế của thẻ trên cùng ở khung hình hiện tại.
  Offset get _offset => _isAnimating ? _animOffset : _drag;

  /// Đẩy hướng và tiến độ hiện tại ra cho các lớp hiệu ứng bên ngoài.
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
    // Con trỏ lùi lại nghĩa là người dùng vừa hoàn tác.
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

  // ── Suy ra hành động từ quãng kéo ────────────────────────────────

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

  // ── Cử chỉ ───────────────────────────────────────────────────────

  void _onPanStart(DragStartDetails _) {
    if (_isAnimating) return;
    _exitCtrl.stop();
    _returnCtrl.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_isAnimating) return;
    setState(() => _drag += details.delta);
    _publish();

    // Rung nhẹ đúng một lần khi vượt ngưỡng, để người dùng cảm nhận được
    // ranh giới mà không cần nhìn.
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

  // ── Chuyển động ──────────────────────────────────────────────────

  /// Thẻ bật về vị trí cũ khi cú vuốt chưa đủ ngưỡng.
  ///
  /// Dùng đường cong nảy nhẹ [AppMotion.spring]: thẻ vượt qua điểm gốc một
  /// chút rồi mới dừng, cho cảm giác đàn hồi thay vì trượt về vô hồn.
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

  /// Thẻ bay ra khỏi màn hình rồi báo kết quả lên màn hình cha.
  void commit(SwipeAction action, {Offset? velocity, bool fromButton = false}) {
    if (_isAnimating || widget.cursor >= widget.foods.length) return;

    HapticFeedback.mediumImpact();
    final food = widget.foods[widget.cursor];
    final from = fromButton ? Offset.zero : _drag;
    final target = _exitTarget(action, from);

    // Vuốt càng mạnh thì thẻ bay ra càng nhanh — giữ được quán tính của
    // cú vuốt thay vì luôn chạy đúng một tốc độ cố định.
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
      // Giữ lại độ lệch trục còn lại để đường bay nối tiếp hướng ngón tay,
      // không bẻ ngoặt sang phương ngang/dọc thuần túy.
      SwipeAction.like => Offset(w * 1.6, from.dy + h * 0.12),
      SwipeAction.dislike => Offset(-w * 1.6, from.dy + h * 0.12),
      SwipeAction.neutral => Offset(from.dx * 0.4, -h * 1.3),
      SwipeAction.unknown => Offset(from.dx * 0.4, h * 1.3),
    };
  }

  /// Hoàn tác — thẻ bay ngược từ ngoài màn hình về đúng chồng thẻ.
  void _playUndo() {
    final action = widget.undoFrom;
    if (action == null || _deckSize.isEmpty) return;

    final from = _exitTarget(action, Offset.zero);
    // Đặt vị trí đầu ngay lập tức. Không có dòng này thì khung hình đầu tiên
    // vẽ thẻ ở giữa màn hình rồi mới nhảy ra ngoài, thấy rõ một cú giật.
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

  // ── Dựng giao diện ───────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _deckSize = constraints.biggest;

        final offset = _offset;
        final action = _committedAction ?? _actionFor(offset);
        final progress = _committedAction != null ? 1.0 : _progressFor(offset);

        final layers = <Widget>[];
        // Vẽ từ thẻ xa nhất trở vào để thứ tự chồng lớp đúng.
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

  /// Đặt một thẻ vào đúng ô giữa vùng chồng thẻ.
  ///
  /// Bề rộng thẻ lấy đúng tỷ lệ của bản thiết kế: 198 trên khung 390, tức
  /// hơn nửa bề ngang màn hình một chút. Chiều cao suy ra từ tỷ lệ 198 : 280.
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

  /// Thẻ phía sau xoay dần về thẳng đứng theo tiến độ của thẻ trên cùng —
  /// mỗi thẻ tiến lên một nấc trong hình xoè quạt của bản thiết kế.
  Widget _buildStackedCard(Food food, int depth, double progress) {
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

  /// Lớp sương trắng — layer `Background_FOG` (6:2), phủ 60 % lên các thẻ phía
  /// sau và nằm dưới thẻ trên cùng, để thẻ đang xét nổi hẳn lên.
  ///
  /// Sương nhạt dần theo tiến độ vuốt: tới lúc thẻ kế tiếp lên làm thẻ chính
  /// thì sương đã tan hết, nên không có cú nhảy sáng đột ngột.
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
    Food food,
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

    // Quãng kéo chuẩn hóa, truyền xuống thẻ để biểu tượng món dịch ngược
    // chiều tạo hiệu ứng chiều sâu.
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

/// Nội suy tuyến tính có kẹp biên — đặt tên riêng để không đụng `lerpDouble`
/// của `dart:ui`.
double _lerp(double a, double b, double t) => a + (b - a) * t.clamp(0.0, 1.0);
