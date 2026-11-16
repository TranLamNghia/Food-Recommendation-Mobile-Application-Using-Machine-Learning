import 'package:flutter/material.dart';

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
    (code: 'lactose_intolerance', label: 'Không dung nạp lactose', emoji: '🥛'),
    (code: 'gluten_intolerance', label: 'Không dung nạp gluten', emoji: '🌾'),
    (code: 'vegetarian', label: 'Ăn chay', emoji: '🥬'),
    (code: 'vegan', label: 'Ăn thuần chay', emoji: '🌱'),
  ];

  /// The pseudo-code for the "nothing" option. It does not exist in the
  /// `conditions` table and is stripped before anything is sent to the
  /// server.
  static const _noneCode = '__none__';

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
      sel.contains(code) ? sel.remove(code) : sel.add(code);
    }
    onChanged();
  }

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
          for (final item in _items)
            OptionCard(
              label: item.label,
              leading: item.emoji,
              selected: sel.contains(item.code),
              onTap: () => _toggle(item.code),
            ),
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
