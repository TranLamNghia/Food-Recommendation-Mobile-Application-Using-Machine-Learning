import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/value_wheel.dart';

/// Bước 4 — cân nặng hiện tại.
class WeightStep extends StatefulWidget {
  const WeightStep({
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
  State<WeightStep> createState() => _WeightStepState();
}

class _WeightStepState extends State<WeightStep> {
  late double _weight;

  @override
  void initState() {
    super.initState();
    _weight = widget.profile.weightKg ?? 58;
  }

  @override
  Widget build(BuildContext context) {
    return OnboardingScaffold(
      progress: widget.progress,
      onBack: widget.onBack,
      title: 'Cân nặng hiện tại của bạn?',
      subtitle: 'Cứ lấy số gần nhất bạn nhớ, chỉnh lại sau cũng được',
      center: true,
      onAction: () {
        widget.profile.weightKg = _weight;
        widget.onNext();
      },
      child: ValueWheel(
        min: 30,
        max: 150,
        value: _weight,
        unit: 'kg',
        step: 0.5,
        fractionDigits: 1,
        onChanged: (v) => setState(() => _weight = v),
      ),
    );
  }
}
