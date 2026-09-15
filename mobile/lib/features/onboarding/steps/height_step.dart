import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/value_wheel.dart';

/// Bước 3 — chiều cao.
class HeightStep extends StatefulWidget {
  const HeightStep({
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
  State<HeightStep> createState() => _HeightStepState();
}

class _HeightStepState extends State<HeightStep> {
  late double _height;

  @override
  void initState() {
    super.initState();
    _height = widget.profile.heightCm ?? 165;
  }

  @override
  Widget build(BuildContext context) {
    return OnboardingScaffold(
      progress: widget.progress,
      onBack: widget.onBack,
      title: 'Bạn cao bao nhiêu?',
      subtitle: 'Cùng với cân nặng, đây là cơ sở tính chỉ số khối cơ thể',
      center: true,
      onAction: () {
        widget.profile.heightCm = _height;
        widget.onNext();
      },
      child: ValueWheel(
        min: 130,
        max: 210,
        value: _height,
        unit: 'cm',
        onChanged: (v) => setState(() => _height = v),
      ),
    );
  }
}
