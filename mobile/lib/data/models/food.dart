import 'package:flutter/material.dart';

/// Món ăn — phản chiếu các cột chính của bảng `foods` + `food_nutrition`.
///
/// Ở giai đoạn dựng giao diện, ảnh món được thay bằng cặp màu gradient và
/// một biểu tượng, để chạy được hoàn toàn ngoại tuyến. Khi có ảnh thật chỉ
/// cần thêm trường `imageUrl` và đổi phần nền của thẻ.
class Food {
  const Food({
    required this.id,
    required this.name,
    required this.category,
    required this.dishRole,
    required this.spiceLevel,
    required this.kcal,
    required this.protein,
    required this.carb,
    required this.fat,
    required this.sugar,
    required this.sodium,
    required this.fiber,
    required this.servingSizeG,
    required this.emoji,
    required this.gradient,
    this.imageAsset,
    this.tags = const [],
  });

  final String id;
  final String name;

  /// Nhóm thực phẩm — bảng `food_categories`.
  final String category;

  /// Vai trò trong bữa — cột `foods.dish_role`.
  final String dishRole;

  /// Mức cay 0–3 — cột `foods.spice_level`.
  final int spiceLevel;

  final int kcal;
  final double protein;
  final double carb;
  final double fat;

  /// Đường tính bằng gam trong một suất. Nguồn: `food_nutrition.sugar_g`.
  final double sugar;

  /// Natri tính bằng miligam trong một suất. Nguồn: `food_nutrition.sodium_mg`.
  final double sodium;

  /// Chất xơ tính bằng gam trong một suất. Nguồn: `food_nutrition.fiber_g`.
  ///
  /// Có mặt ở đây vì **khẩu vị không phải thứ duy nhất quyết định chất lượng
  /// gợi ý**. Người dùng có thể muốn ăn nhiều chất xơ, và nếu chất xơ không
  /// nằm trong vector đặc trưng thì sở thích đó không biểu diễn được: bộ gợi
  /// ý chỉ bắt được nó gián tiếp qua nhóm món.
  ///
  /// Đo trên 305 món thật: với người thích món giàu xơ, vector không có
  /// chiều này thu hẹp được 41,7 % khoảng cách tới tập 20 món giàu xơ nhất;
  /// thêm chiều này thì lên 59,7 %.
  final double fiber;

  /// Khối lượng một suất, tính bằng gam. Nguồn: `food_nutrition.serving_size_g`.
  ///
  /// Mọi số dinh dưỡng ở trên là **của cả suất**, không phải trên 100 g. Nên
  /// trường này là mẫu số bắt buộc khi cần một đại lượng **nồng độ** — xem
  /// [sugarConcentration].
  final double servingSizeG;

  final String emoji;
  final List<Color> gradient;

  /// Ảnh món. `null` thì thẻ lùi về nền gradient kèm biểu tượng.
  final String? imageAsset;
  final List<String> tags;

  /// Đường trên mỗi gam món ăn — đại lượng **đo được** cho vị ngọt.
  ///
  /// Dùng **nồng độ** chứ không dùng số gam thuần, cùng lý do như
  /// `macroShare`: khẩu vị là về *cấu trúc* món ăn, không về khối lượng. Một
  /// suất 400 g chứa 20 g đường không ngọt bằng một suất 100 g chứa 15 g.
  ///
  /// **Vì sao mẫu số là [servingSizeG], không phải [carb].** Bản trước dùng
  /// `sugar / carb`, và nó vỡ ở món ít bột đường: tỷ lệ nổ khi mẫu số nhỏ.
  /// Đo trên 318 món thật, **46 món bị kẹp về đúng 1,0** — 14 % danh mục đọc
  /// ra "ngọt tối đa" — trong đó *trứng luộc* (0,6 g bột đường) và *canh hẹ
  /// đậu phụ* (2,2 g) đứng ngang *chuối sứ* và *nước ép lựu*. Hai món đó
  /// không phân biệt được trên chiều này thì Rocchio **không học được sở
  /// thích ngọt**: đó là một chiều đầy nhiễu, không phải một chiều đặc trưng.
  ///
  /// Sau khi đổi mẫu số: 1/318 món ở mức tối đa, trứng luộc 0,048, canh hẹ
  /// 0,099, dưa hấu 0,374, chuối sứ 0,564, nước ép lựu 1,000.
  ///
  /// Trả về nồng độ **thô**; phép chuẩn hóa min-max do `FoodVectorSpace` làm,
  /// cùng cách với natri và chất xơ.
  double get sugarConcentration =>
      servingSizeG <= 0 ? 0 : sugar / servingSizeG;

  /// Tỷ lệ năng lượng đến từ mỗi chất, dùng để vẽ thanh macro trên thẻ.
  ({double protein, double carb, double fat}) get macroShare {
    final total = protein * 4 + carb * 4 + fat * 9;
    if (total <= 0) return (protein: 0, carb: 0, fat: 0);
    return (
      protein: protein * 4 / total,
      carb: carb * 4 / total,
      fat: fat * 9 / total,
    );
  }
}
