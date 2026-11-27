part of 'progress_screen.dart';

/// The weight over the period, and the button to record today's.
///
/// §7.10.1 keeps one weighing a day, so the line has at most one point per
/// day and the morning-to-evening swing of water weight never reads as a
/// trend.
class _WeightCard extends StatelessWidget {
  const _WeightCard({
    required this.profile,
    required this.trend,
    required this.onLog,
  });

  final HealthProfile profile;

  /// `null` while the report loads.
  final List<WeightPoint>? trend;

  final VoidCallback onLog;

  @override
  Widget build(BuildContext context) {
    final current = profile.weightKg;
    final target = profile.targetWeightKg;
    final points = trend ?? const <WeightPoint>[];
    final change = points.length < 2
        ? null
        : points.last.weightKg - points.first.weightKg;

    return _Card(
      title: 'Cân nặng',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              // Shrinks under a large font scale, like the BMI figure.
              Flexible(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    current == null ? '—' : formatNumber(current, 1),
                    style: const TextStyle(
                      fontSize: 36,
                      height: 1,
                      color: AppColors.textPrimary,
                      fontVariations: [FontVariation('wght', 700)],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              const Text(
                'kg',
                style: TextStyle(
                  fontSize: 14,
                  color: AppColors.textSecondary,
                  fontVariations: [FontVariation('wght', 600)],
                ),
              ),
              const Spacer(),
              if (change != null)
                Text(
                  '${change > 0
                      ? '+'
                      : change < 0
                      ? '−'
                      : '±'}'
                  '${formatNumber(change.abs(), 1)} kg',
                  style: const TextStyle(
                    fontSize: 13.5,
                    color: AppColors.textSecondary,
                    fontVariations: [FontVariation('wght', 700)],
                  ),
                ),
            ],
          ),
          if (target != null) ...[
            const SizedBox(height: 6),
            Text(
              'Mục tiêu ${formatNumber(target, 1)} kg',
              style: const TextStyle(
                fontSize: 12.5,
                color: AppColors.textTertiary,
              ),
            ),
          ],
          const SizedBox(height: 16),
          SizedBox(
            height: 64,
            child: points.length < 2
                ? Center(
                    child: Text(
                      trend == null
                          ? 'Đang tải…'
                          : 'Ghi cân nặng vài ngày để thấy đường xu hướng.',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 12.5,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  )
                : CustomPaint(
                    size: Size.infinite,
                    painter: _TrendPainter(points),
                  ),
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onLog,
              icon: const Icon(Icons.monitor_weight_outlined, size: 18),
              label: const Text('Ghi cân nặng'),
            ),
          ),
        ],
      ),
    );
  }
}

/// A plain line through the weighings, spaced by date rather than by index
/// so a week without weighing shows as a gap, not as a steep step.
class _TrendPainter extends CustomPainter {
  _TrendPainter(this.points);

  final List<WeightPoint> points;

  @override
  void paint(Canvas canvas, Size size) {
    final first = points.first.date;
    final span = math.max(1, points.last.date.difference(first).inDays);
    final weights = points.map((p) => p.weightKg);
    var low = weights.reduce(math.min);
    var high = weights.reduce(math.max);
    // A flat line in the middle rather than a division by zero.
    if (high - low < 0.5) {
      low -= 0.25;
      high += 0.25;
    }

    Offset at(WeightPoint p) => Offset(
      size.width * p.date.difference(first).inDays / span,
      4 + (size.height - 8) * (1 - (p.weightKg - low) / (high - low)),
    );

    final path = Path()..moveTo(at(points.first).dx, at(points.first).dy);
    for (final p in points.skip(1)) {
      path.lineTo(at(p).dx, at(p).dy);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = AppColors.accentInk
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round,
    );
    final dot = Paint()..color = AppColors.accentInk;
    for (final p in points) {
      canvas.drawCircle(at(p), 3, dot);
    }
  }

  @override
  bool shouldRepaint(_TrendPainter old) => old.points != points;
}

/// Energy eaten against the target, over the chosen period.
class _EnergyCard extends StatelessWidget {
  const _EnergyCard({
    required this.report,
    required this.days,
    required this.onDays,
    required this.failure,
    required this.onRetry,
  });

  final ProgressReport? report;
  final int days;
  final ValueChanged<int> onDays;
  final String? failure;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final r = report;

    return _Card(
      title: 'Năng lượng đã ăn',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SegmentedButton<int>(
            segments: const [
              ButtonSegment(value: 7, label: Text('7 ngày')),
              ButtonSegment(value: 30, label: Text('30 ngày')),
            ],
            selected: {days},
            showSelectedIcon: false,
            onSelectionChanged: (s) => onDays(s.first),
          ),
          const SizedBox(height: 16),
          if (failure != null)
            Row(
              children: [
                Expanded(
                  child: Text(
                    failure!,
                    style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
                TextButton(onPressed: onRetry, child: const Text('Thử lại')),
              ],
            )
          else if (r == null)
            const SizedBox(
              height: 80,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (r.summary.daysLogged == 0)
            const Text(
              'Chưa có ngày nào được ghi nhật ký trong khoảng này.',
              style: TextStyle(fontSize: 13.5, color: AppColors.textSecondary),
            )
          else ...[
            SizedBox(height: 92, child: _Bars(report: r)),
            const SizedBox(height: 6),
            const Text(
              'Cột là phần đã ăn, vạch ngang là hạn mức của ngày đó. Ngày '
              'không ghi nhật ký để trống chứ không tính là 0.',
              style: TextStyle(fontSize: 11.5, color: AppColors.textTertiary),
            ),
            const Divider(height: 26),
            _Row(
              label: 'Trung bình mỗi ngày ghi',
              value: _kcal(r.summary.avgConsumedKcal),
            ),
            const SizedBox(height: 10),
            _Row(
              label: 'Hạn mức trung bình',
              value: _kcal(r.summary.avgTargetKcal),
            ),
            const SizedBox(height: 10),
            _Row(
              label: 'Lệch so với hạn mức',
              value: _pct(r.summary.avgDeviationPct, signed: true),
              emphasize: true,
            ),
            const SizedBox(height: 10),
            _Row(
              label: 'Tuân thủ thực đơn',
              value: _pct(r.summary.avgCompliancePct),
            ),
            const SizedBox(height: 10),
            _Row(
              label: 'Số ngày đã ghi',
              value: '${r.summary.daysLogged}/${r.summary.daysInRange}',
            ),
          ],
        ],
      ),
    );
  }

  static String _kcal(double? v) => v == null ? '—' : '${formatNumber(v)} kcal';

  static String _pct(double? v, {bool signed = false}) {
    if (v == null) return '—';
    final sign = !signed || v == 0 ? '' : (v > 0 ? '+' : '−');
    return '$sign${formatNumber(signed ? v.abs() : v, 1)}%';
  }
}

/// One slot per day of the range, so the bars line up with the calendar
/// and a day not logged is visibly a gap.
class _Bars extends StatelessWidget {
  const _Bars({required this.report});

  final ProgressReport report;

  @override
  Widget build(BuildContext context) {
    final byDay = {
      for (final p in report.series)
        DateTime(p.date.year, p.date.month, p.date.day): p,
    };
    final days = report.to.difference(report.from).inDays + 1;
    final peak = report.series
        .expand((p) => [p.consumedKcal, p.targetKcal ?? 0])
        .fold<double>(1, math.max);

    return LayoutBuilder(
      builder: (context, box) {
        final slot = box.maxWidth / days;
        return Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < days; i++)
              SizedBox(
                width: slot,
                height: box.maxHeight,
                child: _bar(
                  byDay[DateTime(
                    report.from.year,
                    report.from.month,
                    report.from.day + i,
                  )],
                  peak,
                  box.maxHeight,
                  slot,
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _bar(ProgressPoint? p, double peak, double height, double slot) {
    if (p == null || !p.logged) return const SizedBox.shrink();
    final target = p.targetKcal;
    final over = target != null && p.consumedKcal > target * 1.1;
    return Stack(
      alignment: Alignment.bottomCenter,
      children: [
        Container(
          width: math.max(2, slot * 0.6),
          height: height * p.consumedKcal / peak,
          decoration: BoxDecoration(
            color: over ? AppColors.kcal : AppColors.accentInk,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        if (target != null)
          Positioned(
            bottom: height * target / peak,
            child: Container(
              width: math.max(4, slot * 0.9),
              height: 2,
              color: AppColors.textPrimary,
            ),
          ),
      ],
    );
  }
}

/// The sheet that records one weighing.
class _WeighInSheet extends StatefulWidget {
  const _WeighInSheet({this.initial});

  final double? initial;

  @override
  State<_WeighInSheet> createState() => _WeighInSheetState();
}

class _WeighInSheetState extends State<_WeighInSheet> {
  final _form = GlobalKey<FormState>();
  late final _kg = TextEditingController(
    text: widget.initial == null ? '' : formatNumber(widget.initial!, 1),
  );
  DateTime _day = DateTime.now();
  bool _busy = false;
  String? _serverError;

  @override
  void dispose() {
    _kg.dispose();
    super.dispose();
  }

  static double? _parse(String raw) =>
      double.tryParse(raw.trim().replaceAll(',', '.'));

  Future<void> _pickDay() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: now.subtract(const Duration(days: 365)),
      // §7.10.1 refuses a day that has not come yet.
      lastDate: now,
    );
    if (picked != null) setState(() => _day = picked);
  }

  Future<void> _save() async {
    setState(() => _serverError = null);
    if (!_form.currentState!.validate()) return;
    final session = SessionScope.of(context);
    final navigator = Navigator.of(context);
    setState(() => _busy = true);
    try {
      final current = await session.logWeight(_parse(_kg.text)!, on: _day);
      navigator.pop(current);
    } on ApiFailure catch (failure) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _serverError =
            failure.forField('weightKg') ??
            failure.forField('loggedOn') ??
            failure.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final isToday =
        _day.year == now.year && _day.month == now.month && _day.day == now.day;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        24,
        20,
        24,
        24 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Form(
        key: _form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Ghi cân nặng', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            const Text(
              'Mỗi ngày giữ một lần cân, ghi lại thì thay số cũ. Nên cân '
              'vào cùng một giờ, tốt nhất là buổi sáng.',
              style: TextStyle(fontSize: 13, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 18),
            TextFormField(
              controller: _kg,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: 'Cân nặng',
                suffixText: 'kg',
                errorText: _serverError,
              ),
              validator: (v) {
                final kg = _parse(v ?? '');
                if (kg == null) return 'Nhập cân nặng, ví dụ 68,5';
                if (kg < 20 || kg > 300) return 'Từ 20 đến 300 kg';
                return null;
              },
              onFieldSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _pickDay,
                icon: const Icon(Icons.event_outlined, size: 18),
                label: Text(
                  isToday
                      ? 'Hôm nay'
                      : 'Ngày ${_day.day}/${_day.month}/${_day.year}',
                ),
              ),
            ),
            if (!isToday)
              const Text(
                'Ghi bù một ngày đã qua chỉ thêm vào đường xu hướng; cân '
                'nặng hiện tại giữ nguyên nếu đã có lần cân mới hơn.',
                style: TextStyle(fontSize: 12, color: AppColors.textTertiary),
              ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy ? null : _save,
              child: Text(_busy ? 'Đang lưu…' : 'Lưu'),
            ),
          ],
        ),
      ),
    );
  }
}
