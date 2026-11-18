import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Asks before an action that cannot be taken back. Resolves to `true` only
/// when the user picked [action].
Future<bool> confirmDestructive(
  BuildContext context, {
  required String title,
  required String body,
  required String action,
}) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      title: Text(title),
      content: Text(body),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Thôi'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(true),
          style: TextButton.styleFrom(foregroundColor: AppColors.dislike),
          child: Text(action),
        ),
      ],
    ),
  );
  return ok ?? false;
}
