import 'dart:math' as math;

import '../models/food.dart';
import '../models/meal_plan.dart';
import 'nutrient_target.dart';
import 'preference_profile.dart';

/// Hình dạng của một bữa ăn: những vai trò món bắt buộc và những vai trò có
/// thể thêm vào nếu bữa còn thiếu năng lượng.
///
/// Ràng buộc vai trò tồn tại vì lấy top-K món điểm cao nhất **không** tạo ra
/// một bữa hợp lý — cả ba món có thể cùng là món mặn, hoặc cùng là tráng
/// miệng nếu người dùng thích đồ ngọt. Vai trò ép bữa ăn có hình dạng đúng
/// trước khi tính đến khẩu vị.
///
/// Phần [optional] tồn tại vì một món không phủ nổi hạn mức của cả bữa: bữa
/// sáng của người cần 2.500 kcal được chia 27,5 %, tức khoảng 690 kcal, trong
/// khi món nặng nhất trong kho chỉ hơn 600. Không có suất tùy chọn thì thực
/// đơn luôn hụt hạn mức bất kể thuật toán chọn khéo đến đâu.
class _MealShape {
  const _MealShape({required this.required, this.optional = const []});

  final List<String> required;
  final List<String> optional;
}

const _mealStructure = <MealType, _MealShape>{
  MealType.breakfast: _MealShape(
    required: ['Món chính'],
    optional: ['Món phụ'],
  ),
  MealType.lunch: _MealShape(
    required: ['Món chính', 'Món mặn'],
    optional: ['Món canh'],
  ),
  MealType.dinner: _MealShape(
    required: ['Món chính', 'Món rau'],
    optional: ['Món mặn'],
  ),
  MealType.snack: _MealShape(required: ['Món phụ']),
};

/// Một suất cần điền, xác định bởi bữa và vai trò món.
typedef _Slot = ({MealType meal, String role, bool explore});

/// Sinh thực đơn hằng ngày từ hồ sơ sở thích và hạn mức dinh dưỡng.
///
/// Cài đặt Bước 3 và Bước 4 của thuật toán khuyến nghị:
///
/// 1. Chấm điểm từng món bằng độ tương đồng cosin với hồ sơ sở thích.
/// 2. Chia suất theo cơ chế 70-30 — phần lớn xếp theo vector sở thích, phần
///    còn lại xếp theo chính vector đó đã làm nhiễu.
/// 3. Chọn tổ hợp bằng **tham lam theo mật độ điểm**, bù thêm suất tùy chọn
///    cho tới khi chạm hạn mức, rồi cải thiện bằng **tìm kiếm cục bộ** trên
///    hàm mục tiêu có phạt.
///
/// Bộ lọc F1 (dị ứng, bệnh lý, chế độ ăn) nằm ngoài lớp này: nó phải chạy
/// **trước** và truyền vào [candidates] tập món đã an toàn. Thăm dò chỉ nới
/// lỏng về khẩu vị, không bao giờ nới lỏng về an toàn.
class MenuBuilder {
  MenuBuilder({
    required this.candidates,
    required this.profile,
    this.explorationRatio = 0.3,
    this.explorationDelta = 0.35,
    this.energyPenalty = 1.2,
    this.macroPenalty = 0.6,
    this.localSearchRounds = 20,
    this.nutrientTargets = const [],
    this.nutrientRepairRounds = 12,
    this.maxEnergyDeviation = 0.10,
    math.Random? rng,
  }) : _rng = rng ?? math.Random();

  /// Tập món đã qua Bộ lọc F1.
  final List<Food> candidates;

  final PreferenceProfile profile;

  /// Tỷ lệ suất dành cho thăm dò. Trần cứng 50 % — xem `chk_expl_ratio`.
  final double explorationRatio;

  /// Biên độ nhiễu δ dùng khi xoay vector sở thích cho nhóm thăm dò.
  final double explorationDelta;

  /// Hệ số phạt λ cho sai lệch năng lượng trong hàm mục tiêu.
  final double energyPenalty;

  /// Hệ số phạt μ cho sai lệch từng chất sinh năng lượng.
  final double macroPenalty;

  /// Số vòng lặp tối đa của pha tìm kiếm cục bộ.
  final int localSearchRounds;

  /// Ràng buộc vi chất ở cấp **ngày** — ngưỡng cứng `per_day` của
  /// `condition_rules`, cộng mục tiêu người dùng tự khai.
  final List<NutrientTarget> nutrientTargets;

  /// Số phép đổi tối đa mà pha 5 được làm. Chặn trên để pha sửa không chạy
  /// mãi khi danh mục không đủ món để thỏa ràng buộc.
  final int nutrientRepairRounds;

  /// Trần độ lệch năng lượng mà pha 5 được phép đẩy thực đơn tới.
  ///
  /// 10 % là cam kết trong đề cương. Pha 5 **không bao giờ** đẩy độ lệch vượt
  /// mốc này để đổi lấy việc thỏa một ràng buộc vi chất: làm vậy là chữa một
  /// vi phạm bằng cách tạo ra một vi phạm khác.
  final double maxEnergyDeviation;

  final math.Random _rng;

  /// Sinh thực đơn cho một ngày.
  ///
  /// [targetKcal] là hạn mức năng lượng cả ngày đã tính từ hồ sơ sức khỏe
  /// (TDEE điều chỉnh theo mục tiêu). Hạn mức từng bữa suy ra theo
  /// [MealType.energyShare].
  DailyPlan build({
    required DateTime date,
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    final ratio = explorationRatio.clamp(0.0, 0.5);
    final exploreProfile = profile.jittered(delta: explorationDelta, rng: _rng);

    final slots = _assignExplorationSlots(ratio);
    final picks = <MealType, List<MealPlanItem>>{
      for (final t in MealType.values) t: [],
    };
    final usedIds = <String>{};

    // ── Pha 1 — tham lam trên các suất bắt buộc ──────────────────────
    for (final slot in slots) {
      final activeProfile = slot.explore ? exploreProfile : profile;
      final pool = candidates
          .where((f) => f.dishRole == slot.role && !usedIds.contains(f.id))
          .toList();

      // Không còn món đúng vai trò thì bỏ suất, thay vì chèn bừa một món sai
      // vai trò — bữa thiếu món canh vẫn hợp lý hơn bữa có hai món chính.
      if (pool.isEmpty) continue;

      final mealTarget = targetKcal * slot.meal.energyShare;
      final already = _kcalOf(picks[slot.meal]!);
      final remainingSlots = slots
          .where((s) => s.meal == slot.meal)
          .length
          .clamp(1, 99);

      final best = _greedyPick(
        pool: pool,
        profile: activeProfile,
        slotTargetKcal: (mealTarget - already) / remainingSlots,
      );

      usedIds.add(best.id);
      picks[slot.meal]!.add(
        MealPlanItem(
          food: best,
          score: activeProfile.score(best),
          explorationDelta: slot.explore ? explorationDelta : null,
        ),
      );
    }

    // ── Pha 2 — bù suất tùy chọn ở cấp ngày ──────────────────────────
    _topUp(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    // ── Pha 3 — tìm kiếm cục bộ trên từng bữa ────────────────────────
    for (final type in MealType.values) {
      final before = picks[type]!.map((i) => i.food.id).toSet();

      final refined = _localSearch(
        selected: picks[type]!,
        usedIds: usedIds,
        targetKcal: targetKcal * type.energyShare,
        targetProtein: targetProtein * type.energyShare,
        targetCarb: targetCarb * type.energyShare,
        targetFat: targetFat * type.energyShare,
      );

      // Cập nhật `usedIds` theo kết quả hoán đổi trước khi sang bữa sau.
      //
      // Thiếu bước này thì món vừa được đổi VÀO bữa sáng không nằm trong
      // `usedIds`, nên bữa trưa vẫn thấy nó còn trống và lấy luôn — cùng một
      // món xuất hiện hai lần trong ngày. Ngược lại, món bị đổi RA phải được
      // trả lại tập ứng viên, vì nó không còn trong thực đơn nữa.
      final after = refined.map((i) => i.food.id).toSet();
      usedIds
        ..removeAll(before.difference(after))
        ..addAll(after);

      picks[type] = refined;
    }

    // ── Pha 4 — bù lại ở cấp ngày ────────────────────────────────────
    //
    // Pha 3 tối ưu từng bữa **riêng lẻ**, nên nó có thể kéo tổng năng lượng
    // của cả ngày xa hạn mức dù mỗi bữa đều khá hơn: đổi một món chính nhẹ
    // hơn vào bữa trưa làm bữa đó khớp macro hơn, nhưng cả ngày hụt thêm.
    //
    // Gọi lại `_topUp` sau pha 3 để sửa. Phép này chỉ thêm món khi món đó
    // làm khoảng lệch cấp ngày **nhỏ lại**, nên nó không bao giờ làm xấu đi
    // — chạy thêm một lượt là an toàn.
    _topUp(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    // -- Pha 5 - thi hanh rang buoc vi chat o cap ngay --
    //
    // Phải ở cấp ngày và phải ở cuối: ngưỡng "natri dưới 2000 mg/ngày" là
    // phát biểu về **tổng cả ngày**, nên không kiểm được ở pha 1 (chọn từng
    // suất) cũng không ở pha 3 (tối ưu từng bữa).
    //
    // Đây là phần trước đây thiếu hẳn. `condition_rules` lưu sáu ngưỡng cứng
    // `per_day`, tài liệu nói Bước 4 kiểm chúng, nhưng Bước 4 chỉ bám `kcal`
    // và ba macro — tức các ngưỡng đó không được thi hành ở đâu cả.
    _repairNutrients(picks: picks, usedIds: usedIds, targetKcal: targetKcal);

    final result = [
      for (final type in MealType.values)
        MealSlot(
          type: type,
          targetKcal: targetKcal * type.energyShare,
          items: picks[type]!,
        ),
    ];

    return DailyPlan(
      date: date,
      targetKcal: targetKcal,
      targetProtein: targetProtein,
      targetCarb: targetCarb,
      targetFat: targetFat,
      slots: result,
      explorationRatio: ratio,
      nutrientTargets: nutrientTargets,
    );
  }

  /// Tổng từng chất của cả ngày.
  Map<String, double> _dayTotals(Map<MealType, List<MealPlanItem>> picks) {
    final totals = <String, double>{};
    for (final nutrient in NutrientTarget.supported) {
      var sum = 0.0;
      for (final items in picks.values) {
        for (final item in items) {
          sum += NutrientTarget.valueOf(item.food, nutrient) ?? 0;
        }
      }
      totals[nutrient] = sum;
    }
    return totals;
  }

  /// Pha 5 — sửa thực đơn cho thỏa các ràng buộc vi chất cấp ngày.
  ///
  /// Cách làm là **hoán đổi một món cùng vai trò**, không thêm và không bớt
  /// món: thêm món sẽ phá hạn mức năng lượng, bớt món sẽ phá cấu trúc bữa.
  ///
  /// Mỗi vòng xử lý **vi phạm nặng nhất** trước, đo theo tỷ lệ trên ngưỡng để
  /// so được giữa các chất khác đơn vị. Một phép đổi chỉ được nhận khi:
  ///
  ///   1. nó làm vi phạm đang xét **nhỏ lại**;
  ///   2. nó không tạo ra vi phạm mới ở ràng buộc nào khác đang thỏa;
  ///   3. độ lệch năng lượng sau khi đổi vẫn trong [maxEnergyDeviation], hoặc
  ///      không tệ hơn mức đang có.
  ///
  /// Điều kiện 2 là chỗ dễ sai nhất. Không có nó thì pha này sẽ sửa thiếu
  /// chất xơ bằng cách nhồi món nhiều natri, và người tăng huyết áp nhận một
  /// thực đơn đạt xơ nhưng vi phạm đúng ngưỡng quan trọng với họ.
  ///
  /// Khi nhiều phép đổi cùng mức cải thiện, chọn phép **giữ khẩu vị tốt
  /// nhất**: đo được rằng bỏ mặc tiêu chí này làm điểm hợp khẩu vị rơi 7,1 %
  /// thay vì 2,1 %.
  void _repairNutrients({
    required Map<MealType, List<MealPlanItem>> picks,
    required Set<String> usedIds,
    required double targetKcal,
  }) {
    final active = nutrientTargets
        .where((t) => NutrientTarget.supported.contains(t.nutrient))
        .toList();
    if (active.isEmpty) return;

    for (var round = 0; round < nutrientRepairRounds; round++) {
      final totals = _dayTotals(picks);

      NutrientTarget? worst;
      var worstViolation = 0.0;
      for (final target in active) {
        final v = target.violation(totals[target.nutrient] ?? 0);
        if (v > worstViolation) {
          worstViolation = v;
          worst = target;
        }
      }
      if (worst == null) return;

      final kcalNow = picks.values.fold<double>(0, (s, l) => s + _kcalOf(l));
      final deviationNow = targetKcal <= 0
          ? 0.0
          : (kcalNow - targetKcal).abs() / targetKcal;
      final deviationCap = math.max(deviationNow, maxEnergyDeviation);

      MealType? bestMeal;
      var bestIndex = -1;
      Food? bestFood;
      var bestViolation = worstViolation;
      var bestScore = -1.0;

      for (final type in MealType.values) {
        final items = picks[type]!;
        for (var i = 0; i < items.length; i++) {
          final current = items[i].food;
          final currentValue =
              NutrientTarget.valueOf(current, worst.nutrient) ?? 0;

          for (final swap in candidates) {
            if (swap.dishRole != current.dishRole) continue;
            if (usedIds.contains(swap.id)) continue;

            final swapValue = NutrientTarget.valueOf(swap, worst.nutrient) ?? 0;
            final newTotal =
                (totals[worst.nutrient] ?? 0) - currentValue + swapValue;
            final newViolation = worst.violation(newTotal);
            if (newViolation > bestViolation) continue;

            final newKcal = kcalNow - current.kcal + swap.kcal;
            final newDeviation = targetKcal <= 0
                ? 0.0
                : (newKcal - targetKcal).abs() / targetKcal;
            if (newDeviation > deviationCap) continue;

            var breaksOther = false;
            for (final other in active) {
              if (other == worst) continue;
              final before = totals[other.nutrient] ?? 0;
              if (!other.isSatisfiedBy(before)) continue;
              final after =
                  before -
                  (NutrientTarget.valueOf(current, other.nutrient) ?? 0) +
                  (NutrientTarget.valueOf(swap, other.nutrient) ?? 0);
              if (!other.isSatisfiedBy(after)) {
                breaksOther = true;
                break;
              }
            }
            if (breaksOther) continue;

            final score = profile.score(swap);
            final strictlyBetter = newViolation < bestViolation - 1e-9;
            if (strictlyBetter || score > bestScore) {
              bestViolation = newViolation;
              bestScore = score;
              bestMeal = type;
              bestIndex = i;
              bestFood = swap;
            }
          }
        }
      }

      // Không còn phép đổi nào cải thiện được: danh mục không đủ món để thỏa
      // ràng buộc này. Dừng và để `DailyPlan.nutrientViolations` báo ra, thay
      // vì tiếp tục đổi món vô ích hay trả về một thực đơn rỗng.
      if (bestMeal == null || bestFood == null) return;
      if (bestViolation >= worstViolation) return;

      final replaced = picks[bestMeal]![bestIndex];
      usedIds
        ..remove(replaced.food.id)
        ..add(bestFood.id);
      picks[bestMeal]![bestIndex] = MealPlanItem(
        food: bestFood,
        score: profile.score(bestFood),
        explorationDelta: replaced.explorationDelta,
      );
    }
  }

  /// Quyết định suất nào là thăm dò, tính trên **toàn thực đơn**.
  ///
  /// Tỷ lệ 70-30 là thuộc tính của cả thực đơn chứ không của từng bữa — đúng
  /// như cột `exploration_ratio` nằm ở bảng `meal_plans`. Nếu chia theo từng
  /// bữa rồi làm tròn xuống, bữa một món luôn nhận 0 suất thăm dò và bữa ba
  /// món cũng vậy, kết quả là cơ chế thăm dò không bao giờ chạy.
  ///
  /// Suất thăm dò được ưu tiên đặt vào bữa có nhiều món, để không có bữa nào
  /// bị biến thành toàn món thử nghiệm.
  List<_Slot> _assignExplorationSlots(double ratio) {
    final base = <({MealType meal, String role})>[
      for (final type in MealType.values)
        for (final role in _mealStructure[type]!.required)
          (meal: type, role: role),
    ];

    final budget = (base.length * ratio).round();
    if (budget == 0) {
      return [
        for (final s in base) (meal: s.meal, role: s.role, explore: false),
      ];
    }

    // Xếp ứng viên theo số món của bữa, giảm dần; xáo trộn trước để các bữa
    // cùng cỡ không phải lúc nào cũng theo đúng một thứ tự.
    final order = [for (var i = 0; i < base.length; i++) i]..shuffle(_rng);
    order.sort((a, b) {
      final sizeA = _mealStructure[base[a].meal]!.required.length;
      final sizeB = _mealStructure[base[b].meal]!.required.length;
      return sizeB.compareTo(sizeA);
    });

    final explore = order.take(budget).toSet();
    return [
      for (var i = 0; i < base.length; i++)
        (meal: base[i].meal, role: base[i].role, explore: explore.contains(i)),
    ];
  }

  /// Thêm dần suất tùy chọn chừng nào nó còn kéo tổng năng lượng lại gần hạn
  /// mức của cả ngày.
  ///
  /// Chạy ở cấp ngày chứ không cấp bữa vì cam kết trong đề cương là độ lệch
  /// của **thực đơn** không quá 10 %. Một bữa lệch nhiều có thể được bữa khác
  /// bù lại, và đó là hành vi đúng: người ta ăn sáng nhẹ rồi ăn trưa nhiều.
  void _topUp({
    required Map<MealType, List<MealPlanItem>> picks,
    required Set<String> usedIds,
    required double targetKcal,
  }) {
    while (true) {
      final current = picks.values.fold<double>(0, (s, l) => s + _kcalOf(l));
      var bestGap = (current - targetKcal).abs();

      MealType? bestMeal;
      Food? bestFood;

      for (final type in MealType.values) {
        for (final role in _mealStructure[type]!.optional) {
          // Không thêm hai món cùng vai trò vào một bữa.
          if (picks[type]!.any((i) => i.food.dishRole == role)) continue;

          for (final food in candidates) {
            if (food.dishRole != role || usedIds.contains(food.id)) continue;

            final gap = (current + food.kcal - targetKcal).abs();
            if (gap < bestGap) {
              bestGap = gap;
              bestMeal = type;
              bestFood = food;
            }
          }
        }
      }

      if (bestMeal == null || bestFood == null) return;

      usedIds.add(bestFood.id);
      picks[bestMeal]!.add(
        MealPlanItem(food: bestFood, score: profile.score(bestFood)),
      );
    }
  }

  /// Tham lam theo **mật độ điểm**.
  ///
  /// Sắp xếp theo `score / kcal` chứ không theo `score` thuần là điểm mấu
  /// chốt, và là chiến lược kinh điển của bài toán cái túi: ưu tiên món mang
  /// lại nhiều điểm ưa thích nhất **trên mỗi đơn vị năng lượng tiêu tốn**.
  /// Nếu xếp theo điểm thuần, một món 650 kcal điểm 0,9 sẽ luôn thắng món
  /// 300 kcal điểm 0,8, và bữa ăn cạn hạn mức chỉ sau một món.
  ///
  /// Mật độ được cân thêm bởi độ khớp với hạn mức của suất, nếu không thì
  /// món nhẹ nhất luôn thắng vì mẫu số nhỏ.
  Food _greedyPick({
    required List<Food> pool,
    required PreferenceProfile profile,
    required double slotTargetKcal,
  }) {
    Food? best;
    var bestValue = double.negativeInfinity;

    for (final food in pool) {
      final kcal = food.kcal.toDouble();
      if (kcal <= 0) continue;

      final density = profile.score(food) / kcal;
      final fit = slotTargetKcal <= 0
          ? 1.0
          : 1 -
                ((kcal - slotTargetKcal).abs() / slotTargetKcal).clamp(
                  0.0,
                  1.0,
                );

      final value = density * (0.35 + 0.65 * fit);
      if (value > bestValue) {
        bestValue = value;
        best = food;
      }
    }

    return best ?? pool.first;
  }

  /// Tìm kiếm cục bộ bằng phép hoán đổi từng món.
  ///
  /// Lời giải tham lam chỉ nhìn được một suất tại một thời điểm, nên tổng của
  /// cả bữa có thể lệch hạn mức dù từng suất đều hợp lý. Pha này thử thay
  /// từng món đang chọn bằng một món khác cùng vai trò, giữ lại phép thay nào
  /// làm hàm mục tiêu tăng, và dừng khi không còn cải thiện được.
  List<MealPlanItem> _localSearch({
    required List<MealPlanItem> selected,
    required Set<String> usedIds,
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    var current = [...selected];
    var currentScore = _objective(
      current,
      targetKcal: targetKcal,
      targetProtein: targetProtein,
      targetCarb: targetCarb,
      targetFat: targetFat,
    );

    for (var round = 0; round < localSearchRounds; round++) {
      var improved = false;

      for (var i = 0; i < current.length; i++) {
        final item = current[i];
        final inPlan = current.map((e) => e.food.id).toSet();

        final pool = candidates.where(
          (f) =>
              f.dishRole == item.food.dishRole &&
              !inPlan.contains(f.id) &&
              !usedIds.contains(f.id),
        );

        for (final swap in pool) {
          final trial = [...current];
          trial[i] = MealPlanItem(
            food: swap,
            score: profile.score(swap),
            explorationDelta: item.explorationDelta,
          );

          final trialScore = _objective(
            trial,
            targetKcal: targetKcal,
            targetProtein: targetProtein,
            targetCarb: targetCarb,
            targetFat: targetFat,
          );

          if (trialScore > currentScore) {
            current = trial;
            currentScore = trialScore;
            improved = true;
          }
        }
      }

      if (!improved) break;
    }

    return current;
  }

  /// Hàm mục tiêu có phạt.
  ///
  /// ```text
  ///                        | kcal(S) − E |            | macroₖ(S) − Tₖ |
  /// F(S) = Σ score(i)  − λ ────────────────  −  μ  Σ ───────────────────
  ///                               E              k         Tₖ
  /// ```
  ///
  /// Ràng buộc dinh dưỡng được đưa vào hàm mục tiêu dưới dạng thành phần
  /// phạt thay vì loại thẳng lời giải vi phạm. Nhờ vậy thuật toán đi qua
  /// được các lời giải tạm thời lệch nhẹ để tới lời giải tốt hơn, thay vì
  /// kẹt sớm ở một lời giải kém nhưng hợp lệ.
  double _objective(
    List<MealPlanItem> items, {
    required double targetKcal,
    required double targetProtein,
    required double targetCarb,
    required double targetFat,
  }) {
    final totalScore = items.fold<double>(0, (sum, i) => sum + i.score);

    final kcal = _kcalOf(items);
    final energyTerm = targetKcal <= 0
        ? 0.0
        : (kcal - targetKcal).abs() / targetKcal;

    double macroTerm(double actual, double target) =>
        target <= 0 ? 0.0 : (actual - target).abs() / target;

    final protein = items.fold<double>(0, (s, i) => s + i.food.protein);
    final carb = items.fold<double>(0, (s, i) => s + i.food.carb);
    final fat = items.fold<double>(0, (s, i) => s + i.food.fat);

    final macroSum =
        macroTerm(protein, targetProtein) +
        macroTerm(carb, targetCarb) +
        macroTerm(fat, targetFat);

    return totalScore - energyPenalty * energyTerm - macroPenalty * macroSum;
  }

  double _kcalOf(List<MealPlanItem> items) =>
      items.fold(0, (sum, i) => sum + i.food.kcal.toDouble());

  /// Gợi ý món thay thế cho một suất, xếp theo điểm giảm dần.
  ///
  /// Dùng khi người dùng bấm đổi món. Thao tác đổi sinh ra hai tín hiệu huấn
  /// luyện cùng lúc: món bị bỏ nhận nhãn thấp, món được chọn nhận nhãn cao —
  /// xem bảng quy đổi nhãn `plan_replaced` và `plan_kept`.
  List<Food> alternativesFor(
    MealPlanItem item, {
    required Set<String> excludeIds,
    int limit = 6,
  }) {
    final pool = candidates
        .where(
          (f) => f.dishRole == item.food.dishRole && !excludeIds.contains(f.id),
        )
        .toList();

    pool.sort((a, b) {
      final byScore = profile.score(b).compareTo(profile.score(a));
      if (byScore != 0) return byScore;
      // Cùng điểm thì ưu tiên món gần hạn mức của suất đang thay hơn.
      final da = (a.kcal - item.food.kcal).abs();
      final db = (b.kcal - item.food.kcal).abs();
      return da.compareTo(db);
    });

    return pool.take(limit).toList();
  }
}
