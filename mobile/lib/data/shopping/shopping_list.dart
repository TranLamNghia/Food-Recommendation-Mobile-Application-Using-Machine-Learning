import '../mock/mock_ingredients.dart';
import '../models/ingredient.dart';
import '../models/meal_plan.dart';

/// One row of the shopping list: an ingredient summed over every dish that
/// needs it.
class ShoppingLine {
  ShoppingLine({required this.name, required this.aisle});

  final String name;
  final Aisle aisle;

  double grams = 0;

  /// Names of the dishes this ingredient goes into, for the "used in" hint.
  final Set<String> dishes = {};
}

/// Adds up the ingredients of every dish still **planned** in [plans].
///
/// Eaten, skipped and replaced items are left out: the first is already
/// cooked, the other two will never be. Rows come back grouped by aisle (in
/// enum order), then alphabetically.
List<ShoppingLine> buildShoppingList(Iterable<DailyPlan> plans) {
  final lines = <String, ShoppingLine>{};

  for (final plan in plans) {
    for (final item in plan.allItems) {
      if (item.status != MealItemStatus.planned) continue;
      for (final ing in MockIngredients.of(item.food.id)) {
        final line = lines.putIfAbsent(
          ing.name,
          () => ShoppingLine(name: ing.name, aisle: ing.aisle),
        );
        line.grams += ing.grams;
        line.dishes.add(item.food.name);
      }
    }
  }

  return lines.values.toList()..sort((a, b) {
    final byAisle = a.aisle.index.compareTo(b.aisle.index);
    return byAisle != 0 ? byAisle : a.name.compareTo(b.name);
  });
}
