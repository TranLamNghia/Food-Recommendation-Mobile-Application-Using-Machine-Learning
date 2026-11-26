using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;

namespace Api.Auth;

/// <summary>
/// The three password endpoints — specification §7.1.5 through §7.1.7.
///
/// <para>Beside <see cref="AuthController"/> under the same route rather than
/// inside it: those four endpoints issue tokens, these three take them away,
/// and the two files read more easily apart.</para>
/// </summary>
[ApiController]
[Route("api/v1/auth")]
public sealed class PasswordController(
    AppDbContext db,
    TokenService tokens,
    ResetMailQueue mail,
    ILogger<PasswordController> log) : ControllerBase
{
    /// <summary>§7.1.6: a code lives 15 minutes.</summary>
    public static readonly TimeSpan CodeLifetime = TimeSpan.FromMinutes(15);

    /// <summary>§7.1.5: at most 3 codes per account in 15 minutes.</summary>
    public const int CodesPerWindow = 3;

    public const string ForgotPolicy = "forgot-password";
    public const string ResetPolicy = "reset-password";

    private const string Done = "Đã đổi mật khẩu. Hãy đăng nhập lại.";

    private ObjectResult Fail(
        int status, string code, string message,
        List<ApiError.FieldError>? details = null)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier,
                           details);

    // ── 7.1.5 Forgot password ────────────────────────────────────────────

    [HttpPost("forgot-password")]
    [AllowAnonymous]
    [EnableRateLimiting(ForgotPolicy)]
    public async Task<IActionResult> Forgot(ForgotPasswordRequest req)
    {
        var email = req.Email.Trim().ToLowerInvariant();
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == email);

        // A disabled account gets no code: resetting the password would not
        // let it log in, and a mail saying otherwise would be a lie.
        if (user is { IsActive: true })
        {
            var now = Clock.Now;
            var since = now - CodeLifetime;
            var recent = await db.PasswordResets.CountAsync(
                r => r.UserId == user.Id && r.CreatedAt > since);

            // **Over the limit still answers 202**, unlike the 429 §7.1.5
            // lists. A 429 here only ever happens to a REGISTERED address —
            // a stranger's creates no row to count — so four requests would
            // read out whether an address has an account, exactly what the
            // 202 exists to hide. The per-IP limiter in `Program.cs` is
            // where 429 comes from, and it answers the same for every
            // address.
            if (recent < CodesPerWindow)
            {
                var token = TokenService.NewRefreshToken();
                db.PasswordResets.Add(new PasswordResets
                {
                    Id = Guid.NewGuid().ToString(),
                    UserId = user.Id,
                    TokenHash = TokenService.Hash(token),
                    // One instant for both, so `chk_reset_window` holds.
                    CreatedAt = now,
                    ExpiresAt = now + CodeLifetime,
                });
                await db.SaveChangesAsync();

                if (!mail.TryEnqueue(new ResetMail(
                        user.Email, user.DisplayName, token, now + CodeLifetime)))
                {
                    log.LogError(
                        "The reset mail queue is full; a code was stored "
                        + "but its mail was dropped.");
                }
            }
            else
            {
                log.LogInformation(
                    "Reset code not issued: {Limit} already in the last "
                    + "{Minutes} minutes for one account.",
                    CodesPerWindow, CodeLifetime.TotalMinutes);
            }
        }

        return StatusCode(StatusCodes.Status202Accepted, new MessageResponse
        {
            Message = "Nếu email này đã đăng ký, hướng dẫn đặt lại đã được gửi.",
        });
    }

    // ── 7.1.6 Reset password ─────────────────────────────────────────────

    [HttpPost("reset-password")]
    [AllowAnonymous]
    [EnableRateLimiting(ResetPolicy)]
    public async Task<IActionResult> Reset(ResetPasswordRequest req)
    {
        var hash = TokenService.Hash(req.Token.Trim());
        var now = Clock.Now;

        var row = await db.PasswordResets
            .AsNoTracking()
            .FirstOrDefaultAsync(r => r.TokenHash == hash);
        var user = row is null
            ? null
            : await db.Users.FirstOrDefaultAsync(u => u.Id == row.UserId);

        // Unknown, used, expired and disabled all get the same answer: the
        // code is no good, ask for another. Which of them it was is nothing
        // the holder of a bad code needs to know.
        if (row is null || row.UsedAt is not null || row.ExpiresAt <= now
            || user is null || !user.IsActive)
        {
            return Invalid();
        }

        await using var tx = await db.Database.BeginTransactionAsync();

        // CLAIM the code with one conditional UPDATE, as `TokenService`
        // claims a refresh token: two requests carrying the same code both
        // pass the read above, and only the one whose UPDATE touches a row
        // may go on. Without this a leaked code could be used twice inside
        // the same millisecond, and "dùng được đúng một lần" would be a
        // hope.
        var claimed = await db.PasswordResets
            .Where(r => r.Id == row.Id && r.UsedAt == null
                        && r.ExpiresAt > now)
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.UsedAt, now));
        if (claimed == 0)
        {
            await tx.RollbackAsync();
            return Invalid();
        }

        user.PasswordHash = BCrypt.Net.BCrypt.HashPassword(req.NewPassword);
        user.UpdatedAt = now;
        await db.SaveChangesAsync();

        await CloseOtherWaysInAsync(user.Id, now);
        await tx.CommitAsync();

        return Ok(new MessageResponse { Message = Done });
    }

    private ObjectResult Invalid()
        => Fail(StatusCodes.Status400BadRequest, ErrorCode.ResetTokenInvalid,
                "Mã đặt lại không đúng, đã hết hạn hoặc đã được dùng. Hãy "
                + "gửi lại yêu cầu quên mật khẩu.");

    // ── 7.1.7 Change password ────────────────────────────────────────────

    [HttpPut("password")]
    [Authorize]
    public async Task<IActionResult> Change(ChangePasswordRequest req)
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

        // Asked again although the token is valid — §7.1.7: the token sits
        // on a phone, and a phone can be in somebody else's hand.
        if (!BCrypt.Net.BCrypt.Verify(req.CurrentPassword, user.PasswordHash))
        {
            return Fail(StatusCodes.Status401Unauthorized,
                        ErrorCode.InvalidCredentials,
                        "Mật khẩu hiện tại không đúng");
        }

        if (BCrypt.Net.BCrypt.Verify(req.NewPassword, user.PasswordHash))
        {
            return Fail(StatusCodes.Status400BadRequest,
                        ErrorCode.ValidationFailed,
                        "Dữ liệu gửi lên không hợp lệ",
                        [new ApiError.FieldError
                        {
                            Field = "newPassword",
                            Message = "Mật khẩu mới phải khác mật khẩu hiện tại",
                        }]);
        }

        var now = Clock.Now;
        await using var tx = await db.Database.BeginTransactionAsync();
        user.PasswordHash = BCrypt.Net.BCrypt.HashPassword(req.NewPassword);
        user.UpdatedAt = now;
        await db.SaveChangesAsync();
        await CloseOtherWaysInAsync(user.Id, now);
        await tx.CommitAsync();

        return Ok(new MessageResponse { Message = Done });
    }

    /// <summary>
    /// After the password changes, every other way into the account goes:
    /// all refresh tokens (§7.1.7), and every reset code still alive.
    ///
    /// <para>The codes are not in the specification. A user who asked for a
    /// code twice and used the second still has the first sitting in their
    /// inbox for up to 15 minutes, and whoever reads that inbox could set
    /// the password once more. They are marked used rather than deleted, so
    /// a later attempt with one is still recorded as such.</para>
    /// </summary>
    private async Task CloseOtherWaysInAsync(string userId, DateTime now)
    {
        await db.PasswordResets
            .Where(r => r.UserId == userId && r.UsedAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.UsedAt, now));
        await tokens.RevokeAllAsync(userId);
    }
}
