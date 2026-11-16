import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/value_wheel.dart';

/// Step 2 — year of birth.
///
/// The year is asked rather than the age, so it can be stored in the `DATE`
/// type of the `health_profiles.birth_date` column. The day and month default
/// to 1 January: at most one year of age off, which is 5 kcal in the BMR —
/// not worth making the user spin two more wheels for.
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
