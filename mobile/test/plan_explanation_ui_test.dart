import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/mock/mock_rules.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/meal_plan.dart';
import 'package:nutrition_app/data/models/swipe_action.dart';
import 'package:nutrition_app/data/recommender/food_vector.dart';
import 'package:nutrition_app/data/recommender/preference_profile.dart';
import 'package:nutrition_app/data/rules/condition_rule.dart';
import 'package:nutrition_app/data/rules/day_budget.dart';
import 'package:nutrition_app/data/rules/dish_screening.dart';
import 'package:nutrition_app/data/rules/evidence_level.dart';
import 'package:nutrition_app/features/plan/excluded_screen.dart';
import 'package:nutrition_app/features/plan/reason_screen.dart';
import 'package:nutrition_app/features/plan/widgets/day_budget_card.dart';
import 'package:nutrition_app/features/plan/widgets/replace_sheet.dart';

/// Bốn màn giải thích — kiểm những điều mà chú thích trong mã chỉ *hứa*.
///
/// Mỗi phép kiểm ở đây tương ứng một cách nói sai cụ thể mà màn hình phải
/// tránh, không phải "widget dựng được không". Một màn giải thích dựng xong
/// nhưng nói sai thì tệ hơn không có màn nào.

const _grey = [Color(0xFFCCCCCC), Color(0xFF888888)];

Food _food({
  required String id,
  required String name,
  double sodium = 100,
  double? purine,
  double fat = 5,
  int kcal = 200,
  String category = 'Món canh',
  List<String> tags = const [],
}) => Food(
  id: id,
  name: name,
  category: category,
  dishRole: 'Món chính',
  spiceLevel: 0,
  kcal: kcal,
  protein: 10,
  carb: 10,
  fat: fat,
  sugar: 2,
  sodium: sodium,
  fiber: 2,
  servingSizeG: 200,
  purine: purine,
  emoji: '🍚',
  gradient: _grey,
  tags: tags,
);

Widget _host(Widget child) =>
    MaterialApp(theme: AppTheme.light, home: Scaffold(body: child));

void _tall(WidgetTester tester) {
  tester.view.physicalSize = const Size(412 * 3, 2200 * 3);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

const _conditions = [
  UserCondition('Tăng huyết áp'),
  UserCondition('Gút'),
];

DayBudget _budget({
  List<Food> eaten = const [],
  List<Food> planned = const [],
}) => DayBudget.from(
  thresholds: dayThresholdsFor(_conditions),
  eaten: eaten,
  planned: planned,
);

void main() {
  group('DayBudgetCard — hạn mức hiện TRƯỚC khi nó chặn món', () {
    testWidgets('nêu phần còn lại, tên bệnh và xuất xứ ngưỡng', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          DayBudgetCard(
            budget: _budget(
              eaten: [_food(id: 'a', name: 'Đã ăn', sodium: 800, purine: 76)],
            ),
          ),
        ),
      );

      expect(find.text('Hạn mức còn lại hôm nay'), findsOneWidget);
      expect(find.textContaining('Natri'), findsWidgets);
      expect(find.textContaining('800 / 2.000 mg'), findsOneWidget);
      expect(find.textContaining('Còn 1.200 mg'), findsOneWidget);
      expect(find.textContaining('Tăng huyết áp'), findsWidgets);
      // Xuất xứ phải ở trên màn hình, không chỉ trong CSDL.
      expect(find.textContaining('có nguồn công bố'), findsWidgets);
      expect(find.textContaining('WHO'), findsWidgets);
    });

    testWidgets('vượt trần thì nói vượt BAO NHIÊU', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          DayBudgetCard(
            budget: _budget(
              eaten: [_food(id: 'a', name: 'Mặn', sodium: 2500, purine: 10)],
            ),
          ),
        ),
      );
      // Kẹp phần còn lại về 0 thì câu này không viết được.
      expect(find.textContaining('Đã vượt 500 mg'), findsOneWidget);
    });

    testWidgets('món khuyết số liệu thì nói con số đang NỚI hơn thực tế', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          DayBudgetCard(
            budget: _budget(
              eaten: [_food(id: 'a', name: 'Khuyết purin', sodium: 300)],
              planned: [_food(id: 'b', name: 'Khuyết nữa', sodium: 200)],
            ),
          ),
        ),
      );
      // Đây là phép kiểm quan trọng nhất của thẻ này: cộng món khuyết thành
      // 0 rồi hiện một con số trông bình thường là để tầng an toàn thất bại
      // theo hướng MỞ mà không báo gì.
      expect(find.textContaining('2 món không có số liệu purin'), findsOneWidget);
      expect(find.textContaining('thấp hơn thực tế'), findsOneWidget);
    });

    testWidgets('hạn mức MỀM nói "vượt khuyến cáo", không nói "bị loại"', (
      tester,
    ) async {
      _tall(tester);
      final budget = DayBudget.from(
        thresholds: dayThresholdsFor(const [UserCondition('Đái tháo đường')]),
        eaten: [
          Food(
            id: 'ngot',
            name: 'Rất ngọt',
            category: 'Tráng miệng',
            dishRole: 'Món phụ',
            spiceLevel: 0,
            kcal: 200,
            protein: 1,
            carb: 50,
            fat: 1,
            sugar: 60,
            sodium: 10,
            fiber: 1,
            servingSizeG: 200,
            emoji: '🍰',
            gradient: _grey,
          ),
        ],
        planned: const [],
      );
      await tester.pumpWidget(_host(DayBudgetCard(budget: budget)));

      expect(find.textContaining('Vượt khuyến cáo đường'), findsOneWidget);
      expect(find.textContaining('không món nào bị chặn'), findsOneWidget);
      expect(find.text('Khuyến cáo hôm nay'), findsOneWidget);
      expect(find.text('Hạn mức còn lại hôm nay'), findsNothing);
    });
  });

  group('ExcludedScreen — ba bậc, và bậc giữa nói rõ "hôm khác vẫn hợp"', () {
    final foods = [
      _food(id: 'ok', name: 'Canh nhạt', sodium: 100, purine: 30),
      _food(
        id: 'tom',
        name: 'Tôm hấp',
        sodium: 100,
        purine: 30,
        tags: const ['Có hải sản'],
      ),
      _food(id: 'man', name: 'Bún siêu mặn', sodium: 9000, purine: 30),
      _food(id: 'la', name: 'Món chưa đo purin', sodium: 100),
    ];

    ScreeningResult result() => screenDishes(
      foods: foods,
      conditions: const [...
        _conditions,
        UserCondition('Dị ứng hải sản'),
      ],
      budget: _budget(),
      softRules: softRulesFor(_conditions),
    );

    testWidgets('ba tiêu đề bậc, mỗi bậc có câu dẫn riêng', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );

      expect(find.text('Không phù hợp với bạn'), findsOneWidget);
      expect(find.text('Hôm nay hết hạn mức'), findsOneWidget);
      expect(find.text('Chưa xét được'), findsOneWidget);

      // Câu quyết định của cả màn. Thiếu nó thì người dùng tin món bị chặn
      // vì hạn mức là món cấm với mình.
      expect(
        find.textContaining('hôm khác những món này vẫn hợp'),
        findsOneWidget,
      );
      // Và bậc chưa xét được KHÔNG được trình bày như an toàn.
      expect(find.textContaining('không phải "an toàn"'), findsOneWidget);
    });

    testWidgets('lý do nhãn nêu tên nhãn, không nêu con số', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Tôm hấp'), findsOneWidget);
      expect(find.textContaining('Có nhãn'), findsWidgets);
      expect(find.textContaining('Dị ứng hải sản'), findsWidgets);
      expect(find.textContaining('quy tắc định nghĩa'), findsWidgets);
    });

    testWidgets('thiếu số liệu nói "không có số liệu", KHÔNG nói "vượt"', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Món chưa đo purin'), findsOneWidget);
      expect(find.textContaining('Không có số liệu purin'), findsWidgets);
      // Nói "vượt ngưỡng" khi thật ra là "chúng tôi không biết" là sai sự
      // thật, nên câu đó không được xuất hiện cho món này.
      expect(
        find.textContaining('Không có số liệu purin nên không đối chiếu'),
        findsWidgets,
      );
    });

    testWidgets('món sạch KHÔNG nằm trong danh sách bị bỏ', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Canh nhạt'), findsNothing);
    });
  });

  group('ReasonScreen — điểm tổng đứng TRƯỚC thanh so sánh', () {
    final mon = [
      _food(id: 'a', name: 'Canh A', sodium: 100, purine: 30),
      _food(
        id: 'b',
        name: 'Cơm B',
        sodium: 200,
        purine: 40,
        kcal: 400,
        // Khác nhóm là bắt buộc: hai món cùng nhóm thì chiều one-hot bị
        // một lượt `like` và một lượt `dislike` triệt tiêu về 0, và câu
        // "Bạn thích nhóm …" không bao giờ xuất hiện.
        category: 'Cơm',
      ),
    ];
    final space = FoodVectorSpace.fromFoods(mon);

    testWidgets('hiện điểm khớp tổng và câu cảnh báo về thanh so sánh', (
      tester,
    ) async {
      _tall(tester);
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [(food: mon[0], action: SwipeAction.like)],
      );
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: mon[0],
            profile: profile,
            budget: _budget(),
            penalty: PenaltyOutcome.of(mon[0], softRulesFor(_conditions)),
            betterThanShare: 0.71,
          ),
        ),
      );

      expect(find.text('khớp khẩu vị của bạn'), findsOneWidget);
      expect(find.textContaining('Cao hơn 71 %'), findsOneWidget);
      // Câu này là điều kiện để mấy thanh kia không nói sai: ratio chuẩn hóa
      // theo đỉnh của chính món, nên một món khớp yếu vẫn ra ba thanh gần đầy.
      expect(find.textContaining('không đo mức khớp'), findsOneWidget);
      expect(find.text('ĐIỀU GÌ KHỚP NHẤT'), findsOneWidget);
    });

    testWidgets('câu giải thích là CÂU, không lọt số thô', (tester) async {
      _tall(tester);
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: mon[0], action: SwipeAction.like),
          (food: mon[1], action: SwipeAction.dislike),
        ],
      );
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: mon[0],
            profile: profile,
            budget: _budget(),
            penalty: PenaltyOutcome.of(mon[0], softRulesFor(_conditions)),
          ),
        ),
      );
      expect(find.textContaining('Bạn thích nhóm'), findsWidgets);
      expect(find.textContaining('+0.'), findsNothing);
      expect(find.textContaining('Tỷ lệ đạm ('), findsNothing);
    });

    testWidgets('hồ sơ rỗng thì nói thật, không bịa ba lý do', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: mon[0],
            profile: PreferenceProfile.empty(space),
            budget: _budget(),
            penalty: PenaltyOutcome.of(mon[0], softRulesFor(_conditions)),
          ),
        ),
      );
      expect(find.textContaining('Chưa đủ lượt vuốt'), findsOneWidget);
      expect(find.text('ĐIỀU GÌ KHỚP NHẤT'), findsNothing);
    });

    testWidgets('món khuyết purin: nói không đối chiếu được, không nói đạt', (
      tester,
    ) async {
      _tall(tester);
      final khuyet = _food(id: 'x', name: 'Chưa đo', sodium: 100);
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: khuyet,
            profile: PreferenceProfile.empty(space),
            budget: _budget(),
            penalty: PenaltyOutcome.of(khuyet, softRulesFor(_conditions)),
          ),
        ),
      );
      expect(
        find.textContaining('danh mục không có số liệu'),
        findsWidgets,
      );
      expect(find.text('ẢNH HƯỞNG HÔM NAY'), findsOneWidget);
    });

    testWidgets('điểm cần lưu ý nêu hệ số nhân và chữ "vẫn chọn được"', (
      tester,
    ) async {
      _tall(tester);
      final man = _food(id: 'm', name: 'Rất mặn', sodium: 900, purine: 10);
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: man,
            profile: PreferenceProfile.empty(space),
            budget: _budget(),
            penalty: PenaltyOutcome.of(man, softRulesFor(_conditions)),
          ),
        ),
      );
      expect(find.text('ĐIỂM CẦN LƯU Ý'), findsOneWidget);
      expect(find.textContaining('×0.60'), findsOneWidget);
      expect(find.textContaining('vẫn chọn được'), findsOneWidget);
      expect(find.textContaining('không phải chống chỉ định'), findsOneWidget);
    });
  });

  group('ReplaceSheet — hai hạn mức song song, món không vừa vẫn hiện', () {
    final cu = MealPlanItem(
      food: _food(id: 'cu', name: 'Món cũ', sodium: 400, purine: 50),
      score: 0.6,
    );

    testWidgets('dải hạn mức nêu CẢ HAI chất, kèm câu "vừa cả hai"', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: cu,
            alternatives: [_food(id: 'a', name: 'Món A', purine: 20)],
            scoreOf: (_) => 0.7,
            budgetAfterRemoval: _budget(
              eaten: [_food(id: 'e', name: 'Đã ăn', sodium: 1500, purine: 300)],
            ),
          ),
        ),
      );
      expect(find.textContaining('Bỏ món cũ ra'), findsOneWidget);
      expect(find.textContaining('natri'), findsWidgets);
      expect(find.textContaining('purin'), findsWidgets);
      // Một món có thể rất tốt ở chất đang thiếu mà vẫn bị chặn bởi chất
      // khác, nên xếp hạng theo một chất rồi kết luận là sai.
      expect(find.textContaining('vừa cả hai'), findsOneWidget);
    });

    testWidgets('món không vừa vẫn HIỆN, kèm lý do và "hôm khác chọn được"', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: cu,
            alternatives: [
              _food(id: 'man', name: 'Món quá mặn', sodium: 5000, purine: 20),
              _food(id: 'ok', name: 'Món vừa', sodium: 50, purine: 20),
            ],
            scoreOf: (_) => 0.7,
            budgetAfterRemoval: _budget(),
          ),
        ),
      );
      // Ẩn món không vừa thì người dùng không bao giờ biết món mình muốn vẫn
      // chọn được vào hôm khác.
      expect(find.text('Món quá mặn'), findsOneWidget);
      expect(find.textContaining('hôm khác chọn được'), findsOneWidget);
      expect(find.text('Món vừa'), findsOneWidget);
    });

    testWidgets('bấm món không vừa thì KHÔNG đóng bảng', (tester) async {
      _tall(tester);
      Food? chon;
      await tester.pumpWidget(
        _host(
          Builder(
            builder: (context) => ElevatedButton(
              onPressed: () async {
                chon = await ReplaceSheet.show(
                  context,
                  item: cu,
                  alternatives: [
                    _food(id: 'man', name: 'Món quá mặn', sodium: 5000, purine: 20),
                  ],
                  scoreOf: (_) => 0.7,
                  budgetAfterRemoval: _budget(),
                );
              },
              child: const Text('mở'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('mở'));
      await tester.pumpAndSettle();
      expect(find.text('Món quá mặn'), findsOneWidget);

      await tester.tap(find.text('Món quá mặn'));
      await tester.pumpAndSettle();
      expect(
        find.text('Món quá mặn'),
        findsOneWidget,
        reason: 'bảng vẫn mở vì món đó không chọn được hôm nay',
      );
      expect(chon, isNull);
    });

    testWidgets('món khuyết số liệu KHÔNG bị chặn, nhưng được nói ra', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: cu,
            alternatives: [_food(id: 'la', name: 'Chưa đo purin', sodium: 50)],
            scoreOf: (_) => 0.7,
            budgetAfterRemoval: _budget(),
          ),
        ),
      );
      // Chặn vì danh mục thiếu số liệu là phạt sai đối tượng; im lặng cho qua
      // thì lại nới hạn mức. Nên: cho qua, và nói ra.
      expect(find.text('Chưa đo purin'), findsOneWidget);
      expect(find.textContaining('Chưa có số liệu purin'), findsOneWidget);
    });
  });

  group('EvidenceLevel trên giao diện', () {
    testWidgets('mức không dẫn được nguồn hiện chữ riêng, không chỉ màu', (
      tester,
    ) async {
      _tall(tester);
      const suyRa = DayLimit(
        condition: 'Bệnh thận',
        nutrient: 'protein_g',
        unit: 'g',
        amount: 48,
        eaten: 10,
        planned: 0,
        isHard: true,
        evidence: EvidenceLevel.derived,
        note: 'KDIGO 2024: 0,8 g đạm/kg/ngày. 48 g cho người 60 kg',
      );
      await tester.pumpWidget(
        _host(const DayBudgetCard(budget: DayBudget(limits: [suyRa]))),
      );
      // Màu một mình thì người mù màu không đọc được, mà đây là thông tin
      // về sức khỏe.
      expect(find.textContaining('suy ra kèm giả thiết'), findsOneWidget);
      expect(find.textContaining('cho người 60 kg'), findsOneWidget);
    });
  });
}
