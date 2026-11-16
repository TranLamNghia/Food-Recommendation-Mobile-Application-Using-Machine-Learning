import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Step 5 — the health goal.
///
/// This is the most consequential step of the whole flow: it both sets the
/// energy target (plus or minus 500 kcal against the expenditure) and decides
/// whether the flow goes on to ask for a target weight.
class GoalStep extends StatelessWidget {
  const GoalStep({
    super.key,
    required this.profile,
    required this.progress,
    required this.onBack,
    required this.onNext,
    required this.onChanged,
  });

  final HealthProfile profile;
  final double progress;
  final VoidCallback? onBack;
  final VoidCallback onNext;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return OnboardingScaffold(
      progress: progress,
      onBack: onBack,
      title: 'Bạn muốn đạt điều gì?',
      subtitle: 'Thực đơn sẽ được tính theo mục tiêu này',
      onAction: profile.goal == null ? null : onNext,
      child: OptionList(
        children: [
          for (final g in HealthGoal.values)
            OptionCard(
              label: g.label,
              hint: g.hint,
              leading: switch (g) {
                HealthGoal.loseWeight => '📉',
                HealthGoal.maintain => '⚖️',
                HealthGoal.gainWeight => '📈',
                HealthGoal.healthyEating => '🥗',
              },
              selected: profile.goal == g,
              onTap: () {
                profile.goal = g;
                // Changing the goal makes the old target weight
                // meaningless.
                if (!g.needsTargetWeight) profile.targetWeightKg = null;
                onChanged();
              },
            ),
        ],
      ),
    );
  }
}
