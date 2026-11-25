import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/app_card.dart';
import '../../data/api/failure.dart';
import '../../core/dish_look.dart';
import '../../data/mock/mock_ingredients.dart';
import '../../data/models/food_brief.dart';
import '../../data/models/food_detail.dart';
import '../../data/rules/day_budget.dart';
import '../../data/models/meal_plan.dart';
import '../../data/session.dart';
import '../plan/widgets/replace_sheet.dart';

/// Everything known about one dish: picture, energy, the nutrients the rules
/// act on, what goes into it, and the two verdicts the user can leave on it.
///
/// Opened by tapping a dish anywhere it appears. Mirrors `GET /foods/{id}`,
/// except for the ingredient block, which has no server source yet.
///
/// Stateful because both verdicts are now a round trip: the bookmark and the
/// "không gợi ý món này nữa" switch each write to the server and either can
/// be refused, so the controls have to be disabled while in flight and put
/// back when the answer is no.
class FoodDetailScreen extends StatefulWidget {
  const FoodDetailScreen({super.key, required this.dish});

  /// What the list that opened this screen already knew. Shown at once, so
  /// the name and the picture are never a spinner; the nutrition underneath
  /// arrives from §7.5.2, which is the only answer in the API carrying a
  /// whole `food_nutrition` row.
  final FoodBrief dish;

  static Future<void> open(BuildContext context, FoodBrief dish) =>
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => FoodDetailScreen(dish: dish)),
      );

  @override
  State<FoodDetailScreen> createState() => _FoodDetailScreenState();
}

/// Which of the three the user picked for a serving already on the plate.
enum _PlateChoice { keep, skip, replace }

class _FoodDetailScreenState extends State<FoodDetailScreen> {
  /// True while a mark is being written. Both controls read it, because
  /// setting one mark clears the other: letting the bookmark be tapped while
  /// the block is in flight would race two writes to the same row.
  bool _saving = false;

  FoodDetail? _detail;
  ApiFailure? _error;
  bool _loading = true;

  FoodBrief get food => widget.dish;

  @override
  void initState() {
    super.initState();
    // `didChangeDependencies` and not `initState` for the session lookup:
    // `SessionScope.of` reads an inherited widget, which asserts if it is
    // called before the first build.
    _started = false;
  }

  bool _started = true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final session = SessionScope.of(context);
    try {
      final detail = await session.dishDetail(widget.dish);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
      });
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _error = failure;
        _loading = false;
      });
    }
  }

  /// Runs one mark write, turning a failure into something the user can act
  /// on. Returns nothing: what was actually stored is read back off the
  /// session, because a refusal leaves it as it was.
  Future<void> _write(Future<void> Function() save) async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      await save();
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      if (failure.code == ApiFailure.blockWouldEmptyMeal) {
        // A dialog and not a snackbar. The user is being told they cannot
        // have what they asked for, and the reason names the meal that would
        // break — that is worth reading, not glimpsing.
        await showDialog<void>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: const Text('Không bỏ được món này'),
            content: Text(failure.message),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Đã hiểu'),
              ),
            ],
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(failure.message),
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _setNeverAgain(AppSession session, bool value) async {
    await _write(() => session.setNeverAgain(food, value));
    if (!mounted) return;

    // What was actually stored, not what was asked for: a refusal leaves the
    // set alone, and everything below is about a dish that really is blocked
    // now.
    if (!session.neverAgainIds.contains(food.id)) {
      if (value) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 2),
          content: Text('Đã cho ${food.name.toLowerCase()} quay lại'),
        ),
      );
      return;
    }

    // The dish is out of every plan from here on. Today's plate is NOT
    // touched by the write, deliberately: the user answered a question about
    // what gets suggested, and silently dropping a serving would move the
    // day's energy figure under someone who was not asked about today. So it
    // is offered as its own choice, and nothing is generated in its place.
    final item = session.plannedTodayItem(food);
    if (item == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 2),
          content: Text(
            'Từ thực đơn sau sẽ không còn ${food.name.toLowerCase()}',
          ),
        ),
      );
      return;
    }
    await _offerToClearThePlate(session, item);
  }

  Future<void> _offerToClearThePlate(
    AppSession session,
    MealPlanItem item,
  ) async {
    final choice = await showDialog<_PlateChoice>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Món này vẫn trong thực đơn hôm nay'),
        content: Text(
          'Thực đơn sắp tới sẽ không còn ${food.name.toLowerCase()}, nhưng '
          'suất hôm nay thì vẫn còn. Bạn muốn làm gì với suất đó?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(_PlateChoice.keep),
            child: const Text('Giữ nguyên'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(_PlateChoice.skip),
            child: const Text('Bỏ suất đó'),
          ),
          TextButton(
            onPressed: () =>
                Navigator.of(dialogContext).pop(_PlateChoice.replace),
            child: const Text('Đổi món khác'),
          ),
        ],
      ),
    );
    if (!mounted || choice == null || choice == _PlateChoice.keep) return;

    if (choice == _PlateChoice.skip) {
      session.setSkipped(item, true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          duration: Duration(seconds: 3),
          content: Text(
            'Đã bỏ suất đó. Năng lượng hôm nay giảm theo, và không có món '
            'nào tự thay vào.',
          ),
        ),
      );
      return;
    }

    final offlineDish = item.dish;
    final replacement = await ReplaceSheet.show(
      context,
      item: item,
      alternatives: session.alternativesFor(item),
      scoreOf: session.preference.score,
      // Offline only, for the same reason as the plan screen's sheet: the
      // allowance is arithmetic over whole nutrition rows, and a serving
      // from §7.6 carries only its energy.
      budgetAfterRemoval: offlineDish == null
          ? const DayBudget()
          : session.dayBudget.withoutPlanned(offlineDish),
    );
    if (!mounted || replacement == null) return;
    session.replaceItem(item, replacement);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        duration: const Duration(seconds: 2),
        content: Text('Đã đổi sang ${replacement.name.toLowerCase()}'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final loved = session.lovedIds.contains(food.id);
    final banned = session.neverAgainIds.contains(food.id);
    final ingredients = MockIngredients.of(food.id);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: 260,
            backgroundColor: AppColors.surface,
            surfaceTintColor: Colors.transparent,
            foregroundColor: AppColors.textPrimary,
            leading: _RoundButton(
              icon: Icons.arrow_back_rounded,
              tooltip: 'Quay lại',
              onTap: () => Navigator.of(context).pop(),
            ),
            actions: [
              // A bookmark, not a heart. The heart read as a rating, and the
              // user would reasonably expect the system to learn from it —
              // but it feeds nothing: a dish that has never been eaten
              // cannot carry an opinion the model may use (§7.8.1), so this
              // is a list the user keeps and nothing more. A bookmark says
              // that; a heart promised otherwise.
              _RoundButton(
                icon: loved
                    ? Icons.bookmark_rounded
                    : Icons.bookmark_border_rounded,
                color: loved ? AppColors.accentInk : AppColors.textPrimary,
                tooltip: loved ? 'Bỏ khỏi món đã lưu' : 'Lưu món này',
                onTap: _saving ? null : () => _write(() => session.toggleLoved(food)),
              ),
              const SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(background: _Hero(food: food)),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
            sliver: SliverList.list(
              children: [
                Text(
                  food.name,
                  style: const TextStyle(
                    fontFamily: AppTheme.fontDisplay,
                    fontSize: 30,
                    height: 1.15,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 800)],
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${food.dishRole} · ${food.category} · '
                  '${formatNumber(food.servingSizeG)} g mỗi suất',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    // Only offline, where there is a local vector and a
                    // local dish to put through it. Online the taste model
                    // lives in the ML service and no endpoint scores one
                    // dish, so the tag goes rather than showing a number
                    // this side made up.
                    if (session.scoreOf(food) case final score?)
                      _Tag('Hợp gu ${(score * 100).round()}%', accent: true),
                    if (food.spiceLevel > 0)
                      _Tag('Cay ${'🌶' * food.spiceLevel}'),
                    for (final t in food.tags) _Tag(t),
                  ],
                ),
                const SizedBox(height: 18),
                if (_loading)
                  const _Pending()
                else if (_error case final failure?)
                  _LoadFailed(failure: failure, onRetry: _load)
                else if (_detail case final detail?) ...[
                  if (detail.warnings.isNotEmpty) ...[
                    _WarningsCard(warnings: detail.warnings),
                    const SizedBox(height: 14),
                  ],
                  _EnergyCard(nutrition: detail.nutrition),
                  const SizedBox(height: 14),
                  AppCard(
                    title: 'Trong một suất',
                    child: Column(
                      children: [
                        // Every one of these can be absent, and `null` is
                        // never 0: the Vietnamese food composition table
                        // leaves real gaps, and printing "0 mg" where the
                        // answer is "nobody measured it" is the kind of false
                        // statement that reads as reassuring.
                        _Amount('Đường', detail.nutrition.sugarG, 'g', 1),
                        _Amount('Natri', detail.nutrition.sodiumMg, 'mg', 0),
                        _Amount('Chất xơ', detail.nutrition.fiberG, 'g', 1),
                        _Amount(
                          'Purin',
                          detail.nutrition.purineMg,
                          'mg',
                          0,
                          last: true,
                        ),
                      ],
                    ),
                  ),
                ],
                if (ingredients.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  AppCard(
                    title: 'Nguyên liệu cho một suất',
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        for (var i = 0; i < ingredients.length; i++)
                          _Fact(
                            '${ingredients[i].aisle.emoji}  ${ingredients[i].name}',
                            '${formatNumber(ingredients[i].grams)} g',
                            last: i == ingredients.length - 1,
                          ),
                        const SizedBox(height: 10),
                        const Text(
                          'Khối lượng ước lượng cho một suất.',
                          style: TextStyle(
                            fontSize: 12,
                            color: AppColors.textTertiary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 14),
                _NeverAgainCard(
                  banned: banned,
                  onChanged: _saving
                      ? null
                      : (v) => _setNeverAgain(session, v),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero({required this.food});

  final FoodBrief food;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: food.gradient,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: food.imageAsset == null
          ? Center(
              child: Text(food.emoji, style: const TextStyle(fontSize: 96)),
            )
          : Image.asset(
              food.imageAsset!,
              fit: BoxFit.cover,
              color: food.gradient.last.withValues(alpha: 0.25),
              colorBlendMode: BlendMode.overlay,
            ),
    );
  }
}

/// Circular white button that stays legible over the hero picture.
class _RoundButton extends StatelessWidget {
  const _RoundButton({
    required this.icon,
    required this.tooltip,
    required this.onTap,
    this.color = AppColors.textPrimary,
  });

  final IconData icon;
  final String tooltip;

  /// `null` disables the button, which `IconButton` already renders as
  /// greyed out — what the bookmark needs while its write is in flight.
  final VoidCallback? onTap;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Material(
        color: AppColors.surface,
        shape: const CircleBorder(),
        child: IconButton(
          tooltip: tooltip,
          onPressed: onTap,
          icon: Icon(icon, size: 22, color: color),
          constraints: const BoxConstraints.tightFor(width: 40, height: 40),
          padding: EdgeInsets.zero,
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, {this.accent = false});

  final String text;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: accent ? AppColors.accentSoft : AppColors.surface,
        borderRadius: BorderRadius.circular(999),
        border: accent ? null : Border.all(color: AppColors.border),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 12.5,
          color: accent ? AppColors.accentInk : AppColors.textSecondary,
          fontVariations: const [FontVariation('wght', 600)],
        ),
      ),
    );
  }
}

/// Energy of the serving, and where it comes from.
class _EnergyCard extends StatelessWidget {
  const _EnergyCard({required this.nutrition});

  final DishNutrition nutrition;

  @override
  Widget build(BuildContext context) {
    final share = nutrition.macroShare;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                formatNumber(nutrition.caloriesKcal),
                style: const TextStyle(
                  fontSize: 40,
                  height: 1,
                  color: AppColors.textPrimary,
                  fontVariations: [FontVariation('wght', 700)],
                ),
              ),
              const SizedBox(width: 6),
              const Text(
                'kcal mỗi suất',
                style: TextStyle(fontSize: 14, color: AppColors.textSecondary),
              ),
            ],
          ),
          // No bars when any of the three macros is missing. Two thirds of
          // a composition is not a composition, and drawing it as one would
          // overstate whichever macros happen to be known — the bar would
          // fill, so it would read as complete.
          if (share == null)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: Text(
                'Chưa có đủ số liệu đạm · bột đường · béo để tách tỉ lệ.',
                style: TextStyle(fontSize: 12.5, color: AppColors.textTertiary),
              ),
            )
          else ...[
            const SizedBox(height: 16),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: SizedBox(
                height: 8,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final part in [
                      (share.protein, AppColors.protein),
                      (share.carbs, AppColors.carb),
                      (share.fat, AppColors.fat),
                    ])
                      if (part.$1 > 0)
                        Expanded(
                          flex: (part.$1 * 1000).round().clamp(1, 1000),
                          child: ColoredBox(color: part.$2),
                        ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                _Macro(
                  'Đạm',
                  nutrition.proteinG!,
                  share.protein,
                  AppColors.protein,
                ),
                _Macro(
                  'Bột đường',
                  nutrition.carbsG!,
                  share.carbs,
                  AppColors.carb,
                ),
                _Macro('Béo', nutrition.fatG!, share.fat, AppColors.fat),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _Macro extends StatelessWidget {
  const _Macro(this.label, this.grams, this.share, this.color);

  final String label;
  final double grams;
  final double share;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${formatNumber(grams, 1)} g',
            style: const TextStyle(
              fontSize: 16,
              color: AppColors.textPrimary,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
          Text(
            '${(share * 100).round()}% năng lượng',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 11.5,
              color: AppColors.textTertiary,
            ),
          ),
        ],
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact(this.label, this.value, {this.muted = false, this.last = false});

  final String label;
  final String value;
  final bool muted;
  final bool last;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10),
      decoration: BoxDecoration(
        border: last
            ? null
            : const Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 14.5,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 14.5,
              color: muted ? AppColors.textTertiary : AppColors.textPrimary,
              fontVariations: [FontVariation('wght', muted ? 500 : 700)],
            ),
          ),
        ],
      ),
    );
  }
}

/// The hard "never suggest this again" switch.
///
/// Kept apart from swapping a dish out: a swap says *not today*, this says
/// *not ever*, and the dish leaves the candidate pool before scoring.
class _NeverAgainCard extends StatelessWidget {
  const _NeverAgainCard({required this.banned, required this.onChanged});

  final bool banned;

  /// `null` while a mark is being written, which disables the switch: the
  /// two marks share one row, so a second tap would race the first.
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.fromLTRB(20, 14, 12, 14),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Không gợi ý món này nữa',
                  style: TextStyle(
                    fontSize: 15,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  banned
                      ? 'Món này đang bị loại khỏi mọi thực đơn sắp tới. '
                            'Bỏ công tắc là món quay lại.'
                      : 'Món sẽ bị loại khỏi mọi thực đơn sắp tới. Suất '
                            'hôm nay vẫn còn, và không có món nào tự thay '
                            'vào.',
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.4,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: banned,
            onChanged: onChanged,
            activeTrackColor: AppColors.ink,
          ),
        ],
      ),
    );
  }
}

/// While §7.5.2 is in flight. A card and not a full-screen spinner: the name
/// and the picture are already on screen from the list row, so only the part
/// that is actually unknown should look unknown.
class _Pending extends StatelessWidget {
  const _Pending();

  @override
  Widget build(BuildContext context) {
    return const AppCard(
      child: SizedBox(
        height: 96,
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      ),
    );
  }
}

/// When the nutrition could not be fetched.
///
/// It says what is missing rather than showing the dish as though nothing
/// were: a detail screen with no numbers and no warnings looks like a dish
/// with nothing to warn about, which for someone with an allergy is the one
/// mistake this screen must not make.
class _LoadFailed extends StatelessWidget {
  const _LoadFailed({required this.failure, required this.onRetry});

  final ApiFailure failure;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Chưa tải được thông tin dinh dưỡng',
            style: TextStyle(
              fontSize: 15,
              color: AppColors.textPrimary,
              fontVariations: [FontVariation('wght', 700)],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            failure.message,
            style: const TextStyle(
              fontSize: 13,
              height: 1.4,
              color: AppColors.textSecondary,
            ),
          ),
          if (failure.isRetryable) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton(onPressed: onRetry, child: const Text('Thử lại')),
            ),
          ],
        ],
      ),
    );
  }
}

/// The hard medical rules this dish breaks for this user — §7.5.2's
/// `warnings[]`.
///
/// Above the numbers, because it is the one part of the screen that can stop
/// someone eating something. The sentences are written by the backend and
/// shown as they arrive: the app composes no safety prose, so there is one
/// wording per rule and one place it comes from.
class _WarningsCard extends StatelessWidget {
  const _WarningsCard({required this.warnings});

  final List<FoodWarning> warnings;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.warning_amber_rounded,
                size: 18,
                color: AppColors.danger,
              ),
              const SizedBox(width: 6),
              Text(
                warnings.length == 1
                    ? 'Món này không phù hợp với bạn'
                    : 'Món này vi phạm ${warnings.length} quy tắc',
                style: const TextStyle(
                  fontSize: 15,
                  color: AppColors.danger,
                  fontVariations: [FontVariation('wght', 700)],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          // Every rule, not the first. Fixing one does not make the dish
          // acceptable, so the user has to see them all.
          for (final warning in warnings) ...[
            Text(
              '· ${warning.message}',
              style: const TextStyle(
                fontSize: 13,
                height: 1.45,
                color: AppColors.textSecondary,
              ),
            ),
            if (warning != warnings.last) const SizedBox(height: 4),
          ],
        ],
      ),
    );
  }
}

/// One nutrition figure, or the fact that nobody measured it.
///
/// The muted "Chưa có số liệu" is the whole reason this is its own widget:
/// `null` is not 0 anywhere in this project, and a health app that prints
/// "Purin 0 mg" for an unmeasured dish has told a gout patient it is safe.
class _Amount extends StatelessWidget {
  const _Amount(
    this.label,
    this.value,
    this.unit,
    this.decimals, {
    this.last = false,
  });

  final String label;
  final double? value;
  final String unit;
  final int decimals;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final amount = value;
    return _Fact(
      label,
      amount == null
          ? 'Chưa có số liệu'
          : '${formatNumber(amount, decimals)} $unit',
      muted: amount == null,
      last: last,
    );
  }
}
