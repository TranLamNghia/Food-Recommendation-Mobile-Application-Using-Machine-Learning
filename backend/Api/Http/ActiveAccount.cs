using Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.EntityFrameworkCore;

namespace Api.Http;

/// <summary>
/// Blocks every authenticated request from an account that is <b>no longer
/// active</b> or has been deleted.
///
/// <para><b>Why a global filter rather than a check in each
/// controller.</b> The previous version checked <c>IsActive</c> at
/// <c>/auth/login</c>, <c>/auth/refresh</c> and <c>/auth/me</c> — four places
/// — but NOT at any <c>/profile</c> endpoint. A disabled account could still
/// read and write its profile for up to an hour, that is, until the
/// accessToken expired. 34 public endpoints and 4 internal ones are still to
/// be built; a check that has to be remembered at every endpoint is a check
/// that will be forgotten, and when it is, nothing reports it.</para>
///
/// <para>Registered globally in <c>Program.cs</c>, so a new endpoint is
/// protected <b>by default</b> with nobody having to remember anything.
/// Removing the protection has to be an explicit act: adding
/// <c>[AllowAnonymous]</c>.</para>
///
/// <para><b>It does not apply to <c>/auth/login</c> or
/// <c>/auth/refresh</c></b>: those two are <c>[AllowAnonymous]</c> and
/// authenticate with a password or a refreshToken rather than an accessToken,
/// so there is no <c>sub</c> claim to look up. They keep their own
/// <c>IsActive</c> check, and that is not duplication — they are two different
/// ways in.</para>
///
/// <para>The cost: one <c>SELECT is_active FROM users WHERE id = ?</c> by
/// primary key per authenticated request. Worth it in exchange for not being
/// able to forget.</para>
/// </summary>
public sealed class ActiveAccountFilter(AppDbContext db)
    : IAsyncAuthorizationFilter
{
    public async Task OnAuthorizationAsync(AuthorizationFilterContext ctx)
    {
        // With `[AllowAnonymous]` there is nothing to look up. The endpoint's
        // metadata is what gets checked, because that is where
        // `[AllowAnonymous]` actually lives once routing has run.
        var endpoint = ctx.HttpContext.GetEndpoint();
        if (endpoint?.Metadata.GetMetadata<IAllowAnonymous>() is not null)
        {
            return;
        }

        // When authentication did not succeed, leave it to the JwtBearer
        // layer to return 401 with the right TOKEN_EXPIRED / TOKEN_INVALID
        // code — see `OnChallenge` in Program.cs.
        if (ctx.HttpContext.User.Identity?.IsAuthenticated is not true)
        {
            return;
        }

        var uid = ctx.HttpContext.User.FindFirst("sub")?.Value;
        if (string.IsNullOrEmpty(uid))
        {
            ctx.Result = Problem(ctx, StatusCodes.Status401Unauthorized,
                                 ErrorCode.TokenInvalid, "Token thiếu `sub`");
            return;
        }

        // One column, not the whole row. A `bool?` distinguishes three states:
        // no row at all (null), a row that is disabled (false), and normal
        // (true).
        var isActive = await db.Users
            .Where(u => u.Id == uid)
            .Select(u => (bool?)u.IsActive)
            .FirstOrDefaultAsync();

        if (isActive is null)
        {
            // The token's signature is valid but the user has been deleted
            // from the database. 401 rather than 403: there is no account left
            // to call disabled.
            ctx.Result = Problem(ctx, StatusCodes.Status401Unauthorized,
                                 ErrorCode.TokenInvalid,
                                 "Tài khoản không còn tồn tại");
            return;
        }

        if (isActive is false)
        {
            ctx.Result = Problem(ctx, StatusCodes.Status403Forbidden,
                                 ErrorCode.AccountDisabled,
                                 "Tài khoản đã bị khóa, vui lòng liên hệ quản trị");
        }
    }

    private static ObjectResult Problem(
        AuthorizationFilterContext ctx, int status, string code, string message)
        => ApiProblem.Make(status, code, message,
                           ctx.HttpContext.TraceIdentifier);
}
