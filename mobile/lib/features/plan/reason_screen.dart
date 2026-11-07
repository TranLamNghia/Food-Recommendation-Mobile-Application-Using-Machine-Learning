import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/food.dart';
import '../../data/recommender/match_reason.dart';
import '../../data/recommender/preference_profile.dart';
import '../../data/rules/condition_rule.dart';
import '../../data/rules/day_budget.dart';
import 'widgets/day_budget_card.dart' show nutrientLabel;

/// Vì sao món này được gợi ý.
///
/// Ba khối, theo thứ tự quan trọng với người đọc: khớp khẩu vị đến đâu, nó
/// giúp gì cho hôm nay, và điều gì cần lưu ý. Khối thứ ba không phải phần
/// thêm cho đẹp — một màn giải thích chỉ nêu điểm tốt thì là quảng cáo, và
/// người dùng sẽ thôi tin nó ngay lần đầu tự phát hiện một điểm trừ.
class ReasonScreen extends StatelessWidget {
  const ReasonScreen({
    super.key,
    required this.food,
    required this.profile,
    required this.budget,
    required this.penalty,
    this.betterThanShare,
  });

  final Food food;
  final PreferenceProfile profile;
  final DayBudget budget;
  final PenaltyOutcome penalty;

  /// Tỷ lệ món trong danh mục có điểm khớp **thấp hơn** món này.
  ///
  /// Cần nó vì điểm cosin thô không nói được nhiều: 0,78 là cao hay thấp thì
  /// chỉ có nghĩa khi so với các món khác.
  final double? betterThanShare;

  static Future<void> open(
    BuildContext context, {
    required Food food,
    required PreferenceProfile profile,
    required DayBudget budget,
    required PenaltyOutcome penalty,
    double? betterThanShare,
  }) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ReasonScreen(
          food: food,
          profile: profile,
          budget: budget,
          penalty: penalty,
          betterThanShare: betterThanShare,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final reasons = matchReasons(profile, food);
    final score = profile.score(food);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text(
          'Vì sao món này',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        children: [
          Text(
            food.name,
            style: const TextStyle(
              fontSize: 21,
              fontWeight: FontWeight.w700,
              height: 1.2,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${food.category} · ${food.dishRole} · ${food.kcal} kcal '
            '/ suất ${formatNumber(food.servingSizeG)} g',
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w500,
              color: AppColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          _ScoreBanner(score: score, betterThanShare: betterThanShare),
          const SizedBox(height: 20),
          if (reasons.isEmpty)
            const _NoProfileYet()
          else
            _MatchBlock(reasons: reasons),
          const SizedBox(height: 20),
          _TodayBlock(food: food, budget: budget),
          if (penalty.penalised || penalty.missingNutrients.isNotEmpty) ...[
            const SizedBox(height: 20),
            _CaveatBlock(penalty: penalty),
          ],
        ],
      ),
    );
  }
}

/// Điểm khớp **tổng**, đặt trước mấy thanh so sánh.
///
/// Thứ tự này là bắt buộc, không phải thẩm mỹ. [MatchReason.ratio] chuẩn hóa
/// theo đỉnh của chính món đó, nên một món khớp rất yếu vẫn cho ba thanh gần
/// đầy — đo được: một món đã bị vuốt `dislike` ra 100 % / 91 % / 88 % trong
/// khi đóng góp tuyệt đối chỉ quanh +0,009. Vẽ riêng mấy thanh đó là nói với
/// người dùng rằng mọi món đều khớp mạnh như nhau.
class _ScoreBanner extends StatelessWidget {
  const _ScoreBanner({required this.score, this.betterThanShare});

  final double score;
  final double? betterThanShare;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 15),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            '${(score * 100).round()}',
            style: const TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w700,
              height: 1,
              color: AppColors.textPrimary,
            ),
          ),
          const Padding(
            padding: EdgeInsets.only(top: 6),
            child: Text(
              '%',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'khớp khẩu vị của bạn',
                  style: TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w700,
                    color: AppColors.textPrimary,
                  ),
                ),
                if (betterThanShare != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      'Cao hơn ${(betterThanShare! * 100).round()} % '
                      'số món trong danh mục',
                      style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w500,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MatchBlock extends StatelessWidget {
  const _MatchBlock({required this.reasons});

  final List<MatchReason> reasons;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockHeading(color: AppColors.accentInk, text: 'ĐIỀU GÌ KHỚP NHẤT'),
        const SizedBox(height: 12),
        for (final r in reasons)
          if (r.sentence != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 11),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    r.sentence!,
                    style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w500,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 5),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      value: r.ratio,
                      minHeight: 6,
                      backgroundColor: AppColors.surfaceMuted,
                      valueColor: const AlwaysStoppedAnimation(
                        AppColors.accentInk,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
          decoration: BoxDecoration(
            color: AppColors.surfaceMuted,
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Text(
            'Thanh trên so ba lý do với nhau, không đo mức khớp — con số ở '
            'khối trên mới làm việc đó.',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w500,
              height: 1.5,
              color: AppColors.textSecondary,
            ),
          ),
        ),
      ],
    );
  }
}

class _NoProfileYet extends StatelessWidget {
  const _NoProfileYet();

  @override
  Widget build(BuildContext context) {
    // Hồ sơ rỗng thì KHÔNG có cơ sở nào để nói người này thích gì. Hiện một
    // khối trống kèm lời giải thích thật thà, chứ không bịa ra ba lý do.
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 13, 14, 14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: const Text(
        'Chưa đủ lượt vuốt để nói bạn thích gì, nên món này được chọn theo '
        'mục tiêu dinh dưỡng và độ phổ biến. Làm xong khảo sát khẩu vị thì '
        'phần này sẽ có nội dung.',
        style: TextStyle(
          fontSize: 12.5,
          fontWeight: FontWeight.w500,
          height: 1.5,
          color: AppColors.textSecondary,
        ),
      ),
    );
  }
}

/// Món này ảnh hưởng thế nào đến hạn mức của hôm nay.
class _TodayBlock extends StatelessWidget {
  const _TodayBlock({required this.food, required this.budget});

  final Food food;
  final DayBudget budget;

  @override
  Widget build(BuildContext context) {
    final hard = budget.hard;
    if (hard.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockHeading(color: AppColors.neutral, text: 'ẢNH HƯỞNG HÔM NAY'),
        const SizedBox(height: 10),
        for (final limit in hard)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: _TodayRow(food: food, limit: limit),
          ),
      ],
    );
  }
}

class _TodayRow extends StatelessWidget {
  const _TodayRow({required this.food, required this.limit});

  final Food food;
  final DayLimit limit;

  @override
  Widget build(BuildContext context) {
    final value = DayBudget.valueOf(food, limit.nutrient);
    final ten = nutrientLabel(limit.nutrient);

    // `null` là KHÔNG BIẾT, không phải 0 — và hai thứ đó phải hiện khác nhau.
    final khuyet = value == null;
    final vua = !khuyet && limit.fits(value);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 2, right: 9),
          child: Icon(
            khuyet
                ? Icons.help_outline_rounded
                : vua
                ? Icons.check_rounded
                : Icons.priority_high_rounded,
            size: 14,
            color: khuyet
                ? AppColors.unknown
                : vua
                ? AppColors.neutral
                : AppColors.dislike,
          ),
        ),
        Expanded(
          child: Text.rich(
            TextSpan(
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                height: 1.45,
                color: AppColors.textPrimary,
              ),
              children: khuyet
                  ? [
                      TextSpan(text: '$ten: '),
                      const TextSpan(
                        text: 'danh mục không có số liệu',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                      TextSpan(
                        text:
                            ' cho món này, nên không đối chiếu được với hạn '
                            'mức ${limit.condition}',
                      ),
                    ]
                  : [
                      TextSpan(text: '$ten '),
                      TextSpan(
                        text: '${formatNumber(value)} ${limit.unit}',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      TextSpan(
                        text: vua
                            ? ', hôm nay còn '
                                  '${formatNumber(limit.remaining)} '
                                  '${limit.unit}'
                            : ', vượt phần còn lại '
                                  '${formatNumber(value - limit.remaining)} '
                                  '${limit.unit}',
                      ),
                    ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Điểm cần lưu ý — phần món này **không** tốt.
class _CaveatBlock extends StatelessWidget {
  const _CaveatBlock({required this.penalty});

  final PenaltyOutcome penalty;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _BlockHeading(color: AppColors.unknown, text: 'ĐIỂM CẦN LƯU Ý'),
        const SizedBox(height: 10),
        for (final v in penalty.violations)
          Padding(
            padding: const EdgeInsets.only(bottom: 9),
            child: Text.rich(
              TextSpan(
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  height: 1.45,
                  color: AppColors.textPrimary,
                ),
                children: [
                  TextSpan(
                    text: nutrientLabel(v.rule.nutrient),
                  ),
                  TextSpan(
                    text: ' ${formatNumber(v.measured)} ${v.rule.unit}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  TextSpan(
                    text:
                        ', khuyến cáo dưới '
                        '${formatNumber(v.rule.threshold)} ${v.rule.unit} '
                        'mỗi suất. Món bị nhân điểm ',
                  ),
                  TextSpan(
                    text: '×${v.rule.penalty.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const TextSpan(
                    text: ' nên xếp sau, nhưng vẫn chọn được — đây là '
                        'khuyến cáo, không phải chống chỉ định.',
                  ),
                ],
              ),
            ),
          ),
        for (final n in penalty.missingNutrients)
          Padding(
            padding: const EdgeInsets.only(bottom: 9),
            child: Text(
              'Không có số liệu ${nutrientLabel(n).toLowerCase()} cho món '
              'này, nên ràng buộc mềm của chất đó chưa được kiểm. Món không '
              'bị trừ điểm vì chuyện đó — thiếu số liệu là lỗi của danh mục, '
              'không phải của món.',
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                height: 1.45,
                color: AppColors.textPrimary,
              ),
            ),
          ),
      ],
    );
  }
}

class _BlockHeading extends StatelessWidget {
  const _BlockHeading({required this.color, required this.text});

  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Text(
          text,
          style: const TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.5,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}
