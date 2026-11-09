import '../models/food.dart';
import 'food_vector.dart';
import 'preference_profile.dart';

/// Vì sao **món này** khớp khẩu vị — bằng câu, không bằng số.
///
/// Khác [PreferenceProfile.topTraits], vốn nói người dùng thích gì *nói
/// chung*. Ở đây là đóng góp của từng chiều vào điểm của **một món cụ thể**:
/// `p_u[i] · vᵢ[i]`, tức số hạng của chính nó trong tử số của phép cosin.
///
/// Phản chiếu `dong_gop` ở `ml/serve.py`, và dùng cùng bảng mệnh đề, để câu
/// hiện trên điện thoại giống câu máy chủ sinh ra.
///
/// ## Vì sao bỏ con số đi
///
/// Bản trước trả về `"Tỷ lệ đạm (+0.182)"`. Nhãn chiều thì đã tiếng Việt
/// đọc được, nhưng `+0.182` vô nghĩa với người dùng: không đơn vị, không
/// phải phần trăm, và độ lớn phụ thuộc cả vào hồ sơ lẫn vào món. **Thứ tự
/// mới là thông tin.**
///
/// ## Vì sao câu luôn là "nhiều X", không bao giờ "ít X"
///
/// Mọi chiều của vector món nằm trong [0, 1] — `food_vector_parity_test`
/// khẳng định điều đó. Nên `v[i] ≥ 0` luôn, và dấu của `p_u[i]·v[i]` chính
/// là dấu của `p_u[i]`. Một đóng góp **dương** vì vậy nghĩa là món người
/// này thích có giá trị cao ở chiều đó; nghiêng về giá trị thấp cho đóng góp
/// âm, và đóng góp âm đã bị loại khỏi danh sách này.
class MatchReason {
  const MatchReason({
    required this.dimension,
    required this.value,
    required this.ratio,
    required this.sentence,
  });

  /// Nhãn kỹ thuật của chiều, giữ để gỡ lỗi — **không** hiện cho người dùng.
  final String dimension;

  /// `p_u[i] · vᵢ[i]`. Giữ để kiểm và gỡ lỗi, không hiện ra.
  final double value;

  /// So với đóng góp lớn nhất **của chính món này**, trong (0, 1].
  ///
  /// Đây là thứ vẽ thành thanh so sánh, nhưng nó chỉ nói thứ tự BÊN TRONG
  /// một món, KHÔNG nói món đó khớp khẩu vị mạnh đến đâu. Một món người dùng
  /// đã vuốt `dislike` vẫn cho ba tỷ lệ 100 % / 91 % / 88 % trong khi đóng
  /// góp tuyệt đối chỉ quanh +0,009: chuẩn hóa theo đỉnh của chính nó nên
  /// một món khớp rất yếu vẫn ra ba thanh gần đầy.
  ///
  /// Vì vậy giao diện **phải** hiện điểm khớp tổng ([PreferenceProfile.score])
  /// bên cạnh. Vẽ riêng mấy thanh này là nói với người dùng rằng mọi món đều
  /// khớp mạnh như nhau.
  final double ratio;

  /// Câu cho người dùng. `null` khi chiều này chưa có mệnh đề — giao diện bỏ
  /// dòng đó thay vì hiện nhãn kỹ thuật.
  final String? sentence;
}

/// Nhãn chiều → mệnh đề mô tả món, để dựng câu "Bạn thường chọn món …".
///
/// Thiếu một nhãn ở đây **không** làm hàm nổ — giao diện vẫn chạy, chỉ là
/// chiều đó không có câu. Nhưng [dimensionsWithoutSentence] báo ra và bộ
/// kiểm gọi nó, nên một chiều mới thêm vào mà quên đặt câu thì phép kiểm sai
/// ngay chứ không âm thầm hiện nhãn kỹ thuật cho người dùng.
const Map<String, String> clauseByDimension = {
  'Tỷ lệ đạm': 'nhiều đạm',
  'Tỷ lệ bột đường': 'nhiều bột đường',
  'Tỷ lệ béo': 'nhiều chất béo',
  'Năng lượng': 'nhiều năng lượng',
  'Vị ngọt': 'có vị ngọt',
  'Vị mặn': 'đậm vị mặn',
  'Chất xơ': 'nhiều chất xơ',
  'Mức cay': 'có vị cay',
};

/// Tiền tố mà [FoodVectorSpace.labels] gắn cho chiều one-hot nhóm món.
const String categoryPrefix = 'Nhóm: ';

String? sentenceForDimension(String label) {
  if (label.startsWith(categoryPrefix)) {
    return 'Bạn thích nhóm ${label.substring(categoryPrefix.length)}';
  }
  final clause = clauseByDimension[label];
  return clause == null ? null : 'Bạn thường chọn món $clause';
}

/// Các chiều chưa có câu cho người dùng.
///
/// Chiều nhóm món luôn có câu vì nó dựng từ tên nhóm, nên danh sách này chỉ
/// gồm chiều cố định bị quên trong [clauseByDimension].
List<String> dimensionsWithoutSentence(FoodVectorSpace space) => [
  for (final label in space.labels)
    if (sentenceForDimension(label) == null) label,
];

/// `limit` chiều đóng góp nhiều nhất vào điểm khớp khẩu vị của [food].
///
/// Chỉ nêu chiều **dương**: một chiều âm nghĩa là món bị trừ điểm ở đó, nó
/// không phải lý do món được gợi ý. Hồ sơ rỗng trả về danh sách rỗng — không
/// có cơ sở nào để nói người này thích gì.
List<MatchReason> matchReasons(
  PreferenceProfile profile,
  Food food, {
  int limit = 3,
}) {
  if (profile.isEmpty) return const [];

  final space = profile.space;
  final vector = space.encode(food);
  final labels = space.labels;

  final gop = <({String label, double value})>[];
  for (var i = 0; i < vector.length; i++) {
    final v = profile.weights[i] * vector[i];
    if (v > 0) gop.add((label: labels[i], value: v));
  }
  if (gop.isEmpty) return const [];

  gop.sort((a, b) => b.value.compareTo(a.value));
  final chon = gop.take(limit).toList();
  final lonNhat = chon.first.value;

  return [
    for (final g in chon)
      MatchReason(
        dimension: g.label,
        value: g.value,
        ratio: g.value / lonNhat,
        sentence: sentenceForDimension(g.label),
      ),
  ];
}

/// Các câu giải thích, đã bỏ chiều chưa có mệnh đề. Dùng cho giao diện.
List<String> matchSentences(
  PreferenceProfile profile,
  Food food, {
  int limit = 3,
}) => [
  for (final r in matchReasons(profile, food, limit: limit))
    if (r.sentence != null) r.sentence!,
];
