import 'food.dart';
import 'food_brief.dart';
import 'food_detail.dart';

/// Turns the offline mode's `Food` into the shapes the screens read.
///
/// The screens were rewritten to read what the server sends — [FoodBrief] for
/// a list row, [FoodDetail] for one dish in full — so that there is **one**
/// path through each screen rather than one per mode. These two conversions
/// are what keeps the offline mode working through that single path: the mock
/// dishes come in here and come out looking like answers.
///
/// It goes the one way only. Nothing converts a server answer into a `Food`,
/// and that is deliberate: `Food` is the feature vector the Dart copies of
/// steps 1 and 4 compute from, and the only answer carrying a whole nutrition
/// row is §7.5.2, one dish at a time. Building a `Food` out of a list row
/// would mean inventing the numbers it does not carry.
extension FoodAsBrief on Food {
  /// A mock dish as a list row.
  ///
  /// `imageAsset` comes with it: the offline deck's thirty dishes each carry
  /// a placeholder photo from the Figma design, and those are what actually
  /// show — the role's gradient is only the floor underneath.
  FoodBrief get brief => FoodBrief(
    id: id,
    name: name,
    category: category,
    dishRole: dishRole,
    spiceLevel: spiceLevel,
    kcal: kcal.toDouble(),
    servingSizeG: servingSizeG,
    imageAsset: imageAsset,
    tags: tags,
  );

  /// A mock dish as the detail screen's subject.
  ///
  /// The micronutrients `Food` does not carry stay **null**, not 0: the
  /// offline mode knows a dish's energy, macros, sodium, sugar, fibre and
  /// sometimes purine, and it does not know its calcium. `null` is how the
  /// screen says "chưa có số liệu" instead of printing a reassuring zero.
  ///
  /// `warnings` is empty here, and that is not the same as "safe": offline,
  /// the F1 verdict comes from `rules/dish_screening.dart`, the Dart copy of
  /// the filter, which the screen asks separately. Filling this list from it
  /// would put the same verdict in two places.
  FoodDetail get detail => FoodDetail(
    brief: brief,
    nutrition: DishNutrition(
      servingSizeG: servingSizeG,
      caloriesKcal: kcal.toDouble(),
      proteinG: protein,
      carbsG: carb,
      fatG: fat,
      fiberG: fiber,
      sugarG: sugar,
      sodiumMg: sodium,
      purineMg: purine,
    ),
  );
}
