import 'dart:math' as math;

import '../models/food.dart';
import '../models/swipe_action.dart';
import 'food_vector.dart';

/// The user's preference profile — a weight vector built up from their swipe
/// history.
///
/// This is Stage 1 of the cold-start strategy. Right after the taste survey
/// the system has nowhere near enough data to train a machine learning model
/// of its own — around 30 samples over a few dozen feature dimensions means
/// the model memorises those exact 30 dishes instead of learning a rule.
/// Instead, the preference is summarised into **one single vector**:
///
/// ```text
///          Σ w(aᵢ) · vᵢ
///   p_u = ──────────────       w(like) = +1 , w(neutral) = 0 , w(dislike) = −1
///          Σ | w(aᵢ) |         aᵢ = unknown → dropped from the sums
/// ```
///
/// This formula is the **Rocchio** algorithm in the vector space model
/// (Manning et al., *Introduction to Information Retrieval*, chapter 9), also
/// known as the nearest centroid classifier. At bottom it is still a linear
/// model learned from those same 30 samples; the difference is that the
/// solution is a closed form rather than an iterative optimisation — which
/// makes it stable on little data, instant to compute, and explainable to the
/// user.
class PreferenceProfile {
  const PreferenceProfile({
    required this.space,
    required this.weights,
    required this.signalCount,
  });

  /// Builds the profile from the result of one swipe session.
  ///
  /// `unknown` swipes are dropped entirely: the user is saying *I have never
  /// eaten this*, which is not a signal about taste, so including it would
  /// only add noise to the vector.
  factory PreferenceProfile.fromSwipes({
    required FoodVectorSpace space,
    required List<({Food food, SwipeAction action})> swipes,
  }) {
    final sum = List<double>.filled(space.length, 0);
    var totalAbsWeight = 0.0;
    var used = 0;

    for (final s in swipes) {
      final w = _rocchioWeight(s.action);
      if (w == null) continue;

      used++;
      totalAbsWeight += w.abs();

      final v = space.encode(s.food);
      for (var i = 0; i < sum.length; i++) {
        sum[i] += w * v[i];
      }
    }

    // A `neutral` swipe has weight 0, so it contributes 0 to the denominator.
    // If a whole session were nothing but `neutral`, the denominator would be
    // 0 — in which case the vector is left empty, every dish gets the same
    // score, and the ordering is decided by the other criteria.
    if (totalAbsWeight > 0) {
      for (var i = 0; i < sum.length; i++) {
        sum[i] /= totalAbsWeight;
      }
    }

    return PreferenceProfile(space: space, weights: sum, signalCount: used);
  }

  final FoodVectorSpace space;

  /// The preference vector `p_u`. A positive dimension means the user leans
  /// towards that feature, a negative one means they avoid it.
  final List<double> weights;

  /// How many signals went into the profile — `unknown` swipes excluded.
  final int signalCount;

  /// An empty profile, for a user who has not swiped at all (Stage 0).
  factory PreferenceProfile.empty(FoodVectorSpace space) => PreferenceProfile(
    space: space,
    weights: List<double>.filled(space.length, 0),
    signalCount: 0,
  );

  /// Empty when **every weight is 0**, not when there has been no swipe.
  ///
  /// The distinction matters: a user can **state a goal before their first
  /// swipe**. The profile then has `signalCount == 0` but non-zero weights,
  /// and it still has to be able to rank. Were `signalCount == 0` still
  /// consulted, `score` would return 0.5 for every dish and the goal just
  /// stated would be ignored completely.
  ///
  /// It does not change the behaviour of the earlier cases: an `empty`
  /// profile and an all-`neutral` session both give an all-zero vector, so
  /// they are still empty as before.
  bool get isEmpty => weights.every((w) => w == 0);

  /// Scores how much the user is likely to prefer a dish, mapped into [0, 1].
  ///
  /// The cosine similarity takes values in [-1, 1]; `(1 + cos) / 2` brings it
  /// into [0, 1] so it shares a scale with the machine learning model's score
  /// at Stage 2, which means the formula blending the two stages does not
  /// have to convert between scales.
  double score(Food food) {
    if (isEmpty) return 0.5;
    final cos = cosineSimilarity(weights, space.encode(food));
    return (1 + cos) / 2;
  }

  /// A copy of the profile with **nutrition goals the user states
  /// themselves** embedded straight into the vector.
  ///
  /// [goals] maps a nutrition column name onto a **signed** nudge: positive
  /// is "I want more" (`'fiber_g': 0.6`), negative is "I want less"
  /// (`'sodium_mg': -0.6`). A nutrient with no dimension of its own is
  /// ignored — see `FoodVectorSpace.dimensionOfNutrient`.
  ///
  /// **Why this can be embedded here instead of being handled only at Step
  /// 4.** `p_u` is just a vector; Rocchio in information retrieval has always
  /// allowed the query vector to be seeded from an explicit intent rather
  /// than learned entirely from feedback. Measured over 305 dishes, with a
  /// goal of 25 g of fibre a day and 12 taste profiles unrelated to fibre:
  ///
  /// | Where the goal goes | Fibre/day | Met | Repairs Step 4 must make | Taste score |
  /// |---|---|---|---|---|
  /// | nowhere | 18.7 g | 0/12 | 0 | 0.7452 |
  /// | `p_u` only | 23.7 g | 0/12 | 0 | 0.7410 |
  /// | Step 4 only | 28.4 g | 12/12 | 3.5 | 0.6924 |
  /// | both | 25.5 g | 12/12 | **1.7** | **0.7294** |
  ///
  /// Embedding it in `p_u` closes 79 % of the gap at almost no cost in taste,
  /// but it **does not guarantee** the goal is met (0/12) — the guarantee
  /// still has to come from Step 4. Leaving it all to Step 4 means twice as
  /// many dishes swapped and a 7.1 % drop in the taste score instead of
  /// 2.1 %.
  ///
  /// **This is a NUDGE, not an EXCLUSION.** Hard filtering on a fibre
  /// threshold of ≥ 2 g wipes out the `side_protein` role entirely (71 → 0
  /// dishes) because meat and fish have no fibre, and Step 4 cannot build a
  /// meal — exactly the failure of the earlier 600 mg per-serving sodium
  /// threshold. Hard filtering is for conditions and allergies, not for
  /// goals.
  PreferenceProfile withNutrientGoals(Map<String, double> goals) {
    if (goals.isEmpty) return this;

    final adjusted = List<double>.of(weights);
    var changed = false;
    for (final entry in goals.entries) {
      final dim = space.dimensionOfNutrient(entry.key);
      if (dim == null || entry.value == 0) continue;
      adjusted[dim] += entry.value;
      changed = true;
    }
    if (!changed) return this;

    return PreferenceProfile(
      space: space,
      weights: adjusted,
      signalCount: signalCount,
    );
  }

  /// A copy of the profile rotated slightly in a random direction.
  ///
  /// Used for the **exploration** group in the 70-30 mechanism: instead of
  /// inserting a random dish the way ε-greedy would, the system ranks by the
  /// preference vector itself after adding noise, so an exploration dish
  /// lands in the *neighbourhood* of the user's taste rather than somewhere
  /// absurd. That makes it easier for the user to accept, and when they do
  /// reject it the information gained is greater — it shows where the
  /// boundary of their taste lies.
  ///
  /// [delta] is the noise amplitude δ. Too small and the "new" dish is
  /// practically the old one; too large and it degenerates into random
  /// selection, losing every advantage.
  PreferenceProfile jittered({
    required double delta,
    required math.Random rng,
  }) {
    if (isEmpty) return this;

    // The noise is drawn from a normal distribution and then normalised to a
    // unit vector, so the rotation direction is spread evenly in all
    // directions rather than biased towards the corners of the cube — which
    // is what would happen with noise drawn uniformly per dimension.
    final noise = List<double>.generate(weights.length, (_) => _gaussian(rng));
    var norm = 0.0;
    for (final n in noise) {
      norm += n * n;
    }
    norm = math.sqrt(norm);
    if (norm == 0) return this;

    final rotated = <double>[];
    for (var i = 0; i < weights.length; i++) {
      rotated.add(weights[i] + delta * noise[i] / norm);
    }

    return PreferenceProfile(
      space: space,
      weights: rotated,
      signalCount: signalCount,
    );
  }

  /// The features the user leans towards most, in descending weight order.
  ///
  /// This is the **explainable** part of the content model: the system can
  /// tell the user outright *"this dish is suggested because you like grilled
  /// food and high-protein dishes"* instead of leaving them to guess.
  List<({String label, double weight})> topTraits({int limit = 4}) {
    final labels = space.labels;
    final entries = <({String label, double weight})>[];

    for (var i = 0; i < weights.length; i++) {
      if (weights[i] <= 0) continue;
      entries.add((label: labels[i], weight: weights[i]));
    }

    entries.sort((a, b) => b.weight.compareTo(a.weight));
    return entries.take(limit).toList();
  }
}

/// The Rocchio weight for a swipe action. `null` means drop it from the sums.
///
/// Unlike [SwipeAction.label] — which is the preference label in [0, 1] used
/// as the target for the Stage 2 machine learning model — the weight here
/// takes negative values too, because Rocchio needs to pull the vector
/// **away** from the group of disliked dishes.
double? _rocchioWeight(SwipeAction action) => switch (action) {
  SwipeAction.like => 1.0,
  SwipeAction.neutral => 0.0,
  SwipeAction.dislike => -1.0,
  SwipeAction.unknown => null,
};

/// One sample from the standard normal distribution, by the Box-Muller
/// transform.
double _gaussian(math.Random rng) {
  // `nextDouble` returns [0, 1) so it can come out as exactly 0, and log(0)
  // is infinite. Lift the lower bound by a tiny amount so the logarithm is
  // always valid.
  final u1 = math.max(rng.nextDouble(), 1e-12);
  final u2 = rng.nextDouble();
  return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2);
}
