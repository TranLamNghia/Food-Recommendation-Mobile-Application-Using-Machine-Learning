import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../data/models/swipe_action.dart';

/// Lớp phủ hiện lên trên thẻ trong lúc vuốt.
///
/// Ba thứ chạy cùng lúc, tất cả đều bám theo [progress] chứ không phải chạy
/// theo thời gian — nhờ vậy người dùng thấy thẻ phản hồi tức thì theo ngón
/// tay, và biết chính xác khi nào cú vuốt đã đủ ngưỡng:
/// 1. một lớp màu mỏng phủ toàn thẻ,
/// 2. viền sáng dày dần,
/// 3. con dấu (icon + chữ) phóng to và xoay nhẹ vào vị trí.
class SwipeOverlay extends StatelessWidget {
  const SwipeOverlay({super.key, required this.action, required this.progress});

  final SwipeAction? action;

  /// Mức độ hoàn thành cú vuốt trong đoạn [0, 1]; 1 nghĩa là đã đủ ngưỡng.
  final double progress;

  @override
  Widget build(BuildContext context) {
    final act = action;
    if (act == null || progress <= 0.01) return const SizedBox.shrink();

    final t = progress.clamp(0.0, 1.0);
    // Con dấu xuất hiện muộn hơn lớp màu một chút để không che thẻ quá sớm.
    final stampT = ((t - 0.12) / 0.55).clamp(0.0, 1.0);

    return IgnorePointer(
      child: LayoutBuilder(
        builder: (context, constraints) {
          // Bo góc bám theo thẻ: 12 trên khổ gốc rộng 198 của bản thiết kế.
          final radius = constraints.maxWidth / 198 * 12;
          // Con dấu cũng co giãn theo thẻ, nếu không nó sẽ tràn ra ngoài
          // khi thẻ chỉ rộng bằng nửa màn hình như trong bản thiết kế.
          final scale = constraints.maxWidth / 198;

          return Stack(
            fit: StackFit.expand,
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: act.color.withValues(alpha: 0.16 * t),
                  borderRadius: BorderRadius.circular(radius),
                  border: Border.all(
                    color: act.color.withValues(alpha: t),
                    width: 3.5 * t,
                  ),
                ),
              ),
              Align(
                alignment: _stampAlignment(act),
                child: Padding(
                  padding: EdgeInsets.all(12 * scale),
                  child: Transform.rotate(
                    angle: _stampAngle(act) * (1.6 - 0.6 * stampT),
                    child: Transform.scale(
                      scale: 0.55 + 0.45 * Curves.easeOutBack.transform(stampT),
                      child: Opacity(
                        opacity: stampT,
                        child: _Stamp(
                          action: act,
                          filled: t >= 0.999,
                          scale: scale,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  /// Con dấu luôn đặt ở phần thẻ **ngược hướng vuốt**, vì đó là phần còn nằm
  /// trong khung nhìn khi thẻ đã trôi đi: vuốt phải thì mép trái còn thấy,
  /// vuốt lên thì mép dưới còn thấy. Đặt cùng hướng vuốt sẽ bị vùng cắt của
  /// chồng thẻ che mất đúng lúc người dùng cần đọc nó nhất.
  Alignment _stampAlignment(SwipeAction action) => switch (action) {
    SwipeAction.like => Alignment.topLeft,
    SwipeAction.dislike => Alignment.topRight,
    // Đặt cao hơn đáy thẻ một chút: khối tên món chiếm 29 % dưới cùng, dán
    // con dấu sát đáy sẽ che mất tên món đúng lúc người dùng đang cân nhắc.
    SwipeAction.neutral => const Alignment(0, 0.28),
    SwipeAction.unknown => Alignment.topCenter,
  };

  double _stampAngle(SwipeAction action) => switch (action) {
    SwipeAction.like => -12 * math.pi / 180,
    SwipeAction.dislike => 12 * math.pi / 180,
    SwipeAction.neutral => -4 * math.pi / 180,
    SwipeAction.unknown => 4 * math.pi / 180,
  };
}

class _Stamp extends StatelessWidget {
  const _Stamp({
    required this.action,
    required this.filled,
    required this.scale,
  });

  final SwipeAction action;

  /// Hệ số co giãn so với khổ thẻ gốc rộng 198 trong Figma.
  final double scale;

  /// Khi cú vuốt đã vượt ngưỡng, con dấu chuyển sang nền đặc — tín hiệu
  /// thị giác cho biết thả tay ra là ăn chắc.
  final bool filled;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      padding: EdgeInsets.symmetric(
        horizontal: 10 * scale,
        vertical: 6 * scale,
      ),
      decoration: BoxDecoration(
        color: filled ? action.color : Colors.white.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(9 * scale),
        border: Border.all(color: action.color, width: 2 * scale),
        boxShadow: [
          if (filled)
            BoxShadow(
              color: action.color.withValues(alpha: 0.45),
              blurRadius: 14 * scale,
              offset: Offset(0, 4 * scale),
            ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            action.icon,
            size: 14 * scale,
            color: filled ? Colors.white : action.color,
          ),
          SizedBox(width: 6 * scale),
          Text(
            action.title.toUpperCase(),
            style: TextStyle(
              fontSize: 11.5 * scale,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.8 * scale,
              color: filled ? Colors.white : action.color,
            ),
          ),
        ],
      ),
    );
  }
}
