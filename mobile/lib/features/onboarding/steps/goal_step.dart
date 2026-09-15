import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Bước 5 — mục tiêu sức khỏe.
///
/// Đây là bước quyết định nhất của cả luồng: nó vừa đặt hạn mức năng lượng
/// (cộng hay trừ 500 kcal so với mức tiêu hao), vừa quyết định luồng có hỏi
/// thêm cân nặng mục tiêu hay không.
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
                // Đổi mục tiêu thì cân nặng mục tiêu cũ không còn nghĩa.
                if (!g.needsTargetWeight) profile.targetWeightKg = null;
                onChanged();
              },
            ),
        ],
      ),
    );
  }
}
