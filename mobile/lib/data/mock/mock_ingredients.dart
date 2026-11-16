import '../models/ingredient.dart';

typedef _I = IngredientLine;

const _v = Aisle.produce;
const _m = Aisle.meat;
const _s = Aisle.seafood;
const _g = Aisle.staples;
const _d = Aisle.dairySoy;
const _p = Aisle.pantry;

/// Illustrative ingredients for the 30 dishes of `MockFoods.surveyDeck`, keyed
/// by `Food.id`.
///
/// The gram figures are rough per-serving estimates written for the UI build,
/// **not** sourced data: they must not be used for nutrition maths. The same
/// ingredient is spelled identically across dishes so the shopping list can
/// add it up.
abstract final class MockIngredients {
  static List<IngredientLine> of(String foodId) => byFoodId[foodId] ?? const [];

  static const Map<String, List<IngredientLine>> byFoodId = {
    // Phở bò tái
    '1': [
      _I('Bánh phở', 200, _g),
      _I('Thịt bò', 90, _m),
      _I('Xương bò', 150, _m),
      _I('Hành lá', 15, _v),
      _I('Gừng', 5, _v),
      _I('Nước mắm', 10, _p),
    ],
    // Bún chả Hà Nội
    '2': [
      _I('Bún tươi', 180, _g),
      _I('Thịt heo', 130, _m),
      _I('Rau sống', 60, _v),
      _I('Đu đủ xanh', 30, _v),
      _I('Tỏi', 5, _v),
      _I('Nước mắm', 20, _p),
      _I('Đường', 10, _p),
    ],
    // Cơm tấm sườn nướng
    '3': [
      _I('Gạo tấm', 100, _g),
      _I('Sườn heo', 150, _m),
      _I('Dưa leo', 40, _v),
      _I('Cà chua', 30, _v),
      _I('Hành lá', 10, _v),
      _I('Nước mắm', 15, _p),
    ],
    // Gỏi cuốn tôm thịt
    '4': [
      _I('Bánh tráng', 30, _g),
      _I('Bún tươi', 60, _g),
      _I('Tôm', 60, _s),
      _I('Thịt heo', 50, _m),
      _I('Rau sống', 50, _v),
      _I('Đậu phộng', 10, _p),
    ],
    // Canh chua cá lóc
    '5': [
      _I('Cá lóc', 120, _s),
      _I('Cà chua', 60, _v),
      _I('Thơm (dứa)', 50, _v),
      _I('Giá đỗ', 40, _v),
      _I('Đậu bắp', 40, _v),
      _I('Me chua', 15, _p),
    ],
    // Thịt kho tàu
    '6': [
      _I('Thịt heo', 150, _m),
      _I('Trứng', 60, _m),
      _I('Nước dừa', 120, _p),
      _I('Nước mắm', 15, _p),
      _I('Đường', 8, _p),
    ],
    // Rau muống xào tỏi
    '7': [
      _I('Rau muống', 200, _v),
      _I('Tỏi', 10, _v),
      _I('Dầu ăn', 10, _p),
      _I('Nước mắm', 5, _p),
    ],
    // Cá kho tộ
    '8': [
      _I('Cá basa', 150, _s),
      _I('Thịt heo', 30, _m),
      _I('Hành lá', 10, _v),
      _I('Ớt', 5, _v),
      _I('Nước mắm', 15, _p),
      _I('Đường', 8, _p),
    ],
    // Bánh xèo miền Tây
    '9': [
      _I('Bột bánh xèo', 80, _g),
      _I('Tôm', 60, _s),
      _I('Thịt heo', 50, _m),
      _I('Giá đỗ', 60, _v),
      _I('Rau sống', 60, _v),
      _I('Dầu ăn', 15, _p),
    ],
    // Chả giò
    '10': [
      _I('Bánh tráng', 30, _g),
      _I('Thịt heo', 80, _m),
      _I('Miến', 15, _g),
      _I('Cà rốt', 30, _v),
      _I('Trứng', 20, _m),
      _I('Dầu ăn', 20, _p),
    ],
    // Bún bò Huế
    '11': [
      _I('Bún tươi', 200, _g),
      _I('Thịt bò', 80, _m),
      _I('Giò heo', 80, _m),
      _I('Sả', 15, _v),
      _I('Ớt', 5, _v),
      _I('Mắm ruốc', 8, _p),
    ],
    // Hủ tiếu Nam Vang
    '12': [
      _I('Hủ tiếu', 180, _g),
      _I('Thịt heo', 70, _m),
      _I('Tôm', 50, _s),
      _I('Trứng cút', 30, _m),
      _I('Giá đỗ', 40, _v),
      _I('Hẹ', 10, _v),
    ],
    // Cơm gà Hội An
    '13': [
      _I('Gạo', 100, _g),
      _I('Thịt gà', 130, _m),
      _I('Hành tây', 30, _v),
      _I('Rau răm', 10, _v),
      _I('Nghệ', 3, _p),
    ],
    // Bò lúc lắc
    '14': [
      _I('Thịt bò', 150, _m),
      _I('Ớt chuông', 60, _v),
      _I('Hành tây', 50, _v),
      _I('Tỏi', 8, _v),
      _I('Dầu ăn', 10, _p),
    ],
    // Đậu hũ sốt cà chua
    '15': [
      _I('Đậu hũ', 200, _d),
      _I('Cà chua', 120, _v),
      _I('Hành lá', 10, _v),
      _I('Dầu ăn', 10, _p),
      _I('Nước mắm', 8, _p),
    ],
    // Canh bí đao nấu tôm
    '16': [
      _I('Bí đao', 200, _v),
      _I('Tôm', 60, _s),
      _I('Hành lá', 10, _v),
      _I('Nước mắm', 8, _p),
    ],
    // Nem nướng Nha Trang
    '17': [
      _I('Thịt heo', 130, _m),
      _I('Bánh tráng', 40, _g),
      _I('Rau sống', 70, _v),
      _I('Dưa leo', 40, _v),
      _I('Đậu phộng', 10, _p),
    ],
    // Bánh mì thịt nướng
    '18': [
      _I('Bánh mì', 90, _g),
      _I('Thịt heo', 80, _m),
      _I('Dưa leo', 30, _v),
      _I('Cà rốt', 20, _v),
      _I('Ngò rí', 5, _v),
    ],
    // Xôi gà
    '19': [
      _I('Gạo nếp', 110, _g),
      _I('Thịt gà', 90, _m),
      _I('Hành phi', 8, _p),
      _I('Dầu ăn', 5, _p),
    ],
    // Cháo lòng
    '20': [
      _I('Gạo', 60, _g),
      _I('Lòng heo', 100, _m),
      _I('Hành lá', 10, _v),
      _I('Gừng', 5, _v),
      _I('Nước mắm', 8, _p),
    ],
    // Mì Quảng
    '21': [
      _I('Mì Quảng', 180, _g),
      _I('Tôm', 50, _s),
      _I('Thịt heo', 60, _m),
      _I('Rau sống', 50, _v),
      _I('Đậu phộng', 10, _p),
      _I('Bánh tráng', 15, _g),
    ],
    // Lẩu thái hải sản
    '22': [
      _I('Tôm', 80, _s),
      _I('Mực', 80, _s),
      _I('Nghêu', 100, _s),
      _I('Nấm', 60, _v),
      _I('Rau muống', 80, _v),
      _I('Sả', 15, _v),
      _I('Bún tươi', 100, _g),
    ],
    // Tôm rang me
    '23': [
      _I('Tôm', 150, _s),
      _I('Me chua', 20, _p),
      _I('Tỏi', 8, _v),
      _I('Đường', 10, _p),
      _I('Dầu ăn', 10, _p),
    ],
    // Gà kho gừng
    '24': [
      _I('Thịt gà', 150, _m),
      _I('Gừng', 15, _v),
      _I('Hành lá', 10, _v),
      _I('Nước mắm', 15, _p),
      _I('Đường', 5, _p),
    ],
    // Salad rau trộn dầu giấm
    '25': [
      _I('Xà lách', 100, _v),
      _I('Cà chua', 60, _v),
      _I('Dưa leo', 60, _v),
      _I('Hành tây', 20, _v),
      _I('Dầu ô liu', 10, _p),
      _I('Giấm', 8, _p),
    ],
    // Trứng chiên hành
    '26': [
      _I('Trứng', 110, _m),
      _I('Hành lá', 15, _v),
      _I('Dầu ăn', 10, _p),
      _I('Nước mắm', 5, _p),
    ],
    // Sữa chua nếp cẩm
    '27': [_I('Sữa chua', 100, _d), _I('Nếp cẩm', 40, _g), _I('Đường', 10, _p)],
    // Chè đậu xanh
    '28': [
      _I('Đậu xanh', 50, _d),
      _I('Đường', 25, _p),
      _I('Nước cốt dừa', 30, _p),
    ],
    // Bánh cuốn nóng
    '29': [
      _I('Bột gạo', 80, _g),
      _I('Thịt heo', 50, _m),
      _I('Nấm mèo', 10, _v),
      _I('Hành phi', 8, _p),
      _I('Nước mắm', 15, _p),
    ],
    // Canh rau ngót thịt bằm
    '30': [
      _I('Rau ngót', 120, _v),
      _I('Thịt heo', 50, _m),
      _I('Nước mắm', 8, _p),
    ],
  };
}
