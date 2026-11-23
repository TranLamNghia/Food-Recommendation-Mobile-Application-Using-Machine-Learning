// ONLINE: where the server is, and whether there is one at all.

/// Which of the app's two modes this build runs in.
///
/// The address comes from `--dart-define=API_BASE_URL=...` at compile time
/// rather than from a file in the repository, because the repository is
/// **public**: a committed address is one more thing to remember to not
/// commit. No address means [AppMode.offline], which is what `flutter run`
/// and `flutter test` get by default — so the whole test suite keeps running
/// without a server, exactly as it did before any of this existed.
///
/// See `mobile/README.md` for the two modes and the `// OFFLINE:` /
/// `// ONLINE:` labelling convention.
enum AppMode { offline, online }

class ApiConfig {
  const ApiConfig._();

  /// Example: `http://10.0.2.2:5055/api/v1`.
  ///
  /// `10.0.2.2` is the host machine as seen from the Android emulator;
  /// `localhost` inside the emulator is the emulator itself, which is the
  /// first thing that goes wrong when wiring a Flutter app to a local server.
  static const String baseUrl = String.fromEnvironment('API_BASE_URL');

  static AppMode get mode =>
      baseUrl.isEmpty ? AppMode.offline : AppMode.online;

  static bool get isOnline => mode == AppMode.online;

  /// How long one request may take.
  ///
  /// Ten seconds, not the two the backend gives the ML service. That budget
  /// is the backend's own, and it is measured on a loopback connection;
  /// this one crosses a phone's network and then waits for the backend to
  /// finish its own work, plan generation included.
  static const Duration timeout = Duration(seconds: 10);
}
