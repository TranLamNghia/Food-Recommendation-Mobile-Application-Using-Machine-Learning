import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import 'survey_progress.dart';

/// Vùng chân màn hình — layer `Footer_Backgound` (2:15) trong Figma.
///
/// Nền là một dải chuyển sắc dọc cao 264 trên khung 844: **trong suốt ở mép
/// trên**, đặc dần xuống `#4F4E4E` ở đáy. Phần trên trong suốt để hạt của
/// vùng "Chưa biết" (xem `SwipeBurst.bottomOverflow`) trôi xuống bên dưới và
/// chìm dần vào màu xám, thay vì bị cắt cụt ở mép trên. Bên trong là khối `Introduce`
/// (1:4) đặt ở toạ độ 48, 68 với khổ 310 × 100 — chỗ đặt thanh tiến độ và
/// dòng nhắn nhờ người dùng phân loại món.
class SurveyFooter extends StatelessWidget {
  const SurveyFooter({super.key, required this.done, required this.total});

  /// Tỷ lệ chiều cao của vùng chân trên toàn khung thiết kế.
  static const heightRatio = 264 / 844;

  /// Khổ gốc của vùng chân trong Figma.
  static const _designSize = Size(390, 264);

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          // Same grey at both ends, only the alpha changes. Over the white
          // scaffold this blends to exactly the old white → grey ramp, so the
          // footer looks unchanged wherever nothing sits behind it. Fading
          // from transparent *white* instead would wash the middle out.
          colors: [
            AppColors.footerBottom.withValues(alpha: 0),
            AppColors.footerBottom,
          ],
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final sx = constraints.maxWidth / _designSize.width;
          final sy = constraints.maxHeight / _designSize.height;

          return Column(
            children: [
              SizedBox(height: 68 * sy),
              SizedBox(
                height: 100 * sy,
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: 48 * sx),
                  child: _Introduce(done: done, total: total),
                ),
              ),
              // Phần dưới khối `Introduce` để trống, đúng như bản thiết kế.
              // Màn hình này thuần cử chỉ: mọi thao tác đều bằng vuốt thẻ.
              Expanded(child: SizedBox(height: bottomInset)),
            ],
          );
        },
      ),
    );
  }
}

/// Khối `Introduce` (1:4) — 310 × 100.
///
/// Dòng nhắn đặt phía trên, thanh tiến độ phía dưới. Thứ tự này không tuỳ
/// tiện: nền chuyển sắc sáng ở trên và tối dần xuống dưới, nên chữ — thứ cần
/// độ tương phản nhất — phải nằm ở nửa sáng, còn thanh tiến độ thì đọc được
/// ở cả hai vùng nhờ cặp rãnh tối / phần chạy trắng.
class _Introduce extends StatelessWidget {
  const _Introduce({required this.done, required this.total});

  /// Câu nhắn. Cố ý viết giọng đời thường, vì đây là lúc phải xin người dùng
  /// bỏ ra hai phút làm một việc chưa thấy ngay lợi ích.
  static const _note =
      'Quẹo trái quẹo phải giúp tụi mình phân loại món nha — '
      'app học gu bạn từ đây đó 🤙';

  final int done;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            _note,
            style: TextStyle(
              fontFamily: 'Afacad',
              fontVariations: const [FontVariation('wght', 600)],
              fontSize: 15,
              height: 1.35,
              color: AppColors.textPrimary.withValues(alpha: 0.88),
            ),
          ),
        ),
        SurveyProgress(done: done, total: total),
      ],
    );
  }
}
