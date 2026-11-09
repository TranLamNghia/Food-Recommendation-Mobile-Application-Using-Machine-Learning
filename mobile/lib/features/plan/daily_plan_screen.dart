import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/meal_plan.dart';
import '../../data/mock/mock_rules.dart';
import '../../data/recommender/match_reason.dart';
import '../../data/rules/condition_rule.dart';
import '../../data/session.dart';
import 'excluded_screen.dart';
import 'reason_screen.dart';
import 'widgets/day_budget_card.dart';
import 'widgets/energy_summary_card.dart';
import 'widgets/plan_item_tile.dart';
import 'widgets/replace_sheet.dart';

/// Thực đơn hằng ngày — sản phẩm chính của hệ thống.
///
/// Mọi thứ trước màn hình này (khai báo hồ sơ, phiên vuốt khảo sát) đều chỉ
/// là bước chuẩn bị dữ liệu. Đây là nơi bốn bước của thuật toán khuyến nghị
/// cho ra kết quả nhìn thấy được.
class DailyPlanScreen extends StatelessWidget {
  const DailyPlanScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final plan = session.plan;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: plan == null
            ? const _MissingProfile()
            : _PlanBody(session: session, plan: plan),
      ),
    );
  }
}

class _PlanBody extends StatelessWidget {
  const _PlanBody({required this.session, required this.plan});

  final AppSession session;
  final DailyPlan plan;

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
            child: _Header(plan: plan, session: session),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
            child: EnergySummaryCard(plan: plan),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
            child: DayBudgetCard(budget: session.dayBudget),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
            child: _ExcludedLink(session: session),
          ),
        ),
        for (final slot in plan.slots)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 22, 20, 0),
              child: _MealSection(slot: slot, session: session),
            ),
          ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
            child: _ExplorationNote(plan: plan),
          ),
        ),
        const SliverToBoxAdapter(child: SizedBox(height: 28)),
      ],
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.plan, required this.session});

  final DailyPlan plan;
  final AppSession session;

  static const _weekdays = [
    'Thứ hai',
    'Thứ ba',
    'Thứ tư',
    'Thứ năm',
    'Thứ sáu',
    'Thứ bảy',
    'Chủ nhật',
  ];

  @override
  Widget build(BuildContext context) {
    final d = plan.date;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Thực đơn hôm nay',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 4),
              Text(
                '${_weekdays[d.weekday - 1]}, ${d.day}/${d.month}/${d.year}',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
        IconButton(
          onPressed: () {
            session.regeneratePlan();
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Đã sinh lại thực đơn'),
                duration: Duration(seconds: 2),
              ),
            );
          },
          tooltip: 'Sinh lại thực đơn',
          icon: const Icon(Icons.refresh_rounded),
          color: AppColors.textPrimary,
        ),
      ],
    );
  }
}

/// Một bữa trong ngày, kèm hạn mức riêng và danh sách suất.
class _MealSection extends StatelessWidget {
  const _MealSection({required this.slot, required this.session});

  final MealSlot slot;
  final AppSession session;

  Future<void> _replace(BuildContext context, MealPlanItem item) async {
    final choice = await ReplaceSheet.show(
      context,
      item: item,
      alternatives: session.alternativesFor(item),
      scoreOf: session.preference.score,
      // Hạn mức phải trừ món đang thay ra: dư địa cho món mới gồm cả phần
      // món cũ đang chiếm.
      budgetAfterRemoval: session.dayBudget.withoutPlanned(item.food),
    );
    if (choice == null) return;

    session.replaceItem(item, choice);
    if (!context.mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã đổi sang ${choice.name.toLowerCase()}'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _eat(BuildContext context, MealPlanItem item) {
    session.logMeal(food: item.food, meal: slot.type);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã ghi ${item.food.name.toLowerCase()} vào nhật ký'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              slot.type.label,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Spacer(),
            Text(
              '${formatNumber(slot.actualKcal)} / '
              '${formatNumber(slot.targetKcal)} kcal',
              style: const TextStyle(
                fontSize: 13,
                color: AppColors.textSecondary,
                fontVariations: [FontVariation('wght', 600)],
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (slot.items.isEmpty)
          const _EmptySlot()
        else
          for (final item in slot.items) ...[
            PlanItemTile(
              item: item,
              onReplace: () => _replace(context, item),
              onEat: () => _eat(context, item),
            ),
            _WhyRow(item: item, session: session),
          ],
      ],
    );
  }
}

class _EmptySlot extends StatelessWidget {
  const _EmptySlot();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Text(
        'Kho món chưa đủ lựa chọn cho bữa này.',
        style: TextStyle(fontSize: 13.5, color: AppColors.textSecondary),
      ),
    );
  }
}

/// Giải thích cơ chế 70-30 ngay trên màn hình.
///
/// Người dùng thấy một món lệch gu sẽ nghĩ hệ thống đoán sai. Nói rõ đó là
/// món cố ý đưa vào để thăm dò sẽ đổi cách họ hiểu tình huống — và đó cũng
/// chính là nội dung cần minh họa cho phần chống bong bóng lọc trong báo cáo.
class _ExplorationNote extends StatelessWidget {
  const _ExplorationNote({required this.plan});

  final DailyPlan plan;

  @override
  Widget build(BuildContext context) {
    final count = plan.allItems.where((i) => i.isExploration).length;
    if (count == 0) return const SizedBox.shrink();

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
            Icons.auto_awesome_rounded,
            size: 19,
            color: AppColors.accentInk,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: RichText(
              text: TextSpan(
                style: const TextStyle(
                  fontSize: 13,
                  height: 1.5,
                  color: AppColors.textSecondary,
                ),
                children: [
                  TextSpan(
                    text: '$count món hôm nay được đánh dấu "Thử mới". ',
                    style: const TextStyle(
                      color: AppColors.textPrimary,
                      fontVariations: [FontVariation('wght', 700)],
                    ),
                  ),
                  const TextSpan(
                    text:
                        'Đó là những món nằm ở vùng lân cận khẩu vị của bạn, '
                        'hệ thống đưa vào để mở rộng hiểu biết thay vì chỉ lặp '
                        'lại những gì đã biết bạn thích. Bạn đổi đi cũng được — '
                        'chính thao tác đó cũng là một tín hiệu.',
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

/// Hiện khi chưa đủ dữ liệu hồ sơ để tính hạn mức.
class _MissingProfile extends StatelessWidget {
  const _MissingProfile();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.info_outline_rounded,
              size: 44,
              color: AppColors.textTertiary,
            ),
            const SizedBox(height: 16),
            Text(
              'Chưa tính được hạn mức',
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Hồ sơ sức khỏe còn thiếu thông tin nên chưa suy ra được nhu '
              'cầu năng lượng. Hãy khai báo lại từ đầu.',
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

/// Đường dẫn tới màn món bị bỏ qua.
///
/// Đặt ngay dưới thẻ hạn mức, vì hai thứ này giải thích lẫn cho nhau: người
/// dùng thấy natri gần cạn rồi mới hiểu vì sao hôm nay nhiều món vắng mặt.
class _ExcludedLink extends StatelessWidget {
  const _ExcludedLink({required this.session});

  final AppSession session;

  @override
  Widget build(BuildContext context) {
    final screening = session.screening;
    final soBiBo = screening.excluded.length;
    if (soBiBo == 0) return const SizedBox.shrink();

    final theoBac = screening.byTier;
    final soHanMuc = (theoBac[ExclusionTier.dayBudget] ?? const []).length;

    return InkWell(
      borderRadius: BorderRadius.circular(18),
      onTap: () => ExcludedScreen.open(
        context,
        screening: screening,
        foods: session.candidates,
      ),
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 13, 14, 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Row(
          children: [
            const Icon(
              Icons.filter_alt_outlined,
              size: 18,
              color: AppColors.neutral,
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${screening.allowed.length} món phù hợp, '
                    '$soBiBo món bị bỏ qua',
                    style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    soHanMuc > 0
                        ? '$soHanMuc món chỉ vắng hôm nay vì hết hạn mức'
                        : 'Xem ba bậc lý do',
                    style: const TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w500,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              size: 20,
              color: AppColors.textSecondary,
            ),
          ],
        ),
      ),
    );
  }
}

/// Chip lý do khớp khẩu vị, kèm đường dẫn sang màn giải thích đầy đủ.
///
/// Chip hiện **câu**, không hiện số: `+0.182` là một số hạng trong tử số của
/// phép cosin, vô nghĩa với người dùng. Thứ tự mới là thông tin.
class _WhyRow extends StatelessWidget {
  const _WhyRow({required this.item, required this.session});

  final MealPlanItem item;
  final AppSession session;

  @override
  Widget build(BuildContext context) {
    final cau = matchSentences(session.preference, item.food, limit: 2);
    final penalty = PenaltyOutcome.of(
      item.food,
      softRulesFor(session.userConditions),
    );

    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Một hàng duy nhất: chip lý do cộng đường dẫn. Trước đây khối này
          // chiếm ba dòng dưới MỖI suất, tức mười hai dòng cho một ngày bốn
          // bữa — nhiều hơn cả phần thực đơn. Bản thiết kế chỉ đặt đường dẫn
          // ở một suất, và đó là tỷ lệ đúng.
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (final c in cau) _ReasonChip(text: c),
              InkWell(
                onTap: () => ReasonScreen.open(
                  context,
                  food: item.food,
                  profile: session.preference,
                  budget: session.dayBudget,
                  penalty: penalty,
                  betterThanShare: _betterThanShare(),
                ),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 2, vertical: 4),
                  child: Text(
                    'Vì sao?',
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700,
                      color: AppColors.accentInk,
                      decoration: TextDecoration.underline,
                      decorationColor: AppColors.accentInk,
                    ),
                  ),
                ),
              ),
            ],
          ),
          if (penalty.penalised)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                // "Chỉ bị xếp sau" là cụm bắt buộc: vượt một khuyến cáo KHÁC
                // vi phạm một chống chỉ định, và người dùng phải phân biệt
                // được hai thứ.
                '${nutrientLabel(penalty.violations.first.rule.nutrient)} '
                'cao hơn khuyến cáo — chỉ bị xếp sau, không bị loại',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  height: 1.4,
                  color: AppColors.unknown,
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// Tỷ lệ món trong danh mục có điểm khớp THẤP hơn món này.
  ///
  /// Điểm cosin thô không nói được nhiều: 0,78 là cao hay thấp chỉ có nghĩa
  /// khi so với các món khác. Hồ sơ rỗng thì mọi món cùng điểm nên tỷ lệ này
  /// vô nghĩa — trả `null` để giao diện bỏ dòng đó đi.
  double? _betterThanShare() {
    if (session.preference.isEmpty) return null;
    final diem = session.preference.score(item.food);
    final tatCa = session.candidates;
    if (tatCa.isEmpty) return null;
    var thapHon = 0;
    for (final f in tatCa) {
      if (session.preference.score(f) < diem) thapHon++;
    }
    return thapHon / tatCa.length;
  }
}

class _ReasonChip extends StatelessWidget {
  const _ReasonChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
        ),
      ),
    );
  }
}
