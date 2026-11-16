import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../account/account_screen.dart';
import '../diary/diary_screen.dart';
import '../plan/daily_plan_screen.dart';
import '../progress/progress_screen.dart';
import '../shopping/shopping_screen.dart';

/// The main shell, once the profile and the taste survey are done.
///
/// The first three tabs mirror the system's feedback loop exactly: receive
/// the **plan**, record what was eaten in the **diary**, then watch the
/// **progress** change over time. The data from the latter two flows back to
/// feed the first.
///
/// Two more sit around that loop: **Đi chợ** turns the plan into what to buy,
/// and **Tôi** holds the answers the plan is built from.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _tabs = [
    (icon: Icons.restaurant_menu_rounded, label: 'Thực đơn'),
    (icon: Icons.shopping_basket_outlined, label: 'Đi chợ'),
    (icon: Icons.menu_book_rounded, label: 'Nhật ký'),
    (icon: Icons.insights_rounded, label: 'Tiến trình'),
    (icon: Icons.person_outline_rounded, label: 'Tôi'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: const [
          DailyPlanScreen(),
          ShoppingScreen(),
          DiaryScreen(),
          ProgressScreen(),
          AccountScreen(),
        ],
      ),
      bottomNavigationBar: _BottomBar(
        index: _index,
        onChanged: (i) => setState(() => _index = i),
        tabs: _tabs,
      ),
    );
  }
}

/// The bottom navigation bar.
///
/// Drawn by hand rather than using Material 3's [NavigationBar], because the
/// default bar is 80 tall and puts a rounded pill behind the selected icon —
/// both of which depart from the app's white–black–cyan design language.
class _BottomBar extends StatelessWidget {
  const _BottomBar({
    required this.index,
    required this.onChanged,
    required this.tabs,
  });

  final int index;
  final ValueChanged<int> onChanged;
  final List<({IconData icon, String label})> tabs;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 64,
          child: Row(
            children: [
              for (var i = 0; i < tabs.length; i++)
                Expanded(
                  child: _BarItem(
                    icon: tabs[i].icon,
                    label: tabs[i].label,
                    selected: i == index,
                    onTap: () => onChanged(i),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BarItem extends StatelessWidget {
  const _BarItem({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.ink : AppColors.textTertiary;

    return InkWell(
      onTap: onTap,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AnimatedScale(
            scale: selected ? 1.0 : 0.92,
            duration: AppMotion.quick,
            curve: AppMotion.standard,
            child: Icon(icon, size: 24, color: color),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11.5,
              height: 1.1,
              color: color,
              fontVariations: [FontVariation('wght', selected ? 700 : 500)],
            ),
          ),
        ],
      ),
    );
  }
}
