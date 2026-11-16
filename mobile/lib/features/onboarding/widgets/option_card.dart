import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// An option card in the profile flow.
///
/// Unselected is a white card face on a pale grey background; selected
/// inverts completely to a black block with white text. The inversion is
/// that strong so a glance is enough to see what has been chosen, even when
/// the list is long and several items can be selected.
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

  /// The small secondary line under the label.
  final String? hint;

  /// The icon at the head of the card, usually an emoji.
  final String? leading;

  /// The value shown at the end of the card, such as the matching
  /// energy level.
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
                  // Centre only when the card is bare on both sides. With
                  // an icon at the head, centred text looks plainly
                  // misaligned, because the eye takes the icon as the left
                  // margin.
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
                    color: AppColors.accentInk,
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

/// A list of option cards, appearing from below one after another.
class OptionList extends StatelessWidget {
  const OptionList({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(
      // The list is exactly as tall as the cards in it, taking no spare
      // room.
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
    // Each card enters one beat later than the one above, so the list
    // feels like it unrolls rather than popping up all at once.
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
