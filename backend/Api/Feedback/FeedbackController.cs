using Api.Catalogue;
using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Planning;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Feedback;

/// <summary>
/// Star ratings — specification §7.8.
///
/// <para>This is the most trustworthy signal the system has, sample weight
/// <b>1.0</b> in §4.6, and the two conditions of §7.8.1 are what earns that
/// weight. A rating is only accepted for a dish that <b>was in one of the
/// user's own plans</b> and <b>is in their diary</b>: the first stops a user
/// scrolling the catalogue and starring food the system never suggested, the
/// second stops them starring a dish they skipped or swapped away. Without
/// both, the strongest label in the training set would be the one the user
/// had least reason to mean.</para>
///
/// <para><b>Rating the same dish again is allowed.</b> There is no unique key
/// on <c>(user_id, food_id)</c> and this writes a new row every time, because
/// taste changes: five stars today and two stars in three months are two
/// facts, not a correction. <c>ml/build_dataset.py</c> takes the latest
/// rating as of the dataset cut-off, so the newest one wins without the older
/// one being destroyed.</para>
/// </summary>
[ApiController]
[Route("api/v1/feedbacks")]
[Authorize]
public sealed class FeedbackController(
    AppDbContext db,
    IMlClient ml,
    ILogger<FeedbackController> log) : ControllerBase
{
    public const int DefaultPageSize = 20;
    public const int MaxPageSize = 100;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.8.1 Send a rating ──────────────────────────────────────────────

    [HttpPost]
    public async Task<IActionResult> Create(
        CreateFeedbackRequest req,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var foodId = req.FoodId!;
        var food = await db.Foods
            .Where(f => f.Id == foodId)
            .Select(f => new { f.Id, f.Name })
            .FirstOrDefaultAsync(ct);
        if (food is null)
        {
            return Fail(404, ErrorCode.NotFound, "Không tìm thấy món ăn");
        }

        // ① the dish was suggested to this user at some point. Any status
        // counts, including `replaced` and `skipped`: the system did put it
        // in front of them, and condition ② is what decides whether they
        // went on to eat it.
        var wasSuggested = await db.MealPlanItems
            .Join(db.MealPlans, i => i.MealPlanId, p => p.Id,
                  (i, p) => new { Item = i, Plan = p })
            .AnyAsync(
                x => x.Plan.UserId == uid && x.Item.FoodId == foodId, ct);

        // ② and they ate it. Any day — a rating is an opinion about the
        // dish, not about one sitting, which is why `feedbacks` has neither
        // a diary id nor a date of its own.
        var wasEaten = await db.FoodDiary.AnyAsync(
            d => d.UserId == uid && d.FoodId == foodId, ct);

        if (!wasSuggested || !wasEaten)
        {
            // One message for both halves, as §7.8.1 writes it. Telling the
            // user which half failed would describe the mechanism rather
            // than what to do, and the app is meant to have hidden the
            // button in the first place.
            log.LogInformation(
                "Rating refused for {User} on {Food}: suggested={Suggested}, "
                + "eaten={Eaten}.",
                uid, foodId, wasSuggested, wasEaten);
            return Fail(
                409, ErrorCode.FeedbackNotAllowed,
                "Chỉ được đánh giá món đã có trong thực đơn và đã ghi vào "
                + "nhật ký ăn uống");
        }

        var entry = new Feedbacks
        {
            Id = Guid.NewGuid().ToString(),
            UserId = uid,
            FoodId = foodId,
            Rating = (byte)req.Rating!.Value,
            // An empty comment is stored as NULL, not as "". The column is
            // nullable precisely so that "said nothing" and "said nothing in
            // particular" are not the same row.
            Comment = string.IsNullOrWhiteSpace(req.Comment)
                ? null
                : req.Comment.Trim(),
            CreatedAt = Clock.Now,
        };
        db.Feedbacks.Add(entry);
        await db.SaveChangesAsync(ct);

        // Saved first, rebuilt second, and the rebuild is allowed to fail.
        // The ML service reads the row over its own connection, so it has to
        // be committed before the call — and a rating is the user's, not the
        // model's: losing it because a service was down would be the wrong
        // way round. `profileUpdated` reports what actually happened.
        var rebuilt = await ml.RebuildProfileAsync(uid, ct);
        if (!rebuilt.Ok)
        {
            log.LogWarning(
                "Rating {Id} by {User} on {Food} is stored, but the "
                + "preference vector was not rebuilt, so the next plan uses "
                + "the vector as it was. {Detail}",
                entry.Id, uid, foodId, rebuilt.Failure!.Detail);
        }
        else
        {
            log.LogInformation(
                "Rating {Id}: {Stars} star(s) on {Food} by {User}. Vector "
                + "rebuilt from {Signals} signals, stage {Stage}. Label "
                + "weight 1.0 in §4.6.",
                entry.Id, entry.Rating, foodId, uid,
                rebuilt.Value!.NSignals, rebuilt.Value!.Stage);
        }

        return StatusCode(
            StatusCodes.Status201Created,
            new FeedbackResponse
            {
                Id = entry.Id,
                FoodId = entry.FoodId,
                FoodName = food.Name,
                Rating = entry.Rating,
                Comment = entry.Comment,
                CreatedAt = entry.CreatedAt,
                ProfileUpdated = rebuilt.Ok,
            });
    }

    // ── 7.8.2 What I have rated ──────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> Mine(
        [FromQuery] string? foodId,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = DefaultPageSize,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        if (page < 1)
        {
            return Invalid("page", "Số trang phải từ 1");
        }
        if (pageSize is < 1 or > MaxPageSize)
        {
            return Invalid(
                "pageSize", $"Số đánh giá mỗi trang phải từ 1 đến {MaxPageSize}");
        }

        var q = db.Feedbacks.Where(f => f.UserId == uid);
        if (foodId is { Length: > 0 })
        {
            q = q.Where(f => f.FoodId == foodId);
        }

        var total = await q.CountAsync(ct);

        // Newest first, and `Id` to break a tie: ratings of a whole meal
        // arrive in the same second, and without a total order the same page
        // can come back in two different arrangements — which with `Skip`
        // means a row appearing on two pages while another appears on none.
        //
        // No `StringComparer.Ordinal` here. It is what the in-memory sorts
        // in `MealPlanMapper` pass, but inside an EF query it cannot be
        // translated and MySQL raises it as a 500 at run time rather than a
        // compile error. The database's own collation on a CHAR(36) UUID is
        // deterministic, which is all a stable page needs.
        var rows = await q
            .OrderByDescending(f => f.CreatedAt)
            .ThenBy(f => f.Id)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToListAsync(ct);

        var cards = await FoodCardReader.ReadAsync(
            db, rows.Select(r => r.FoodId).Distinct().ToList(), ct);

        return Ok(new FeedbackPageResponse
        {
            Items = rows.Select(r => new FeedbackItemDto
            {
                Id = r.Id,
                Food = MealPlanMapper.Brief(r.FoodId, cards),
                Rating = r.Rating,
                Comment = r.Comment,
                CreatedAt = r.CreatedAt,
            }).ToList(),
            Page = page,
            PageSize = pageSize,
            TotalItems = total,
            TotalPages = total == 0
                ? 0
                : (int)Math.Ceiling(total / (double)pageSize),
        });
    }
}
