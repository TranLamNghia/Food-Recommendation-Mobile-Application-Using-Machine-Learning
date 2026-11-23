import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/app_card.dart';
import '../../data/session.dart';
import '../home/home_shell.dart';
import '../onboarding/onboarding_flow.dart';
import '../survey/survey_intro_screen.dart';
import 'auth_screen.dart';

/// First screen of the app: says what it does, then offers the two ways in.
///
/// Both ways go through an account. The profile, the learned taste and the
/// diary are stored under it, so there is no anonymous mode to fall back to.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  static const _points = [
    (
      icon: Icons.favorite_border_rounded,
      title: 'Tính theo cơ thể bạn',
      body: 'Hạn mức năng lượng và ba chất đa lượng tính từ hồ sơ sức khỏe.',
    ),
    (
      icon: Icons.shield_outlined,
      title: 'An toàn với bệnh lý và dị ứng',
      body: 'Món không phù hợp bị loại trước khi được chấm điểm.',
    ),
    (
      icon: Icons.auto_awesome_outlined,
      title: 'Càng dùng càng hợp gu',
      body:
          'Mỗi lần vuốt, đổi món hay chấm sao đều dạy hệ thống thêm một chút.',
    ),
  ];

  /// Opens the auth form in [mode], then routes by what the account holds.
  /// The form lets the user switch between the two modes, so either button
  /// can end in either outcome.
  Future<void> _enter(BuildContext context, AuthMode mode) async {
    final ok = await Navigator.of(context)
        .push<bool>(MaterialPageRoute(builder: (_) => AuthScreen(mode: mode)));
    if (ok != true || !context.mounted) return;

    final session = SessionScope.of(context);
    Navigator.of(context).pushReplacement(fadeRoute(nextFor(session)));
  }

  /// Where an account goes after signing in.
  ///
  /// This is the whole point of having an account: someone who answered the
  /// questions last week must not be asked them again. Which screen that is
  /// depends on how far they got, and the two modes know that in different
  /// ways.
  @visibleForTesting
  static Widget nextFor(AppSession session) {
    if (session.isOnline) {
      // ONLINE: what `GET /auth/me` reported, read back in `logIn`.
      //
      // `onboardingCompletedAt` is the server's own record of having
      // accepted the taste survey, and `isComplete` is true once the six
      // fields step 1 needs came back from §7.2.1. Three states, in the
      // order the user passes through them.
      if (session.hasFinishedOnboarding) return const HomeShell();
      if (session.profile.isComplete) return const SurveyIntroScreen();
      return const OnboardingFlow();
    }

    // OFFLINE: nothing survives a restart, so a plan built earlier in this
    // session is the only evidence the questions were ever answered.
    return session.todayPlan != null
        ? const HomeShell()
        : const OnboardingFlow();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        // Fills the screen when there is room and scrolls when there is not
        // (small phones, large system font) instead of overflowing.
        child: LayoutBuilder(
          builder: (context, box) => SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: box.maxHeight),
              child: IntrinsicHeight(child: _body(context, text)),
            ),
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context, TextTheme text) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Spacer(flex: 2),
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: AppColors.ink,
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Icon(
              Icons.restaurant_menu_rounded,
              size: 32,
              color: AppColors.accent,
            ),
          ),
          const SizedBox(height: 28),
          Text(
            'Thực đơn mỗi ngày,\ntính riêng cho bạn',
            style: text.displaySmall,
          ),
          const SizedBox(height: 12),
          Text(
            'Tạo tài khoản, trả lời vài câu hỏi và vuốt thử 30 món. Phần '
            'còn lại để hệ thống lo.',
            style: text.bodyLarge,
          ),
          const Spacer(),
          for (final p in _points)
            Padding(
              padding: const EdgeInsets.only(bottom: 18),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: AppColors.accentSoft,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(p.icon, size: 20, color: AppColors.accentInk),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(p.title, style: text.titleMedium),
                        const SizedBox(height: 2),
                        Text(p.body, style: text.bodyMedium),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          const Spacer(flex: 2),
          FilledButton(
            onPressed: () => _enter(context, AuthMode.register),
            child: const Text('Đăng ký'),
          ),
          const SizedBox(height: 10),
          OutlinedButton(
            onPressed: () => _enter(context, AuthMode.login),
            child: const Text('Đăng nhập'),
          ),
        ],
      ),
    );
  }
}
