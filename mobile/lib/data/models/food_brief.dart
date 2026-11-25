/// A dish as a **list** carries it: a name, a group, a figure, a role.
///
/// ## Why this exists next to `Food`
///
/// `Food` is the **feature vector**. Every one of its nutrition fields is
/// required because `FoodVectorSpace`, `MenuBuilder` and `DayBudget` compute
/// from them, and `null` is never 0 in this project — a missing measurement
/// excludes a dish rather than counting as zero.
///
/// The server's list answers carry none of that. §7.4.1's deck and §7.5.1's
/// browse rows hold id, name, category, role, spice, energy and serving
/// weight, because that is what a row shows; the full nutrition arrives only
/// from §7.5.2, one dish at a time. Pouring a list row into `Food` would mean
/// inventing zeros for protein, sodium and fibre — numbers the offline
/// algorithm would then compute with, and the parity checks would start
/// disagreeing with Python over dishes nobody had measured.
///
/// So the two are kept apart: this one is what the deck, the browse list and
/// the saved-dish lists are built from, in **both** modes — `Food.brief`
/// turns a mock dish into one — and `Food` stays what the arithmetic reads.
///
/// ## Why there is no colour in here
///
/// Nothing in this file imports Flutter, and that is load-bearing:
/// `tool/smoke_api.dart` drives the API layer from the command line with
/// `dart run`, which compiles plain Dart and cannot see the Flutter engine.
/// One `Color` field here took the whole data layer out of its reach. The
/// look a card is drawn with lives in `core/dish_look.dart` instead, as an
/// extension — which is where presentation belongs anyway.
class FoodBrief {
  const FoodBrief({
    required this.id,
    required this.name,
    required this.category,
    required this.dishRole,
    required this.spiceLevel,
    required this.kcal,
    required this.servingSizeG,
    this.imageUrl,
    this.imageAsset,
    this.tags = const [],
    this.isSafeForUser = true,
    this.mark,
  });

  /// One row of §7.5.1's `items[]`, or one card of §7.4.1's deck. The two
  /// shapes differ only in the fields the browse list adds, which are absent
  /// rather than guessed at when they do not come.
  factory FoodBrief.fromJson(Map<String, dynamic> json) => FoodBrief(
    id: json['id'] as String,
    name: json['name'] as String,
    category: json['categoryName'] as String? ?? '',
    dishRole: json['dishRole'] as String? ?? '',
    spiceLevel: (json['spiceLevel'] as num?)?.toInt() ?? 0,
    kcal: (json['caloriesKcal'] as num?)?.toDouble() ?? 0,
    servingSizeG: (json['servingSizeG'] as num?)?.toDouble() ?? 0,
    imageUrl: json['imageUrl'] as String?,
    tags: [for (final t in (json['tags'] as List? ?? const [])) t.toString()],
    // §7.5.1 sends both; §7.4.1's deck sends neither, and a deck card is
    // safe by construction — the F1 filter is what chose it.
    isSafeForUser: json['isSafeForUser'] as bool? ?? true,
    mark: json['mark'] as String?,
  );

  final String id;
  final String name;

  /// `food_categories.name` — already Vietnamese, shown as it arrives.
  final String category;

  /// A `foods.dish_role` code online (`main`, `soup`, …) and a Vietnamese
  /// label offline, because `MockFoods` stores the label and the Dart copy of
  /// step 4 matches on it. `DishRole.labelOf` renders both: it falls back to
  /// the raw string, which for the mock is the label already.
  final String dishRole;

  final int spiceLevel;

  /// Energy per serving. A `double` and not an `int` as in `Food`: it comes
  /// off a `DECIMAL` column, and rounding it on the way in would make a list
  /// disagree with the detail screen beside it.
  final double kcal;

  final double servingSizeG;

  /// `foods.image_url`. **Null for all 318 rows** — there is no photo set for
  /// Vietnamese dishes in this project, and producing one is not a thesis
  /// task. So a server-fed card always falls back to its role's look.
  final String? imageUrl;

  /// The placeholder photo a mock dish carries, from the Figma design. The
  /// offline mode's 30 dishes all have one.
  final String? imageAsset;

  final List<String> tags;

  /// Whether this user may **eat** it. A dish they blocked is still `true`:
  /// §7.5.1's field means health, not whether it gets suggested.
  final bool isSafeForUser;

  /// `loved` · `blocked` · `null` — `user_food_marks.kind`.
  final String? mark;

  bool get isLoved => mark == 'loved';
  bool get isBlocked => mark == 'blocked';

  FoodBrief copyWith({String? mark, bool? isSafeForUser}) => FoodBrief(
    id: id,
    name: name,
    category: category,
    dishRole: dishRole,
    spiceLevel: spiceLevel,
    kcal: kcal,
    servingSizeG: servingSizeG,
    imageUrl: imageUrl,
    imageAsset: imageAsset,
    tags: tags,
    isSafeForUser: isSafeForUser ?? this.isSafeForUser,
    mark: mark,
  );
}
