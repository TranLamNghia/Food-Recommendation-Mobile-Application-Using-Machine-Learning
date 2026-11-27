using Api.Data;
using Api.Http;
using Api.Planning;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Progress;

/// <summary>
/// Health progress over a range of days — specification §7.9.1.
///
/// <para>Every figure here is read from what is already stored —
/// <c>food_diary</c>, the plans' target snapshots, <c>body_logs</c> — and
/// none is recomputed from the body as it is today: last month's target was
/// the one taken when last month's plans were built.</para>
/// </summary>
[ApiController]
[Route("api/v1/stats")]
[Authorize]
public sealed class StatsController(AppDbContext db) : ControllerBase
{
    /// <summary>§7.9.1's ceiling: <c>to</c> at most 365 days after <c>from</c>.</summary>
    public const int MaxRangeDays = 365;

    private string? UserId => User.FindFirst("sub")?.Value;

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    [HttpGet("progress")]
    public async Task<IActionResult> Progress(
        [FromQuery] DateOnly? from,
        [FromQuery] DateOnly? to,
        [FromQuery] string? groupBy,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return ApiProblem.Make(401, ErrorCode.TokenInvalid,
                                   "Token thiếu `sub`",
                                   HttpContext.TraceIdentifier);
        }
        if (from is not { } start) return Invalid("from", "Thiếu ngày bắt đầu");
        if (to is not { } end) return Invalid("to", "Thiếu ngày kết thúc");
        if (end < start)
        {
            return Invalid("to", "Ngày kết thúc phải từ ngày bắt đầu trở đi");
        }
        if (end.DayNumber - start.DayNumber > MaxRangeDays)
        {
            return Invalid("to", $"Khoảng xem tối đa {MaxRangeDays} ngày");
        }
        var grouping = groupBy ?? "day";
        if (grouping is not ("day" or "week"))
        {
            return Invalid("groupBy", "groupBy phải là day hoặc week");
        }

        // Nothing after today is a day that happened. A plan already built
        // for tomorrow would otherwise count as a day of zero compliance.
        var today = Clock.Today;
        var last = end < today ? end : today;

        var profile = await db.HealthProfiles
            .Where(h => h.UserId == uid)
            .Select(h => new { h.DailyCaloriesTarget })
            .FirstOrDefaultAsync(ct);

        var plans = await db.MealPlans
            .Where(p => p.UserId == uid
                        && p.PlanDate >= start && p.PlanDate <= last)
            .Select(p => new { p.Id, p.PlanDate, p.TargetCaloriesKcal })
            .ToListAsync(ct);
        var planIds = plans.Select(p => p.Id).ToList();
        var items = await db.MealPlanItems
            .Where(i => planIds.Contains(i.MealPlanId))
            .Select(i => new { i.MealPlanId, i.MealType, i.FoodId })
            .ToListAsync(ct);

        var diary = await db.FoodDiary
            .Where(d => d.UserId == uid
                        && d.AteOn >= start && d.AteOn <= last)
            .Select(d => new
            {
                d.AteOn, d.MealType, d.FoodId, d.PortionMultiplier,
            })
            .ToListAsync(ct);
        var nutrition = await MealPlanMapper.NutritionByFood(
            db, diary.Select(d => d.FoodId).Distinct().ToList(), ct);

        var planByDay = plans.ToDictionary(p => p.PlanDate);
        var itemsByPlan = items.ToLookup(i => i.MealPlanId);
        var diaryByDay = diary.ToLookup(d => d.AteOn);

        var facts = new Dictionary<DateOnly, DayFacts>();
        foreach (var day in planByDay.Keys.Union(diaryByDay.Select(g => g.Key)))
        {
            var lines = diaryByDay[day].ToList();
            planByDay.TryGetValue(day, out var plan);
            var eaten = lines.Select(l => (l.MealType, l.FoodId)).ToHashSet();
            var suggested = plan is null ? null : itemsByPlan[plan.Id].ToList();

            facts[day] = new DayFacts
            {
                // A food with no nutrition row adds nothing, the rule
                // §7.7.1's day total already follows.
                Consumed = lines.Sum(l =>
                    nutrition.TryGetValue(l.FoodId, out var n)
                        ? n.CaloriesKcal * l.PortionMultiplier
                        : 0m),
                LoggedMeals = lines.Select(l => l.MealType).Distinct().Count(),
                Target = plan?.TargetCaloriesKcal
                         ?? (decimal?)profile?.DailyCaloriesTarget,
                Suggested = suggested?.Count,
                Hit = suggested?.Count(
                    i => eaten.Contains((i.MealType, i.FoodId))) ?? 0,
            };
        }

        var weights = await db.BodyLogs
            .Where(b => b.UserId == uid
                        && b.LoggedOn >= start && b.LoggedOn <= end)
            .OrderBy(b => b.LoggedOn)
            .Select(b => new WeightPointDto
            {
                Date = b.LoggedOn,
                WeightKg = b.WeightKg,
            })
            .ToListAsync(ct);

        var since = start.ToDateTime(TimeOnly.MinValue);
        var until = end.AddDays(1).ToDateTime(TimeOnly.MinValue);
        var feedbacks = await db.Feedbacks.CountAsync(
            f => f.UserId == uid && f.CreatedAt >= since && f.CreatedAt < until,
            ct);

        return Ok(ProgressReport.Build(
            start, end, grouping, facts, weights, feedbacks));
    }
}
