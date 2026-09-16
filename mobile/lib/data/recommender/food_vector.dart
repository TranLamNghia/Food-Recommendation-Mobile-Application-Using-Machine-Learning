import 'dart:math' as math;

import '../models/food.dart';

/// Biểu diễn món ăn thành vector đặc trưng số.
///
/// Đây là bước **trích chọn đặc trưng** nêu trong đề cương. Mỗi món được quy
/// về một điểm trong không gian nhiều chiều, để hai món "giống nhau" nằm gần
/// nhau và độ tương đồng giữa chúng đo được bằng góc.
///
/// Vector gồm bốn khối, ghép nối tiếp:
///
/// | Khối | Số chiều | Nội dung |
/// |---|---|---|
/// | Dinh dưỡng | 4 | tỷ lệ đạm – bột đường – béo, và năng lượng chuẩn hóa |
/// | Mức cay | 1 | `spiceLevel / 3` |
/// | Nhóm thực phẩm | n | mã hóa one-hot |
/// | Phương pháp chế biến | m | mã hóa one-hot |
///
/// Ba chiều macro đã tự nằm trong đoạn [0, 1] và cộng lại bằng 1 nên không
/// cần chuẩn hóa thêm. Riêng năng lượng có đơn vị kcal với khoảng giá trị
/// hàng trăm, nếu để nguyên nó sẽ át toàn bộ các chiều còn lại khi tính
/// khoảng cách — nên phải đưa về [0, 1] bằng min-max trên chính tập món.
class FoodVectorSpace {
  FoodVectorSpace._({
    required this.categories,
    required this.methods,
    required this.minKcal,
    required this.maxKcal,
  });

  /// Dựng không gian đặc trưng từ một tập món.
  ///
  /// Danh mục và phương pháp chế biến được **suy ra từ dữ liệu** chứ không
  /// liệt kê cứng, để khi tập món mở rộng thì vector tự dài ra theo. Cả hai
  /// đều sắp xếp lại để thứ tự chiều ổn định giữa các lần chạy — nếu thứ tự
  /// đổi theo thứ tự duyệt, vector lưu ở lần trước sẽ không còn so được với
  /// vector dựng ở lần sau.
  factory FoodVectorSpace.fromFoods(List<Food> foods) {
    final categories = foods.map((f) => f.category).toSet().toList()..sort();
    final methods = foods.map((f) => f.cookingMethod).toSet().toList()..sort();

    var minKcal = double.infinity;
    var maxKcal = double.negativeInfinity;
    for (final f in foods) {
      final k = f.kcal.toDouble();
      if (k < minKcal) minKcal = k;
      if (k > maxKcal) maxKcal = k;
    }

    return FoodVectorSpace._(
      categories: categories,
      methods: methods,
      minKcal: minKcal,
      maxKcal: maxKcal,
    );
  }

  final List<String> categories;
  final List<String> methods;
  final double minKcal;
  final double maxKcal;

  /// Số chiều: 4 dinh dưỡng + 1 cay + one-hot nhóm + one-hot chế biến.
  int get length => 5 + categories.length + methods.length;

  /// Nhãn của từng chiều, dùng khi cần giải thích vì sao một món được gợi ý.
  List<String> get labels => [
    'Tỷ lệ đạm',
    'Tỷ lệ bột đường',
    'Tỷ lệ béo',
    'Năng lượng',
    'Mức cay',
    ...categories.map((c) => 'Nhóm: $c'),
    ...methods.map((m) => 'Chế biến: $m'),
  ];

  List<double> encode(Food food) {
    final v = List<double>.filled(length, 0);
    final share = food.macroShare;

    v[0] = share.protein;
    v[1] = share.carb;
    v[2] = share.fat;
    v[3] = _normalizeKcal(food.kcal.toDouble());
    v[4] = food.spiceLevel / 3;

    final ci = categories.indexOf(food.category);
    if (ci >= 0) v[5 + ci] = 1;

    final mi = methods.indexOf(food.cookingMethod);
    if (mi >= 0) v[5 + categories.length + mi] = 1;

    return v;
  }

  /// Chuẩn hóa min-max. Khi cả tập chỉ có một mức năng lượng thì mẫu số bằng
  /// 0, lúc đó trả về 0,5 để chiều này không đóng góp lệch về bên nào.
  double _normalizeKcal(double kcal) {
    final range = maxKcal - minKcal;
    if (range <= 0) return 0.5;
    return ((kcal - minKcal) / range).clamp(0.0, 1.0);
  }
}

/// Độ tương đồng cosin giữa hai vector cùng số chiều.
///
/// Trả về giá trị trong đoạn [-1, 1]. Khi một trong hai vector có độ dài 0
/// thì góc không xác định — trả về 0 để món đó nhận điểm trung tính thay vì
/// làm hỏng phép chia.
double cosineSimilarity(List<double> a, List<double> b) {
  assert(a.length == b.length, 'Hai vector phải cùng số chiều');

  var dot = 0.0;
  var normA = 0.0;
  var normB = 0.0;

  for (var i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA == 0 || normB == 0) return 0;
  return dot / (math.sqrt(normA) * math.sqrt(normB));
}
