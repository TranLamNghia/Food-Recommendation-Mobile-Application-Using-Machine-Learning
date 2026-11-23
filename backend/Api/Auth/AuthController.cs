using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Auth;

/// <summary>
/// The Authentication group — specification §7.1.1 through §7.1.4.
///
/// <para>These four endpoints are wave 1 in the implementation order of
/// §10.2, because every other endpoint needs a token.</para>
///
/// <para>Note on language: every <c>message</c> passed to <see cref="Fail"/>
/// stays in Vietnamese. It is the <c>error.message</c> of specification §2.5,
/// which end users read; the stable string the frontend branches on is
/// <c>error.code</c>.</para>
/// </summary>
[ApiController]
[Route("api/v1/auth")]
public sealed class AuthController(AppDbContext db, TokenService tokens)
    : ControllerBase
{
    private ObjectResult Fail(
        int status, string code, string message,
        List<ApiError.FieldError>? details = null)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier,
                        details);

    // ── 7.1.1 Register ───────────────────────────────────────────────────

    [HttpPost("register")]
    [AllowAnonymous]
    public async Task<IActionResult> Register(RegisterRequest req)
    {
        var email = req.Email.Trim().ToLowerInvariant();

        // Emails are matched case-INSENSITIVELY. `users.email` is UNIQUE with
        // the `utf8mb4_unicode_ci` collation, so the database already treats
        // `A@x.com` and `a@x.com` as one — but storing whatever form the user
        // typed would make logging in with a different form depend on the
        // collation rather than on the code, and that changes with the server
        // configuration. Normalise to lower case right here.
        if (await db.Users.AnyAsync(u => u.Email == email))
        {
            return Fail(StatusCodes.Status409Conflict,
                        ErrorCode.EmailAlreadyExists,
                        "Email này đã được đăng ký");
        }

        var now = Clock.Now;
        var user = new Users
        {
            Id = Guid.NewGuid().ToString(),
            Email = email,
            // `role` defaults to `user`. `role` is NEVER taken from the
            // request body — that is how someone grants themselves admin
            // rights with one line of JSON.
            Role = "user",
            IsActive = true,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(req.Password),
            DisplayName = req.DisplayName.Trim(),
            AvatarUrl = null,
            // `null` = the exploratory swipe session is not finished, so they
            // are still in Stage 0.
            OnboardingCompletedAt = null,
            CreatedAt = now,
            UpdatedAt = now,
        };
        db.Users.Add(user);

        try
        {
            await db.SaveChangesAsync();
        }
        catch (DbUpdateException)
        {
            // Two registrations for the same email at the same time: the
            // check above lets both through, and then `UNIQUE (email)` stops
            // the second one. This is why that UNIQUE constraint has to exist
            // — a check at the application layer is never atomic.
            //
            // `await` is not allowed in a `catch`'s `when` clause, so the
            // lookup has to happen in the body. And the row just added has to
            // be DETACHED from the ChangeTracker before querying: otherwise
            // EF would try to write it again on the next SaveChanges in the
            // same request scope.
            db.Entry(user).State = EntityState.Detached;

            if (await db.Users.AnyAsync(u => u.Email == email))
            {
                return Fail(StatusCodes.Status409Conflict,
                            ErrorCode.EmailAlreadyExists,
                            "Email này đã được đăng ký");
            }
            throw;
        }

        var pair = await tokens.IssueAsync(user, onboarded: false);
        return StatusCode(StatusCodes.Status201Created,
                          BuildResponse(pair, user));
    }

    // ── 7.1.2 Log in ─────────────────────────────────────────────────────

    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login(LoginRequest req)
    {
        var email = req.Email.Trim().ToLowerInvariant();
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == email);

        // The password is verified EVEN WHEN there is no such user, against a
        // dummy hash.
        //
        // Returning early when the email does not exist leaks information
        // through the response time: BCrypt takes around 100 ms, so "no such
        // email" would answer instantly while "wrong password" took 100 ms.
        // Timing the responses then reads out which emails are registered —
        // exactly what specification §7.1.2 tries to hide by returning one
        // single error code.
        var hash = user?.PasswordHash ?? DummyHash;
        var matches = BCrypt.Net.BCrypt.Verify(req.Password, hash);

        if (user is null || !matches)
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.InvalidCredentials,
                        "Email hoặc mật khẩu không đúng");
        }

        // A disabled account is told so plainly rather than given
        // INVALID_CREDENTIALS: a genuine user needs to know to contact an
        // administrator instead of sitting there retrying their password. The
        // check comes AFTER the password has been verified — otherwise anyone
        // could probe which accounts are disabled.
        if (!user.IsActive)
        {
            return Fail(StatusCodes.Status403Forbidden,
                        ErrorCode.AccountDisabled,
                        "Tài khoản đã bị khóa, vui lòng liên hệ quản trị");
        }

        var pair = await tokens.IssueAsync(
            user, onboarded: user.OnboardingCompletedAt is not null);
        return Ok(BuildResponse(pair, user));
    }

    /// <summary>
    /// The BCrypt hash of a password nobody knows, verified against when the
    /// email does not exist. The particular value does not matter — it only
    /// has to be a valid BCrypt hash so that <c>Verify</c> performs the full
    /// number of rounds.
    /// </summary>
    private const string DummyHash =
        "$2a$11$N9qo8uLOickgx2ZMRZoMye" +
        "IjZAgcfl7p92ldGxad68LJZdL17lhWy";

    // ── 7.1.3 Refresh a token ────────────────────────────────────────────

    [HttpPost("refresh")]
    [AllowAnonymous]
    public async Task<IActionResult> Refresh(RefreshRequest req)
    {
        var (outcome, row) = await tokens.InspectAsync(req.RefreshToken);

        if (outcome == TokenService.RefreshOutcome.Reused && row is not null)
        {
            // An already-revoked token sent in again. Two possibilities, and
            // they cannot be told apart: a genuine user who lost their
            // connection mid-rotation, or a token that has leaked. Cut the
            // whole chain.
            await tokens.RevokeFamilyAsync(row.Id);
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid,
                        "refreshToken đã bị thu hồi — vui lòng đăng nhập lại");
        }

        if (outcome != TokenService.RefreshOutcome.Valid || row is null)
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid,
                        "refreshToken không hợp lệ hoặc đã hết hạn");
        }

        var user = await db.Users.FirstOrDefaultAsync(u => u.Id == row.UserId);
        if (user is null || !user.IsActive)
        {
            // The account was disabled after the token was issued. Revoke
            // them all, otherwise that person could keep refreshing for 30
            // days.
            await tokens.RevokeAllAsync(row.UserId);
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid,
                        "Tài khoản không còn hoạt động");
        }

        var pair = await tokens.RotateAsync(
            user,
            onboarded: user.OnboardingCompletedAt is not null,
            oldId: row.Id);

        if (pair is null)
        {
            // LOST THE RACE: between the `InspectAsync` above and the row
            // claim inside `RotateAsync`, another request revoked this exact
            // token. The same token was sent in twice — indistinguishable
            // from a leak, so it is handled exactly like a reuse.
            //
            // Which means a duplicate submission (the user tapping twice, or
            // the app retrying after a dropped packet) will LOG THE USER OUT.
            // That is the price of reuse detection, and it was already
            // accepted in the `Reused` branch above; this only makes it hold
            // under concurrency too.
            await tokens.RevokeFamilyAsync(row.Id);
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid,
                        "refreshToken đã được dùng ở một yêu cầu khác — vui "
                        + "lòng đăng nhập lại");
        }

        return Ok(new RefreshResponse
        {
            AccessToken = pair.AccessToken,
            RefreshToken = pair.RefreshToken,
            ExpiresIn = pair.ExpiresInSeconds,
        });
    }

    // ── 7.1.4 Account information ────────────────────────────────────────

    [HttpGet("me")]
    [Authorize]
    public async Task<IActionResult> Me()
    {
        var userId = User.FindFirst("sub")?.Value;
        if (userId is null)
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        // One query, not three. Three round trips to the database for an
        // endpoint the frontend calls the MOMENT the app opens is three
        // internal network hops before the first screen can be drawn.
        var found = await db.Users
            .Where(u => u.Id == userId)
            .Select(u => new
            {
                User = u,
                HasProfile = db.HealthProfiles.Any(h => h.UserId == u.Id),
                Stage = db.UserPreferenceProfiles
                    .Where(p => p.UserId == u.Id)
                    .Select(p => p.Stage)
                    .FirstOrDefault(),
            })
            .FirstOrDefaultAsync();

        if (found is null)
        {
            // `ActiveAccountFilter` already looked up `is_active` before
            // reaching here, so this branch only runs when the user was
            // deleted BETWEEN the two queries. It stays because otherwise a
            // possibly-null value would have to be `!`-ed.
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid, "Tài khoản không còn tồn tại");
        }

        // `IsActive` is NOT checked here any more. The global
        // `ActiveAccountFilter` does that for EVERY authenticated endpoint. A
        // second check here would be dead code that looks like a safety net,
        // and it would hide the fact that the other 38 endpoints have no net
        // at all.

        return Ok(new MeResponse
        {
            Id = found.User.Id,
            Email = found.User.Email,
            DisplayName = found.User.DisplayName,
            AvatarUrl = found.User.AvatarUrl,
            OnboardingCompletedAt = found.User.OnboardingCompletedAt,
            HasHealthProfile = found.HasProfile,
            // No `user_preference_profiles` row yet means no signal has been
            // given — which is precisely Stage 0, `cold`.
            PreferenceStage = string.IsNullOrEmpty(found.Stage)
                ? "cold"
                : found.Stage,
            CreatedAt = found.User.CreatedAt,
        });
    }

    // ── Change the account's own details ─────────────────────────────────

    /// <summary>
    /// Renames the account — <b>not in the specification</b>.
    ///
    /// <para>§6 lists seven authentication endpoints and not one of them
    /// edits the account itself, while the app has a settings screen for the
    /// display name. The name was typed, shown, and lost on the next launch.
    /// </para>
    ///
    /// <para>It answers with the same body as <c>GET /auth/me</c>, so the
    /// client has one shape to parse and does not need a second call to see
    /// the result.</para>
    /// </summary>
    [HttpPut("me")]
    [Authorize]
    public async Task<IActionResult> UpdateMe(UpdateAccountRequest req)
    {
        var userId = User.FindFirst("sub")?.Value;
        if (userId is null)
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var user = await db.Users.FirstOrDefaultAsync(u => u.Id == userId);
        if (user is null)
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.TokenInvalid, "Tài khoản không còn tồn tại");
        }

        // Trimmed before the length check has already happened, so a name of
        // two spaces passed `MinLength(2)` and would be stored as empty. The
        // check is repeated here on the trimmed value.
        var name = req.DisplayName.Trim();
        if (name.Length < 2)
        {
            return ApiProblem.Make(
                StatusCodes.Status400BadRequest, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ", HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "displayName",
                    Message = "Tên hiển thị tối thiểu 2 ký tự",
                }]);
        }

        user.DisplayName = name;
        user.UpdatedAt = Clock.Now;
        await db.SaveChangesAsync();

        return await Me();
    }

    // ── shared ───────────────────────────────────────────────────────────

    private static AuthResponse BuildResponse(TokenPair pair, Users user)
        => new()
        {
            AccessToken = pair.AccessToken,
            RefreshToken = pair.RefreshToken,
            ExpiresIn = pair.ExpiresInSeconds,
            User = new UserSummary
            {
                Id = user.Id,
                Email = user.Email,
                DisplayName = user.DisplayName,
                AvatarUrl = user.AvatarUrl,
                OnboardingCompletedAt = user.OnboardingCompletedAt,
                CreatedAt = user.CreatedAt,
            },
        };
}
