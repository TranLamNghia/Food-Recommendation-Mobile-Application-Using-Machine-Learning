/// Định dạng số theo quy ước Việt Nam: dấu phẩy ngăn phần thập phân, dấu
/// chấm ngăn hàng nghìn.
///
/// `5.0` của Dart đọc ra thành `5,0`, và `1850` thành `1.850`.
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
