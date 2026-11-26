// ONLINE: §7.1 — the account.

import '../models/health_profile.dart';
import 'api_client.dart';
import 'failure.dart';

/// The account as the server describes it — §7.1.1's `user` and §7.1.4.
class Account {
  const Account({
    required this.id,
    required this.email,
    required this.displayName,
    this.avatarUrl,
    this.onboardingCompletedAt,
    this.hasHealthProfile,
    this.preferenceStage,
  });

  factory Account.fromJson(Map<String, dynamic> json) => Account(
    id: json['id'] as String,
    email: json['email'] as String,
    displayName: json['displayName'] as String? ?? '',
    avatarUrl: json['avatarUrl'] as String?,
    onboardingCompletedAt: _parseDate(json['onboardingCompletedAt']),
    hasHealthProfile: json['hasHealthProfile'] as bool?,
    preferenceStage: json['preferenceStage'] as String?,
  );

  final String id;
  final String email;
  final String displayName;
  final String? avatarUrl;

  /// `null` until the taste survey of §7.4.2 has been accepted. It is what
  /// decides whether the app opens on the survey or on the plan.
  final DateTime? onboardingCompletedAt;

  /// Only §7.1.4 sends these two; §7.1.1 and §7.1.2 leave them out.
  final bool? hasHealthProfile;

  /// `cold` · `content` · `hybrid` · `ml` — §4.5's stages.
  final String? preferenceStage;

  bool get hasFinishedOnboarding => onboardingCompletedAt != null;

  static DateTime? _parseDate(Object? value) =>
      value is String ? DateTime.tryParse(value) : null;
}

/// A successful sign-in or registration — §7.1.1 and §7.1.2.
class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.account,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
    accessToken: json['accessToken'] as String,
    refreshToken: json['refreshToken'] as String,
    account: Account.fromJson(json['user'] as Map<String, dynamic>),
  );

  final String accessToken;
  final String refreshToken;
  final Account account;
}

class AuthApi {
  const AuthApi(this._client);

  final ApiClient _client;

  /// §7.1.1. `409 EMAIL_ALREADY_EXISTS` when the address is taken.
  Future<AuthSession> register({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final json = await _client.post(
      '/auth/register',
      authenticated: false,
      body: {
        'email': email.trim(),
        'password': password,
        'displayName': displayName.trim(),
      },
    );
    return _store(parsed(() => AuthSession.fromJson(json)));
  }

  /// §7.1.2. `401 INVALID_CREDENTIALS`, or `403 ACCOUNT_DISABLED`.
  Future<AuthSession> logIn({
    required String email,
    required String password,
  }) async {
    final json = await _client.post(
      '/auth/login',
      authenticated: false,
      body: {'email': email.trim(), 'password': password},
    );
    return _store(parsed(() => AuthSession.fromJson(json)));
  }

  /// §7.1.4 — and the question the app actually asks it: which screen to
  /// open on.
  Future<Account> me() async {
    final json = await _client.get('/auth/me');
    return parsed(() => Account.fromJson(json));
  }

  /// Renames the account. Answers with the same body as [me], so the
  /// caller sees the result without a second call.
  ///
  /// Not in §6's list of seven: the specification has no endpoint that edits
  /// the account's own details, and the app has a screen that does.
  Future<Account> updateDisplayName(String displayName) async {
    final json = await _client.put(
      '/auth/me',
      body: {'displayName': displayName.trim()},
    );
    return parsed(() => Account.fromJson(json));
  }

  /// §7.1.5 — mail a reset code to [email].
  ///
  /// Always `202` when the address is well formed, registered or not: the
  /// answer must not tell anyone which addresses have accounts. So there is
  /// nothing to return, and the screen words its confirmation as an "if".
  /// `429 RATE_LIMITED` comes from too many requests from one network.
  Future<void> forgotPassword(String email) => _client.post(
    '/auth/forgot-password',
    authenticated: false,
    body: {'email': email.trim()},
  );

  /// §7.1.6 — set a new password with the code from the mail.
  ///
  /// `400 RESET_TOKEN_INVALID` for a code that is wrong, expired or already
  /// used. Success ends every session of the account, so nothing is stored
  /// here: the user logs in with the new password next.
  Future<void> resetPassword({
    required String token,
    required String newPassword,
  }) => _client.post(
    '/auth/reset-password',
    authenticated: false,
    body: {'token': token.trim(), 'newPassword': newPassword},
  );

  /// §7.1.7 — change the password while signed in.
  ///
  /// `401 INVALID_CREDENTIALS` for a wrong current password — which the
  /// client must not mistake for a dead session: only `TOKEN_EXPIRED` makes
  /// it refresh. On success the server has revoked every refresh token,
  /// this one included, so the tokens are dropped here and the user signs in
  /// again, as §7.1.7 asks.
  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _client.put(
      '/auth/password',
      body: {'currentPassword': currentPassword, 'newPassword': newPassword},
    );
    _client.clearTokens();
  }

  void logOut() => _client.clearTokens();

  AuthSession _store(AuthSession session) {
    _client.setTokens(
      accessToken: session.accessToken,
      refreshToken: session.refreshToken,
    );
    return session;
  }
}

/// What §7.2.3 sends back: step 1's output, computed by the server.
///
/// The app has its own copy of this arithmetic in
/// `data/rules/day_budget.dart` for the offline mode. When there is a server,
/// **these numbers win** — they are the ones written into `health_profiles`
/// and used to build the plan, so a screen showing anything else would be
/// showing a second opinion nobody asked for.
class ServerTargets {
  const ServerTargets({
    required this.bmrKcal,
    required this.tdeeKcal,
    required this.caloriesKcal,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
    required this.proteinPct,
    required this.carbsPct,
    required this.fatPct,
    this.mealShare = const {},
  });

  factory ServerTargets.fromJson(Map<String, dynamic> json) {
    // The three percentages sit INSIDE `macroTargets` next to the grams —
    // §7.2.3 — not in an object of their own.
    final macros = json['macroTargets'] as Map<String, dynamic>? ?? const {};
    return ServerTargets(
      bmrKcal: _num(json['bmrKcal']),
      tdeeKcal: _num(json['tdeeKcal']),
      caloriesKcal: _num(json['dailyCaloriesTarget']),
      proteinG: _num(macros['proteinG']),
      carbsG: _num(macros['carbsG']),
      fatG: _num(macros['fatG']),
      proteinPct: _num(macros['proteinPct']).round(),
      carbsPct: _num(macros['carbsPct']).round(),
      fatPct: _num(macros['fatPct']).round(),
      mealShare: {
        for (final m in (json['mealDistribution'] as List? ?? const []))
          if (m is Map && m['mealType'] is String)
            m['mealType'] as String: _num(m['caloriesKcal']),
      },
    );
  }

  static double _num(Object? v) => v is num ? v.toDouble() : 0;

  final double bmrKcal;
  final double tdeeKcal;
  final double caloriesKcal;
  final double proteinG;
  final double carbsG;
  final double fatG;
  final int proteinPct;
  final int carbsPct;
  final int fatPct;

  /// kcal per meal, keyed by `meal_type` — §7.2.3's `mealDistribution`. The
  /// same 27.5 / 37.5 / 27.5 / 7.5 split step 4 assembles a day by, but
  /// taken from the server rather than worked out again here.
  final Map<String, double> mealShare;

  /// Copies the three percentages onto the profile, which is what
  /// [HealthProfile.proteinPct] and its two neighbours were left writable
  /// for: the offline arithmetic then splits the energy the same way the
  /// server just did, instead of by its own defaults of 15 / 60 / 25.
  void applyTo(HealthProfile profile) {
    if (proteinPct + carbsPct + fatPct != 100) return;
    profile
      ..proteinPct = proteinPct
      ..carbsPct = carbsPct
      ..fatPct = fatPct;
  }
}
