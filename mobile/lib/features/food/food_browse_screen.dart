import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/dish_look.dart';
import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/api/food_api.dart';
import '../../data/models/food.dart';
import '../../data/models/food_brief.dart';
import '../../data/models/food_query.dart';
import '../../data/models/meal_plan.dart';
import '../../data/session.dart';
import 'food_detail_screen.dart';

/// The whole catalogue, searchable — §7.5.1.
///
/// Before this screen a dish was reachable only through the day's plan or the
/// diary's add sheet, and none of §7.5.1's filters had anything driving them.
/// Here every one does: the name, the food group, the meal, the role, an
/// energy ceiling and the user's own marks, plus the safety switch.
///
/// The safety switch starts **on**, as the server's `excludeUnsafe` does:
/// browsing should not lead someone with a seafood allergy to a seafood
/// dish. Turning it off shows those dishes marked, never unmarked.
class FoodBrowseScreen extends StatefulWidget {
  const FoodBrowseScreen({super.key, this.initial = const FoodQuery()});

  final FoodQuery initial;

  static Future<void> open(BuildContext context) => Navigator.of(context)
      .push(MaterialPageRoute<void>(builder: (_) => const FoodBrowseScreen()));

  @override
  State<FoodBrowseScreen> createState() => _FoodBrowseScreenState();
}

class _FoodBrowseScreenState extends State<FoodBrowseScreen> {
  late FoodQuery _query = widget.initial;
  late final _text = TextEditingController(text: widget.initial.text);
  final _scroll = ScrollController();
  Timer? _debounce;

  final List<FoodBrief> _items = [];
  int _total = 0;
  int _page = 0;
  bool _hasMore = false;
  bool _loading = false;
  ApiFailure? _error;

  /// Bumped on every new search, so a slow page answering an old query is
  /// dropped instead of being appended to the new one.
  int _generation = 0;

  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _scroll.addListener(_maybeLoadMore);
    _search();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _text.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _setQuery(FoodQuery query) {
    setState(() => _query = query);
    _search();
  }

  void _onTyped(String value) {
    _debounce?.cancel();
    // One request per pause in typing, not per letter.
    _debounce = Timer(
      const Duration(milliseconds: 300),
      () => _setQuery(_query.copyWith(text: value)),
    );
  }

  Future<void> _search() async {
    final generation = ++_generation;
    setState(() {
      _items.clear();
      _page = 0;
      _total = 0;
      _hasMore = false;
      _error = null;
    });
    await _loadPage(generation);
  }

  void _maybeLoadMore() {
    if (!_hasMore || _loading) return;
    if (_scroll.position.extentAfter < 400) _loadPage(_generation);
  }

  Future<void> _loadPage(int generation) async {
    final session = SessionScope.of(context);
    setState(() => _loading = true);
    try {
      final page = await session.searchFoods(_query, page: _page + 1);
      if (!mounted || generation != _generation) return;
      setState(() {
        _items.addAll(page.items);
        _page = page.page;
        _total = page.totalItems;
        _hasMore = page.hasMore;
      });
    } on ApiFailure catch (failure) {
      if (!mounted || generation != _generation) return;
      setState(() => _error = failure);
    } finally {
      if (mounted && generation == _generation) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _openDish(FoodBrief dish) async {
    await FoodDetailScreen.open(context, dish);
    // The detail screen is where a dish gets bookmarked or blocked, and the
    // row has to show that on the way back.
    if (mounted) _search();
  }

  // ── Filters ─────────────────────────────────────────────────────

  Future<void> _pickMeal() async {
    final picked = await _ChoiceSheet.show<MealType>(
      context,
      title: 'Hợp với bữa',
      options: [for (final m in MealType.values) (m, m.label)],
      selected: _query.meal,
    );
    if (picked == null) return;
    _setQuery(
      picked.clear
          ? _query.copyWith(clearMeal: true)
          : _query.copyWith(meal: picked.value),
    );
  }

  Future<void> _pickCategory() async {
    final session = SessionScope.of(context);
    final List<FoodCategory> groups;
    try {
      groups = await session.foodCategories();
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(failure.message)));
      return;
    }
    if (!mounted) return;
    final picked = await _ChoiceSheet.show<FoodCategory>(
      context,
      title: 'Nhóm món',
      options: [for (final g in groups) (g, g.name)],
      selected: groups.where((g) => g.id == _query.categoryId).firstOrNull,
    );
    if (picked == null) return;
    _setQuery(
      picked.clear
          ? _query.copyWith(clearCategory: true)
          : _query.copyWith(
              categoryId: picked.value!.id,
              categoryName: picked.value!.name,
            ),
    );
  }

  Future<void> _pickRole() async {
    final picked = await _ChoiceSheet.show<DishRole>(
      context,
      title: 'Vai trò trong bữa',
      options: [for (final r in DishRole.values) (r, r.label)],
      selected: _query.role,
    );
    if (picked == null) return;
    _setQuery(
      picked.clear
          ? _query.copyWith(clearRole: true)
          : _query.copyWith(role: picked.value),
    );
  }

  static const _ceilings = [150.0, 250.0, 350.0, 450.0, 600.0];

  Future<void> _pickCeiling() async {
    final picked = await _ChoiceSheet.show<double>(
      context,
      title: 'Năng lượng mỗi suất',
      options: [for (final c in _ceilings) (c, 'Dưới ${formatNumber(c)} kcal')],
      selected: _query.maxKcal,
    );
    if (picked == null) return;
    _setQuery(
      picked.clear
          ? _query.copyWith(clearMaxKcal: true)
          : _query.copyWith(maxKcal: picked.value),
    );
  }

  Future<void> _pickMark() async {
    final picked = await _ChoiceSheet.show<String>(
      context,
      title: 'Món bạn đã đánh dấu',
      options: const [
        (FoodMark.loved, 'Đã lưu'),
        (FoodMark.blocked, 'Không gợi ý nữa'),
      ],
      selected: _query.mark,
    );
    if (picked == null) return;
    _setQuery(
      picked.clear
          ? _query.copyWith(clearMark: true)
          : _query.copyWith(mark: picked.value),
    );
  }

  @override
  Widget build(BuildContext context) {
    final q = _query;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        title: const Text('Tìm món'),
      ),
      body: SafeArea(
        top: false,
        child: CustomScrollView(
          controller: _scroll,
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
                child: TextField(
                  controller: _text,
                  onChanged: _onTyped,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: 'Tên món, ví dụ "canh chua"',
                    prefixIcon: const Icon(Icons.search_rounded, size: 22),
                    suffixIcon: _text.text.isEmpty
                        ? null
                        : IconButton(
                            tooltip: 'Xóa chữ',
                            icon: const Icon(Icons.close_rounded, size: 20),
                            onPressed: () {
                              _text.clear();
                              _setQuery(q.copyWith(text: ''));
                            },
                          ),
                    filled: true,
                    fillColor: AppColors.surface,
                    contentPadding: const EdgeInsets.symmetric(vertical: 14),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: const BorderSide(color: AppColors.border),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: const BorderSide(color: AppColors.border),
                    ),
                  ),
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: SizedBox(
                height: 54,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 6),
                  children: [
                    if (q.activeFilters > 0) ...[
                      _FilterPill(
                        label: 'Bỏ lọc (${q.activeFilters})',
                        icon: Icons.close_rounded,
                        onTap: () => _setQuery(q.cleared()),
                      ),
                      const SizedBox(width: 8),
                    ],
                    _FilterPill(
                      label: q.meal?.label ?? 'Bữa',
                      active: q.meal != null,
                      onTap: _pickMeal,
                    ),
                    const SizedBox(width: 8),
                    _FilterPill(
                      label: q.categoryName ?? 'Nhóm món',
                      active: q.categoryId != null,
                      onTap: _pickCategory,
                    ),
                    const SizedBox(width: 8),
                    _FilterPill(
                      label: q.role?.label ?? 'Vai trò',
                      active: q.role != null,
                      onTap: _pickRole,
                    ),
                    const SizedBox(width: 8),
                    _FilterPill(
                      label: q.maxKcal == null
                          ? 'Năng lượng'
                          : 'Dưới ${formatNumber(q.maxKcal!)} kcal',
                      active: q.maxKcal != null,
                      onTap: _pickCeiling,
                    ),
                    const SizedBox(width: 8),
                    _FilterPill(
                      label: switch (q.mark) {
                        FoodMark.loved => 'Đã lưu',
                        FoodMark.blocked => 'Không gợi ý nữa',
                        _ => 'Đánh dấu',
                      },
                      active: q.mark != null,
                      onTap: _pickMark,
                    ),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 6, 20, 0),
                child: _SafetySwitch(
                  value: q.safeOnly,
                  onChanged: (v) => _setQuery(q.copyWith(safeOnly: v)),
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
                child: Text(
                  _loading && _items.isEmpty
                      ? 'Đang tìm…'
                      : '${formatNumber(_total.toDouble())} món',
                  style: const TextStyle(
                    fontSize: 13,
                    color: AppColors.textSecondary,
                    fontVariations: [FontVariation('wght', 600)],
                  ),
                ),
              ),
            ),
            if (_error != null && _items.isEmpty)
              SliverToBoxAdapter(
                child: _Message(
                  icon: Icons.cloud_off_rounded,
                  title: 'Chưa tải được danh sách món',
                  body: _error!.message,
                  action: _error!.isRetryable ? 'Thử lại' : null,
                  onAction: _search,
                ),
              )
            else if (!_loading && _items.isEmpty)
              SliverToBoxAdapter(
                child: _Message(
                  icon: Icons.search_off_rounded,
                  title: 'Không có món nào khớp',
                  body: q.activeFilters > 0
                      ? 'Thử bỏ bớt bộ lọc, hoặc tìm bằng một phần tên món.'
                      : 'Thử tìm bằng một phần tên món.',
                  action: q.activeFilters > 0 ? 'Bỏ lọc' : null,
                  onAction: () => _setQuery(q.cleared()),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
                sliver: SliverList.builder(
                  itemCount: _items.length,
                  itemBuilder: (context, i) => _DishRow(
                    dish: _items[i],
                    onTap: () => _openDish(_items[i]),
                  ),
                ),
              ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Center(
                  child: _loading && _items.isNotEmpty
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.4),
                        )
                      : _loading
                      ? const CircularProgressIndicator()
                      : const SizedBox.shrink(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterPill extends StatelessWidget {
  const _FilterPill({
    required this.label,
    required this.onTap,
    this.active = false,
    this.icon,
  });

  final String label;
  final VoidCallback onTap;
  final bool active;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final fg = active ? AppColors.textOnDark : AppColors.textPrimary;
    return Material(
      color: active ? AppColors.ink : AppColors.surface,
      shape: StadiumBorder(
        side: BorderSide(color: active ? AppColors.ink : AppColors.border),
      ),
      child: InkWell(
        onTap: onTap,
        customBorder: const StadiumBorder(),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 16, color: fg),
                const SizedBox(width: 4),
              ],
              Text(
                label,
                style: TextStyle(
                  fontSize: 13.5,
                  color: fg,
                  fontVariations: const [FontVariation('wght', 600)],
                ),
              ),
              if (icon == null) ...[
                const SizedBox(width: 2),
                Icon(Icons.keyboard_arrow_down_rounded, size: 18, color: fg),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SafetySwitch extends StatelessWidget {
  const _SafetySwitch({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.shield_outlined,
            size: 22,
            color: AppColors.accentInk,
          ),
          const SizedBox(width: 10),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Chỉ món bạn ăn được',
                  style: TextStyle(
                    fontSize: 14.5,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Ẩn món không hợp với bệnh lý và dị ứng đã khai',
                  style: TextStyle(
                    fontSize: 12.5,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Switch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _DishRow extends StatelessWidget {
  const _DishRow({required this.dish, required this.onTap});

  final FoodBrief dish;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final details = [
      '${formatNumber(dish.kcal)} kcal',
      if (dish.category.isNotEmpty) dish.category,
      if (dish.dishRole.isNotEmpty) DishRole.labelOf(dish.dishRole),
    ].join(' · ');

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: const BorderSide(color: AppColors.border),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: dish.gradient,
                    ),
                  ),
                  child: Text(dish.emoji, style: const TextStyle(fontSize: 24)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        dish.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 15,
                          color: AppColors.textPrimary,
                          fontVariations: [FontVariation('wght', 700)],
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        details,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 12.5,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      if (!dish.isSafeForUser) ...[
                        const SizedBox(height: 6),
                        const _Badge(
                          label: 'Không hợp với bạn',
                          color: AppColors.dislike,
                        ),
                      ],
                    ],
                  ),
                ),
                if (dish.isLoved)
                  const Padding(
                    padding: EdgeInsets.only(left: 6),
                    child: Icon(
                      Icons.bookmark_rounded,
                      size: 20,
                      color: AppColors.accentInk,
                      semanticLabel: 'Đã lưu',
                    ),
                  ),
                if (dish.isBlocked)
                  const Padding(
                    padding: EdgeInsets.only(left: 6),
                    child: Icon(
                      Icons.block_rounded,
                      size: 20,
                      color: AppColors.textTertiary,
                      semanticLabel: 'Không gợi ý nữa',
                    ),
                  ),
                const SizedBox(width: 4),
                const Icon(
                  Icons.chevron_right_rounded,
                  color: AppColors.textTertiary,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11.5,
          color: color,
          fontVariations: const [FontVariation('wght', 700)],
        ),
      ),
    );
  }
}

class _Message extends StatelessWidget {
  const _Message({
    required this.icon,
    required this.title,
    required this.body,
    required this.onAction,
    this.action,
  });

  final IconData icon;
  final String title;
  final String body;
  final String? action;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 40, 32, 0),
      child: Column(
        children: [
          Icon(icon, size: 44, color: AppColors.textTertiary),
          const SizedBox(height: 14),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 6),
          Text(
            body,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (action != null) ...[
            const SizedBox(height: 14),
            TextButton(onPressed: onAction, child: Text(action!)),
          ],
        ],
      ),
    );
  }
}

/// What a filter sheet answered: a value, or the filter removed.
typedef _Picked<T> = ({T? value, bool clear});

/// One filter's choices, one of which can be picked.
class _ChoiceSheet<T> extends StatelessWidget {
  const _ChoiceSheet({
    required this.title,
    required this.options,
    required this.selected,
  });

  final String title;
  final List<(T, String)> options;
  final T? selected;

  /// `null` when dismissed, which changes nothing.
  static Future<_Picked<T>?> show<T>(
    BuildContext context, {
    required String title,
    required List<(T, String)> options,
    required T? selected,
  }) => showModalBottomSheet<_Picked<T>>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) =>
        _ChoiceSheet<T>(title: title, options: options, selected: selected),
  );

  @override
  Widget build(BuildContext context) {
    // Material, not a coloured Container: the list tiles inside paint their
    // highlight and ripple on the nearest Material, which a coloured box
    // would cover.
    return Material(
      color: AppColors.surface,
      borderRadius: const BorderRadius.vertical(top: Radius.circular(26)),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.75,
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 10),
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
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 12, 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        title,
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                    ),
                    if (selected != null)
                      TextButton(
                        onPressed: () =>
                            Navigator.of(context)
                                .pop<_Picked<T>>((value: null, clear: true)),
                        child: const Text('Bỏ lọc'),
                      ),
                  ],
                ),
              ),
              Flexible(
                child: ListView(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                  children: [
                    for (final (value, label) in options)
                      ListTile(
                        title: Text(
                          label,
                          style: const TextStyle(
                            fontSize: 15.5,
                            fontVariations: [FontVariation('wght', 600)],
                          ),
                        ),
                        trailing: value == selected
                            ? const Icon(
                                Icons.check_rounded,
                                color: AppColors.textPrimary,
                              )
                            : null,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                        selected: value == selected,
                        selectedTileColor: AppColors.surfaceMuted,
                        onTap: () =>
                            Navigator.of(context)
                                .pop<_Picked<T>>((value: value, clear: false)),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
