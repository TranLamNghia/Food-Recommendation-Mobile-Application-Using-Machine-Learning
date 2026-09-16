import 'package:flutter/material.dart';

import '../../core/theme/app_motion.dart';
import '../../data/models/food.dart';
import '../../data/models/swipe_action.dart';
import '../../data/session.dart';
import 'survey_result_screen.dart';
import 'widgets/survey_footer.dart';
import 'widgets/swipe_burst.dart';
import 'widgets/swipe_deck.dart';

/// Một lượt vuốt đã ghi nhận.
typedef SwipeResult = ({Food food, SwipeAction action});

/// Màn hình khảo sát khẩu vị — chạy đúng một lần, ngay sau khi người dùng
/// khai báo hồ sơ sức khỏe.
///
/// Toàn bộ kết quả được giữ trong bộ nhớ và chỉ gửi lên máy chủ **một lần
/// duy nhất** khi vuốt xong (đặc tả API mục 7.4). Vì vậy màn hình này tự
/// đếm tiến độ, không hỏi máy chủ sau mỗi lượt vuốt, và vuốt được cả khi
/// mất mạng.
class SurveyScreen extends StatefulWidget {
  const SurveyScreen({super.key, required this.foods});

  final List<Food> foods;

  @override
  State<SurveyScreen> createState() => _SurveyScreenState();
}

class _SurveyScreenState extends State<SurveyScreen> {
  final _deck = SwipeDeckController();
  final List<SwipeResult> _results = [];

  int _cursor = 0;

  /// Vùng chồng thẻ chiếm 581 trên 844 chiều cao khung thiết kế.
  static const _deckRatio = 581 / 844;

  bool get _isDone => _cursor >= widget.foods.length;

  @override
  void dispose() {
    _deck.dispose();
    super.dispose();
  }

  void _handleSwipe(Food food, SwipeAction action) {
    setState(() {
      _results.add((food: food, action: action));
      _cursor++;
    });

    if (_isDone) _finish();
  }

  void _finish() {
    // Nộp trọn gói kết quả một lần, đúng như thiết kế phiên vuốt: ứng dụng
    // giữ toàn bộ lượt vuốt trong bộ nhớ rồi gửi một lượt duy nhất.
    SessionScope.of(context).completeSurvey(_results);

    // Chờ thẻ cuối bay hết ra ngoài rồi mới chuyển màn, tránh cắt ngang
    // chuyển động đang chạy.
    Future.delayed(AppMotion.quick, () {
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        PageRouteBuilder(
          transitionDuration: AppMotion.page,
          pageBuilder: (_, _, _) => SurveyResultScreen(results: _results),
          transitionsBuilder: (_, animation, _, child) => FadeTransition(
            opacity: animation,
            child: SlideTransition(
              position: Tween(begin: const Offset(0, 0.06), end: Offset.zero)
                  .animate(
                    CurvedAnimation(
                      parent: animation,
                      curve: AppMotion.emphasized,
                    ),
                  ),
              child: child,
            ),
          ),
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final height = MediaQuery.sizeOf(context).height;

    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        children: [
          // Vùng chồng thẻ — khung `Card` (5:32) chiếm 581 trên 844 chiều cao.
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            height: height * _deckRatio,
            // Cắt theo vùng này để thẻ đang bay ra trượt xuống dưới vùng chân
            // màn hình thay vì đè lên, và để hạt không tràn ra ngoài.
            child: ClipRect(
              child: Stack(
                children: [
                  // Hạt bay nằm dưới chồng thẻ để thẻ luôn nổi lên trên.
                  Positioned.fill(child: SwipeBurst(signal: _deck.signal)),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: _isDone
                        ? const SizedBox.shrink()
                        : SwipeDeck(
                            foods: widget.foods,
                            cursor: _cursor,
                            controller: _deck,
                            onSwipe: _handleSwipe,
                          ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: height * SurveyFooter.heightRatio,
            child: SurveyFooter(done: _cursor, total: widget.foods.length),
          ),
        ],
      ),
    );
  }
}
