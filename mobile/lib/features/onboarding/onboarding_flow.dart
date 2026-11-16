import 'package:flutter/material.dart';

import '../../core/theme/app_motion.dart';
import '../../data/models/health_profile.dart';
import '../../data/session.dart';
import 'calculating_screen.dart';
import 'steps/activity_step.dart';
import 'steps/birth_year_step.dart';
import 'steps/conditions_step.dart';
import 'steps/gender_step.dart';
import 'steps/goal_step.dart';
import 'steps/height_step.dart';
import 'steps/motivation_step.dart';
import 'steps/target_weight_step.dart';
import 'steps/weight_step.dart';

/// The profile steps, in the order the user meets them.
enum OnboardingStep {
  gender,
  birthYear,
  height,
  weight,
  goal,
  targetWeight,
  activity,
  conditions,
  allergies,
  motivation,
}

/// The health profile flow, which runs before the taste survey session.
///
/// All the data is held in one single [HealthProfile] object and only sent to
/// the server at the end of the flow, the same way the swipe session sends
/// its result as one package. That lets the user go back and edit as often as
/// they like without producing dozens of half-finished network calls.
class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({super.key});

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  /// The profile lives in [AppSession] rather than in this flow alone,
  /// because the plan screen and the progress screen behind it both need to
  /// read it back.
  HealthProfile get _profile => SessionScope.of(context).profile;

  int _index = 0;

  /// The most recent direction of travel, so a new screen slides in from
  /// the right side.
  bool _forward = true;

  /// The `targetWeight` step only appears when the goal is to gain or lose
  /// weight, so the step list is recomputed on every build rather than being
  /// fixed.
  List<OnboardingStep> get _steps => [
    for (final step in OnboardingStep.values)
      if (step != OnboardingStep.targetWeight ||
          (_profile.goal?.needsTargetWeight ?? false))
        step,
  ];

  void _next() {
    final steps = _steps;
    if (_index >= steps.length - 1) {
      _finish();
      return;
    }
    setState(() {
      _forward = true;
      _index++;
    });
  }

  void _back() {
    if (_index == 0) return;
    setState(() {
      _forward = false;
      _index--;
    });
  }

  void _finish() {
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        transitionDuration: AppMotion.page,
        pageBuilder: (_, _, _) => CalculatingScreen(profile: _profile),
        transitionsBuilder: (_, animation, _, child) =>
            FadeTransition(opacity: animation, child: child),
      ),
    );
  }

  /// Called when a step changes data that can make the step list longer or
  /// shorter — specifically, when the user changes their goal.
  void _onChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final steps = _steps;
    final step = steps[_index.clamp(0, steps.length - 1)];

    // The progress is computed from the step's fixed position in the enum,
    // not from the filtered list. Were the denominator the actual number of
    // steps, then the moment the user chose "gain weight" — the very action
    // that adds a step to the flow — the denominator would jump from 9 to 10
    // and the progress bar would slide backwards in front of them. This way
    // the bar only holds still or advances, and a skipped step makes it jump
    // two notches.
    final progress =
        (OnboardingStep.values.indexOf(step) + 1) /
        OnboardingStep.values.length;

    final onBack = _index == 0 ? null : _back;

    final child = switch (step) {
      OnboardingStep.gender => GenderStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.birthYear => BirthYearStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.height => HeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.weight => WeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.goal => GoalStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.targetWeight => TargetWeightStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
      OnboardingStep.activity => ActivityStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
      ),
      OnboardingStep.conditions => ConditionsStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
        kind: ConditionKind.disease,
      ),
      OnboardingStep.allergies => ConditionsStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
        onChanged: _onChanged,
        kind: ConditionKind.allergy,
      ),
      OnboardingStep.motivation => MotivationStep(
        profile: _profile,
        progress: progress,
        onBack: onBack,
        onNext: _next,
      ),
    };

    return AnimatedSwitcher(
      duration: AppMotion.page,
      switchInCurve: AppMotion.emphasized,
      switchOutCurve: Curves.easeIn,
      // The new screen slides in from the direction the user is heading and
      // the old one retreats the other way — it feels like walking down a
      // corridor rather than jumping between disconnected pages.
      transitionBuilder: (child, animation) {
        final incoming = child.key == ValueKey(step);
        final dx = _forward ? 1.0 : -1.0;
        return FadeTransition(
          opacity: animation,
          child: SlideTransition(
            position: Tween(
              begin: Offset(incoming ? dx * 0.10 : -dx * 0.10, 0),
              end: Offset.zero,
            ).animate(animation),
            child: child,
          ),
        );
      },
      layoutBuilder: (current, previous) => Stack(
        alignment: Alignment.topCenter,
        children: [...previous, ?current],
      ),
      child: KeyedSubtree(key: ValueKey(step), child: child),
    );
  }
}
