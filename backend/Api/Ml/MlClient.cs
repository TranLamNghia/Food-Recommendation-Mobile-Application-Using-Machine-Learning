using System.Diagnostics;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Api.Ml;

/// <summary>
/// The backend's side of the ML service — the four internal endpoints of
/// specification §8.
///
/// <para>Before this interface existed, <c>grep -rn "HttpClient"
/// backend/Api</c> returned nothing: the recommendation pipeline was built
/// in <c>ml/</c> and reachable from a Python command line, but not from the
/// server the app calls. This is that seam.</para>
///
/// <para><b>No method throws for a service that is down.</b> Every one
/// returns <see cref="MlResult{T}"/>, because specification §8.1 makes
/// carrying on without the ML layer a requirement, not an error path: the
/// backend still builds a meal plan and records
/// <c>generation_source = "rule_based"</c>. Callers branch on
/// <see cref="MlFailure.IsDegradable"/> — and must NOT degrade on a failure
/// that says otherwise, above all
/// <see cref="MlFailureKind.NoScoreableCandidate"/>, which is the F1 safety
/// layer speaking.</para>
/// </summary>
public interface IMlClient
{
    /// <summary>Step 3 — score a candidate set (§8.1).</summary>
    Task<MlResult<MlPredictResponse>> PredictAsync(
        MlPredictRequest request, CancellationToken ct = default);

    /// <summary>
    /// Step 4 — assemble one day's plan.
    ///
    /// <para>The answer is <b>not written anywhere</b> by the ML service.
    /// Persisting it into <c>meal_plans</c> and <c>meal_plan_items</c> is
    /// this backend's job, and so is the <c>409 MEAL_PLAN_EXISTS</c>
    /// rule.</para>
    /// </summary>
    Task<MlResult<MlPlanResponse>> PlanAsync(
        MlPlanRequest request, CancellationToken ct = default);

    /// <summary>
    /// §7.4.1 — the taste-survey deck for one user, as food ids in the order
    /// to ask about them.
    /// </summary>
    Task<MlResult<MlSurveyDeckResponse>> SurveyDeckAsync(
        MlSurveyDeckRequest request, CancellationToken ct = default);

    /// <summary>
    /// §7.4 — how many foods a set of conditions would leave, for the
    /// onboarding filter screen. Reads nothing saved and writes nothing.
    /// </summary>
    Task<MlResult<MlCandidateCountResponse>> CandidateCountAsync(
        MlCandidateCountRequest request, CancellationToken ct = default);

    /// <summary>
    /// §7.5 — which of these foods the F1 filter excludes for this user, and
    /// under which rule. Cheaper than <see cref="PredictAsync"/> when only
    /// safety is wanted: nothing is scored and no model is loaded.
    /// </summary>
    Task<MlResult<MlFoodSafetyResponse>> FoodSafetyAsync(
        MlFoodSafetyRequest request, CancellationToken ct = default);

    /// <summary>
    /// Rebuild a user's preference vector (§8.2). Call it after onboarding
    /// finishes, and when <c>featureVersion</c> changes.
    /// </summary>
    Task<MlResult<MlRebuildResponse>> RebuildProfileAsync(
        string userId, CancellationToken ct = default);

    /// <summary>
    /// Retrain, asynchronously (§8.3). A <c>202</c> means the job started,
    /// not that a model exists.
    /// </summary>
    Task<MlResult<MlTrainResponse>> TrainAsync(
        MlTrainRequest request, CancellationToken ct = default);

    /// <summary>
    /// Which model is serving (§8.4). Needs no key, and
    /// <c>status = "degraded"</c> is a <c>200</c>.
    /// </summary>
    Task<MlResult<MlHealthResponse>> HealthAsync(
        CancellationToken ct = default);
}

/// <inheritdoc cref="IMlClient"/>
public sealed class MlClient : IMlClient
{
    /// <summary>
    /// The header name from §8. Spelled once: a typo would read as a
    /// missing key and return <c>401</c> for every call, which looks exactly
    /// like a wrong key.
    /// </summary>
    public const string KeyHeader = "X-Internal-Key";

    /// <summary>
    /// Separate from the MVC options in <c>Program.cs</c>. Those govern what
    /// this API answers its clients; these govern what this backend sends to
    /// the ML service, and the two contracts are free to differ.
    ///
    /// <para><c>NumberHandling</c> allows <c>"0.42"</c> as well as
    /// <c>0.42</c>: Pydantic serialises floats as numbers today, and a
    /// <c>float</c> that arrives quoted after some future change would
    /// otherwise throw inside the deserialiser and degrade the whole call to
    /// rule-based scoring.</para>
    /// </summary>
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
        // The service distinguishes "no ML term" (`scoreMl: null`) from a
        // score of 0, so nulls have to survive the round trip rather than be
        // dropped.
        DefaultIgnoreCondition = JsonIgnoreCondition.Never,
    };

    private readonly HttpClient _http;
    private readonly MlOptions _options;
    private readonly ILogger<MlClient> _log;

    /// <summary>
    /// Guards the "no key configured" log line, so a server running without
    /// <c>ML_INTERNAL_KEY</c> says so once per process instead of once per
    /// request. <c>int</c> rather than <c>bool</c> because
    /// <see cref="Interlocked"/> has no <c>Exchange</c> for <c>bool</c>.
    /// </summary>
    private int _disabledLogged;

    public MlClient(
        HttpClient http, MlOptions options, ILogger<MlClient> log)
    {
        _http = http;
        _options = options;
        _log = log;
    }

    public Task<MlResult<MlPredictResponse>> PredictAsync(
        MlPredictRequest request, CancellationToken ct = default)
    {
        // `null` means "score the whole catalogue" and is the normal case.
        // An EMPTY list is a different thing and is refused here rather than
        // left to the service's `422`: a round trip and part of the 2 s
        // budget spent to be told something this side already knows. The two
        // must not be conflated — reading an empty list as "everything" is
        // how a bug upstream turns into a full-catalogue recommendation.
        if (request.CandidateFoodIds is { Count: 0 })
        {
            return Task.FromResult(MlResult<MlPredictResponse>.Fail(
                MlFailureKind.BadRequest,
                null,
                "EMPTY_CANDIDATE_SET",
                "PredictAsync was given an empty CandidateFoodIds. Leave it "
                + "null to score the whole catalogue; an empty list means "
                + "something upstream produced no food, which is a "
                + "RULE_TOO_RESTRICTIVE answer to the client, not a "
                + "prediction request."));
        }

        return SendAsync<MlPredictResponse>(
            HttpMethod.Post, "predict", request, needsKey: true, ct);
    }

    public Task<MlResult<MlPlanResponse>> PlanAsync(
        MlPlanRequest request, CancellationToken ct = default)
    {
        // Refused here rather than at the service's own `422`. The cap is a
        // database CHECK (`chk_expl_ratio`), so a value above it could not be
        // written even if a plan came back — and more than half a plan being
        // trial dishes is no longer a personalised recommendation.
        if (request.ExplorationRatio is < 0 or > 0.5)
        {
            return Task.FromResult(MlResult<MlPlanResponse>.Fail(
                MlFailureKind.BadRequest, null, "EXPLORATION_OUT_OF_RANGE",
                $"ExplorationRatio {request.ExplorationRatio} is outside "
                + "0 to 0.5, the range chk_expl_ratio allows in "
                + "meal_plans.exploration_ratio."));
        }

        // An empty list is not "all four": it is a caller that computed a
        // set of meals and got none. Refused here rather than sent, because
        // the service would answer `400` for it and this side already knows.
        if (request.MealTypes is { Count: 0 })
        {
            return Task.FromResult(MlResult<MlPlanResponse>.Fail(
                MlFailureKind.BadRequest, null, "EMPTY_MEAL_TYPES",
                "PlanAsync was given an empty MealTypes. Leave it null to "
                + "build the whole day; an empty list means something "
                + "upstream selected no meal at all."));
        }

        return SendAsync<MlPlanResponse>(
            HttpMethod.Post, "plan", request, needsKey: true, ct);
    }

    public Task<MlResult<MlCandidateCountResponse>> CandidateCountAsync(
        MlCandidateCountRequest request, CancellationToken ct = default)
        => SendAsync<MlCandidateCountResponse>(
            HttpMethod.Post, "candidates/count", request,
            needsKey: true, ct);

    public Task<MlResult<MlFoodSafetyResponse>> FoodSafetyAsync(
        MlFoodSafetyRequest request, CancellationToken ct = default)
    {
        // An empty list is not "all foods": it is a caller that worked out a
        // set and got none. Answered here rather than sent, because the
        // right answer needs no round trip at all.
        if (request.FoodIds is { Count: 0 })
        {
            return Task.FromResult(MlResult<MlFoodSafetyResponse>.Success(
                new MlFoodSafetyResponse { UserId = request.UserId }));
        }

        return SendAsync<MlFoodSafetyResponse>(
            HttpMethod.Post, "foods/safety", request, needsKey: true, ct);
    }

    public Task<MlResult<MlSurveyDeckResponse>> SurveyDeckAsync(
        MlSurveyDeckRequest request, CancellationToken ct = default)
    {
        // §7.4.1's range, checked on this side so the caller gets a
        // `400 VALIDATION_FAILED` naming the field instead of a round trip
        // and FastAPI's own schema error.
        if (request.Size is < 20 or > 50)
        {
            return Task.FromResult(MlResult<MlSurveyDeckResponse>.Fail(
                MlFailureKind.BadRequest, null, "DECK_SIZE_OUT_OF_RANGE",
                $"Deck size {request.Size} is outside the 20 to 50 of "
                + "specification §7.4.1."));
        }

        return SendAsync<MlSurveyDeckResponse>(
            HttpMethod.Post, "survey-deck", request, needsKey: true, ct);
    }

    public Task<MlResult<MlRebuildResponse>> RebuildProfileAsync(
        string userId, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(userId))
        {
            return Task.FromResult(MlResult<MlRebuildResponse>.Fail(
                MlFailureKind.BadRequest, null, "EMPTY_USER_ID",
                "RebuildProfileAsync was called with an empty user id."));
        }

        // `Uri.EscapeDataString` even though the ids are UUIDs: the value
        // comes from a route elsewhere in the system, and concatenating
        // unescaped input into a path is how a `../train` ends up calling a
        // different endpoint than the one this method names.
        var path = $"profiles/{Uri.EscapeDataString(userId)}/rebuild";
        return SendAsync<MlRebuildResponse>(
            HttpMethod.Post, path, body: null, needsKey: true, ct);
    }

    public Task<MlResult<MlTrainResponse>> TrainAsync(
        MlTrainRequest request, CancellationToken ct = default)
    {
        if (!MlAlgorithm.All.Contains(request.Algorithm))
        {
            return Task.FromResult(MlResult<MlTrainResponse>.Fail(
                MlFailureKind.BadRequest, null, "UNKNOWN_ALGORITHM",
                $"Unknown algorithm '{request.Algorithm}'. ml/train.py "
                + "implements: "
                + string.Join(", ", MlAlgorithm.All)));
        }

        // Training takes minutes, but the response does not: §8.3 answers
        // `202` and runs the job on a background thread. So the ordinary 2 s
        // budget is right here too — what is being waited on is the
        // acknowledgement, not the model.
        return SendAsync<MlTrainResponse>(
            HttpMethod.Post, "train", request, needsKey: true, ct);
    }

    public Task<MlResult<MlHealthResponse>> HealthAsync(
        CancellationToken ct = default)
        => SendAsync<MlHealthResponse>(
            HttpMethod.Get, "health", body: null, needsKey: false, ct);

    // ── The one place a request is made ───────────────────────────────

    private async Task<MlResult<T>> SendAsync<T>(
        HttpMethod method,
        string path,
        object? body,
        bool needsKey,
        CancellationToken ct) where T : class
    {
        if (needsKey && !_options.Enabled)
        {
            // Error level, not Warning: a backend that cannot reach the ML
            // layer at all is serving every user rule-based plans, and that
            // is invisible from the outside — the plans still look like
            // plans.
            if (Interlocked.Exchange(ref _disabledLogged, 1) == 0)
            {
                _log.LogError(
                    "ML_INTERNAL_KEY is not configured, so the ML service "
                    + "cannot be called. Every recommendation will fall back "
                    + "to rule-based scoring (specification §8.1). Set "
                    + "ML_INTERNAL_KEY in .env to the same value the ML "
                    + "service was started with.");
            }
            return MlResult<T>.Fail(
                MlFailureKind.Disabled, null, null,
                "ML_INTERNAL_KEY is not configured on this server.");
        }

        using var request = new HttpRequestMessage(method, path);
        if (needsKey)
        {
            request.Headers.Add(KeyHeader, _options.InternalKey);
        }
        if (body is not null)
        {
            request.Content = JsonContent.Create(body, options: Json);
        }

        // A linked source rather than `HttpClient.Timeout` alone, so that a
        // timeout can be told apart from the CALLER giving up: both surface
        // as `TaskCanceledException`, and reporting "the ML service timed
        // out" for a client that closed the connection sends somebody
        // looking at the wrong service.
        using var budget = CancellationTokenSource
            .CreateLinkedTokenSource(ct);
        budget.CancelAfter(_options.TimeoutMs);

        var watch = Stopwatch.StartNew();
        HttpResponseMessage response;
        try
        {
            response = await _http.SendAsync(request, budget.Token);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            _log.LogWarning(
                "ML service did not answer {Method} {Path} within {Budget} "
                + "ms; falling back (specification §8.1).",
                method, path, _options.TimeoutMs);
            return MlResult<T>.Fail(
                MlFailureKind.Timeout, null, null,
                $"No answer from the ML service within {_options.TimeoutMs} "
                + $"ms ({method} {path}).");
        }
        catch (OperationCanceledException)
        {
            // The caller cancelled — the request was abandoned, nothing is
            // known about the ML service. Rethrown rather than turned into a
            // failure: a cancelled request has no answer to degrade to.
            throw;
        }
        catch (HttpRequestException e)
        {
            _log.LogWarning(
                e,
                "ML service unreachable at {BaseAddress} ({Method} {Path}).",
                _http.BaseAddress, method, path);
            return MlResult<T>.Fail(
                MlFailureKind.Unreachable, null, null,
                $"Could not reach the ML service at {_http.BaseAddress}: "
                + e.Message);
        }

        using (response)
        {
            if (response.IsSuccessStatusCode)
            {
                return await ReadSuccessAsync<T>(
                    response, method, path, watch, ct);
            }
            return await ReadFailureAsync<T>(response, method, path, ct);
        }
    }

    private async Task<MlResult<T>> ReadSuccessAsync<T>(
        HttpResponseMessage response,
        HttpMethod method,
        string path,
        Stopwatch watch,
        CancellationToken ct) where T : class
    {
        T? value;
        try
        {
            value = await response.Content
                .ReadFromJsonAsync<T>(Json, ct);
        }
        catch (JsonException e)
        {
            // Degradable, but logged at error level: a 200 that will not
            // parse means this file and `ml/api.py` no longer agree on the
            // contract, and no amount of waiting fixes that.
            _log.LogError(
                e,
                "ML service answered {Status} to {Method} {Path} with a body "
                + "that does not match {Type}. The two sides disagree about "
                + "the §8 contract; tools/smoke_ml_api.py checks it.",
                (int)response.StatusCode, method, path, typeof(T).Name);
            return MlResult<T>.Fail(
                MlFailureKind.MalformedResponse,
                (int)response.StatusCode,
                null,
                $"Could not read the ML service answer as {typeof(T).Name}: "
                + e.Message);
        }

        if (value is null)
        {
            return MlResult<T>.Fail(
                MlFailureKind.MalformedResponse,
                (int)response.StatusCode,
                null,
                $"The ML service answered {(int)response.StatusCode} to "
                + $"{method} {path} with a null body.");
        }

        _log.LogDebug(
            "ML {Method} {Path} -> {Status} in {Elapsed} ms.",
            method, path, (int)response.StatusCode, watch.ElapsedMilliseconds);
        return MlResult<T>.Success(value);
    }

    private async Task<MlResult<T>> ReadFailureAsync<T>(
        HttpResponseMessage response,
        HttpMethod method,
        string path,
        CancellationToken ct) where T : class
    {
        var status = (int)response.StatusCode;
        var (code, message) = await ReadEnvelopeAsync(response, ct);

        // Branch on `error.code` first and the status second. The code is
        // the stable string (§2.5), and two different codes share `404` and
        // `422` — telling USER_NOT_FOUND from DATASET_NOT_FOUND, and
        // NO_SCOREABLE_CANDIDATE from INSUFFICIENT_SIGNALS, is exactly what
        // the caller needs in order NOT to degrade on them.
        var kind = code switch
        {
            "USER_NOT_FOUND" => MlFailureKind.UserNotFound,
            "DATASET_NOT_FOUND" => MlFailureKind.DatasetNotFound,
            "NO_SCOREABLE_CANDIDATE" => MlFailureKind.NoScoreableCandidate,
            "INSUFFICIENT_SIGNALS" => MlFailureKind.InsufficientSignals,
            // Both arrive as `422` from /plan, and both mean the user has a
            // step to complete — not that anything is unavailable. Without
            // these two rows they would fall through to the status switch
            // below, become `BadRequest`, and reach the user as
            // "lỗi máy chủ" when the real answer is "fill in your profile".
            "PROFILE_REQUIRED" => MlFailureKind.ProfileRequired,
            "ONBOARDING_REQUIRED" => MlFailureKind.OnboardingRequired,
            // Both mean this backend asked for something impossible rather
            // than the user missing a step: a meal of a day that has no
            // plan, or a condition id that does not exist. `BadRequest` is
            // right — it is a bug on this side, it does not degrade, and it
            // reaches the client as a 500 with the detail in the log.
            "MEAL_PLAN_REQUIRED" => MlFailureKind.BadRequest,
            "CONDITION_NOT_FOUND" => MlFailureKind.BadRequest,
            "TRAINING_IN_PROGRESS" => MlFailureKind.TrainingInProgress,
            // Numbers rather than the `HttpStatusCode` names: 422 is
            // `UnprocessableEntity` in some .NET versions and
            // `UnprocessableContent` in others, and the status this service
            // sends does not change with the framework.
            _ => status switch
            {
                400 => MlFailureKind.BadRequest,
                401 => MlFailureKind.Unauthorized,
                404 => MlFailureKind.UserNotFound,
                409 => MlFailureKind.TrainingInProgress,
                // FastAPI answers 422 for a body its own schema rejects,
                // with no `error.code` of ours. That is this backend sending
                // the wrong shape, not the safety layer talking — so it maps
                // to BadRequest, which does NOT degrade.
                422 => MlFailureKind.BadRequest,
                503 => MlFailureKind.NoActiveModel,
                _ => status >= 500
                    ? MlFailureKind.ServerError
                    : MlFailureKind.BadRequest,
            },
        };

        var detail = $"ML service answered {status} to {method} {path}"
            + (code is null ? string.Empty : $" [{code}]")
            + (string.IsNullOrWhiteSpace(message)
                ? string.Empty
                : $": {message}");

        if (kind is MlFailureKind.Unauthorized)
        {
            _log.LogError(
                "The ML service rejected this backend's X-Internal-Key. "
                + "Both sides read ML_INTERNAL_KEY; they are not the same "
                + "value. Every recommendation falls back to rule-based "
                + "scoring until this is fixed.");
        }
        else if (kind is MlFailureKind.NoScoreableCandidate)
        {
            // Not a malfunction: the F1 filter removed every candidate.
            // Logged at information level with the code, so the line is
            // findable, without implying the service is broken.
            _log.LogInformation(
                "ML {Path}: the F1 filter removed every candidate sent. "
                + "This is a NO_FEASIBLE_PLAN answer to the client, not a "
                + "fallback.",
                path);
        }
        else
        {
            _log.LogWarning("{Detail}", detail);
        }

        return MlResult<T>.Fail(kind, status, code, detail);
    }

    /// <summary>
    /// Pulls <c>error.code</c> and <c>error.message</c> out of the §2.5
    /// envelope.
    ///
    /// <para>Tolerant on purpose. A failure body can be anything —
    /// FastAPI's own <c>{"detail": ...}</c> for a schema error, or HTML from
    /// a proxy that answered instead of the service — and a parse error
    /// while READING an error must not replace the real failure with a
    /// parsing one.</para>
    /// </summary>
    private static async Task<(string? Code, string? Message)>
        ReadEnvelopeAsync(HttpResponseMessage response, CancellationToken ct)
    {
        try
        {
            var raw = await response.Content.ReadAsStringAsync(ct);
            if (string.IsNullOrWhiteSpace(raw))
            {
                return (null, null);
            }

            using var doc = JsonDocument.Parse(raw);
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
            {
                return (null, Truncate(raw));
            }

            if (doc.RootElement.TryGetProperty("error", out var error)
                && error.ValueKind == JsonValueKind.Object)
            {
                var code = error.TryGetProperty("code", out var c)
                    && c.ValueKind == JsonValueKind.String
                    ? c.GetString()
                    : null;
                var message = error.TryGetProperty("message", out var m)
                    && m.ValueKind == JsonValueKind.String
                    ? m.GetString()
                    : null;
                return (code, message);
            }

            // FastAPI's validation errors arrive as `{"detail": [...]}`.
            if (doc.RootElement.TryGetProperty("detail", out var detail))
            {
                return (null, Truncate(detail.ToString()));
            }

            return (null, Truncate(raw));
        }
        catch (Exception e) when (e is JsonException or HttpRequestException
            or InvalidOperationException)
        {
            return (null, null);
        }
    }

    /// <summary>
    /// Keeps one log line to one log line. An HTML error page from a proxy
    /// is tens of kilobytes, and it would be logged on every request for as
    /// long as the proxy is misconfigured.
    /// </summary>
    private static string Truncate(string s)
        => s.Length <= 300 ? s : string.Concat(s.AsSpan(0, 300), "…");
}
