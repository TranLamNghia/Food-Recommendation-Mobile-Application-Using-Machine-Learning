import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../core/theme/app_colors.dart';
import '../../data/models/diary_entry.dart';
import '../../data/models/food.dart';
import '../../data/models/meal_plan.dart';
import '../../data/session.dart';

/// Nhật ký ăn uống — bảng `food_diary`.
///
/// Màn hình này ghi lại những gì người dùng **thật sự ăn**, không phải những
/// gì hệ thống gợi ý. Khoảng cách giữa hai thứ đó chính là tín hiệu quan
/// trọng nhất sau phiên khảo sát: món trong thực đơn bị bỏ qua, món ngoài
/// thực đơn được ăn thêm, và điểm đánh giá sau khi ăn.
class DiaryScreen extends StatelessWidget {
  const DiaryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    final today = DateTime.now();
    final entries = session.entriesOn(today);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        bottom: false,
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Nhật ký hôm nay',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Ghi lại món đã ăn và chấm điểm sau khi ăn. Đây là '
                      'nguồn tín hiệu đáng tin nhất để hệ thống học gu của bạn.',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                child: _ConsumedCard(session: session, entries: entries),
              ),
            ),
            if (entries.isEmpty)
              const SliverToBoxAdapter(child: _EmptyDiary())
            else
              for (final type in MealType.values)
                SliverToBoxAdapter(
                  child: _MealGroup(
                    session: session,
                    type: type,
                    entries: entries.where((e) => e.meal == type).toList(),
                  ),
                ),
            const SliverToBoxAdapter(child: SizedBox(height: 28)),
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
    final result = await showModalBottomSheet<({Food food, MealType meal})>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => _AddEntrySheet(candidates: session.candidates),
    );
    if (result == null) return;

    session.logMeal(food: result.food, meal: result.meal);
  }
}

/// Năng lượng đã nạp so với hạn mức.
///
/// Khác với thẻ trên màn hình thực đơn: ở đó là **dự kiến** theo thực đơn,
/// ở đây là **thực tế** theo nhật ký. Hai con số lệch nhau là chuyện bình
/// thường và chính nó cho biết thực đơn có được tuân thủ hay không.
class _ConsumedCard extends StatelessWidget {
  const _ConsumedCard({required this.session, required this.entries});

  final AppSession session;
  final List<DiaryEntry> entries;

  @override
  Widget build(BuildContext context) {
    final target = session.profile.energyTarget ?? 0;
    final consumed = entries.fold<double>(0, (sum, e) => sum + e.kcal);
    final remaining = target - consumed;
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
            // Ba ô thống kê chia đều bề ngang nên mỗi ô rất hẹp; con số bốn
            // chữ số kèm đơn vị phải co lại được thay vì tràn sang ô bên.
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
              onRate: (stars) => session.rate(entry, stars),
              onRemove: () => session.removeDiaryEntry(entry),
            ),
        ],
      ),
    );
  }
}

class _DiaryTile extends StatelessWidget {
  const _DiaryTile({
    required this.entry,
    required this.onRate,
    required this.onRemove,
  });

  final DiaryEntry entry;
  final ValueChanged<int> onRate;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          Row(
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
                      '${formatNumber(entry.kcal)} kcal · '
                      '${entry.ateAt.hour.toString().padLeft(2, '0')}:'
                      '${entry.ateAt.minute.toString().padLeft(2, '0')}',
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: onRemove,
                icon: const Icon(Icons.close_rounded, size: 18),
                color: AppColors.textTertiary,
                tooltip: 'Xóa khỏi nhật ký',
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          const Divider(height: 18),
          Row(
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
        ],
      ),
    );
  }
}

class _EmptyDiary extends StatelessWidget {
  const _EmptyDiary();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 56, 32, 0),
      child: Column(
        children: [
          const Icon(
            Icons.ramen_dining_rounded,
            size: 44,
            color: AppColors.textTertiary,
          ),
          const SizedBox(height: 16),
          Text(
            'Chưa ghi món nào hôm nay',
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'Bấm "Đã ăn" ở màn hình thực đơn, hoặc dùng nút bên dưới để ghi '
            'một món ngoài thực đơn.',
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

/// Bảng chọn món để ghi vào nhật ký.
///
/// Cho phép ghi **món ngoài thực đơn** là điều bắt buộc: người dùng ăn ngoài
/// hàng quán, ăn cùng gia đình, hoặc đơn giản là đổi ý. Nếu chỉ ghi được món
/// trong thực đơn thì nhật ký sẽ luôn khớp thực đơn một cách giả tạo, và tỷ
/// lệ tuân thủ mất hết ý nghĩa.
class _AddEntrySheet extends StatefulWidget {
  const _AddEntrySheet({required this.candidates});

  final List<Food> candidates;

  @override
  State<_AddEntrySheet> createState() => _AddEntrySheetState();
}

class _AddEntrySheetState extends State<_AddEntrySheet> {
  MealType _meal = MealType.lunch;
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final matches = widget.candidates
        .where(
          (f) => f.name.toLowerCase().contains(_query.trim().toLowerCase()),
        )
        .toList();

    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.82,
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
                    const SizedBox(height: 14),
                    Wrap(
                      spacing: 8,
                      children: [
                        for (final type in MealType.values)
                          ChoiceChip(
                            label: Text(type.label),
                            selected: _meal == type,
                            onSelected: (_) => setState(() => _meal = type),
                            showCheckmark: false,
                            selectedColor: AppColors.ink,
                            backgroundColor: AppColors.surfaceMuted,
                            side: BorderSide.none,
                            labelStyle: TextStyle(
                              fontSize: 13,
                              color: _meal == type
                                  ? AppColors.textOnDark
                                  : AppColors.textPrimary,
                              fontVariations: const [
                                FontVariation('wght', 600),
                              ],
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      onChanged: (v) => setState(() => _query = v),
                      decoration: InputDecoration(
                        hintText: 'Tìm món…',
                        prefixIcon: const Icon(Icons.search_rounded, size: 20),
                        filled: true,
                        fillColor: AppColors.surfaceMuted,
                        contentPadding: const EdgeInsets.symmetric(vertical: 4),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Flexible(
                child: ListView.builder(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                  itemCount: matches.length,
                  itemBuilder: (context, i) {
                    final food = matches[i];
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
                      subtitle: Text('${food.kcal} kcal · ${food.dishRole}'),
                      onTap: () =>
                          Navigator.of(context).pop((food: food, meal: _meal)),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
