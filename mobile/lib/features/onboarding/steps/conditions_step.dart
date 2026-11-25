import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/api/failure.dart';
import '../../../data/models/candidate_count.dart';
import '../../../data/models/food.dart';
import '../../../data/models/health_profile.dart';
import '../../../data/session.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// The two health-constraint steps share one screen.
enum ConditionKind { disease, allergy }

/// One item of the list, tied to a code in the `conditions` table.
typedef _Item = ({String code, String label, String emoji});

/// Steps 8 and 9 — the conditions, then the allergies and diets.
///
/// This is the **safety-critical** data of the whole flow: it feeds the F1
/// filter, the layer that drops dishes before the machine learning model
/// scores anything. A dish dropped here is never recommended, however much
/// the user likes it.
///
/// Because several items can be selected, the list carries an extra "none of
/// the above" option. Choosing it clears every other selection, and vice
/// versa — which rules out the contradictory state of having declared both
/// diabetes and no condition at all.
///
/// Note on language: each item's `code` is the value in the `conditions`
/// table and its `label` is text shown on screen, so both stay in
/// Vietnamese.
class ConditionsStep extends StatelessWidget {
  const ConditionsStep({
    super.key,
    required this.profile,
    required this.progress,
    required this.onBack,
    required this.onNext,
    required this.onChanged,
    required this.kind,
  });

  final HealthProfile profile;
  final double progress;
  final VoidCallback? onBack;
  final VoidCallback onNext;
  final VoidCallback onChanged;
  final ConditionKind kind;

  static const _diseases = <_Item>[
    (code: 'diabetes', label: 'Đái tháo đường', emoji: '🩸'),
    (code: 'hypertension', label: 'Tăng huyết áp', emoji: '🫀'),
    (code: 'dyslipidemia', label: 'Rối loạn mỡ máu', emoji: '🧈'),
    (code: 'kidney_disease', label: 'Bệnh thận', emoji: '🫘'),
    (code: 'gout', label: 'Gút', emoji: '🦴'),
  ];

  static const _allergies = <_Item>[
    (code: 'allergy_seafood', label: 'Dị ứng hải sản', emoji: '🦐'),
    (code: 'allergy_peanut', label: 'Dị ứng đậu phộng', emoji: '🥜'),
    (code: 'allergy_egg', label: 'Dị ứng trứng', emoji: '🥚'),
    // `conditions` has had this row and `condition_rules` a working
    // `exclude_tag` for it over 20 dishes, while this list did not offer it —
    // so a user allergic to soy could not say so, and F1 excluded nothing for
    // them.
    (code: 'allergy_soy', label: 'Dị ứng đậu nành', emoji: '🫘'),
    (code: 'lactose_intolerance', label: 'Không dung nạp lactose', emoji: '🥛'),
    (code: 'gluten_intolerance', label: 'Không dung nạp gluten', emoji: '🌾'),
    (code: 'vegetarian', label: 'Ăn chay', emoji: '🥬'),
    (code: 'vegan', label: 'Ăn thuần chay', emoji: '🌱'),
  ];

  /// The pseudo-code for the "nothing" option. Defined on the model, because
  /// the layer that sends the declarations is the one that strips it.
  static const _noneCode = HealthProfile.noneCode;

  List<_Item> get _items =>
      kind == ConditionKind.disease ? _diseases : _allergies;

  Set<String> get _selection =>
      kind == ConditionKind.disease ? profile.conditions : profile.allergies;

  void _toggle(String code) {
    final sel = _selection;
    if (code == _noneCode) {
      sel
        ..clear()
        ..add(_noneCode);
    } else {
      sel.remove(_noneCode);
      if (sel.contains(code)) {
        sel.remove(code);
        // The severity goes with it: a condition no longer declared must not
        // leave a severity behind to be sent for something else.
        profile.severities.remove(code);
      } else {
        sel.add(code);
      }
    }
    onChanged();
  }

  void _setSeverity(String code, String severity) {
    profile.severities[code] = severity;
    onChanged();
  }

  /// Everything declared across **both** condition screens.
  ///
  /// Not just this screen's own kind: the F1 filter removes dishes by every
  /// declaration a user has made, so a count showing only the effect of the
  /// question on screen would go **up** when the user moves from allergies
  /// to diseases, as the allergies dropped out of the sum.
  Set<String> _declaredForCount() => {
    ...profile.conditions,
    ...profile.allergies,
  }..remove(_noneCode);

  /// Only diseases are asked.
  ///
  /// Of the fifteen rows in `condition_rules`, two sit above `mild`: gout
  /// stops allowing high-purine dishes from `moderate`, and hypertension
  /// tightens its sodium limit at `severe`. Every allergy, intolerance and
  /// diet rule applies from `mild` upwards, so a severity question there
  /// would change nothing at all — and a question whose answer changes
  /// nothing teaches the user that the answers do not matter.
  bool get _asksSeverity => kind == ConditionKind.disease;

  @override
  Widget build(BuildContext context) {
    final sel = _selection;

    return OnboardingScaffold(
      progress: progress,
      onBack: onBack,
      scrollable: true,
      title: kind == ConditionKind.disease
          ? 'Bạn có bệnh lý nào không?'
          : 'Bạn kiêng hoặc dị ứng gì không?',
      subtitle: kind == ConditionKind.disease
          ? 'Chọn tất cả những mục đúng với bạn. Món vi phạm sẽ bị loại khỏi thực đơn'
          : 'Món chứa thành phần bạn chọn sẽ không bao giờ được gợi ý',
      onAction: sel.isEmpty ? null : onNext,
      child: OptionList(
        children: [
          // The catalogue narrowing as the answers come in — §7.4.3. The
          // selection is passed as a sorted list so the child can tell a
          // real change from a rebuild: the parent rebuilds on every tick,
          // including the ones that did not alter the set.
          _RemainingDishes(
            declared: _declaredForCount(),
            severities: Map.of(profile.severities),
          ),
          const SizedBox(height: 4),
          for (final item in _items) ...[
            OptionCard(
              label: item.label,
              leading: item.emoji,
              selected: sel.contains(item.code),
              onTap: () => _toggle(item.code),
            ),
            if (_asksSeverity && sel.contains(item.code))
              _SeverityRow(
                selected: profile.severityOf(item.code),
                onPick: (value) => _setSeverity(item.code, value),
              ),
          ],
          OptionCard(
            label: kind == ConditionKind.disease
                ? 'Tôi không có bệnh lý nào'
                : 'Tôi không kiêng gì cả',
            leading: '✅',
            selected: sel.contains(_noneCode),
            onTap: () => _toggle(_noneCode),
          ),
        ],
      ),
    );
  }
}

/// How bad a declared disease is — `user_conditions.severity`.
///
/// Three choices, shown under the disease the moment it is selected rather
/// than on a screen of their own: the answer only makes sense next to the
/// question it qualifies, and a separate step would ask about five diseases
/// the user may not have.
///
/// The labels are the user's words for the three ENUM values. `moderate` is
/// preselected because that is the column's own `DEFAULT`, so leaving the row
/// alone stores exactly what the database would have stored by itself.
class _SeverityRow extends StatelessWidget {
  const _SeverityRow({required this.selected, required this.onPick});

  final String selected;
  final void Function(String severity) onPick;

  static const _options = <({String code, String label})>[
    (code: 'mild', label: 'Nhẹ'),
    (code: 'moderate', label: 'Vừa'),
    (code: 'severe', label: 'Nặng'),
  ];

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.only(left: 16, right: 16, bottom: 10),
      child: Row(
        children: [
          Text(
            'Mức độ',
            style: text.bodySmall?.copyWith(color: AppColors.textSecondary),
          ),
          const SizedBox(width: 12),
          for (final option in _options)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(option.label),
                selected: selected == option.code,
                onSelected: (_) => onPick(option.code),
                showCheckmark: false,
                labelStyle: text.bodySmall?.copyWith(
                  color: selected == option.code
                      ? AppColors.textOnDark
                      : AppColors.textPrimary,
                ),
                selectedColor: AppColors.primary,
                backgroundColor: AppColors.surfaceMuted,
                side: const BorderSide(color: AppColors.border),
              ),
            ),
        ],
      ),
    );
  }
}

/// The live count of what is left to eat, under the question.
///
/// Stateful and debounced: the parent rebuilds on every tick, and three
/// boxes ticked in a second are one question, not three. Without the delay
/// each tap would be a round trip and the number would flicker through
/// answers to selections the user had already moved past.
///
/// It never blocks the flow. A failure leaves the line out rather than
/// stopping the user: the count is reassurance, and the declarations
/// themselves are saved by §7.2.5 later, which has its own error path.
class _RemainingDishes extends StatefulWidget {
  const _RemainingDishes({required this.declared, required this.severities});

  final Set<String> declared;
  final Map<String, String> severities;

  @override
  State<_RemainingDishes> createState() => _RemainingDishesState();
}

class _RemainingDishesState extends State<_RemainingDishes> {
  static const _debounce = Duration(milliseconds: 350);

  Timer? _timer;
  CandidateCount? _count;
  bool _started = false;

  /// Guards against a slow answer landing after a faster, later one. Without
  /// it, two requests in flight can finish out of order and the screen keeps
  /// the older number.
  int _request = 0;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    _fetch();
  }

  @override
  void didUpdateWidget(_RemainingDishes old) {
    super.didUpdateWidget(old);
    if (!setEquals(old.declared, widget.declared) ||
        !mapEquals(old.severities, widget.severities)) {
      _timer?.cancel();
      _timer = Timer(_debounce, _fetch);
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _fetch() async {
    final session = SessionScope.of(context);
    final mine = ++_request;
    try {
      final count = await session.countCandidates(
        codes: widget.declared,
        severities: widget.severities,
      );
      if (!mounted || mine != _request) return;
      setState(() => _count = count);
    } on ApiFailure {
      if (!mounted || mine != _request) return;
      setState(() => _count = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final count = _count;
    if (count == null) return const SizedBox.shrink();

    // The empty required roles come first: the total can look healthy while
    // no day can be assembled at all, and that is the more serious fact.
    final blocked = count.emptyRequiredRoles
        .map(DishRole.labelOf)
        .join(', ');

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            count.removedFoods == 0
                ? 'Còn đủ ${count.totalFoods} món trong thư viện'
                : 'Còn ${count.remainingFoods}/${count.totalFoods} món '
                      '— đã loại ${count.removedFoods} món',
            style: TextStyle(
              fontSize: 13,
              color: count.canBuildAPlan
                  ? AppColors.textSecondary
                  : AppColors.danger,
              fontVariations: const [FontVariation('wght', 600)],
            ),
          ),
          if (blocked.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                'Không còn món nào thuộc nhóm $blocked, nên chưa dựng được '
                'thực đơn. Hãy xem lại các mục đã chọn.',
                style: const TextStyle(
                  fontSize: 12.5,
                  height: 1.4,
                  color: AppColors.danger,
                ),
              ),
            ),
          // The server's own sentences, when it has one. Shown as they
          // arrive: they explain cases the app cannot work out for itself,
          // such as a condition whose tag is on no dish yet.
          for (final note in count.notes)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                note,
                style: const TextStyle(
                  fontSize: 12.5,
                  height: 1.4,
                  color: AppColors.textTertiary,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
