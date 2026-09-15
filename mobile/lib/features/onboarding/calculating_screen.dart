import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../../data/models/health_profile.dart';
import '../survey/survey_intro_screen.dart';

/// Màn hình tính hạn mức, chạy sau khi khai báo xong hồ sơ.
///
/// Các phép tính ở đây — BMI, BMR, TDEE — chỉ mất vài micro giây, nên về mặt
/// kỹ thuật màn hình này hoàn toàn không cần thiết. Nó tồn tại vì lý do khác:
/// người dùng vừa bỏ ra chín bước khai báo, và cần thấy số liệu của mình được
/// dùng vào việc gì. Từng dòng chạy qua là từng bước có thật của Bước 1 trong
/// thuật toán, không phải chữ trang trí.
class CalculatingScreen extends StatefulWidget {
  const CalculatingScreen({super.key, required this.profile});

  final HealthProfile profile;

  @override
  State<CalculatingScreen> createState() => _CalculatingScreenState();
}

class _CalculatingScreenState extends State<CalculatingScreen>
    with SingleTickerProviderStateMixin {
  static const _lines = [
    'Đang tính chỉ số khối cơ thể',
    'Đang áp dụng công thức Mifflin-St Jeor',
    'Đang ước tính năng lượng tiêu hao cả ngày',
    'Đang lọc món theo bệnh lý và dị ứng',
    'Đang chốt hạn mức cho từng bữa',
  ];

  static const _perLine = Duration(milliseconds: 900);

  late final AnimationController _spin;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    _spin = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
    _advance();
  }

  Future<void> _advance() async {
    for (var i = 1; i < _lines.length; i++) {
      await Future.delayed(_perLine);
      if (!mounted) return;
      setState(() => _index = i);
    }
    await Future.delayed(_perLine);
    if (!mounted) return;

    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: AppMotion.page,
        pageBuilder: (_, _, _) => const SurveyIntroScreen(),
        transitionsBuilder: (_, animation, _, child) =>
            FadeTransition(opacity: animation, child: child),
      ),
    );
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 40),
            Text('Đang dựng hạn mức cho bạn', style: text.titleMedium),
            const Spacer(),
            RotationTransition(
              turns: _spin,
              child: const SizedBox(
                width: 88,
                height: 88,
                child: CircularProgressIndicator(
                  strokeWidth: 6,
                  strokeCap: StrokeCap.round,
                  value: 0.22,
                  backgroundColor: AppColors.surfaceMuted,
                  valueColor: AlwaysStoppedAnimation(AppColors.accent),
                ),
              ),
            ),
            const SizedBox(height: 48),
            // Cửa sổ ba dòng: dòng vừa xong mờ phía trên, dòng đang chạy đậm
            // ở giữa, dòng sắp tới mờ phía dưới.
            SizedBox(
              height: 140,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _Line(text: _lineAt(_index - 1), state: _LineState.done),
                  const SizedBox(height: 14),
                  _Line(text: _lineAt(_index), state: _LineState.current),
                  const SizedBox(height: 14),
                  _Line(text: _lineAt(_index + 1), state: _LineState.upcoming),
                ],
              ),
            ),
            const Spacer(),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  String _lineAt(int i) => i < 0 || i >= _lines.length ? '' : _lines[i];
}

enum _LineState { done, current, upcoming }

class _Line extends StatelessWidget {
  const _Line({required this.text, required this.state});

  final String text;
  final _LineState state;

  @override
  Widget build(BuildContext context) {
    final current = state == _LineState.current;

    return AnimatedSwitcher(
      duration: AppMotion.quick,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position: Tween(
            begin: const Offset(0, 0.4),
            end: Offset.zero,
          ).animate(animation),
          child: child,
        ),
      ),
      child: Padding(
        key: ValueKey('$text$state'),
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: 'Afacad',
            fontVariations: [FontVariation('wght', current ? 700 : 400)],
            fontSize: current ? 21 : 16,
            height: 1.3,
            color: current ? AppColors.textPrimary : AppColors.textTertiary,
          ),
        ),
      ),
    );
  }
}
