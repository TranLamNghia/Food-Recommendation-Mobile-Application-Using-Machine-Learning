using System.ComponentModel.DataAnnotations;
using Api.Data;
using Api.Http;
using Api.Ml;
using Api.Profile;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Onboarding;

/// <summary>
/// The onboarding filter screen — how many foods are left after what the
/// user has declared so far.
///
/// <para><b>Why it exists.</b> The flow used to be: fill in everything, then
/// swipe thirty cards. A card could then be a food the user must not eat —
/// they had declared gout after the deck was drawn — and the swipe was spent
/// on a dish the system had already ruled out. Asking this endpoint after
/// each answer narrows the pool as the user answers (318 → 228 → 116), so
/// the deck drawn at the end satisfies every condition by construction.</para>
///
/// <para><b>Nothing is saved.</b> The conditions in the request are what the
/// user has ticked, not what is on file, and the ML service is told to ignore
/// <c>user_conditions</c> entirely. So the screen can be opened, changed and
/// abandoned, and the first view of it shows the whole catalogue even for a
/// user who already has conditions saved.</para>
///
/// <para><b>Only hard rules narrow the count.</b> A soft rule lowers a
/// food's score and leaves it eligible — the penalty on salty dishes for
/// hypertension, for one — so counting it here would tell the user a dish is
/// gone while the plan can still contain it. Four of the thirteen conditions
/// therefore remove nothing at all, and <see cref="CandidateCountResponse"/>
/// says so instead of leaving the user to wonder why the number did not
/// move.</para>
/// </summary>
[ApiController]
[Route("api/v1/onboarding/candidates")]
[Authorize]
public sealed class CandidateFilterController(
    AppDbContext db,
    IMlClient ml,
    ILogger<CandidateFilterController> log) : ControllerBase
{
    /// <summary>
    /// How many conditions one request may carry. The catalogue has
    /// thirteen; the cap is there so a malformed client cannot send
    /// thousands and have the service build a query out of them.
    /// </summary>
    public const int MaxConditions = 50;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private string? UserId => User.FindFirst("sub")?.Value;

    [HttpPost("count")]
    public async Task<IActionResult> Count(
        CandidateCountRequest req, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var conditions = req.Conditions ?? [];

        var duplicates = conditions
            .GroupBy(c => c.ConditionId)
            .Where(g => g.Count() > 1)
            .Select(g => g.Key!.Value)
            .ToList();
        if (duplicates.Count > 0)
        {
            // Not harmless: the same condition twice at two severities would
            // apply the stricter one, and the screen would show a number the
            // user cannot account for from what they ticked.
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "conditions",
                    Message = "conditionId lặp lại: "
                        + string.Join(", ", duplicates),
                }]);
        }

        // The ids are checked here rather than left to the ML service.
        // That service answers `CONDITION_NOT_FOUND`, which maps to "this
        // backend sent something impossible" and reaches the client as a
        // 500 — right for a backend bug, wrong for a client that sent an id
        // the user picked from a stale list. `ProfileController.PutConditions`
        // validates the same field the same way.
        var ids = conditions
            .Where(c => c.ConditionId is not null)
            .Select(c => c.ConditionId!.Value)
            .ToList();
        if (ids.Count > 0)
        {
            var known = await db.Conditions
                .Where(c => ids.Contains(c.Id))
                .Select(c => c.Id)
                .ToListAsync(ct);
            var missing = ids.Except(known).ToList();
            if (missing.Count > 0)
            {
                return ApiProblem.Make(
                    400, ErrorCode.ValidationFailed,
                    "Dữ liệu gửi lên không hợp lệ",
                    HttpContext.TraceIdentifier,
                    [new ApiError.FieldError
                    {
                        Field = "conditions",
                        Message = "conditionId không tồn tại: "
                            + string.Join(", ", missing),
                    }]);
            }
        }

        var answer = await ml.CandidateCountAsync(
            new MlCandidateCountRequest
            {
                // Sent so the user's own foods are inside the count. The
                // conditions applied are still only the ones above.
                UserId = uid,
                Conditions = conditions
                    .Select(c => new MlCondition
                    {
                        ConditionId = (int)c.ConditionId!.Value,
                        Severity = c.Severity ?? "moderate",
                    })
                    .ToList(),
            },
            ct);

        if (answer.Failure is { } failure)
        {
            if (failure.IsSystemFault())
            {
                log.LogError("Onboarding filter: {Detail}", failure.Detail);
            }
            return failure.ToActionResult(HttpContext.TraceIdentifier);
        }

        var counts = answer.Required;

        // The ML service's warnings are developer-facing English for the
        // log. What the user reads is built here, in Vietnamese, from the
        // structured fields — the same split as everywhere else in this API.
        foreach (var warning in counts.Warnings)
        {
            log.LogInformation(
                "Onboarding filter for {User}: {Warning}", uid, warning);
        }

        return Ok(new CandidateCountResponse
        {
            TotalFoods = counts.NFoodsTotal,
            RemainingFoods = counts.NFoods,
            RemovedFoods = Math.Max(0, counts.NFoodsTotal - counts.NFoods),
            ByDishRole = counts.ByRole,
            EmptyRequiredRoles = counts.EmptyRequiredRoles,
            EnoughForSurvey = counts.EnoughForDeck,
            SurveyDeckSize = counts.DeckSize,
            Notes = CandidateNotes.For(counts, conditions.Count),
        });
    }
}

/// <summary>§7.4 — what the user has ticked so far.</summary>
public sealed class CandidateCountRequest
{
    /// <summary>
    /// May be empty, and an empty list means <b>no restriction</b> — the
    /// first view of the screen. It is not read as "whatever this user has
    /// on file", which is the distinction the screen depends on.
    /// </summary>
    [MaxLength(CandidateFilterController.MaxConditions,
               ErrorMessage = "Quá nhiều bệnh lý trong một lần gửi")]
    public List<ConditionChoiceDto>? Conditions { get; init; }
}

/// <summary>One condition, with the severity the user picked.</summary>
public sealed class ConditionChoiceDto
{
    /// <summary>
    /// <c>conditions.id</c>. A <c>uint</c> because the column is
    /// <c>INT UNSIGNED</c> — the same type
    /// <c>Api.Profile.UpsertConditionDto</c> uses, so the two endpoints that
    /// take a condition id take the same thing.
    /// </summary>
    [Required(ErrorMessage = "Thiếu mã bệnh lý")]
    public uint? ConditionId { get; init; }

    /// <summary><c>mild</c> · <c>moderate</c> · <c>severe</c>.</summary>
    [InEnum(nameof(Enums.Severity))]
    public string? Severity { get; init; }
}

/// <summary>
/// What the filter screen shows: the catalogue narrowing as the user answers.
/// </summary>
public sealed class CandidateCountResponse
{
    /// <summary>Active foods before anything was declared.</summary>
    public int TotalFoods { get; init; }

    /// <summary>What is left that this user may eat.</summary>
    public int RemainingFoods { get; init; }

    /// <summary>
    /// The difference, which is the number the screen animates. Sent rather
    /// than left to the client to subtract, so the figure the user sees and
    /// the figure in the log are the same arithmetic.
    /// </summary>
    public int RemovedFoods { get; init; }

    /// <summary>
    /// The remainder by <c>dish_role</c> — ENUM codes, which the app
    /// translates before the UI.
    ///
    /// <para>Reported, and deliberately not used to refuse anything: the
    /// filtering goes by the declared conditions alone. It is here because
    /// the total is not the figure that binds. 102 foods with 2 of them in
    /// the <c>side_protein</c> role still builds a lunch — with no
    /// alternative to offer and nothing for the exploration mechanism to
    /// draw.</para>
    /// </summary>
    public IReadOnlyDictionary<string, int> ByDishRole { get; init; }
        = new Dictionary<string, int>();

    /// <summary>
    /// Roles a plan cannot be assembled without that have nothing left in
    /// them. Non-empty means no meal plan is possible, whatever the total
    /// says.
    /// </summary>
    public IReadOnlyList<string> EmptyRequiredRoles { get; init; } = [];

    /// <summary>Whether a full-size taste survey can still be drawn.</summary>
    public bool EnoughForSurvey { get; init; }

    public int SurveyDeckSize { get; init; }

    /// <summary>
    /// Vietnamese sentences for the screen, when there is something worth
    /// saying. Empty is the normal case.
    /// </summary>
    public List<string> Notes { get; init; } = [];
}
