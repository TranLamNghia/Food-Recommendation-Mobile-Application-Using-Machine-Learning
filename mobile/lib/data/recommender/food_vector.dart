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
/// | Vị ngọt | 1 | `sugarConcentration` — đường trên gam món, **đo được** |
/// | Vị mặn | 1 | natri chuẩn hóa min–max, **đo được** |
/// | Chất xơ | 1 | xơ chuẩn hóa min–max, **đo được** |
/// | Mức cay | 1 | `spiceLevel / 3` — **người nhập đánh giá** |
/// | Nhóm thực phẩm | n | mã hóa one-hot |
///
/// Khối nhóm thực phẩm **gánh luôn phương pháp chế biến** mà đề cương nêu:
/// phần lớn nhóm món của hệ thống chính là cách chế biến — `mon_chien` là
/// chiên, `mon_nuong` là nướng, `mon_xao` là xào. Nên không có khối one-hot
/// riêng cho cách chế biến; xem chú thích ở `length`.
///
/// Ba chiều macro đã tự nằm trong đoạn [0, 1] và cộng lại bằng 1 nên không
/// cần chuẩn hóa thêm. Riêng năng lượng có đơn vị kcal với khoảng giá trị
/// hàng trăm, nếu để nguyên nó sẽ át toàn bộ các chiều còn lại khi tính
/// khoảng cách — nên phải đưa về [0, 1] bằng min-max trên chính tập món.
class FoodVectorSpace {
  FoodVectorSpace._({
    required this.categories,
    required this.minKcal,
    required this.maxKcal,
    required this.minSugar,
    required this.maxSugar,
    required this.minSodium,
    required this.maxSodium,
    required this.minFiber,
    required this.maxFiber,
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

    var minKcal = double.infinity;
    var maxKcal = double.negativeInfinity;
    var minSugar = double.infinity;
    var maxSugar = double.negativeInfinity;
    var minSodium = double.infinity;
    var maxSodium = double.negativeInfinity;
    var minFiber = double.infinity;
    var maxFiber = double.negativeInfinity;
    for (final f in foods) {
      final k = f.kcal.toDouble();
      if (k < minKcal) minKcal = k;
      if (k > maxKcal) maxKcal = k;
      final sg = f.sugarConcentration;
      if (sg < minSugar) minSugar = sg;
      if (sg > maxSugar) maxSugar = sg;
      if (f.sodium < minSodium) minSodium = f.sodium;
      if (f.sodium > maxSodium) maxSodium = f.sodium;
      if (f.fiber < minFiber) minFiber = f.fiber;
      if (f.fiber > maxFiber) maxFiber = f.fiber;
    }

    return FoodVectorSpace._(
      categories: categories,
      minKcal: minKcal,
      maxKcal: maxKcal,
      minSugar: minSugar,
      maxSugar: maxSugar,
      minSodium: minSodium,
      maxSodium: maxSodium,
      minFiber: minFiber,
      maxFiber: maxFiber,
    );
  }

  final List<String> categories;
  final double minKcal;
  final double maxKcal;

  /// Biên nồng độ đường (g đường trên g món) — xem `Food.sugarConcentration`.
  final double minSugar;
  final double maxSugar;
  final double minSodium;
  final double maxSodium;
  final double minFiber;
  final double maxFiber;

  /// Số chiều: 4 dinh dưỡng + 1 ngọt + 1 mặn + 1 xơ + 1 cay + one-hot nhóm.
  ///
  /// Vị ngọt và vị mặn lấy từ `sugar_g` và `sodium_mg` — hai đại lượng **có
  /// trong bảng thành phần thực phẩm**, khác với mức cay là đánh giá chủ quan
  /// của người nhập. Không có chiều cho vị chua và vị đắng vì không nguồn nào
  /// công bố chúng; thêm cột số cho chúng là tạo ra độ chính xác giả.
  ///
  /// Không có khối one-hot riêng cho cách chế biến, nhưng **tín hiệu đó
  /// không mất** — nhóm món đã mang nó (nhóm `Món chiên` thì cách chế biến
  /// là chiên), nên hai khối one-hot gần như trùng nhau.
  ///
  /// Quan trọng hơn, hai trục độc lập cho phép dữ liệu tự mâu thuẫn: mì tôm
  /// nấu nước và mì tôm xào khô là hai món khác nhau với dinh dưỡng khác
  /// nhau, không phải một món với hai cách chế biến. Tách rời thì không gì
  /// ngăn một món thuộc nhóm `Món nước` lại mang cách chế biến `xao`.
  /// Vì sao có chiều chất xơ. Khẩu vị không phải thứ duy nhất quyết định
  /// chất lượng gợi ý: người dùng có thể **muốn ăn nhiều chất xơ**. Không có
  /// chiều này thì sở thích đó không biểu diễn được trong vector ưa thích
  /// Rocchio, và bộ gợi ý chỉ bắt được nó gián tiếp qua nhóm món.
  ///
  /// Đo trên 305 món thật, mô phỏng người dùng thích 10 món giàu xơ nhất rồi
  /// chấm điểm cosin cho phần còn lại:
  ///
  /// | Vector | Chất xơ trung bình của top-20 |
  /// |---|---|
  /// | Cả danh mục | 1,75 g |
  /// | Không có chiều xơ | 2,97 g — thu hẹp 41,7 % |
  /// | Có chiều xơ | 3,50 g — thu hẹp 59,7 % |
  /// | Mốc lý tưởng (20 món xơ nhất) | 4,67 g |
  ///
  /// Lưu ý phạm vi: chiều này phục vụ sở thích **suy ra từ hành vi**. Một
  /// mục tiêu do người dùng tự khai — "tôi cần 25 g xơ mỗi ngày" — là đại
  /// lượng **theo ngày**, thuộc về Bước 4 chứ không phải phép đo góc ở đây.
  int get length => 8 + categories.length;

  /// Nhãn của từng chiều, dùng khi cần giải thích vì sao một món được gợi ý.
  List<String> get labels => [
    'Tỷ lệ đạm',
    'Tỷ lệ bột đường',
    'Tỷ lệ béo',
    'Năng lượng',
    'Vị ngọt',
    'Vị mặn',
    'Chất xơ',
    'Mức cay',
    ...categories.map((c) => 'Nhóm: $c'),
  ];

  /// Chiều ứng với một chất dinh dưỡng đơn lẻ, hoặc `null` nếu chất đó không
  /// có chiều riêng.
  ///
  /// Dùng khi người dùng **tự khai một mục tiêu** — "tôi muốn ăn nhiều chất
  /// xơ" — để nhúng mục tiêu đó thẳng vào vector ưa thích, xem
  /// `PreferenceProfile.withNutrientGoals`.
  ///
  /// Tra theo **nhãn** chứ không trả về chỉ số cứng: nhãn và chiều luôn đi
  /// cùng nhau, nên chèn thêm một chiều ở giữa sẽ không làm hàm này trỏ sai.
  ///
  /// Chỉ ba chất có mặt ở đây. Ba chiều macro **cố tình không** có, vì chúng
  /// là **tỷ lệ cộng lại bằng 1**: đẩy tỷ lệ đạm lên đồng nghĩa với dìm tỷ lệ
  /// bột đường và béo xuống, không phải cùng một ý với "tôi muốn ăn nhiều
  /// đạm hơn". Một mục tiêu về lượng đạm thuộc về hạn mức theo ngày ở Bước 4.
  int? dimensionOfNutrient(String nutrient) {
    const labelOf = {
      'sugar_g': 'Vị ngọt',
      'sodium_mg': 'Vị mặn',
      'fiber_g': 'Chất xơ',
    };
    final label = labelOf[nutrient];
    if (label == null) return null;
    final i = labels.indexOf(label);
    return i < 0 ? null : i;
  }

  List<double> encode(Food food) {
    final v = List<double>.filled(length, 0);
    final share = food.macroShare;

    v[0] = share.protein;
    v[1] = share.carb;
    v[2] = share.fat;
    v[3] = _normalizeKcal(food.kcal.toDouble());
    v[4] = _normalizeSugar(food.sugarConcentration);
    v[5] = _normalizeSodium(food.sodium);
    v[6] = _normalizeFiber(food.fiber);
    v[7] = food.spiceLevel / 3;

    final ci = categories.indexOf(food.category);
    if (ci >= 0) v[8 + ci] = 1;

    return v;
  }

  /// Chuẩn hóa min-max. Khi cả tập chỉ có một mức năng lượng thì mẫu số bằng
  /// 0, lúc đó trả về 0,5 để chiều này không đóng góp lệch về bên nào.
  double _normalizeKcal(double kcal) {
    final range = maxKcal - minKcal;
    if (range <= 0) return 0.5;
    return ((kcal - minKcal) / range).clamp(0.0, 1.0);
  }

  /// Chuẩn hóa nồng độ đường về `[0,1]` theo min–max của tập món, cùng cách
  /// với natri: "ngọt" cũng là khái niệm tương đối trong phạm vi tập món.
  double _normalizeSugar(double conc) {
    if (maxSugar <= minSugar) return 0.5;
    return ((conc - minSugar) / (maxSugar - minSugar)).clamp(0.0, 1.0);
  }

  /// Chuẩn hóa natri về `[0,1]` theo min–max của tập món.
  ///
  /// Dùng cùng cách với năng lượng thay vì một ngưỡng cố định, vì "mặn" là
  /// khái niệm tương đối trong phạm vi tập món đang có.
  double _normalizeSodium(double sodium) {
    if (maxSodium <= minSodium) return 0.5;
    return ((sodium - minSodium) / (maxSodium - minSodium)).clamp(0.0, 1.0);
  }

  /// Chuẩn hóa chất xơ về `[0,1]` theo min–max của tập món, cùng cách với
  /// natri: "nhiều xơ" cũng là khái niệm tương đối trong phạm vi tập món.
  double _normalizeFiber(double fiber) {
    if (maxFiber <= minFiber) return 0.5;
    return ((fiber - minFiber) / (maxFiber - minFiber)).clamp(0.0, 1.0);
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
