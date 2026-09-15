import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_colors.dart';

/// Bánh xe chọn một con số.
///
/// Dùng cho chiều cao, cân nặng và năm sinh. So với ô nhập bàn phím, bánh xe
/// có ba cái lợi ở đúng ngữ cảnh này: không bật bàn phím che nửa màn hình,
/// không nhập được giá trị vô lý, và cuộn nhanh hơn gõ khi giá trị mặc định
/// đã gần đúng.
///
/// Mỗi nấc cuộn qua đều rung nhẹ — người dùng đếm được số nấc mà không cần
/// nhìn, giống cảm giác vặn núm cơ khí.
class ValueWheel extends StatefulWidget {
  const ValueWheel({
    super.key,
    required this.min,
    required this.max,
    required this.value,
    required this.onChanged,
    required this.unit,
    this.fractionDigits = 0,
    this.step = 1,
  });

  final double min;
  final double max;
  final double value;
  final ValueChanged<double> onChanged;

  /// Đơn vị hiện cạnh con số, ví dụ `kg` hoặc `cm`.
  final String unit;

  final int fractionDigits;
  final double step;

  @override
  State<ValueWheel> createState() => _ValueWheelState();
}

class _ValueWheelState extends State<ValueWheel> {
  static const _itemExtent = 64.0;

  late final FixedExtentScrollController _controller;
  late int _index;

  int get _count => ((widget.max - widget.min) / widget.step).round() + 1;

  double _valueAt(int i) => widget.min + i * widget.step;

  @override
  void initState() {
    super.initState();
    _index = ((widget.value - widget.min) / widget.step).round().clamp(
      0,
      _count - 1,
    );
    _controller = FixedExtentScrollController(initialItem: _index);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onSelected(int i) {
    if (i == _index) return;
    setState(() => _index = i);
    HapticFeedback.selectionClick();
    widget.onChanged(_valueAt(i));
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: _itemExtent * 5,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Ô sáng đánh dấu giá trị đang chọn, đứng yên trong khi số chạy qua.
          Container(
            height: _itemExtent,
            margin: const EdgeInsets.symmetric(horizontal: 24),
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(18),
            ),
          ),
          ListWheelScrollView.useDelegate(
            controller: _controller,
            itemExtent: _itemExtent,
            physics: const FixedExtentScrollPhysics(),
            // Nghiêng nhẹ theo hình trụ, đủ để thấy chiều sâu mà chữ chưa méo.
            diameterRatio: 2.2,
            perspective: 0.003,
            onSelectedItemChanged: _onSelected,
            childDelegate: ListWheelChildBuilderDelegate(
              childCount: _count,
              builder: (context, i) => _WheelItem(
                text: _valueAt(i).toStringAsFixed(widget.fractionDigits),
                unit: widget.unit,
                selected: i == _index,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WheelItem extends StatelessWidget {
  const _WheelItem({
    required this.text,
    required this.unit,
    required this.selected,
  });

  final String text;
  final String unit;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          Text(
            text,
            style: TextStyle(
              fontFamily: 'Afacad',
              fontVariations: [FontVariation('wght', selected ? 700 : 500)],
              fontSize: selected ? 38 : 30,
              height: 1,
              color: selected
                  ? AppColors.textPrimary
                  : AppColors.textTertiary.withValues(alpha: 0.75),
            ),
          ),
          if (selected) ...[
            const SizedBox(width: 8),
            Text(
              unit,
              style: const TextStyle(
                fontFamily: 'Afacad',
                fontVariations: [FontVariation('wght', 600)],
                fontSize: 17,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
