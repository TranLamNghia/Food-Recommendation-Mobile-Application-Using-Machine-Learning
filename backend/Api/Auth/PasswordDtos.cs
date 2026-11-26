using System.ComponentModel.DataAnnotations;

namespace Api.Auth;

/// <summary>
/// The password rules of §7.1.1, in one place for every endpoint that takes
/// a new password — registration, §7.1.6 and §7.1.7. A rule that could be
/// dodged by registering with one password and resetting to a weaker one is
/// not a rule.
/// </summary>
public static class PasswordRules
{
    public const int MinLength = 8;

    /// <summary>BCrypt reads only the first 72 bytes — see
    /// <see cref="MaxUtf8BytesAttribute"/>.</summary>
    public const int MaxBytes = 72;

    /// <summary>"Có chữ và số" — at least one letter and one digit.</summary>
    public const string Pattern = @"^(?=.*[A-Za-z])(?=.*\d).+$";

    public const string TooShort = "Mật khẩu tối thiểu 8 ký tự";
    public const string NeedsLettersAndDigits = "Mật khẩu phải có cả chữ và số";
}

/// <summary>Body of <c>POST /auth/forgot-password</c> — §7.1.5.</summary>
public sealed class ForgotPasswordRequest
{
    [Required(ErrorMessage = "Thiếu email")]
    [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
    [MaxLength(255, ErrorMessage = "Email tối đa 255 ký tự")]
    public string Email { get; set; } = string.Empty;
}

/// <summary>Body of <c>POST /auth/reset-password</c> — §7.1.6.</summary>
public sealed class ResetPasswordRequest
{
    [Required(ErrorMessage = "Thiếu mã đặt lại")]
    // A real code is 43 characters. The cap only stops a megabyte of text
    // being hashed for nothing; a wrong length is answered like any wrong
    // code, as RESET_TOKEN_INVALID, so the length is not a hint.
    [MaxLength(200, ErrorMessage = "Mã đặt lại không hợp lệ")]
    public string Token { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu mới")]
    [MinLength(PasswordRules.MinLength, ErrorMessage = PasswordRules.TooShort)]
    [MaxUtf8Bytes(PasswordRules.MaxBytes)]
    [RegularExpression(PasswordRules.Pattern,
        ErrorMessage = PasswordRules.NeedsLettersAndDigits)]
    public string NewPassword { get; set; } = string.Empty;
}

/// <summary>Body of <c>PUT /auth/password</c> — §7.1.7.</summary>
public sealed class ChangePasswordRequest
{
    // No rules on the current password beyond being there: it is checked
    // against the hash, and a password registered before a rule existed must
    // still be able to prove itself.
    [Required(ErrorMessage = "Thiếu mật khẩu hiện tại")]
    public string CurrentPassword { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mật khẩu mới")]
    [MinLength(PasswordRules.MinLength, ErrorMessage = PasswordRules.TooShort)]
    [MaxUtf8Bytes(PasswordRules.MaxBytes)]
    [RegularExpression(PasswordRules.Pattern,
        ErrorMessage = PasswordRules.NeedsLettersAndDigits)]
    public string NewPassword { get; set; } = string.Empty;
}

/// <summary>The one-sentence answer the three password endpoints give.</summary>
public sealed class MessageResponse
{
    public string Message { get; init; } = string.Empty;
}
