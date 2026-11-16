import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_colors.dart';

/// A wheel for picking one number.
///
/// Used for height, weight and year of birth. Against a keyboard field, a
/// wheel has three advantages in exactly this context: it does not raise a
/// keyboard over half the screen, an absurd value cannot be entered, and it
/// is quicker to spin than to type when the default is already close.
///
/// Every notch scrolled past gives a light haptic tick — the user can count
/// the notches without looking, like turning a mechanical knob.
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

  /// The unit shown next to the number, such as `kg` or `cm`.
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
          // The highlight marking the selected value; it stays still
          // while the numbers scroll past.
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
            // A gentle cylindrical tilt, enough to read as depth
            // without distorting the text.
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
