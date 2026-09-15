import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Bước 7 — mức vận động.
///
/// Cuối mỗi thẻ là **mức năng lượng tiêu hao tương ứng của chính người dùng**,
/// không phải hệ số nhân. Hệ số `×1,200` là biến nội bộ của công thức TDEE —
/// nó đúng về mặt thuật toán nhưng chẳng nói lên điều gì với người đang chọn.
/// Còn "1.620 kcal" thì trả lời thẳng câu hỏi họ đang nghĩ: chọn mức này thì
/// mỗi ngày tôi được ăn bao nhiêu.
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
