import 'diary_day.dart';
import 'food.dart';
import 'food_adapters.dart';
import 'food_brief.dart';
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
    this.dish,
    this.id,
    this.portion = 1.0,
    this.rating,
    this.kcalOverride,
    this.fromMealPlan = false,
    this.editable = true,
  });

  /// A line the offline mode wrote, which has the whole dish in hand.
  DiaryEntry.offline({
    required Food dish,
    required MealType meal,
    required DateTime ateAt,
    double portion = 1.0,
    int? rating,
    bool fromMealPlan = false,
  }) : this(
         food: dish.brief,
         dish: dish,
         meal: meal,
         ateAt: ateAt,
         portion: portion,
         rating: rating,
         fromMealPlan: fromMealPlan,
       );

  /// One line of §7.7.1, eaten [on] the day it was listed under.
  ///
  /// The day comes from the `days[]` it sat in, not from `createdAt`: a
  /// lunch logged this morning for yesterday was **eaten** yesterday, and
  /// the diary has to show it there. `createdAt` only lends the time of day.
  factory DiaryEntry.fromLine(DiaryLine line, {DateTime? on}) => DiaryEntry(
    id: line.id,
    food: line.food,
    meal: MealType.values.firstWhere(
      (m) => m.code == line.mealType,
      orElse: () => MealType.snack,
    ),
    ateAt: on == null
        ? line.createdAt
        : DateTime(
            on.year,
            on.month,
            on.day,
            line.createdAt.toLocal().hour,
            line.createdAt.toLocal().minute,
          ),
    // The portion is already applied to the energy the server sent, so it is
    // not reapplied here: `portion` stays 1 and [kcalOverride] carries the
    // figure. Multiplying a server figure by a portion this side guessed
    // would double-count it.
    kcalOverride: line.actualCaloriesKcal,
    rating: line.hasFeedback ? _ratedSentinel : null,
    fromMealPlan: line.fromMealPlan,
    editable: line.editable,
  );

  /// `food_diary.id`. `null` on an offline line, which is stored nowhere.
  final String? id;

  /// What a row draws. A **brief**: §7.7.1 sends the same card the plan
  /// does, and no nutrition beyond the energy of the line.
  final FoodBrief food;

  /// The whole dish — **offline only**, and what the day's allowance
  /// arithmetic reads.
  final Food? dish;

  final MealType meal;
  final DateTime ateAt;

  /// The energy of this line as the server computed it, at the portion
  /// actually eaten. `null` offline, where it is computed from [dish].
  final double? kcalOverride;

  /// Whether this dish was in the user's own plan for this day and meal.
  ///
  /// It words the delete confirmation: `true` is "I have not eaten it after
  /// all" and the serving goes back on the plate; `false` is removing a line
  /// of a health log. It does **not** choose the behaviour — §7.7.4 decides
  /// that from the data, so two clients cannot disagree.
  final bool fromMealPlan;

  /// `false` once a rating exists that this line could be the evidence for,
  /// after which §7.7.3 and §7.7.4 both refuse it. The app hides the buttons
  /// rather than letting the user press one and read an error.
  final bool editable;

  /// Stands for "rated" when §7.7.1 says so without saying with what — the
  /// stars themselves come from §7.5.2's `myFeedback`. Not a real score, and
  /// never shown as one.
  static const int _ratedSentinel = -1;

  /// Whether the user has rated this dish, whatever the stars were.
  bool get hasRating => rating != null;

  /// The stars, when they are known. `null` both for unrated and for a line
  /// that only reported *that* it was rated.
  int? get stars => rating == _ratedSentinel ? null : rating;

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

  /// Energy of this line. The server's figure when there is one, because it
  /// was computed from the whole nutrition row at the portion eaten.
  double get kcal => kcalOverride ?? (dish?.kcal ?? 0) * portion;

  /// Grams eaten on this line. Online the brief's serving weight is the
  /// LINE's — `DiaryLine.fromJson` puts it there — so it is already the
  /// portion actually eaten.
  double get grams =>
      dish != null ? dish!.servingSizeG * portion : food.servingSizeG;

  /// One standard serving of this dish in grams, or `null` when it cannot
  /// be known.
  ///
  /// Online §7.7.1 sends no portion, but it does send the brief's energy per
  /// standard serving next to the line's own energy, and their ratio is the
  /// portion.
  double? get servingGrams {
    if (dish != null) return dish!.servingSizeG;
    if (food.kcal <= 0 || kcal <= 0 || grams <= 0) return null;
    return grams * food.kcal / kcal;
  }

  /// Energy per gram of this dish, for previewing a corrected portion before
  /// it is sent. `null` with nothing to divide by.
  double? get kcalPerGram => grams <= 0 ? null : kcal / grams;

  /// The macros, or `null` when this line carries no whole dish — §7.7.1
  /// sends none, and §7.7.5 is where the day's macros come from instead.
  double? get protein => dish == null ? null : dish!.protein * portion;
  double? get carb => dish == null ? null : dish!.carb * portion;
  double? get fat => dish == null ? null : dish!.fat * portion;

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
