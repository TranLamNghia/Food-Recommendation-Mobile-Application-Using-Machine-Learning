using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Nutrition;
using Api.Profile;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Progress;

/// <summary>
/// One weighing — specification §7.10.1.
///
/// <para><b>One row per day</b>, on <c>uq_user_day</c>: weighing again the
/// same day replaces the figure, so the trend is not a saw of water weight.</para>
///
/// <para><b>And the profile follows — but only from the latest day.</b>
/// §7.10.1 says a weighing updates <c>health_profiles.weight_kg</c> so the
/// energy target keeps up with the body. Taken literally, filling in last
/// month's forgotten entry would then set the CURRENT weight to last month's
/// and move tomorrow's target backwards. So the profile moves only when no
/// later weighing exists. Plans already built keep their own snapshot either
/// way, which is what "today's plan does not change" asks for.</para>
/// </summary>
[ApiController]
[Route("api/v1/body-logs")]
[Authorize]
public sealed class BodyLogController(AppDbContext db) : ControllerBase
{
    private string? UserId => User.FindFirst("sub")?.Value;

    [HttpPost]
    public async Task<IActionResult> Log(
        BodyLogRequest req, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return ApiProblem.Make(401, ErrorCode.TokenInvalid,
                                   "Token thiếu `sub`",
                                   HttpContext.TraceIdentifier);
        }

        var today = Clock.Today;
        var day = req.LoggedOn ?? today;
        if (day > today)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "loggedOn",
                    Message = "Không ghi cân nặng cho ngày chưa tới",
                }]);
        }

        // The BMI needs a height, and the profile is the only place that
        // has one. A body log with nothing to measure it against is not what
        // §7.10.1 answers with, so the app is sent to the profile form.
        var profile = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid, ct);
        if (profile is null)
        {
            return ApiProblem.Make(409, ErrorCode.ProfileRequired,
                                   "Chưa khai báo hồ sơ sức khỏe",
                                   HttpContext.TraceIdentifier);
        }

        var weight = Math.Round(
            req.WeightKg!.Value, 2, MidpointRounding.AwayFromZero);
        var note = string.IsNullOrWhiteSpace(req.Note) ? null : req.Note.Trim();

        await using var tx = await db.Database.BeginTransactionAsync(ct);

        var (row, created) = await WeightHistory.WriteAsync(
            db, uid, day, weight, note, keepNote: false, ct);
        var updated = await WeightHistory.FollowAsync(
            db, profile, day, weight, today, ct);

        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);

        var bmi = Math.Round(
            NutritionTargets.Bmi(weight, profile.HeightCm), 2,
            MidpointRounding.AwayFromZero);
        var body = new BodyLogResponse
        {
            Id = row.Id,
            LoggedOn = row.LoggedOn,
            WeightKg = row.WeightKg,
            Bmi = bmi,
            BmiCategory = NutritionTargets.BmiCategory(bmi),
            Note = row.Note,
            ProfileUpdated = updated,
        };
        return created ? StatusCode(StatusCodes.Status201Created, body) : Ok(body);
    }
}

/// <summary>
/// Writing <c>body_logs</c>, shared by §7.10.1 and by the profile form,
/// whose weight is a weighing too.
/// </summary>
public static class WeightHistory
{
    /// <summary>
    /// Inserts the day's row or replaces its figure. Changes are tracked,
    /// not saved — the caller saves inside its own transaction.
    /// </summary>
    /// <param name="keepNote">
    /// The profile form has no note field; it must not wipe the note the
    /// user wrote with that morning's weighing.
    /// </param>
    public static async Task<(BodyLogs Row, bool Created)> WriteAsync(
        AppDbContext db, string uid, DateOnly day, decimal weight,
        string? note, bool keepNote, CancellationToken ct)
    {
        var row = await db.BodyLogs.FirstOrDefaultAsync(
            b => b.UserId == uid && b.LoggedOn == day, ct);
        if (row is null)
        {
            row = new BodyLogs
            {
                Id = Guid.NewGuid().ToString(),
                UserId = uid,
                LoggedOn = day,
                WeightKg = weight,
                Note = note,
                CreatedAt = Clock.Now,
            };
            db.BodyLogs.Add(row);
            return (row, true);
        }

        row.WeightKg = weight;
        if (!keepNote) row.Note = note;
        return (row, false);
    }

    /// <summary>
    /// Makes <paramref name="weight"/> the profile's current weight, and
    /// recomputes Step 1 from it, when <paramref name="day"/> is the latest
    /// weighing. Returns whether it did.
    /// </summary>
    public static async Task<bool> FollowAsync(
        AppDbContext db, HealthProfiles profile, DateOnly day, decimal weight,
        DateOnly today, CancellationToken ct)
    {
        var later = await db.BodyLogs.AnyAsync(
            b => b.UserId == profile.UserId && b.LoggedOn > day, ct);
        if (later) return false;

        profile.WeightKg = weight;
        profile.UpdatedAt = Clock.Now;
        var step1 = ProfileController.ComputeStep1(profile, today);
        profile.BmrKcal = ProfileController.Round(step1.BmrKcal);
        profile.TdeeKcal = ProfileController.Round(step1.TdeeKcal);
        profile.DailyCaloriesTarget =
            ProfileController.Round(step1.DailyCaloriesTarget);
        return true;
    }
}
