import 'package:flutter/material.dart';

import '../../../data/models/health_profile.dart';
import '../widgets/onboarding_scaffold.dart';
import '../widgets/option_card.dart';

/// Hai bước khai báo ràng buộc sức khỏe dùng chung một màn hình.
enum ConditionKind { disease, allergy }

/// Một mục trong danh sách, gắn với mã trong bảng `conditions`.
typedef _Item = ({String code, String label, String emoji});

/// Bước 8 và 9 — bệnh lý, rồi dị ứng và chế độ ăn.
///
/// Đây là dữ liệu **quan trọng nhất về mặt an toàn** trong cả luồng: nó nuôi
/// Bộ lọc F1, tầng loại bỏ món trước khi mô hình học máy được chấm điểm. Món
/// bị loại ở đây thì dù người dùng có thích tới đâu cũng không bao giờ được
/// gợi ý.
///
/// Vì cho chọn nhiều mục, danh sách có thêm một lựa chọn "Không có mục nào ở
/// trên". Chọn nó sẽ xoá mọi lựa chọn khác, và ngược lại — tránh trạng thái
/// mâu thuẫn kiểu vừa khai bệnh tiểu đường vừa khai không có bệnh gì.
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

  /// Mã giả cho lựa chọn "không có gì". Không tồn tại trong bảng `conditions`
  /// và bị loại trước khi gửi lên máy chủ.
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
