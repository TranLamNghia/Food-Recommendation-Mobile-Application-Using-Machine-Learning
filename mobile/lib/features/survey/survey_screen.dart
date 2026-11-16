import 'package:flutter/material.dart';

import '../../core/theme/app_motion.dart';
import '../../data/models/food.dart';
import '../../data/models/swipe_action.dart';
import '../../data/session.dart';
import 'survey_result_screen.dart';
import 'widgets/survey_footer.dart';
import 'widgets/swipe_burst.dart';
import 'widgets/swipe_deck.dart';

/// One recorded swipe.
typedef SwipeResult = ({Food food, SwipeAction action});

/// The taste survey screen — it runs exactly once, right after the user
/// fills in their health profile.
///
/// The whole result is held in memory and sent to the server **once only**,
/// when the swiping is done (API specification §7.4). So this screen counts
/// its own progress, never asks the server after each swipe, and keeps
/// working with no connection at all.
class SurveyScreen extends StatefulWidget {
  const SurveyScreen({super.key, required this.foods});

  final List<Food> foods;

  @override
  State<SurveyScreen> createState() => _SurveyScreenState();
}

class _SurveyScreenState extends State<SurveyScreen> {
  final _deck = SwipeDeckController();
  final List<SwipeResult> _results = [];

  int _cursor = 0;

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

  void _handleSwipe(Food food, SwipeAction action) {
    setState(() {
      _results.add((food: food, action: action));
      _cursor++;
    });

    if (_isDone) _finish();
  }

  void _finish() {
    // Submit the whole result as one package, exactly as the swipe session
    // is designed: the app holds every swipe in memory and then sends one
    // single request.
    SessionScope.of(context).completeSurvey(_results);

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
