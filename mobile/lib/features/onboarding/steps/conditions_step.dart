import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../data/models/health_profile.dart';
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
