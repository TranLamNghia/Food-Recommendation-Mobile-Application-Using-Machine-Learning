import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';
import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';

/// Bước cuối — màn xác nhận mục tiêu.
///
/// Không hỏi thêm gì, chỉ đọc lại cho người dùng nghe điều họ vừa chọn, dưới
/// dạng một con số lớn. Đây là chỗ luồng dài chín bước được đền đáp: người
/// dùng thấy đích của mình thành hình trước khi bước tiếp.
class MotivationStep extends StatelessWidget {
  const MotivationStep({
    super.key,
    required this.profile,
    required this.progress,
    required this.onBack,
    required this.onNext,
  });

  final HealthProfile profile;
  final double progress;
  final VoidCallback? onBack;
  final VoidCallback onNext;

  /// Con số nổi bật và phần chữ hai bên nó.
  ///
  /// Mục tiêu tăng hoặc giảm cân thì con số là số cân chênh lệch. Hai mục
  /// tiêu còn lại không có con số cân nặng nào có nghĩa, nên lấy hạn mức năng
  /// lượng hằng ngày thay thế.
  ({String before, double value, String unit, String after}) get _headline {
    final goal = profile.goal;
    final delta = profile.weightDelta;

    if (goal != null && goal.needsTargetWeight && delta != null) {
      final verb = goal == HealthGoal.loseWeight ? 'Giảm' : 'Tăng';
      return (
        before: '$verb ',
        value: delta.abs(),
        unit: ' kg',
        after: ' là mục tiêu trong tầm tay của bạn',
      );
    }

    return (
      before: '',
      value: profile.energyTarget ?? 0,
      unit: ' kcal',
      after: ' mỗi ngày là hạn mức vừa vặn với bạn',
    );
  }

  @override
  Widget build(BuildContext context) {
    final h = _headline;
    final digits = h.unit.trim() == 'kg' ? 1 : 0;

    return OnboardingScaffold(
      progress: progress,
      onBack: onBack,
      center: true,
      title: '',
      actionLabel: 'Tôi sẵn sàng bắt đầu',
      onAction: onNext,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: h.value),
            duration: const Duration(milliseconds: 900),
            curve: AppMotion.emphasized,
            builder: (context, value, _) => Text.rich(
              TextSpan(
                style: Theme.of(context).textTheme.displaySmall,
                children: [
                  TextSpan(text: h.before),
                  TextSpan(
                    text: formatNumber(value, digits) + h.unit,
                    style: const TextStyle(color: AppColors.accent),
                  ),
                  TextSpan(text: h.after),
                ],
              ),
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: 18),
          _FadeIn(
            delay: 600,
            child: Text(
              'Hạn mức này được tính bằng công thức Mifflin-St Jeor dựa trên '
              'chính số liệu bạn vừa khai, không phải con số áng chừng.',
              style: Theme.of(context).textTheme.bodyLarge,
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }
}

class _FadeIn extends StatefulWidget {
  const _FadeIn({required this.delay, required this.child});

  final int delay;
  final Widget child;

  @override
  State<_FadeIn> createState() => _FadeInState();
}

class _FadeInState extends State<_FadeIn> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: AppMotion.page);
    Future.delayed(Duration(milliseconds: widget.delay), () {
      if (mounted) _ctrl.forward();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curved = CurvedAnimation(parent: _ctrl, curve: AppMotion.emphasized);
    return AnimatedBuilder(
      animation: curved,
      builder: (context, child) => Opacity(
        opacity: curved.value,
        child: Transform.translate(
          offset: Offset(0, 14 * (1 - curved.value)),
          child: child,
        ),
      ),
      child: widget.child,
    );
  }
}
