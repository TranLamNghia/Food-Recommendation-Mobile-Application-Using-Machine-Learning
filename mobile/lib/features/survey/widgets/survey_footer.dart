import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import 'survey_progress.dart';

/// The screen footer — the `Footer_Backgound` layer (2:15) in Figma.
///
/// The background is a vertical gradient 264 tall on an 844 frame:
/// **transparent at the top edge**, thickening down to `#4F4E4E` at the
/// bottom. The transparent top lets the particles of the "Chưa biết" zone
/// (see `SwipeBurst.bottomOverflow`) drift underneath and sink into the grey,
/// rather than being cut off at the top edge. Inside sits the `Introduce`
/// block (1:4) at coordinates 48, 68 and 310 × 100 in size — where the
/// progress bar and the line asking the user to sort the dishes go.
class SurveyFooter extends StatelessWidget {
  const SurveyFooter({super.key, required this.done, required this.total});

  /// The footer's share of the design frame's height.
  static const heightRatio = 264 / 844;

  /// The footer's original size in Figma.
  static const _designSize = Size(390, 264);

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          // Same grey at both ends, only the alpha changes. Over the white
          // scaffold this blends to exactly the old white → grey ramp, so the
          // footer looks unchanged wherever nothing sits behind it. Fading
          // from transparent *white* instead would wash the middle out.
          colors: [
            AppColors.footerBottom.withValues(alpha: 0),
            AppColors.footerBottom,
          ],
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final sx = constraints.maxWidth / _designSize.width;
          final sy = constraints.maxHeight / _designSize.height;

          return Column(
            children: [
              SizedBox(height: 68 * sy),
              SizedBox(
                height: 100 * sy,
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: 48 * sx),
                  child: _Introduce(done: done, total: total),
                ),
              ),
              // The area below the `Introduce` block is left empty, as in
              // the design. This screen is purely gestural: every action is
              // a card swipe.
              Expanded(child: SizedBox(height: bottomInset)),
            ],
          );
        },
      ),
    );
  }
}

/// The `Introduce` block (1:4) — 310 × 100.
///
/// The message line goes on top, the progress bar below. That order is not
/// arbitrary: the gradient background is light at the top and darkens
/// downwards, so the text — which needs the most contrast — has to sit in the
/// light half, while the progress bar reads in either region thanks to its
/// dark track and white fill.
class _Introduce extends StatelessWidget {
  const _Introduce({required this.done, required this.total});

  /// The message. Deliberately written in an everyday voice, because this
  /// is the moment of asking the user to spend two minutes on something
  /// whose benefit is not yet visible.
  static const _note =
      'Quẹo trái quẹo phải giúp tụi mình phân loại món nha — '
      'app học gu bạn từ đây đó 🤙';

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            _note,
            style: TextStyle(
              fontFamily: 'Afacad',
              fontVariations: const [FontVariation('wght', 600)],
              fontSize: 15,
              height: 1.35,
              color: AppColors.textPrimary.withValues(alpha: 0.88),
            ),
          ),
        ),
        SurveyProgress(done: done, total: total),
      ],
    );
  }
}
