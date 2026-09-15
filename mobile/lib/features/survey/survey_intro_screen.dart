import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../../data/mock/mock_foods.dart';
import '../../data/models/swipe_action.dart';
import 'survey_screen.dart';

/// Màn hình mở đầu phiên khảo sát — dạy cử chỉ trước khi bắt đầu.
///
/// Thay vì mô tả bằng chữ, màn hình chạy một thẻ mẫu tự vuốt lần lượt theo
/// bốn hướng. Người dùng nhìn một vòng là hiểu, không cần đọc.
class SurveyIntroScreen extends StatelessWidget {
  const SurveyIntroScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.accentSoft,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Text(
                  'Bước cuối trước khi bắt đầu',
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.accent,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text('Khảo sát khẩu vị', style: text.displaySmall),
              const SizedBox(height: 10),
              Text(
                'Vuốt 30 món để hệ thống nhận ra gu ăn uống của bạn. '
                'Mất khoảng 2 phút và chỉ phải làm một lần duy nhất.',
                style: text.bodyLarge,
              ),
              const Expanded(child: Center(child: _GestureDemo())),
              const _LegendGrid(),
              const SizedBox(height: 22),
              FilledButton(
                onPressed: () => Navigator.of(context).push(
                  PageRouteBuilder(
                    transitionDuration: AppMotion.page,
                    pageBuilder: (_, _, _) =>
                        SurveyScreen(foods: MockFoods.surveyDeck),
                    transitionsBuilder: (_, animation, _, child) =>
                        FadeTransition(
                          opacity: animation,
                          child: ScaleTransition(
                            scale: Tween(begin: 0.94, end: 1.0).animate(
                              CurvedAnimation(
                                parent: animation,
                                curve: AppMotion.emphasized,
                              ),
                            ),
                            child: child,
                          ),
                        ),
                  ),
                ),
                child: const Text('Bắt đầu vuốt'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Thẻ mẫu tự vuốt vòng lặp qua bốn hướng.
class _GestureDemo extends StatefulWidget {
  const _GestureDemo();

  @override
  State<_GestureDemo> createState() => _GestureDemoState();
}

class _GestureDemoState extends State<_GestureDemo>
    with SingleTickerProviderStateMixin {
  static const _cycle = Duration(milliseconds: 2000);

  late final AnimationController _ctrl;
  int _index = 0;

  SwipeAction get _action => SwipeAction.values[_index];

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: _cycle)
      ..addStatusListener((status) {
        // Hết một vòng thì đổi sang hướng kế tiếp rồi chạy lại.
        if (status == AnimationStatus.completed) {
          setState(() => _index = (_index + 1) % SwipeAction.values.length);
          _ctrl.forward(from: 0);
        }
      })
      ..forward();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (context, _) {
        final t = _ctrl.value;

        // Ba chặng trong một vòng: giữ yên → vuốt ra → thẻ mới hiện lên.
        final push = const Interval(
          0.18,
          0.58,
          curve: Curves.easeInOutCubic,
        ).transform(t);
        final fadeOut =
            1 - const Interval(0.42, 0.58, curve: Curves.easeIn).transform(t);
        final fadeIn = const Interval(
          0.68,
          0.92,
          curve: Curves.easeOut,
        ).transform(t);

        final direction = switch (_action) {
          SwipeAction.like => const Offset(1, -0.12),
          SwipeAction.dislike => const Offset(-1, -0.12),
          SwipeAction.neutral => const Offset(0, -1),
          SwipeAction.unknown => const Offset(0, 1),
        };

        final offset = direction * (push * 120);
        final tilt = direction.dx * push * 0.22;
        final opacity = (t < 0.6 ? fadeOut : fadeIn).clamp(0.0, 1.0);

        return SizedBox(
          height: 200,
          child: Stack(
            alignment: Alignment.center,
            clipBehavior: Clip.none,
            children: [
              // Thẻ nền, luôn đứng yên — cho thấy chồng thẻ còn tiếp.
              Transform.scale(
                scale: 0.9,
                child: Transform.translate(
                  offset: const Offset(0, 14),
                  child: const _MiniCard(faded: true),
                ),
              ),
              Opacity(
                opacity: opacity,
                child: Transform.translate(
                  offset: offset,
                  child: Transform.rotate(
                    angle: tilt,
                    child: _MiniCard(
                      action: t < 0.6 ? _action : null,
                      stampProgress: push,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _MiniCard extends StatelessWidget {
  const _MiniCard({this.action, this.stampProgress = 0, this.faded = false});

  final SwipeAction? action;
  final double stampProgress;
  final bool faded;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 168,
      height: 176,
      decoration: BoxDecoration(
        color: faded ? AppColors.surfaceMuted : AppColors.surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(
          color: action == null
              ? AppColors.border
              : action!.color.withValues(alpha: stampProgress.clamp(0, 1)),
          width: action == null ? 1 : 2.5,
        ),
        boxShadow: faded
            ? null
            : const [
                BoxShadow(
                  color: AppColors.shadowSoft,
                  blurRadius: 24,
                  offset: Offset(0, 10),
                ),
              ],
      ),
      child: faded
          ? null
          : Stack(
              alignment: Alignment.center,
              children: [
                const Text('🍜', style: TextStyle(fontSize: 56)),
                if (action != null && stampProgress > 0.05)
                  Positioned(
                    top: 16,
                    child: Transform.rotate(
                      angle: -8 * math.pi / 180,
                      child: Opacity(
                        opacity: stampProgress.clamp(0, 1),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: action!.color,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            action!.title.toUpperCase(),
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }
}

class _LegendGrid extends StatelessWidget {
  const _LegendGrid();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final action in SwipeAction.values)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: action.color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(action.icon, size: 17, color: action.color),
                ),
                const SizedBox(width: 12),
                Text(
                  action.title,
                  style: const TextStyle(
                    fontSize: 14.5,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
                const Spacer(),
                Text(
                  action.hint,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textTertiary,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
