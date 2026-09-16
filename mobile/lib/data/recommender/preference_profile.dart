import 'dart:math' as math;

import '../models/food.dart';
import '../models/swipe_action.dart';
import 'food_vector.dart';

/// Hồ sơ sở thích của người dùng — vector trọng số tổng hợp từ lịch sử vuốt.
///
/// Đây là Giai đoạn 1 của chiến lược khởi đầu nguội. Sau phiên khảo sát khẩu
/// vị, hệ thống chưa có đủ dữ liệu để huấn luyện một mô hình học máy riêng —
/// khoảng 30 mẫu trên vài chục chiều đặc trưng thì mô hình sẽ học thuộc đúng
/// 30 món đó thay vì học ra quy luật. Thay vào đó, sở thích được tóm lại
/// thành **một vector duy nhất**:
///
/// ```text
///          Σ w(aᵢ) · vᵢ
///   p_u = ──────────────       w(like) = +1 , w(neutral) = 0 , w(dislike) = −1
///          Σ | w(aᵢ) |         aᵢ = unknown → loại khỏi tổng
/// ```
///
/// Công thức này là thuật toán **Rocchio** trong mô hình không gian vector
/// (Manning và cộng sự, *Introduction to Information Retrieval*, chương 9),
/// còn gọi là bộ phân lớp trọng tâm gần nhất. Bản chất nó vẫn là một mô hình
/// tuyến tính học từ chính 30 mẫu ấy, chỉ khác ở chỗ nghiệm tính bằng công
/// thức đóng thay vì tối ưu lặp — nhờ vậy ổn định khi dữ liệu ít, cho kết quả
/// tức thì, và giải thích được với người dùng.
class PreferenceProfile {
  const PreferenceProfile({
    required this.space,
    required this.weights,
    required this.signalCount,
  });

  /// Dựng hồ sơ từ kết quả một phiên vuốt.
  ///
  /// Lượt vuốt `unknown` bị loại hoàn toàn: người dùng nói *chưa từng ăn*,
  /// đó không phải tín hiệu về khẩu vị nên đưa vào sẽ làm nhiễu vector.
  factory PreferenceProfile.fromSwipes({
    required FoodVectorSpace space,
    required List<({Food food, SwipeAction action})> swipes,
  }) {
    final sum = List<double>.filled(space.length, 0);
    var totalAbsWeight = 0.0;
    var used = 0;

    for (final s in swipes) {
      final w = _rocchioWeight(s.action);
      if (w == null) continue;

      used++;
      totalAbsWeight += w.abs();

      final v = space.encode(s.food);
      for (var i = 0; i < sum.length; i++) {
        sum[i] += w * v[i];
      }
    }

    // Vuốt `neutral` có trọng số 0 nên đóng góp vào mẫu số bằng 0. Nếu cả
    // phiên chỉ toàn `neutral` thì mẫu số bằng 0 — khi đó giữ vector rỗng,
    // mọi món sẽ nhận cùng một điểm và thứ tự do các tiêu chí khác quyết định.
    if (totalAbsWeight > 0) {
      for (var i = 0; i < sum.length; i++) {
        sum[i] /= totalAbsWeight;
      }
    }

    return PreferenceProfile(space: space, weights: sum, signalCount: used);
  }

  final FoodVectorSpace space;

  /// Vector sở thích `p_u`. Chiều dương nghĩa là người dùng thiên về đặc
  /// trưng đó, chiều âm nghĩa là né tránh.
  final List<double> weights;

  /// Số tín hiệu đã dùng để dựng hồ sơ — không tính lượt `unknown`.
  final int signalCount;

  /// Hồ sơ rỗng, dùng cho người dùng chưa vuốt lượt nào (Giai đoạn 0).
  factory PreferenceProfile.empty(FoodVectorSpace space) => PreferenceProfile(
    space: space,
    weights: List<double>.filled(space.length, 0),
    signalCount: 0,
  );

  bool get isEmpty => signalCount == 0 || weights.every((w) => w == 0);

  /// Chấm điểm mức độ ưa thích của một món, đưa về đoạn [0, 1].
  ///
  /// Độ tương đồng cosin nhận giá trị trong [-1, 1]; phép `(1 + cos) / 2`
  /// đưa nó về [0, 1] để dùng chung thang với điểm của mô hình học máy ở
  /// Giai đoạn 2, nhờ vậy công thức trộn dần giữa hai giai đoạn không phải
  /// quy đổi thang đo.
  double score(Food food) {
    if (isEmpty) return 0.5;
    final cos = cosineSimilarity(weights, space.encode(food));
    return (1 + cos) / 2;
  }

  /// Bản sao của hồ sơ sau khi xoay nhẹ theo một hướng ngẫu nhiên.
  ///
  /// Dùng cho nhóm **thăm dò** trong cơ chế 70-30: thay vì chèn món ngẫu
  /// nhiên như ε-greedy, hệ thống xếp hạng theo chính vector sở thích đã làm
  /// nhiễu, nên món thăm dò rơi vào *vùng lân cận* khẩu vị chứ không rơi ra
  /// chỗ vô lý. Người dùng vì vậy dễ chấp nhận hơn, và khi họ từ chối thì
  /// thông tin thu được cũng nhiều hơn — biết ranh giới khẩu vị nằm ở đâu.
  ///
  /// [delta] là biên độ nhiễu δ. Quá nhỏ thì món "mới" gần như trùng món cũ;
  /// quá lớn thì suy biến thành chọn ngẫu nhiên, mất hết ưu điểm.
  PreferenceProfile jittered({
    required double delta,
    required math.Random rng,
  }) {
    if (isEmpty) return this;

    // Nhiễu lấy từ phân phối chuẩn rồi chuẩn hóa về vector đơn vị, để hướng
    // xoay rải đều mọi phía thay vì thiên về các góc của khối lập phương —
    // điều sẽ xảy ra nếu lấy nhiễu đều trên từng chiều.
    final noise = List<double>.generate(weights.length, (_) => _gaussian(rng));
    var norm = 0.0;
    for (final n in noise) {
      norm += n * n;
    }
    norm = math.sqrt(norm);
    if (norm == 0) return this;

    final rotated = <double>[];
    for (var i = 0; i < weights.length; i++) {
      rotated.add(weights[i] + delta * noise[i] / norm);
    }

    return PreferenceProfile(
      space: space,
      weights: rotated,
      signalCount: signalCount,
    );
  }

  /// Các đặc trưng người dùng thiên về nhất, xếp giảm dần theo trọng số.
  ///
  /// Đây là phần **giải thích được** của mô hình nội dung: có thể nói thẳng
  /// với người dùng *"gợi ý món này vì bạn thích đồ nướng và món nhiều đạm"*
  /// thay vì để họ đoán.
  List<({String label, double weight})> topTraits({int limit = 4}) {
    final labels = space.labels;
    final entries = <({String label, double weight})>[];

    for (var i = 0; i < weights.length; i++) {
      if (weights[i] <= 0) continue;
      entries.add((label: labels[i], weight: weights[i]));
    }

    entries.sort((a, b) => b.weight.compareTo(a.weight));
    return entries.take(limit).toList();
  }
}

/// Trọng số Rocchio theo hành động vuốt. `null` nghĩa là loại khỏi tổng.
///
/// Khác với [SwipeAction.label] — vốn là nhãn ưa thích trong đoạn [0, 1] dùng
/// làm đích cho mô hình học máy ở Giai đoạn 2 — trọng số ở đây nhận cả giá
/// trị âm, vì Rocchio cần kéo vector **ra xa** nhóm món bị ghét.
double? _rocchioWeight(SwipeAction action) => switch (action) {
  SwipeAction.like => 1.0,
  SwipeAction.neutral => 0.0,
  SwipeAction.dislike => -1.0,
  SwipeAction.unknown => null,
};

/// Một mẫu từ phân phối chuẩn chuẩn tắc theo phép biến đổi Box-Muller.
double _gaussian(math.Random rng) {
  // `nextDouble` trả về [0, 1) nên có thể ra đúng 0, mà log(0) là vô cực.
  // Đẩy cận dưới lên một lượng rất nhỏ để phép lấy log luôn hợp lệ.
  final u1 = math.max(rng.nextDouble(), 1e-12);
  final u2 = rng.nextDouble();
  return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2);
}
