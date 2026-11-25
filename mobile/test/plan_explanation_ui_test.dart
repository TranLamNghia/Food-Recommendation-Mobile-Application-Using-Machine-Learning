import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nutrition_app/core/theme/app_theme.dart';
import 'package:nutrition_app/data/mock/mock_rules.dart';
import 'package:nutrition_app/data/models/food.dart';
import 'package:nutrition_app/data/models/food_adapters.dart';
import 'package:nutrition_app/data/models/food_brief.dart';
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

/// The four explanation screens — checking what the comments in the code
/// only *promise*.
///
/// Each check here corresponds to one specific way of misstating something
/// that the screen has to avoid; none of them is "does the widget build". An
/// explanation screen that builds but says the wrong thing is worse than no
/// screen at all.

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

/// A candidate the OFFLINE builder would hand over: the whole dish and a
/// score, and no day-level figures, because nothing on this side computes
/// them. See [ReplaceOption].
ReplaceOption _option(Food dish, {double score = 0.7}) =>
    ReplaceOption(food: dish.brief, dish: dish, score: score);

void main() {
  group('DayBudgetCard — the allowance shows BEFORE it blocks a dish', () {
    testWidgets('states what is left, the condition and the source', (
      tester,
    ) async {
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
      // The provenance has to be on the screen, not only in the database.
      expect(find.textContaining('có nguồn công bố'), findsWidgets);
      expect(find.textContaining('WHO'), findsWidgets);
    });

    testWidgets('over the ceiling, it says BY HOW MUCH', (tester) async {
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
      // Clamping the remainder at 0 would make this sentence
      // unwritable.
      expect(find.textContaining('Đã vượt 500 mg'), findsOneWidget);
    });

    testWidgets('with missing data it says the number is TOO PERMISSIVE', (
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
      // This is the most important check on this card: adding the missing
      // dishes up as 0 and showing a normal-looking number is letting the
      // safety layer fail OPEN with no warning.
      expect(find.textContaining('2 món không có số liệu purin'), findsOneWidget);
      expect(find.textContaining('thấp hơn thực tế'), findsOneWidget);
    });

    testWidgets('a SOFT allowance says "over the recommendation", not "excluded"', (
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

  group('ExcludedScreen — three tiers, the middle one saying "fine another day"', () {
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

    testWidgets('three tier headings, each with its own leading line', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );

      expect(find.text('Không phù hợp với bạn'), findsOneWidget);
      expect(find.text('Hôm nay hết hạn mức'), findsOneWidget);
      expect(find.text('Chưa xét được'), findsOneWidget);

      // The decisive sentence of the whole screen. Without it the user
      // believes a dish blocked by an allowance is forbidden to them.
      expect(
        find.textContaining('hôm khác những món này vẫn hợp'),
        findsOneWidget,
      );
      // And the undecidable tier must NOT be presented as safe.
      expect(find.textContaining('không phải "an toàn"'), findsOneWidget);
    });

    testWidgets('a tag reason names the tag, not a number', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Tôm hấp'), findsOneWidget);
      expect(find.textContaining('Có nhãn'), findsWidgets);
      expect(find.textContaining('Dị ứng hải sản'), findsWidgets);
      expect(find.textContaining('quy tắc định nghĩa'), findsWidgets);
    });

    testWidgets('missing data says "no measurement", NOT "over"', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Món chưa đo purin'), findsOneWidget);
      expect(find.textContaining('Không có số liệu purin'), findsWidgets);
      // Saying "over the limit" when the truth is "we do not know" is a
      // false statement, so that wording must not appear for this dish.
      expect(
        find.textContaining('Không có số liệu purin nên không đối chiếu'),
        findsWidgets,
      );
    });

    testWidgets('a clean dish is NOT in the dropped list', (tester) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(ExcludedScreen(screening: result(), foods: foods)),
      );
      expect(find.text('Canh nhạt'), findsNothing);
    });
  });

  group('ReasonScreen — the overall score comes BEFORE the bars', () {
    final food = [
      _food(id: 'a', name: 'Canh A', sodium: 100, purine: 30),
      _food(
        id: 'b',
        name: 'Cơm B',
        sodium: 200,
        purine: 40,
        kcal: 400,
        // Different groups are mandatory: for two dishes in the same
        // group, one `like` and one `dislike` cancel the one-hot dimension
        // to 0, and the sentence "Bạn thích nhóm …" never appears.
        category: 'Cơm',
      ),
    ];
    final space = FoodVectorSpace.fromFoods(food);

    testWidgets('shows the overall score and the caveat about the bars', (
      tester,
    ) async {
      _tall(tester);
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [(food: food[0], action: SwipeAction.like)],
      );
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: food[0],
            profile: profile,
            budget: _budget(),
            penalty: PenaltyOutcome.of(food[0], softRulesFor(_conditions)),
            betterThanShare: 0.71,
          ),
        ),
      );

      expect(find.text('khớp khẩu vị của bạn'), findsOneWidget);
      expect(find.textContaining('Cao hơn 71 %'), findsOneWidget);
      // This sentence is what stops the bars from misleading: the ratio is
      // normalised against the dish's own peak, so a weak match still gives
      // three nearly full bars.
      expect(find.textContaining('không đo mức khớp'), findsOneWidget);
      expect(find.text('ĐIỀU GÌ KHỚP NHẤT'), findsOneWidget);
    });

    testWidgets('an explanation is a SENTENCE, with no raw number', (
      tester,
    ) async {
      _tall(tester);
      final profile = PreferenceProfile.fromSwipes(
        space: space,
        swipes: [
          (food: food[0], action: SwipeAction.like),
          (food: food[1], action: SwipeAction.dislike),
        ],
      );
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: food[0],
            profile: profile,
            budget: _budget(),
            penalty: PenaltyOutcome.of(food[0], softRulesFor(_conditions)),
          ),
        ),
      );
      expect(find.textContaining('Bạn thích nhóm'), findsWidgets);
      expect(find.textContaining('+0.'), findsNothing);
      expect(find.textContaining('Tỷ lệ đạm ('), findsNothing);
    });

    testWidgets('an empty profile is honest, it invents no three reasons', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReasonScreen(
            food: food[0],
            profile: PreferenceProfile.empty(space),
            budget: _budget(),
            penalty: PenaltyOutcome.of(food[0], softRulesFor(_conditions)),
          ),
        ),
      );
      expect(find.textContaining('Chưa đủ lượt vuốt'), findsOneWidget);
      expect(find.text('ĐIỀU GÌ KHỚP NHẤT'), findsNothing);
    });

    testWidgets('a dish with no purine: says it cannot be checked, not met', (
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

    testWidgets('the caveats name the multiplier and "vẫn chọn được"', (
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

  group('ReplaceSheet — two allowances side by side, misfits still shown', () {
    final old = MealPlanItem.offline(
      dish: _food(id: 'cu', name: 'Món cũ', sodium: 400, purine: 50),
      score: 0.6,
    );

    testWidgets('the strip names BOTH nutrients, with a "fits both" line', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: old,
            alternatives: [_option(_food(id: 'a', name: 'Món A', purine: 20))],
            budgetAfterRemoval: _budget(
              eaten: [_food(id: 'e', name: 'Đã ăn', sodium: 1500, purine: 300)],
            ),
          ),
        ),
      );
      expect(find.textContaining('Bỏ món cũ ra'), findsOneWidget);
      expect(find.textContaining('natri'), findsWidgets);
      expect(find.textContaining('purin'), findsWidgets);
      // A dish can be excellent on the nutrient that is short and still be
      // blocked by another, so ranking by one nutrient and concluding from
      // that is wrong.
      expect(find.textContaining('vừa cả hai'), findsOneWidget);
    });

    testWidgets('a misfit is still SHOWN, with its reason and "another day"', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: old,
            alternatives: [
              _option(_food(
                id: 'man', name: 'Món quá mặn', sodium: 5000, purine: 20)),
              _option(_food(
                id: 'ok', name: 'Món vừa', sodium: 50, purine: 20)),
            ],
            budgetAfterRemoval: _budget(),
          ),
        ),
      );
      // Hiding a misfit means the user never learns the dish they wanted is
      // selectable on another day.
      expect(find.text('Món quá mặn'), findsOneWidget);
      expect(find.textContaining('hôm khác chọn được'), findsOneWidget);
      expect(find.text('Món vừa'), findsOneWidget);
    });

    testWidgets('tapping a misfit does NOT close the sheet', (tester) async {
      _tall(tester);
      FoodBrief? picked;
      await tester.pumpWidget(
        _host(
          Builder(
            builder: (context) => ElevatedButton(
              onPressed: () async {
                picked = await ReplaceSheet.show(
                  context,
                  item: old,
                  alternatives: [
                    _option(_food(
                      id: 'man', name: 'Món quá mặn',
                      sodium: 5000, purine: 20)),
                  ],
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
        reason: 'the sheet stays open because that dish is unselectable '
            'today',
      );
      expect(picked, isNull);
    });

    testWidgets('a dish with missing data is NOT blocked, but is flagged', (
      tester,
    ) async {
      _tall(tester);
      await tester.pumpWidget(
        _host(
          ReplaceSheet(
            item: old,
            alternatives: [_option(_food(id: 'la', name: 'Chưa đo purin', sodium: 50))],
            budgetAfterRemoval: _budget(),
          ),
        ),
      );
      // Blocking because the catalogue is incomplete penalises the wrong
      // party; letting it through in silence loosens the allowance. So: let
      // it through, and say so.
      expect(find.text('Chưa đo purin'), findsOneWidget);
      expect(find.textContaining('Chưa có số liệu purin'), findsOneWidget);
    });
  });

  group('EvidenceLevel in the interface', () {
    testWidgets('an uncitable level has its own wording, not just colour', (
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
      // Colour by itself is unreadable to a colour-blind user, and this is
      // health information.
      expect(find.textContaining('suy ra kèm giả thiết'), findsOneWidget);
      expect(find.textContaining('cho người 60 kg'), findsOneWidget);
    });
  });
}
