// ONLINE: §7.5 the catalogue, §7.3 the dictionaries it filters by, and the
// dish marks that go with both.

import '../models/food_brief.dart';
import '../models/food_detail.dart';
import 'api_client.dart';
import 'failure.dart';

/// The two marks a user can leave on a dish — `user_food_marks.kind`.
///
/// Spelled out as constants rather than an enum because they travel as the
/// ENUM's own strings and come back the same way: a Dart enum would need a
/// parser in both directions for no gain, and a wrong spelling would be
/// caught by the server's `400` rather than by the compiler either way.
abstract final class FoodMark {
  /// Bookmarked — "saved to try". Affects nothing the system computes: it is
  /// a list the user keeps, not a signal. Deliberately so, since a dish the
  /// user has never eaten cannot carry a rating (§7.8.1).
  static const String loved = 'loved';

  /// "Không gợi ý món này nữa". A **hard** filter: the F1 safety layer
  /// subtracts it before anything is scored, because every ML signal is soft
  /// — a label of 0.0 lowers a score and leaves the dish eligible — so a
  /// dish the user rejected would come back the moment its role ran thin.
  static const String blocked = 'blocked';
}

/// What `PUT /foods/{id}/mark` answered: the mark as it now stands.
class FoodMarkState {
  const FoodMarkState({required this.foodId, this.kind, this.markedAt});

  factory FoodMarkState.fromJson(Map<String, dynamic> json) => FoodMarkState(
    foodId: json['foodId'] as String,
    kind: json['kind'] as String?,
    markedAt: switch (json['markedAt']) {
      final String s => DateTime.tryParse(s),
      _ => null,
    },
  );

  final String foodId;

  /// `loved` · `blocked` · `null` for cleared.
  final String? kind;

  final DateTime? markedAt;
}

class FoodApi {
  const FoodApi(this._client);

  final ApiClient _client;

  /// Sets or clears this user's mark on a dish.
  ///
  /// Idempotent: sending the same `kind` twice answers the same body twice,
  /// so a toggle may re-send rather than track what it already sent.
  ///
  /// The two marks are **exclusive** — one row per (user, food) — so
  /// bookmarking a blocked dish unblocks it. The answer is the state the
  /// server now holds, not an acknowledgement, and it is what the screen
  /// should draw from: a UI that assumed otherwise would show both controls
  /// on at once.
  ///
  /// Throws [ApiFailure] with [ApiFailure.blockWouldEmptyMeal] when blocking
  /// this dish would leave a meal with nothing to put in a role it needs.
  /// The caller has to put its switch back — the server stored nothing.
  Future<FoodMarkState> setMark(String foodId, String? kind) async {
    final json = await _client.put(
      '/foods/$foodId/mark',
      body: {'kind': kind},
    );
    return parsed(() => FoodMarkState.fromJson(json));
  }

  /// §7.5.1 — browse and search the catalogue.
  ///
  /// Every argument left out is a filter not applied, which is what the
  /// server's own defaults mean. [excludeUnsafe] has a default here too, and
  /// it is the server's: dishes this user may not eat are hidden unless asked
  /// for. A dish they merely **blocked** is not hidden by it — that flag is
  /// about health, and a blocked dish has to stay findable or the screen that
  /// unblocks it can never be reached.
  Future<FoodPage> search({
    String? query,
    String? categoryId,
    String? mealType,
    String? dishRole,
    double? maxCalories,
    String? mark,
    bool excludeUnsafe = true,
    int page = 1,
    int pageSize = defaultPageSize,
  }) async {
    final json = await _client.get(
      '/foods',
      query: {
        if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
        'categoryId': ?categoryId,
        'mealType': ?mealType,
        'dishRole': ?dishRole,
        if (maxCalories != null) 'maxCalories': '$maxCalories',
        'mark': ?mark,
        'excludeUnsafe': '$excludeUnsafe',
        'page': '$page',
        'pageSize': '$pageSize',
      },
    );
    return parsed(() => FoodPage.fromJson(json));
  }

  /// The dishes carrying [kind], for the saved-dishes screens.
  ///
  /// `excludeUnsafe: false` on purpose. The default hides dishes this user
  /// may not eat, and a dish can be bookmarked and later become unsafe — a
  /// new allergy, a tighter severity. Hiding it would leave the user with a
  /// list they cannot empty, because the row they want to remove is the row
  /// that is not there.
  ///
  /// One page, and that is enough: a user with more than a hundred
  /// bookmarked dishes out of a 318-dish catalogue has bookmarked a third of
  /// everything, and a second page would be the smaller of their problems.
  Future<List<FoodBrief>> marked(String kind) async => (await search(
    mark: kind,
    excludeUnsafe: false,
    pageSize: maxPageSize,
  )).items;

  /// §7.5.2 — one dish in full: its whole nutrition row, the medical warnings
  /// for this user, their own mark and their latest rating.
  ///
  /// `404 NOT_FOUND` for a dish this user cannot see, which includes another
  /// user's private food. `503 ML_UNAVAILABLE` when the safety verdict cannot
  /// be obtained — the screen cannot be drawn honestly without it, so the
  /// endpoint refuses rather than showing a dish with no warnings.
  Future<FoodDetail> detail(String foodId) async {
    final json = await _client.get('/foods/$foodId');
    return parsed(() => FoodDetail.fromJson(json));
  }

  /// §7.3.3 — the food groups, for the browse screen's filter.
  ///
  /// A bare array, not a page: these are dictionaries, and §7.3 answers all
  /// three of them that way.
  Future<List<FoodCategory>> categories() async {
    final rows = await _client.getList('/food-categories');
    return parsed(() => [
      for (final row in rows)
        FoodCategory.fromJson(row as Map<String, dynamic>),
    ]);
  }

  /// §7.3.2 — the tags: allergen, diet and nutrition labels.
  ///
  /// [type] narrows to one `tags.tag_type`. There is no `taste` type: the
  /// schema dropped it, because salty and sweet became measured vector
  /// dimensions computed from `sodium_mg` and `sugar_g`, and sour and bitter
  /// are published by no source this project uses.
  Future<List<FoodTag>> tags({String? type}) async {
    final rows = await _client.getList(
      '/tags',
      query: {'type': ?type},
    );
    return parsed(() => [
      for (final row in rows) FoodTag.fromJson(row as Map<String, dynamic>),
    ]);
  }

  /// §7.5.1's default page size, and its cap.
  static const int defaultPageSize = 20;
  static const int maxPageSize = 100;
}

/// One page of §7.5.1.
class FoodPage {
  const FoodPage({
    required this.items,
    required this.page,
    required this.pageSize,
    required this.totalItems,
    required this.totalPages,
  });

  factory FoodPage.fromJson(Map<String, dynamic> json) => FoodPage(
    items: [
      for (final item in (json['items'] as List? ?? const []))
        FoodBrief.fromJson(item as Map<String, dynamic>),
    ],
    page: (json['page'] as num?)?.toInt() ?? 1,
    pageSize: (json['pageSize'] as num?)?.toInt() ?? 0,
    totalItems: (json['totalItems'] as num?)?.toInt() ?? 0,
    // 0 for an empty result and not 1: there is no page to ask for.
    totalPages: (json['totalPages'] as num?)?.toInt() ?? 0,
  );

  final List<FoodBrief> items;
  final int page;
  final int pageSize;
  final int totalItems;
  final int totalPages;

  bool get hasMore => page < totalPages;
}

/// One row of `food_categories` — §7.3.3.
class FoodCategory {
  const FoodCategory({required this.id, required this.name, this.description});

  factory FoodCategory.fromJson(Map<String, dynamic> json) => FoodCategory(
    // A **CHAR(36) UUID**, not an int. §7.5.1's own parameter table says
    // `int` for `categoryId` while the JSON example beside it shows a UUID;
    // the schema is the side that is right, and this is the side that has to
    // match it.
    id: json['id'] as String,
    name: json['name'] as String,
    description: json['description'] as String?,
  );

  final String id;

  /// Already Vietnamese in the database, so it is shown as it arrives.
  final String name;
  final String? description;
}

/// One row of `tags` — §7.3.2.
class FoodTag {
  const FoodTag({
    required this.id,
    required this.nameVi,
    required this.tagType,
  });

  factory FoodTag.fromJson(Map<String, dynamic> json) => FoodTag(
    // An **int**, unlike `foods.id` and `food_categories.id`: `tags.id` is
    // `INT UNSIGNED AUTO_INCREMENT`. The two kinds of key live side by side
    // in this API, which is worth stating rather than discovering.
    id: (json['id'] as num).toInt(),
    nameVi: json['nameVi'] as String,
    tagType: json['tagType'] as String,
  );

  final int id;
  final String nameVi;

  /// `allergen` · `diet` · `nutrition` — a `tags.tag_type` code.
  final String tagType;
}
