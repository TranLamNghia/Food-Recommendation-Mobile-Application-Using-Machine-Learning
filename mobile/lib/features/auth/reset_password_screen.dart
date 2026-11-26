import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/session.dart';
import 'auth_screen.dart';

/// Sets a new password with the code from the reset mail — §7.1.6.
///
/// Pops `true` once the password is changed. The server has then ended
/// every session of the account, so the caller goes back to the login form
/// rather than into the app.
class ResetPasswordScreen extends StatefulWidget {
  const ResetPasswordScreen({super.key, this.email = ''});

  /// The address the code was sent to, only to say so on screen.
  final String email;

  @override
  State<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends State<ResetPasswordScreen> {
  final _form = GlobalKey<FormState>();
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _again = TextEditingController();

  bool _busy = false;

  /// The server's verdict on the code, shown under its field until the next
  /// attempt, or until a code is pasted.
  String? _codeError;

  @override
  void dispose() {
    _code.dispose();
    _password.dispose();
    _again.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim() ?? '';
    if (text.isEmpty) return;
    _code.text = text;
    setState(() => _codeError = null);
  }

  Future<void> _save() async {
    setState(() => _codeError = null);
    if (!_form.currentState!.validate()) return;

    final messenger = ScaffoldMessenger.of(context);
    setState(() => _busy = true);
    try {
      await SessionScope.of(context)
          .resetPassword(code: _code.text.trim(), newPassword: _password.text);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        // A bad code belongs under the code; anything else is a snackbar.
        if (failure.code == ApiFailure.resetTokenInvalid) {
          _codeError = failure.message;
        }
      });
      if (failure.code != ApiFailure.resetTokenInvalid) {
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
    if (!mounted) return;
    messenger.showSnackBar(
      const SnackBar(
        content: Text('Đã đổi mật khẩu. Hãy đăng nhập bằng mật khẩu mới.'),
        duration: Duration(seconds: 3),
      ),
    );
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final to = widget.email.isEmpty ? 'email của bạn' : widget.email;

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
              Text('Đặt mật khẩu mới', style: text.displaySmall),
              const SizedBox(height: 10),
              Text(
                'Dán mã trong thư vừa gửi tới $to, rồi chọn mật khẩu mới. '
                'Mọi máy đang đăng nhập tài khoản này sẽ phải đăng nhập lại.',
                style: text.bodyLarge,
              ),
              const SizedBox(height: 28),
              AuthField(
                controller: _code,
                label: 'Mã đặt lại',
                icon: Icons.key_rounded,
                validator: (v) => (v ?? '').trim().isEmpty
                    ? 'Dán mã trong thư vào đây'
                    : _codeError,
                trailing: IconButton(
                  onPressed: _paste,
                  tooltip: 'Dán mã',
                  icon: const Icon(Icons.content_paste_rounded, size: 20),
                ),
              ),
              const SizedBox(height: 14),
              AuthField(
                controller: _password,
                label: 'Mật khẩu mới (từ 8 ký tự)',
                icon: Icons.lock_reset_rounded,
                obscure: true,
                validator: AuthRules.password,
              ),
              const SizedBox(height: 14),
              AuthField(
                controller: _again,
                label: 'Nhập lại mật khẩu mới',
                icon: Icons.lock_outline_rounded,
                obscure: true,
                // Asked twice because nothing else will catch a typo here:
                // there is no old password to fall back on, and the next
                // attempt costs another mail.
                validator: (v) =>
                    v == _password.text ? null : 'Hai mật khẩu chưa khớp',
                onSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: Text(_busy ? 'Đang lưu…' : 'Đổi mật khẩu'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
