using Api.Data;
using Api.Http;
using Api.Profile;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Catalogue;

/// <summary>
/// The three lookup dictionaries — specification §7.3.
///
/// <para><b>Why these came after the screens that need them.</b> The
/// implementation order of §10.2 puts them in wave 1, and waves 4 and 5 were
/// built first. The onboarding filter screen takes a list of
/// <c>conditionId</c>s and had no endpoint to obtain them from: an endpoint
/// whose input the client cannot get is not finished. These three close
/// that.</para>
///
/// <para><b>Public on purpose</b> (🌐 in §6). None of the three says anything
/// about a user, and the sign-up flow needs the condition list before an
/// account exists — a user picks their conditions on the way in. So
/// <c>[AllowAnonymous]</c>, which also takes them out of
/// <see cref="ActiveAccountFilter"/>'s reach, since there is no token to look
/// an account up with.</para>
///
/// <para><b>No paging.</b> 13 conditions, 12 categories, 13 tags. A page
/// parameter on a list that cannot grow past a screenful is a parameter every
/// client has to handle for nothing.</para>
///
/// <para>Note on language: every row returned is Vietnamese free text out of
/// the database (<c>conditions.name_vi</c>, <c>food_categories.name</c>,
/// <c>tags.name_vi</c>) and goes to the screen as it stands.
/// <c>conditionType</c> and <c>tagType</c> are ENUM codes and are never
/// translated here — the app does that right before the UI.</para>
/// </summary>
[ApiController]
[Route("api/v1")]
[AllowAnonymous]
public sealed class LookupController(AppDbContext db) : ControllerBase
{
    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    // ── 7.3.1 The condition dictionary ───────────────────────────────────

    [HttpGet("conditions")]
    public async Task<IActionResult> Conditions(
        [FromQuery] string? type, CancellationToken ct = default)
    {
        // Refused rather than ignored. A client sending `type=desease` would
        // otherwise get the whole list back and show it as filtered, and the
        // user would see conditions they had just excluded.
        if (type is not null && !Enums.ConditionType.Contains(type))
        {
            return Invalid(
                "type",
                "Loại bệnh lý không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.ConditionType));
        }

        var rows = await db.Conditions
            .Where(c => type == null || c.ConditionType == type)
            // By type, then by name, so the declaration screen can show the
            // list in groups without sorting it again — and so two calls
            // never come back in a different order.
            .OrderBy(c => c.ConditionType)
            .ThenBy(c => c.NameVi)
            .Select(c => new ConditionDto
            {
                Id = c.Id,
                NameVi = c.NameVi,
                ConditionType = c.ConditionType,
                Description = c.Description,
            })
            .ToListAsync(ct);

        return Ok(rows);
    }

    // ── 7.3.2 The food categories ────────────────────────────────────────

    [HttpGet("food-categories")]
    public async Task<IActionResult> FoodCategories(
        CancellationToken ct = default)
        => Ok(await db.FoodCategories
            .OrderBy(c => c.Name)
            .Select(c => new FoodCategoryDto
            {
                Id = c.Id,
                Name = c.Name,
                Description = c.Description,
                IconUrl = c.IconUrl,
            })
            .ToListAsync(ct));

    // ── 7.3.3 The tag dictionary ─────────────────────────────────────────

    [HttpGet("tags")]
    public async Task<IActionResult> Tags(
        [FromQuery] string? type, CancellationToken ct = default)
    {
        if (type is not null && !Enums.TagType.Contains(type))
        {
            return Invalid(
                "type",
                "Loại nhãn không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.TagType));
        }

        var rows = await db.Tags
            .Where(t => type == null || t.TagType == type)
            .OrderBy(t => t.TagType)
            .ThenBy(t => t.NameVi)
            .Select(t => new TagDto
            {
                Id = t.Id,
                NameVi = t.NameVi,
                TagType = t.TagType,
                Description = t.Description,
            })
            .ToListAsync(ct);

        return Ok(rows);
    }
}

/// <summary>One row of §7.3.1 — a condition, allergy, intolerance or diet.</summary>
public sealed class ConditionDto
{
    /// <summary>
    /// <c>conditions.id</c>, which is what
    /// <c>POST /onboarding/candidates/count</c> and
    /// <c>PUT /profile/conditions</c> both take.
    /// </summary>
    public uint Id { get; init; }

    /// <summary>Vietnamese, as <c>name_vi</c> stores it.</summary>
    public string NameVi { get; init; } = string.Empty;

    /// <summary>
    /// <c>disease</c> · <c>allergy</c> · <c>intolerance</c> · <c>diet</c> —
    /// an ENUM code, for the app to group the list by.
    /// </summary>
    public string ConditionType { get; init; } = string.Empty;

    /// <summary>
    /// What the condition means for eating, in Vietnamese. <c>null</c> where
    /// the row has none — not an empty string, so the app can tell "no
    /// description" from "an empty one" (§10.3).
    /// </summary>
    public string? Description { get; init; }
}

/// <summary>One row of §7.3.2.</summary>
public sealed class FoodCategoryDto
{
    public string Id { get; init; } = string.Empty;

    /// <summary>Vietnamese free text — "Món nước", "Món canh".</summary>
    public string Name { get; init; } = string.Empty;

    public string? Description { get; init; }
    public string? IconUrl { get; init; }
}

/// <summary>One row of §7.3.3.</summary>
public sealed class TagDto
{
    public uint Id { get; init; }
    public string NameVi { get; init; } = string.Empty;

    /// <summary>
    /// <c>allergen</c> · <c>diet</c> · <c>nutrition</c>. There is no
    /// <c>taste</c> type: salty and sweet are measured vector dimensions
    /// computed from <c>sodium_mg</c> and <c>sugar_g</c>, and sour and bitter
    /// are not published by any source this project uses.
    /// </summary>
    public string TagType { get; init; } = string.Empty;

    /// <summary>
    /// Not in §7.3.3's example, and included because the column exists and
    /// carries the explanation of what the tag means — the one thing a user
    /// looking at "Giàu purin" needs.
    /// </summary>
    public string? Description { get; init; }
}
