import 'package:flutter/material.dart';

import 'core/app_scroll_behavior.dart';
import 'core/device_frame.dart';
import 'core/theme/app_theme.dart';
import 'features/onboarding/onboarding_flow.dart';

void main() {
  runApp(const NutritionApp());
}

class NutritionApp extends StatelessWidget {
  const NutritionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Thực đơn của tôi',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      scrollBehavior: const AppScrollBehavior(),
      // Bọc ở `builder` chứ không bọc `home`, để mọi màn hình đẩy vào
      // Navigator sau này đều nằm trong khung.
      builder: (context, child) => DeviceFrame(child: child!),
      home: const OnboardingFlow(),
    );
  }
}
