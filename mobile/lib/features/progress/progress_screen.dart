import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/health_profile.dart';
import '../../data/session.dart';

/// Tiến trình sức khỏe và mức độ hệ thống đã hiểu người dùng.
///
/// Màn hình này trả lời hai câu hỏi khác nhau. Câu thứ nhất thuộc về người
/// dùng: *thể trạng của tôi đang ở đâu*. Câu thứ hai thuộc về hệ thống:
/// *mô hình đã học được bao nhiêu về tôi rồi*. Câu thứ hai hiếm khi được
/// hiển thị trong các ứng dụng dinh dưỡng, nhưng ở đây nó là phần cốt lõi —
/// nó cho người dùng thấy dữ liệu họ đóng góp đang đi về đâu.
class ProgressScreen extends StatelessWidget {
  const ProgressScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final profile = session.profile;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            Text(
              'Tiến trình',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 18),
            _BodyCard(profile: profile),
            const SizedBox(height: 14),
            _LearningCard(session: session),
            const SizedBox(height: 14),
            _TasteCard(session: session),
          ],
        ),
      ),
    );
  }
}

/// Chỉ số thể trạng: BMI kèm phân loại theo ngưỡng châu Á.
class _BodyCard extends StatelessWidget {
  const _BodyCard({required this.profile});

  final HealthProfile profile;

  /// Phân loại BMI theo ngưỡng dành riêng cho người châu Á.
  ///
  /// Khác ngưỡng WHO chung (thừa cân từ 25, béo phì từ 30). Người châu Á
  /// tích mỡ nội tạng và có nguy cơ chuyển hóa ở mức BMI thấp hơn, nên
  /// WHO Expert Consultation (2004) khuyến nghị hạ ngưỡng xuống 23 và 25.
  /// Dùng ngưỡng quốc tế sẽ xếp nhầm nhiều người Việt đã thừa cân vào nhóm
  /// bình thường, kéo theo hệ thống gợi ý sai mục tiêu.
  static ({String label, Color color}) _classify(double bmi) {
    if (bmi < 18.5) return (label: 'Thiếu cân', color: AppColors.unknown);
    if (bmi < 23) return (label: 'Bình thường', color: AppColors.like);
    if (bmi < 25) return (label: 'Thừa cân', color: AppColors.carb);
    return (label: 'Béo phì', color: AppColors.dislike);
  }

  @override
  Widget build(BuildContext context) {
    final bmi = profile.bmi;
    final bmr = profile.bmr;
    final tdee = profile.tdee;
    final target = profile.energyTarget;

    if (bmi == null || bmr == null || tdee == null || target == null) {
      return const _Card(
        title: 'Chỉ số thể trạng',
        child: Text(
          'Hồ sơ sức khỏe chưa đủ thông tin để tính chỉ số.',
          style: TextStyle(fontSize: 13.5, color: AppColors.textSecondary),
        ),
      );
    }

    final band = _classify(bmi);

    return _Card(
      title: 'Chỉ số thể trạng',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                formatNumber(bmi, 1),
                style: const TextStyle(
                  fontSize: 36,
                  height: 1,
                  color: AppColors.textPrimary,
                  fontVariations: [FontVariation('wght', 700)],
                ),
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'BMI',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 14,
                    color: AppColors.textSecondary,
                    fontVariations: [FontVariation('wght', 600)],
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 7,
                ),
                decoration: BoxDecoration(
                  color: band.color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  band.label,
                  style: TextStyle(
                    fontSize: 13,
                    color: band.color,
                    fontVariations: const [FontVariation('wght', 700)],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'Phân loại theo ngưỡng dành cho người châu Á (WHO, 2004).',
            style: TextStyle(fontSize: 12, color: AppColors.textTertiary),
          ),
          const Divider(height: 26),
          _Row(
            label: 'Chuyển hóa cơ bản (BMR)',
            value: '${formatNumber(bmr)} kcal',
          ),
          const SizedBox(height: 10),
          _Row(
            label: 'Tiêu hao cả ngày (TDEE)',
            value: '${formatNumber(tdee)} kcal',
          ),
          const SizedBox(height: 10),
          _Row(
            label: 'Hạn mức theo mục tiêu',
            value: '${formatNumber(target)} kcal',
            emphasize: true,
          ),
        ],
      ),
    );
  }
}

/// Mức độ trưởng thành dữ liệu — hệ thống đang ở giai đoạn nào.
class _LearningCard extends StatelessWidget {
  const _LearningCard({required this.session});

  final AppSession session;

  @override
  Widget build(BuildContext context) {
    final alpha = session.mlBlendFactor;
    final signals = session.signalCount;

    final stage = switch (alpha) {
      0 => 'Giai đoạn 1 — chấm điểm theo độ tương đồng nội dung',
      1 => 'Giai đoạn 2 — mô hình học máy có giám sát',
      _ => 'Đang chuyển tiếp giữa hai giai đoạn',
    };

    return _Card(
      title: 'Hệ thống đã hiểu bạn tới đâu',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            stage,
            style: const TextStyle(
              fontSize: 14.5,
              height: 1.4,
              color: AppColors.textPrimary,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: alpha,
              minHeight: 7,
              backgroundColor: AppColors.surfaceMuted,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'Hệ số trộn α = ${alpha.toStringAsFixed(2)} · đã thu $signals tín hiệu',
            style: const TextStyle(
              fontSize: 12.5,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 14),
          const Text(
            'Điểm gợi ý hiện là kết hợp có trọng số giữa mô hình học máy và '
            'độ tương đồng với hồ sơ sở thích. Càng nhiều tín hiệu, phần học '
            'máy càng chiếm ưu thế — chuyển dần chứ không nhảy đột ngột, để '
            'thực đơn không thay đổi bất thường.',
            style: TextStyle(
              fontSize: 13,
              height: 1.5,
              color: AppColors.textSecondary,
            ),
          ),
          const Divider(height: 26),
          _Row(
            label: 'Tuân thủ thực đơn',
            value: '${(session.adherenceRate * 100).round()}%',
          ),
          const SizedBox(height: 10),
          _Row(
            label: 'Số món đã ghi nhật ký',
            value: '${session.diary.length}',
          ),
          const SizedBox(height: 10),
          _Row(
            label: 'Số món đã chấm điểm',
            value: '${session.diary.where((e) => e.rating != null).length}',
          ),
        ],
      ),
    );
  }
}

/// Những đặc trưng người dùng thiên về, đọc thẳng từ vector sở thích.
class _TasteCard extends StatelessWidget {
  const _TasteCard({required this.session});

  final AppSession session;

  @override
  Widget build(BuildContext context) {
    final traits = session.preference.topTraits(limit: 6);

    return _Card(
      title: 'Gu ăn của bạn',
      child: traits.isEmpty
          ? const Text(
              'Chưa đủ dữ liệu để dựng hồ sơ sở thích.',
              style: TextStyle(fontSize: 13.5, color: AppColors.textSecondary),
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Đọc trực tiếp từ vector trọng số — đây là phần giải thích '
                  'được của mô hình, không phải phỏng đoán.',
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.5,
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 14),
                for (final t in traits) ...[
                  _TraitBar(
                    label: t.label,
                    weight: t.weight,
                    max: traits.first.weight,
                  ),
                  const SizedBox(height: 10),
                ],
              ],
            ),
    );
  }
}

class _TraitBar extends StatelessWidget {
  const _TraitBar({
    required this.label,
    required this.weight,
    required this.max,
  });

  final String label;
  final double weight;
  final double max;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 13,
                  color: AppColors.textPrimary,
                  fontVariations: [FontVariation('wght', 600)],
                ),
              ),
            ),
            Text(
              weight.toStringAsFixed(2),
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textTertiary,
                fontVariations: [FontVariation('wght', 600)],
              ),
            ),
          ],
        ),
        const SizedBox(height: 5),
        ClipRRect(
          borderRadius: BorderRadius.circular(999),
          child: LinearProgressIndicator(
            value: max <= 0 ? 0 : (weight / max).clamp(0.0, 1.0),
            minHeight: 5,
            backgroundColor: AppColors.surfaceMuted,
            valueColor: const AlwaysStoppedAnimation(AppColors.accent),
          ),
        ),
      ],
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 13.5,
              color: AppColors.textSecondary,
              fontVariations: [FontVariation('wght', 600)],
            ),
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.label,
    required this.value,
    this.emphasize = false,
  });

  final String label;
  final String value;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            label,
            style: const TextStyle(
              fontSize: 13.5,
              color: AppColors.textSecondary,
            ),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: emphasize ? 15.5 : 14,
            color: emphasize ? AppColors.primaryDark : AppColors.textPrimary,
            fontVariations: const [FontVariation('wght', 700)],
          ),
        ),
      ],
    );
  }
}
