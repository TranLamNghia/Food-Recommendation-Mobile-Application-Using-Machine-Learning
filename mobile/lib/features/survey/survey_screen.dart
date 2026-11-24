import 'package:flutter/material.dart';

import '../../core/theme/app_motion.dart';
import '../../data/api/failure.dart';
import '../../data/models/food_brief.dart';
import '../../data/models/swipe_action.dart';
import '../../data/session.dart';
import 'survey_result_screen.dart';
import 'widgets/survey_footer.dart';
import 'widgets/swipe_burst.dart';
import 'widgets/swipe_deck.dart';

/// One recorded swipe.
typedef SwipeResult = ({FoodBrief food, SwipeAction action});

/// The taste survey screen — it runs exactly once, right after the user
/// fills in their health profile.
///
/// The whole result is held in memory and sent to the server **once only**,
/// when the swiping is done (API specification §7.4). So this screen counts
/// its own progress, never asks the server after each swipe, and keeps
/// working with no connection at all.
class SurveyScreen extends StatefulWidget {
  const SurveyScreen({super.key, required this.foods});

  final List<FoodBrief> foods;

  @override
  State<SurveyScreen> createState() => _SurveyScreenState();
}

class _SurveyScreenState extends State<SurveyScreen> {
  final _deck = SwipeDeckController();
  final List<SwipeResult> _results = [];

  int _cursor = 0;

  /// True while the session is being sent. The deck is already exhausted by
  /// then, so nothing can be swiped on top of it; the flag is what stops a
  /// retry from running twice.
  bool _submitting = false;

  /// The deck area takes 581 of the design frame's 844 height.
  static const _deckRatio = 581 / 844;

  /// Share of the footer's height the bottom particle zone reaches under.
  /// Just under half: particles stay in the footer's see-through upper part
  /// and are gone before its grey turns solid.
  static const _burstUnderFooter = 0.45;

  bool get _isDone => _cursor >= widget.foods.length;

  @override
  void dispose() {
    _deck.dispose();
    super.dispose();
  }

  void _handleSwipe(FoodBrief food, SwipeAction action) {
    setState(() {
      _results.add((food: food, action: action));
      _cursor++;
    });

    if (_isDone) _finish();
  }

  /// Submits the session and moves on — or stays put and says why.
  ///
  /// The submission is **the end of onboarding**: it is what stamps
  /// `users.onboarding_completed_at`, and the launch screen reads that stamp
  /// to decide where to send the user. So this cannot be fire-and-forget. An
  /// earlier version called it and navigated on regardless, which online put
  /// the user back on this screen at every launch, for good, with thirty
  /// swipes stored and no stamp to show for them.
  Future<void> _finish() async {
    if (_submitting) return;
    setState(() => _submitting = true);
    final session = SessionScope.of(context);
    try {
      // The whole result as one package, exactly as the swipe session is
      // designed: the app holds every swipe in memory and sends one request.
      await session.completeSurvey(_results);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() => _submitting = false);
      await _explain(failure);
      return;
    }
    if (!mounted) return;
    setState(() => _submitting = false);
    _goToResult();
  }

  /// What to do about a refusal, which differs by kind and is not a snackbar
  /// in any of the three cases.
  Future<void> _explain(ApiFailure failure) async {
    if (failure.code == ApiFailure.onboardingAlreadyCompleted) {
      // Not an error to the user: the account has been through this before.
      // The app is simply on the wrong screen, so it leaves.
      _goToResult();
      return;
    }

    final insufficient = failure.code == ApiFailure.onboardingInsufficient;
    final retry = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(
          insufficient ? 'Cần thêm ý kiến của bạn' : 'Chưa gửi được',
        ),
        content: Text(failure.message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Để sau'),
          ),
          if (insufficient)
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Vuốt lại'),
            )
          else if (failure.isRetryable)
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Thứ lại'),
            ),
        ],
      ),
    );
    if (!mounted) return;

    if (retry != true) {
      Navigator.of(context).pop();
      return;
    }
    if (insufficient) {
      // A fresh deck and a fresh session id. The old session's rows stay
      // where they are — they record that the user was asked — and the
      // account is not stamped, so this screen is still the right one.
      Navigator.of(context).pop();
      return;
    }
    // Re-sending the same session id REPLACES that session's rows rather
    // than adding a second copy, so retrying is safe however far the first
    // attempt got.
    await _finish();
  }

  void _goToResult() {
    // Wait for the last card to fly fully off screen before changing
    // screens, so no motion is cut short.
    Future.delayed(AppMotion.quick, () {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          transitionDuration: AppMotion.page,
          pageBuilder: (_, _, _) => SurveyResultScreen(results: _results),
          transitionsBuilder: (_, animation, _, child) => FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween(begin: const Offset(0, 0.06), end: Offset.zero)
                  .animate(
                    CurvedAnimation(
                      parent: animation,
                      curve: AppMotion.emphasized,
                    ),
                  ),
              child: child,
            ),
          ),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final height = MediaQuery.sizeOf(context).height;
    final footerHeight = height * SurveyFooter.heightRatio;

    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          // The particles: the same frame as the deck area but **not
          // clipped**, and sitting under both the cards and the footer. The
          // bottom particle zone is pushed down by nearly half the footer's
          // height, so its particles drift through the footer's transparent
          // top and then sink into the solid grey below.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: height * _deckRatio,
            child: SwipeBurst(
              signal: _deck.signal,
              bottomOverflow: footerHeight * _burstUnderFooter,
            ),
          ),
          // The deck area — the `Card` frame (5:32) takes 581 of the
          // 844 height.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: height * _deckRatio,
            // Clipped to this area so a card flying out disappears at the
            // footer's edge instead of showing through its transparent
            // part.
            child: ClipRect(
              child: Stack(
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: _isDone
                        ? const SizedBox.shrink()
                        : SwipeDeck(
                            foods: widget.foods,
                            cursor: _cursor,
                            controller: _deck,
                            onSwipe: _handleSwipe,
                          ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: footerHeight,
            child: SurveyFooter(done: _cursor, total: widget.foods.length),
          ),
        ],
      ),
    );
  }
}
