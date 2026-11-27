import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/dish_look.dart';
import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/models/diary_day.dart';
import '../../data/models/diary_entry.dart';
import '../../data/models/food.dart';
import '../../data/models/food_brief.dart';
import '../../data/models/food_query.dart';
import '../../data/models/meal_plan.dart';
import '../../data/session.dart';
import '../plan/widgets/week_strip.dart';

/// The food diary — the `food_diary` table.
///
/// This screen records what the user **actually ate**, not what the system
/// recommended. The gap between the two is the most important signal there is
/// after the survey: dishes in the plan that were skipped, dishes outside it
/// that were eaten, and the rating given after eating.
///
/// Any past day can be opened, from the week strip or the month calendar: a
/// health log that only shows today is a counter, not a log. Days after today
/// cannot — nothing has been eaten on them.
///
/// Stateful because online the log lives in `food_diary` — §7.7.1 — and
/// taking a line back is a round trip that can be refused.
class DiaryScreen extends StatefulWidget {
  const DiaryScreen({super.key});

  @override
  State<DiaryScreen> createState() => _DiaryScreenState();
}

class _DiaryScreenState extends State<DiaryScreen> {
  bool _started = false;

  /// The day on screen. Local to this screen and not in the session: the
  /// plan tab has its own selected day, and the two answering different
  /// questions — what to eat, what was eaten — should not drag each other.
  DateTime _day = _today();

  static DateTime _today() {
    final now = DateTime.now();
    return DateTime(now.year, now.month, now.day);
  }

  static bool _same(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  bool get _isToday => _same(_day, _today());

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _load();
  }

  Future<void> _load() async {
    final session = SessionScope.of(context);
    try {
      await session.loadDiary();
    } on ApiFailure catch (failure) {
      _fail(failure, retry: _load);
      return;
    }
    await _loadSummary(_day);
  }

  void _fail(ApiFailure failure, {VoidCallback? retry}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 3),
          action: retry != null && failure.isRetryable
              ? SnackBarAction(label: 'Thử lại', onPressed: retry)
              : null,
        ),
      );
  }

  /// §7.7.5 for the day on screen. `null` offline, and `null` while it is in
  /// flight — the card falls back to what this side can compute, which is
  /// the whole of the offline mode's answer.
  DaySummary? _summary;

  Future<void> _goTo(DateTime day) async {
    final target = DateTime(day.year, day.month, day.day);
    if (target.isAfter(_today())) return;
    setState(() {
      _day = target;
      // Dropped at once: keeping the previous day's figures while the new
      // ones arrive would show yesterday's intake under today's heading.
      _summary = null;
    });
    try {
      await SessionScope.of(context).ensureDiaryCovers(target);
      await _loadSummary(target);
    } on ApiFailure catch (failure) {
      _fail(failure, retry: () => _goTo(target));
    }
  }

  /// A failure here is deliberately quiet. The card has a fallback it can
  /// draw, and a day whose summary did not arrive is not a day whose diary
  /// did not — the lines are already on screen, and shouting about a figure
  /// would suggest otherwise.
  Future<void> _loadSummary(DateTime day) async {
    final session = SessionScope.of(context);
    try {
      final loaded = await session.daySummary(date: day);
      if (!mounted || !_isSameDay(day, _day)) return;
      setState(() => _summary = loaded);
    } on ApiFailure {
      if (mounted) setState(() => _summary = null);
    }
  }

  static bool _isSameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  Future<void> _pickFromCalendar(AppSession session) async {
    final picked = await _MonthSheet.show(
      context,
      selected: _day,
      hasEntries: (d) => session.entriesOn(d).isNotEmpty,
    );
    if (picked != null) await _goTo(picked);
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final entries = session.entriesOn(_day);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 12, 0),
                child: _Header(
                  day: _day,
                  isToday: _isToday,
                  onToday: () => _goTo(_today()),
                  onCalendar: () => _pickFromCalendar(session),
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 14, 12, 0),
                child: _DiaryWeek(
                  selected: _day,
                  onSelected: _goTo,
                  hasEntries: (d) => session.entriesOn(d).isNotEmpty,
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                child: _ConsumedCard(
                  target:
                      session.planOn(_day)?.targetKcal ??
                      session.profile.energyTarget ??
                      0,
                  entries: entries,
                  summary: _summary,
                ),
              ),
            ),
            if (entries.isEmpty)
              SliverToBoxAdapter(child: _EmptyDiary(isToday: _isToday))
            else
              for (final type in MealType.values)
                SliverToBoxAdapter(
                  child: _MealGroup(
                    session: session,
                    type: type,
                    entries: entries.where((e) => e.meal == type).toList(),
                  ),
                ),
            // Room for the button floating over the last row.
            const SliverToBoxAdapter(child: SizedBox(height: 96)),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showAddSheet(context, session),
        backgroundColor: AppColors.ink,
        foregroundColor: AppColors.textOnDark,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Ghi món đã ăn'),
      ),
    );
  }

  Future<void> _showAddSheet(BuildContext context, AppSession session) async {
    final day = _day;
    final result =
        await showModalBottomSheet<({FoodBrief food, MealType meal})>(
          context: context,
          backgroundColor: Colors.transparent,
          isScrollControlled: true,
          builder: (_) => _AddEntrySheet(
            session: session,
            day: day,
            initialMeal: _isToday ? _mealAt(DateTime.now()) : MealType.lunch,
          ),
        );
    if (result == null) return;

    try {
      await session.addEaten(food: result.food, meal: result.meal, ateOn: day);
    } on ApiFailure catch (failure) {
      _fail(failure);
    }
  }

  /// The meal a dish logged at [time] most likely belongs to.
  static MealType _mealAt(DateTime time) => switch (time.hour) {
    < 10 => MealType.breakfast,
    < 14 => MealType.lunch,
    < 17 => MealType.snack,
    _ => MealType.dinner,
  };
}

const _weekdays = [
  'Thứ hai',
  'Thứ ba',
  'Thứ tư',
  'Thứ năm',
  'Thứ sáu',
  'Thứ bảy',
  'Chủ nhật',
];

String _dateLine(DateTime d) =>
    '${_weekdays[d.weekday - 1]}, ${d.day}/${d.month}/${d.year}';

class _Header extends StatelessWidget {
  const _Header({
    required this.day,
    required this.isToday,
    required this.onToday,
    required this.onCalendar,
  });

  final DateTime day;
  final bool isToday;
  final VoidCallback onToday;
  final VoidCallback onCalendar;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                isToday ? 'Nhật ký hôm nay' : 'Nhật ký',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 4),
              Text(
                _dateLine(day),
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ),
        ),
        if (!isToday)
          TextButton(onPressed: onToday, child: const Text('Về hôm nay')),
        IconButton(
          onPressed: onCalendar,
          tooltip: 'Chọn ngày',
          icon: const Icon(Icons.calendar_month_rounded),
          color: AppColors.textPrimary,
        ),
      ],
    );
  }
}

/// Monday to Sunday of the week holding the day on screen, with arrows to
/// step a week at a time. Days after today are drawn but cannot be opened.
class _DiaryWeek extends StatelessWidget {
  const _DiaryWeek({
    required this.selected,
    required this.onSelected,
    required this.hasEntries,
  });

  final DateTime selected;
  final ValueChanged<DateTime> onSelected;
  final bool Function(DateTime day) hasEntries;

  static const _short = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final monday = selected.subtract(Duration(days: selected.weekday - 1));
    final nextMonday = monday.add(const Duration(days: 7));

    return Row(
      children: [
        IconButton(
          // The same weekday a week back, so "last Tuesday" is one tap.
          onPressed: () =>
              onSelected(selected.subtract(const Duration(days: 7))),
          tooltip: 'Tuần trước',
          icon: const Icon(Icons.chevron_left_rounded),
          visualDensity: VisualDensity.compact,
        ),
        for (var i = 0; i < 7; i++)
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(left: i == 0 ? 0 : 4),
              child: _chip(monday.add(Duration(days: i)), today),
            ),
          ),
        IconButton(
          // The week after holds no past day once it starts after today.
          onPressed: nextMonday.isAfter(today)
              ? null
              : () {
                  final ahead = selected.add(const Duration(days: 7));
                  onSelected(ahead.isAfter(today) ? today : ahead);
                },
          tooltip: 'Tuần sau',
          icon: const Icon(Icons.chevron_right_rounded),
          visualDensity: VisualDensity.compact,
        ),
      ],
    );
  }

  Widget _chip(DateTime day, DateTime today) {
    final isToday = day == today;
    return DayChip(
      day: day,
      label: isToday ? 'Nay' : _short[day.weekday - 1],
      selected: day == selected,
      planned: hasEntries(day),
      enabled: !day.isAfter(today),
      onTap: () => onSelected(day),
    );
  }
}

/// A month of days to jump to — for a day further back than the week strip
/// reaches with a few taps.
///
/// Its own grid rather than `showDatePicker`: the app ships no Material
/// localisations, so the stock picker would speak English in a Vietnamese
/// app.
class _MonthSheet extends StatefulWidget {
  const _MonthSheet({required this.selected, required this.hasEntries});

  final DateTime selected;
  final bool Function(DateTime day) hasEntries;

  static Future<DateTime?> show(
    BuildContext context, {
    required DateTime selected,
    required bool Function(DateTime day) hasEntries,
  }) => showModalBottomSheet<DateTime>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) => _MonthSheet(selected: selected, hasEntries: hasEntries),
  );

  @override
  State<_MonthSheet> createState() => _MonthSheetState();
}

class _MonthSheetState extends State<_MonthSheet> {
  late DateTime _month = DateTime(widget.selected.year, widget.selected.month);

  static const _heads = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'];

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final first = DateTime(_month.year, _month.month);
    final daysIn = DateTime(_month.year, _month.month + 1, 0).day;
    final lead = first.weekday - 1;
    final isCurrentMonth =
        _month.year == today.year && _month.month == today.month;

    return Container(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  IconButton(
                    onPressed: () => setState(
                      () => _month = DateTime(_month.year, _month.month - 1),
                    ),
                    tooltip: 'Tháng trước',
                    icon: const Icon(Icons.chevron_left_rounded),
                  ),
                  Expanded(
                    child: Text(
                      'Tháng ${_month.month}, ${_month.year}',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    onPressed: isCurrentMonth
                        ? null
                        : () => setState(
                            () => _month = DateTime(
                              _month.year,
                              _month.month + 1,
                            ),
                          ),
                    tooltip: 'Tháng sau',
                    icon: const Icon(Icons.chevron_right_rounded),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  for (final h in _heads)
                    Expanded(
                      child: Text(
                        h,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.textSecondary,
                          fontVariations: [FontVariation('wght', 600)],
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 6),
              GridView.count(
                crossAxisCount: 7,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 1,
                children: [
                  for (var i = 0; i < lead; i++) const SizedBox.shrink(),
                  for (var d = 1; d <= daysIn; d++)
                    _cell(DateTime(_month.year, _month.month, d), today),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _cell(DateTime day, DateTime today) {
    final future = day.isAfter(today);
    final selected = day == widget.selected;
    final isToday = day == today;
    final logged = !future && widget.hasEntries(day);

    return Padding(
      padding: const EdgeInsets.all(3),
      child: Material(
        color: selected ? AppColors.ink : Colors.transparent,
        shape: CircleBorder(
          side: isToday && !selected
              ? const BorderSide(color: AppColors.ink, width: 1.4)
              : BorderSide.none,
        ),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: future ? null : () => Navigator.of(context).pop(day),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                '${day.day}',
                style: TextStyle(
                  fontSize: 15,
                  color: selected
                      ? AppColors.textOnDark
                      : future
                      ? AppColors.textTertiary
                      : AppColors.textPrimary,
                  fontVariations: const [FontVariation('wght', 600)],
                ),
              ),
              const SizedBox(height: 2),
              Container(
                width: 4,
                height: 4,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: !logged
                      ? Colors.transparent
                      : selected
                      ? AppColors.accent
                      : AppColors.accentInk,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The energy taken in, against the target.
///
/// Different from the card on the plan screen: there it is the **projection**
/// from the plan, here it is the **reality** from the diary. The two numbers
/// differing is entirely normal, and it is precisely what shows whether the
/// plan is being followed.
class _ConsumedCard extends StatelessWidget {
  const _ConsumedCard({
    required this.target,
    required this.entries,
    this.summary,
  });

  /// That day's target: the plan's when the day had one, the profile's
  /// otherwise. Used only when [summary] is absent.
  final double target;
  final List<DiaryEntry> entries;

  /// §7.7.5's answer for this day, when there is a server to ask.
  ///
  /// It wins over the two above, and for a reason worth stating: its target
  /// is the one that applied **on that day** — the snapshot stored with the
  /// plan, or the profile's columns as they stood. Computing it here from
  /// today's profile would invent a new answer for a past day, the day the
  /// user weighed three kilograms more. And its `consumed` is summed from
  /// whole nutrition rows, which the lines on this side do not carry.
  final DaySummary? summary;

  @override
  Widget build(BuildContext context) {
    final day = summary;
    final target = day?.targets.caloriesKcal ?? this.target;
    final consumed =
        day?.consumed.caloriesKcal ??
        entries.fold<double>(0, (sum, e) => sum + e.kcal);
    // Allowed to be negative. Clamping it would hide exactly what this card
    // exists to show, and §7.7.5 sends it unclamped for the same reason.
    final remaining = day?.remaining.caloriesKcal ?? (target - consumed);
    final ratio = target <= 0 ? 0.0 : (consumed / target).clamp(0.0, 1.0);

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _Stat(
                  label: 'Đã nạp',
                  value: formatNumber(consumed),
                  unit: 'kcal',
                ),
              ),
              Expanded(
                child: _Stat(
                  label: remaining >= 0 ? 'Còn lại' : 'Vượt',
                  value: formatNumber(remaining.abs()),
                  unit: 'kcal',
                  color: remaining >= 0 ? AppColors.like : AppColors.dislike,
                ),
              ),
              Expanded(
                child: _Stat(
                  label: 'Đã ăn',
                  value: '${entries.length}',
                  unit: 'món',
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: 7,
              backgroundColor: AppColors.surfaceMuted,
              valueColor: const AlwaysStoppedAnimation(AppColors.kcal),
            ),
          ),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({
    required this.label,
    required this.value,
    required this.unit,
    this.color,
  });

  final String label;
  final String value;
  final String unit;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 12.5,
            color: AppColors.textSecondary,
            fontVariations: [FontVariation('wght', 600)],
          ),
        ),
        const SizedBox(height: 5),
        Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            // The three statistics cells split the width evenly, so each
            // is very narrow; a four-digit number plus its unit has to be
            // able to shrink rather than spill into the next cell.
            Flexible(
              child: Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 22,
                  height: 1,
                  color: color ?? AppColors.textPrimary,
                  fontVariations: const [FontVariation('wght', 700)],
                ),
              ),
            ),
            const SizedBox(width: 3),
            Text(
              unit,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textTertiary,
                fontVariations: [FontVariation('wght', 600)],
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _MealGroup extends StatelessWidget {
  const _MealGroup({
    required this.session,
    required this.type,
    required this.entries,
  });

  final AppSession session;
  final MealType type;
  final List<DiaryEntry> entries;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(type.label, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          for (final entry in entries)
            _DiaryTile(
              entry: entry,
              onRate: (stars) => _rate(context, session, entry, stars),
              onUndo: () => _undo(context, session, entry),
              onEdit: () => _edit(context, session, entry),
            ),
        ],
      ),
    );
  }
}

/// Sends a rating, after making sure the user means to.
///
/// **It asks first, and that is a decided behaviour rather than politeness.**
/// §7.8.1 locks the diary line this rating could be the evidence for: from
/// then on §7.7.3 and §7.7.4 both refuse it, and the edit and undo buttons
/// disappear. So the user is giving up the ability to correct what they
/// logged, and they should be told that before the stars are sent, not after
/// the buttons have gone.
Future<void> _rate(
  BuildContext context,
  AppSession session,
  DiaryEntry entry,
  int stars,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text('Đánh giá ${stars.clamp(1, 5)} sao?'),
      content: Text(
        'Sau khi đánh giá, dòng "${entry.food.name}" trong nhật ký sẽ '
        'không sửa hay hoàn tác được nữa — đánh giá dựa trên bữa đã ăn, '
        'nên bữa đó được giữ nguyên làm bằng chứng.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Để sau'),
        ),
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Đánh giá'),
        ),
      ],
    ),
  );
  if (confirmed != true) return;

  try {
    await session.rate(entry, stars);
  } on ApiFailure catch (failure) {
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 4),
        ),
      );
  }
}

/// Takes one line back.
///
/// The wording follows [DiaryEntry.fromMealPlan], because the two cases are
/// different acts: a serving from the plan goes back on the plate, while a
/// dish eaten elsewhere is a line of a health log being removed. §7.7.4
/// decides the BEHAVIOUR from the data; this only decides the sentence.
Future<void> _undo(
  BuildContext context,
  AppSession session,
  DiaryEntry entry,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final wasPlanned = entry.fromMealPlan;
  final name = entry.food.name;
  try {
    await session.undoMeal(entry);
  } on ApiFailure catch (failure) {
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 4),
        ),
      );
    return;
  }
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(
          wasPlanned ? 'Đã trả $name về thực đơn' : 'Đã bỏ $name khỏi nhật ký',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
}

/// Corrects one line: the meal it was eaten at, and how much was eaten.
///
/// Only those two, as §7.7.3 allows. A different dish or a different day is
/// a different eating — changing them in place would carry a rating over to
/// a dish the user never said anything about — so the sheet offers to take
/// the line back instead, and a new one can be logged.
Future<void> _edit(
  BuildContext context,
  AppSession session,
  DiaryEntry entry,
) async {
  final messenger = ScaffoldMessenger.of(context);
  final result = await showModalBottomSheet<_EditResult>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) => _EditEntrySheet(entry: entry),
  );
  if (result == null || !context.mounted) return;

  if (result.undo) {
    await _undo(context, session, entry);
    return;
  }

  try {
    await session.editEaten(
      entry,
      meal: result.meal,
      servingSizeG: result.grams,
    );
  } on ApiFailure catch (failure) {
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(failure.message),
          duration: const Duration(seconds: 4),
        ),
      );
    return;
  }
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text('Đã sửa ${entry.food.name}'),
        duration: const Duration(seconds: 2),
      ),
    );
}

class _DiaryTile extends StatelessWidget {
  const _DiaryTile({
    required this.entry,
    required this.onRate,
    required this.onUndo,
    required this.onEdit,
  });

  final DiaryEntry entry;
  final ValueChanged<int> onRate;
  final VoidCallback onUndo;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final grams = entry.grams;
    final details = [
      '${formatNumber(entry.kcal)} kcal',
      if (grams > 0) '${formatNumber(grams)} g',
      '${entry.ateAt.hour.toString().padLeft(2, '0')}:'
          '${entry.ateAt.minute.toString().padLeft(2, '0')}',
    ].join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          // The row opens the correction sheet. Not on a locked line: a
          // rating has made it the evidence for that rating, and §7.7.3
          // refuses it — so it is not offered.
          InkWell(
            onTap: entry.editable ? onEdit : null,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 4, 4),
              child: Row(
                children: [
                  Text(entry.food.emoji, style: const TextStyle(fontSize: 22)),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entry.food.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 15,
                            color: AppColors.textPrimary,
                            fontVariations: [FontVariation('wght', 700)],
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          details,
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  // Hidden once a rating has locked the line, rather than
                  // shown and refused. §7.8.1 asks for exactly that, and
                  // `editable` is sent so this side does not have to work
                  // the rule out from timestamps it is not given.
                  if (entry.editable) ...[
                    IconButton(
                      onPressed: onUndo,
                      icon: const Icon(Icons.undo_rounded, size: 18),
                      color: AppColors.textTertiary,
                      tooltip: entry.fromMealPlan
                          ? 'Hoàn tác, trả về thực đơn'
                          : 'Bỏ dòng này khỏi nhật ký',
                      visualDensity: VisualDensity.compact,
                    ),
                    IconButton(
                      onPressed: onEdit,
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      color: AppColors.textTertiary,
                      tooltip: 'Sửa bữa hoặc khối lượng',
                      visualDensity: VisualDensity.compact,
                    ),
                  ] else
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 10),
                      child: Tooltip(
                        message: 'Đã chấm điểm nên không sửa được',
                        child: Icon(
                          Icons.lock_outline_rounded,
                          size: 18,
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          const Divider(height: 10, indent: 12, endIndent: 12),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: Row(
              children: [
                const Text(
                  'Ngon không?',
                  style: TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textSecondary,
                    fontVariations: [FontVariation('wght', 600)],
                  ),
                ),
                const Spacer(),
                for (var star = 1; star <= 5; star++)
                  InkWell(
                    onTap: () => onRate(star),
                    borderRadius: BorderRadius.circular(999),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Icon(
                        (entry.rating ?? 0) >= star
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        size: 24,
                        color: (entry.rating ?? 0) >= star
                            ? AppColors.carb
                            : AppColors.textTertiary,
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

class _EmptyDiary extends StatelessWidget {
  const _EmptyDiary({required this.isToday});

  final bool isToday;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 48, 32, 0),
      child: Column(
        children: [
          const Icon(
            Icons.ramen_dining_rounded,
            size: 44,
            color: AppColors.textTertiary,
          ),
          const SizedBox(height: 16),
          Text(
            isToday ? 'Chưa ghi món nào hôm nay' : 'Ngày này chưa ghi món nào',
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            isToday
                ? 'Bấm "Đã ăn" ở màn hình thực đơn, hoặc dùng nút bên dưới để '
                      'ghi một món ngoài thực đơn.'
                : 'Quên ghi hôm đó? Dùng nút bên dưới để ghi bù vào đúng ngày '
                      'này.',
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

/// What the correction sheet answered. [meal] and [grams] are `null` when
/// unchanged, so only what moved is sent.
typedef _EditResult = ({MealType? meal, int? grams, bool undo});

/// The correction sheet for one line: its meal and its weight in grams.
class _EditEntrySheet extends StatefulWidget {
  const _EditEntrySheet({required this.entry});

  final DiaryEntry entry;

  @override
  State<_EditEntrySheet> createState() => _EditEntrySheetState();
}

class _EditEntrySheetState extends State<_EditEntrySheet> {
  late MealType _meal = widget.entry.meal;
  late final int _startGrams = widget.entry.grams.round();
  late final _grams = TextEditingController(text: '$_startGrams');

  static const _step = 10;

  @override
  void dispose() {
    _grams.dispose();
    super.dispose();
  }

  int? get _value => int.tryParse(_grams.text.trim());

  /// The range §7.7.3 accepts: a tenth of a serving to five servings. With
  /// no serving known, a wide range that still catches a typo.
  (int, int) get _range {
    final serving = widget.entry.servingGrams;
    if (serving == null || serving <= 0) return (1, 2000);
    return ((serving / 10).ceil(), (serving * 5).floor());
  }

  String? get _error {
    final v = _value;
    final (min, max) = _range;
    if (v == null) return 'Nhập số gam';
    if (v < min || v > max) return 'Từ $min đến $max g';
    return null;
  }

  bool get _changed =>
      _meal != widget.entry.meal || (_value != null && _value != _startGrams);

  void _setGrams(int grams) {
    final (min, max) = _range;
    final clamped = grams.clamp(min, max);
    _grams.value = TextEditingValue(
      text: '$clamped',
      selection: TextSelection.collapsed(offset: '$clamped'.length),
    );
    setState(() {});
  }

  void _save() {
    if (_error != null || !_changed) return;
    Navigator.of(context).pop<_EditResult>((
      meal: _meal == widget.entry.meal ? null : _meal,
      grams: _value == _startGrams ? null : _value,
      undo: false,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final entry = widget.entry;
    final serving = entry.servingGrams;
    final perGram = entry.kcalPerGram;
    final value = _value;
    final preview = perGram == null || value == null ? null : perGram * value;

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.9,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
      child: Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: SafeArea(
          top: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: AppColors.border,
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Text(
                      entry.food.emoji,
                      style: const TextStyle(fontSize: 28),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            entry.food.name,
                            style: Theme.of(context).textTheme.headlineSmall,
                          ),
                          if (serving != null)
                            Text(
                              '1 suất ${formatNumber(serving)} g · '
                              '${formatNumber(serving * (perGram ?? 0))} kcal',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                const _Label('Bữa'),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final type in MealType.values)
                      _MealChip(
                        type: type,
                        selected: _meal == type,
                        onSelected: () => setState(() => _meal = type),
                      ),
                  ],
                ),
                const SizedBox(height: 20),
                const _Label('Khối lượng đã ăn'),
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _StepButton(
                      icon: Icons.remove_rounded,
                      tooltip: 'Bớt $_step g',
                      onTap: () => _setGrams((value ?? _startGrams) - _step),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: _grams,
                        keyboardType: TextInputType.number,
                        textAlign: TextAlign.center,
                        onChanged: (_) => setState(() {}),
                        style: const TextStyle(
                          fontSize: 20,
                          fontVariations: [FontVariation('wght', 700)],
                        ),
                        decoration: InputDecoration(
                          suffixText: 'g',
                          errorText: _error,
                          filled: true,
                          fillColor: AppColors.surfaceMuted,
                          contentPadding: const EdgeInsets.symmetric(
                            vertical: 12,
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    _StepButton(
                      icon: Icons.add_rounded,
                      tooltip: 'Thêm $_step g',
                      onTap: () => _setGrams((value ?? _startGrams) + _step),
                    ),
                  ],
                ),
                // Shortcuts in servings, because "half a plate" is how people
                // remember a meal and grams are how the server stores it.
                if (serving != null) ...[
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final (factor, label) in const [
                        (0.5, '½ suất'),
                        (1.0, '1 suất'),
                        (1.5, '1½ suất'),
                        (2.0, '2 suất'),
                      ])
                        ActionChip(
                          label: Text(label),
                          onPressed: () =>
                              _setGrams((serving * factor).round()),
                          backgroundColor: value == (serving * factor).round()
                              ? AppColors.accentSoft
                              : AppColors.surface,
                          side: const BorderSide(color: AppColors.border),
                          shape: const StadiumBorder(),
                        ),
                    ],
                  ),
                ],
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.accentSoft,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Tính vào nhật ký',
                          style: TextStyle(
                            fontSize: 14,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ),
                      Text(
                        preview == null ? '—' : '${formatNumber(preview)} kcal',
                        style: const TextStyle(
                          fontSize: 16,
                          color: AppColors.accentInk,
                          fontVariations: [FontVariation('wght', 700)],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Muốn đổi sang món khác hay ngày khác? Đó là một lần ăn '
                  'khác: hoàn tác dòng này rồi ghi món mới.',
                  style: TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textTertiary,
                  ),
                ),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _error == null && _changed ? _save : null,
                    child: const Text('Lưu thay đổi'),
                  ),
                ),
                const SizedBox(height: 4),
                Center(
                  child: TextButton(
                    onPressed: () => Navigator.of(
                      context,
                    ).pop<_EditResult>((meal: null, grams: null, undo: true)),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.dislike,
                    ),
                    child: Text(
                      entry.fromMealPlan
                          ? 'Hoàn tác, trả về thực đơn'
                          : 'Bỏ dòng này khỏi nhật ký',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 13,
        color: AppColors.textSecondary,
        fontVariations: [FontVariation('wght', 600)],
      ),
    );
  }
}

class _StepButton extends StatelessWidget {
  const _StepButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return IconButton.filledTonal(
      onPressed: onTap,
      tooltip: tooltip,
      icon: Icon(icon),
      style: IconButton.styleFrom(
        backgroundColor: AppColors.surfaceMuted,
        foregroundColor: AppColors.textPrimary,
        fixedSize: const Size(52, 52),
      ),
    );
  }
}

class _MealChip extends StatelessWidget {
  const _MealChip({
    required this.type,
    required this.selected,
    required this.onSelected,
  });

  final MealType type;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      label: Text(type.label),
      selected: selected,
      onSelected: (_) => onSelected(),
      showCheckmark: false,
      selectedColor: AppColors.ink,
      backgroundColor: AppColors.surfaceMuted,
      side: BorderSide.none,
      labelStyle: TextStyle(
        fontSize: 13,
        color: selected ? AppColors.textOnDark : AppColors.textPrimary,
        fontVariations: const [FontVariation('wght', 600)],
      ),
    );
  }
}

/// The dish picker for adding a diary entry, on the day the diary is showing.
///
/// Allowing a **dish from outside the plan** is mandatory: people eat out,
/// eat with family, or simply change their mind. If only dishes from the plan
/// could be recorded, the diary would always match the plan artificially and
/// the adherence rate would lose all meaning.
///
/// It searches the whole catalogue — §7.5.1 online — with the safety switch
/// **off**: a log records what happened, including a dish the user should
/// not have eaten, and §7.7.2 deliberately does not refuse one.
class _AddEntrySheet extends StatefulWidget {
  const _AddEntrySheet({
    required this.session,
    required this.day,
    required this.initialMeal,
  });

  final AppSession session;
  final DateTime day;
  final MealType initialMeal;

  @override
  State<_AddEntrySheet> createState() => _AddEntrySheetState();
}

class _AddEntrySheetState extends State<_AddEntrySheet> {
  late MealType _meal = widget.initialMeal;
  Timer? _debounce;
  List<FoodBrief> _matches = const [];
  bool _loading = true;
  ApiFailure? _error;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _search('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _onTyped(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () => _search(text));
  }

  Future<void> _search(String text) async {
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await widget.session.searchFoods(
        FoodQuery(text: text, safeOnly: false),
      );
      if (!mounted || generation != _generation) return;
      setState(() => _matches = page.items);
    } on ApiFailure catch (failure) {
      if (!mounted || generation != _generation) return;
      setState(() => _error = failure);
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final isToday =
        widget.day.year == now.year &&
        widget.day.month == now.month &&
        widget.day.day == now.day;

    // Material, not a coloured Container: the list tiles inside paint their
    // highlight and ripple on the nearest Material, which a coloured box
    // would cover.
    return Material(
      color: AppColors.surface,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(26)),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.82,
        ),
        child: Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 10),
                Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Ghi món đã ăn',
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      // A past day is named, so a late entry cannot land on
                      // the wrong day without the user seeing which.
                      if (!isToday) ...[
                        const SizedBox(height: 2),
                        Text(
                          'Ghi vào ${_dateLine(widget.day).toLowerCase()}',
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final type in MealType.values)
                            _MealChip(
                              type: type,
                              selected: _meal == type,
                              onSelected: () => setState(() => _meal = type),
                            ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        onChanged: _onTyped,
                        decoration: InputDecoration(
                          hintText: 'Tìm món…',
                          prefixIcon: const Icon(
                            Icons.search_rounded,
                            size: 20,
                          ),
                          filled: true,
                          fillColor: AppColors.surfaceMuted,
                          contentPadding: const EdgeInsets.symmetric(
                            vertical: 4,
                          ),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: BorderSide.none,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                if (_loading && _matches.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: CircularProgressIndicator(),
                  )
                else if (_error != null)
                  Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      _error!.message,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  )
                else
                  Flexible(
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                      itemCount: _matches.length,
                      itemBuilder: (context, i) {
                        final food = _matches[i];
                        return ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: Text(
                            food.emoji,
                            style: const TextStyle(fontSize: 24),
                          ),
                          title: Text(
                            food.name,
                            style: const TextStyle(
                              fontSize: 15,
                              fontVariations: [FontVariation('wght', 600)],
                            ),
                          ),
                          subtitle: Text(
                            '${formatNumber(food.kcal)} kcal · '
                            '${DishRole.labelOf(food.dishRole)}',
                          ),
                          onTap: () =>
                              Navigator.of(context)
                                  .pop((food: food, meal: _meal)),
                        );
                      },
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
