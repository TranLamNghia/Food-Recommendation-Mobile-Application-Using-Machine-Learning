namespace Api.Progress;

/// <summary>What one calendar day contributes to §7.9.1.</summary>
public sealed record DayFacts
{
    public decimal Consumed { get; init; }

    /// <summary>Distinct meals with a diary line.</summary>
    public int LoggedMeals { get; init; }

    public decimal? Target { get; init; }

    /// <summary><c>null</c> when the day has no plan.</summary>
    public int? Suggested { get; init; }

    public int Hit { get; init; }

    public bool Logged => LoggedMeals > 0;
}

/// <summary>
/// The arithmetic of §7.9.1, apart from the database so it can be tested
/// on its own.
///
/// <para><b>Means are over logged days.</b> A day with a plan and no diary
/// line is a day nobody wrote down, not a day of fasting; averaging it in as
/// 0 kcal would report every forgetful user as starving.</para>
///
/// <para><b>Compliance is pooled</b> — eaten servings over suggested
/// servings, as §8.4 computes it — rather than a mean of daily percentages,
/// which would weigh a day with two suggestions like a day with twelve.</para>
/// </summary>
public static class ProgressReport
{
    public static ProgressResponse Build(
        DateOnly from,
        DateOnly to,
        string groupBy,
        IReadOnlyDictionary<DateOnly, DayFacts> days,
        IReadOnlyList<WeightPointDto> weights,
        int feedbacks)
    {
        var ordered = days
            .Where(d => d.Key >= from && d.Key <= to)
            .OrderBy(d => d.Key)
            .ToList();

        var series = groupBy == "week"
            ? ordered
                .GroupBy(d => WeekStart(d.Key))
                .Select(w => Point(
                    w.Key < from ? from : w.Key,
                    w.Select(d => d.Value).ToList()))
                .ToList()
            : ordered.Select(d => Point(d.Key, [d.Value])).ToList();

        var all = ordered.Select(d => d.Value).ToList();
        var logged = all.Where(d => d.Logged).ToList();
        var targeted = logged.Where(d => d.Target is not null).ToList();

        decimal? avgConsumed = logged.Count == 0
            ? null
            : Round1(logged.Average(d => d.Consumed));
        decimal? avgTarget = targeted.Count == 0
            ? null
            : Round1(targeted.Average(d => d.Target!.Value));

        // From the same logged-and-targeted days on both sides, so a day with
        // no target cannot pull one mean without the other.
        decimal? deviation = null;
        if (targeted.Count > 0)
        {
            var eaten = targeted.Average(d => d.Consumed);
            var target = targeted.Average(d => d.Target!.Value);
            if (target > 0)
            {
                deviation = Round1(100m * (eaten - target) / target);
            }
        }

        return new ProgressResponse
        {
            From = from,
            To = to,
            GroupBy = groupBy,
            Series = series,
            Summary = new ProgressSummaryDto
            {
                DaysLogged = logged.Count,
                DaysInRange = to.DayNumber - from.DayNumber + 1,
                AvgCaloriesConsumed = avgConsumed,
                AvgCaloriesTarget = avgTarget,
                AvgCompliancePct = Pooled(all),
                AvgCalorieDeviationPct = deviation,
                TotalFeedbacks = feedbacks,
            },
            WeightTrend = weights
                .Where(w => w.Date >= from && w.Date <= to)
                .OrderBy(w => w.Date)
                .ToList(),
        };
    }

    /// <summary>The Monday of <paramref name="day"/>'s ISO week.</summary>
    public static DateOnly WeekStart(DateOnly day)
        => day.AddDays(-(((int)day.DayOfWeek + 6) % 7));

    private static ProgressPointDto Point(DateOnly date, List<DayFacts> days)
    {
        var logged = days.Where(d => d.Logged).ToList();
        var targets = (logged.Count > 0 ? logged : days)
            .Where(d => d.Target is not null)
            .Select(d => d.Target!.Value)
            .ToList();

        return new ProgressPointDto
        {
            Date = date,
            CaloriesConsumed = logged.Count == 0
                ? 0m
                : Round1(logged.Average(d => d.Consumed)),
            CaloriesTarget = targets.Count == 0
                ? null
                : Round1(targets.Average()),
            CompliancePct = Pooled(days),
            LoggedMeals = days.Sum(d => d.LoggedMeals),
        };
    }

    private static decimal? Pooled(IEnumerable<DayFacts> days)
    {
        var planned = days.Where(d => d.Suggested is > 0).ToList();
        if (planned.Count == 0) return null;
        var suggested = planned.Sum(d => d.Suggested!.Value);
        return Round1(100m * planned.Sum(d => d.Hit) / suggested);
    }

    private static decimal Round1(decimal v)
        => Math.Round(v, 1, MidpointRounding.AwayFromZero);
}
