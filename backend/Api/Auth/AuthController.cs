using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Auth;

/// <summary>
/// Nhóm Xác thực — đặc tả §7.1.1 đến §7.1.4.
///
/// <para>Bốn endpoint này là đợt 1 trong thứ tự hiện thực ở §10.2, vì mọi
/// endpoint khác đều cần token.</para>
/// </summary>
[ApiController]
[Route("api/v1/auth")]
public sealed class AuthController(AppDbContext db, TokenService tokens)
    : ControllerBase
{
    private ObjectResult Loi(
        int status, string code, string message,
        List<ApiError.FieldError>? details = null)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier,
                        details);

    // ── 7.1.1 Đăng ký ────────────────────────────────────────────────────

    [HttpPost("register")]
    [AllowAnonymous]
    public async Task<IActionResult> Register(RegisterRequest req)
    {
        var email = req.Email.Trim().ToLowerInvariant();

        // Email so khớp KHÔNG phân biệt hoa thường. `users.email` là UNIQUE
        // với collation `utf8mb4_unicode_ci`, nên CSDL coi `A@x.com` và
        // `a@x.com` là một — nhưng nếu lưu nguyên dạng người dùng gõ thì
        // đăng nhập bằng dạng khác sẽ phụ thuộc vào collation chứ không phải
        // vào mã, và điều đó đổi theo cấu hình máy chủ. Chuẩn hóa về chữ
        // thường ngay tại đây.
        if (await db.Users.AnyAsync(u => u.Email == email))
        {
            return Loi(StatusCodes.Status409Conflict,
                       ErrorCode.EmailAlreadyExists,
                       "Email này đã được đăng ký");
        }

        var now = DongHo.BayGio;
        var user = new Users
        {
            Id = Guid.NewGuid().ToString(),
            Email = email,
            // `role` mặc định `user`. KHÔNG nhận `role` từ thân yêu cầu —
            // đó là cách tự cấp quyền quản trị bằng một dòng JSON.
            Role = "user",
            IsActive = true,
            PasswordHash = BCrypt.Net.BCrypt.HashPassword(req.Password),
            DisplayName = req.DisplayName.Trim(),
            AvatarUrl = null,
            // `null` = chưa hoàn tất phiên vuốt thăm dò, nên còn ở Giai đoạn 0.
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
            // Hai yêu cầu đăng ký cùng một email cùng lúc: phép kiểm ở trên
            // cho cả hai đi qua, rồi `UNIQUE (email)` chặn cái thứ hai. Đây
            // là lý do ràng buộc UNIQUE phải tồn tại — phép kiểm ở tầng ứng
            // dụng không bao giờ nguyên tử.
            //
            // Không thể `await` trong mệnh đề `when` của `catch`, nên phải
            // tra lại trong thân. Và phải GỠ dòng vừa thêm khỏi ChangeTracker
            // trước khi truy vấn: nếu không, EF sẽ cố ghi lại nó ở lần
            // SaveChanges kế tiếp trong cùng phạm vi yêu cầu.
            db.Entry(user).State = EntityState.Detached;

            if (await db.Users.AnyAsync(u => u.Email == email))
            {
                return Loi(StatusCodes.Status409Conflict,
                           ErrorCode.EmailAlreadyExists,
                           "Email này đã được đăng ký");
            }
            throw;
        }

        var pair = await tokens.IssueAsync(user, onboarded: false);
        return StatusCode(StatusCodes.Status201Created,
                          Dung(pair, user));
    }

    // ── 7.1.2 Đăng nhập ──────────────────────────────────────────────────

    [HttpPost("login")]
    [AllowAnonymous]
    public async Task<IActionResult> Login(LoginRequest req)
    {
        var email = req.Email.Trim().ToLowerInvariant();
        var user = await db.Users.FirstOrDefaultAsync(u => u.Email == email);

        // So mật khẩu NGAY CẢ KHI không có người dùng nào, với một băm giả.
        //
        // Thoát sớm khi email không tồn tại làm lộ thông tin qua thời gian
        // trả lời: BCrypt mất khoảng 100 ms, nên "email không có" trả về tức
        // thì còn "sai mật khẩu" mất 100 ms. Đo thời gian là đọc được email
        // nào đã đăng ký — đúng thứ mà đặc tả §7.1.2 cố bịt bằng cách trả
        // chung một mã lỗi.
        var hash = user?.PasswordHash ?? BamGia;
        var dung = BCrypt.Net.BCrypt.Verify(req.Password, hash);

        if (user is null || !dung)
        {
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.InvalidCredentials,
                       "Email hoặc mật khẩu không đúng");
        }

        // Tài khoản bị khóa thì nói thẳng, không trả INVALID_CREDENTIALS:
        // người dùng thật cần biết để liên hệ quản trị, chứ không ngồi thử
        // lại mật khẩu. Phép kiểm đặt SAU khi đã xác thực mật khẩu — nếu
        // không thì ai cũng dò được tài khoản nào đang bị khóa.
        if (!user.IsActive)
        {
            return Loi(StatusCodes.Status403Forbidden,
                       ErrorCode.AccountDisabled,
                       "Tài khoản đã bị khóa, vui lòng liên hệ quản trị");
        }

        var pair = await tokens.IssueAsync(
            user, onboarded: user.OnboardingCompletedAt is not null);
        return Ok(Dung(pair, user));
    }

    /// <summary>
    /// Băm BCrypt của một mật khẩu không ai biết, dùng để so khi email không
    /// tồn tại. Giá trị cụ thể không quan trọng — chỉ cần nó là một băm
    /// BCrypt hợp lệ để <c>Verify</c> làm đủ số vòng.
    /// </summary>
    private const string BamGia =
        "$2a$11$N9qo8uLOickgx2ZMRZoMye" +
        "IjZAgcfl7p92ldGxad68LJZdL17lhWy";

    // ── 7.1.3 Làm mới token ──────────────────────────────────────────────

    [HttpPost("refresh")]
    [AllowAnonymous]
    public async Task<IActionResult> Refresh(RefreshRequest req)
    {
        var (ket_qua, dong) = await tokens.InspectAsync(req.RefreshToken);

        if (ket_qua == TokenService.RefreshOutcome.Reused && dong is not null)
        {
            // Token đã thu hồi mà được nộp lại. Hai khả năng, không phân
            // biệt được: người dùng thật mất mạng giữa lúc xoay vòng, hoặc
            // token đã rò. Cắt cả chuỗi.
            await tokens.RevokeFamilyAsync(dong.Id);
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.TokenInvalid,
                       "refreshToken đã bị thu hồi — vui lòng đăng nhập lại");
        }

        if (ket_qua != TokenService.RefreshOutcome.Valid || dong is null)
        {
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.TokenInvalid,
                       "refreshToken không hợp lệ hoặc đã hết hạn");
        }

        var user = await db.Users.FirstOrDefaultAsync(u => u.Id == dong.UserId);
        if (user is null || !user.IsActive)
        {
            // Tài khoản bị khóa sau khi token được phát. Thu hồi luôn, nếu
            // không thì người đó còn làm mới được token suốt 30 ngày.
            await tokens.RevokeAllAsync(dong.UserId);
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.TokenInvalid,
                       "Tài khoản không còn hoạt động");
        }

        var pair = await tokens.RotateAsync(
            user,
            onboarded: user.OnboardingCompletedAt is not null,
            idCu: dong.Id);

        if (pair is null)
        {
            // MẤT CUỘC ĐUA: giữa lượt `InspectAsync` ở trên và lượt đoạt dòng
            // trong `RotateAsync`, một yêu cầu khác đã thu hồi đúng token
            // này. Cùng một token được nộp hai lần — không phân biệt được
            // với rò rỉ, nên xử lý y như tái dùng.
            //
            // Nghĩa là nộp trùng (người dùng bấm hai lần, hoặc app thử lại
            // sau một gói mất) sẽ ĐĂNG XUẤT người dùng. Đó là giá của phép
            // phát hiện tái dùng, và nó đã được chấp nhận ở nhánh `Reused`
            // phía trên; chỗ này chỉ làm cho nó đúng cả khi có đồng thời.
            await tokens.RevokeFamilyAsync(dong.Id);
            return Loi(StatusCodes.Status401Unauthorized,
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

    // ── 7.1.4 Thông tin tài khoản ────────────────────────────────────────

    [HttpGet("me")]
    [Authorize]
    public async Task<IActionResult> Me()
    {
        var userId = User.FindFirst("sub")?.Value;
        if (userId is null)
        {
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        // Một truy vấn, không ba. Ba lượt đi CSDL cho một endpoint mà
        // Frontend gọi NGAY khi mở app là ba lượt mạng nội bộ trước khi màn
        // hình đầu tiên vẽ được.
        var ket_qua = await db.Users
            .Where(u => u.Id == userId)
            .Select(u => new
            {
                User = u,
                CoHoSo = db.HealthProfiles.Any(h => h.UserId == u.Id),
                GiaiDoan = db.UserPreferenceProfiles
                    .Where(p => p.UserId == u.Id)
                    .Select(p => p.Stage)
                    .FirstOrDefault(),
            })
            .FirstOrDefaultAsync();

        if (ket_qua is null)
        {
            // `TaiKhoanConHoatDongFilter` đã tra `is_active` trước khi vào
            // đây, nên nhánh này chỉ chạy khi người dùng bị xóa GIỮA hai
            // truy vấn. Giữ lại vì nếu không thì phải `!` một giá trị có
            // thể null.
            return Loi(StatusCodes.Status401Unauthorized,
                       ErrorCode.TokenInvalid, "Tài khoản không còn tồn tại");
        }

        // KHÔNG kiểm `IsActive` ở đây nữa. Bộ lọc toàn cục
        // `TaiKhoanConHoatDongFilter` làm việc đó cho MỌI endpoint đã xác
        // thực. Một phép kiểm thứ hai ở đây sẽ là mã chết trông như lưới an
        // toàn, và nó che đi việc 38 endpoint còn lại không có lưới nào.

        return Ok(new MeResponse
        {
            Id = ket_qua.User.Id,
            Email = ket_qua.User.Email,
            DisplayName = ket_qua.User.DisplayName,
            AvatarUrl = ket_qua.User.AvatarUrl,
            OnboardingCompletedAt = ket_qua.User.OnboardingCompletedAt,
            HasHealthProfile = ket_qua.CoHoSo,
            // Chưa có dòng `user_preference_profiles` nghĩa là chưa cho tín
            // hiệu nào — đó chính là Giai đoạn 0, `cold`.
            PreferenceStage = string.IsNullOrEmpty(ket_qua.GiaiDoan)
                ? "cold"
                : ket_qua.GiaiDoan,
            CreatedAt = ket_qua.User.CreatedAt,
        });
    }

    // ── chung ────────────────────────────────────────────────────────────

    private static AuthResponse Dung(TokenPair pair, Users user)
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
