// OFFLINE: one F1 rule as the device understands it.
import '../models/food.dart';
import 'day_budget.dart';
import 'evidence_level.dart';

/// Why a dish was dropped from the recommendations — **three tiers, not
/// two**.
///
/// The `FeasibilityInfo` of comparable apps only has feasible / not feasible.
/// The data here can distinguish more than that, and collapsing it throws
/// away exactly what the user needs most.
///
/// Note on language: `heading` is the group title shown on screen, so it
/// stays in Vietnamese.
enum ExclusionTier {
  /// A property of **the dish itself** — it carries a forbidden tag, or lacks
  /// a required one, or exceeds a hard per-serving threshold. Never
  /// acceptable.
  dish('Không phù hợp với bạn'),

  /// **Today's** allowance is used up. Nothing is wrong with the dish — it is
  /// selectable on another day.
  ///
  /// This tier is the easiest one to describe wrongly. Showing "Phở sốt vang
  /// was dropped" the same way as "Tôm rang me was dropped" leaves the user
  /// believing phở is forbidden for them, when the real reason is only that
  /// they ate something salty this morning.
  dayBudget('Hôm nay hết hạn mức'),

  /// **Cannot be judged**, because the catalogue has no measurement for the
  /// restricted nutrient.
  ///
  /// This is NOT "fits". For purine it is 248 of 318 dishes, so folding this
  /// group into the "fits" group would mean a gout patient's purine ceiling
  /// is almost never reached.
  unknown('Chưa xét được');

  const ExclusionTier(this.heading);

  /// The group title in the interface.
  final String heading;
}

/// One reason a dish was dropped.
///
/// Mirrors `ExclusionReason` in `ml/f1_filter.py` plus `LimitExceedance` in
/// `ml/daily_limits.py` — two sources, one type, because the interface lists
/// them side by side.
class ExclusionReason {
  const ExclusionReason({
    required this.tier,
    required this.condition,
    required this.evidence,
    this.tag,
    this.nutrient,
    this.unit = '',
    this.threshold,
    this.measured,
    this.remaining,
    this.note = '',
  });

  /// The dish carries a forbidden tag, or lacks a required one.
  const ExclusionReason.tagRule({
    required String condition,
    required String tag,
    String note = '',
  }) : this(
         tier: ExclusionTier.dish,
         condition: condition,
         evidence: EvidenceLevel.definitional,
         tag: tag,
         note: note,
       );

  final ExclusionTier tier;
  final String condition;
  final EvidenceLevel evidence;

  /// The tag name, for either kind of tag rule.
  final String? tag;

  final String? nutrient;
  final String unit;

  /// The rule's threshold.
  final double? threshold;

  /// The dish's measurement. `null` means **no data**, not 0.
  final double? measured;

  /// How much of the allowance is left; present only on the
  /// [ExclusionTier.dayBudget] tier.
  final double? remaining;

  final String note;

  /// The dish was dropped for having no measurement, not for exceeding a
  /// threshold.
  ///
  /// Telling the user "this dish exceeds a limit" when the truth is "we do
  /// not know" is a false statement, so the two have to be kept apart.
  bool get missingData => nutrient != null && measured == null;

  /// By how much it is over. `null` when that cannot be computed.
  double? get over {
    if (measured == null) return null;
    final limit = tier == ExclusionTier.dayBudget ? remaining : threshold;
    if (limit == null) return null;
    return measured! - limit;
  }
}

/// A **soft** per-serving constraint: exceeding it costs score, it does not
/// drop the dish.
class SoftRule {
  const SoftRule({
    required this.condition,
    required this.nutrient,
    required this.unit,
    required this.threshold,
    required this.penalty,
    required this.evidence,
    this.note = '',
  });

  final String condition;
  final String nutrient;
  final String unit;
  final double threshold;

  /// A **multiplier**, not an amount to subtract.
  ///
  /// The schema only says `DECIMAL(4,3)`, but the data itself shows how to
  /// read it: hypertension has 0.600 at the mild level and 0.400 at the
  /// severe one, with a note saying "a harsher penalty for the severe level".
  /// Read as a subtraction, 0.400 takes away LESS, meaning the severe level
  /// is penalised more gently — the exact opposite of the note. As a
  /// multiplier, ×0.400 is harsher than ×0.600, which matches; and
  /// multiplying keeps the score inside [0, 1] while subtracting 0.750 would
  /// push a score in [0, 1] below zero.
  final double penalty;

  final EvidenceLevel evidence;
  final String note;

  bool violatedBy(double value) => value > threshold;
}

/// One soft constraint that this dish exceeds.
class SoftViolation {
  const SoftViolation({required this.rule, required this.measured});

  final SoftRule rule;
  final double measured;

  double get over => measured - rule.threshold;
}

/// A dish's penalty factor, with the reasons for the interface to state.
class PenaltyOutcome {
  const PenaltyOutcome({
    required this.factor,
    this.violations = const [],
    this.missingNutrients = const [],
  });

  /// The final multiplier, in (0, 1].
  final double factor;

  final List<SoftViolation> violations;

  /// The nutrients this dish has no measurement for, so none of their soft
  /// rules could be judged. Not penalised, but not to be treated as checked
  /// either.
  final List<String> missingNutrients;

  bool get penalised => factor < 1.0;

  /// Applies the factor to a score in [0, 1].
  ///
  /// The original score stays with the caller: the interface needs to say
  /// "taste match 0.78, reduced for being salty" rather than just showing
  /// 0.47 with no explanation.
  double applyTo(double score) => score * factor;

  /// A dish's penalty factor under the **per-serving** soft constraints.
  ///
  /// **Penalties are combined per group, not multiplied straight through.**
  /// Two rules sharing a (condition, nutrient) pair are two nested bands —
  /// sodium ≤ 700 mg and ≤ 500 mg, both from hypertension. A dish at 800 mg
  /// exceeds both, but that is **one** concern, not two: multiplying both
  /// gives ×0.24 instead of ×0.40, which is double counting. So within each
  /// group the harshest factor wins, and the factors are then multiplied
  /// across different groups.
  ///
  /// Missing data means **no penalty**, but it is recorded. A soft constraint
  /// is a ranking decision, not a safety one, so lowering a dish's score
  /// because the catalogue is incomplete penalises the wrong party.
  static PenaltyOutcome of(Food food, List<SoftRule> rules) {
    final harshest = <String, SoftViolation>{};
    final missing = <String>[];

    for (final r in rules) {
      final value = DayBudget.valueOf(food, r.nutrient);
      if (value == null) {
        if (!missing.contains(r.nutrient)) missing.add(r.nutrient);
        continue;
      }
      if (!r.violatedBy(value)) continue;
      final key = '${r.condition}|${r.nutrient}';
      final current = harshest[key];
      if (current == null || r.penalty < current.rule.penalty) {
        harshest[key] = SoftViolation(rule: r, measured: value);
      }
    }

    var factor = 1.0;
    for (final v in harshest.values) {
      factor *= v.rule.penalty;
    }
    final sorted = harshest.values.toList()
      ..sort((a, b) => a.rule.penalty.compareTo(b.rule.penalty));
    missing.sort();

    return PenaltyOutcome(
      factor: factor,
      violations: sorted,
      missingNutrients: missing,
    );
  }
}
