import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import 'auth_screen.dart';

/// Asks for the account email and reports that reset instructions were sent.
///
/// The confirmation is worded the same whether or not the email exists —
/// `POST /auth/forgot-password` always answers `202` so the form cannot be
/// used to find out who has an account.
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
    await Future<void>.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;
    setState(() {
      _busy = false;
      _sent = true;
    });
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
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.mark_email_read_outlined,
                      size: 44,
                      color: AppColors.accentInk,
                    ),
                    const SizedBox(height: 20),
                    Text('Kiểm tra hộp thư', style: text.displaySmall),
                    const SizedBox(height: 10),
                    Text(
                      'Nếu ${_email.text.trim()} đã đăng ký, hướng dẫn đặt lại '
                      'mật khẩu đã được gửi tới đó. Liên kết chỉ dùng được '
                      'một lần.',
                      style: text.bodyLarge,
                    ),
                    const Spacer(),
                    FilledButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Quay lại đăng nhập'),
                    ),
                  ],
                )
              : Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Quên mật khẩu?', style: text.displaySmall),
                      const SizedBox(height: 10),
                      Text(
                        'Nhập email của tài khoản, chúng tôi sẽ gửi liên kết '
                        'để bạn đặt mật khẩu mới.',
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
                        child: Text(_busy ? 'Đang gửi…' : 'Gửi liên kết'),
                      ),
                    ],
                  ),
                ),
        ),
      ),
    );
  }
}
