import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';

/// Kiểm chứng chéo: bản Dart và bản Python phải cho ra **cùng một vector**.
///
/// Mô hình học máy được huấn luyện bằng `ml/features.py` ở phía máy chủ,
/// nhưng khi chạy thật thì điểm số được tính bằng `FoodVectorSpace` ở đây.
/// Hai bản lệch nhau dù chỉ một chiều là mô hình học trên một không gian và
/// suy luận trên một không gian khác — và **không có gì báo lỗi**: mô hình
/// vẫn chạy, vẫn trả về số, chỉ là số sai. Nên phép đối chiếu này phải là
/// một bài kiểm, không phải một lần xem mắt.
///
/// Tệp mẫu do `python tools/check_feature_parity.py` sinh ra từ CSDL thật:
/// nó chứa cả đầu vào (món ăn) lẫn đầu ra mong đợi (vector bản Python).
/// Nhờ vậy bài kiểm này chạy được mà không cần CSDL.
///
/// Sai số cho phép là 1e-12 chứ không phải so sánh bằng tuyệt đối: hai bản
/// làm **cùng một dãy phép tính** nên về nguyên tắc ra đúng từng bit, nhưng
/// giá trị đi qua một vòng JSON nên để một khe hở nhỏ cho phép làm tròn ở
/// tầng văn bản. Khe hở này nhỏ hơn mọi sai lệch thuật toán có thể có.
const double _saiSoChoPhep = 1e-12;

const _mauXam = [Color(0xFFCCCCCC), Color(0xFF888888)];

Food _monTuMau(Map<String, dynamic> j) => Food(
  id: j['id'] as String,
  name: j['name'] as String,
  category: j['category'] as String,
  dishRole: j['dishRole'] as String,
  spiceLevel: j['spiceLevel'] as int,
  kcal: j['kcal'] as int,
  protein: (j['protein'] as num).toDouble(),
  carb: (j['carb'] as num).toDouble(),
  fat: (j['fat'] as num).toDouble(),
  sugar: (j['sugar'] as num).toDouble(),
  sodium: (j['sodium'] as num).toDouble(),
  fiber: (j['fiber'] as num).toDouble(),
  servingSizeG: (j['servingSizeG'] as num).toDouble(),
  // Hai trường chỉ dùng cho giao diện, không vào vector.
  emoji: '🍚',
  gradient: _mauXam,
);

void main() {
  final tep = File('test/fixtures/food_vector_parity.json');

  group('Trích chọn đặc trưng — bản Dart khớp bản Python', () {
    setUpAll(() {
      expect(
        tep.existsSync(),
        isTrue,
        reason:
            'Chưa có tệp mẫu ${tep.path}. '
            'Sinh bằng: python tools/check_feature_parity.py --chi-sinh',
      );
    });

    final mau =
        jsonDecode(tep.readAsStringSync()) as Map<String, dynamic>;
    final mon = (mau['foods'] as List)
        .map((j) => _monTuMau(j as Map<String, dynamic>))
        .toList();
    final vectorMongDoi = (mau['vectors'] as List)
        .map((v) => (v as List).map((x) => (x as num).toDouble()).toList())
        .toList();
    final scaler = mau['scaler'] as Map<String, dynamic>;

    final khongGian = FoodVectorSpace.fromFoods(mon);

    test('tập món mẫu không rỗng', () {
      expect(mon, isNotEmpty);
      expect(vectorMongDoi.length, mon.length);
    });

    test('danh sách nhóm món và số chiều trùng nhau', () {
      expect(
        khongGian.categories,
        (scaler['categories'] as List).cast<String>(),
        reason: 'Thứ tự nhóm món quyết định thứ tự chiều one-hot. '
            'Lệch thứ tự là lệch toàn bộ phần đuôi của vector.',
      );
      expect(khongGian.length, mau['length'] as int);
      expect(khongGian.labels.length, khongGian.length);
    });

    test('tám tham số min–max của phép chuẩn hóa trùng nhau', () {
      // Đây là trạng thái của không gian, không phải của món. Hai bản tự
      // tính độc lập từ cùng tập món, nên lệch ở đây nghĩa là một bên đã
      // lọc hoặc suy giá trị khác bên kia.
      expect(khongGian.minKcal, closeTo(
          (scaler['min_kcal'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.maxKcal, closeTo(
          (scaler['max_kcal'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.minSugar, closeTo(
          (scaler['min_sugar'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.maxSugar, closeTo(
          (scaler['max_sugar'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.minSodium, closeTo(
          (scaler['min_sodium'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.maxSodium, closeTo(
          (scaler['max_sodium'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.minFiber, closeTo(
          (scaler['min_fiber'] as num).toDouble(), _saiSoChoPhep));
      expect(khongGian.maxFiber, closeTo(
          (scaler['max_fiber'] as num).toDouble(), _saiSoChoPhep));
    });

    test('từng chiều của từng món trùng nhau', () {
      var lechLonNhat = 0.0;
      String? choLech;

      for (var i = 0; i < mon.length; i++) {
        final thucTe = khongGian.encode(mon[i]);
        final mongDoi = vectorMongDoi[i];

        expect(
          thucTe.length,
          mongDoi.length,
          reason: 'Số chiều lệch ở món ${mon[i].name}',
        );

        for (var d = 0; d < thucTe.length; d++) {
          final lech = (thucTe[d] - mongDoi[d]).abs();
          if (lech > lechLonNhat) {
            lechLonNhat = lech;
            choLech = '${mon[i].name} · chiều $d (${khongGian.labels[d]})';
          }
        }
      }

      expect(
        lechLonNhat,
        lessThan(_saiSoChoPhep),
        reason: 'Lệch lớn nhất $lechLonNhat tại $choLech',
      );
    });

    test('mỗi món bật đúng một chiều one-hot nhóm', () {
      // Nếu một món thuộc nhóm không có trong không gian thì toàn bộ khối
      // one-hot bằng 0 và món đó mất thông tin nhóm một cách im lặng.
      final batDau = khongGian.length - khongGian.categories.length;
      for (final m in mon) {
        final v = khongGian.encode(m);
        final tongOneHot = v.skip(batDau).fold<double>(0, (a, b) => a + b);
        expect(
          tongOneHot,
          closeTo(1.0, _saiSoChoPhep),
          reason: 'Món ${m.name} (nhóm ${m.category}) không bật chiều nào',
        );
      }
    });

    test('mọi chiều nằm trong đoạn [0, 1]', () {
      for (final m in mon) {
        for (final (d, x) in khongGian.encode(m).indexed) {
          expect(
            x,
            inInclusiveRange(0.0, 1.0),
            reason: 'Món ${m.name}, chiều $d (${khongGian.labels[d]}) = $x',
          );
        }
      }
    });
  });
}
