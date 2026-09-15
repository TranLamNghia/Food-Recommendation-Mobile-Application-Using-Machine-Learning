import 'package:flutter/material.dart';

import 'app_colors.dart';

abstract final class AppTheme {
  /// Chữ thường của toàn ứng dụng dùng Afacad — cùng font với phụ đề trên thẻ
  /// món, và có sẵn bộ dấu tiếng Việt.
  static const fontBody = 'Afacad';

  /// Font hiển thị, dành riêng cho tên món trên thẻ.
  static const fontDisplay = 'Display';

  static const _fallback = <String>['Roboto', 'Segoe UI', 'Arial'];

  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.accent,
        primary: AppColors.ink,
        secondary: AppColors.accent,
        surface: AppColors.surface,
        brightness: Brightness.light,
      ),
      scaffoldBackgroundColor: AppColors.background,
    );

    return base.copyWith(
      textTheme: _textTheme(base.textTheme),
      splashFactory: InkSparkle.splashFactory,
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: 1,
        space: 1,
      ),
      // Nút hành động chính: khối đen bo tròn hết cỡ, chiếm trọn bề ngang.
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.ink,
          foregroundColor: AppColors.textOnDark,
          disabledBackgroundColor: AppColors.surfaceMuted,
          disabledForegroundColor: AppColors.textTertiary,
          minimumSize: const Size.fromHeight(60),
          textStyle: const TextStyle(
            fontFamily: fontBody,
            fontSize: 18,
            fontVariations: [FontVariation('wght', 700)],
            fontFamilyFallback: _fallback,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(30),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.textSecondary,
          textStyle: const TextStyle(
            fontFamily: fontBody,
            fontSize: 16,
            fontVariations: [FontVariation('wght', 600)],
            fontFamilyFallback: _fallback,
          ),
        ),
      ),
    );
  }

  static TextTheme _textTheme(TextTheme base) {
    TextStyle style(double size, int weight, {double? height, Color? color}) {
      return TextStyle(
        fontFamily: fontBody,
        fontVariations: [FontVariation('wght', weight.toDouble())],
        fontSize: size,
        height: height,
        color: color ?? AppColors.textPrimary,
        fontFamilyFallback: _fallback,
        letterSpacing: size >= 24 ? -0.3 : 0,
      );
    }

    return base.copyWith(
      // Tiêu đề câu hỏi trong luồng khai báo hồ sơ.
      displaySmall: style(30, 700, height: 1.22),
      headlineMedium: style(26, 700, height: 1.25),
      headlineSmall: style(22, 700, height: 1.3),
      titleLarge: style(19, 700, height: 1.3),
      titleMedium: style(17, 600, height: 1.35),
      bodyLarge: style(16, 400, height: 1.45, color: AppColors.textSecondary),
      bodyMedium: style(15, 400, height: 1.45, color: AppColors.textSecondary),
      labelLarge: style(15, 600, height: 1.2),
      labelMedium: style(
        13.5,
        600,
        height: 1.2,
        color: AppColors.textSecondary,
      ),
      labelSmall: style(12.5, 600, height: 1.2, color: AppColors.textTertiary),
    );
  }
}
