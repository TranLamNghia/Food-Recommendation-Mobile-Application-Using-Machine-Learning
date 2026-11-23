// ONLINE: §7.5 the catalogue, and the dish marks that go with it.

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

  /// The ids of the dishes carrying [kind], for the saved-dishes screens.
  ///
  /// `excludeUnsafe=false` on purpose. The default hides dishes this user may
  /// not eat, and a dish can be bookmarked and later become unsafe — a new
  /// allergy, a tighter severity. Hiding it would leave the user with a list
  /// they cannot empty, because the row they want to remove is the row that
  /// is not there.
  Future<List<String>> markedIds(String kind) async {
    final json = await _client.get(
      '/foods',
      query: {
        'mark': kind,
        'excludeUnsafe': 'false',
        'pageSize': '$_pageSize',
      },
    );
    return parsed(() => [
      for (final item in json['items'] as List) (item as Map)['id'] as String,
    ]);
  }

  /// §7.5.1's cap. One page is enough for both lists: a user with more than
  /// a hundred bookmarked dishes out of a 318-dish catalogue has bookmarked
  /// a third of everything, and a second page would be the smaller problem.
  static const int _pageSize = 100;
}
