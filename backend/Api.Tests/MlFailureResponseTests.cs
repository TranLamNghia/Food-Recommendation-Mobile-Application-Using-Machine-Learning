using Api.Http;
using Api.Ml;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Api.Tests;

/// <summary>
/// What the user is told when the ML layer does not produce a recommendation.
///
/// <para>The decision being tested is the one that replaced §8.1's soft
/// degradation: the backend no longer builds a rule-based plan behind the
/// user's back, it says the recommendation system is unavailable. So the
/// failing cases now have a visible, testable answer — which is the whole
/// reason to prefer it.</para>
///
/// <para>The split these tests defend: "the ML layer is down" (retry later)
/// versus "the ML layer answered, and the answer is no" (retrying is
/// pointless, and scoring the foods anyway would be the F1 safety filter
/// failing open).</para>
/// </summary>
public class MlFailureResponseTests
{
    private const string Trace = "trace-0001";

    private static MlFailure Failure(MlFailureKind kind)
        => new(kind, null, null, "developer-facing detail");

    private static ApiError Body(ObjectResult result)
    {
        var error = Assert.IsType<ApiError>(result.Value);
        return error;
    }

    /// <summary>
    /// Every degradable kind becomes one answer: 503, <c>ML_UNAVAILABLE</c>,
    /// "try again later". They stay separate kinds for the LOG, where a
    /// missing key and a 2 s timeout need different fixing.
    /// </summary>
    [Theory]
    [InlineData(MlFailureKind.Disabled)]
    [InlineData(MlFailureKind.Timeout)]
    [InlineData(MlFailureKind.Unreachable)]
    [InlineData(MlFailureKind.Unauthorized)]
    [InlineData(MlFailureKind.NoActiveModel)]
    [InlineData(MlFailureKind.ServerError)]
    [InlineData(MlFailureKind.MalformedResponse)]
    public void An_unavailable_ml_layer_is_a_503_asking_to_retry(
        MlFailureKind kind)
    {
        var failure = Failure(kind);
        var result = failure.ToActionResult(Trace);

        Assert.True(failure.IsDegradable);
        Assert.Equal(
            StatusCodes.Status503ServiceUnavailable, result.StatusCode);
        Assert.Equal(ErrorCode.MlUnavailable, Body(result).Error.Code);
        Assert.Contains("thử lại", Body(result).Error.Message);
        Assert.Equal(Trace, Body(result).Error.TraceId);
    }

    /// <summary>
    /// The expensive confusion, in the form the user would see it. If the F1
    /// filter removing every food read as "the system is having trouble, try
    /// again", the user would tap again all afternoon — nothing about their
    /// medical conditions changes between taps.
    /// </summary>
    [Fact]
    public void Every_food_excluded_is_not_a_retry_message()
    {
        var failure = Failure(MlFailureKind.NoScoreableCandidate);
        var result = failure.ToActionResult(Trace, foodsBeforeF1: 318);

        Assert.False(failure.IsDegradable);
        Assert.Equal(
            StatusCodes.Status422UnprocessableEntity, result.StatusCode);
        Assert.Equal(ErrorCode.NoFeasiblePlan, Body(result).Error.Code);

        var message = Body(result).Error.Message;
        Assert.DoesNotContain("thử lại", message);
        // The number is what makes it an explanation rather than a refusal.
        Assert.Contains("318", message);
        Assert.Contains("bệnh lý", message);
    }

    [Fact]
    public void Every_food_excluded_still_reads_without_the_count()
    {
        var result = Failure(MlFailureKind.NoScoreableCandidate)
            .ToActionResult(Trace);

        Assert.Equal(ErrorCode.NoFeasiblePlan, Body(result).Error.Code);
        Assert.Contains("hiện có", Body(result).Error.Message);
    }

    [Fact]
    public void Too_few_swipes_points_at_the_taste_survey()
    {
        var result = Failure(MlFailureKind.InsufficientSignals)
            .ToActionResult(Trace);

        Assert.Equal(
            StatusCodes.Status422UnprocessableEntity, result.StatusCode);
        Assert.Equal(
            ErrorCode.OnboardingInsufficient, Body(result).Error.Code);
        Assert.Contains("khẩu vị", Body(result).Error.Message);
    }

    [Fact]
    public void A_missing_user_is_a_404()
    {
        var result = Failure(MlFailureKind.UserNotFound)
            .ToActionResult(Trace);

        Assert.Equal(StatusCodes.Status404NotFound, result.StatusCode);
        Assert.Equal(ErrorCode.NotFound, Body(result).Error.Code);
    }

    /// <summary>
    /// A body the ML service refused is a bug on this side. The user gets the
    /// generic 500 and the traceId; the detail stays in the log.
    /// </summary>
    [Theory]
    [InlineData(MlFailureKind.BadRequest)]
    [InlineData(MlFailureKind.DatasetNotFound)]
    [InlineData(MlFailureKind.TrainingInProgress)]
    public void Our_own_bugs_are_a_generic_500(MlFailureKind kind)
    {
        var result = Failure(kind).ToActionResult(Trace);

        Assert.Equal(
            StatusCodes.Status500InternalServerError, result.StatusCode);
        Assert.Equal(ErrorCode.InternalError, Body(result).Error.Code);
    }

    /// <summary>
    /// <c>MlFailure.Detail</c> is English written for a developer and can
    /// carry a user id, a dataset version or a MySQL error. It must never
    /// reach a client — the user gets a Vietnamese sentence and the traceId
    /// that finds the real line in the log.
    /// </summary>
    [Fact]
    public void The_developer_detail_is_never_sent_to_the_client()
    {
        var failure = new MlFailure(
            MlFailureKind.Unreachable,
            null,
            null,
            "Could not reach http://ml.internal:8000 for user "
            + "00000001-0000-4000-8000-000000000000: connection refused");

        var body = Body(failure.ToActionResult(Trace));

        Assert.DoesNotContain("00000001", body.Error.Message);
        Assert.DoesNotContain("ml.internal", body.Error.Message);
        Assert.DoesNotContain("connection refused", body.Error.Message);
        Assert.Null(body.Error.Details);
        Assert.Equal(Trace, body.Error.TraceId);
    }

    /// <summary>
    /// "The answer was no" is not a fault. Logging it as one teaches everyone
    /// to ignore the error log, which is how the faults that matter get
    /// missed.
    /// </summary>
    [Fact]
    public void An_answer_of_no_is_not_logged_as_a_system_fault()
    {
        Assert.False(
            Failure(MlFailureKind.NoScoreableCandidate).IsSystemFault());
        Assert.False(
            Failure(MlFailureKind.InsufficientSignals).IsSystemFault());
        Assert.False(Failure(MlFailureKind.UserNotFound).IsSystemFault());

        Assert.True(Failure(MlFailureKind.Timeout).IsSystemFault());
        Assert.True(Failure(MlFailureKind.Disabled).IsSystemFault());
        Assert.True(Failure(MlFailureKind.BadRequest).IsSystemFault());
    }

    /// <summary>
    /// Every kind has to be mapped. A kind added later without a thought
    /// falls into the 500 branch, which is the safe default here — but it
    /// must not fall through to an exception while a user waits for a meal
    /// plan.
    /// </summary>
    [Fact]
    public void Every_failure_kind_maps_to_a_response()
    {
        foreach (var kind in Enum.GetValues<MlFailureKind>())
        {
            var result = Failure(kind).ToActionResult(Trace);
            Assert.NotNull(result.StatusCode);
            Assert.InRange(result.StatusCode!.Value, 400, 599);
            Assert.False(
                string.IsNullOrWhiteSpace(Body(result).Error.Code));
            Assert.False(
                string.IsNullOrWhiteSpace(Body(result).Error.Message));
        }
    }
}
