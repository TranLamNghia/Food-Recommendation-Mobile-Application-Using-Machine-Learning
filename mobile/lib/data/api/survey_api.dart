// ONLINE: §7.4 the taste survey — the cold-start answer.

import '../models/candidate_count.dart';
import '../models/food_brief.dart';
import 'api_client.dart';
import 'failure.dart';

/// §7.4.1 — the deck to swipe, and the session it belongs to.
class SurveyDeck {
  const SurveyDeck({
    required this.sessionId,
    required this.totalItems,
    required this.minRequired,
    required this.items,
  });

  factory SurveyDeck.fromJson(Map<String, dynamic> json) => SurveyDeck(
    sessionId: json['sessionId'] as String,
    totalItems: (json['totalItems'] as num?)?.toInt() ?? 0,
    minRequired: (json['minRequired'] as num?)?.toInt() ?? 0,
    items: [
      for (final item in (json['items'] as List? ?? const []))
        FoodBrief.fromJson(item as Map<String, dynamic>),
    ],
  );

  /// The id every swipe of this session is stored under, and the one thing
  /// that makes a re-submission recognisable as the same event rather than a
  /// second survey. It must travel back in [SurveyApi.submit].
  final String sessionId;

  /// The progress bar's denominator. **Can be smaller than the size asked
  /// for**: the F1 filter may leave fewer safe dishes than that, and a bar
  /// counting to 30 over a deck of 24 would never fill.
  final int totalItems;

  /// How many **opinionated** swipes finish the survey. `unknown` ("chưa
  /// từng ăn") is stored but carries no taste, so it does not count.
  final int minRequired;

  final List<FoodBrief> items;
}

/// §7.4.2 — what the survey produced, as the closing screen needs it.
class SurveyOutcome {
  const SurveyOutcome({
    required this.sessionId,
    required this.onboardingCompletedAt,
    required this.total,
    required this.opinionated,
    required this.skipped,
    required this.droppedUnsafe,
    required this.stage,
    required this.nSignals,
    this.topLikedCategories = const [],
    this.topLikedTastes = const [],
  });

  factory SurveyOutcome.fromJson(Map<String, dynamic> json) {
    final recorded = json['recorded'] as Map<String, dynamic>? ?? const {};
    final profile =
        json['preferenceProfile'] as Map<String, dynamic>? ?? const {};
    final taste = json['tasteSummary'] as Map<String, dynamic>? ?? const {};
    return SurveyOutcome(
      sessionId: json['sessionId'] as String,
      // Not nullable: an answer without it means the account was not
      // stamped, and the whole point of this call is that it was.
      onboardingCompletedAt:
          DateTime.parse(json['onboardingCompletedAt'] as String),
      total: (recorded['total'] as num?)?.toInt() ?? 0,
      opinionated: (recorded['opinionated'] as num?)?.toInt() ?? 0,
      skipped: (recorded['skipped'] as num?)?.toInt() ?? 0,
      droppedUnsafe: (recorded['droppedUnsafe'] as num?)?.toInt() ?? 0,
      stage: profile['stage'] as String? ?? 'cold',
      nSignals: (profile['nSignals'] as num?)?.toInt() ?? 0,
      topLikedCategories: [
        for (final c in (taste['topLikedCategories'] as List? ?? const []))
          c.toString(),
      ],
      topLikedTastes: [
        for (final t in (taste['topLikedTastes'] as List? ?? const []))
          t.toString(),
      ],
    );
  }

  final String sessionId;

  /// The stamp on `users.onboarding_completed_at`. **This is what ends the
  /// onboarding flow**: the app asks `GET /auth/me` for it on every launch to
  /// decide which screen to open on, so until this call returns, a user who
  /// has swiped thirty cards is still a user who has not finished.
  ///
  /// Only its presence is meaningful. The column is a `DATETIME` with no
  /// fractional seconds, so what this answer carries is the value before
  /// MySQL rounded it: `GET /auth/me` can report a time up to half a second
  /// away. Nothing in the app compares the two, and nothing should.
  final DateTime onboardingCompletedAt;

  /// Rows written to `interactions`.
  final int total;

  /// `like`, `dislike` and `neutral` — the ones that carry taste.
  final int opinionated;

  /// `unknown` — stored, and left out of the vector.
  final int skipped;

  /// Swipes on a dish this user may not eat.
  ///
  /// The swipes are stored as the user made them, because the table is a
  /// record of what happened; the F1 filter is applied where it lives, when
  /// the vector is built. So [total] can exceed [nSignals], and without this
  /// number that gap would read as a bug.
  final int droppedUnsafe;

  /// `cold` · `content` · `hybrid` · `ml` — §4.5's stages.
  final String stage;

  /// Usable signals behind the vector: after F1, and after `unknown`.
  final int nSignals;

  /// `food_categories.name`, Vietnamese, most-liked first.
  final List<String> topLikedCategories;

  /// `salty` · `sweet` · `fatty` — stable codes, translated by the app.
  final List<String> topLikedTastes;
}

/// One swipe on its way to the server: §7.4.2's `swipes[]`.
///
/// An id and a code, which is all the request holds. The app does **not**
/// send the dish's nutrition or its own opinion of the vector: Rocchio runs
/// in the ML service, and a second implementation of it here would be the one
/// nothing compares.
typedef SurveySwipe = ({String foodId, String action});

class SurveyApi {
  const SurveyApi(this._client);

  final ApiClient _client;

  /// §7.4.1. `409 ONBOARDING_ALREADY_COMPLETED` when the survey is done,
  /// which is also how the app learns it is on the wrong screen.
  Future<SurveyDeck> deck({int size = defaultSize}) async {
    final json = await _client.get(
      '/onboarding/survey',
      query: {'size': '$size'},
    );
    return parsed(() => SurveyDeck.fromJson(json));
  }

  /// §7.4.2. Sends the whole session in one request, as the specification
  /// designs it: there is no per-swipe endpoint, because the app already
  /// holds that state and the session is one event in the data.
  ///
  /// **Safe to retry, but read what the retry can answer.** Re-sending the
  /// same [sessionId] replaces that session's rows rather than adding a
  /// second copy — *while the account is still unstamped*. The server checks
  /// `onboarding_completed_at` **before** it looks at the session id, so once
  /// the stamp exists every submission is refused, the same session
  /// included.
  ///
  /// That matters for the one failure the retry is for: the request arrives,
  /// the account is stamped, and the answer is lost on the way back. Sending
  /// the same body again then gives `409 ONBOARDING_ALREADY_COMPLETED`, which
  /// the caller has to read as **success** — the survey is done. Treating it
  /// as an error would leave the user on a screen they can never leave,
  /// which is the whole defect this call was added to fix.
  ///
  /// `422 ONBOARDING_INSUFFICIENT` when too few swipes carried an opinion;
  /// `404 NOT_FOUND` for a food id that is not in the catalogue, which a deck
  /// cached on the device past a catalogue change can produce.
  Future<SurveyOutcome> submit({
    required String sessionId,
    required List<SurveySwipe> swipes,
  }) async {
    final json = await _client.post(
      '/onboarding/survey',
      body: {
        'sessionId': sessionId,
        'swipes': [
          for (final s in swipes) {'foodId': s.foodId, 'action': s.action},
        ],
      },
    );
    return parsed(() => SurveyOutcome.fromJson(json));
  }

  /// §7.4.3 — how much of the catalogue the declarations so far leave.
  ///
  /// [conditions] is what the user has ticked **on screen**, not what is
  /// stored for them, and an empty list therefore means **no restriction at
  /// all**. That distinction is the whole endpoint: answering an empty list
  /// with "whatever this account has on file" would show a filtered number
  /// as if it were the catalogue, on the very first view of the screen.
  ///
  /// Only **hard** rules narrow this count. A soft rule lowers a dish's
  /// score and leaves it eligible, so counting one here would promise the
  /// user a dish is gone while the plan can still contain it.
  Future<CandidateCount> countCandidates(
    List<({int conditionId, String severity})> conditions,
  ) async {
    final json = await _client.post(
      '/onboarding/candidates/count',
      body: {
        'conditions': [
          for (final c in conditions)
            {'conditionId': c.conditionId, 'severity': c.severity},
        ],
      },
    );
    return parsed(() => CandidateCount.fromJson(json));
  }

  /// §7.4.1's default. The range is 20–50 and the server checks it, but the
  /// app has no reason to ask for anything else: the number is a trade
  /// between how long the user swipes and how much direction Rocchio gets,
  /// and it was settled at 30 in the specification.
  static const int defaultSize = 30;
}
