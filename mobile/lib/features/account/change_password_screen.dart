import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/app_card.dart';
import '../../data/api/failure.dart';
import '../../data/session.dart';
import '../auth/auth_screen.dart';
import '../auth/welcome_screen.dart';

/// Change the password of the signed-in account — `PUT /auth/password`.
///
/// The current password is asked for even though the user is signed in —
/// §7.1.7: a phone that is signed in can be in somebody else's hand.
///
/// Online, success ends every session, this one included, so the screen
/// leaves for the welcome screen and the user logs in with the new password.
/// The profile, plans and diary stay with the account.
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _form = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();

  bool _busy = false;

  /// What the server said about each field, shown under that field until
  /// the next attempt.
  String? _currentError;
  String? _nextError;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _currentError = null;
      _nextError = null;
    });
    if (!_form.currentState!.validate()) return;

    final session = SessionScope.of(context);
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);

    setState(() => _busy = true);
    final bool signedOut;
    try {
      signedOut = await session.changePassword(
        current: _current.text,
        next: _next.text,
      );
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        if (failure.code == ApiFailure.invalidCredentials) {
          _currentError = failure.message;
        }
        _nextError = failure.forField('newPassword');
      });
      if (_currentError == null && _nextError == null) {
        messenger.showSnackBar(
          SnackBar(
            content: Text(failure.message),
            duration: const Duration(seconds: 4),
          ),
        );
      }
      _form.currentState!.validate();
      return;
    }

    if (signedOut) {
      navigator.pushAndRemoveUntil(
        fadeRoute<void>(const WelcomeScreen()),
        (_) => false,
      );
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Đã đổi mật khẩu. Hãy đăng nhập lại.'),
          duration: Duration(seconds: 3),
        ),
      );
      return;
    }

    messenger.showSnackBar(
      const SnackBar(
        content: Text('Đã đổi mật khẩu'),
        duration: Duration(seconds: 2),
      ),
    );
    navigator.pop();
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
              Text('Đổi mật khẩu', style: text.displaySmall),
              const SizedBox(height: 10),
              Text(
                'Đổi xong, mọi máy đang đăng nhập tài khoản này, kể cả máy '
                'này, sẽ phải đăng nhập lại bằng mật khẩu mới.',
                style: text.bodyLarge,
              ),
              const SizedBox(height: 28),
              AuthField(
                controller: _current,
                label: 'Mật khẩu hiện tại',
                icon: Icons.lock_outline_rounded,
                obscure: true,
                validator: (v) => (v ?? '').isEmpty
                    ? 'Nhập mật khẩu hiện tại'
                    : _currentError,
              ),
              const SizedBox(height: 14),
              AuthField(
                controller: _next,
                label: 'Mật khẩu mới (từ 8 ký tự)',
                icon: Icons.lock_reset_rounded,
                obscure: true,
                validator: (v) =>
                    AuthRules.password(v) ??
                    (v == _current.text
                        ? 'Mật khẩu mới phải khác mật khẩu hiện tại'
                        : _nextError),
                onSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: Text(_busy ? 'Đang lưu…' : 'Lưu mật khẩu mới'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
