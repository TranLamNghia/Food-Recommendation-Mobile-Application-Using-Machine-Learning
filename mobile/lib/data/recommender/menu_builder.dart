// OFFLINE: the Dart copy of step 4, held in parity with ml/menu_builder.py.
import 'dart:math' as math;

import '../models/food.dart';
import '../models/meal_plan.dart';
import 'nutrient_target.dart';
import 'preference_profile.dart';

/// The shape of a meal: the dish roles it must have, and the roles that can
/// be added if the meal is still short of energy.
///
/// The role constraint exists because taking the top-K highest-scoring dishes
/// does **not** produce a sensible meal — all three could be savoury dishes,
/// or all three desserts if the user has a sweet tooth. The roles force the
/// meal into the right shape before taste is considered at all.
///
/// [optional] exists because one dish cannot cover a whole meal's allowance:
/// breakfast for someone needing 2,500 kcal gets 27.5 %, around 690 kcal,
/// while the heaviest dish in the catalogue is just over 600. Without
/// optional servings the plan always falls short of the target, no matter how
/// cleverly the algorithm picks.
///
/// Note on language: the role strings in [_mealStructure] are data — they
/// match the `Food.dishRole` values exactly — so they stay in Vietnamese.
class _MealShape {
  const _MealShape({required this.required, this.optional = const []});

  final List<String> required;
  final List<String> optional;
}

const _mealStructure = <MealType, _MealShape>{
  MealType.breakfast: _MealShape(
    required: ['Món chính'],
    optional: ['Món phụ'],
  ),
  MealType.lunch: _MealShape(
    required: ['Món chính', 'Món mặn'],
    optional: ['Món canh'],
  ),
  MealType.dinner: _MealShape(
    required: ['Món chính', 'Món rau'],
    optional: ['Món mặn'],
  ),
  MealType.snack: _MealShape(required: ['Món phụ']),
};

/// One serving to fill, identified by its meal and its dish role.
typedef _Slot = ({MealType meal, String role, bool explore});

/// Generates the daily meal plan from the preference profile and the
/// nutrition targets.
///
/// Implements Step 3 and Step 4 of the recommendation algorithm:
///
/// 1. Score every dish by its cosine similarity to the preference profile.
/// 2. Split the servings by the 70-30 mechanism — most are ranked by the
///    preference vector, the rest by that same vector after adding noise.
/// 3. Choose the combination by **greedy score density**, top up with
///    optional servings until the target is reached, then improve it with a
///    **local search** on a penalised objective function.
///
/// The F1 filter (allergies, conditions, diets) sits outside this class: it
/// has to run **first** and pass in an already-safe dish set as
/// [candidates]. Exploration only loosens things on taste, never on safety.
class MenuBuilder {
  MenuBuilder({
    required this.candidates,
    required this.profile,
    this.explorationRatio = 0.3,
    this.explorationDelta = 0.35,
    this.energyPenalty = 1.2,
    this.macroPenalty = 0.6,
    this.localSearchRounds = 20,
    this.nutrientTargets = const [],
    this.nutrientRepairRounds = 12,
    this.maxEnergyDeviation = 0.10,
    math.Random? rng,
  }) : _rng = rng ?? math.Random();

  /// The dish set that has already passed the F1 filter.
  final List<Food> candidates;

  final PreferenceProfile profile;

  /// The share of servings given to exploration. Hard-capped at 50 % — see
  /// `chk_expl_ratio`.
  final double explorationRatio;

  /// The noise amplitude δ used when rotating the preference vector for the
  /// exploration group.
  final double explorationDelta;

  /// The penalty coefficient λ for the energy deviation in the objective
  /// function.
  final double energyPenalty;

  /// The penalty coefficient μ for each macronutrient's deviation.
  final double macroPenalty;

  /// The maximum number of rounds in the local search phase.
  final int localSearchRounds;

  /// The micronutrient constraints at the **day** level — the `per_day` hard
  /// thresholds of `condition_rules`, plus the goals the user stated.
  final List<NutrientTarget> nutrientTargets;

  /// The maximum number of swaps phase 5 may make. An upper bound, so the
  /// repair phase does not run forever when the catalogue holds no dishes
  /// that would satisfy the constraint.
  final int nutrientRepairRounds;

  /// The ceiling on the energy deviation phase 5 is allowed to push the plan
  /// to.
  ///
  /// 10 % is the commitment made in the thesis proposal. Phase 5 **never**
  /// pushes the deviation past that mark in exchange for satisfying a
  /// micronutrient constraint: doing so would cure one violation by creating
  /// another.
  final double maxEnergyDeviation;

  final math.Random _rng;

  /// Generates the plan for one day.
  ///
  /// [targetKcal] is the whole day's energy target, already computed from the
  /// health profile (the TDEE adjusted for the goal). Each meal's target
  /// follows from [MealType.energyShare].
  DailyPlan build({
    required DateTime date,
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    final ratio = explorationRatio.clamp(0.0, 0.5);
    final exploreProfile = profile.jittered(delta: explorationDelta, rng: _rng);

    final slots = _assignExplorationSlots(ratio);
    final picks = <MealType, List<MealPlanItem>>{
      for (final t in MealType.values) t: [],
    };
    final usedIds = <String>{};

    // ── Phase 1 — greedy over the required servings ──────────────────
    for (final slot in slots) {
      final activeProfile = slot.explore ? exploreProfile : profile;
      final pool = candidates
          .where((f) => f.dishRole == slot.role && !usedIds.contains(f.id))
          .toList();

      // With no dish left in the right role, skip the serving rather than
      // forcing in a dish of the wrong role — a meal missing its soup is
      // still more sensible than a meal with two main dishes.
      if (pool.isEmpty) continue;

      final mealTarget = targetKcal * slot.meal.energyShare;
      final already = _kcalOf(picks[slot.meal]!);
      final remainingSlots = slots
          .where((s) => s.meal == slot.meal)
          .length
          .clamp(1, 99);

      final best = _greedyPick(
        pool: pool,
        profile: activeProfile,
        slotTargetKcal: (mealTarget - already) / remainingSlots,
      );

      usedIds.add(best.id);
      picks[slot.meal]!.add(
        MealPlanItem.offline(
          dish: best,
          score: activeProfile.score(best),
          explorationDelta: slot.explore ? explorationDelta : null,
        ),
      );
    }

    // ── Phase 2 — top up with optional servings, at the day level ────
    _topUp(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    // ── Phase 3 — local search within each meal ──────────────────────
    for (final type in MealType.values) {
      final before = picks[type]!.map((i) => i.dish!.id).toSet();

      final refined = _localSearch(
        selected: picks[type]!,
        usedIds: usedIds,
        targetKcal: targetKcal * type.energyShare,
        targetProtein: targetProtein * type.energyShare,
        targetCarb: targetCarb * type.energyShare,
        targetFat: targetFat * type.energyShare,
      );

      // Update `usedIds` from the swap result before moving to the next meal.
      //
      // Without this step, a dish just swapped INTO breakfast is not in
      // `usedIds`, so lunch still sees it as free and takes it too — the same
      // dish appears twice in one day. Conversely, a dish swapped OUT has to
      // be returned to the candidate set, because it is no longer in the
      // plan.
      final after = refined.map((i) => i.dish!.id).toSet();
      usedIds
        ..removeAll(before.difference(after))
        ..addAll(after);

      picks[type] = refined;
    }

    // ── Phase 4 — top up again at the day level ──────────────────────
    //
    // Phase 3 optimises each meal **separately**, so it can pull the whole
    // day's energy away from the target even while every single meal
    // improves: swapping a lighter main dish into lunch makes that meal match
    // its macros better, but leaves the day shorter still.
    //
    // Calling `_topUp` again after phase 3 fixes that. It only adds a dish
    // when that dish makes the day-level gap **smaller**, so it can never
    // make things worse — running one more pass is safe.
    _topUp(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    // ── Phase 5 — enforce the day-level micronutrient constraints ────
    //
    // It has to be at the day level and it has to be last: the threshold
    // "sodium under 2000 mg/day" is a statement about the **whole day's
    // total**, so it cannot be checked in phase 1 (which picks one serving at
    // a time) nor in phase 3 (which optimises one meal at a time).
    //
    // This is the part that used to be missing entirely. `condition_rules`
    // stores six hard `per_day` thresholds, the documentation said Step 4
    // checked them, but Step 4 only tracked `kcal` and the three macros —
    // meaning those thresholds were enforced nowhere at all.
    _repairNutrients(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    final result = [
      for (final type in MealType.values)
        MealSlot(
          type: type,
          targetKcal: targetKcal * type.energyShare,
          items: picks[type]!,
        ),
    ];

    return DailyPlan(
      date: date,
      targetKcal: targetKcal,
      targetProtein: targetProtein,
      targetCarb: targetCarb,
      targetFat: targetFat,
      slots: result,
      explorationRatio: ratio,
      nutrientTargets: nutrientTargets,
    );
  }

  /// The whole day's total of each nutrient.
  Map<String, double> _dayTotals(Map<MealType, List<MealPlanItem>> picks) {
    final totals = <String, double>{};
    for (final nutrient in NutrientTarget.supported) {
      var sum = 0.0;
      for (final items in picks.values) {
        for (final item in items) {
          sum += NutrientTarget.valueOf(item.dish!, nutrient) ?? 0;
        }
      }
      totals[nutrient] = sum;
    }
    return totals;
  }

  /// Phase 5 — repair the plan so it satisfies the day-level micronutrient
  /// constraints.
  ///
  /// It works by **swapping one dish for another in the same role**, adding
  /// nothing and removing nothing: adding a dish would break the energy
  /// target, removing one would break the meal's structure.
  ///
  /// Each round handles the **worst violation** first, measured as a fraction
  /// of the threshold so that nutrients in different units can be compared. A
  /// swap is only accepted when:
  ///
  ///   1. it makes the violation under consideration **smaller**;
  ///   2. it creates no new violation in any other constraint that is
  ///      currently satisfied;
  ///   3. the energy deviation after the swap is still within
  ///      [maxEnergyDeviation], or at least no worse than it already is.
  ///
  /// Condition 2 is the easiest one to get wrong. Without it this phase would
  /// fix a fibre shortfall by stuffing in high-sodium dishes, and someone
  /// with hypertension would get a plan that meets its fibre goal while
  /// breaching the very threshold that matters to them.
  ///
  /// When several swaps improve things equally, the one that **preserves
  /// taste best** is chosen: ignoring that criterion was measured to drop the
  /// taste-match score by 7.1 % instead of 2.1 %.
  void _repairNutrients({
    required Map<MealType, List<MealPlanItem>> picks,
    required Set<String> usedIds,
    required double targetKcal,
  }) {
    final active = nutrientTargets
        .where((t) => NutrientTarget.supported.contains(t.nutrient))
        .toList();
    if (active.isEmpty) return;

    for (var round = 0; round < nutrientRepairRounds; round++) {
      final totals = _dayTotals(picks);

      NutrientTarget? worst;
      var worstViolation = 0.0;
      for (final target in active) {
        final v = target.violation(totals[target.nutrient] ?? 0);
        if (v > worstViolation) {
          worstViolation = v;
          worst = target;
        }
      }
      if (worst == null) return;

      final kcalNow = picks.values.fold<double>(0, (s, l) => s + _kcalOf(l));
      final deviationNow = targetKcal <= 0
          ? 0.0
          : (kcalNow - targetKcal).abs() / targetKcal;
      final deviationCap = math.max(deviationNow, maxEnergyDeviation);

      MealType? bestMeal;
      var bestIndex = -1;
      Food? bestFood;
      var bestViolation = worstViolation;
      var bestScore = -1.0;

      for (final type in MealType.values) {
        final items = picks[type]!;
        for (var i = 0; i < items.length; i++) {
          final current = items[i].dish!;
          final currentValue =
              NutrientTarget.valueOf(current, worst.nutrient) ?? 0;

          for (final swap in candidates) {
            if (swap.dishRole != current.dishRole) continue;
            if (usedIds.contains(swap.id)) continue;

            final swapValue = NutrientTarget.valueOf(swap, worst.nutrient) ?? 0;
            final newTotal =
                (totals[worst.nutrient] ?? 0) - currentValue + swapValue;
            final newViolation = worst.violation(newTotal);
            if (newViolation > bestViolation) continue;

            final newKcal = kcalNow - current.kcal + swap.kcal;
            final newDeviation = targetKcal <= 0
                ? 0.0
                : (newKcal - targetKcal).abs() / targetKcal;
            if (newDeviation > deviationCap) continue;

            var breaksOther = false;
            for (final other in active) {
              if (other == worst) continue;
              final before = totals[other.nutrient] ?? 0;
              if (!other.isSatisfiedBy(before)) continue;
              final after =
                  before -
                  (NutrientTarget.valueOf(current, other.nutrient) ?? 0) +
                  (NutrientTarget.valueOf(swap, other.nutrient) ?? 0);
              if (!other.isSatisfiedBy(after)) {
                breaksOther = true;
                break;
              }
            }
            if (breaksOther) continue;

            final score = profile.score(swap);
            final strictlyBetter = newViolation < bestViolation - 1e-9;
            if (strictlyBetter || score > bestScore) {
              bestViolation = newViolation;
              bestScore = score;
              bestMeal = type;
              bestIndex = i;
              bestFood = swap;
            }
          }
        }
      }

      // No swap improves anything any more: the catalogue holds no dishes
      // that would satisfy this constraint. Stop and let
      // `DailyPlan.nutrientViolations` report it, rather than swapping dishes
      // pointlessly or returning an empty plan.
      if (bestMeal == null || bestFood == null) return;
      if (bestViolation >= worstViolation) return;

      final replaced = picks[bestMeal]![bestIndex];
      usedIds
        ..remove(replaced.dish!.id)
        ..add(bestFood.id);
      picks[bestMeal]![bestIndex] = MealPlanItem.offline(
        dish: bestFood,
        score: profile.score(bestFood),
        explorationDelta: replaced.explorationDelta,
      );
    }
  }

  /// Decides which servings are exploration, counted over the **whole plan**.
  ///
  /// The 70-30 ratio is a property of the plan rather than of a single meal —
  /// exactly as the `exploration_ratio` column sits on the `meal_plans`
  /// table. Were it split per meal and rounded down, a one-dish meal would
  /// always get 0 exploration servings and so would a three-dish one, with
  /// the result that the exploration mechanism never ran at all.
  ///
  /// Exploration servings are placed preferentially in the meals with more
  /// dishes, so that no single meal turns into nothing but trial dishes.
  List<_Slot> _assignExplorationSlots(double ratio) {
    final base = <({MealType meal, String role})>[
      for (final type in MealType.values)
        for (final role in _mealStructure[type]!.required)
          (meal: type, role: role),
    ];

    final budget = (base.length * ratio).round();
    if (budget == 0) {
      return [
        for (final s in base) (meal: s.meal, role: s.role, explore: false),
      ];
    }

    // Order the candidates by the meal's dish count, descending; shuffle
    // first so that meals of the same size do not always come out in the same
    // order.
    final order = [for (var i = 0; i < base.length; i++) i]..shuffle(_rng);
    order.sort((a, b) {
      final sizeA = _mealStructure[base[a].meal]!.required.length;
      final sizeB = _mealStructure[base[b].meal]!.required.length;
      return sizeB.compareTo(sizeA);
    });

    final explore = order.take(budget).toSet();
    return [
      for (var i = 0; i < base.length; i++)
        (meal: base[i].meal, role: base[i].role, explore: explore.contains(i)),
    ];
  }

  /// Adds optional servings one at a time for as long as each one pulls the
  /// day's total energy closer to the target.
  ///
  /// It runs at the day level rather than per meal because the commitment in
  /// the thesis proposal is that the **plan's** deviation stays under 10 %.
  /// One meal being far off can be compensated by another, and that is the
  /// right behaviour: people eat a light breakfast and then a large lunch.
  void _topUp({
    required Map<MealType, List<MealPlanItem>> picks,
    required Set<String> usedIds,
    required double targetKcal,
  }) {
    while (true) {
      final current = picks.values.fold<double>(0, (s, l) => s + _kcalOf(l));
      var bestGap = (current - targetKcal).abs();

      MealType? bestMeal;
      Food? bestFood;

      for (final type in MealType.values) {
        for (final role in _mealStructure[type]!.optional) {
          // Never add two dishes of the same role to one meal.
          if (picks[type]!.any((i) => i.dish!.dishRole == role)) continue;

          for (final food in candidates) {
            if (food.dishRole != role || usedIds.contains(food.id)) continue;

            final gap = (current + food.kcal - targetKcal).abs();
            if (gap < bestGap) {
              bestGap = gap;
              bestMeal = type;
              bestFood = food;
            }
          }
        }
      }

      if (bestMeal == null || bestFood == null) return;

      usedIds.add(bestFood.id);
      picks[bestMeal]!.add(
        MealPlanItem.offline(dish: bestFood, score: profile.score(bestFood)),
      );
    }
  }

  /// Greedy by **score density**.
  ///
  /// Sorting by `score / kcal` rather than by `score` alone is the crux, and
  /// it is the classic strategy for the knapsack problem: prefer the dish
  /// that delivers the most preference score **per unit of energy spent**.
  /// Sorted by score alone, a 650 kcal dish scoring 0.9 would always beat a
  /// 300 kcal dish scoring 0.8, and the meal would exhaust its allowance
  /// after a single dish.
  ///
  /// The density is additionally weighted by how well the dish fits the
  /// serving's target; without that, the lightest dish always wins because
  /// its denominator is smallest.
  Food _greedyPick({
    required List<Food> pool,
    required PreferenceProfile profile,
    required double slotTargetKcal,
  }) {
    Food? best;
    var bestValue = double.negativeInfinity;

    for (final food in pool) {
      final kcal = food.kcal.toDouble();
      if (kcal <= 0) continue;

      final density = profile.score(food) / kcal;
      final fit = slotTargetKcal <= 0
          ? 1.0
          : 1 -
                ((kcal - slotTargetKcal).abs() / slotTargetKcal).clamp(
                  0.0,
                  1.0,
                );

      final value = density * (0.35 + 0.65 * fit);
      if (value > bestValue) {
        bestValue = value;
        best = food;
      }
    }

    return best ?? pool.first;
  }

  /// Local search by swapping one dish at a time.
  ///
  /// The greedy solution can only see one serving at a time, so a meal's
  /// total can miss its target even when every individual serving is
  /// sensible. This phase tries replacing each selected dish with another in
  /// the same role, keeps whichever replacement raises the objective
  /// function, and stops when nothing improves any more.
  List<MealPlanItem> _localSearch({
    required List<MealPlanItem> selected,
    required Set<String> usedIds,
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    var current = [...selected];
    var currentScore = _objective(
      current,
      targetKcal: targetKcal,
      targetProtein: targetProtein,
      targetCarb: targetCarb,
      targetFat: targetFat,
    );

    for (var round = 0; round < localSearchRounds; round++) {
      var improved = false;

      for (var i = 0; i < current.length; i++) {
        final item = current[i];
        final inPlan = current.map((e) => e.dish!.id).toSet();

        final pool = candidates.where(
          (f) =>
              f.dishRole == item.dish!.dishRole &&
              !inPlan.contains(f.id) &&
              !usedIds.contains(f.id),
        );

        for (final swap in pool) {
          final trial = [...current];
          trial[i] = MealPlanItem.offline(
            dish: swap,
            score: profile.score(swap),
            explorationDelta: item.explorationDelta,
          );

          final trialScore = _objective(
            trial,
            targetKcal: targetKcal,
            targetProtein: targetProtein,
            targetCarb: targetCarb,
            targetFat: targetFat,
          );

          if (trialScore > currentScore) {
            current = trial;
            currentScore = trialScore;
            improved = true;
          }
        }
      }

      if (!improved) break;
    }

    return current;
  }

  /// The penalised objective function.
  ///
  /// ```text
  ///                        | kcal(S) − E |            | macroₖ(S) − Tₖ |
  /// F(S) = Σ score(i)  − λ ────────────────  −  μ  Σ ───────────────────
  ///                               E              k         Tₖ
  /// ```
  ///
  /// The nutrition constraints enter the objective function as penalty terms
  /// rather than disqualifying a violating solution outright. That lets the
  /// algorithm pass through solutions that are temporarily slightly off on
  /// its way to a better one, instead of getting stuck early on a poor but
  /// valid solution.
  double _objective(
    List<MealPlanItem> items, {
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    final totalScore = items.fold<double>(0, (sum, i) => sum + i.score);

    final kcal = _kcalOf(items);
    final energyTerm = targetKcal <= 0
        ? 0.0
        : (kcal - targetKcal).abs() / targetKcal;

    double macroTerm(double actual, double target) =>
        target <= 0 ? 0.0 : (actual - target).abs() / target;

    final protein = items.fold<double>(0, (s, i) => s + i.dish!.protein);
    final carb = items.fold<double>(0, (s, i) => s + i.dish!.carb);
    final fat = items.fold<double>(0, (s, i) => s + i.dish!.fat);

    final macroSum =
        macroTerm(protein, targetProtein) +
        macroTerm(carb, targetCarb) +
        macroTerm(fat, targetFat);

    return totalScore - energyPenalty * energyTerm - macroPenalty * macroSum;
  }

  double _kcalOf(List<MealPlanItem> items) =>
      items.fold(0, (sum, i) => sum + i.dish!.kcal.toDouble());

  /// Suggests replacements for one serving, in descending score order.
  ///
  /// Used when the user taps to swap a dish. The swap produces two training
  /// signals at once: the dropped dish takes a low label, the chosen dish a
  /// high one — see the `plan_replaced` and `plan_kept` rows of the label
  /// mapping table.
  List<Food> alternativesFor(
    MealPlanItem item, {
    required Set<String> excludeIds,
    int limit = 6,
  }) {
    final pool = candidates
        .where(
          (f) => f.dishRole == item.dish!.dishRole && !excludeIds.contains(f.id),
        )
        .toList();

    pool.sort((a, b) {
      final byScore = profile.score(b).compareTo(profile.score(a));
      if (byScore != 0) return byScore;
      // On an equal score, prefer the dish closer to the target of the
      // serving being replaced.
      final da = (a.kcal - item.dish!.kcal).abs();
      final db = (b.kcal - item.dish!.kcal).abs();
      return da.compareTo(db);
    });

    return pool.take(limit).toList();
  }
}
