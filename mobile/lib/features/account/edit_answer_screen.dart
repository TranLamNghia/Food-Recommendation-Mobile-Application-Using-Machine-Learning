import 'package:flutter/material.dart';

import '../../data/session.dart';
import '../onboarding/onboarding_flow.dart';
import '../onboarding/steps/activity_step.dart';
import '../onboarding/steps/birth_year_step.dart';
import '../onboarding/steps/conditions_step.dart';
import '../onboarding/steps/gender_step.dart';
import '../onboarding/steps/goal_step.dart';
import '../onboarding/steps/height_step.dart';
import '../onboarding/steps/motivation_step.dart';
import '../onboarding/steps/target_weight_step.dart';
import '../onboarding/steps/weight_step.dart';
import '../onboarding/widgets/onboarding_scaffold.dart';

/// One onboarding question re-opened on its own, to change a single answer.
///
/// Reuses the step widget as is — same wording, same input — inside an
/// [OnboardingEditScope], which swaps the progress bar and "next" for a plain
/// "save". Pops `true` when the user saved, `null` when they backed out.
///
/// Steps that write to the profile on every tap (gender, goal, activity, the
/// two condition lists) cannot be backed out of: the tap already changed the
/// profile. The caller recalculates on `true` only, so backing out leaves a
/// changed answer with a stale plan until the next save. Acceptable for a
/// mock; the API version should edit a copy and commit on save.
class EditAnswerScreen extends StatefulWidget {
  const EditAnswerScreen({super.key, required this.step});

  final OnboardingStep step;

  static Future<bool?> open(BuildContext context, OnboardingStep step) =>
      Navigator.of(context).push<bool>(
        MaterialPageRoute(builder: (_) => EditAnswerScreen(step: step)),
      );

  @override
  State<EditAnswerScreen> createState() => _EditAnswerScreenState();
}

class _EditAnswerScreenState extends State<EditAnswerScreen> {
  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final profile = SessionScope.of(context).profile;
    void back() => Navigator.of(context).pop();
    void save() => Navigator.of(context).pop(true);

    return OnboardingEditScope(
      child: switch (widget.step) {
        OnboardingStep.gender => GenderStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
          onChanged: _changed,
        ),
        OnboardingStep.birthYear => BirthYearStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
        ),
        OnboardingStep.height => HeightStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
        ),
        OnboardingStep.weight => WeightStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
        ),
        OnboardingStep.goal => GoalStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
          onChanged: _changed,
        ),
        OnboardingStep.targetWeight => TargetWeightStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
        ),
        OnboardingStep.activity => ActivityStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
          onChanged: _changed,
        ),
        OnboardingStep.conditions => ConditionsStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
          onChanged: _changed,
          kind: ConditionKind.disease,
        ),
        OnboardingStep.allergies => ConditionsStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
          onChanged: _changed,
          kind: ConditionKind.allergy,
        ),
        OnboardingStep.motivation => MotivationStep(
          profile: profile,
          progress: 1,
          onBack: back,
          onNext: save,
        ),
      },
    );
  }
}
