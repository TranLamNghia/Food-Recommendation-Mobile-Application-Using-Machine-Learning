using System.ComponentModel.DataAnnotations;
using System.Text;

namespace Api.Auth;

/// <summary>
/// Chuỗi không được dài quá <paramref name="toi_da"/> <b>byte</b> khi mã hóa
/// UTF-8.
///
/// <para>Tồn tại vì BCrypt chỉ dùng <b>72 byte đầu</b> của mật khẩu và lặng
/// lẽ bỏ phần còn lại: hai mật khẩu khác nhau mà trùng 72 byte đầu sẽ đăng
/// nhập được lẫn nhau. <c>MaxLength</c> không đủ — nó đếm KÝ TỰ, còn một chữ
/// tiếng Việt có dấu chiếm 2–3 byte UTF-8, nên 72 ký tự có thể là hơn 200
/// byte và vẫn bị cắt.</para>
/// </summary>
public sealed class MaxUtf8BytesAttribute(int toi_da) : ValidationAttribute
{
    public override bool IsValid(object? value)
        => value is not string s
            || Encoding.UTF8.GetByteCount(s) <= toi_da;

    public override string FormatErrorMessage(string name)
        => $"Tối đa {toi_da} byte UTF-8 (chữ có dấu chiếm 2–3 byte mỗi chữ)";
}

/// <summary>Thân của <c>POST /auth/register</c> — đặc tả §7.1.1.</summary>
public sealed class RegisterRequest
{
    [Required(ErrorMessage = "Thiếu email")]
    [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
    [MaxLength(255, ErrorMessage = "Email tối đa 255 ký tự")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu")]
    [MinLength(8, ErrorMessage = "Mật khẩu tối thiểu 8 ký tự")]
    // Chặn trên 72 BYTE, bằng đúng giới hạn BCrypt dùng. Đặc tả §7.1.1 chỉ
    // nói "tối thiểu 8 ký tự, có chữ và số" nên không đòi chặn trên — nhưng
    // không có nó thì mật khẩu dài hơn bị cắt im lặng, và người dùng sẽ
    // không bao giờ biết phần sau không được tính.
    [MaxUtf8Bytes(72)]
    // Đặc tả §7.1.1 đòi "có chữ và số". `RegularExpression` chứ không kiểm
    // trong controller, để lỗi đi qua cùng một đường với mọi lỗi validation
    // khác và ra đúng vỏ `details` ở §2.5.
    [RegularExpression(@"^(?=.*[A-Za-z])(?=.*\d).+$",
        ErrorMessage = "Mật khẩu phải có cả chữ và số")]
    public string Password { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu tên hiển thị")]
    [MinLength(2, ErrorMessage = "Tên hiển thị tối thiểu 2 ký tự")]
    [MaxLength(100, ErrorMessage = "Tên hiển thị tối đa 100 ký tự")]
    public string DisplayName { get; set; } = string.Empty;
}

/// <summary>Thân của <c>POST /auth/login</c> — đặc tả §7.1.2.</summary>
public sealed class LoginRequest
{
    [Required(ErrorMessage = "Thiếu email")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu")]
    public string Password { get; set; } = string.Empty;
}

/// <summary>Thân của <c>POST /auth/refresh</c> — đặc tả §7.1.3.</summary>
public sealed class RefreshRequest
{
    [Required(ErrorMessage = "Thiếu refreshToken")]
    public string RefreshToken { get; set; } = string.Empty;
}

/// <summary>Người dùng trong phản hồi đăng ký và đăng nhập.</summary>
public sealed class UserSummary
{
    public string Id { get; init; } = string.Empty;
    public string Email { get; init; } = string.Empty;
    public string DisplayName { get; init; } = string.Empty;
    public string? AvatarUrl { get; init; }
    public DateTime? OnboardingCompletedAt { get; init; }
    public DateTime CreatedAt { get; init; }
}

/// <summary>Phản hồi của đăng ký và đăng nhập — §7.1.1 và §7.1.2.</summary>
public sealed class AuthResponse
{
    public string AccessToken { get; init; } = string.Empty;
    public string RefreshToken { get; init; } = string.Empty;
    public string TokenType { get; init; } = "Bearer";
    public int ExpiresIn { get; init; }
    public UserSummary User { get; init; } = new();
}

/// <summary>
/// Phản hồi của <c>POST /auth/refresh</c> — §7.1.3.
///
/// <para>Không có <c>user</c>, đúng theo đặc tả: Frontend đã có thông tin đó
/// từ lúc đăng nhập, và endpoint này chỉ đổi token.</para>
/// </summary>
public sealed class RefreshResponse
{
    public string AccessToken { get; init; } = string.Empty;
    public string RefreshToken { get; init; } = string.Empty;
    public string TokenType { get; init; } = "Bearer";
    public int ExpiresIn { get; init; }
}

/// <summary>Phản hồi của <c>GET /auth/me</c> — §7.1.4.</summary>
public sealed class MeResponse
{
    public string Id { get; init; } = string.Empty;
    public string Email { get; init; } = string.Empty;
    public string DisplayName { get; init; } = string.Empty;
    public string? AvatarUrl { get; init; }
    public DateTime? OnboardingCompletedAt { get; init; }
    public bool HasHealthProfile { get; init; }

    /// <summary>
    /// <c>cold</c> · <c>content</c> · <c>hybrid</c> · <c>ml</c>, đọc từ
    /// <c>user_preference_profiles.stage</c>.
    ///
    /// <para><c>cold</c> khi chưa có dòng nào: giai đoạn 0 là trạng thái của
    /// người chưa cho tín hiệu nào, không phải một trạng thái thiếu dữ liệu.
    /// Trả <c>null</c> ở đây sẽ buộc Frontend tự đoán, và nó sẽ đoán khác
    /// với <c>ml/serve.py</c>.</para>
    /// </summary>
    public string PreferenceStage { get; init; } = "cold";

    public DateTime CreatedAt { get; init; }
}
