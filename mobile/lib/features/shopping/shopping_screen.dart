import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_motion.dart';
import '../../core/widgets/app_card.dart';
import '../../data/models/ingredient.dart';
import '../../data/session.dart';
import '../../data/shopping/shopping_list.dart';

/// Shopping list: every ingredient the coming days need, added up across
/// dishes and grouped by market section.
///
/// Built from the plan rather than typed by hand, so it follows the plan —
/// swap or skip a dish and its ingredients leave the list.
class ShoppingScreen extends StatefulWidget {
  const ShoppingScreen({super.key});

  @override
  State<ShoppingScreen> createState() => _ShoppingScreenState();
}

class _ShoppingScreenState extends State<ShoppingScreen> {
  static const _ranges = [
    (days: 1, label: 'Hôm nay'),
    (days: 3, label: '3 ngày'),
    (days: 7, label: '7 ngày'),
  ];

  int _days = 3;
  final _extra = TextEditingController();

  @override
  void dispose() {
    _extra.dispose();
    super.dispose();
  }

  void _addExtra(AppSession session) {
    session.addShoppingExtra(_extra.text);
    _extra.clear();
  }

  Future<void> _copy(List<ShoppingLine> lines, AppSession session) async {
    final buffer = StringBuffer('Danh sách đi chợ — $_days ngày\n');
    Aisle? aisle;
    for (final line in lines) {
      if (line.aisle != aisle) {
        aisle = line.aisle;
        buffer.writeln('\n${aisle.label}');
      }
      buffer.writeln('- ${line.name}: ${formatGrams(line.grams)}');
    }
    if (session.shoppingExtras.isNotEmpty) {
      buffer.writeln('\nKhác');
      for (final e in session.shoppingExtras) {
        buffer.writeln('- $e');
      }
    }

    await Clipboard.setData(ClipboardData(text: buffer.toString()));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Đã chép danh sách'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final plans = session.plansForNext(_days);
    final lines = buildShoppingList(plans);
    final ticked = session.shoppingTicked;

    final total = lines.length + session.shoppingExtras.length;
    final done =
        lines.where((l) => ticked.contains(l.name)).length +
        session.shoppingExtras.where(ticked.contains).length;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Đi chợ',
                    style: Theme.of(context).textTheme.headlineMedium,
                  ),
                ),
                if (lines.isNotEmpty)
                  IconButton(
                    tooltip: 'Chép danh sách',
                    onPressed: () => _copy(lines, session),
                    icon: const Icon(Icons.copy_rounded),
                    color: AppColors.textPrimary,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Cộng từ những món còn chờ ăn trong thực đơn.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            _RangePicker(
              ranges: _ranges,
              selected: _days,
              onChanged: (d) => setState(() => _days = d),
            ),
            const SizedBox(height: 14),
            if (plans.isEmpty)
              const _Empty(
                icon: Icons.info_outline_rounded,
                title: 'Chưa có thực đơn',
                body:
                    'Hoàn tất hồ sơ sức khỏe để có thực đơn, danh sách đi chợ '
                    'sẽ tự lập từ đó.',
              )
            else ...[
              _ProgressCard(
                done: done,
                total: total,
                onClear: done == 0 ? null : session.clearShoppingTicks,
              ),
              if (lines.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 14),
                  child: _Empty(
                    icon: Icons.check_circle_outline_rounded,
                    title: 'Không còn gì phải mua',
                    body: 'Mọi suất trong khoảng này đã ăn hoặc đã bỏ qua.',
                  ),
                ),
              for (final aisle in Aisle.values)
                if (lines.any((l) => l.aisle == aisle))
                  Padding(
                    padding: const EdgeInsets.only(top: 14),
                    child: AppCard(
                      title: '${aisle.emoji}  ${aisle.label}',
                      padding: const EdgeInsets.fromLTRB(20, 18, 14, 10),
                      child: Column(
                        children: [
                          for (final line in lines.where(
                            (l) => l.aisle == aisle,
                          ))
                            _LineRow(
                              name: line.name,
                              hint: line.dishes.join(', '),
                              amount: formatGrams(line.grams),
                              ticked: ticked.contains(line.name),
                              onTap: () =>
                                  session.toggleShoppingTick(line.name),
                            ),
                        ],
                      ),
                    ),
                  ),
              const SizedBox(height: 14),
              AppCard(
                title: 'Thứ khác cần mua',
                padding: const EdgeInsets.fromLTRB(20, 18, 14, 14),
                child: Column(
                  children: [
                    for (final e in session.shoppingExtras)
                      _LineRow(
                        name: e,
                        ticked: ticked.contains(e),
                        onTap: () => session.toggleShoppingTick(e),
                        onRemove: () => session.removeShoppingExtra(e),
                      ),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _extra,
                            textCapitalization: TextCapitalization.sentences,
                            onSubmitted: (_) => _addExtra(session),
                            decoration: const InputDecoration(
                              hintText: 'Ví dụ: nước rửa chén',
                              hintStyle: TextStyle(
                                color: AppColors.textTertiary,
                              ),
                              border: InputBorder.none,
                              isDense: true,
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Thêm vào danh sách',
                          onPressed: () => _addExtra(session),
                          icon: const Icon(Icons.add_circle_rounded),
                          color: AppColors.ink,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                'Khối lượng là ước lượng cho một người, chưa trừ phần bạn còn '
                'sẵn trong bếp.',
                style: TextStyle(
                  fontSize: 12.5,
                  height: 1.45,
                  color: AppColors.textTertiary,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RangePicker extends StatelessWidget {
  const _RangePicker({
    required this.ranges,
    required this.selected,
    required this.onChanged,
  });

  final List<({int days, String label})> ranges;
  final int selected;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          for (final r in ranges)
            Expanded(
              child: GestureDetector(
                onTap: () => onChanged(r.days),
                behavior: HitTestBehavior.opaque,
                child: AnimatedContainer(
                  duration: AppMotion.quick,
                  curve: AppMotion.standard,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  decoration: BoxDecoration(
                    color: r.days == selected
                        ? AppColors.surface
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    r.label,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 14,
                      color: r.days == selected
                          ? AppColors.textPrimary
                          : AppColors.textSecondary,
                      fontVariations: [
                        FontVariation('wght', r.days == selected ? 700 : 500),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  const _ProgressCard({
    required this.done,
    required this.total,
    required this.onClear,
  });

  final int done;
  final int total;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final complete = total > 0 && done == total;

    return AppCard(
      padding: const EdgeInsets.fromLTRB(20, 16, 12, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  complete
                      ? 'Đủ đồ rồi, về nấu thôi'
                      : '$done / $total thứ đã vào giỏ',
                  style: const TextStyle(
                    fontSize: 16,
                    color: AppColors.textPrimary,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
              ),
              TextButton(onPressed: onClear, child: const Text('Bỏ đánh dấu')),
            ],
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                value: total == 0 ? 0 : done / total,
                minHeight: 7,
                backgroundColor: AppColors.surfaceMuted,
                valueColor: AlwaysStoppedAnimation(
                  complete ? AppColors.like : AppColors.accentInk,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LineRow extends StatelessWidget {
  const _LineRow({
    required this.name,
    required this.ticked,
    required this.onTap,
    this.hint,
    this.amount,
    this.onRemove,
  });

  final String name;
  final String? hint;
  final String? amount;
  final bool ticked;
  final VoidCallback onTap;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 9),
        child: Row(
          children: [
            AnimatedContainer(
              duration: AppMotion.instant,
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: ticked ? AppColors.ink : Colors.transparent,
                border: Border.all(
                  color: ticked ? AppColors.ink : AppColors.textTertiary,
                  width: 1.5,
                ),
              ),
              child: ticked
                  ? const Icon(
                      Icons.check_rounded,
                      size: 16,
                      color: AppColors.textOnDark,
                    )
                  : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: TextStyle(
                      fontSize: 15,
                      color: ticked
                          ? AppColors.textTertiary
                          : AppColors.textPrimary,
                      decoration: ticked ? TextDecoration.lineThrough : null,
                      decorationColor: AppColors.textTertiary,
                      fontVariations: const [FontVariation('wght', 600)],
                    ),
                  ),
                  if (hint != null)
                    Text(
                      hint!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textTertiary,
                      ),
                    ),
                ],
              ),
            ),
            if (amount != null)
              Padding(
                padding: const EdgeInsets.only(left: 10, right: 6),
                child: Text(
                  amount!,
                  style: TextStyle(
                    fontSize: 14,
                    color: ticked
                        ? AppColors.textTertiary
                        : AppColors.textSecondary,
                    fontVariations: const [FontVariation('wght', 600)],
                  ),
                ),
              ),
            if (onRemove != null)
              IconButton(
                tooltip: 'Xóa khỏi danh sách',
                onPressed: onRemove,
                icon: const Icon(Icons.close_rounded, size: 18),
                color: AppColors.textTertiary,
                visualDensity: VisualDensity.compact,
              ),
          ],
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  const _Empty({required this.icon, required this.title, required this.body});

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 22, color: AppColors.textTertiary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(body, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
