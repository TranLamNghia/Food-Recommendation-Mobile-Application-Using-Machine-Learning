import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/value_wheel.dart';

/// Bước 2 — năm sinh.
///
/// Hỏi năm sinh thay vì tuổi để lưu đúng kiểu `DATE` của cột
/// `health_profiles.birth_date`. Ngày và tháng mặc định là 1/1: sai lệch tối
/// đa một năm tuổi, tương đương 5 kcal trong BMR, không đáng để bắt người
/// dùng chọn thêm hai bánh xe nữa.
class BirthYearStep extends StatefulWidget {
  const BirthYearStep({
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

  @override
  State<BirthYearStep> createState() => _BirthYearStepState();
}

class _BirthYearStepState extends State<BirthYearStep> {
  late int _year;

  @override
  void initState() {
    super.initState();
    _year = widget.profile.birthday?.year ?? DateTime.now().year - 22;
  }

  @override
  Widget build(BuildContext context) {
    final thisYear = DateTime.now().year;

    return OnboardingScaffold(
      progress: widget.progress,
      onBack: widget.onBack,
      title: 'Bạn sinh năm nào?',
      subtitle: 'Tuổi ảnh hưởng trực tiếp tới mức chuyển hóa cơ bản',
      center: true,
      onAction: () {
        widget.profile.birthday = DateTime(_year, 1, 1);
        widget.onNext();
      },
      child: ValueWheel(
        min: (thisYear - 80).toDouble(),
        max: (thisYear - 10).toDouble(),
        value: _year.toDouble(),
        unit: '',
        onChanged: (v) => setState(() => _year = v.round()),
      ),
    );
  }
}
