import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Step 7 — the activity level.
///
/// The end of each card shows **that user's own matching energy
/// expenditure**, not the multiplier. The factor `×1.200` is an internal
/// variable of the TDEE formula — algorithmically correct, but it tells the
/// person choosing nothing at all. "1,620 kcal" answers the question they are
/// actually asking: if I pick this level, how much do I get to eat each day.
class ActivityStep extends StatelessWidget {
  const ActivityStep({
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
    final bmr = profile.bmr;

    return OnboardingScaffold(
      progress: progress,
      onBack: onBack,
      title: 'Bạn vận động nhiều không?',
      subtitle: 'Càng vận động nhiều thì hạn mức năng lượng càng cao',
      scrollable: true,
      onAction: profile.activity == null ? null : onNext,
      child: OptionList(
        children: [
          for (final a in ActivityLevel.values)
            OptionCard(
              label: a.label,
              hint: a.hint,
              leading: switch (a) {
                ActivityLevel.sedentary => '🪑',
                ActivityLevel.light => '🚶',
                ActivityLevel.moderate => '🏃',
                ActivityLevel.active => '🚴',
                ActivityLevel.veryActive => '🏋️',
              },
              trailing: bmr == null
                  ? null
                  : '${formatNumber(bmr * a.factor)} kcal',
              selected: profile.activity == a,
              onTap: () {
                profile.activity = a;
                onChanged();
              },
            ),
        ],
      ),
    );
  }
}
