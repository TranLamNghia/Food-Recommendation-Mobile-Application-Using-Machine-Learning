import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../diary/diary_screen.dart';
import '../plan/daily_plan_screen.dart';
import '../progress/progress_screen.dart';

/// Khung chính sau khi hoàn tất khai báo hồ sơ và phiên khảo sát khẩu vị.
///
/// Ba tab phản ánh đúng vòng lặp phản hồi của hệ thống: nhận **thực đơn**,
/// ghi lại những gì đã ăn vào **nhật ký**, rồi xem **tiến trình** thay đổi
/// theo thời gian. Dữ liệu từ hai tab sau quay lại nuôi tab đầu.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _tabs = [
    (icon: Icons.restaurant_menu_rounded, label: 'Thực đơn'),
    (icon: Icons.menu_book_rounded, label: 'Nhật ký'),
    (icon: Icons.insights_rounded, label: 'Tiến trình'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: const [DailyPlanScreen(), DiaryScreen(), ProgressScreen()],
      ),
      bottomNavigationBar: _BottomBar(
        index: _index,
        onChanged: (i) => setState(() => _index = i),
        tabs: _tabs,
      ),
    );
  }
}

/// Thanh điều hướng đáy.
///
/// Tự vẽ thay vì dùng [NavigationBar] của Material 3 vì thanh mặc định cao
/// 80 và chèn một viên nền bo tròn sau biểu tượng đang chọn — cả hai đều
/// lệch khỏi ngôn ngữ thiết kế trắng–đen–lơ của ứng dụng.
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
