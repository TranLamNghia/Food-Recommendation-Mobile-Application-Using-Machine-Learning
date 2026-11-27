using System.ComponentModel.DataAnnotations;

namespace Api.Progress;

// ── 7.10.1 Log a weight ──────────────────────────────────────────────────

public sealed class BodyLogRequest
{
    /// <summary>Today when left out. A future day is refused.</summary>
    public DateOnly? LoggedOn { get; init; }

    /// <summary>
    /// The same 20–300 as <c>chk_log_weight</c>. Compared as a decimal: the
    /// <c>int</c> overload converts the value first, and 19.99 becomes 20.
    /// </summary>
    [Required(ErrorMessage = "Thiếu cân nặng")]
    [Range(typeof(decimal), "20", "300",
           ParseLimitsInInvariantCulture = true,
           ConvertValueInInvariantCulture = true,
           ErrorMessage = "Cân nặng phải trong khoảng 20 đến 300 kg")]
    public decimal? WeightKg { get; init; }

    [MaxLength(255, ErrorMessage = "Ghi chú tối đa 255 ký tự")]
    public string? Note { get; init; }
}

public sealed class BodyLogResponse
{
    public string Id { get; init; } = string.Empty;
    public DateOnly LoggedOn { get; init; }
    public decimal WeightKg { get; init; }

    /// <summary>
    /// The BMI of THIS weight at the profile's height — not the profile's
    /// own BMI, which a back-dated entry does not change.
    /// </summary>
    public decimal Bmi { get; init; }

    public string BmiCategory { get; init; } = string.Empty;
    public string? Note { get; init; }

    /// <summary>
    /// Whether this entry became the profile's current weight, and so moved
    /// the energy target from tomorrow on. <c>false</c> for a day older than
    /// the latest weighing.
    /// </summary>
    public bool ProfileUpdated { get; init; }
}

// ── 7.9.1 Progress over a range ──────────────────────────────────────────

public sealed class ProgressResponse
{
    public DateOnly From { get; init; }
    public DateOnly To { get; init; }
    public string GroupBy { get; init; } = "day";
    public List<ProgressPointDto> Series { get; init; } = [];
    public ProgressSummaryDto Summary { get; init; } = new();
    public List<WeightPointDto> WeightTrend { get; init; } = [];
}

/// <summary>
/// One day, or one week with <c>groupBy=week</c>. Only the days that have a
/// plan or a diary line are listed — and never one after today.
/// </summary>
public sealed class ProgressPointDto
{
    /// <summary>The day; for a week, its first day inside the range.</summary>
    public DateOnly Date { get; init; }

    /// <summary>
    /// For a week, the mean over its LOGGED days. <c>0</c> with
    /// <see cref="LoggedMeals"/> <c>0</c> means nothing was logged, not that
    /// nothing was eaten.
    /// </summary>
    public decimal CaloriesConsumed { get; init; }

    /// <summary>
    /// The day's plan's snapshot when it has one, else the profile's stored
    /// target — the same rule as §7.7.5, so both screens show one figure for
    /// one day. <c>null</c> when neither exists.
    /// </summary>
    public decimal? CaloriesTarget { get; init; }

    /// <summary>
    /// Servings of the plan that have a diary line on the natural key.
    /// <c>null</c> without a plan. For a week, pooled over the servings, not
    /// a mean of daily percentages.
    /// </summary>
    public decimal? CompliancePct { get; init; }

    /// <summary>Meals (of four) with at least one line; summed for a week.</summary>
    public int LoggedMeals { get; init; }
}

public sealed class ProgressSummaryDto
{
    public int DaysLogged { get; init; }
    public int DaysInRange { get; init; }

    /// <summary>Means over the logged days only; <c>null</c> if none.</summary>
    public decimal? AvgCaloriesConsumed { get; init; }

    public decimal? AvgCaloriesTarget { get; init; }

    /// <summary>Pooled over every planned serving up to today.</summary>
    public decimal? AvgCompliancePct { get; init; }

    /// <summary>
    /// <c>100 × (avgConsumed − avgTarget) / avgTarget</c>, over the logged
    /// days that have a target.
    /// </summary>
    public decimal? AvgCalorieDeviationPct { get; init; }

    public int TotalFeedbacks { get; init; }
}

public sealed class WeightPointDto
{
    public DateOnly Date { get; init; }
    public decimal WeightKg { get; init; }
}
