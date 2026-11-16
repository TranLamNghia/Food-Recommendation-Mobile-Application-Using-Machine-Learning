import '../mock/mock_rules.dart';
import '../models/food.dart';
import 'condition_rule.dart';
import 'day_budget.dart';

/// The result of screening a set of dishes against the user's conditions and
/// what is left of today's allowance.
///
/// Mirrors `f1_filter.allowed_foods` + `f1_filter.exclusion_reasons` +
/// `daily_limits.classify_foods` on the Python side. The important part is
/// that it returns the **reasons**, not just the surviving set: taking the
/// complement only tells you which dishes disappeared, not why, and the "why"
/// is the only thing that makes a health recommendation believable.
class ScreeningResult {
  const ScreeningResult({
    required this.allowed,
    required this.excluded,
    required this.penalties,
  });

  /// Dishes that pass every hard constraint **and** have a measurement for
  /// every restricted nutrient.
  final List<Food> allowed;

  /// The dropped dishes with all their reasons. One dish can breach several
  /// rules at once, and every breached rule is listed: fixing one does not
  /// make the dish acceptable.
  final Map<String, List<ExclusionReason>> excluded;

  /// The soft penalty factor of the **allowed** dishes, keyed by `food.id`.
  ///
  /// Only the allowed ones: a soft penalty is a ranking matter, so computing
  /// it for a dish that has already been dropped is meaningless.
  final Map<String, PenaltyOutcome> penalties;

  /// The dropped dishes, grouped by reason tier.
  ///
  /// A dish belongs to the **most serious** of its reasons: breaching a
  /// property of the dish itself makes it irrelevant whether today's
  /// allowance is also used up.
  Map<ExclusionTier, List<String>> get byTier {
    final grouped = <ExclusionTier, List<String>>{
      ExclusionTier.dish: [],
      ExclusionTier.dayBudget: [],
      ExclusionTier.unknown: [],
    };
    for (final e in excluded.entries) {
      final tier = e.value
          .map((r) => r.tier)
          .reduce((a, b) => a.index <= b.index ? a : b);
      grouped[tier]!.add(e.key);
    }
    return grouped;
  }
}

/// Screens [foods] for one person: three reason tiers, not two.
///
/// The order of the checks is deliberate and cannot be changed:
///
/// 1. **Tags** — properties of the dish itself, independent of what was eaten
///    today.
/// 2. **The day's allowance** — nothing is wrong with the dish, today's
///    allowance is simply nearly used up. It is selectable on another day,
///    and the interface has to say so.
/// 3. **Missing data** — no conclusion is possible. This is NOT "fits": for
///    purine it is 20 of the 30 sample dishes, so folding it into the "fits"
///    group would mean a gout patient's purine ceiling is almost never
///    reached.
///
/// Breaching a **known** threshold settles it immediately, even when another
/// threshold has no data — it already definitely does not fit.
ScreeningResult screenDishes({
  required List<Food> foods,
  required List<UserCondition> conditions,
  required DayBudget budget,
  List<SoftRule> softRules = const [],
}) {
  final allowed = <Food>[];
  final excluded = <String, List<ExclusionReason>>{};
  final penalties = <String, PenaltyOutcome>{};

  final hardLimits = budget.hard;

  for (final food in foods) {
    final reasons = <ExclusionReason>[];

    // ── 1. Tags ──
    reasons.addAll(tagExclusionsFor(food, conditions));

    // ── 2 & 3. The day's allowance ──
    final missing = <ExclusionReason>[];
    for (final limit in hardLimits) {
      final value = DayBudget.valueOf(food, limit.nutrient);
      if (value == null) {
        missing.add(
          ExclusionReason(
            tier: ExclusionTier.unknown,
            condition: limit.condition,
            evidence: limit.evidence,
            nutrient: limit.nutrient,
            unit: limit.unit,
            threshold: limit.amount,
            remaining: limit.remaining,
            note: limit.note,
          ),
        );
        continue;
      }
      if (!limit.fits(value)) {
        reasons.add(
          ExclusionReason(
            tier: ExclusionTier.dayBudget,
            condition: limit.condition,
            evidence: limit.evidence,
            nutrient: limit.nutrient,
            unit: limit.unit,
            threshold: limit.amount,
            measured: value,
            remaining: limit.remaining,
            note: limit.note,
          ),
        );
      }
    }

    if (reasons.isNotEmpty) {
      excluded[food.id] = reasons;
      continue;
    }
    if (missing.isNotEmpty) {
      excluded[food.id] = missing;
      continue;
    }

    allowed.add(food);
    penalties[food.id] = PenaltyOutcome.of(food, softRules);
  }

  return ScreeningResult(
    allowed: allowed,
    excluded: excluded,
    penalties: penalties,
  );
}
