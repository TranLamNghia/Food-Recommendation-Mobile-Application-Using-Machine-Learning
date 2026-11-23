import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/meal_plan.dart';
import '../../data/mock/mock_rules.dart';
import '../../data/recommender/match_reason.dart';
import '../../data/rules/condition_rule.dart';
import '../../data/session.dart';
import '../food/food_detail_screen.dart';
import 'excluded_screen.dart';
import 'reason_screen.dart';
import 'widgets/day_budget_card.dart';
import 'widgets/energy_summary_card.dart';
import 'widgets/plan_item_tile.dart';
import 'widgets/replace_sheet.dart';
import 'widgets/week_strip.dart';

/// The daily meal plan — the system's main product.
///
/// Everything before this screen (the profile, the survey swipes) is only
/// preparing data. This is where the four steps of the recommendation
/// algorithm produce a visible result.
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
            ? _NoPlan(complete: session.profile.isComplete)
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
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
            child: WeekStrip(
              selected: session.selectedDay,
              onSelected: session.selectDay,
              hasPlan: (day) => session.planOn(day) != null,
            ),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
            child: EnergySummaryCard(plan: plan, isToday: session.viewingToday),
          ),
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
            child: DayBudgetCard(
              budget: session.dayBudget,
              isToday: session.viewingToday,
            ),
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
                session.viewingToday
                    ? 'Thực đơn hôm nay'
                    : 'Thực đơn ${_weekdays[d.weekday - 1].toLowerCase()}',
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

/// One meal of the day, with its own target and its list of servings.
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
      // The allowance has to have the dish being replaced subtracted:
      // the room for the new dish includes what the old one takes up.
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
              onOpen: () => FoodDetailScreen.open(context, item.food),
              onReplace: () => _replace(context, item),
              // Only today can be eaten: logging a meal stamps it with the
              // current time, so "eating" tomorrow's dinner would land in
              // today's diary.
              onEat: session.viewingToday ? () => _eat(context, item) : null,
              onSkip: () => session.setSkipped(item, true),
              onRestore: () => session.setSkipped(item, false),
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

/// Explains the 70-30 mechanism right on the screen.
///
/// A user who sees a dish off their taste will think the system guessed
/// wrong. Saying plainly that it was put there deliberately to explore
/// changes how they read the situation — and that is exactly what the
/// filter-bubble section of the report needs to illustrate.
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

/// Shown when the profile does not hold enough data to compute the
/// targets.
/// There is no plan for the day on screen.
///
/// Two different reasons, and telling them apart matters. The profile being
/// incomplete is the user's to fix and the message says so. A **complete**
/// profile with no plan is not the user's fault at all — it is a day the plan
/// has not been generated for — and the old single message told those users
/// their health profile was missing information and to start over, which was
/// both wrong and alarming.
///
/// Offline the second case cannot happen: finishing the survey builds a plan
/// at once. It appears with a server, where the profile is read back on
/// signing in and the plan is fetched separately.
class _NoPlan extends StatelessWidget {
  const _NoPlan({required this.complete});

  /// Whether the six fields step 1 needs all have answers.
  final bool complete;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              complete
                  ? Icons.restaurant_menu_rounded
                  : Icons.info_outline_rounded,
              size: 44,
              color: AppColors.textTertiary,
            ),
            const SizedBox(height: 16),
            Text(
              complete
                  ? 'Chưa có thực đơn cho ngày này'
                  : 'Chưa tính được hạn mức',
              style: text.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              complete
                  ? 'Hạn mức dinh dưỡng của bạn đã có. Thực đơn cho ngày '
                        'này thì chưa được tạo.'
                  : 'Hồ sơ sức khỏe còn thiếu thông tin nên chưa suy ra '
                        'được nhu cầu năng lượng. Hãy khai báo lại từ đầu.',
              style: text.bodyMedium,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

/// The link to the excluded-dishes screen.
///
/// Placed directly under the allowance card, because the two explain each
/// other: seeing that the sodium is nearly used up is what makes it clear why
/// so many dishes are missing today.
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

/// The taste-match reason chips, with a link to the full explanation
/// screen.
///
/// A chip shows a **sentence**, not a number: `+0.182` is one term in the
/// numerator of the cosine and means nothing to a user. The ordering is the
/// information.
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
          // One single row: the reason chips plus the link. This block
          // used to take three lines under EVERY serving, that is twelve
          // lines for a four-meal day — more than the plan itself. The
          // design puts the link on one serving only, and that is the right
          // proportion.
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
                // "Chỉ bị xếp sau" is a mandatory phrase: exceeding a
                // recommendation is NOT the same as breaching a
                // contraindication, and the user has to be able to tell them
                // apart.
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

  /// The share of the catalogue whose match score is LOWER than this
  /// dish's.
  ///
  /// A raw cosine score says little on its own: whether 0.78 is high or low
  /// only means something against the other dishes. With an empty profile
  /// every dish scores the same, so this share is meaningless — it returns
  /// `null` so the interface drops that line.
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
