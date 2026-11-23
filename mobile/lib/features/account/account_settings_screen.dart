import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/app_card.dart';
import '../../core/widgets/confirm_dialog.dart';
import '../../data/api/failure.dart';
import '../../data/session.dart';
import '../auth/auth_screen.dart';
import '../auth/welcome_screen.dart';
import 'change_password_screen.dart';

/// Everything about the account that has nothing to do with health: the
/// display name, the password, signing out and deleting.
///
/// Kept apart from the answers on the "Tôi" tab on purpose. Changing an
/// answer there recalculates the plan; nothing on this screen does.
class AccountSettingsScreen extends StatelessWidget {
  const AccountSettingsScreen({super.key});

  static Future<void> open(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => const AccountSettingsScreen()),
  );

  Future<void> _editName(BuildContext context, AppSession session) async {
    final value = await _EditFieldScreen.open(
      context,
      title: 'Tên hiển thị',
      hint: 'Tên này hiện trong ứng dụng, không dùng để đăng nhập.',
      label: 'Tên hiển thị',
      icon: Icons.person_outline_rounded,
      initial: session.displayName ?? '',
      validator: AuthRules.displayName,
      textCapitalization: TextCapitalization.words,
    );
    if (value == null) return;
    try {
      await session.updateAccount(displayName: value);
    } on ApiFailure catch (failure) {
      if (!context.mounted) return;
      // The server refused the new name. Say so where the user is rather
      // than leaving the old one on screen with no explanation.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(failure.message)),
      );
    }
  }

  /// Leaves the main shell for the welcome screen, then runs [leave]. In that
  /// order so no screen rebuilds on top of an account that is already gone.
  void _leave(BuildContext context, VoidCallback leave) {
    Navigator.of(
      context,
    ).pushAndRemoveUntil(fadeRoute<void>(const WelcomeScreen()), (_) => false);
    leave();
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final name = session.displayName;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Tài khoản'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            AppCard(
              title: 'Thông tin cá nhân',
              padding: const EdgeInsets.fromLTRB(20, 18, 14, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AppRow(
                    icon: Icons.person_outline_rounded,
                    label: 'Tên hiển thị',
                    value: (name == null || name.isEmpty) ? 'Chưa đặt' : name,
                    onTap: () => _editName(context, session),
                  ),
                  // Not tappable, so it has no chevron; the inset stands in
                  // for one and keeps the three values on the same edge.
                  Padding(
                    padding: const EdgeInsets.only(right: 24),
                    child: AppRow(
                      icon: Icons.mail_outline_rounded,
                      label: 'Email',
                      value: session.accountEmail ?? '',
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(left: 32, right: 6),
                    child: Text(
                      'Email dùng để đăng nhập nên không đổi được ở đây.',
                      style: TextStyle(
                        fontSize: 12.5,
                        height: 1.4,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppCard(
              title: 'Bảo mật',
              padding: const EdgeInsets.fromLTRB(20, 18, 14, 10),
              child: AppRow(
                icon: Icons.lock_outline_rounded,
                label: 'Đổi mật khẩu',
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const ChangePasswordScreen(),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),
            AppCard(
              padding: const EdgeInsets.fromLTRB(20, 8, 14, 8),
              child: Column(
                children: [
                  AppRow(
                    icon: Icons.logout_rounded,
                    label: 'Đăng xuất',
                    onTap: () async {
                      final ok = await confirmDestructive(
                        context,
                        title: 'Đăng xuất?',
                        body:
                            'Hồ sơ, thực đơn và nhật ký vẫn nằm trong tài '
                            'khoản, bạn đăng nhập lại là thấy.',
                        action: 'Đăng xuất',
                      );
                      if (ok && context.mounted) {
                        _leave(context, session.signOut);
                      }
                    },
                  ),
                  AppRow(
                    icon: Icons.delete_outline_rounded,
                    label: 'Xóa tài khoản',
                    destructive: true,
                    onTap: () async {
                      final ok = await confirmDestructive(
                        context,
                        title: 'Xóa tài khoản?',
                        body:
                            'Tài khoản cùng toàn bộ hồ sơ, khẩu vị đã học, '
                            'thực đơn và nhật ký sẽ bị xóa. Không hoàn tác '
                            'được.',
                        action: 'Xóa tài khoản',
                      );
                      if (ok && context.mounted) {
                        _leave(context, session.deleteAccount);
                      }
                    },
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

/// One text field on its own screen. Pops the trimmed value on save, `null`
/// when the user backs out.
class _EditFieldScreen extends StatefulWidget {
  const _EditFieldScreen({
    required this.title,
    required this.hint,
    required this.label,
    required this.icon,
    required this.initial,
    required this.validator,
    this.keyboardType,
    this.textCapitalization = TextCapitalization.none,
  });

  final String title;
  final String hint;
  final String label;
  final IconData icon;
  final String initial;
  final FormFieldValidator<String> validator;
  final TextInputType? keyboardType;
  final TextCapitalization textCapitalization;

  static Future<String?> open(
    BuildContext context, {
    required String title,
    required String hint,
    required String label,
    required IconData icon,
    required String initial,
    required FormFieldValidator<String> validator,
    TextInputType? keyboardType,
    TextCapitalization textCapitalization = TextCapitalization.none,
  }) => Navigator.of(context).push<String>(
    MaterialPageRoute(
      builder: (_) => _EditFieldScreen(
        title: title,
        hint: hint,
        label: label,
        icon: icon,
        initial: initial,
        validator: validator,
        keyboardType: keyboardType,
        textCapitalization: textCapitalization,
      ),
    ),
  );

  @override
  State<_EditFieldScreen> createState() => _EditFieldScreenState();
}

class _EditFieldScreenState extends State<_EditFieldScreen> {
  final _form = GlobalKey<FormState>();
  late final _controller = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _save() {
    if (!_form.currentState!.validate()) return;
    Navigator.of(context).pop(_controller.text.trim());
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            children: [
              Text(widget.title, style: text.displaySmall),
              const SizedBox(height: 10),
              Text(widget.hint, style: text.bodyLarge),
              const SizedBox(height: 28),
              AuthField(
                controller: _controller,
                label: widget.label,
                icon: widget.icon,
                validator: widget.validator,
                keyboardType: widget.keyboardType,
                textCapitalization: widget.textCapitalization,
                onSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 24),
              FilledButton(onPressed: _save, child: const Text('Lưu')),
            ],
          ),
        ),
      ),
    );
  }
}
