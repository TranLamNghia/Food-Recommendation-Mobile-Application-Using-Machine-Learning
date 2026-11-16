/// Market section an ingredient is bought from. The shopping list is grouped
/// by this so one pass through the market covers it.
enum Aisle {
  produce('Rau củ & trái cây', '🥬'),
  meat('Thịt & trứng', '🥩'),
  seafood('Thủy hải sản', '🐟'),
  staples('Gạo, bún, mì', '🍚'),
  dairySoy('Đậu & sữa', '🥛'),
  pantry('Gia vị & đồ khô', '🧂');

  const Aisle(this.label, this.emoji);

  final String label;
  final String emoji;
}

/// One ingredient of one serving of a dish.
///
/// **Mock-only.** The database has no `ingredients` / `food_ingredients`
/// tables — `DATABASE_DESIGN.md` lists them as future work — so nothing on the
/// server can produce this yet. See `MockIngredients`.
class IngredientLine {
  const IngredientLine(this.name, this.grams, this.aisle);

  final String name;
  final double grams;
  final Aisle aisle;
}
