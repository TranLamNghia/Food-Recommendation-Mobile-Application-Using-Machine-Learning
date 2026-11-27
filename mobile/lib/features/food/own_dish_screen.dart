import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../data/api/failure.dart';
import '../../data/api/food_api.dart';
import '../../data/models/food.dart';
import '../../data/models/food_brief.dart';
import '../../data/models/own_dish.dart';
import '../../data/session.dart';

/// Adds a dish the catalogue does not have — §7.5.3. Pops with the new
/// [FoodBrief], so the caller can log it straight away.
///
/// The dish is the user's alone: nobody else sees it, and it never shapes
/// the scale the recommender measures other dishes on.
///
/// **Blank is not zero.** Only the energy is required. Every other figure
/// left blank is sent as "unknown", and the screen says so beside the
/// fields, because a 0 typed for "I don't know" is what would let a dish
/// through a gout or blood-pressure limit it actually breaks.
class OwnDishScreen extends StatefulWidget {
  const OwnDishScreen({super.key, this.initialName = ''});

  /// What the user had typed into the search that found nothing.
  final String initialName;

  @override
  State<OwnDishScreen> createState() => _OwnDishScreenState();
}

class _OwnDishScreenState extends State<OwnDishScreen> {
  final _form = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.initialName.trim());
  final _serving = TextEditingController();
  final _kcal = TextEditingController();
  final _protein = TextEditingController();
  final _carbs = TextEditingController();
  final _fat = TextEditingController();
  final _fiber = TextEditingController();
  final _sugar = TextEditingController();
  final _sodium = TextEditingController();
  final _purine = TextEditingController();

  List<FoodCategory>? _categories;
  List<FoodTag> _tags = const [];
  String? _categoryId;
  DishRole _role = DishRole.main;
  int _spice = 0;
  final Set<int> _tagIds = {};

  bool _busy = false;
  String? _nameError;
  String? _loadError;
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _loadChoices();
  }

  Future<void> _loadChoices() async {
    final session = SessionScope.of(context);
    setState(() => _loadError = null);
    try {
      final categories = await session.foodCategories();
      final tags = await session.ownDishTags();
      if (!mounted) return;
      setState(() {
        _categories = categories;
        _tags = tags;
        _categoryId ??= categories.isEmpty ? null : categories.first.id;
      });
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _loadError = failure.message);
    }
  }

  @override
  void dispose() {
    for (final c in [
      _name,
      _serving,
      _kcal,
      _protein,
      _carbs,
      _fat,
      _fiber,
      _sugar,
      _sodium,
      _purine,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  static double? _number(String raw) =>
      double.tryParse(raw.trim().replaceAll(',', '.'));

  /// Blank is fine; anything typed must be a number, not negative.
  static String? _optional(String? raw) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    final v = _number(text);
    if (v == null) return 'Nhập một con số';
    if (v < 0) return 'Không nhỏ hơn 0';
    return null;
  }

  Future<void> _save() async {
    setState(() => _nameError = null);
    if (!_form.currentState!.validate()) return;
    final session = SessionScope.of(context);
    final navigator = Navigator.of(context);
    double? opt(TextEditingController c) =>
        c.text.trim().isEmpty ? null : _number(c.text);

    setState(() => _busy = true);
    try {
      final dish = await session.addOwnDish(
        OwnDishDraft(
          name: _name.text,
          categoryId: _categoryId!,
          dishRole: _role.code,
          servingSizeG: _number(_serving.text)!.round(),
          kcal: _number(_kcal.text)!,
          spiceLevel: _spice,
          proteinG: opt(_protein),
          carbsG: opt(_carbs),
          fatG: opt(_fat),
          fiberG: opt(_fiber),
          sugarG: opt(_sugar),
          sodiumMg: opt(_sodium),
          purineMg: opt(_purine),
          tagIds: _tagIds.toList(),
        ),
      );
      navigator.pop<FoodBrief>(dish);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        if (failure.code == ApiFailure.foodAlreadyExists) {
          _nameError = failure.message;
        }
      });
      if (_nameError != null) {
        _form.currentState!.validate();
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            failure.fields.isEmpty
                ? failure.message
                : failure.fields.map((f) => f.message).join('\n'),
          ),
          duration: const Duration(seconds: 4),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final categories = _categories;

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
      ),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
            children: [
              Text('Thêm món của tôi', style: text.headlineSmall),
              const SizedBox(height: 6),
              const Text(
                'Món này chỉ mình bạn thấy. Số liệu tính cho một suất.',
                style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 18),
              TextFormField(
                controller: _name,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(labelText: 'Tên món'),
                validator: (v) {
                  final name = (v ?? '').trim();
                  if (name.length < 2) return 'Tên món từ 2 ký tự';
                  if (name.length > 200) return 'Tên món tối đa 200 ký tự';
                  return _nameError;
                },
              ),
              const SizedBox(height: 14),
              if (_loadError != null)
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _loadError!,
                        style: const TextStyle(
                          fontSize: 13,
                          color: AppColors.danger,
                        ),
                      ),
                    ),
                    TextButton(
                      onPressed: _loadChoices,
                      child: const Text('Thử lại'),
                    ),
                  ],
                )
              else if (categories == null)
                const LinearProgressIndicator()
              else
                DropdownButtonFormField<String>(
                  initialValue: _categoryId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Nhóm món'),
                  items: [
                    for (final c in categories)
                      DropdownMenuItem(value: c.id, child: Text(c.name)),
                  ],
                  onChanged: (v) => setState(() => _categoryId = v),
                  validator: (v) => v == null ? 'Chọn nhóm món' : null,
                ),
              const SizedBox(height: 14),
              DropdownButtonFormField<DishRole>(
                initialValue: _role,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Vai trò trong bữa',
                ),
                items: [
                  for (final r in DishRole.values)
                    DropdownMenuItem(value: r, child: Text(r.label)),
                ],
                onChanged: (v) => setState(() => _role = v ?? _role),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _serving,
                      keyboardType: const TextInputType.numberWithOptions(),
                      decoration: const InputDecoration(
                        labelText: 'Một suất',
                        suffixText: 'g',
                      ),
                      validator: (v) {
                        final g = _number(v ?? '');
                        if (g == null) return 'Nhập số gam';
                        if (g < 1 || g > 5000) return 'Từ 1 đến 5000 g';
                        return null;
                      },
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextFormField(
                      controller: _kcal,
                      keyboardType: const TextInputType.numberWithOptions(
                        decimal: true,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Năng lượng',
                        suffixText: 'kcal',
                      ),
                      validator: (v) {
                        final kcal = _number(v ?? '');
                        if (kcal == null) return 'Bắt buộc';
                        if (kcal <= 0 || kcal > 5000) return 'Từ 1 đến 5000';
                        return null;
                      },
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Text(
                'Mức cay',
                style: TextStyle(
                  fontSize: 13.5,
                  color: AppColors.textSecondary,
                  fontVariations: [FontVariation('wght', 600)],
                ),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: [
                  for (final (level, label) in const [
                    (0, 'Không cay'),
                    (1, 'Hơi cay'),
                    (2, 'Cay'),
                    (3, 'Rất cay'),
                  ])
                    ChoiceChip(
                      label: Text(label),
                      selected: _spice == level,
                      onSelected: (_) => setState(() => _spice = level),
                    ),
                ],
              ),
              const SizedBox(height: 22),
              const Text(
                'Thành phần (nếu biết)',
                style: TextStyle(
                  fontSize: 13.5,
                  color: AppColors.textSecondary,
                  fontVariations: [FontVariation('wght', 600)],
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Không biết thì để trống, đừng ghi 0. Ô trống được hiểu là '
                '"chưa rõ", nên món sẽ không được tự động gợi ý cho bệnh lý '
                'cần đúng chất đó — bạn vẫn ghi nhật ký được.',
                style: TextStyle(
                  fontSize: 12,
                  height: 1.4,
                  color: AppColors.textTertiary,
                ),
              ),
              const SizedBox(height: 10),
              _pair(_protein, 'Đạm', 'g', _carbs, 'Bột đường', 'g'),
              _pair(_fat, 'Béo', 'g', _fiber, 'Chất xơ', 'g'),
              _pair(_sugar, 'Đường', 'g', _sodium, 'Natri', 'mg'),
              _pair(_purine, 'Purin', 'mg', null, '', ''),
              if (_tags.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Text(
                  'Món có chứa',
                  style: TextStyle(
                    fontSize: 13.5,
                    color: AppColors.textSecondary,
                    fontVariations: [FontVariation('wght', 600)],
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'Đánh dấu để bộ lọc dị ứng nhận ra món này như mọi món khác.',
                  style: TextStyle(fontSize: 12, color: AppColors.textTertiary),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final t in _tags)
                      FilterChip(
                        label: Text(t.nameVi),
                        selected: _tagIds.contains(t.id),
                        onSelected: (on) => setState(
                          () => on ? _tagIds.add(t.id) : _tagIds.remove(t.id),
                        ),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy || categories == null ? null : _save,
                child: Text(_busy ? 'Đang lưu…' : 'Lưu và ghi vào bữa'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _pair(
    TextEditingController a,
    String aLabel,
    String aUnit,
    TextEditingController? b,
    String bLabel,
    String bUnit,
  ) {
    Widget field(TextEditingController c, String label, String unit) =>
        TextFormField(
          controller: c,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: label,
            suffixText: unit,
            hintText: 'chưa rõ',
          ),
          validator: _optional,
        );

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Expanded(child: field(a, aLabel, aUnit)),
          const SizedBox(width: 12),
          Expanded(
            child: b == null
                ? const SizedBox.shrink()
                : field(b, bLabel, bUnit),
          ),
        ],
      ),
    );
  }
}
