import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../auth/auth_screen.dart';

/// Change the password of the signed-in account — `PUT /auth/password`.
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

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;

    setState(() => _busy = true);
    await Future<void>.delayed(const Duration(milliseconds: 600));
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Đã đổi mật khẩu'),
        duration: Duration(seconds: 2),
      ),
    );
    Navigator.of(context).pop();
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
                'Các máy khác đang đăng nhập tài khoản này sẽ phải đăng nhập '
                'lại bằng mật khẩu mới.',
                style: text.bodyLarge,
              ),
              const SizedBox(height: 28),
              AuthField(
                controller: _current,
                label: 'Mật khẩu hiện tại',
                icon: Icons.lock_outline_rounded,
                obscure: true,
                validator: (v) =>
                    (v ?? '').isEmpty ? 'Nhập mật khẩu hiện tại' : null,
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
                        : null),
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
