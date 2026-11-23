import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/app_card.dart';
import '../../data/session.dart';
import '../onboarding/onboarding_flow.dart';
import 'account_settings_screen.dart';
import 'edit_answer_screen.dart';
import 'saved_dishes_screen.dart';

/// The "Tôi" tab: who is signed in, every answer the plan is built from, the
/// dishes the user has ruled in or out, and the app's few settings.
///
/// The answers are the important part. Onboarding asks them once; without
/// this screen a wrong weight or a newly diagnosed condition could only be
/// fixed by starting over.
class AccountScreen extends StatelessWidget {
  const AccountScreen({super.key});

  Future<void> _edit(BuildContext context, OnboardingStep step) async {
    final session = SessionScope.of(context);
    final saved = await EditAnswerScreen.open(context, step);
    if (saved != true || !context.mounted) return;

    // A goal that needs a target weight is incomplete without one.
    if (step == OnboardingStep.goal &&
        (session.profile.goal?.needsTargetWeight ?? false) &&
        session.profile.targetWeightKg == null) {
      await EditAnswerScreen.open(context, OnboardingStep.targetWeight);
      if (!context.mounted) return;
    }

    session.rebuildUpcomingPlans();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Đã lưu. Thực đơn sắp tới được tính lại.'),
        duration: Duration(seconds: 2),
      ),
    );
  }


  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final p = session.profile;
    final macro = p.macroTarget;
    final energy = p.energyTarget;

    String count(Set<String> codes) {
      final n = codes.where((c) => !c.startsWith('__')).length;
      return n == 0 ? 'Không có' : '$n mục';
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            Text('Tôi', style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 18),
            // Only absent for the instant between signing out and the
            // welcome screen taking over.
            if (session.isSignedIn) ...[
              _AccountCard(
                session: session,
                onTap: () => AccountSettingsScreen.open(context),
              ),
              const SizedBox(height: 14),
            ],
            if (energy != null && macro != null) ...[
              AppCard(
                title: 'Hạn mức mỗi ngày',
                child: Row(
                  children: [
                    _Target(formatNumber(energy), 'kcal', AppColors.kcal),
                    _Target(
                      '${formatNumber(macro.protein)} g',
                      'Đạm',
                      AppColors.protein,
                    ),
                    _Target(
                      '${formatNumber(macro.carb)} g',
                      'Bột đường',
                      AppColors.carb,
                    ),
                    _Target(
                      '${formatNumber(macro.fat)} g',
                      'Béo',
                      AppColors.fat,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
            ],
            AppCard(
              title: 'Câu trả lời của bạn',
              padding: const EdgeInsets.fromLTRB(20, 18, 14, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(right: 6, bottom: 6),
                    child: Text(
                      'Chạm vào một dòng để sửa riêng dòng đó. Thực đơn những '
                      'ngày chưa bắt đầu sẽ được tính lại.',
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.45,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
                  AppRow(
                    label: 'Giới tính',
                    value: p.gender?.label ?? 'Chưa khai',
                    onTap: () => _edit(context, OnboardingStep.gender),
                  ),
                  AppRow(
                    label: 'Năm sinh',
                    value: p.birthday == null
                        ? 'Chưa khai'
                        : '${p.birthday!.year} · ${p.age} tuổi',
                    onTap: () => _edit(context, OnboardingStep.birthYear),
                  ),
                  AppRow(
                    label: 'Chiều cao',
                    value: p.heightCm == null
                        ? 'Chưa khai'
                        : '${formatNumber(p.heightCm!)} cm',
                    onTap: () => _edit(context, OnboardingStep.height),
                  ),
                  AppRow(
                    label: 'Cân nặng',
                    value: p.weightKg == null
                        ? 'Chưa khai'
                        : '${formatNumber(p.weightKg!, 1)} kg',
                    onTap: () => _edit(context, OnboardingStep.weight),
                  ),
                  AppRow(
                    label: 'Mục tiêu',
                    value: p.goal?.label ?? 'Chưa khai',
                    onTap: () => _edit(context, OnboardingStep.goal),
                  ),
                  if (p.goal?.needsTargetWeight ?? false)
                    AppRow(
                      label: 'Cân nặng mục tiêu',
                      value: p.targetWeightKg == null
                          ? 'Chưa khai'
                          : '${formatNumber(p.targetWeightKg!, 1)} kg',
                      onTap: () => _edit(context, OnboardingStep.targetWeight),
                    ),
                  AppRow(
                    label: 'Mức vận động',
                    value: p.activity?.label ?? 'Chưa khai',
                    onTap: () => _edit(context, OnboardingStep.activity),
                  ),
                  AppRow(
                    label: 'Bệnh lý',
                    value: count(p.conditions),
                    onTap: () => _edit(context, OnboardingStep.conditions),
                  ),
                  AppRow(
                    label: 'Dị ứng & chế độ ăn',
                    value: count(p.allergies),
                    onTap: () => _edit(context, OnboardingStep.allergies),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppCard(
              title: 'Món đã lưu',
              padding: const EdgeInsets.fromLTRB(20, 18, 14, 10),
              child: Column(
                children: [
                  AppRow(
                    icon: Icons.favorite_border_rounded,
                    label: 'Yêu thích',
                    value: '${session.lovedIds.length} món',
                    onTap: () =>
                        SavedDishesScreen.open(context, SavedKind.loved),
                  ),
                  AppRow(
                    icon: Icons.block_rounded,
                    label: 'Không gợi ý nữa',
                    value: '${session.neverAgainIds.length} món',
                    onTap: () =>
                        SavedDishesScreen.open(context, SavedKind.neverAgain),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppCard(
              title: 'Thông báo',
              padding: const EdgeInsets.fromLTRB(20, 18, 10, 10),
              child: Column(
                children: [
                  _Toggle(
                    label: 'Nhắc ghi bữa ăn',
                    hint: 'Một lời nhắc sau mỗi bữa nếu bạn chưa ghi nhật ký.',
                    value: session.mealReminders,
                    onChanged: (v) => session.mealReminders = v,
                  ),
                  _Toggle(
                    label: 'Tổng kết tuần',
                    hint: 'Mỗi Chủ nhật: tuân thủ thực đơn và cân nặng.',
                    value: session.weeklySummary,
                    onChanged: (v) => session.weeklySummary = v,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppCard(
              padding: const EdgeInsets.fromLTRB(20, 8, 14, 8),
              child: Column(
                children: [
                  AppRow(
                    icon: Icons.info_outline_rounded,
                    label: 'Giới thiệu',
                    onTap: () => showAboutDialog(
                      context: context,
                      applicationName: 'Thực đơn của tôi',
                      applicationVersion: '1.0.0',
                      children: const [
                        Text(
                          'Ứng dụng khuyến nghị thực đơn dinh dưỡng cá nhân '
                          'hóa. Gợi ý trong ứng dụng không thay cho tư vấn '
                          'của bác sĩ hay chuyên gia dinh dưỡng.',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Who is signed in. Tapping it opens the account settings.
class _AccountCard extends StatelessWidget {
  const _AccountCard({required this.session, required this.onTap});

  final AppSession session;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final email = session.accountEmail ?? '';
    final name = session.displayName;
    final shown = (name == null || name.isEmpty) ? email : name;

    return Semantics(
      button: true,
      label: 'Cài đặt tài khoản',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(24),
        child: AppCard(child: _identity(context, shown, email)),
      ),
    );
  }

  Widget _identity(BuildContext context, String shown, String email) {
    return Row(
      children: [
        Container(
          width: 52,
          height: 52,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            color: AppColors.ink,
            shape: BoxShape.circle,
          ),
          child: Text(
            shown.characters.first.toUpperCase(),
            style: const TextStyle(
              fontSize: 22,
              color: AppColors.accent,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                shown,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              if (shown != email)
                Text(
                  email,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        const Icon(
          Icons.chevron_right_rounded,
          size: 22,
          color: AppColors.textTertiary,
        ),
      ],
    );
  }
}

class _Target extends StatelessWidget {
  const _Target(this.value, this.label, this.color);

  final String value;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 18,
              color: color,
              fontVariations: const [FontVariation('wght', 700)],
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
              fontSize: 12.5,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _Toggle extends StatelessWidget {
  const _Toggle({
    required this.label,
    required this.hint,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final String hint;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    fontSize: 15,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 600)],
                  ),
                ),
                Text(
                  hint,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.4,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: value,
            onChanged: onChanged,
            activeTrackColor: AppColors.ink,
          ),
        ],
      ),
    );
  }
}
