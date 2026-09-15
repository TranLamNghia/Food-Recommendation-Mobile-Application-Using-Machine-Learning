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
    required this.cookingMethod,
    required this.dishRole,
    required this.spiceLevel,
    required this.kcal,
    required this.protein,
    required this.carb,
    required this.fat,
    required this.emoji,
    required this.gradient,
    this.imageAsset,
    this.tags = const [],
  });

  final int id;
  final String name;

  /// Nhóm thực phẩm — bảng `food_categories`.
  final String category;

  /// Phương pháp chế biến — cột `foods.cooking_method`.
  final String cookingMethod;

  /// Vai trò trong bữa — cột `foods.dish_role`.
  final String dishRole;

  /// Mức cay 0–3 — cột `foods.spice_level`.
  final int spiceLevel;

  final int kcal;
  final double protein;
  final double carb;
  final double fat;

  final String emoji;
  final List<Color> gradient;

  /// Ảnh món. `null` thì thẻ lùi về nền gradient kèm biểu tượng.
  final String? imageAsset;
  final List<String> tags;

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
