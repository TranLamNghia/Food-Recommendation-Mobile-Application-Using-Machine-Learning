using System.ComponentModel.DataAnnotations;
using System.Text;

namespace Api.Auth;

/// <summary>
/// The string must not be longer than <paramref name="maxBytes"/>
/// <b>bytes</b> once encoded as UTF-8.
///
/// <para>It exists because BCrypt only uses the <b>first 72 bytes</b> of a
/// password and silently drops the rest: two different passwords that share
/// their first 72 bytes can each log into the other's account.
/// <c>MaxLength</c> is not enough — it counts CHARACTERS, and an accented
/// Vietnamese letter takes 2–3 UTF-8 bytes, so 72 characters can be more than
/// 200 bytes and still get truncated.</para>
///
/// <para>Note on language: the message returned by
/// <see cref="FormatErrorMessage"/> stays in Vietnamese, as do every
/// <c>ErrorMessage</c> in this file — they are the <c>error.details[].message</c>
/// strings of specification §2.5, which end users read. The stable part the
/// frontend branches on is <c>error.code</c>, not these sentences.</para>
/// </summary>
public sealed class MaxUtf8BytesAttribute(int maxBytes) : ValidationAttribute
{
    public override bool IsValid(object? value)
        => value is not string s
            || Encoding.UTF8.GetByteCount(s) <= maxBytes;

    public override string FormatErrorMessage(string name)
        => $"Tối đa {maxBytes} byte UTF-8 (chữ có dấu chiếm 2–3 byte mỗi chữ)";
}

/// <summary>Body of <c>POST /auth/register</c> — specification
/// §7.1.1.</summary>
public sealed class RegisterRequest
{
    [Required(ErrorMessage = "Thiếu email")]
    [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
    [MaxLength(255, ErrorMessage = "Email tối đa 255 ký tự")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu")]
    [MinLength(PasswordRules.MinLength, ErrorMessage = PasswordRules.TooShort)]
    // An upper bound of 72 BYTES, exactly the limit BCrypt uses.
    // Specification §7.1.1 only says "at least 8 characters, with letters and
    // digits", so it does not ask for an upper bound — but without one, a
    // longer password gets silently truncated and the user would never know
    // the tail of it was not counted.
    [MaxUtf8Bytes(PasswordRules.MaxBytes)]
    // Specification §7.1.1 requires "letters and digits". A
    // `RegularExpression` rather than a check in the controller, so the error
    // travels the same path as every other validation error and comes out in
    // the §2.5 `details` envelope.
    [RegularExpression(PasswordRules.Pattern,
        ErrorMessage = PasswordRules.NeedsLettersAndDigits)]
    public string Password { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu tên hiển thị")]
    [MinLength(2, ErrorMessage = "Tên hiển thị tối thiểu 2 ký tự")]
    [MaxLength(100, ErrorMessage = "Tên hiển thị tối đa 100 ký tự")]
    public string DisplayName { get; set; } = string.Empty;
}

/// <summary>
/// Body of <c>PUT /auth/me</c>.
///
/// <para><b>Not in the specification.</b> §6 lists seven authentication
/// endpoints and none of them changes the account's own details, while the
/// app has a settings screen that edits the display name. Without this the
/// name could be typed and would be gone on the next launch.</para>
///
/// <para>The display name is the only field. The email identifies the
/// account and changing it is a different operation with its own
/// confirmation flow; the password has §7.1.7 already.</para>
/// </summary>
public sealed class UpdateAccountRequest
{
    // The same bounds as registration, deliberately: a name that could not
    // have been registered must not be reachable by editing either.
    [Required(ErrorMessage = "Thiếu tên hiển thị")]
    [MinLength(2, ErrorMessage = "Tên hiển thị tối thiểu 2 ký tự")]
    [MaxLength(100, ErrorMessage = "Tên hiển thị tối đa 100 ký tự")]
    public string DisplayName { get; set; } = string.Empty;
}

/// <summary>Body of <c>POST /auth/login</c> — specification §7.1.2.</summary>
public sealed class LoginRequest
{
    [Required(ErrorMessage = "Thiếu email")]
    public string Email { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu")]
    public string Password { get; set; } = string.Empty;
}

/// <summary>Body of <c>POST /auth/refresh</c> — specification
/// §7.1.3.</summary>
public sealed class RefreshRequest
{
    [Required(ErrorMessage = "Thiếu refreshToken")]
    public string RefreshToken { get; set; } = string.Empty;
}

/// <summary>The user as returned by register and login.</summary>
public sealed class UserSummary
{
    public string Id { get; init; } = string.Empty;
    public string Email { get; init; } = string.Empty;
    public string DisplayName { get; init; } = string.Empty;
    public string? AvatarUrl { get; init; }
    public DateTime? OnboardingCompletedAt { get; init; }
    public DateTime CreatedAt { get; init; }
}

/// <summary>The register and login response — §7.1.1 and §7.1.2.</summary>
public sealed class AuthResponse
{
    public string AccessToken { get; init; } = string.Empty;
    public string RefreshToken { get; init; } = string.Empty;
    public string TokenType { get; init; } = "Bearer";
    public int ExpiresIn { get; init; }
    public UserSummary User { get; init; } = new();
}

/// <summary>
/// The <c>POST /auth/refresh</c> response — §7.1.3.
///
/// <para>No <c>user</c>, exactly as the specification says: the frontend
/// already has that from logging in, and this endpoint only exchanges
/// tokens.</para>
/// </summary>
public sealed class RefreshResponse
{
    public string AccessToken { get; init; } = string.Empty;
    public string RefreshToken { get; init; } = string.Empty;
    public string TokenType { get; init; } = "Bearer";
    public int ExpiresIn { get; init; }
}

/// <summary>The <c>GET /auth/me</c> response — §7.1.4.</summary>
public sealed class MeResponse
{
    public string Id { get; init; } = string.Empty;
    public string Email { get; init; } = string.Empty;
    public string DisplayName { get; init; } = string.Empty;
    public string? AvatarUrl { get; init; }
    public DateTime? OnboardingCompletedAt { get; init; }
    public bool HasHealthProfile { get; init; }

    /// <summary>
    /// <c>cold</c> · <c>content</c> · <c>hybrid</c> · <c>ml</c>, read from
    /// <c>user_preference_profiles.stage</c>.
    ///
    /// <para><c>cold</c> when there is no row yet: stage 0 is the state of
    /// someone who has given no signal, not a state of missing data.
    /// Returning <c>null</c> here would force the frontend to guess, and it
    /// would guess differently from <c>ml/serve.py</c>.</para>
    /// </summary>
    public string PreferenceStage { get; init; } = "cold";

    public DateTime CreatedAt { get; init; }
}
