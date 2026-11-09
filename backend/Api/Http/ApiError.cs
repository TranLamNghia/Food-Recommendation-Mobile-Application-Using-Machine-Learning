using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;

namespace Api.Http;

/// <summary>
/// Vỏ lỗi duy nhất của toàn bộ API — đặc tả §2.5.
///
/// <para>Một cấu trúc cho mọi lỗi, không phải mỗi endpoint một kiểu. Frontend
/// bóc <c>error.code</c> ra để quyết định làm gì (đặc tả §4 nói rõ từng mã
/// Frontend nên làm gì), nên <c>code</c> phải là chuỗi ổn định, không phải
/// câu tiếng Việt — câu tiếng Việt là <c>message</c>, và sửa nó không được
/// làm hỏng Frontend.</para>
/// </summary>
public sealed class ApiError
{
    [JsonPropertyName("error")]
    public ErrorBody Error { get; init; } = new();

    public sealed class ErrorBody
    {
        public string Code { get; init; } = string.Empty;
        public string Message { get; init; } = string.Empty;

        /// <summary>
        /// Chỉ có ở <c>VALIDATION_FAILED</c>; các lỗi khác bỏ trống.
        /// </summary>
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public List<FieldError>? Details { get; init; }

        public string TraceId { get; init; } = string.Empty;
    }

    public sealed class FieldError
    {
        public string Field { get; init; } = string.Empty;
        public string Message { get; init; } = string.Empty;
    }
}

/// <summary>
/// Danh mục mã lỗi — đặc tả §4.
///
/// <para>Hằng số chứ không phải chuỗi rải khắp controller. Năm mã lỗi bịa
/// từng lọt vào sơ đồ luồng của đề tài này (<c>EMAIL_EXISTS</c> trong khi
/// danh mục ghi <c>EMAIL_ALREADY_EXISTS</c>, và bốn mã nữa) và không mã nào
/// gây lỗi gì — chúng chỉ mô tả một hệ thống không tồn tại. Gõ chuỗi tay ở
/// controller thì khoảng sai đó mở lại.</para>
/// </summary>
public static class ErrorCode
{
    public const string ValidationFailed = "VALIDATION_FAILED";
    public const string InvalidCredentials = "INVALID_CREDENTIALS";
    public const string TokenExpired = "TOKEN_EXPIRED";
    public const string TokenInvalid = "TOKEN_INVALID";
    public const string Forbidden = "FORBIDDEN";
    public const string NotFound = "NOT_FOUND";
    public const string EmailAlreadyExists = "EMAIL_ALREADY_EXISTS";
    public const string ProfileRequired = "PROFILE_REQUIRED";
    public const string OnboardingRequired = "ONBOARDING_REQUIRED";
    public const string OnboardingAlreadyCompleted =
        "ONBOARDING_ALREADY_COMPLETED";
    public const string OnboardingInsufficient = "ONBOARDING_INSUFFICIENT";
    public const string FeedbackNotAllowed = "FEEDBACK_NOT_ALLOWED";
    public const string MealPlanExists = "MEAL_PLAN_EXISTS";
    public const string NoFeasiblePlan = "NO_FEASIBLE_PLAN";
    public const string AccountDisabled = "ACCOUNT_DISABLED";
    public const string AdminRequired = "ADMIN_REQUIRED";
    public const string ResetTokenInvalid = "RESET_TOKEN_INVALID";
    public const string FoodAlreadyExists = "FOOD_ALREADY_EXISTS";
    public const string RuleTooRestrictive = "RULE_TOO_RESTRICTIVE";
    public const string RateLimited = "RATE_LIMITED";
    public const string InternalError = "INTERNAL_ERROR";
}

/// <summary>Dựng phản hồi lỗi theo đúng vỏ ở §2.5.</summary>
public static class ApiProblem
{
    public static ObjectResult Make(
        int status,
        string code,
        string message,
        string traceId,
        List<ApiError.FieldError>? details = null)
        => new(new ApiError
        {
            Error = new ApiError.ErrorBody
            {
                Code = code,
                Message = message,
                Details = details,
                TraceId = traceId,
            },
        })
        { StatusCode = status };
}
