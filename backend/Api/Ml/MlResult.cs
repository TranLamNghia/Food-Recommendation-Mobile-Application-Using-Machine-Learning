namespace Api.Ml;

/// <summary>
/// Why a call to the ML service did not return an answer.
///
/// <para>The split that matters is <see cref="MlFailure.IsDegradable"/>: a
/// failure is either "the ML layer is not available right now", which
/// specification §8.1 answers by scoring without it and recording
/// <c>generation_source = "rule_based"</c>, or it is "the ML layer answered,
/// and the answer is that this request cannot be served", which has to reach
/// the user. Collapsing the two is the expensive mistake here — see
/// <see cref="NoScoreableCandidate"/>.</para>
/// </summary>
public enum MlFailureKind
{
    /// <summary>No <c>ML_INTERNAL_KEY</c> on this server. Degradable.</summary>
    Disabled,

    /// <summary>The 2 s budget of §8.1 ran out. Degradable.</summary>
    Timeout,

    /// <summary>
    /// Connection refused, DNS failure, socket reset — the service is not
    /// listening. Degradable.
    /// </summary>
    Unreachable,

    /// <summary>
    /// <c>401</c>: the two keys do not match. Degradable in behaviour,
    /// because the user must still get a plan, but it is a deployment fault
    /// and is logged at error level every time.
    /// </summary>
    Unauthorized,

    /// <summary>
    /// <c>400</c>: the body this backend sent is not valid. NOT degradable —
    /// it is a bug on this side, and silently serving rule-based scores
    /// would hide it for as long as the code lives.
    /// </summary>
    BadRequest,

    /// <summary><c>404 USER_NOT_FOUND</c>. Not degradable.</summary>
    UserNotFound,

    /// <summary><c>404 DATASET_NOT_FOUND</c>, from /train. Not degradable.</summary>
    DatasetNotFound,

    /// <summary>
    /// <c>422 NO_SCOREABLE_CANDIDATE</c>: the F1 filter removed every food
    /// sent.
    ///
    /// <para><b>Never degrade on this one.</b> It is not the ML layer being
    /// unavailable — it is the safety layer saying this user may eat none of
    /// these foods. Falling back to rule-based scoring here would score a
    /// candidate set the F1 filter has already rejected, which is the safety
    /// layer failing open. It maps to the public API's
    /// <c>422 NO_FEASIBLE_PLAN</c> / <c>RULE_TOO_RESTRICTIVE</c>, not to a
    /// plan.</para>
    /// </summary>
    NoScoreableCandidate,

    /// <summary>
    /// <c>422 INSUFFICIENT_SIGNALS</c>, from /rebuild: no usable swipe left
    /// after the F1 filter. Not degradable — §8.2 gives it its own status.
    /// </summary>
    InsufficientSignals,

    /// <summary>
    /// <c>422 PROFILE_REQUIRED</c>, from /plan: this user has no
    /// <c>health_profiles</c> row, so Step 1 has never run and there is no
    /// energy target to build a plan against.
    ///
    /// <para>Not degradable, and <b>not</b> a server fault: nothing is wrong
    /// with the ML service, the user simply has to fill in the profile form
    /// first. It maps to the public <c>409 PROFILE_REQUIRED</c>, which §4
    /// already defines, and reporting it as "try again later" would have the
    /// user retry forever on a screen that can never succeed.</para>
    /// </summary>
    ProfileRequired,

    /// <summary>
    /// <c>422 ONBOARDING_REQUIRED</c>, from /plan: the profile exists but
    /// <c>daily_calories_target</c> is NULL. Not degradable, for the same
    /// reason as <see cref="ProfileRequired"/>.
    /// </summary>
    OnboardingRequired,

    /// <summary><c>409 TRAINING_IN_PROGRESS</c>. Not degradable.</summary>
    TrainingInProgress,

    /// <summary>
    /// <c>503</c>: nothing can be scored at all. Degradable — this is
    /// exactly the case §8.1 describes.
    ///
    /// <para>Note that a missing model alone does NOT produce this.
    /// <c>ml/serve.py</c> falls back to Stage 1 by itself and still returns
    /// content-based scores with <c>200</c>; the header comment of
    /// <c>ml/api.py</c> measures the difference as 0.862 vs 0.694 nDCG@5. So
    /// seeing this often means something worse than "the model is
    /// stale".</para>
    /// </summary>
    NoActiveModel,

    /// <summary>Any other 5xx. Degradable.</summary>
    ServerError,

    /// <summary>
    /// A <c>200</c> whose body would not parse, or parsed to <c>null</c>.
    /// Degradable, and logged: it means the two sides disagree about the
    /// contract.
    /// </summary>
    MalformedResponse,
}

/// <summary>A failed call, with enough detail to log and to branch on.</summary>
/// <param name="Kind">Which failure, and therefore whether to degrade.</param>
/// <param name="Status">
/// The HTTP status, when there was a response. <c>null</c> for a timeout, an
/// unreachable service, or a disabled client.
/// </param>
/// <param name="Code">
/// <c>error.code</c> out of the §2.5 envelope the ML service returns, when
/// present. A stable string, safe to branch on.
/// </param>
/// <param name="Detail">
/// Developer-facing English, for the log. <b>Never</b> put this in an
/// <c>error.message</c> sent to a client: it can name a user id, a dataset
/// version, or a database row.
/// </param>
public sealed record MlFailure(
    MlFailureKind Kind,
    int? Status,
    string? Code,
    string Detail)
{
    /// <summary>
    /// Whether the caller should carry on without the ML layer (§8.1's soft
    /// degradation) rather than surface an error.
    ///
    /// <para>Written as an explicit list of the degradable kinds, not as a
    /// <c>default: true</c> switch. A kind added later then has to be
    /// classified deliberately — the wrong default here is the F1 filter
    /// failing open, and it would fail open silently.</para>
    /// </summary>
    public bool IsDegradable => Kind is MlFailureKind.Disabled
        or MlFailureKind.Timeout
        or MlFailureKind.Unreachable
        or MlFailureKind.Unauthorized
        or MlFailureKind.NoActiveModel
        or MlFailureKind.ServerError
        or MlFailureKind.MalformedResponse;
}

/// <summary>
/// The answer from the ML service, or the reason there is none.
///
/// <para>A result type rather than exceptions, because the failure path is
/// the NORMAL path here: specification §8.1 requires the backend to carry on
/// without the ML layer, and a <c>try/catch</c> around every call is a
/// <c>try/catch</c> that will be forgotten at one of them.</para>
/// </summary>
public sealed class MlResult<T> where T : class
{
    private MlResult(T? value, MlFailure? failure)
    {
        Value = value;
        Failure = failure;
    }

    public T? Value { get; }

    public MlFailure? Failure { get; }

    public bool Ok => Failure is null;

    /// <summary>
    /// The value, or an exception if this is a failure. Only for a caller
    /// that has already checked <see cref="Ok"/>.
    /// </summary>
    public T Required => Value ?? throw new InvalidOperationException(
        "MlResult.Required read on a failed result: "
        + (Failure?.Detail ?? "unknown"));

    public static MlResult<T> Success(T value) => new(value, null);

    public static MlResult<T> Fail(
        MlFailureKind kind, int? status, string? code, string detail)
        => new(null, new MlFailure(kind, status, code, detail));
}
