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

/// <summary>Cấu hình JWT, đọc từ <c>appsettings</c> hoặc biến môi trường.</summary>
public sealed class JwtOptions
{
    public const string Section = "Jwt";

    public string Issuer { get; set; } = "nutrition-rec";
    public string Audience { get; set; } = "nutrition-rec-mobile";

    /// <summary>
    /// Khóa ký HMAC-SHA256. <b>Không có giá trị mặc định</b>, có chủ ý:
    /// một khóa mặc định trong mã nguồn sẽ đi theo lên môi trường thật, và
    /// mọi ai đọc được repo đều ký được token hợp lệ. Repo này là repo công
    /// khai.
    /// </summary>
    public string SigningKey { get; set; } = string.Empty;

    /// <summary>1 giờ — đặc tả §2.4.</summary>
    public int AccessTokenMinutes { get; set; } = 60;

    /// <summary>30 ngày — đặc tả §2.4.</summary>
    public int RefreshTokenDays { get; set; } = 30;
}

/// <summary>Cặp token trả về cho Frontend.</summary>
public sealed record TokenPair(
    string AccessToken, string RefreshToken, int ExpiresInSeconds);

/// <summary>
/// Phát và xoay vòng token.
///
/// <para><b>accessToken</b> là JWT tự chứa: mọi endpoint
/// <c>🔒 Protected</c> xác thực nó bằng chữ ký, không cần tra CSDL. Đó là lý
/// do nó chỉ sống một giờ — không thu hồi được trong một giờ đó.</para>
///
/// <para><b>refreshToken</b> thì ngược lại: một chuỗi ngẫu nhiên, băm rồi lưu
/// vào bảng <c>refresh_tokens</c>. Nó phải có trạng thái phía máy chủ vì đặc
/// tả §7.1.3 hứa "thu hồi token cũ" và §7.1.7 hứa "thu hồi mọi token khi đổi
/// mật khẩu" — hai lời hứa mà một JWT tự chứa không giữ được.</para>
/// </summary>
public sealed class TokenService(AppDbContext db, JwtOptions opt)
{
    /// <summary>
    /// Băm token để lưu. SHA-256 chứ không BCrypt: token là 32 byte ngẫu
    /// nhiên, không dò được bằng từ điển, nên cái chậm cố ý của BCrypt chỉ
    /// còn là chi phí trên mỗi lượt gọi <c>/auth/refresh</c>.
    /// </summary>
    public static string Hash(string token)
        => Convert.ToHexStringLower(
            SHA256.HashData(Encoding.UTF8.GetBytes(token)));

    /// <summary>
    /// Sinh refreshToken: 32 byte từ bộ sinh số ngẫu nhiên mật mã.
    ///
    /// <para><b>Không dùng <c>Guid.NewGuid()</c></b> dù đặc tả vẽ token dưới
    /// dạng UUID. <c>Guid.NewGuid()</c> trên .NET là ngẫu nhiên mật mã nên về
    /// kỹ thuật thì được, nhưng nó chỉ có 122 bit entropy và không có gì bảo
    /// đảm điều đó theo hợp đồng API của nó. 32 byte từ
    /// <c>RandomNumberGenerator</c> thì được bảo đảm.</para>
    /// </summary>
    public static string NewRefreshToken()
        => Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
            .Replace('+', '-').Replace('/', '_').TrimEnd('=');

    /// <summary>
    /// Phát accessToken cho một người dùng.
    ///
    /// <para><b>Chỗ duy nhất trong dự án còn dùng <c>DateTime.UtcNow</c>, và
    /// phải như vậy.</b> <c>nbf</c> và <c>exp</c> của JWT là số giây tính từ
    /// mốc Unix, luôn theo UTC (RFC 7519 §2). Đưa giờ Việt Nam vào đây thì
    /// <c>nbf</c> nằm ở 7 giờ trong tương lai, và với
    /// <c>ClockSkew = TimeSpan.Zero</c> ở <c>Program.cs</c> thì MỌI token bị
    /// từ chối ngay lúc vừa phát ra.</para>
    /// </summary>
    public string CreateAccessToken(Users user, bool onboarded)
    {
        var key = new SymmetricSecurityKey(
            Encoding.UTF8.GetBytes(opt.SigningKey));
        var now = DateTime.UtcNow;

        // `sub` là UUID 36 ký tự của `users.id`, theo đặc tả §2.3. Bản trước
        // của ví dụ trong đặc tả ghi `"sub": "1"` — khóa số nguyên của một
        // bản thiết kế đã bỏ.
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
    /// Phát một cặp token mới cho đăng ký và đăng nhập — không xoay vòng gì.
    /// </summary>
    public async Task<TokenPair> IssueAsync(Users user, bool onboarded)
    {
        var (cap, _) = await GhiAsync(user, onboarded, null);
        return cap!;
    }

    /// <summary>
    /// Xoay vòng: thu hồi <paramref name="idCu"/> và phát cặp mới.
    ///
    /// <para>Trả <c>null</c> khi <b>mất cuộc đua</b> — một yêu cầu khác đã
    /// thu hồi đúng dòng đó trước. Người gọi phải xử lý y như trường hợp
    /// <see cref="RefreshOutcome.Reused"/>; xem <c>AuthController.Refresh</c>.
    /// </para>
    /// </summary>
    public async Task<TokenPair?> RotateAsync(
        Users user, bool onboarded, string idCu)
    {
        var (cap, _) = await GhiAsync(user, onboarded, idCu);
        return cap;
    }

    private async Task<(TokenPair? Cap, bool Doat)> GhiAsync(
        Users user, bool onboarded, string? idCu)
    {
        var refresh = NewRefreshToken();
        var now = DongHo.BayGio;
        var row = new RefreshTokens
        {
            Id = Guid.NewGuid().ToString(),
            UserId = user.Id,
            TokenHash = Hash(refresh),
            // `chk_refresh_window CHECK (expires_at > created_at)` đòi
            // `created_at` phải nhỏ hơn. Không để CSDL tự đặt `created_at`
            // bằng CURRENT_TIMESTAMP: hai lượt ghi khác nhau sẽ lấy hai mốc
            // khác nhau, và khi đó ràng buộc có thể chặn một dòng hợp lệ.
            CreatedAt = now,
            ExpiresAt = now.AddDays(opt.RefreshTokenDays),
        };

        if (idCu is null)
        {
            db.RefreshTokens.Add(row);
            await db.SaveChangesAsync();
            return (Cap(user, onboarded, refresh), true);
        }

        await using var gd = await db.Database.BeginTransactionAsync();

        // ── ĐOẠT dòng cũ trước, bằng MỘT lệnh UPDATE có điều kiện ──
        //
        // Đây là chỗ sửa cuộc đua. Bản trước ĐỌC dòng cũ rồi mới GHI, nên
        // hai yêu cầu đồng thời cùng một token đều thấy `revoked_at IS NULL`
        // trước khi bên nào kịp ghi — cả hai đi qua, cả hai phát token mới,
        // và kết quả là HAI token sống trong một họ mà không bên nào bị coi
        // là tái dùng. Phép phát hiện tái dùng khi đó chỉ còn là trang trí.
        //
        // `WHERE id = @id AND revoked_at IS NULL` đẩy phép kiểm và phép ghi
        // vào cùng một lệnh, nên InnoDB khóa dòng và đúng MỘT lệnh thấy
        // `affected = 1`. Lệnh còn lại thấy 0 và biết mình đã mất.
        var doat = await db.RefreshTokens
            .Where(t => t.Id == idCu && t.RevokedAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.RevokedAt, now));

        if (doat == 0)
        {
            await gd.RollbackAsync();
            return (null, false);
        }

        // INSERT trước, rồi mới trỏ `replaced_by`. Khóa ngoại TỰ TRỎ về
        // `refresh_tokens(id)` đòi dòng mới phải tồn tại trước; EF không suy
        // ra thứ tự đó — nó xếp UPDATE trước INSERT và MySQL trả:
        //
        //   Cannot add or update a child row: a foreign key constraint fails
        //   (`refresh_tokens`, CONSTRAINT `refresh_tokens_ibfk_2` ...)
        db.RefreshTokens.Add(row);
        await db.SaveChangesAsync();

        await db.RefreshTokens
            .Where(t => t.Id == idCu)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.ReplacedBy, row.Id));

        await gd.CommitAsync();
        return (Cap(user, onboarded, refresh), true);
    }

    private TokenPair Cap(Users user, bool onboarded, string refresh)
        => new(CreateAccessToken(user, onboarded),
               refresh,
               opt.AccessTokenMinutes * 60);

    /// <summary>Kết quả tra một refreshToken do Frontend nộp lên.</summary>
    public enum RefreshOutcome
    {
        /// <summary>Hợp lệ, còn sống — cấp cặp mới.</summary>
        Valid,

        /// <summary>Không có trong CSDL, hoặc đã hết hạn.</summary>
        Unknown,

        /// <summary>
        /// Đã bị thu hồi mà vẫn được nộp lại — tín hiệu rò rỉ. Cả họ bị thu
        /// hồi; xem <see cref="RevokeFamilyAsync"/>.
        /// </summary>
        Reused,
    }

    /// <summary>Tra một refreshToken, không thay đổi gì.</summary>
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
        if (row.ExpiresAt <= DongHo.BayGio)
        {
            return (RefreshOutcome.Unknown, row);
        }
        return (RefreshOutcome.Valid, row);
    }

    /// <summary>
    /// Thu hồi cả chuỗi mà <paramref name="row"/> thuộc về.
    ///
    /// <para>Gọi khi một token đã thu hồi được nộp lại. Chỉ có hai khả năng —
    /// người dùng thật mất mạng đúng giữa lúc xoay vòng nên vẫn giữ token cũ,
    /// hoặc token đã rò ra ngoài. Máy chủ không phân biệt được, nên xử lý
    /// theo hướng an toàn: cắt cả chuỗi, buộc đăng nhập lại.</para>
    ///
    /// <para>Lần xuôi theo <c>replaced_by</c>, có chặn số bước: nếu một bất
    /// biến bị vi phạm và chuỗi thành vòng, vòng lặp này sẽ không bao giờ
    /// dừng. Lược đồ không có ràng buộc nào chặn vòng — xem ghi chú
    /// "bất biến mà lược đồ không bắt buộc" ở DATABASE_DESIGN 3.7.</para>
    /// </summary>
    public async Task RevokeFamilyAsync(string idBatDau)
    {
        var now = DongHo.BayGio;
        var seen = new HashSet<string>();
        string? id = idBatDau;

        while (id is not null && seen.Add(id))
        {
            // ĐỌC MỚI từng mắt, không dùng thực thể đã nạp sẵn.
            //
            // Bản trước nhận vào `RefreshTokens row` rồi lần theo
            // `row.ReplacedBy`. Trong một cuộc đua, `row` là bản mà
            // `InspectAsync` đã đọc TRƯỚC khi lượt thắng ghi `replaced_by`,
            // và EF trả lại đúng thực thể đã theo dõi đó — nên `ReplacedBy`
            // vẫn là `null` và vòng lặp dừng ở mắt đầu, để token mới của
            // lượt thắng sống nguyên. Phép kiểm 8 luồng trong
            // `tools/smoke_backend.py` bắt được chuyện này; với 2 luồng thì
            // nó không hiện ra.
            //
            // `AsNoTracking` là phần quan trọng: thiếu nó thì EF lại trả bản
            // đã cache trong cùng phạm vi yêu cầu, và lỗi quay lại y nguyên.
            //
            // Lượt đọc này thấy được `replaced_by`: khi `ExecuteUpdateAsync`
            // của lượt thua trả về 0 dòng, nó đã đợi InnoDB nhả khóa dòng,
            // nghĩa là giao dịch của lượt thắng đã commit cả `replaced_by`.
            var ke = await db.RefreshTokens
                .AsNoTracking()
                .Where(t => t.Id == id)
                .Select(t => t.ReplacedBy)
                .FirstOrDefaultAsync();

            // `revoked_at ?? now` chứ không gán đè: giữ nguyên mốc thu hồi
            // đầu tiên, vì đó là lúc token thật sự mất hiệu lực.
            await db.RefreshTokens
                .Where(t => t.Id == id)
                .ExecuteUpdateAsync(s => s.SetProperty(
                    t => t.RevokedAt, t => t.RevokedAt ?? now));

            id = ke;
        }
    }

    /// <summary>
    /// Thu hồi mọi token còn sống của một người — đặc tả §7.1.7.
    ///
    /// <para>Người ta đổi mật khẩu chủ yếu vì nghi có người khác đang truy
    /// cập. Giữ nguyên các phiên cũ thì phiên của kẻ đó sống thêm 30 ngày và
    /// việc đổi mật khẩu không giải quyết được gì.</para>
    /// </summary>
    public async Task RevokeAllAsync(string userId)
    {
        var now = DongHo.BayGio;
        await db.RefreshTokens
            .Where(t => t.UserId == userId && t.RevokedAt == null)
            .ExecuteUpdateAsync(s => s.SetProperty(t => t.RevokedAt, now));
    }
}

/// <summary>
/// Tên claim viết thẳng, không qua <c>JwtRegisteredClaimNames</c> của thư
/// viện — để không phụ thuộc vào một hằng số có thể đổi giữa các phiên bản.
/// </summary>
internal static class JwtRegisteredClaimNames
{
    public const string Sub = "sub";
}
