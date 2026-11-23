// OFFLINE: explains a local score in words; the server sends its own.
import '../models/food.dart';
import 'food_vector.dart';
import 'preference_profile.dart';

/// Why **this dish** matches the user's taste — in sentences, not numbers.
///
/// Different from [PreferenceProfile.topTraits], which says what the user
/// likes *in general*. Here it is each dimension's contribution to the score
/// of **one specific dish**: `p_u[i] · vᵢ[i]`, that is, its own term in the
/// numerator of the cosine.
///
/// Mirrors `contributions` in `ml/serve.py`, and uses the same clause table,
/// so the sentence shown on the phone matches the one the server produces.
///
/// ## Why the number was dropped
///
/// An earlier version returned `"Tỷ lệ đạm (+0.182)"`. The dimension label is
/// readable Vietnamese, but `+0.182` is meaningless to a user: no unit, not a
/// percentage, and its magnitude depends on both the profile and the dish.
/// **The ordering is the information.**
///
/// ## Why the sentence is always "a lot of X" and never "little X"
///
/// Every dimension of a dish vector lies in [0, 1] —
/// `food_vector_parity_test` asserts that. So `v[i] ≥ 0` always holds, and
/// the sign of `p_u[i]·v[i]` is just the sign of `p_u[i]`. A **positive**
/// contribution therefore means the dishes this person likes have a high
/// value on that dimension; leaning towards low values gives a negative
/// contribution, and negative contributions are excluded from this list.
///
/// Note on language: the keys of [clauseByDimension] are the dimension
/// labels, which are data shared with `ml/features.py`'s `FIXED_LABELS`, and
/// the clauses are text shown on screen — so both stay in Vietnamese.
class MatchReason {
  const MatchReason({
    required this.dimension,
    required this.value,
    required this.ratio,
    required this.sentence,
  });

  /// The dimension's technical label, kept for debugging — **not** shown to
  /// the user.
  final String dimension;

  /// `p_u[i] · vᵢ[i]`. Kept for checking and debugging, not displayed.
  final double value;

  /// Relative to the largest contribution **of this same dish**, in (0, 1].
  ///
  /// This is what gets drawn as a comparison bar, but it only states the
  /// ordering WITHIN one dish; it does NOT say how strongly that dish matches
  /// the user's taste. A dish the user swiped `dislike` still produces three
  /// ratios of 100 % / 91 % / 88 % while the absolute contributions sit
  /// around +0.009: normalising against the dish's own peak means even a very
  /// weak match comes out as three nearly full bars.
  ///
  /// So the interface **must** show the overall match score
  /// ([PreferenceProfile.score]) alongside. Drawing these bars on their own
  /// tells the user that every dish matches equally strongly.
  final double ratio;

  /// The sentence for the user. `null` when this dimension has no clause yet
  /// — the interface drops that line rather than showing a technical label.
  final String? sentence;
}

/// Dimension label → the clause describing a dish, used to build the sentence
/// "Bạn thường chọn món …".
///
/// A missing label here does **not** blow the function up — the interface
/// still works, that dimension simply has no sentence. But
/// [dimensionsWithoutSentence] reports it and the test suite calls that, so a
/// newly added dimension with a forgotten clause fails a check immediately
/// rather than quietly showing the user a technical label.
const Map<String, String> clauseByDimension = {
  'Tỷ lệ đạm': 'nhiều đạm',
  'Tỷ lệ bột đường': 'nhiều bột đường',
  'Tỷ lệ béo': 'nhiều chất béo',
  'Năng lượng': 'nhiều năng lượng',
  'Vị ngọt': 'có vị ngọt',
  'Vị mặn': 'đậm vị mặn',
  'Chất xơ': 'nhiều chất xơ',
  'Mức cay': 'có vị cay',
};

/// The prefix [FoodVectorSpace.labels] puts on the one-hot food-group
/// dimension.
const String categoryPrefix = 'Nhóm: ';

String? sentenceForDimension(String label) {
  if (label.startsWith(categoryPrefix)) {
    return 'Bạn thích nhóm ${label.substring(categoryPrefix.length)}';
  }
  final clause = clauseByDimension[label];
  return clause == null ? null : 'Bạn thường chọn món $clause';
}

/// The dimensions that have no sentence for the user yet.
///
/// The food-group dimension always has one, because it is built from the
/// group's name, so this list only holds fixed dimensions forgotten in
/// [clauseByDimension].
List<String> dimensionsWithoutSentence(FoodVectorSpace space) => [
  for (final label in space.labels)
    if (sentenceForDimension(label) == null) label,
];

/// The `limit` dimensions contributing most to [food]'s taste-match score.
///
/// Only **positive** dimensions are listed: a negative one means the dish
/// lost score there, which is not a reason it was recommended. An empty
/// profile returns an empty list — there is no basis for saying what this
/// person likes.
List<MatchReason> matchReasons(
  PreferenceProfile profile,
  Food food, {
  int limit = 3,
}) {
  if (profile.isEmpty) return const [];

  final space = profile.space;
  final vector = space.encode(food);
  final labels = space.labels;

  final contributions = <({String label, double value})>[];
  for (var i = 0; i < vector.length; i++) {
    final v = profile.weights[i] * vector[i];
    if (v > 0) contributions.add((label: labels[i], value: v));
  }
  if (contributions.isEmpty) return const [];

  contributions.sort((a, b) => b.value.compareTo(a.value));
  final top = contributions.take(limit).toList();
  final largest = top.first.value;

  return [
    for (final c in top)
      MatchReason(
        dimension: c.label,
        value: c.value,
        ratio: c.value / largest,
        sentence: sentenceForDimension(c.label),
      ),
  ];
}

/// The explanation sentences, with the clause-less dimensions dropped. For
/// the interface.
List<String> matchSentences(
  PreferenceProfile profile,
  Food food, {
  int limit = 3,
}) => [
  for (final r in matchReasons(profile, food, limit: limit))
    if (r.sentence != null) r.sentence!,
];
