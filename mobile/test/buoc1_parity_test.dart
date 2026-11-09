import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/models/health_profile.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';

/// Bản Dart của Bước 1 phải khớp bản tham chiếu Python, từng con số.
///
/// Cùng tệp ca thử mà `backend/Api.Tests/Buoc1ParityTests.cs` dùng, nên ba
/// bản hiện thực bị khóa vào MỘT bộ số:
///
///     tools/gen_buoc1_cases.py                   Python, bản tham chiếu
///     backend/Api/Nutrition/NutritionTargets.cs  C#, máy chủ
///     mobile/lib/data/models/health_profile.dart Dart, ứng dụng  <- ở đây
///
/// Vì sao cần. Ba bản chạy ở ba tầng và không bao giờ gặp nhau, nên khi
/// chúng lệch thì không gì báo ra: ứng dụng hiện một hạn mức, máy chủ sinh
/// thực đơn theo một hạn mức khác, và cả hai con số đều trông hợp lý.
/// Chuyện đó đã xảy ra — bản Dart từng cứng hóa macro 17/60/23 trong khi cột
/// `DEFAULT` của CSDL và đặc tả API đều ghi 15/60/25.
void main() {
  final goc = _timGocRepo();
  final tep = File('${goc.path}/data/buoc1_cases.json');

  if (!tep.existsSync()) {
    test('thiếu tệp ca thử', () {
      fail('Thiếu ${tep.path}\n'
          'Sinh bằng: python tools/gen_buoc1_cases.py');
    });
    return;
  }

  final mau = jsonDecode(tep.readAsStringSync()) as Map<String, dynamic>;
  final cases = (mau['cases'] as List).cast<Map<String, dynamic>>();

  group('Bước 1 — Dart khớp bản tham chiếu Python', () {
    for (final ca in cases) {
      final ten = ca['ten'] as String;
      final vao = ca['vao'] as Map<String, dynamic>;
      final mong = ca['ra'] as Map<String, dynamic>;

      test(ten, () {
        final gioi = vao['gender'] as String;

        // `Gender` của Dart chỉ có male và female — ứng dụng không bao giờ
        // hiện lựa chọn thứ ba. Nhưng ENUM `health_profiles.gender` có
        // `other`, và máy chủ phải xử lý được thứ lược đồ cho phép. Bỏ qua
        // những ca đó ở đây, KHÔNG làm chúng đạt một cách giả.
        if (gioi == 'other') {
          markTestSkipped(
            "Gender của Dart không có 'other'; bản C# xử lý bằng trung "
            'điểm hai hằng số Mifflin — xem NutritionTargets.MifflinOther',
          );
          return;
        }

        final hoSo = HealthProfile()
          ..gender = gioi == 'male' ? Gender.male : Gender.female
          ..birthday = DateTime.parse(vao['dateOfBirth'] as String)
          ..heightCm = (vao['heightCm'] as num).toDouble()
          ..weightKg = (vao['weightKg'] as num).toDouble()
          ..activity = ActivityLevel.values
              .firstWhere((a) => a.code == vao['activityLevel'])
          ..goal =
              HealthGoal.values.firstWhere((g) => g.code == vao['goal'])
          ..proteinPct = vao['proteinPct'] as int
          ..carbsPct = vao['carbsPct'] as int
          ..fatPct = vao['fatPct'] as int
          // Gán "hôm nay" cố định theo tệp mẫu. Không có dòng này thì mọi
          // ca có tuổi khác tuổi tính ra hôm nay sẽ bị bỏ qua — tức là gần
          // hết, gần như cả năm, mà bài kiểm vẫn báo đạt.
          ..today = DateTime.parse(vao['today'] as String);

        // Tuổi phải khớp, không được bỏ qua. Trước đây bài kiểm này bỏ
        // qua mọi ca có tuổi lệch, vì `HealthProfile.age` luôn đọc
        // `DateTime.now()`. Giờ `HealthProfile.today` nhận ngày tham chiếu,
        // nên phép so này so thật.
        expect(hoSo.age, mong['age'], reason: 'age');

        expect(_tron(hoSo.bmi!, 2), mong['bmi'], reason: 'bmi');
        expect(_tron(hoSo.bmr!, 0), mong['bmrKcal'], reason: 'bmrKcal');
        expect(_tron(hoSo.tdee!, 0), mong['tdeeKcal'], reason: 'tdeeKcal');
        expect(hoSo.activity!.factor, mong['activityFactor'],
            reason: 'activityFactor');
        expect(_tron(hoSo.energyTarget!, 0), mong['dailyCaloriesTarget'],
            reason: 'dailyCaloriesTarget');

        final macro = hoSo.macroTarget!;
        expect(_tron(macro.protein, 1), mong['proteinG'],
            reason: 'proteinG');
        expect(_tron(macro.carb, 1), mong['carbsG'], reason: 'carbsG');
        expect(_tron(macro.fat, 1), mong['fatG'], reason: 'fatG');

        final buaMong = mong['mealKcal'] as Map<String, dynamic>;
        for (final m in MealType.values) {
          expect(
            _tron(hoSo.energyTarget! * m.energyShare, 0),
            buaMong[m.code],
            reason: 'mealKcal.${m.code}',
          );
        }
      });
    }
  });

  test('tỷ lệ bữa của MealType khớp tệp mẫu, cả hai chiều', () {
    final tl = (mau['mealShare'] as Map<String, dynamic>);
    expect(
      MealType.values.map((m) => m.code).toList()..sort(),
      tl.keys.toList()..sort(),
    );
    for (final m in MealType.values) {
      expect(m.energyShare, tl[m.code], reason: m.code);
    }
    // Bốn tỷ lệ phải cộng đúng 1. Một bộ cộng 0.95 không gây lỗi nào — Bước
    // 4 chỉ đơn giản phân bổ thiếu 5 % năng lượng mỗi ngày.
    final tong = MealType.values
        .fold<double>(0, (s, m) => s + m.energyShare);
    expect(tong, closeTo(1.0, 1e-12));
  });

  test('hệ số vận động của ActivityLevel khớp tệp mẫu, cả hai chiều', () {
    final hs = (mau['activityFactor'] as Map<String, dynamic>);
    expect(
      ActivityLevel.values.map((a) => a.code).toList()..sort(),
      hs.keys.toList()..sort(),
    );
    for (final a in ActivityLevel.values) {
      expect(a.factor, hs[a.code], reason: a.code);
    }
  });

  test('ba tỷ lệ macro mặc định cộng đúng 100 và khớp DEFAULT của lược đồ',
      () {
    final p = HealthProfile();
    expect(p.proteinPct + p.carbsPct + p.fatPct, 100);
    // Đúng bằng `DEFAULT` của ba cột target_*_pct trong db/schema.sql.
    expect([p.proteinPct, p.carbsPct, p.fatPct], [15, 60, 25]);
  });
}

/// Làm tròn ra xa 0, như bản Python và như `MidpointRounding.AwayFromZero`.
///
/// `double.round()` của Dart làm tròn ra xa 0 với .5, nên chỉ cần nhân–chia
/// để lấy số chữ số thập phân. Nhưng phải cộng một epsilon rất nhỏ: nhân
/// `double` lên 100 có thể cho 2314.9999999999995 thay vì 2315, và khi đó
/// `.round()` trả 2314 — lệch một đơn vị ở chữ số cuối, đúng kiểu sai mà chỉ
/// một bộ kiểm parity bắt được.
num _tron(double v, int le) {
  final heSo = [1, 10, 100][le];
  final nhan = v * heSo;
  final dau = nhan.isNegative ? -1 : 1;
  final lamTron = ((nhan.abs() + 1e-9).round()) * dau;
  return le == 0 ? lamTron : lamTron / heSo;
}

/// Lần từ thư mục chạy lên gốc repo, theo DẤU HIỆU `db/schema.sql`.
///
/// `flutter test` chạy với thư mục hiện tại là `mobile/`, nhưng không đếm số
/// bậc: nó đổi theo cách gọi.
Directory _timGocRepo() {
  var d = Directory.current;
  while (!File('${d.path}/db/schema.sql').existsSync()) {
    final cha = d.parent;
    if (cha.path == d.path) {
      throw StateError('Không tìm thấy gốc repo từ ${Directory.current.path}');
    }
    d = cha;
  }
  return d;
}
