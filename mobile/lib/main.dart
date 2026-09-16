import 'package:flutter/material.dart';

import 'core/app_scroll_behavior.dart';
import 'core/device_frame.dart';
import 'core/theme/app_theme.dart';
import 'data/session.dart';
import 'features/onboarding/onboarding_flow.dart';

void main() {
  runApp(const NutritionApp());
}

class NutritionApp extends StatefulWidget {
  const NutritionApp({super.key});

  @override
  State<NutritionApp> createState() => _NutritionAppState();
}

class _NutritionAppState extends State<NutritionApp> {
  /// Một phiên duy nhất cho cả vòng đời ứng dụng. Giữ ở đây thay vì trong
  /// `main()` để `dispose` được gọi đúng lúc.
  final _session = AppSession();

  @override
  void dispose() {
    _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SessionScope(
      session: _session,
      child: MaterialApp(
        title: 'Thực đơn của tôi',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        scrollBehavior: const AppScrollBehavior(),
        // Bọc ở `builder` chứ không bọc `home`, để mọi màn hình đẩy vào
        // Navigator sau này đều nằm trong khung.
        builder: (context, child) => DeviceFrame(child: child!),
        home: const OnboardingFlow(),
      ),
    );
  }
}
