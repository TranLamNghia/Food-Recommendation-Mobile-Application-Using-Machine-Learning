import 'food.dart';
import 'meal_plan.dart';

/// One row of the food diary — the `food_diary` table.
///
/// The diary records what the user **actually ate**, not what the system
/// recommended. The gap between the two is the most valuable data there is:
/// the distance between the suggested plan and the real meal tells you
/// whether the recommendations are close or not.
///
/// This table holds **no** foreign key to `meal_plan_items`. A user can eat
/// something entirely outside the plan, and a dish from the plan can be eaten
/// at a different meal from the one it was scheduled for. Plan adherence is
/// therefore computed by joining on the natural key (date, meal, dish) rather
/// than on a foreign key — see `DATABASE_DESIGN.md` §6.2.
class DiaryEntry {
  DiaryEntry({
    required this.food,
    required this.meal,
    required this.ateAt,
    this.portion = 1.0,
    this.rating,
  });

  final Food food;
  final MealType meal;
  final DateTime ateAt;

  /// How many servings were eaten. 1.0 is one standard portion; 0.5 is half.
  final double portion;

  /// The rating given after eating, from 1 to 5 stars. `null` means not rated
  /// yet.
  ///
  /// This is the **strongest** signal source in the label mapping table, with
  /// a sample weight of 1.0 — because the user actually ate the dish before
  /// scoring it, quite unlike a swipe that only guesses from a photo.
  int? rating;

  /// When the user took the entry back, or `null` while it stands. An undone
  /// entry stays in the log but counts towards nothing.
  DateTime? undoneAt;

  bool get isUndone => undoneAt != null;

  double get kcal => food.kcal * portion;
  double get protein => food.protein * portion;
  double get carb => food.carb * portion;
  double get fat => food.fat * portion;

  /// The preference label mapped onto [0, 1] for the training set.
  ///
  /// With a star rating, 1–5 stars map linearly onto 0.00–1.00. Without one,
  /// the very fact of having eaten the dish is already a positive signal and
  /// takes the label 0.8 — below 5 stars but above neutral.
  double get trainingLabel => rating == null ? 0.8 : (rating! - 1) / 4;

  /// The matching sample weight — a star rating is more trustworthy than an
  /// inference drawn from behaviour.
  double get sampleWeight => rating == null ? 0.9 : 1.0;
}
