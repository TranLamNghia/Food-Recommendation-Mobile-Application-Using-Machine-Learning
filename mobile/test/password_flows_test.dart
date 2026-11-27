// ONLINE and offline: the three password flows of §7.1.5 – §7.1.7.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/api/api_client.dart';
import 'package:nutrition_app/data/api/failure.dart';
import 'package:nutrition_app/data/session.dart';
import 'package:nutrition_app/features/account/change_password_screen.dart';
import 'package:nutrition_app/features/auth/forgot_password_screen.dart';
import 'package:nutrition_app/features/auth/reset_password_screen.dart';
import 'package:nutrition_app/features/auth/welcome_screen.dart';

http.Response _json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

http.Response _envelope(
  int status,
  String code,
  String message, [
  List<Map<String, String>> details = const [],
]) => _json({
  'error': {
    'code': code,
    'message': message,
    'details': details.isEmpty ? null : details,
    'traceId': 'T',
  },
}, status);

final _user = {
  'id': '00000001-0000-4000-8000-000000000000',
  'email': 'nghia@example.com',
  'displayName': 'Nghĩa',
  'avatarUrl': null,
  'onboardingCompletedAt': null,
  'createdAt': '2026-11-20T07:15:30Z',
};

const _done = {'message': 'Đã đổi mật khẩu. Hãy đăng nhập lại.'};

/// One request as the fake server saw it.
typedef _Seen = ({String method, String path, String? auth, Object? body});

/// A session with a fake server behind it. [route] answers the password
/// endpoints; login, `/auth/me` and the catalogue are answered here, so a
/// test can sign in first.
AppSession _online(
  List<_Seen> seen,
  http.Response Function(http.Request request) route,
) => AppSession(
  api: ApiClient(
    baseUrl: 'http://localhost:5055/api/v1',
    httpClient: MockClient((request) async {
      final path = request.url.path.replaceFirst('/api/v1', '');
      seen.add((
        method: request.method,
        path: path,
        auth: request.headers['Authorization'],
        body: request.body.isEmpty ? null : jsonDecode(request.body),
      ));
      if (path == '/auth/login') {
        return _json({
          'accessToken': 'ACCESS',
          'refreshToken': 'REFRESH',
          'tokenType': 'Bearer',
          'expiresIn': 3600,
          'user': _user,
        });
      }
      if (path == '/auth/me') {
        return _json({..._user, 'hasHealthProfile': false});
      }
      if (path == '/foods') {
        return _json({
          'items': <dynamic>[],
          'page': 1,
          'pageSize': 20,
          'totalItems': 0,
          'totalPages': 0,
        });
      }
      return route(request);
    }),
  ),
);

Widget _app(AppSession session, Widget home) => SessionScope(
  session: session,
  child: MaterialApp(theme: AppTheme.light, home: home),
);

/// A page that opens [screen], so popping it lands somewhere.
class _Host extends StatelessWidget {
  const _Host(this.screen);

  final Widget screen;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: TextButton(
        onPressed: () =>
            Navigator.of(context)
                .push(MaterialPageRoute<void>(builder: (_) => screen)),
        child: const Text('Mở'),
      ),
    ),
  );
}

void main() {
  group('session, online', () {
    test('forgot sends the trimmed address, unauthenticated', () async {
      final seen = <_Seen>[];
      final session = _online(
        seen,
        (_) => _json({'message': 'Nếu email này đã đăng ký…'}, 202),
      );

      await session.requestPasswordReset('  nghia@example.com ');

      expect(seen.single.method, 'POST');
      expect(seen.single.path, '/auth/forgot-password');
      expect(seen.single.auth, isNull);
      expect(seen.single.body, {'email': 'nghia@example.com'});
    });

    test('reset sends the code and the new password', () async {
      final seen = <_Seen>[];
      final session = _online(seen, (_) => _json(_done));

      await session.resetPassword(code: ' CODE ', newPassword: 'MatKhau456');

      expect(seen.single.path, '/auth/reset-password');
      expect(seen.single.auth, isNull);
      expect(seen.single.body, {'token': 'CODE', 'newPassword': 'MatKhau456'});
    });

    test('a bad code comes back as RESET_TOKEN_INVALID', () async {
      final session = _online(
        [],
        (_) => _envelope(400, 'RESET_TOKEN_INVALID', 'Mã đặt lại không đúng'),
      );
      await expectLater(
        session.resetPassword(code: 'x', newPassword: 'MatKhau456'),
        throwsA(
          isA<ApiFailure>().having(
            (f) => f.code,
            'code',
            ApiFailure.resetTokenInvalid,
          ),
        ),
      );
    });

    test('changing ends this session, keeping the data', () async {
      final seen = <_Seen>[];
      final session = _online(seen, (_) => _json(_done));
      await session.logIn(email: 'nghia@example.com', password: 'MatKhau123');
      seen.clear();

      final signedOut = await session.changePassword(
        current: 'MatKhau123',
        next: 'MatKhau456',
      );

      expect(signedOut, isTrue);
      final put = seen.single;
      expect((put.method, put.path), ('PUT', '/auth/password'));
      expect(put.auth, 'Bearer ACCESS');
      expect(put.body, {
        'currentPassword': 'MatKhau123',
        'newPassword': 'MatKhau456',
      });
      expect(session.isSignedIn, isFalse);
      expect(session.displayName, 'Nghĩa');

      // The tokens went with it: the next call carries none.
      await session.requestPasswordReset('nghia@example.com');
      expect(seen.last.auth, isNull);
    });

    test(
      'a wrong current password is not mistaken for a dead session',
      () async {
        final seen = <_Seen>[];
        final session = _online(
          seen,
          (_) => _envelope(401, 'INVALID_CREDENTIALS', 'Sai mật khẩu hiện tại'),
        );
        await session.logIn(email: 'nghia@example.com', password: 'MatKhau123');

        await expectLater(
          session.changePassword(current: 'Sai12345', next: 'MatKhau456'),
          throwsA(isA<ApiFailure>()),
        );
        // A 401 that is not TOKEN_EXPIRED: no refresh, no sign-out.
        expect(seen.where((s) => s.path == '/auth/refresh'), isEmpty);
        expect(session.isSignedIn, isTrue);
      },
    );
  });

  group('session, offline', () {
    test('all three succeed without a server', () async {
      final session = AppSession()..signIn(email: 'a@b.vn');
      await session.requestPasswordReset('a@b.vn');
      await session.resetPassword(code: 'x', newPassword: 'MatKhau456');
      expect(
        await session.changePassword(current: 'a', next: 'MatKhau456'),
        isFalse,
      );
      expect(session.isSignedIn, isTrue);
    });
  });

  group('screens', () {
    testWidgets('forgot leads to the code screen, which reports a bad code', (
      tester,
    ) async {
      var codeIsGood = false;
      final session = _online([], (request) {
        if (request.url.path.endsWith('/forgot-password')) {
          return _json({'message': 'ok'}, 202);
        }
        return codeIsGood
            ? _json(_done)
            : _envelope(400, 'RESET_TOKEN_INVALID', 'Mã đặt lại không đúng');
      });
      await tester.pumpWidget(
        _app(
          session,
          const _Host(ForgotPasswordScreen(initialEmail: 'nghia@example.com')),
        ),
      );
      await tester.tap(find.text('Mở'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Gửi mã'));
      await tester.pumpAndSettle();
      expect(find.text('Kiểm tra hộp thư'), findsOneWidget);

      await tester.tap(find.text('Nhập mã đặt lại'));
      await tester.pumpAndSettle();
      expect(find.byType(ResetPasswordScreen), findsOneWidget);

      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'MA-SAI');
      await tester.enterText(fields.at(1), 'MatKhau456');
      await tester.enterText(fields.at(2), 'MatKhau456');
      await tester.tap(find.text('Đổi mật khẩu'));
      await tester.pumpAndSettle();
      expect(find.text('Mã đặt lại không đúng'), findsOneWidget);

      codeIsGood = true;
      await tester.tap(find.text('Đổi mật khẩu'));
      await tester.pumpAndSettle();
      // Both screens closed: back where the user started, to log in.
      expect(find.byType(ResetPasswordScreen), findsNothing);
      expect(find.byType(ForgotPasswordScreen), findsNothing);
      expect(find.text('Mở'), findsOneWidget);
    });

    testWidgets('the two new passwords have to match', (tester) async {
      await tester.pumpWidget(_app(AppSession(), const ResetPasswordScreen()));
      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'CODE');
      await tester.enterText(fields.at(1), 'MatKhau456');
      await tester.enterText(fields.at(2), 'MatKhau457');
      await tester.tap(find.text('Đổi mật khẩu'));
      await tester.pumpAndSettle();
      expect(find.text('Hai mật khẩu chưa khớp'), findsOneWidget);
    });

    testWidgets('change: a wrong current password shows under its field, '
        'and success goes back to the welcome screen', (tester) async {
      var currentIsRight = false;
      final session = _online(
        [],
        (_) => currentIsRight
            ? _json(_done)
            : _envelope(
                401,
                'INVALID_CREDENTIALS',
                'Mật khẩu hiện tại không đúng',
              ),
      );
      await session.logIn(email: 'nghia@example.com', password: 'MatKhau123');
      await tester.pumpWidget(
        _app(session, const _Host(ChangePasswordScreen())),
      );
      await tester.tap(find.text('Mở'));
      await tester.pumpAndSettle();

      final fields = find.byType(TextFormField);
      await tester.enterText(fields.at(0), 'SaiMatKhau1');
      await tester.enterText(fields.at(1), 'MatKhau456');
      await tester.tap(find.text('Lưu mật khẩu mới'));
      await tester.pumpAndSettle();
      expect(find.text('Mật khẩu hiện tại không đúng'), findsOneWidget);
      expect(session.isSignedIn, isTrue);

      currentIsRight = true;
      await tester.tap(find.text('Lưu mật khẩu mới'));
      await tester.pumpAndSettle();
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.text('Đã đổi mật khẩu. Hãy đăng nhập lại.'), findsOneWidget);
      expect(session.isSignedIn, isFalse);
    });
  });
}
