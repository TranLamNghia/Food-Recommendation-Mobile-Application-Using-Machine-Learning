import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Bước 1 — giới tính.
///
/// Hỏi đầu tiên vì đây là biến bắt buộc của công thức Mifflin-St Jeor, và là
/// câu dễ trả lời nhất: mở màn bằng một câu không phải suy nghĩ giúp người
/// dùng bước vào luồng thay vì thoát ngay.
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
