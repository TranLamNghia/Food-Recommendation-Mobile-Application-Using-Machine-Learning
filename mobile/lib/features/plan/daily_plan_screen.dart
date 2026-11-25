import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/models/meal_plan.dart';
import '../../data/mock/mock_rules.dart';
import '../../data/recommender/match_reason.dart';
import '../../data/rules/condition_rule.dart';
import '../../data/rules/day_budget.dart';
import '../../data/session.dart';
import '../food/food_browse_screen.dart';
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
/// Stateful because the day's plan is a round trip online — §7.6.1 — and a
/// refusal there has to be shown as itself rather than as an empty screen.
class DailyPlanScreen extends StatefulWidget {
  const DailyPlanScreen({super.key});

  @override
  State<DailyPlanScreen> createState() => _DailyPlanScreenState();
}

class _DailyPlanScreenState extends State<DailyPlanScreen> {
  bool _started = false;
  bool _loading = false;
  ApiFailure? _error;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    // Online the day's plan is a round trip (§7.6.1, `autoGenerate` on), so
    // it cannot be fetched during a build. `didChangeDependencies` and not
    // `initState` because `SessionScope.of` reads an inherited widget.
    _load();
  }

  Future<void> _load() async {
    final session = SessionScope.of(context);
    if (session.plan != null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await session.loadPlan();
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _error = failure);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final plan = session.plan;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: switch ((plan, _loading, _error)) {
          (final DailyPlan p, _, _) => _PlanBody(session: session, plan: p),
          (_, true, _) => const Center(child: CircularProgressIndicator()),
          // A refusal is shown as itself. `_NoPlan` says "there is no plan
          // yet", which for a user whose conditions leave no feasible day
          // would be the wrong story entirely.
          (_, _, final ApiFailure f) => _PlanFailed(
            failure: f,
            onRetry: _load,
          ),
          _ => _NoPlan(complete: session.profile.isComplete),
        },
      ),
    );
  }
}

/// When §7.6 refuses to produce a day.
///
/// Its own screen rather than a snackbar over an empty one: the two refusals
/// that matter here are `NO_FEASIBLE_PLAN` and `RULE_TOO_RESTRICTIVE`, and
/// the second is the user's to act on — their declarations left too few
/// dishes. Telling them that is the only way out of it.
class _PlanFailed extends StatelessWidget {
  const _PlanFailed({required this.failure, required this.onRetry});

  final ApiFailure failure;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline_rounded,
              size: 44,
              color: AppColors.textTertiary,
            ),
            const SizedBox(height: 16),
            Text(
              'Chưa dựng được thực đơn',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              failure.message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (failure.isRetryable) ...[
              const SizedBox(height: 18),
              FilledButton(onPressed: onRetry, child: const Text('Thử lại')),
            ],
          ],
        ),
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

/// Regenerating **deletes** the stored plan for the day and builds another,
/// so it asks first — §7.6.2 is explicit that a day the user has started
/// eating from should not vanish because a button was within reach. And the
/// message afterwards says what happened rather than what was attempted: the
/// old version announced success before the request had been made.
Future<void> _regenerate(BuildContext context) async {
  final session = SessionScope.of(context);
  final messenger = ScaffoldMessenger.of(context);

  // The day ON SCREEN, which the week strip can have moved away from today.
  // The question has to name it: a user looking at Thursday who is asked
  // about "hôm nay" would answer the wrong question. One day only — there is
  // no regenerate-the-week, and §7.6.2 takes a single `planDate`.
  final day = session.selectedDay;
  final label = session.viewingToday
      ? 'hôm nay'
      : 'ngày ${day.day}/${day.month}';

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text('Sinh lại thực đơn $label?'),
      content: Text(
        'Thực đơn $label sẽ bị thay bằng một thực đơn mới. '
        '${session.viewingToday ? "Những món đã ăn vẫn ở trong nhật ký. " : ""}'
        'Các ngày khác không đổi.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Để nguyên'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Sinh lại'),
        ),
      ],
    ),
  );
  if (confirmed != true) return;

  try {
    // Explicitly the day that was named in the question, not whatever
    // `_selectedDay` happens to be by the time the dialog closes.
    final built = await session.regeneratePlan(date: day);
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          built
              ? 'Đã sinh lại thực đơn $label'
              : 'Chưa đủ thông tin hồ sơ để dựng thực đơn',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  } on ApiFailure catch (failure) {
    messenger.showSnackBar(
      SnackBar(
        content: Text(failure.message),
        duration: const Duration(seconds: 4),
      ),
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
        // The way into the whole catalogue. Here because the plan is where
        // a user wonders "what else could I eat", and the four tabs are
        // already full.
        IconButton(
          onPressed: () => FoodBrowseScreen.open(context),
          tooltip: 'Tìm món',
          icon: const Icon(Icons.search_rounded),
          color: AppColors.textPrimary,
        ),
        IconButton(
          onPressed: () => _regenerate(context),
          tooltip: 'Sinh lại thực đơn',
          icon: const Icon(Icons.refresh_rounded),
          color: AppColors.textPrimary,
        ),
      ],
    );
  }
}

/// Rebuilds one meal and leaves the other three alone — for a user who likes
/// the day but not its dinner, and would otherwise have had to throw the
/// whole day away to change it.
///
/// Asks first, like the day-level button, because the meal's dishes are
/// replaced and not added to. Milder wording: nothing eaten can be lost, as
/// the button is not offered on a meal with an eaten dish.
Future<void> _regenerateMeal(BuildContext context, MealType meal) async {
  final session = SessionScope.of(context);
  final messenger = ScaffoldMessenger.of(context);
  final day = session.selectedDay;
  final name = meal.label.toLowerCase();

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text('Đổi $name?'),
      content: Text(
        'Các món của $name sẽ được thay bằng món khác, vẫn tính theo hạn mức '
        'của bữa. Những bữa còn lại giữ nguyên.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Để nguyên'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Đổi bữa'),
        ),
      ],
    ),
  );
  if (confirmed != true) return;

  try {
    await session.regenerateMeal(meal, date: day);
    messenger.showSnackBar(
      SnackBar(
        content: Text('Đã đổi $name sang món khác'),
        duration: const Duration(seconds: 2),
      ),
    );
  } on ApiFailure catch (failure) {
    messenger.showSnackBar(
      SnackBar(
        content: Text(failure.message),
        duration: const Duration(seconds: 4),
      ),
    );
  }
}

/// One meal of the day, with its own target and its list of servings.
class _MealSection extends StatelessWidget {
  const _MealSection({required this.slot, required this.session});

  final MealSlot slot;
  final AppSession session;

  Future<void> _replace(BuildContext context, MealPlanItem item) async {
    final offlineDish = item.dish;
    final options = await session.replaceOptions(item);
    if (!context.mounted) return;
    final choice = await ReplaceSheet.show(
      context,
      item: item,
      alternatives: options,
      // The allowance has to have the dish being replaced subtracted:
      // the room for the new dish includes what the old one takes up.
      // Offline only: the allowance is arithmetic over whole nutrition
      // rows, and a serving from §7.6 carries just its energy. Online the
      // sheet shows the alternatives without a budget line rather than one
      // computed from numbers this side does not have.
      budgetAfterRemoval: offlineDish == null
          ? const DayBudget()
          : session.dayBudget.withoutPlanned(offlineDish),
    );
    if (choice == null) return;

    await session.replaceItem(item, choice);
    if (!context.mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã đổi sang ${choice.name.toLowerCase()}'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  // Online this is PATCH /meal-plan-items/{id}/status with `eaten`, which
  // writes the diary entry in the SAME request — two calls would leave a
  // window where the plan says eaten and the diary does not, and every
  // compliance figure reads both.
  Future<void> _eat(BuildContext context, MealPlanItem item) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await session.markEaten(item, slot.type);
    } on ApiFailure catch (failure) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 3),
        ),
      );
      return;
    }
    messenger.showSnackBar(
      SnackBar(
        content: Text('Đã ghi ${item.food.name.toLowerCase()} vào nhật ký'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  /// Taking a serving off the day, or putting it back.
  ///
  /// Online both are §7.6.6. Putting one back sends `kept`, not `suggested`:
  /// a client may set only the three statuses that describe what the USER
  /// did, and §4.6 reads `kept` as a weak positive rather than as nobody
  /// having said anything.
  Future<void> _skip(
    BuildContext context,
    MealPlanItem item,
    bool skipped,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await session.setSkipped(item, skipped);
    } on ApiFailure catch (failure) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 3),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    // A meal with an eaten dish cannot be rebuilt: that dish is in the diary,
    // and §7.6.2b refuses rather than replan around a record. Hidden rather
    // than offered and refused.
    final canRebuild =
        slot.items.isNotEmpty &&
        slot.items.every((i) => i.status != MealItemStatus.eaten);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: _mealTitle(context)),
            if (canRebuild)
              IconButton(
                onPressed: () => _regenerateMeal(context, slot.type),
                tooltip: 'Đổi ${slot.type.label.toLowerCase()}',
                icon: const Icon(Icons.autorenew_rounded, size: 20),
                color: AppColors.textSecondary,
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
        ..._afterTitle(context),
      ],
    );
  }

  Widget _mealTitle(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Text(slot.type.label, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(width: 8),
        // `onPlateKcal`, not `actualKcal`: a skipped serving is off the
        // meal, and showing a lunch as 620 kcal when the user removed
        // the 320 kcal half of it is simply a wrong number on screen.
        // `actualKcal` stays what it is — the plan as generated, which
        // is what the ±10 % commitment is measured on — and the line
        // below names the difference instead of hiding it.
        // Expanded so it gives way, not the meal's name, now that the
        // rebuild button shares the line.
        Expanded(
          child: Text(
            '${formatNumber(slot.onPlateKcal)} / '
            '${formatNumber(slot.targetKcal)} kcal',
            textAlign: TextAlign.end,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
              fontVariations: [FontVariation('wght', 600)],
            ),
          ),
        ),
      ],
    );
  }

  List<Widget> _afterTitle(BuildContext context) {
    return [
      if (slot.onPlateKcal < slot.actualKcal) ...[
        const SizedBox(height: 2),
        Text(
          'Đã bỏ ${slot.skippedItems.length} món · '
          '−${formatNumber(slot.actualKcal - slot.onPlateKcal)} kcal so '
          'với thực đơn gốc',
          style: const TextStyle(fontSize: 12, color: AppColors.textTertiary),
        ),
      ],
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
            onSkip: () => _skip(context, item, true),
            onRestore: () => _skip(context, item, false),
          ),
          _WhyRow(item: item, session: session),
        ],
    ];
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
    // Offline only. Every line of this row is computed from the whole dish
    // — the match sentences from the feature vector, the soft penalty from
    // the nutrition row, the share from scoring the rest of the catalogue —
    // and a serving from §7.6 carries none of that. Online the explanation
    // belongs to the service that did the scoring, and until there is an
    // endpoint for it the row is absent rather than invented.
    final dish = item.dish;
    if (dish == null) return const SizedBox.shrink();

    final cau = matchSentences(session.preference, dish, limit: 2);
    final penalty = PenaltyOutcome.of(
      dish,
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
                  food: dish,
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
    final dish = item.dish;
    if (dish == null || session.preference.isEmpty) return null;
    final diem = session.preference.score(dish);
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
