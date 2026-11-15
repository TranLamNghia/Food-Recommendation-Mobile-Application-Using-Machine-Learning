using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using System.IdentityModel.Tokens.Jwt;
using Api.Data;
using Api.Entities;
using Api.Time;

namespace Api.Auth;

/// <summary>JWT configuration, read from <c>appsettings</c> or from
/// environment variables.</summary>
public sealed class JwtOptions
{
    public const string Section = "Jwt";

    public string Issuer { get; set; } = "nutrition-rec";
    public string Audience { get; set; } = "nutrition-rec-mobile";

    /// <summary>
    /// The HMAC-SHA256 signing key. <b>No default value</b>, deliberately: a
    /// default key in the source would travel along into the real
    /// environment, and anyone who can read the repository could sign valid
    /// tokens. This repository is public.
    /// </summary>
    public string SigningKey { get; set; } = string.Empty;

    /// <summary>1 hour — specification §2.4.</summary>
    public int AccessTokenMinutes { get; set; } = 60;

    /// <summary>30 days — specification §2.4.</summary>
    public int RefreshTokenDays { get; set; } = 30;
}

/// <summary>The token pair returned to the frontend.</summary>
public sealed record TokenPair(
    string AccessToken, string RefreshToken, int ExpiresInSeconds);

/// <summary>
/// Issues and rotates tokens.
///
/// <para>The <b>accessToken</b> is a self-contained JWT: every
/// <c>🔒 Protected</c> endpoint authenticates it by its signature, with no
/// database lookup. That is why it only lives for an hour — it cannot be
/// revoked within that hour.</para>
///
/// <para>The <b>refreshToken</b> is the opposite: a random string, hashed and
/// stored in the <c>refresh_tokens</c> table. It has to have server-side
/// state because specification §7.1.3 promises "the old token is revoked" and
/// §7.1.7 promises "every token is revoked on a password change" — two
/// promises a self-contained JWT cannot keep.</para>
/// </summary>
public sealed class TokenService(AppDbContext db, JwtOptions opt)
{
    /// <summary>
    /// Hashes a token for storage. SHA-256 rather than BCrypt: the token is
    /// 32 random bytes, so it cannot be guessed from a dictionary, which
    /// leaves BCrypt's deliberate slowness as nothing but a cost on every
    /// <c>/auth/refresh</c> call.
    /// </summary>
    public static string Hash(string token)
        => Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes(token)));

    /// <summary>
    /// Generates a refreshToken: 32 bytes from the cryptographic random
    /// number generator.
    ///
    /// <para><b>Not <c>Guid.NewGuid()</c></b>, even though the specification
    /// draws the token as a UUID. <c>Guid.NewGuid()</c> on .NET is
    /// cryptographically random, so technically it would do, but it only has
    /// 122 bits of entropy and nothing in its API contract guarantees the
    /// randomness. 32 bytes from <c>RandomNumberGenerator</c> is
    /// guaranteed.</para>
    /// </summary>
    public static string NewRefreshToken()
        => Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
            .Replace('+', '-').Replace('/', '_').TrimEnd('=');

    /// <summary>
    /// Issues an accessToken for a user.
    ///
    /// <para><b>The only place left in the project that uses
    /// <c>DateTime.UtcNow</c>, and it has to.</b> A JWT's <c>nbf</c> and
    /// <c>exp</c> are seconds since the Unix epoch, always in UTC (RFC 7519
    /// §2). Putting Vietnam time in here would place <c>nbf</c> 7 hours in
    /// the future, and with <c>ClockSkew = TimeSpan.Zero</c> in
    /// <c>Program.cs</c> EVERY token would be rejected the moment it was
    /// issued.</para>
    /// </summary>
    public string CreateAccessToken(Users user, bool onboarded)
    {
        var key = new SymmetricSecurityKey(
            Encoding.UTF8.GetBytes(opt.SigningKey));
        var now = DateTime.UtcNow;

        // `sub` is the 36-character UUID of `users.id`, per specification
        // §2.3. An earlier version of the example in the specification said
        // `"sub": "1"` — the integer key of a design that was dropped.
        var claims = new List<Claim>
        {
            new(JwtRegisteredClaimNames.Sub, user.Id),
            new("email", user.Email),
            new("role", user.Role),
            new("onboarded", onboarded ? "true" : "false"),
        };

        var token = new JwtSecurityToken(
            issuer: opt.Issuer,
            audience: opt.Audience,
            claims: claims,
            notBefore: now,
            expires: now.AddMinutes(opt.AccessTokenMinutes),
            signingCredentials: new SigningCredentials(
                key, SecurityAlgorithms.HmacSha256));

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    /// <summary>
    /// Issues a fresh pair for register and login — nothing is rotated.
    /// </summary>
    public async Task<TokenPair> IssueAsync(Users user, bool onboarded)
    {
        var (pair, _) = await WriteAsync(user, onboarded, null);
        return pair!;
    }

    /// <summary>
    /// Rotates: revokes <paramref name="oldId"/> and issues a new pair.
    ///
    /// <para>Returns <c>null</c> when it <b>lost the race</b> — another
    /// request revoked that same row first. The caller has to handle it
    /// exactly like <see cref="RefreshOutcome.Reused"/>; see
    /// <c>AuthController.Refresh</c>.
    /// </para>
    /// </summary>
    public async Task<TokenPair?> RotateAsync(
        Users user, bool onboarded, string oldId)
    {
        var (pair, _) = await WriteAsync(user, onboarded, oldId);
        return pair;
    }

    private async Task<(TokenPair? Pair, bool Claimed)> WriteAsync(
        Users user, bool onboarded, string? oldId)
    {
        var refresh = NewRefreshToken();
        var now = Clock.Now;
        var row = new RefreshTokens
        {
            Id = Guid.NewGuid().ToString(),
            UserId = user.Id,
            TokenHash = Hash(refresh),
            // `chk_refresh_window CHECK (expires_at > created_at)` requires
            // `created_at` to be the smaller one. `created_at` is not left to
            // the database's CURRENT_TIMESTAMP: two separate writes would
            // then take two different instants, and the constraint could
            // reject a perfectly valid row.
            CreatedAt = now,
            ExpiresAt = now.AddDays(opt.RefreshTokenDays),
        };

        if (oldId is null)
        {
            db.RefreshTokens.Add(row);
            await db.SaveChangesAsync();
            return (MakePair(user, onboarded, refresh), true);
        }

        await using var tx = await db.Database.BeginTransactionAsync();

        // ── CLAIM the old row first, with ONE conditional UPDATE ──
        //
        // This is where the race is fixed. An earlier version READ the old
        // row and only then WROTE, so two concurrent requests carrying the
        // same token both saw `revoked_at IS NULL` before either had written
        // — both got through, both issued new tokens, and the result was TWO
        // live tokens in one family with neither counted as a reuse. Reuse
        // detection was decoration at that point.
        //
        // `WHERE id = @id AND revoked_at IS NULL` pushes the check and the
        // write into a single statement, so InnoDB locks the row and exactly
        // ONE statement sees `affected = 1`. The other sees 0 and knows it
        // lost.
        var claimed = await db.RefreshTokens
            .Where(t => t.Id == oldId && t.RevokedAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.RevokedAt, now));

        if (claimed == 0)
        {
            await tx.RollbackAsync();
            return (null, false);
        }

        // INSERT first, and only then point `replaced_by` at it. The
        // SELF-REFERENTIAL foreign key back to `refresh_tokens(id)` requires
        // the new row to exist first; EF does not infer that ordering — it
        // puts the UPDATE before the INSERT and MySQL answers:
        //
        //   Cannot add or update a child row: a foreign key constraint fails
        //   (`refresh_tokens`, CONSTRAINT `refresh_tokens_ibfk_2` ...)
        db.RefreshTokens.Add(row);
        await db.SaveChangesAsync();

        await db.RefreshTokens
            .Where(t => t.Id == oldId)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.ReplacedBy, row.Id));

        await tx.CommitAsync();
        return (MakePair(user, onboarded, refresh), true);
    }

    private TokenPair MakePair(Users user, bool onboarded, string refresh)
        => new(CreateAccessToken(user, onboarded),
               refresh,
               opt.AccessTokenMinutes * 60);

    /// <summary>The result of looking up a refreshToken the frontend sent
    /// in.</summary>
    public enum RefreshOutcome
    {
        /// <summary>Valid and still alive — issue a new pair.</summary>
        Valid,

        /// <summary>Not in the database, or already expired.</summary>
        Unknown,

        /// <summary>
        /// Already revoked and sent in again — a leak signal. The whole
        /// family is revoked; see <see cref="RevokeFamilyAsync"/>.
        /// </summary>
        Reused,
    }

    /// <summary>Looks up a refreshToken without changing anything.</summary>
    public async Task<(RefreshOutcome Outcome, RefreshTokens? Row)>
        InspectAsync(string refreshToken)
    {
        var hash = Hash(refreshToken);
        var row = await db.RefreshTokens
            .FirstOrDefaultAsync(t => t.TokenHash == hash);

        if (row is null)
        {
            return (RefreshOutcome.Unknown, null);
        }
        if (row.RevokedAt is not null)
        {
            return (RefreshOutcome.Reused, row);
        }
        if (row.ExpiresAt <= Clock.Now)
        {
            return (RefreshOutcome.Unknown, row);
        }
        return (RefreshOutcome.Valid, row);
    }

    /// <summary>
    /// Revokes the whole chain that <paramref name="startId"/> belongs to.
    ///
    /// <para>Called when an already-revoked token is sent in again. There are
    /// only two possibilities — a genuine user who lost their connection
    /// mid-rotation and still holds the old token, or a token that has leaked.
    /// The server cannot tell them apart, so it errs on the safe side: cut the
    /// whole chain and force a fresh login.</para>
    ///
    /// <para>It walks forward along <c>replaced_by</c>, with a bound on the
    /// number of steps: if an invariant were violated and the chain became a
    /// cycle, this loop would never stop. The schema has no constraint
    /// preventing a cycle — see the note on "invariants the schema does not
    /// enforce" in DATABASE_DESIGN 3.7.</para>
    /// </summary>
    public async Task RevokeFamilyAsync(string startId)
    {
        var now = Clock.Now;
        var seen = new HashSet<string>();
        string? id = startId;

        while (id is not null && seen.Add(id))
        {
            // READ each link AFRESH, rather than using an already-loaded
            // entity.
            //
            // An earlier version took a `RefreshTokens row` and walked along
            // `row.ReplacedBy`. In a race, `row` is the copy `InspectAsync`
            // read BEFORE the winner wrote `replaced_by`, and EF hands back
            // that same tracked entity — so `ReplacedBy` is still `null`, the
            // loop stops at the first link, and the winner's new token stays
            // alive. The 8-thread check in `tools/smoke_backend.py` catches
            // that; with 2 threads it does not show up.
            //
            // `AsNoTracking` is the important part: without it EF returns the
            // copy cached in the same request scope, and the bug comes
            // straight back.
            //
            // This read does see `replaced_by`: when the loser's
            // `ExecuteUpdateAsync` returned 0 rows, it had already waited for
            // InnoDB to release the row lock, which means the winner's
            // transaction had committed `replaced_by` along with it.
            var next = await db.RefreshTokens
                .AsNoTracking()
                .Where(t => t.Id == id)
                .Select(t => t.ReplacedBy)
                .FirstOrDefaultAsync();

            // `revoked_at ?? now` rather than overwriting: keep the first
            // revocation instant, because that is when the token actually
            // stopped being valid.
            await db.RefreshTokens
                .Where(t => t.Id == id)
                .ExecuteUpdateAsync(s => s.SetProperty(
                    t => t.RevokedAt, t => t.RevokedAt ?? now));

            id = next;
        }
    }

    /// <summary>
    /// Revokes every live token of one user — specification §7.1.7.
    ///
    /// <para>People change their password mainly because they suspect someone
    /// else has access. Leaving the old sessions alone would keep that
    /// person's session alive for another 30 days, and the password change
    /// would have solved nothing.</para>
    /// </summary>
    public async Task RevokeAllAsync(string userId)
    {
        var now = Clock.Now;
        await db.RefreshTokens
            .Where(t => t.UserId == userId && t.RevokedAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.RevokedAt, now));
    }
}

/// <summary>
/// The claim name written out directly rather than taken from the library's
/// <c>JwtRegisteredClaimNames</c> — so as not to depend on a constant that
/// could change between versions.
/// </summary>
internal static class JwtRegisteredClaimNames
{
    public const string Sub = "sub";
}
