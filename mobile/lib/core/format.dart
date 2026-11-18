/// Formats a number the Vietnamese way: a comma before the decimals, a dot
/// between thousands.
///
/// Dart's `5.0` comes out as `5,0`, and `1850` as `1.850`.
String formatNumber(double value, [int digits = 0]) {
  final parts = value.toStringAsFixed(digits).split('.');

  final buffer = StringBuffer();
  final whole = parts.first;
  for (var i = 0; i < whole.length; i++) {
    if (i > 0 && (whole.length - i) % 3 == 0) buffer.write('.');
    buffer.write(whole[i]);
  }

  return parts.length > 1 ? '$buffer,${parts[1]}' : buffer.toString();
}