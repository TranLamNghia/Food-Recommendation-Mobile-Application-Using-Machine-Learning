import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_motion.dart';

/// Khung chung cho mọi bước khai báo hồ sơ.
///
/// Bố cục cố định giúp người dùng không phải học lại mỗi màn: nút lùi và
/// thanh tiến độ ở trên, câu hỏi lớn, dòng giải thích, phần nhập liệu ở giữa,
/// và một nút hành động chiếm trọn bề ngang ở đáy. Chỉ phần giữa thay đổi.
class OnboardingScaffold extends StatelessWidget {
  const OnboardingScaffold({
    super.key,
    required this.progress,
    required this.title,
    required this.child,
    this.subtitle,
    this.onBack,
    this.actionLabel = 'Tiếp theo',
    this.onAction,
    this.scrollable = false,
    this.center = false,
  });

  /// Tiến độ toàn luồng trong đoạn [0, 1].
  final double progress;

  final String title;
  final String? subtitle;
  final Widget child;

  /// `null` thì nút lùi bị ẩn — dùng cho bước đầu tiên.
  final VoidCallback? onBack;

  final String actionLabel;

  /// `null` thì nút hành động chuyển sang trạng thái mờ và không bấm được.
  /// Dùng để chặn đi tiếp khi người dùng chưa chọn gì.
  final VoidCallback? onAction;

  /// Bật khi phần giữa cao hơn màn hình, ví dụ danh sách bệnh lý.
  final bool scrollable;

  /// Căn phần giữa vào chính giữa khoảng trống thay vì dán ngay dưới câu hỏi.
  /// Bật cho bánh xe chọn số, tắt cho danh sách lựa chọn — danh sách đọc tự
  /// nhiên hơn khi nằm sát câu hỏi.
  final bool center;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    final header = Column(
      children: [
        Text(title, style: text.displaySmall, textAlign: TextAlign.center),
        if (subtitle != null) ...[
          const SizedBox(height: 10),
          Text(subtitle!, style: text.bodyLarge, textAlign: TextAlign.center),
        ],
      ],
    );

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _TopBar(progress: progress, onBack: onBack),
            Expanded(
              child: scrollable
                  ? SingleChildScrollView(
                      // Chừa đáy rộng hơn để thẻ cuối cuộn lên khỏi nút hành
                      // động, thay vì dừng đúng mép nút và trông như bị cắt.
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
                      child: Column(
                        children: [header, const SizedBox(height: 28), child],
                      ),
                    )
                  : Padding(
                      padding: const EdgeInsets.fromLTRB(24, 8, 24, 16),
                      child: Column(
                        children: [
                          header,
                          const SizedBox(height: 28),
                          if (center)
                            Expanded(child: Center(child: child))
                          else
                            child,
                        ],
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
              child: FilledButton(
                onPressed: onAction,
                child: Text(actionLabel),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Nút lùi và thanh tiến độ.
///
/// Thanh chạy mượt giữa hai bước thay vì nhảy — người dùng thấy được mình vừa
/// tiến bao nhiêu và còn bao xa, đó là thứ giữ họ đi hết một luồng dài.
class _TopBar extends StatelessWidget {
  const _TopBar({required this.progress, required this.onBack});

  final double progress;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 12, 24, 12),
      child: Row(
        children: [
          SizedBox(
            width: 48,
            height: 48,
            child: AnimatedOpacity(
              opacity: onBack == null ? 0 : 1,
              duration: AppMotion.quick,
              child: IconButton(
                onPressed: onBack,
                icon: const Icon(Icons.arrow_back_rounded),
                color: AppColors.textPrimary,
                iconSize: 26,
              ),
            ),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: TweenAnimationBuilder<double>(
                tween: Tween(begin: 0, end: progress.clamp(0.0, 1.0)),
                duration: AppMotion.page,
                curve: AppMotion.emphasized,
                builder: (context, value, _) => LinearProgressIndicator(
                  value: value,
                  minHeight: 6,
                  backgroundColor: AppColors.surfaceMuted,
                  valueColor: const AlwaysStoppedAnimation(AppColors.ink),
                ),
              ),
            ),
          ),
          // Chừa khoảng đối xứng với nút lùi để thanh tiến độ nằm giữa.
          const SizedBox(width: 24),
        ],
      ),
    );
  }
}
