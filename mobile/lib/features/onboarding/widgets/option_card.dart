import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// Thẻ lựa chọn trong luồng khai báo hồ sơ.
///
/// Trạng thái chưa chọn là mặt thẻ trắng trên nền xám nhạt; đã chọn thì đảo
/// hẳn sang khối đen chữ trắng. Đảo màu mạnh như vậy để nhìn lướt qua là biết
/// mình đã chọn gì, kể cả khi danh sách dài và chọn được nhiều mục.
class OptionCard extends StatefulWidget {
  const OptionCard({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.hint,
    this.leading,
    this.trailing,
  });

  final String label;

  /// Dòng phụ nhỏ bên dưới nhãn.
  final String? hint;

  /// Biểu tượng đầu thẻ, thường là emoji.
  final String? leading;

  /// Giá trị hiện ở cuối thẻ, ví dụ mức tăng cân dự kiến.
  final String? trailing;

  final bool selected;
  final VoidCallback onTap;

  @override
  State<OptionCard> createState() => _OptionCardState();
}

class _OptionCardState extends State<OptionCard> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final selected = widget.selected;
    final fg = selected ? AppColors.textOnDark : AppColors.textPrimary;
    final hintColor = selected
        ? AppColors.textOnDark.withValues(alpha: 0.6)
        : AppColors.textSecondary;

    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      onTap: () {
        HapticFeedback.selectionClick();
        widget.onTap();
      },
      child: AnimatedScale(
        scale: _pressed ? 0.975 : 1,
        duration: AppMotion.instant,
        curve: AppMotion.standard,
        child: AnimatedContainer(
          duration: AppMotion.quick,
          curve: AppMotion.standard,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
          decoration: BoxDecoration(
            color: selected ? AppColors.ink : AppColors.surface,
            borderRadius: BorderRadius.circular(18),
            boxShadow: [
              BoxShadow(
                color: selected
                    ? AppColors.ink.withValues(alpha: 0.18)
                    : AppColors.shadowSoft,
                blurRadius: selected ? 18 : 10,
                offset: Offset(0, selected ? 8 : 4),
              ),
            ],
          ),
          child: Row(
            children: [
              if (widget.leading != null) ...[
                Text(widget.leading!, style: const TextStyle(fontSize: 22)),
                const SizedBox(width: 14),
              ],
              Expanded(
                child: Column(
                  // Chỉ căn giữa khi thẻ trống trơn hai bên. Có biểu tượng ở
                  // đầu mà chữ vẫn căn giữa thì nhìn lệch hẳn, vì mắt lấy
                  // biểu tượng làm mốc lề trái.
                  crossAxisAlignment:
                      widget.leading == null && widget.hint == null
                      ? CrossAxisAlignment.center
                      : CrossAxisAlignment.start,
                  children: [
                    AnimatedDefaultTextStyle(
                      duration: AppMotion.quick,
                      style: TextStyle(
                        fontFamily: 'Afacad',
                        fontVariations: const [FontVariation('wght', 600)],
                        fontSize: 17,
                        height: 1.3,
                        color: fg,
                      ),
                      child: Text(widget.label),
                    ),
                    if (widget.hint != null) ...[
                      const SizedBox(height: 2),
                      AnimatedDefaultTextStyle(
                        duration: AppMotion.quick,
                        style: TextStyle(
                          fontFamily: 'Afacad',
                          fontVariations: const [FontVariation('wght', 400)],
                          fontSize: 14,
                          height: 1.3,
                          color: hintColor,
                        ),
                        child: Text(widget.hint!),
                      ),
                    ],
                  ],
                ),
              ),
              if (widget.trailing != null) ...[
                const SizedBox(width: 12),
                Text(
                  widget.trailing!,
                  style: const TextStyle(
                    fontFamily: 'Afacad',
                    fontVariations: [FontVariation('wght', 700)],
                    fontSize: 17,
                    color: AppColors.accent,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Danh sách thẻ lựa chọn, xuất hiện lệch pha nhau từ dưới lên.
class OptionList extends StatelessWidget {
  const OptionList({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      // Danh sách chỉ cao bằng đúng số thẻ trong nó, không chiếm chỗ thừa.
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < children.length; i++)
          Padding(
            padding: EdgeInsets.only(bottom: i == children.length - 1 ? 0 : 12),
            child: _Appear(delay: i * 55, child: children[i]),
          ),
      ],
    );
  }
}

class _Appear extends StatefulWidget {
  const _Appear({required this.delay, required this.child});

  final int delay;
  final Widget child;

  @override
  State<_Appear> createState() => _AppearState();
}

class _AppearState extends State<_Appear> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: AppMotion.page);
    // Mỗi thẻ vào chậm hơn thẻ trên một nhịp, tạo cảm giác danh sách trải ra
    // thay vì bật lên cùng lúc.
    Future.delayed(Duration(milliseconds: widget.delay), () {
      if (mounted) _ctrl.forward();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curved = CurvedAnimation(parent: _ctrl, curve: AppMotion.emphasized);
    return AnimatedBuilder(
      animation: curved,
      builder: (context, child) => Opacity(
        opacity: curved.value,
        child: Transform.translate(
          offset: Offset(0, 18 * (1 - curved.value)),
          child: child,
        ),
      ),
      child: widget.child,
    );
  }
}
