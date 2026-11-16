import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/app_card.dart';
import '../../data/session.dart';
import '../home/home_shell.dart';
import '../onboarding/onboarding_flow.dart';
import 'auth_screen.dart';

/// First screen of the app: says what it does, then offers the two ways in.
///
/// A new user goes straight into the profile questions **without** an
/// account — the account is offered later from the "Tôi" tab — so nobody has
/// to hand over an email before seeing a single dish.
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

  Future<void> _logIn(BuildContext context) async {
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => const AuthScreen(mode: AuthMode.login)),
    );
    if (ok != true || !context.mounted) return;

    // With the real API this is `GET /profile`: an account that already has
    // one skips the questions. The mock keeps nothing between launches, so
    // only a profile filled in earlier this session can be picked up.
    final hasPlan = SessionScope.of(context).todayPlan != null;
    Navigator.of(context).pushReplacement(
      fadeRoute(hasPlan ? const HomeShell() : const OnboardingFlow()),
    );
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
            'Trả lời vài câu hỏi và vuốt thử 30 món. Phần còn lại để hệ '
            'thống lo.',
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
            onPressed: () =>
                Navigator.of(context)
                    .pushReplacement(fadeRoute(const OnboardingFlow())),
            child: const Text('Bắt đầu'),
          ),
          const SizedBox(height: 4),
          Center(
            child: TextButton(
              onPressed: () => _logIn(context),
              child: const Text('Đã có tài khoản? Đăng nhập'),
            ),
          ),
        ],
      ),
    );
  }
}
