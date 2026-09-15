import 'package:flutter/material.dart';

import '../../core/theme/app_motion.dart';
import '../../data/models/health_profile.dart';
import 'calculating_screen.dart';
import 'steps/activity_step.dart';
import 'steps/birth_year_step.dart';
import 'steps/conditions_step.dart';
import 'steps/gender_step.dart';
import 'steps/goal_step.dart';
import 'steps/height_step.dart';
import 'steps/motivation_step.dart';
import 'steps/target_weight_step.dart';
import 'steps/weight_step.dart';

/// Các bước khai báo hồ sơ, theo đúng thứ tự người dùng gặp.
enum OnboardingStep {
  gender,
  birthYear,
  height,
  weight,
  goal,
  targetWeight,
  activity,
  conditions,
  allergies,
  motivation,
}

/// Luồng khai báo hồ sơ sức khỏe, chạy trước phiên khảo sát khẩu vị.
///
/// Toàn bộ dữ liệu giữ trong một đối tượng [HealthProfile] duy nhất và chỉ
/// gửi lên máy chủ ở cuối luồng, giống cách phiên vuốt gửi trọn gói kết quả.
/// Nhờ vậy người dùng lùi lại sửa bao nhiêu lần cũng được mà không sinh ra
/// hàng chục lượt gọi mạng dở dang.
class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({super.key});

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  final _profile = HealthProfile();

  int _index = 0;

  /// Hướng di chuyển gần nhất, dùng để màn hình mới trượt vào đúng phía.
  bool _forward = true;

  /// Bước `targetWeight` chỉ xuất hiện khi mục tiêu là tăng hoặc giảm cân,
  /// nên danh sách bước được tính lại mỗi lần dựng, không cố định.
  List<OnboardingStep> get _steps => [
    for (final step in OnboardingStep.values)
      if (step != OnboardingStep.targetWeight ||
          (_profile.goal?.needsTargetWeight ?? false))
        step,
  ];

  void _next() {
    final steps = _steps;
    if (_index >= steps.length - 1) {
      _finish();
      return;
    }
    setState(() {
      _forward = true;
      _index++;
    });
  }

  void _back() {
    if (_index == 0) return;
    setState(() {
      _forward = false;
      _index--;
    });
  }

  void _finish() {
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: AppMotion.page,
        pageBuilder: (_, _, _) => CalculatingScreen(profile: _profile),
        transitionsBuilder: (_, animation, _, child) =>
            FadeTransition(opacity: animation, child: child),
      ),
    );
  }

  /// Gọi khi một bước tự đổi dữ liệu có thể làm danh sách bước dài ra hoặc
  /// ngắn đi — cụ thể là khi người dùng đổi mục tiêu.
  void _onChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final steps = _steps;
    final step = steps[_index.clamp(0, steps.length - 1)];

    // Tiến độ tính theo vị trí cố định của bước trong enum, không theo danh
    // sách đã lọc. Nếu lấy mẫu số là số bước thực tế, thì đúng lúc người dùng
    // chọn "tăng cân" — thao tác vừa thêm một bước vào luồng — mẫu số nhảy từ
    // 9 lên 10 và thanh tiến độ tụt lại ngay trước mắt họ. Cách này khiến
    // thanh chỉ đứng yên hoặc tiến, và bước bị bỏ qua thì nó nhảy hai nấc.
    final progress =
        (OnboardingStep.values.indexOf(step) + 1) /
        OnboardingStep.values.length;

    final onBack = _index == 0 ? null : _back;

    final child = switch (step) {
      OnboardingStep.gender => GenderStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.birthYear => BirthYearStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.height => HeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.weight => WeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.goal => GoalStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.targetWeight => TargetWeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.activity => ActivityStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.conditions => ConditionsStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
        kind: ConditionKind.disease,
      ),
      OnboardingStep.allergies => ConditionsStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
        kind: ConditionKind.allergy,
      ),
      OnboardingStep.motivation => MotivationStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
    };

    return AnimatedSwitcher(
      duration: AppMotion.page,
      switchInCurve: AppMotion.emphasized,
      switchOutCurve: Curves.easeIn,
      // Màn hình mới trượt vào từ phía người dùng đang đi tới, màn cũ lùi về
      // phía ngược lại — cảm giác như đang đi dọc một hành lang, không phải
      // nhảy giữa các trang rời rạc.
      transitionBuilder: (child, animation) {
        final incoming = child.key == ValueKey(step);
        final dx = _forward ? 1.0 : -1.0;
        return FadeTransition(
          opacity: animation,
          child: SlideTransition(
            position: Tween(
              begin: Offset(incoming ? dx * 0.10 : -dx * 0.10, 0),
              end: Offset.zero,
            ).animate(animation),
            child: child,
          ),
        );
      },
      layoutBuilder: (current, previous) => Stack(
        alignment: Alignment.topCenter,
        children: [...previous, ?current],
      ),
      child: KeyedSubtree(key: ValueKey(step), child: child),
    );
  }
}
