import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../data/session.dart';
import 'forgot_password_screen.dart';

enum AuthMode { login, register }

/// Field rules shared by every auth form. They mirror the constraints in
/// `API_SPECIFICATION.md` §7.1 so the form rejects what the server would.
abstract final class AuthRules {
  static final _email = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  static String? email(String? v) {
    final s = v?.trim() ?? '';
    if (s.isEmpty) return 'Nhập email của bạn';
    final valid = s.length <= 255 && _email.hasMatch(s);
    return valid ? null : 'Email chưa đúng định dạng';
  }

  static String? password(String? v) {
    final s = v ?? '';
    if (s.length < 8) return 'Mật khẩu cần ít nhất 8 ký tự';
    if (!s.contains(RegExp(r'[A-Za-z]')) || !s.contains(RegExp(r'\d'))) {
      return 'Mật khẩu cần có cả chữ và số';
    }
    return null;
  }

  static String? displayName(String? v) {
    final n = v?.trim().length ?? 0;
    if (n < 2 || n > 100) return 'Tên hiển thị dài từ 2 đến 100 ký tự';
    return null;
  }

  /// Optional: empty passes. Otherwise a Vietnamese mobile number, written
  /// with a leading 0 or +84; spaces are ignored.
  static String? phone(String? v) {
    final s = (v ?? '').replaceAll(' ', '');
    if (s.isEmpty) return null;
    final valid = RegExp(r'^(0|\+84)\d{9}$').hasMatch(s);
    return valid ? null : 'Số điện thoại gồm 10 chữ số, bắt đầu bằng 0';
  }
}

/// Log in or create an account, on one screen with a switch between the two.
///
/// Pops `true` once signed in; the caller decides where to go next.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.mode});

  final AuthMode mode;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();

  late AuthMode _mode = widget.mode;
  bool _busy = false;
  bool _obscure = true;

  bool get _registering => _mode == AuthMode.register;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;

    setState(() => _busy = true);
    // Stands in for the network round trip.
    await Future<void>.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;

    SessionScope.of(
      context,
    ).signIn(email: _email.text, displayName: _registering ? _name.text : null);
    Navigator.of(context).pop(true);
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
              Text(
                _registering ? 'Tạo tài khoản' : 'Mừng bạn quay lại',
                style: text.displaySmall,
              ),
              const SizedBox(height: 10),
              Text(
                _registering
                    ? 'Tài khoản giữ hồ sơ, thực đơn và nhật ký của bạn. Tạo '
                          'xong là tới phần câu hỏi.'
                    : 'Đăng nhập để tiếp tục với hồ sơ và thực đơn đã lưu.',
                style: text.bodyLarge,
              ),
              const SizedBox(height: 28),
              if (_registering) ...[
                AuthField(
                  controller: _name,
                  label: 'Tên hiển thị',
                  icon: Icons.person_outline_rounded,
                  validator: AuthRules.displayName,
                  textCapitalization: TextCapitalization.words,
                ),
                const SizedBox(height: 14),
              ],
              AuthField(
                controller: _email,
                label: 'Email',
                icon: Icons.mail_outline_rounded,
                keyboardType: TextInputType.emailAddress,
                validator: AuthRules.email,
              ),
              const SizedBox(height: 14),
              AuthField(
                controller: _password,
                label: _registering ? 'Mật khẩu (từ 8 ký tự)' : 'Mật khẩu',
                icon: Icons.lock_outline_rounded,
                obscure: _obscure,
                // Logging in only checks that something was typed: the server
                // decides whether it is right, and an old password may predate
                // the current rules.
                validator: _registering
                    ? AuthRules.password
                    : (v) => (v ?? '').isEmpty ? 'Nhập mật khẩu' : null,
                trailing: IconButton(
                  tooltip: _obscure ? 'Hiện mật khẩu' : 'Ẩn mật khẩu',
                  onPressed: () => setState(() => _obscure = !_obscure),
                  icon: Icon(
                    _obscure
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                    size: 20,
                    color: AppColors.textSecondary,
                  ),
                ),
                onSubmitted: (_) => _submit(),
              ),
              if (!_registering)
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) =>
                            ForgotPasswordScreen(initialEmail: _email.text),
                      ),
                    ),
                    child: const Text('Quên mật khẩu?'),
                  ),
                )
              else
                const SizedBox(height: 20),
              const SizedBox(height: 4),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: _busy
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: AppColors.textSecondary,
                        ),
                      )
                    : Text(_registering ? 'Tạo tài khoản' : 'Đăng nhập'),
              ),
              const SizedBox(height: 8),
              Center(
                child: TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _mode = _registering
                              ? AuthMode.login
                              : AuthMode.register;
                          _form.currentState?.reset();
                        }),
                  child: Text(
                    _registering
                        ? 'Đã có tài khoản? Đăng nhập'
                        : 'Chưa có tài khoản? Tạo mới',
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Filled, borderless text field used by the auth forms.
class AuthField extends StatelessWidget {
  const AuthField({
    super.key,
    required this.controller,
    required this.label,
    required this.icon,
    this.validator,
    this.keyboardType,
    this.obscure = false,
    this.trailing,
    this.onSubmitted,
    this.textCapitalization = TextCapitalization.none,
  });

  final TextEditingController controller;
  final String label;
  final IconData icon;
  final FormFieldValidator<String>? validator;
  final TextInputType? keyboardType;
  final bool obscure;
  final Widget? trailing;
  final ValueChanged<String>? onSubmitted;
  final TextCapitalization textCapitalization;

  @override
  Widget build(BuildContext context) {
    OutlineInputBorder border(Color color) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(16),
      borderSide: BorderSide(color: color, width: 1.5),
    );

    return TextFormField(
      controller: controller,
      validator: validator,
      keyboardType: keyboardType,
      obscureText: obscure,
      autocorrect: false,
      textCapitalization: textCapitalization,
      onFieldSubmitted: onSubmitted,
      style: const TextStyle(fontSize: 16, color: AppColors.textPrimary),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: AppColors.textSecondary),
        prefixIcon: Icon(icon, size: 20, color: AppColors.textSecondary),
        suffixIcon: trailing,
        filled: true,
        fillColor: AppColors.background,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 18,
        ),
        enabledBorder: border(Colors.transparent),
        focusedBorder: border(AppColors.ink),
        errorBorder: border(AppColors.dislike),
        focusedErrorBorder: border(AppColors.dislike),
      ),
    );
  }
}
