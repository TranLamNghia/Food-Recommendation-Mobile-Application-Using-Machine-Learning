using System.ComponentModel.DataAnnotations;
using Api.Progress;

namespace Api.Tests;

/// <summary>
/// The arithmetic of §7.9.1 and the rules of §7.10.1's body. The endpoints
/// run against MySQL in <c>tools/smoke_backend.py</c>.
/// </summary>
public class ProgressTests
{
    private static readonly DateOnly Mon = new(2026, 11, 16);

    private static DateOnly D(int offset) => Mon.AddDays(offset);

    private static DayFacts Logged(
        decimal kcal, decimal target = 2000, int? suggested = 10,
        int hit = 5, int meals = 3)
        => new()
        {
            Consumed = kcal,
            Target = target,
            LoggedMeals = meals,
            Suggested = suggested,
            Hit = hit,
        };

    private static ProgressResponse Build(
        Dictionary<DateOnly, DayFacts> days, string groupBy = "day",
        DateOnly? from = null, DateOnly? to = null)
        => ProgressReport.Build(
            from ?? D(0), to ?? D(6), groupBy, days, [], feedbacks: 0);

    /// <summary>
    /// A day with a plan and no line is a day nobody wrote down. Counting it
    /// as 0 kcal would report a forgetful user as fasting.
    /// </summary>
    [Fact]
    public void Means_are_over_logged_days_only()
    {
        var report = Build(new()
        {
            [D(0)] = Logged(1800),
            [D(1)] = Logged(2200),
            [D(2)] = new DayFacts { Target = 2000, Suggested = 10, Hit = 0 },
        });

        Assert.Equal(2, report.Summary.DaysLogged);
        Assert.Equal(7, report.Summary.DaysInRange);
        Assert.Equal(2000m, report.Summary.AvgCaloriesConsumed);
        Assert.Equal(0m, report.Summary.AvgCalorieDeviationPct);
        // The unlogged day is still listed — it had a plan — with nothing
        // logged against it.
        var empty = report.Series.Single(p => p.Date == D(2));
        Assert.Equal(0, empty.LoggedMeals);
        Assert.Equal(0m, empty.CaloriesConsumed);
    }

    /// <summary>
    /// But its servings still count against compliance — they were
    /// suggested and not eaten, which is what §8.4 measures.
    /// </summary>
    [Fact]
    public void Compliance_is_pooled_over_servings()
    {
        var report = Build(new()
        {
            [D(0)] = Logged(2000, suggested: 2, hit: 2),     // 100 %
            [D(1)] = Logged(2000, suggested: 12, hit: 3),    //  25 %
        });

        // (2 + 3) / (2 + 12), not the mean of 100 % and 25 %.
        Assert.Equal(35.7m, report.Summary.AvgCompliancePct);
    }

    [Fact]
    public void A_day_without_a_plan_has_no_compliance()
    {
        var report = Build(new() { [D(0)] = Logged(2000, suggested: null) });

        Assert.Null(report.Series.Single().CompliancePct);
        Assert.Null(report.Summary.AvgCompliancePct);
    }

    [Fact]
    public void The_deviation_matches_the_specification_example()
    {
        // §7.9.1's sample: 2312.5 eaten on average against 2573 → −10.1 %.
        var report = Build(new()
        {
            [D(0)] = Logged(2312.5m, target: 2573),
        });

        Assert.Equal(-10.1m, report.Summary.AvgCalorieDeviationPct);
    }

    [Fact]
    public void Nothing_logged_gives_nulls_not_zeros()
    {
        var report = Build(new());

        Assert.Empty(report.Series);
        Assert.Equal(0, report.Summary.DaysLogged);
        Assert.Null(report.Summary.AvgCaloriesConsumed);
        Assert.Null(report.Summary.AvgCaloriesTarget);
        Assert.Null(report.Summary.AvgCalorieDeviationPct);
    }

    [Theory]
    [InlineData(0, 0)]   // Monday
    [InlineData(3, 0)]   // Thursday
    [InlineData(6, 0)]   // Sunday belongs to the week before it
    [InlineData(7, 7)]   // the next Monday
    public void Weeks_start_on_monday(int offset, int start)
        => Assert.Equal(D(start), ProgressReport.WeekStart(D(offset)));

    [Fact]
    public void A_week_pools_its_days_and_is_dated_inside_the_range()
    {
        // From a Wednesday: the first week is labelled with the Wednesday,
        // not a Monday outside what was asked.
        var report = Build(
            new()
            {
                [D(2)] = Logged(1800, suggested: 4, hit: 4, meals: 4),
                [D(4)] = Logged(2200, suggested: 4, hit: 0, meals: 2),
                [D(7)] = Logged(2000, meals: 1),
            },
            groupBy: "week", from: D(2), to: D(13));

        Assert.Equal([D(2), D(7)], report.Series.Select(p => p.Date));
        var first = report.Series[0];
        Assert.Equal(2000m, first.CaloriesConsumed);
        Assert.Equal(50m, first.CompliancePct);
        Assert.Equal(6, first.LoggedMeals);
    }

    [Fact]
    public void The_weight_trend_stays_inside_the_range_in_order()
    {
        var report = ProgressReport.Build(
            D(0), D(6), "day", new Dictionary<DateOnly, DayFacts>(),
            [
                new WeightPointDto { Date = D(5), WeightKg = 68.5m },
                new WeightPointDto { Date = D(-1), WeightKg = 70m },
                new WeightPointDto { Date = D(0), WeightKg = 69m },
            ],
            feedbacks: 0);

        Assert.Equal([D(0), D(5)], report.WeightTrend.Select(w => w.Date));
    }

    private static List<ValidationResult> Validate(object model)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(
            model, new ValidationContext(model), results,
            validateAllProperties: true);
        return results;
    }

    [Theory]
    [InlineData(19.99)]
    [InlineData(300.01)]
    public void A_weight_outside_the_schema_check_is_refused(double kg)
        => Assert.NotEmpty(Validate(new BodyLogRequest { WeightKg = (decimal)kg }));

    [Theory]
    [InlineData(20)]
    [InlineData(68.5)]
    [InlineData(300)]
    public void A_weight_inside_it_passes(double kg)
        => Assert.Empty(Validate(new BodyLogRequest { WeightKg = (decimal)kg }));

    [Fact]
    public void The_weight_is_required_and_the_note_capped()
    {
        Assert.NotEmpty(Validate(new BodyLogRequest()));
        Assert.NotEmpty(Validate(new BodyLogRequest
        {
            WeightKg = 68,
            Note = new string('a', 256),
        }));
    }
}
