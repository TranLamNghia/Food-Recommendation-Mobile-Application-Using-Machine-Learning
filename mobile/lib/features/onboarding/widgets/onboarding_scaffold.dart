import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// Marks the steps below it as being re-opened from the account tab to change
/// one answer, instead of running inside the first-time flow.
///
/// [OnboardingScaffold] reads it to drop the progress bar and relabel the
/// action, so the nine step widgets are reused untouched.
class OnboardingEditScope extends InheritedWidget {
  const OnboardingEditScope({super.key, required super.child});

  static bool of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<OnboardingEditScope>() != null;

  @override
  bool updateShouldNotify(OnboardingEditScope oldWidget) => false;
}

/// The shared frame for every profile step.
///
/// A fixed layout means the user does not have to learn each screen anew: the
/// back button and the progress bar on top, the big question, the explanatory
/// line, the input in the middle, and one full-width action button at the
/// bottom. Only the middle changes.
class OnboardingScaffold extends StatelessWidget {
  const OnboardingScaffold({
    super.key,
    required this.progress,
    required this.title,
    required this.child,
    this.subtitle,
    this.onBack,
    this.actionLabel = 'Tiếp theo',
    this.onAction,
    this.scrollable = false,
    this.center = false,
  });

  /// Progress through the whole flow, in [0, 1].
  final double progress;

  final String title;
  final String? subtitle;
  final Widget child;

  /// `null` hides the back button — used for the first step.
  final VoidCallback? onBack;

  final String actionLabel;

  /// `null` puts the action button into its dimmed, untappable state. Used
  /// to block going on while the user has chosen nothing.
  final VoidCallback? onAction;

  /// Switched on when the middle is taller than the screen, as with the
  /// condition list.
  final bool scrollable;

  /// Centres the middle in the free space instead of butting it up under
  /// the question. On for the number wheel, off for an option list — a list
  /// reads more naturally when it sits close to the question.
  final bool center;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final editing = OnboardingEditScope.of(context);

    final header = Column(
      children: [
        Text(title, style: text.displaySmall, textAlign: TextAlign.center),
        if (subtitle != null) ...[
          const SizedBox(height: 10),
          Text(subtitle!, style: text.bodyLarge, textAlign: TextAlign.center),
        ],
      ],
    );

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(progress: editing ? null : progress, onBack: onBack),
            Expanded(
              child: scrollable
                  ? SingleChildScrollView(
                      // A wider bottom inset so the last card scrolls
                      // clear of the action button, rather than stopping at
                      // its edge and looking cut off.
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
                      child: Column(
                        children: [header, const SizedBox(height: 28), child],
                      ),
                    )
                  : Padding(
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
                      child: Column(
                        children: [
                          header,
                          const SizedBox(height: 28),
                          if (center)
                            Expanded(child: Center(child: child))
                          else
                            child,
                        ],
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
              child: FilledButton(
                onPressed: onAction,
                child: Text(editing ? 'Lưu thay đổi' : actionLabel),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The back button and the progress bar.
///
/// The bar animates smoothly between steps rather than jumping — the user can
/// see how far they just advanced and how far is left, and that is what keeps
/// them walking through a long flow.
class _TopBar extends StatelessWidget {
  const _TopBar({required this.progress, required this.onBack});

  /// `null` hides the bar: a single answer being edited has no flow to be
  /// part-way through.
  final double? progress;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final progress = this.progress;

    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 12, 24, 12),
      child: Row(
        children: [
          SizedBox(
            width: 48,
            height: 48,
            child: AnimatedOpacity(
              opacity: onBack == null ? 0 : 1,
              duration: AppMotion.quick,
              child: IconButton(
                onPressed: onBack,
                icon: const Icon(Icons.arrow_back_rounded),
                color: AppColors.textPrimary,
                iconSize: 26,
              ),
            ),
          ),
          if (progress == null)
            const Spacer()
          else
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: progress.clamp(0.0, 1.0)),
                  duration: AppMotion.page,
                  curve: AppMotion.emphasized,
                  builder: (context, value, _) => LinearProgressIndicator(
                    value: value,
                    minHeight: 6,
                    backgroundColor: AppColors.surfaceMuted,
                    valueColor: const AlwaysStoppedAnimation(AppColors.ink),
                  ),
                ),
              ),
            ),
          // A gap symmetric with the back button, so the progress bar
          // sits centred.
          const SizedBox(width: 24),
        ],
      ),
    );
  }
}
