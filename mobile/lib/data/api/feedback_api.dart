// ONLINE: §7.8 the ratings — the strongest preference signal there is.

import 'api_client.dart';
import 'failure.dart';

/// What §7.8.1 answered: the rating as stored, and what became of the
/// preference vector.
class FeedbackResult {
  const FeedbackResult({
    required this.id,
    required this.foodId,
    required this.foodName,
    required this.rating,
    required this.createdAt,
    required this.profileUpdated,
    this.comment,
  });

  factory FeedbackResult.fromJson(Map<String, dynamic> json) => FeedbackResult(
    id: json['id'] as String,
    foodId: json['foodId'] as String,
    foodName: json['foodName'] as String? ?? '',
    rating: (json['rating'] as num).toInt(),
    comment: json['comment'] as String?,
    createdAt: DateTime.parse(json['createdAt'] as String),
    profileUpdated: json['profileUpdated'] as bool? ?? false,
  );

  final String id;
  final String foodId;

  /// Vietnamese, from `foods.name`.
  final String foodName;

  final int rating;
  final String? comment;
  final DateTime createdAt;

  /// Whether the preference vector was rebuilt from this rating before the
  /// answer came back.
  ///
  /// **`false` does not mean the rating was lost.** It is stored either way
  /// and §7.8.1 answers `201` either way; it means the ML service did not
  /// reply, so the next plan is built from the vector as it stood. The
  /// rating is in the database and the next rebuild picks it up. A screen
  /// that treated this as a failure would tell the user their rating did not
  /// count, which is the opposite of true.
  final bool profileUpdated;
}

class FeedbackApi {
  const FeedbackApi(this._client);

  final ApiClient _client;

  /// §7.8.1 — rate a dish that was eaten.
  ///
  /// **Two conditions, both required.** The dish must have been in one of
  /// this user's plans **and** be in their diary, or the answer is
  /// `409 FEEDBACK_NOT_ALLOWED`. That is deliberate: a rating carries the
  /// heaviest weight in the training set (1.0) precisely because the person
  /// ate the dish before scoring it, quite unlike a swipe that guesses from
  /// a photo. A rating of a dish nobody ate would be a swipe wearing the
  /// weight of a meal.
  ///
  /// **It locks the diary line.** From here on §7.7.3 and §7.7.4 refuse the
  /// line this rating could be the evidence for, and §7.7.1 reports
  /// `editable: false` so the app can hide those buttons. So the screen
  /// should confirm before sending — the user is giving up the ability to
  /// correct what they logged.
  ///
  /// Rating again is allowed and writes a **new** row rather than
  /// overwriting: taste changes, and both answers are kept.
  Future<FeedbackResult> rate({
    required String foodId,
    required int rating,
    String? comment,
  }) async {
    final json = await _client.post(
      '/feedbacks',
      body: {
        'foodId': foodId,
        'rating': rating,
        'comment': ?comment,
      },
    );
    return parsed(() => FeedbackResult.fromJson(json));
  }

  /// §7.8.2 — the ratings this user has sent, newest first.
  ///
  /// `GET /feedbacks`, not `/feedbacks/me`: §6 names it the first way, and
  /// the token already says whose they are.
  Future<List<FeedbackResult>> mine({
    int page = 1,
    int pageSize = 20,
  }) async {
    final json = await _client.get(
      '/feedbacks',
      query: {'page': '$page', 'pageSize': '$pageSize'},
    );
    return parsed(() => [
      for (final item in (json['items'] as List? ?? const []))
        FeedbackResult.fromJson(item as Map<String, dynamic>),
    ]);
  }
}
