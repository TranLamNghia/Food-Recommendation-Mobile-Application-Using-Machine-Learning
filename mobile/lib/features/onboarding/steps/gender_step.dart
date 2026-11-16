import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Step 1 — sex.
///
/// Asked first because it is a mandatory variable of the Mifflin-St Jeor
/// formula, and it is the easiest question to answer: opening with something
/// that needs no thought gets the user into the flow instead of out of it.
class GenderStep extends StatelessWidget {
  const GenderStep({
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
      title: 'Bạn là nam hay nữ?',
      subtitle: 'Công thức tính năng lượng khác nhau giữa hai giới',
      onAction: profile.gender == null ? null : onNext,
      child: OptionList(
        children: [
          for (final g in Gender.values)
            OptionCard(
              label: g.label,
              selected: profile.gender == g,
              onTap: () {
                profile.gender = g;
                onChanged();
              },
            ),
        ],
      ),
    );
  }
}
