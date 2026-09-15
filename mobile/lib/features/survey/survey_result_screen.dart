import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../../data/models/swipe_action.dart';
import 'survey_screen.dart';

/// Màn hình tổng kết sau khi vuốt xong.
///
/// Đây là lúc hệ thống dựng xong hồ sơ sở thích ban đầu, nên màn hình nói lại
/// cho người dùng biết nó vừa học được gì — vừa để họ thấy công sức vuốt có
/// ích, vừa là phần "giải thích được" của mô hình nội dung.
class SurveyResultScreen extends StatefulWidget {
  const SurveyResultScreen({super.key, required this.results});

  final List<SwipeResult> results;

  @override
  State<SurveyResultScreen> createState() => _SurveyResultScreenState();
}

class _SurveyResultScreenState extends State<SurveyResultScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _entry;

  @override
  void initState() {
    super.initState();
    _entry = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..forward();
  }

  @override
  void dispose() {
    _entry.dispose();
    super.dispose();
  }

  Map<SwipeAction, int> get _counts {
    final map = {for (final a in SwipeAction.values) a: 0};
    for (final r in widget.results) {
      map[r.action] = map[r.action]! + 1;
    }
    return map;
  }

  /// Đặc trưng nổi bật của các món được thích — xếp theo số lần xuất hiện.
  ///
  /// Đếm riêng phương pháp chế biến và nhóm món rồi lấy hai đặc trưng mạnh
  /// nhất của mỗi loại. Nếu gộp chung một rổ, hai nhãn gần như đồng nghĩa
  /// ("Chiên" và "Món chiên") sẽ cùng lọt vào và nói đi nói lại một ý.
  List<({String label, int count})> _topTraits() {
    final byMethod = <String, int>{};
    final byCategory = <String, int>{};

    for (final r in widget.results.where((r) => r.action == SwipeAction.like)) {
      byMethod[r.food.cookingMethod] =
          (byMethod[r.food.cookingMethod] ?? 0) + 1;
      byCategory[r.food.category] = (byCategory[r.food.category] ?? 0) + 1;
    }

    String key(String s) => s.toLowerCase().replaceAll('món ', '').trim();

    final picked = <({String label, int count})>[];
    final seen = <String>{};

    void takeTop(Map<String, int> tally, int limit) {
      final entries = tally.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));
      var added = 0;
      for (final e in entries) {
        if (added == limit) break;
        if (!seen.add(key(e.key))) continue;
        picked.add((label: e.key, count: e.value));
        added++;
      }
    }

    takeTop(byMethod, 2);
    takeTop(byCategory, 2);
    return picked;
  }

  @override
  Widget build(BuildContext context) {
    final counts = _counts;
    final total = widget.results.length;
    final trainable = total - counts[SwipeAction.unknown]!;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Stagger(
                      controller: _entry,
                      start: 0,
                      child: const _SuccessMark(),
                    ),
                    const SizedBox(height: 26),
                    _Stagger(
                      controller: _entry,
                      start: 0.12,
                      child: Text(
                        'Đã hiểu gu ăn của bạn',
                        style: Theme.of(context).textTheme.displaySmall,
                      ),
                    ),
                    const SizedBox(height: 10),
                    _Stagger(
                      controller: _entry,
                      start: 0.18,
                      child: Text(
                        '$trainable trên $total lượt vuốt được đưa vào tập huấn '
                        'luyện. Thực đơn từ hôm nay đã tính theo gu của bạn.',
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ),
                    const SizedBox(height: 28),
                    for (var i = 0; i < SwipeAction.values.length; i++)
                      _Stagger(
                        controller: _entry,
                        start: 0.26 + i * 0.07,
                        child: Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _CountRow(
                            action: SwipeAction.values[i],
                            count: counts[SwipeAction.values[i]]!,
                            total: total == 0 ? 1 : total,
                            controller: _entry,
                          ),
                        ),
                      ),
                    const SizedBox(height: 16),
                    _Stagger(
                      controller: _entry,
                      start: 0.6,
                      child: _TraitCard(traits: _topTraits()),
                    ),
                    const SizedBox(height: 14),
                    _Stagger(
                      controller: _entry,
                      start: 0.66,
                      child: const _NextStepNote(),
                    ),
                  ],
                ),
              ),
            ),
            _Stagger(
              controller: _entry,
              start: 0.72,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 20),
                child: FilledButton(
                  onPressed: () {},
                  child: const Text('Xem thực đơn hôm nay'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Đưa một widget vào màn hình theo kiểu trượt lên + hiện dần, lệch pha nhau
/// theo [start] để các khối xuất hiện nối tiếp chứ không ập vào cùng lúc.
class _Stagger extends StatelessWidget {
  const _Stagger({
    required this.controller,
    required this.start,
    required this.child,
  });

  final AnimationController controller;
  final double start;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final animation = CurvedAnimation(
      parent: controller,
      curve: Interval(
        start,
        (start + 0.32).clamp(0.0, 1.0),
        curve: AppMotion.emphasized,
      ),
    );

    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) => Opacity(
        opacity: animation.value,
        child: Transform.translate(
          offset: Offset(0, 22 * (1 - animation.value)),
          child: child,
        ),
      ),
      child: child,
    );
  }
}

/// Dấu tích tròn: vòng nền nở ra trước, dấu tích nảy vào sau.
class _SuccessMark extends StatelessWidget {
  const _SuccessMark();

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 700),
      curve: AppMotion.spring,
      builder: (context, t, _) => Transform.scale(
        scale: t,
        child: Container(
          width: 76,
          height: 76,
          decoration: const BoxDecoration(
            color: AppColors.primarySoft,
            shape: BoxShape.circle,
          ),
          child: const Icon(
            Icons.check_rounded,
            size: 42,
            color: AppColors.primary,
          ),
        ),
      ),
    );
  }
}

/// Một dòng thống kê: nhãn, thanh tỷ lệ chạy từ 0 lên, và số đếm.
class _CountRow extends StatelessWidget {
  const _CountRow({
    required this.action,
    required this.count,
    required this.total,
    required this.controller,
  });

  final SwipeAction action;
  final int count;
  final int total;
  final AnimationController controller;

  @override
  Widget build(BuildContext context) {
    final ratio = count / total;

    return Row(
      children: [
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: action.color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(action.icon, size: 18, color: action.color),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    action.title,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    '$count món',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: ratio),
                  duration: const Duration(milliseconds: 900),
                  curve: AppMotion.emphasized,
                  builder: (context, value, _) => LinearProgressIndicator(
                    value: value,
                    minHeight: 6,
                    backgroundColor: AppColors.surfaceMuted,
                    valueColor: AlwaysStoppedAnimation(action.color),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Nói trước điều người dùng hay thắc mắc: có phải vuốt lại nữa không.
///
/// Đây cũng là chỗ nêu đúng nguyên tắc thiết kế của hệ thống — sau khảo sát,
/// tín hiệu sở thích đến từ hành vi thật chứ không hỏi thêm.
class _NextStepNote extends StatelessWidget {
  const _NextStepNote();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.info_outline_rounded,
            size: 20,
            color: AppColors.accent,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: RichText(
              text: const TextSpan(
                style: TextStyle(
                  fontSize: 13.5,
                  height: 1.5,
                  color: AppColors.textSecondary,
                ),
                children: [
                  TextSpan(
                    text: 'Bạn sẽ không phải vuốt lại. ',
                    style: TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  TextSpan(
                    text:
                        'Từ giờ hệ thống học tiếp từ món bạn giữ lại trong '
                        'thực đơn, món bạn đổi đi, món ăn thật và điểm bạn '
                        'chấm sau khi ăn.',
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TraitCard extends StatelessWidget {
  const _TraitCard({required this.traits});

  final List<({String label, int count})> traits;

  @override
  Widget build(BuildContext context) {
    if (traits.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Hệ thống nhận thấy bạn thiên về',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final trait in traits)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 7,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.primarySoft,
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '${trait.label} · ${trait.count}',
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primaryDark,
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
