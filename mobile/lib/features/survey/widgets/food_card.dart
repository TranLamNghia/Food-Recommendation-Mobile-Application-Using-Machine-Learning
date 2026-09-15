import 'package:flutter/material.dart';

import '../../../data/models/food.dart';
import 'dish_icon.dart';

/// Thẻ món ăn — dựng theo node `Card` (5:32) trong Figma.
///
/// Mọi số đo trong lớp này lấy trực tiếp từ bản thiết kế ở khổ gốc
/// **198 × 280**, rồi nhân với hệ số [_Metrics.scale] theo bề rộng thực tế
/// của thẻ. Giữ nguyên số gốc để đối chiếu lại với Figma khi thiết kế đổi,
/// thay vì quy đổi sẵn thành số đã nhân.
class FoodCard extends StatelessWidget {
  const FoodCard({
    super.key,
    required this.food,
    this.parallax = Offset.zero,
    this.elevated = true,
  });

  /// Khổ gốc của thẻ trong Figma. Tỷ lệ này được giữ nguyên khi phóng to.
  static const designSize = Size(198, 280);
  static const aspectRatio = 198 / 280;

  final Food food;

  /// Quãng kéo đã chuẩn hóa (mỗi trục trong đoạn [-1, 1]) — ảnh dịch ngược
  /// chiều thẻ một chút để tạo chiều sâu.
  final Offset parallax;

  final bool elevated;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final m = _Metrics(constraints.maxWidth);

        return DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(m.radius),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: elevated ? 0.28 : 0.14),
                blurRadius: m.s(elevated ? 28 : 16),
                offset: Offset(0, m.s(elevated ? 14 : 7)),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(m.radius),
            child: Stack(
              fit: StackFit.expand,
              children: [
                _Image(food: food, parallax: parallax),
                const _BottomGradient(),
                _Content(food: food, m: m),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// Quy đổi số đo thiết kế sang số đo thực tế trên máy.
class _Metrics {
  _Metrics(double width) : scale = width / FoodCard.designSize.width;

  final double scale;

  double s(double designValue) => designValue * scale;

  double get radius => s(12);
}

class _Image extends StatelessWidget {
  const _Image({required this.food, required this.parallax});

  final Food food;
  final Offset parallax;

  @override
  Widget build(BuildContext context) {
    final asset = food.imageAsset;

    // Ảnh được phóng nhẹ rồi dịch theo cú vuốt. Phải phóng trước, nếu không
    // mép ảnh sẽ hở ra khi dịch.
    Widget withParallax(Widget child) => Transform.scale(
      scale: 1.06,
      child: Transform.translate(offset: parallax * -10, child: child),
    );

    if (asset == null) {
      // Chưa có ảnh món: lùi về nền gradient kèm biểu tượng, để thẻ vẫn đọc
      // được thay vì hiện ô trống.
      return withParallax(
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: food.gradient,
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Center(
            child: Text(food.emoji, style: const TextStyle(fontSize: 76)),
          ),
        ),
      );
    }

    return withParallax(
      Image.asset(
        asset,
        fit: BoxFit.cover,
        // Nền xanh của layer `Image` trong Figma, lộ ra trong lúc ảnh đang tải.
        errorBuilder: (context, error, stack) =>
            const ColoredBox(color: Color(0xFF006EFF)),
      ),
    );
  }
}

/// Lớp chuyển sắc ở đáy thẻ — layer `Gradient` (5:7).
///
/// Bắt đầu ở 60.53 % chiều cao, chạy từ trong suốt xuống `#121212`. Đây là
/// thứ giữ cho chữ trắng đọc được trên mọi tấm ảnh.
class _BottomGradient extends StatelessWidget {
  const _BottomGradient();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment(0, 0.2106), // 60.53 % tính từ đỉnh
          end: Alignment.bottomCenter,
          colors: [Color(0x00121212), Color(0xFF121212)],
        ),
      ),
    );
  }
}

/// Khối chữ ở đáy thẻ — layer `Content` (5:9), khổ gốc 179 × 58.
class _Content extends StatelessWidget {
  const _Content({required this.food, required this.m});

  final Food food;
  final _Metrics m;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: m.s(11),
      bottom: m.s(23),
      width: m.s(179),
      height: m.s(58),
      child: Stack(
        children: [
          Positioned(
            left: 0,
            top: 0,
            right: m.s(5),
            // Thẻ chỉ rộng bằng nửa màn hình nên tên món dài như "Cơm tấm
            // sườn nướng" không vừa ở cỡ 24. Cho chữ tự co lại thay vì cắt
            // bằng dấu ba chấm — tên món là thứ duy nhất người dùng dựa vào
            // để quyết định, không được phép mất chữ.
            child: FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                food.name,
                maxLines: 1,
                style: TextStyle(
                  fontFamily: 'Display',
                  fontVariations: const [FontVariation('wght', 900)],
                  fontSize: m.s(24),
                  height: 34 / 24,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            top: m.s(39),
            child: DishIcon(size: Size(m.s(17), m.s(13))),
          ),
          Positioned(
            left: m.s(25),
            top: m.s(37),
            right: m.s(53),
            child: Text(
              food.category,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontFamily: 'Afacad',
                fontVariations: const [FontVariation('wght', 600)],
                fontSize: m.s(12),
                height: 18 / 12,
                letterSpacing: m.s(0.2),
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
