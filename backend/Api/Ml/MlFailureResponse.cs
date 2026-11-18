using Api.Http;
using Microsoft.AspNetCore.Mvc;

namespace Api.Ml;

/// <summary>
/// Turns an <see cref="MlFailure"/> into the one error envelope of
/// specification §2.5.
///
/// <para><b>This is where the decision lives.</b> §8.1 originally had the
/// backend answer a failed <c>/predict</c> by building a meal plan from the
/// rules alone and recording
/// <c>generation_source = "rule_based"</c> — soft degradation, invisible to
/// the user. That was dropped: the user is now told the recommendation system
/// is unavailable and asked to try again. The reason is that a rule-based
/// plan looks exactly like a real one, so a backend quietly serving them
/// cannot be told apart from a working system, by the user or by anyone
/// reading the logs.</para>
///
/// <para>One place rather than a <c>switch</c> in every controller. The
/// mapping below is the difference between "the ML layer is down" and "the ML
/// layer answered, and the answer is no", and getting it wrong at a single
/// endpoint is the F1 safety filter failing open at that endpoint.</para>
///
/// <para>Note on language: every <c>message</c> here is Vietnamese, because
/// these are the <c>error.message</c> of §2.5 that end users read. The
/// English in <see cref="MlFailure.Detail"/> is developer-facing and is
/// <b>never</b> sent: it can carry a user id, a dataset version or a MySQL
/// error. It goes to the log, and the user gets the <c>traceId</c> that finds
/// it.</para>
/// </summary>
public static class MlFailureResponse
{
    /// <summary>
    /// The §2.5 response for a failed recommendation call.
    /// </summary>
    /// <param name="failure">What the ML client reported.</param>
    /// <param name="traceId">
    /// <c>HttpContext.TraceIdentifier</c> — the only thing that connects what
    /// the user saw to the line in the log.
    /// </param>
    /// <param name="foodsBeforeF1">
    /// From <see cref="MlPredictResponse.NFoodsBeforeF1"/> when it is known,
    /// for the <c>NO_FEASIBLE_PLAN</c> message. It is not known on this path
    /// — the call failed — so the caller passes it only if an earlier call
    /// reported it.
    /// </param>
    public static ObjectResult ToActionResult(
        this MlFailure failure, string traceId, int? foodsBeforeF1 = null)
        => failure.Kind switch
        {
            // ── The ML layer is not available ──
            //
            // All of these are `IsDegradable`, and they all now become the
            // same thing the user sees: try again later. They are still
            // separate kinds because they are not the same thing in the LOG
            // — a missing key and a 2 s timeout need different fixing.
            MlFailureKind.Disabled
                or MlFailureKind.Timeout
                or MlFailureKind.Unreachable
                or MlFailureKind.Unauthorized
                or MlFailureKind.NoActiveModel
                or MlFailureKind.ServerError
                or MlFailureKind.MalformedResponse
                => ApiProblem.Make(
                    StatusCodes.Status503ServiceUnavailable,
                    ErrorCode.MlUnavailable,
                    "Hệ thống gợi ý đang tạm thời không khả dụng. Vui lòng "
                    + "thử lại sau ít phút.",
                    traceId),

            // ── The ML layer answered, and the answer is no ──
            //
            // The F1 safety layer removed every food. Retrying changes
            // nothing, so this must NOT read as "the system is having
            // trouble" — that would have the user tap again all afternoon.
            MlFailureKind.NoScoreableCandidate
                => ApiProblem.Make(
                    StatusCodes.Status422UnprocessableEntity,
                    ErrorCode.NoFeasiblePlan,
                    "Các điều kiện sức khỏe đã khai báo loại hết số món "
                    + (foodsBeforeF1 is null
                        ? "hiện có"
                        : $"trong {foodsBeforeF1} món hiện có")
                    + ", nên chưa dựng được thực đơn. Vui lòng kiểm tra lại "
                    + "phần khai báo bệnh lý và dị ứng, hoặc liên hệ hỗ trợ.",
                    traceId),

            // Not enough usable swipes to build a preference vector — §8.2's
            // own `422`. The catalogue already has a code for it, and the
            // answer is an action the user can take.
            MlFailureKind.InsufficientSignals
                => ApiProblem.Make(
                    StatusCodes.Status422UnprocessableEntity,
                    ErrorCode.OnboardingInsufficient,
                    "Chưa đủ dữ liệu về sở thích để dựng hồ sơ. Vui lòng "
                    + "chọn thêm món ở bước khảo sát khẩu vị.",
                    traceId),

            MlFailureKind.UserNotFound
                => ApiProblem.Make(
                    StatusCodes.Status404NotFound,
                    ErrorCode.NotFound,
                    "Không tìm thấy người dùng.",
                    traceId),

            // ── Everything else is a bug on this side ──
            //
            // `BadRequest` means this backend sent a body the ML service
            // refused; `DatasetNotFound` and `TrainingInProgress` belong to
            // the admin retrain path, which has to handle them itself rather
            // than reach this helper — §8.3 answers `409`, and telling an
            // administrator "lỗi máy chủ" when a training run is simply
            // already going would hide the real reason.
            //
            // A generic 500 on purpose: the detail stays in the log. Anything
            // more specific sent to the client would be describing this
            // project's internals to whoever asked.
            _ => ApiProblem.Make(
                StatusCodes.Status500InternalServerError,
                ErrorCode.InternalError,
                "Lỗi máy chủ, vui lòng thử lại",
                traceId),
        };

    /// <summary>
    /// Whether this failure should be logged as a fault of the system rather
    /// than as a normal answer.
    ///
    /// <para><see cref="MlFailureKind.NoScoreableCandidate"/> and
    /// <see cref="MlFailureKind.InsufficientSignals"/> are not faults: the
    /// system worked and the answer was no. Logging them as errors trains
    /// everyone to ignore the error log, which is how the ones that matter
    /// get missed.</para>
    /// </summary>
    public static bool IsSystemFault(this MlFailure failure)
        => failure.Kind is not (MlFailureKind.NoScoreableCandidate
            or MlFailureKind.InsufficientSignals
            or MlFailureKind.UserNotFound);
}
