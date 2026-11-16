import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/value_wheel.dart';

/// Step 6 — the target weight.
///
/// Shown only when the goal is to gain or lose weight. Someone who chose
/// "maintain" or "healthy eating" has no such figure, and asking anyway only
/// makes the flow longer.
class TargetWeightStep extends StatefulWidget {
  const TargetWeightStep({
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
  State<TargetWeightStep> createState() => _TargetWeightStepState();
}

class _TargetWeightStepState extends State<TargetWeightStep> {
  late double _target;

  @override
  void initState() {
    super.initState();
    final current = widget.profile.weightKg ?? 58;
    final losing = widget.profile.goal == HealthGoal.loseWeight;
    _target =
        widget.profile.targetWeightKg ?? (losing ? current - 5 : current + 5);
  }

  @override
  Widget build(BuildContext context) {
    return OnboardingScaffold(
      progress: widget.progress,
      onBack: widget.onBack,
      title: 'Bạn muốn về mức bao nhiêu?',
      subtitle: 'Có đích cụ thể thì theo dõi tiến độ mới rõ ràng',
      center: true,
      onAction: () {
        widget.profile.targetWeightKg = _target;
        widget.onNext();
      },
      child: ValueWheel(
        min: 30,
        max: 150,
        value: _target,
        unit: 'kg',
        step: 0.5,
        fractionDigits: 1,
        onChanged: (v) => setState(() => _target = v),
      ),
    );
  }
}
