import 'food.dart';
import 'meal_plan.dart';

/// What the browse screen asks §7.5.1 for: its six filters, plus the safety
/// switch.
///
/// Pure Dart like every model under `data/`. Every field left `null` is a
/// filter not applied, which is what the server's own defaults mean.
class FoodQuery {
  const FoodQuery({
    this.text = '',
    this.categoryId,
    this.categoryName,
    this.meal,
    this.role,
    this.maxKcal,
    this.mark,
    this.safeOnly = true,
  });

  /// `q` — part of the dish's name.
  final String text;

  /// `categoryId` — a `food_categories.id`. Offline the mock has no ids, so
  /// the category name stands in for one.
  final String? categoryId;

  /// The chosen category's name, kept only so the chip can show it.
  final String? categoryName;

  /// `mealType` — only dishes that fit this meal.
  final MealType? meal;

  /// `dishRole`.
  final DishRole? role;

  /// `maxCalories` — a ceiling per serving.
  final double? maxKcal;

  /// `mark` — `loved` or `blocked`, the user's own marks.
  final String? mark;

  /// `excludeUnsafe`. On by default, as on the server: dishes this user may
  /// not eat stay hidden unless asked for.
  final bool safeOnly;

  /// How many of the six filters are on. The safety switch is not counted:
  /// it is on by default and is not something the user narrowed.
  int get activeFilters =>
      [categoryId, meal, role, maxKcal, mark].where((f) => f != null).length;

  /// The query with one value changed. A `null` passed through the matching
  /// `clear…` flag removes that filter; a plain `null` leaves it alone.
  FoodQuery copyWith({
    String? text,
    String? categoryId,
    String? categoryName,
    bool clearCategory = false,
    MealType? meal,
    bool clearMeal = false,
    DishRole? role,
    bool clearRole = false,
    double? maxKcal,
    bool clearMaxKcal = false,
    String? mark,
    bool clearMark = false,
    bool? safeOnly,
  }) => FoodQuery(
    text: text ?? this.text,
    categoryId: clearCategory ? null : categoryId ?? this.categoryId,
    categoryName: clearCategory ? null : categoryName ?? this.categoryName,
    meal: clearMeal ? null : meal ?? this.meal,
    role: clearRole ? null : role ?? this.role,
    maxKcal: clearMaxKcal ? null : maxKcal ?? this.maxKcal,
    mark: clearMark ? null : mark ?? this.mark,
    safeOnly: safeOnly ?? this.safeOnly,
  );

  /// The six filters off, keeping the text being searched.
  FoodQuery cleared() => FoodQuery(text: text, safeOnly: safeOnly);
}

/// [text] lower-cased with its Vietnamese marks taken off, so "pho bo"
/// finds "Phở bò" — people type without the marks on a phone keyboard.
///
/// The offline search's answer to the server's collation, which already
/// compares that way.
String foldVietnamese(String text) {
  const groups = {
    'a': 'àáạảãâầấậẩẫăằắặẳẵ',
    'e': 'èéẹẻẽêềếệểễ',
    'i': 'ìíịỉĩ',
    'o': 'òóọỏõôồốộổỗơờớợởỡ',
    'u': 'ùúụủũưừứựửữ',
    'y': 'ỳýỵỷỹ',
    'd': 'đ',
  };
  final out = StringBuffer();
  for (final ch in text.toLowerCase().split('')) {
    var plain = ch;
    for (final group in groups.entries) {
      if (group.value.contains(ch)) {
        plain = group.key;
        break;
      }
    }
    out.write(plain);
  }
  return out.toString();
}
