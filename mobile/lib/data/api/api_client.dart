// ONLINE: the one place the app talks to the backend over HTTP.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_config.dart';
import 'failure.dart';

/// The transport. Everything above it deals in Dart objects and
/// [ApiFailure]; nothing above it mentions a status code or a header.
///
/// It owns the pair of tokens, because the pair is a transport concern: the
/// access token goes on every request and the refresh token exists purely to
/// replace it. Screens never see either.
///
/// **Tokens live in memory only.** Closing the app means signing in again.
/// Persisting them needs a storage package, and writing a JWT to unencrypted
/// storage is a decision worth making on purpose rather than in passing —
/// so for now the honest behaviour is the one that loses them.
class ApiClient {
  ApiClient({
    String? baseUrl,
    http.Client? httpClient,
    Duration? timeout,
    this.onSignedOut,
  }) : baseUrl = _normalise(baseUrl ?? ApiConfig.baseUrl),
       _http = httpClient ?? http.Client(),
       timeout = timeout ?? ApiConfig.timeout;

  static String _normalise(String url) =>
      url.endsWith('/') ? url.substring(0, url.length - 1) : url;

  final String baseUrl;
  final Duration timeout;
  final http.Client _http;

  /// Called when the session has ended for good: the refresh token was
  /// rejected too, so there is nothing left to retry with and the user has
  /// to sign in again.
  final void Function()? onSignedOut;

  String? _accessToken;
  String? _refreshToken;

  bool get hasSession => _accessToken != null;

  void setTokens({required String accessToken, required String refreshToken}) {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
  }

  void clearTokens() {
    _accessToken = null;
    _refreshToken = null;
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String?>? query,
    bool authenticated = true,
  }) => _send('GET', path, query: query, authenticated: authenticated);

  Future<Map<String, dynamic>> post(
    String path, {
    Object? body,
    bool authenticated = true,
  }) => _send('POST', path, body: body, authenticated: authenticated);

  Future<Map<String, dynamic>> put(String path, {Object? body}) =>
      _send('PUT', path, body: body);

  Future<Map<String, dynamic>> patch(String path, {Object? body}) =>
      _send('PATCH', path, body: body);

  Future<Map<String, dynamic>> delete(String path) => _send('DELETE', path);

  /// A request whose body is a JSON **array** rather than an object.
  ///
  /// Several endpoints answer that way and it is easy to assume otherwise:
  /// the three lookup dictionaries of §7.3, and both halves of §7.2.4 and
  /// §7.2.5, which send the list of declared conditions bare — the request
  /// body of §7.2.5 is wrapped in `{"conditions": [...]}` but its answer is
  /// not.
  Future<List<dynamic>> sendList(
    String method,
    String path, {
    Object? body,
    Map<String, String?>? query,
    bool authenticated = true,
  }) async {
    final decoded = await _sendRaw(
      method,
      path,
      body: body,
      query: query,
      authenticated: authenticated,
    );
    if (decoded is List) return decoded;
    throw ApiFailure(
      code: ApiFailure.unexpectedShape,
      message: 'Máy chủ trả về dữ liệu không đọc được',
    );
  }

  Future<List<dynamic>> getList(
    String path, {
    Map<String, String?>? query,
    bool authenticated = true,
  }) => sendList('GET', path, query: query, authenticated: authenticated);

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String?>? query,
    bool authenticated = true,
  }) async {
    final decoded = await _sendRaw(
      method,
      path,
      body: body,
      query: query,
      authenticated: authenticated,
    );
    if (decoded is Map<String, dynamic>) return decoded;
    // `204 No Content` is a success with nothing in it — §7.7.4 answers that
    // way. An empty map rather than a failure: the caller asked for the
    // action, not for a body.
    if (decoded == null) return const {};
    throw ApiFailure(
      code: ApiFailure.unexpectedShape,
      message: 'Máy chủ trả về dữ liệu không đọc được',
    );
  }

  Future<dynamic> _sendRaw(
    String method,
    String path, {
    Object? body,
    Map<String, String?>? query,
    bool authenticated = true,
    bool isRetry = false,
  }) async {
    final response = await _dispatch(
      method,
      path,
      body: body,
      query: query,
      authenticated: authenticated,
    );

    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.bodyBytes.isEmpty) return null;
      try {
        return jsonDecode(utf8.decode(response.bodyBytes));
      } on FormatException {
        throw ApiFailure(
          code: ApiFailure.unexpectedShape,
          message: 'Máy chủ trả về dữ liệu không đọc được',
          status: response.statusCode,
        );
      }
    }

    final failure = _failureFrom(response);

    // An expired access token is the one failure worth handling instead of
    // reporting: refresh once, then replay the original request once. Both
    // "once"es matter — `isRetry` is what stops a server that answers 401 to
    // everything, refresh included, from turning into an endless loop.
    if (!isRetry &&
        authenticated &&
        failure.code == ApiFailure.tokenExpired &&
        _refreshToken != null) {
      if (await _refresh()) {
        return _sendRaw(
          method,
          path,
          body: body,
          query: query,
          authenticated: authenticated,
          isRetry: true,
        );
      }
    }

    throw failure;
  }

  Future<http.Response> _dispatch(
    String method,
    String path, {
    Object? body,
    Map<String, String?>? query,
    bool authenticated = true,
  }) async {
    final uri = _uri(path, query);
    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json; charset=utf-8',
      if (authenticated && _accessToken != null)
        'Authorization': 'Bearer $_accessToken',
    };
    final payload = body == null ? null : jsonEncode(body);

    try {
      final request = switch (method) {
        'GET' => _http.get(uri, headers: headers),
        'POST' => _http.post(uri, headers: headers, body: payload),
        'PUT' => _http.put(uri, headers: headers, body: payload),
        'PATCH' => _http.patch(uri, headers: headers, body: payload),
        'DELETE' => _http.delete(uri, headers: headers, body: payload),
        _ => throw ArgumentError('unsupported method $method'),
      };
      return await request.timeout(timeout);
    } on TimeoutException {
      throw ApiFailure.timedOut();
    } on ApiFailure {
      rethrow;
    } catch (e) {
      // `SocketException`, `ClientException`, a handshake error: from the
      // user's side these are one thing — the server did not answer.
      throw ApiFailure.unreachable(e);
    }
  }

  Uri _uri(String path, Map<String, String?>? query) {
    final cleaned = path.startsWith('/') ? path : '/$path';
    final uri = Uri.parse('$baseUrl$cleaned');
    if (query == null || query.isEmpty) return uri;
    return uri.replace(
      queryParameters: {
        ...uri.queryParameters,
        for (final e in query.entries)
          if (e.value != null) e.key: e.value!,
      },
    );
  }

  ApiFailure _failureFrom(http.Response response) {
    if (response.bodyBytes.isEmpty) {
      return ApiFailure(
        code: ApiFailure.unexpectedShape,
        message: 'Máy chủ trả về lỗi ${response.statusCode}',
        status: response.statusCode,
      );
    }
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map<String, dynamic>) {
        return ApiFailure.fromEnvelope(response.statusCode, decoded);
      }
    } on FormatException {
      // Falls through: an HTML error page from a proxy, for instance.
    }
    return ApiFailure(
      code: ApiFailure.unexpectedShape,
      message: 'Máy chủ trả về lỗi ${response.statusCode}',
      status: response.statusCode,
    );
  }

  /// §7.1.3. Returns whether a new pair arrived.
  ///
  /// The refresh call goes out **unauthenticated** on purpose: the access
  /// token it is replacing is the expired one, and sending it would be asking
  /// the server to validate the very thing that just failed.
  Future<bool> _refresh() async {
    final token = _refreshToken;
    if (token == null) return false;
    try {
      final response = await _dispatch(
        'POST',
        '/auth/refresh',
        body: {'refreshToken': token},
        authenticated: false,
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        clearTokens();
        onSignedOut?.call();
        return false;
      }
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map<String, dynamic>) {
        clearTokens();
        onSignedOut?.call();
        return false;
      }
      final access = decoded['accessToken'] as String?;
      final refresh = decoded['refreshToken'] as String?;
      if (access == null || refresh == null) {
        clearTokens();
        onSignedOut?.call();
        return false;
      }
      // §7.1.3 rotates the refresh token and treats a reused one as theft,
      // so the new one has to replace the old one here or the next refresh
      // invalidates the whole chain.
      setTokens(accessToken: access, refreshToken: refresh);
      return true;
    } on ApiFailure {
      // Unreachable or timed out. The session is not necessarily over, so
      // the tokens are kept and the original failure is reported instead.
      return false;
    }
  }

  void close() => _http.close();
}
