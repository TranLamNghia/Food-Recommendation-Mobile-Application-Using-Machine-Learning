/// What the user types to add a dish of their own — §7.5.3.
///
/// Every nutrient but the energy is optional, and an optional one left blank
/// is sent as `null`, never as `0`. `0` is a claim ("this dish has none"),
/// and the safety filter believes claims: a gout patient would be offered a
/// dish typed with `purineMg: 0` because nobody knew the figure.
library;

class OwnDishDraft {
  const OwnDishDraft({
    required this.name,
    required this.categoryId,
    required this.dishRole,
    required this.servingSizeG,
    required this.kcal,
    this.spiceLevel = 0,
    this.proteinG,
    this.carbsG,
    this.fatG,
    this.fiberG,
    this.sugarG,
    this.sodiumMg,
    this.purineMg,
    this.tagIds = const [],
  });

  final String name;
  final String categoryId;

  /// A `foods.dish_role` code.
  final String dishRole;

  final int servingSizeG;
  final double kcal;
  final int spiceLevel;
  final double? proteinG;
  final double? carbsG;
  final double? fatG;
  final double? fiberG;
  final double? sugarG;
  final double? sodiumMg;
  final double? purineMg;

  /// Allergen and diet tags, so the F1 filter can treat the dish like any
  /// catalogue one.
  final List<int> tagIds;

  Map<String, Object?> toJson() => {
    'name': name.trim(),
    'categoryId': categoryId,
    'dishRole': dishRole,
    'servingSizeG': servingSizeG,
    'spiceLevel': spiceLevel,
    'nutrition': {
      'calories': kcal,
      'proteinG': proteinG,
      'carbsG': carbsG,
      'fatG': fatG,
      'fiberG': fiberG,
      'sugarG': sugarG,
      'sodiumMg': sodiumMg,
      'purineMg': purineMg,
    },
    if (tagIds.isNotEmpty) 'tagIds': tagIds,
  };
}
