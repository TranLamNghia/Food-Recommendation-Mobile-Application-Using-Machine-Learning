import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// Thanh tiến độ của phiên khảo sát.
///
/// Nằm trong khối `Introduce` ở vùng chân màn hình, tức trên nền chuyển sắc
/// xám. Vì vậy thanh dùng rãnh tối và phần chạy màu trắng — cặp này đọc được
/// ở mọi điểm của dải chuyển sắc, khác với cặp màu sáng trên nền trắng.
///
/// Số đếm dùng `AnimatedSwitcher` trượt dọc, để con số mới đẩy con số cũ đi
/// lên — người dùng thấy rõ mình vừa tiến thêm một bước.
class SurveyProgress extends StatelessWidget {
  const SurveyProgress({super.key, required this.done, required this.total});

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    final ratio = total == 0 ? 0.0 : done / total;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: ratio),
              duration: AppMotion.snapBack,
              curve: AppMotion.emphasized,
              builder: (context, value, _) => LinearProgressIndicator(
                value: value,
                minHeight: 7,
                backgroundColor: Colors.black.withValues(alpha: 0.18),
                valueColor: const AlwaysStoppedAnimation(Colors.white),
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            AnimatedSwitcher(
              duration: AppMotion.quick,
              switchInCurve: AppMotion.standard,
              transitionBuilder: (child, animation) => ClipRect(
                child: SlideTransition(
                  position: Tween(
                    begin: const Offset(0, 0.7),
                    end: Offset.zero,
                  ).animate(animation),
                  child: FadeTransition(opacity: animation, child: child),
                ),
              ),
              child: Text(
                '$done',
                key: ValueKey(done),
                style: const TextStyle(
                  fontFamily: 'Afacad',
                  fontVariations: [FontVariation('wght', 700)],
                  fontSize: 18,
                  color: AppColors.textPrimary,
                  height: 1,
                ),
              ),
            ),
            Text(
              '/$total',
              style: TextStyle(
                fontFamily: 'Afacad',
                fontVariations: const [FontVariation('wght', 600)],
                fontSize: 14,
                color: AppColors.textPrimary.withValues(alpha: 0.55),
                height: 1.15,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
