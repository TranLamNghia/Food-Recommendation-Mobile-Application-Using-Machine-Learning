using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;

namespace Api.Http;

/// <summary>
/// The one error envelope for the whole API — specification §2.5.
///
/// <para>One structure for every error, rather than a type per endpoint. The
/// frontend reads <c>error.code</c> to decide what to do (specification §4
/// states what the frontend should do for each code), so <c>code</c> has to be
/// a stable string, not a Vietnamese sentence — the Vietnamese sentence is
/// <c>message</c>, and editing it must not break the frontend.</para>
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
        /// Present only on <c>VALIDATION_FAILED</c>; omitted for every other
        /// error.
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
/// The error code catalogue — specification §4.
///
/// <para>Constants rather than strings scattered across the controllers. Five
/// invented error codes once made it into this project's flow diagrams
/// (<c>EMAIL_EXISTS</c> where the catalogue says <c>EMAIL_ALREADY_EXISTS</c>,
/// plus four more) and none of them broke anything — they merely described a
/// system that did not exist. Typing the strings by hand in a controller
/// reopens that gap.</para>
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

    /// <summary>
    /// <c>503</c>: the ML service could not be reached, so no recommendation
    /// could be produced. The client shows "try again later".
    ///
    /// <para>Its own code rather than <c>INTERNAL_ERROR</c>, because the
    /// client's answer differs: this one is worth retrying and nothing is
    /// broken on the user's side, while <c>INTERNAL_ERROR</c> is a bug.
    /// Specification §4 does not list it — §8.1 assumed the backend would
    /// quietly fall back to rule-based scoring instead of telling anyone,
    /// and that assumption was dropped deliberately. The catalogue in §4
    /// needs a row for it.</para>
    ///
    /// <para><b>Not</b> for <c>NO_SCOREABLE_CANDIDATE</c> from the ML
    /// service. That is the F1 safety layer reporting that this user may eat
    /// none of the foods, which retrying cannot change; it is
    /// <see cref="RuleTooRestrictive"/> / <see cref="NoFeasiblePlan"/>.</para>
    /// </summary>
    public const string MlUnavailable = "ML_UNAVAILABLE";

    /// <summary>
    /// <c>409</c>: the user asked for a dish not to be suggested, and it is
    /// the last one left in a role some meal cannot be assembled without —
    /// so honouring the request would make a plan impossible to build, not
    /// merely poorer.
    ///
    /// <para>Its own code rather than <see cref="RuleTooRestrictive"/>,
    /// which reports the same shape of dead end arrived at by a <b>medical
    /// rule</b>. The difference matters to the client because the remedy
    /// does: this one is undone by picking a different dish to block, that
    /// one by revisiting a declared condition. Not in §4's catalogue —
    /// neither is the feature.</para>
    /// </summary>
    public const string BlockWouldEmptyMeal = "BLOCK_WOULD_EMPTY_MEAL";
}

/// <summary>Builds an error response in exactly the §2.5 envelope.</summary>
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
