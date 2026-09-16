import 'food.dart';
import 'meal_plan.dart';

/// Một dòng nhật ký ăn uống — bảng `food_diary`.
///
/// Nhật ký ghi lại món người dùng **thật sự đã ăn**, không phải món hệ thống
/// gợi ý. Hai thứ này lệch nhau chính là dữ liệu quý nhất: khoảng cách giữa
/// thực đơn đề xuất và bữa ăn thực tế cho biết gợi ý sát hay chưa sát.
///
/// Bảng này **không** giữ khóa ngoại trỏ tới `meal_plan_items`. Người dùng
/// có thể ăn một món hoàn toàn ngoài thực đơn, và món trong thực đơn có thể
/// bị ăn ở bữa khác với bữa được xếp. Tỷ lệ tuân thủ thực đơn vì vậy tính
/// bằng cách ghép theo khóa tự nhiên (ngày, bữa, món) chứ không theo khóa
/// ngoại — xem `DATABASE_DESIGN.md` mục 6.2.
class DiaryEntry {
  DiaryEntry({
    required this.food,
    required this.meal,
    required this.ateAt,
    this.portion = 1.0,
    this.rating,
  });

  final Food food;
  final MealType meal;
  final DateTime ateAt;

  /// Số suất đã ăn. 1,0 là một khẩu phần chuẩn; 0,5 là ăn nửa suất.
  final double portion;

  /// Điểm đánh giá sau khi ăn, từ 1 đến 5 sao. `null` là chưa đánh giá.
  ///
  /// Đây là nguồn tín hiệu **mạnh nhất** trong bảng quy đổi nhãn, trọng số
  /// mẫu 1,0 — vì người dùng đã thật sự ăn rồi mới chấm, khác hẳn lượt vuốt
  /// chỉ nhìn ảnh mà đoán.
  int? rating;

  double get kcal => food.kcal * portion;
  double get protein => food.protein * portion;
  double get carb => food.carb * portion;
  double get fat => food.fat * portion;

  /// Nhãn ưa thích quy về đoạn [0, 1] để đưa vào tập huấn luyện.
  ///
  /// Có đánh giá sao thì quy tuyến tính từ 1–5 sao về 0,00–1,00. Chưa đánh
  /// giá thì bản thân việc đã ăn đã là tín hiệu dương, nhận nhãn 0,8 — thấp
  /// hơn 5 sao nhưng cao hơn mức trung tính.
  double get trainingLabel => rating == null ? 0.8 : (rating! - 1) / 4;

  /// Trọng số mẫu tương ứng — đánh giá sao đáng tin hơn suy luận từ hành vi.
  double get sampleWeight => rating == null ? 0.9 : 1.0;
}
