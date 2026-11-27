// ONLINE: the §2.5 error envelope, as something Dart code can branch on.

/// One field the server refused, from `error.details`.
class FieldProblem {
  const FieldProblem({required this.field, required this.message});

  final String field;

  /// Vietnamese, written by the server for the user to read.
  final String message;

  @override
  String toString() => '$field: $message';
}

/// Anything that stopped a request from succeeding.
///
/// **The app branches on [code], never on [message].** `code` is the stable
/// string the specification pins in §4 — `TOKEN_EXPIRED`,
/// `FEEDBACK_NOT_ALLOWED`, `PROFILE_REQUIRED` — while `message` is Vietnamese
/// prose that may be reworded at any time. A screen that reads the prose to
/// decide what to do breaks the next time someone fixes a typo.
///
/// Every failure carries a [message] that **can be shown as it is**. That is
/// the point of the thesis decision behind this class: a screen that says
/// what went wrong beats an app that crashes, and it only holds if there is
/// never a case with nothing to say.
class ApiFailure implements Exception {
  const ApiFailure({
    required this.code,
    required this.message,
    this.status,
    this.fields = const [],
    this.traceId,
  });

  /// The envelope the server sent — §2.5.
  factory ApiFailure.fromEnvelope(int status, Map<String, dynamic> body) {
    final error = body['error'];
    if (error is! Map) {
      // A JSON body that is not the envelope. The server is answering
      // something, but not this contract, so there is nothing to read out of
      // it and guessing would be worse than saying so.
      return ApiFailure(
        code: unexpectedShape,
        message: 'Máy chủ trả về dữ liệu không đọc được',
        status: status,
      );
    }
    final details = error['details'];
    return ApiFailure(
      code: (error['code'] as String?) ?? unexpectedShape,
      message:
          (error['message'] as String?) ?? 'Có lỗi xảy ra, vui lòng thử lại',
      status: status,
      traceId: error['traceId'] as String?,
      fields: details is List
          ? [
              for (final d in details)
                if (d is Map)
                  FieldProblem(
                    field: (d['field'] as String?) ?? '',
                    message: (d['message'] as String?) ?? '',
                  ),
            ]
          : const [],
    );
  }

  /// No answer at all: no network, the wrong address, the server not running.
  factory ApiFailure.unreachable([Object? cause]) => ApiFailure(
    code: unreachable_,
    message:
        'Không kết nối được tới máy chủ. Hãy kiểm tra mạng rồi thử lại.',
    traceId: cause?.toString(),
  );

  factory ApiFailure.timedOut() => const ApiFailure(
    code: timeout,
    message: 'Máy chủ phản hồi quá chậm, vui lòng thử lại.',
  );

  /// Codes this layer raises itself. They are **not** in §4's catalogue,
  /// which only covers answers the server gives, and they are spelled in the
  /// same shape so a screen can treat all of them alike.
  static const String unreachable_ = 'NETWORK_UNREACHABLE';
  static const String timeout = 'NETWORK_TIMEOUT';
  static const String unexpectedShape = 'UNEXPECTED_RESPONSE';

  /// Codes from §4 the app has to recognise rather than merely display.
  static const String tokenExpired = 'TOKEN_EXPIRED';
  static const String tokenInvalid = 'TOKEN_INVALID';
  static const String validationFailed = 'VALIDATION_FAILED';
  static const String notFound = 'NOT_FOUND';
  static const String profileRequired = 'PROFILE_REQUIRED';
  static const String onboardingRequired = 'ONBOARDING_REQUIRED';

  /// `409` from §7.4: this account has already been through the survey. It
  /// runs once in the lifetime of an account, so the answer is not an error
  /// to show — it means the app is on the wrong screen and should move on.
  static const String onboardingAlreadyCompleted =
      'ONBOARDING_ALREADY_COMPLETED';

  /// `422` from §7.4.2: too few swipes carried an opinion. Below about twenty
  /// usable signals the preference vector is mostly the direction of
  /// whichever few dishes were swiped, so the survey is not accepted and
  /// nothing is stamped. Recognised rather than displayed because the only
  /// way forward is a fresh deck, which the app has to offer.
  static const String onboardingInsufficient = 'ONBOARDING_INSUFFICIENT';
  static const String emailAlreadyExists = 'EMAIL_ALREADY_EXISTS';
  static const String invalidCredentials = 'INVALID_CREDENTIALS';
  static const String accountDisabled = 'ACCOUNT_DISABLED';
  static const String mlUnavailable = 'ML_UNAVAILABLE';

  /// `400` from §7.1.6: the reset code is wrong, expired or already used.
  /// Recognised so the reset screen can show it under the code field, where
  /// the mistake is, rather than in a snackbar.
  static const String resetTokenInvalid = 'RESET_TOKEN_INVALID';

  /// `409` from `PUT /foods/{id}/mark`: the dish is the last one left in a
  /// role some meal cannot be assembled without, so blocking it would leave
  /// a day that cannot be built at all.
  ///
  /// Recognised rather than merely shown because the screen has to put the
  /// switch back: the user flipped it, the server refused, and a switch left
  /// on would be the app claiming something it did not store.
  static const String blockWouldEmptyMeal = 'BLOCK_WOULD_EMPTY_MEAL';

  final String code;
  final String message;

  /// `null` for the three codes raised on this side, where no answer arrived.
  final int? status;

  final List<FieldProblem> fields;
  final String? traceId;

  /// Whether trying the same thing again could plausibly work. Used to decide
  /// whether a screen offers a "thử lại" button, not to retry on its own.
  bool get isRetryable =>
      code == unreachable_ || code == timeout || code == mlUnavailable;

  /// The message for one field, so a form can mark the field itself rather
  /// than show a sentence above everything.
  String? forField(String name) {
    for (final f in fields) {
      if (f.field == name) return f.message;
    }
    return null;
  }

  @override
  String toString() => 'ApiFailure($code${status == null ? '' : ' $status'}): '
      '$message';
}

/// Runs [build] and turns a shape mismatch into an [ApiFailure].
///
/// Reading a field that is not there, or is of another type, throws a
/// `TypeError` — which is an `Error`, not an `Exception`, so nothing above
/// catches it and the app dies on a `200` with an unexpected body. The
/// thesis chose a screen that explains itself over a crash, and that choice
/// only holds if parsing cannot crash either.
///
/// It is deliberately narrow: only the construction of a DTO goes through
/// here, so a real bug in the app's own logic still surfaces as a bug
/// instead of being reported to the user as the server's fault.
T parsed<T>(T Function() build) {
  try {
    return build();
  } on ApiFailure {
    rethrow;
  } catch (_) {
    throw const ApiFailure(
      code: ApiFailure.unexpectedShape,
      message: 'Máy chủ trả về dữ liệu không đọc được',
    );
  }
}
