import 'package:flutter/material.dart';

import 'core/app_scroll_behavior.dart';
import 'core/device_frame.dart';
import 'core/theme/app_theme.dart';
import 'data/session.dart';
import 'features/auth/welcome_screen.dart';

void main() {
  runApp(const NutritionApp());
}

class NutritionApp extends StatefulWidget {
  const NutritionApp({super.key});

  @override
  State<NutritionApp> createState() => _NutritionAppState();
}

class _NutritionAppState extends State<NutritionApp> {
  /// One single session for the app's whole lifetime. Held here rather
  /// than in `main()` so that `dispose` is called at the right moment.
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
        // Wrapped at `builder` rather than around `home`, so every
        // screen pushed onto the Navigator later is inside the frame too.
        builder: (context, child) => DeviceFrame(child: child!),
        home: const WelcomeScreen(),
      ),
    );
  }
}
