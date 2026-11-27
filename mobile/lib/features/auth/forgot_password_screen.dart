import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/session.dart';
import 'auth_screen.dart';
import 'reset_password_screen.dart';

/// Asks for the account email and mails a reset code to it — §7.1.5.
///
/// The confirmation is worded the same whether or not the email exists —
/// `POST /auth/forgot-password` always answers `202` so the form cannot be
/// used to find out who has an account.
///
/// The mail carries a **code**, not a link: the app registers no deep link,
/// so a link would open a browser on nothing. The code is pasted into
/// [ResetPasswordScreen], which this screen leads on to.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key, this.initialEmail = ''});

  final String initialEmail;

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _form = GlobalKey<FormState>();
  late final _email = TextEditingController(text: widget.initialEmail);

  bool _busy = false;
  bool _sent = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (!_form.currentState!.validate()) return;

    setState(() => _busy = true);
    try {
      await SessionScope.of(context).requestPasswordReset(_email.text.trim());
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 4),
        ),
      );
      return;
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _sent = true;
    });
  }

  /// Opens the code screen. When it reports the password changed, this
  /// screen closes too, so the user lands back on the login form.
  Future<void> _enterCode() async {
    final done = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => ResetPasswordScreen(email: _email.text.trim()),
      ),
    );
    if (done == true && mounted) Navigator.of(context).pop();
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
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
          child: _sent
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Icon(
                        Icons.mark_email_read_outlined,
                        size: 44,
                        color: AppColors.accentInk,
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text('Kiểm tra hộp thư', style: text.displaySmall),
                    const SizedBox(height: 10),
                    Text(
                      'Nếu ${_email.text.trim()} đã đăng ký, một mã đặt lại '
                      'mật khẩu vừa được gửi tới đó. Mã dùng được một lần và '
                      'hết hạn sau 15 phút.',
                      style: text.bodyLarge,
                    ),
                    const Spacer(),
                    FilledButton(
                      onPressed: _enterCode,
                      child: const Text('Nhập mã đặt lại'),
                    ),
                    const SizedBox(height: 4),
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Quay lại đăng nhập'),
                    ),
                  ],
                )
              : Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text('Quên mật khẩu?', style: text.displaySmall),
                      const SizedBox(height: 10),
                      Text(
                        'Nhập email của tài khoản, chúng tôi sẽ gửi một mã để '
                        'bạn đặt mật khẩu mới.',
                        style: text.bodyLarge,
                      ),
                      const SizedBox(height: 28),
                      AuthField(
                        controller: _email,
                        label: 'Email',
                        icon: Icons.mail_outline_rounded,
                        keyboardType: TextInputType.emailAddress,
                        validator: AuthRules.email,
                        onSubmitted: (_) => _send(),
                      ),
                      const Spacer(),
                      FilledButton(
                        onPressed: _busy ? null : _send,
                        child: Text(_busy ? 'Đang gửi…' : 'Gửi mã'),
                      ),
                      const SizedBox(height: 4),
                      // For someone coming back with a mail already open.
                      TextButton(
                        onPressed: _enterCode,
                        child: const Text('Tôi đã có mã'),
                      ),
                    ],
                  ),
                ),
        ),
      ),
    );
  }
}
