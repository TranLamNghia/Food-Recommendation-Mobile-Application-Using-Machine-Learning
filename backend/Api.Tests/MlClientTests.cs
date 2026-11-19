using System.Net;
using System.Text;
using System.Text.Json;
using Api.Ml;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace Api.Tests;

/// <summary>
/// The ML service bridge of specification §8, tested against a stub
/// <see cref="HttpMessageHandler"/>.
///
/// <para>No database, no server, no ML service: what is being checked here is
/// this side's half of the contract — the header, the 2 s budget, and above
/// all WHICH failures are allowed to degrade to rule-based scoring. The half
/// that needs both processes running is <c>tools/smoke_ml_api.py</c>.</para>
///
/// <para>The degradation tests are the point of this file. Specification §8.1
/// makes "the ML service is down" a normal path, so a bug there does not
/// throw and does not fail a smoke test: it quietly serves every user a
/// rule-based plan, or — far worse, see
/// <see cref="NoScoreableCandidate_does_not_degrade"/> — quietly scores a
/// candidate set the F1 safety filter has already rejected.</para>
/// </summary>
public class MlClientTests
{
    private const string Key = "test-internal-key";

    /// <summary>
    /// Answers whatever it is told to, and records what it was asked. A stub
    /// rather than a mocking library: the test project has xunit and nothing
    /// else, and this is 20 lines.
    /// </summary>
    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, CancellationToken,
            Task<HttpResponseMessage>> _reply;

        public StubHandler(HttpStatusCode status, string body)
            : this((_, _) => Task.FromResult(Make(status, body)))
        {
        }

        public StubHandler(
            Func<HttpRequestMessage, CancellationToken,
                Task<HttpResponseMessage>> reply)
            => _reply = reply;

        public HttpRequestMessage? LastRequest { get; private set; }

        public string? LastBody { get; private set; }

        public int Calls { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            LastRequest = request;
            LastBody = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync(ct);
            return await _reply(request, ct);
        }

        private static HttpResponseMessage Make(
            HttpStatusCode status, string body)
            => new(status)
            {
                Content = new StringContent(
                    body, Encoding.UTF8, "application/json"),
            };
    }

    private static MlClient Build(
        StubHandler handler, string key = Key, int timeoutMs = 2000)
    {
        var options = new MlOptions
        {
            BaseUrl = "http://ml.test/",
            InternalKey = key,
            TimeoutMs = timeoutMs,
        };
        var http = new HttpClient(handler)
        {
            BaseAddress = new Uri(options.BaseUrl),
        };
        return new MlClient(http, options, NullLogger<MlClient>.Instance);
    }

    /// <summary>
    /// The normal request: no candidate list at all, so the ML service reads
    /// the whole catalogue itself.
    /// </summary>
    private static MlPredictRequest Request()
        => new()
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            ContextMealType = "lunch",
        };

    /// <summary>A §8.1 answer, as the service actually shapes it.</summary>
    private const string PredictOk = """
    {
      "modelVersion": "v1.0.3",
      "featureVersion": "fv1",
      "stage": "hybrid",
      "alpha": 0.42,
      "generationSource": "hybrid",
      "scores": [
        { "foodId": "00000003-0000-4000-8000-000000000000", "score": 0.9105,
          "scoreContent": 0.8802, "scoreMl": 0.9523, "scoreRule": 1.0 },
        { "foodId": "00000005-0000-4000-8000-000000000000", "score": 0.6733,
          "scoreContent": 0.7011, "scoreMl": null, "scoreRule": 0.4 }
      ],
      "skippedFoodIds": ["00000047-0000-4000-8000-000000000000"],
      "nFoodsBeforeF1": 318,
      "nFoodsAfterF1": 204,
      "warnings": ["bmi: request 23.15, database 24.01"],
      "elapsedMs": 34
    }
    """;

    private static string Envelope(string code, string message)
        => JsonSerializer.Serialize(new
        {
            error = new { code, message },
        });

    // ── The happy path ────────────────────────────────────────────────

    [Fact]
    public async Task Predict_reads_every_field_of_the_contract()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        var result = await Build(handler).PredictAsync(Request());

        Assert.True(result.Ok);
        var value = result.Required;
        Assert.Equal("v1.0.3", value.ModelVersion);
        Assert.Equal("fv1", value.FeatureVersion);
        Assert.Equal("hybrid", value.Stage);
        Assert.Equal(0.42, value.Alpha, 3);
        Assert.Equal(GenerationSource.Hybrid, value.GenerationSource);
        Assert.Equal(2, value.Scores.Count);
        Assert.Equal(34, value.ElapsedMs);

        // `skippedFoodIds` and `warnings` must survive. A plan built from a
        // response whose skipped list was dropped would serve a food the F1
        // filter removed.
        Assert.Equal(
            "00000047-0000-4000-8000-000000000000",
            Assert.Single(value.SkippedFoodIds));
        Assert.Single(value.Warnings);

        // The pair the backend can no longer work out for itself, now that
        // the ML service picks the candidate set.
        Assert.Equal(318, value.NFoodsBeforeF1);
        Assert.Equal(204, value.NFoodsAfterF1);
    }

    /// <summary>
    /// <c>scoreMl: null</c> has to stay null. Reading it as 0 is the same
    /// class of bug as reading a missing nutrient as 0: it does not throw, it
    /// just ranks the food as if the model disliked it.
    /// </summary>
    [Fact]
    public async Task Predict_keeps_a_null_scoreMl_null()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        var result = await Build(handler).PredictAsync(Request());

        Assert.Equal(0.9523, result.Required.Scores[0].ScoreMl);
        Assert.Null(result.Required.Scores[1].ScoreMl);
    }

    [Fact]
    public async Task Predict_sends_the_key_header_and_camelCase_body()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        await Build(handler).PredictAsync(Request());

        Assert.NotNull(handler.LastRequest);
        Assert.True(handler.LastRequest!.Headers
            .TryGetValues(MlClient.KeyHeader, out var sent));
        Assert.Equal(Key, Assert.Single(sent!));
        Assert.Equal(HttpMethod.Post, handler.LastRequest.Method);
        Assert.Equal(
            "http://ml.test/predict",
            handler.LastRequest.RequestUri!.ToString());

        // The Python side reads `userId` and `candidateFoodIds`. A
        // PascalCase body deserialises into a Pydantic model with the
        // defaults — a 422, or worse, a request about nobody.
        Assert.Contains("\"userId\"", handler.LastBody);
        Assert.Contains("\"contextMealType\"", handler.LastBody);
        Assert.DoesNotContain("\"UserId\"", handler.LastBody);

        // `candidateFoodIds: null` is the request to score the whole
        // catalogue. It has to travel as an explicit null rather than be
        // dropped: the field being absent and the field being null mean the
        // same thing to Pydantic today, and relying on that is relying on a
        // default this side does not control.
        Assert.Contains("\"candidateFoodIds\":null", handler.LastBody);
        Assert.Contains("\"excludeFoodIds\":[]", handler.LastBody);
    }

    [Fact]
    public async Task Health_does_not_send_the_key()
    {
        const string body = """
        {
          "status": "degraded",
          "activeModel": null,
          "featureVersion": "fv1",
          "reason": "no model has is_active = 1"
        }
        """;
        var handler = new StubHandler(HttpStatusCode.OK, body);
        var result = await Build(handler).HealthAsync();

        Assert.True(result.Ok);
        Assert.Equal("degraded", result.Required.Status);
        Assert.Null(result.Required.ActiveModel);
        Assert.NotNull(result.Required.Reason);

        // §8.4 requires no key, so an infrastructure liveness probe does not
        // have to carry an application secret. Sending it anyway would make
        // this backend the only caller that needs one.
        Assert.False(handler.LastRequest!.Headers
            .Contains(MlClient.KeyHeader));
    }

    [Fact]
    public async Task Rebuild_posts_to_the_user_path()
    {
        const string body = """
        {
          "userId": "00000001-0000-4000-8000-000000000000",
          "featureVersion": "fv1",
          "nSignals": 26,
          "sumAbsWeight": 21.0,
          "stage": "content",
          "alpha": 0.0,
          "updatedAt": "2026-11-20T08:02:11+07:00"
        }
        """;
        var handler = new StubHandler(HttpStatusCode.OK, body);
        var result = await Build(handler).RebuildProfileAsync(
            "00000001-0000-4000-8000-000000000000");

        Assert.True(result.Ok);
        Assert.Equal(26, result.Required.NSignals);
        Assert.Equal(
            "http://ml.test/profiles/00000001-0000-4000-8000-000000000000"
            + "/rebuild",
            handler.LastRequest!.RequestUri!.ToString());

        // The offset has to survive as text. Parsed into a DateTime it would
        // be rebased onto the server's zone, and the one clock of this system
        // is Asia/Ho_Chi_Minh.
        Assert.EndsWith("+07:00", result.Required.UpdatedAt);
    }

    [Fact]
    public async Task Train_accepts_the_202_of_the_specification()
    {
        const string body = """
        {
          "jobId": "train-20261120-0900",
          "status": "queued",
          "startedAt": "2026-11-20T09:00:00+07:00"
        }
        """;
        var handler = new StubHandler(HttpStatusCode.Accepted, body);
        var result = await Build(handler).TrainAsync(new MlTrainRequest
        {
            DatasetVersion = "ds-2026-11-20",
            Algorithm = MlAlgorithm.RandomForest,
        });

        Assert.True(result.Ok);
        Assert.Equal("queued", result.Required.Status);
    }

    // ── Degradable: the ML layer is not available ─────────────────────

    [Fact]
    public async Task No_key_configured_is_degradable_and_makes_no_request()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        var result = await Build(handler, key: "").PredictAsync(Request());

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.Disabled, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
        Assert.Equal(0, handler.Calls);
    }

    [Fact]
    public async Task A_timeout_is_degradable()
    {
        var handler = new StubHandler(async (_, ct) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(30), ct);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        var result = await Build(handler, timeoutMs: 60)
            .PredictAsync(Request());

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.Timeout, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
    }

    [Fact]
    public async Task An_unreachable_service_is_degradable()
    {
        var handler = new StubHandler((_, _) =>
            Task.FromException<HttpResponseMessage>(
                new HttpRequestException("Connection refused")));
        var result = await Build(handler).PredictAsync(Request());

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.Unreachable, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
    }

    /// <summary>
    /// §8.1's own case: no model can score anything. Degradable — the plan is
    /// built from the rules and recorded as <c>rule_based</c>.
    /// </summary>
    [Fact]
    public async Task A_503_is_degradable()
    {
        var handler = new StubHandler(
            HttpStatusCode.ServiceUnavailable,
            Envelope("NO_ACTIVE_MODEL", "No model has is_active = 1."));
        var result = await Build(handler).PredictAsync(Request());

        Assert.Equal(MlFailureKind.NoActiveModel, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
        Assert.Equal(503, result.Failure.Status);
    }

    [Fact]
    public async Task A_wrong_key_degrades_rather_than_failing_the_request()
    {
        var handler = new StubHandler(
            HttpStatusCode.Unauthorized,
            Envelope("UNAUTHORIZED", "Missing or incorrect header."));
        var result = await Build(handler).PredictAsync(Request());

        // A deployment fault, logged at error level — but the user still has
        // to get a meal plan, so it degrades.
        Assert.Equal(MlFailureKind.Unauthorized, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
    }

    [Fact]
    public async Task A_200_that_will_not_parse_is_degradable()
    {
        var handler = new StubHandler(
            HttpStatusCode.OK, "<html>502 from a proxy</html>");
        var result = await Build(handler).PredictAsync(Request());

        Assert.Equal(MlFailureKind.MalformedResponse, result.Failure!.Kind);
        Assert.True(result.Failure.IsDegradable);
    }

    // ── NOT degradable: the ML layer answered ─────────────────────────

    /// <summary>
    /// The expensive one. <c>422 NO_SCOREABLE_CANDIDATE</c> means the F1
    /// filter removed every food sent — this user may eat none of them.
    /// Degrading here would re-score a candidate set the safety layer has
    /// already rejected: the F1 filter failing OPEN, with a plan to show for
    /// it and nothing in the logs.
    /// </summary>
    [Fact]
    public async Task NoScoreableCandidate_does_not_degrade()
    {
        var handler = new StubHandler(
            HttpStatusCode.UnprocessableEntity,
            Envelope(
                "NO_SCOREABLE_CANDIDATE",
                "The F1 filter removed all 12 foods sent."));
        var result = await Build(handler).PredictAsync(Request());

        Assert.Equal(
            MlFailureKind.NoScoreableCandidate, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
        Assert.Equal("NO_SCOREABLE_CANDIDATE", result.Failure.Code);
    }

    /// <summary>
    /// 422 again, and a different meaning. Branching on the status alone
    /// would merge this with the case above, and one of the two would get the
    /// wrong answer.
    /// </summary>
    [Fact]
    public async Task InsufficientSignals_does_not_degrade()
    {
        var handler = new StubHandler(
            HttpStatusCode.UnprocessableEntity,
            Envelope("INSUFFICIENT_SIGNALS", "No usable swipe left."));
        var result = await Build(handler).RebuildProfileAsync("u1");

        Assert.Equal(
            MlFailureKind.InsufficientSignals, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
    }

    /// <summary>
    /// 404 is shared too: a missing user from /predict and /rebuild, a
    /// missing dataset from /train.
    /// </summary>
    [Fact]
    public async Task The_two_404_codes_are_told_apart()
    {
        var user = new StubHandler(
            HttpStatusCode.NotFound,
            Envelope("USER_NOT_FOUND", "No user u1."));
        var userResult = await Build(user).PredictAsync(Request());
        Assert.Equal(MlFailureKind.UserNotFound, userResult.Failure!.Kind);
        Assert.False(userResult.Failure.IsDegradable);

        var dataset = new StubHandler(
            HttpStatusCode.NotFound,
            Envelope("DATASET_NOT_FOUND", "No sample has that version."));
        var trainResult = await Build(dataset).TrainAsync(new MlTrainRequest
        {
            DatasetVersion = "ds-missing",
        });
        Assert.Equal(
            MlFailureKind.DatasetNotFound, trainResult.Failure!.Kind);
        Assert.False(trainResult.Failure.IsDegradable);
    }

    [Fact]
    public async Task A_409_from_train_does_not_degrade()
    {
        var handler = new StubHandler(
            HttpStatusCode.Conflict,
            Envelope("TRAINING_IN_PROGRESS", "train-20261120-0900 running."));
        var result = await Build(handler).TrainAsync(new MlTrainRequest
        {
            DatasetVersion = "ds-2026-11-20",
        });

        Assert.Equal(
            MlFailureKind.TrainingInProgress, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
    }

    /// <summary>
    /// FastAPI's own schema error: a 422 with <c>{"detail": [...]}</c> and no
    /// <c>error.code</c>. That is this backend sending the wrong shape, so it
    /// must NOT degrade — degrading would hide the bug for as long as the
    /// code lives.
    /// </summary>
    [Fact]
    public async Task A_schema_422_without_a_code_is_our_bug_not_a_fallback()
    {
        var handler = new StubHandler(
            HttpStatusCode.UnprocessableEntity,
            """{"detail":[{"loc":["body","userId"],"msg":"required"}]}""");
        var result = await Build(handler).PredictAsync(Request());

        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
        Assert.Contains("userId", result.Failure.Detail);
    }

    // ── Checked before the request is made ────────────────────────────

    /// <summary>
    /// An empty list is not "everything". <c>null</c> is. Conflating them is
    /// how a bug upstream that produced no food turns into a recommendation
    /// over the whole catalogue — including, at that point, foods nobody
    /// asked about.
    /// </summary>
    [Fact]
    public async Task An_empty_candidate_list_is_rejected_without_a_request()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        var result = await Build(handler).PredictAsync(new MlPredictRequest
        {
            UserId = "u1",
            CandidateFoodIds = [],
        });

        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
        Assert.Equal(0, handler.Calls);
    }

    [Fact]
    public async Task A_null_candidate_list_is_sent_and_scores_everything()
    {
        var handler = new StubHandler(HttpStatusCode.OK, PredictOk);
        var result = await Build(handler).PredictAsync(new MlPredictRequest
        {
            UserId = "u1",
            CandidateFoodIds = null,
            ExcludeFoodIds = ["00000009-0000-4000-8000-000000000000"],
        });

        Assert.True(result.Ok);
        Assert.Equal(1, handler.Calls);
        Assert.Contains(
            "00000009-0000-4000-8000-000000000000", handler.LastBody);
    }

    [Fact]
    public async Task An_unknown_algorithm_is_rejected_without_a_request()
    {
        var handler = new StubHandler(HttpStatusCode.Accepted, "{}");
        var result = await Build(handler).TrainAsync(new MlTrainRequest
        {
            DatasetVersion = "ds-2026-11-20",
            Algorithm = "xgboost",
        });

        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.Equal(0, handler.Calls);
        Assert.Contains("gradient_boosting", result.Failure.Detail);
    }

    // ── Cancellation is not a timeout ─────────────────────────────────

    /// <summary>
    /// A caller that gives up has no answer to degrade to, so the
    /// cancellation propagates instead of being reported as "the ML service
    /// timed out" — which would send somebody looking at the wrong service.
    /// </summary>
    [Fact]
    public async Task Caller_cancellation_propagates()
    {
        var handler = new StubHandler(async (_, ct) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(30), ct);
            return new HttpResponseMessage(HttpStatusCode.OK);
        });
        using var cts = new CancellationTokenSource();
        var pending = Build(handler, timeoutMs: 10_000)
            .PredictAsync(Request(), cts.Token);
        await cts.CancelAsync();

        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => pending);
    }

    // ── The options ───────────────────────────────────────────────────

    /// <summary>
    /// <c>new Uri(base, "predict")</c> drops the last segment of a base that
    /// does not end in a slash, so <c>http://h/ml</c> would resolve to
    /// <c>http://h/predict</c> — a 404 against a service that is running
    /// fine.
    /// </summary>
    [Fact]
    public void A_base_url_without_a_trailing_slash_is_normalised()
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["MlService:BaseUrl"] = "http://ml.test/ml",
                ["MlService:InternalKey"] = Key,
            })
            .Build();

        var options = MlOptions.FromConfiguration(config);

        Assert.Equal("http://ml.test/ml/", options.BaseUrl);
        Assert.True(options.Enabled);
        Assert.Equal(
            "http://ml.test/ml/predict",
            new Uri(new Uri(options.BaseUrl), "predict").ToString());
    }

    /// <summary>
    /// The budget specification §8.1 states in prose, as a number this side
    /// can be held to.
    /// </summary>
    [Fact]
    public void The_default_timeout_is_the_two_seconds_of_the_specification()
        => Assert.Equal(2000, new MlOptions().TimeoutMs);

    [Fact]
    public void A_blank_key_counts_as_not_configured()
    {
        Assert.False(new MlOptions { InternalKey = "   " }.Enabled);
        Assert.False(new MlOptions().Enabled);
        Assert.True(new MlOptions { InternalKey = "k" }.Enabled);
    }

    // ── The guards on the two newer calls ─────────────────────────────

    /// <summary>
    /// <c>chk_expl_ratio</c> caps <c>meal_plans.exploration_ratio</c> at 0.5,
    /// so a plan built with more than that could not be written even if one
    /// came back. Refused before the request, and the proof is that no
    /// request was made: a round trip spent to be told something this side
    /// already knows is a round trip out of the 2 s budget.
    /// </summary>
    [Theory]
    [InlineData(0.51)]
    [InlineData(1.0)]
    [InlineData(-0.1)]
    public async Task A_plan_outside_the_exploration_cap_never_leaves_here(
        double ratio)
    {
        var handler = new StubHandler(HttpStatusCode.OK, "{}");
        var client = Build(handler);

        var result = await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            ExplorationRatio = ratio,
        });

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.Equal("EXPLORATION_OUT_OF_RANGE", result.Failure.Code);
        Assert.Equal(0, handler.Calls);
        // NOT degradable: it is a bug on this side, and serving a plan
        // anyway would hide it for as long as the code lives.
        Assert.False(result.Failure.IsDegradable);
    }

    [Theory]
    [InlineData(0.0)]
    [InlineData(0.3)]
    [InlineData(0.5)]
    public async Task A_ratio_inside_the_cap_is_sent(double ratio)
    {
        var handler = new StubHandler(
            HttpStatusCode.ServiceUnavailable, "{}");
        var client = Build(handler);

        await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            ExplorationRatio = ratio,
        });

        Assert.Equal(1, handler.Calls);
    }

    /// <summary>
    /// §7.4.1's deck is 20 to 50 foods. Checked here so the caller gets a
    /// named field back instead of FastAPI's own schema error, which carries
    /// the library's wording and no <c>error.code</c>.
    /// </summary>
    [Theory]
    [InlineData(19)]
    [InlineData(51)]
    [InlineData(0)]
    public async Task A_deck_size_outside_the_range_never_leaves_here(
        int size)
    {
        var handler = new StubHandler(HttpStatusCode.OK, "{}");
        var client = Build(handler);

        var result = await client.SurveyDeckAsync(new MlSurveyDeckRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            Size = size,
        });

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.Equal("DECK_SIZE_OUT_OF_RANGE", result.Failure.Code);
        Assert.Equal(0, handler.Calls);
    }

    /// <summary>
    /// <c>/plan</c>'s two "complete a step first" codes have to survive the
    /// trip through <see cref="MlClient"/> as their own kinds. Without the
    /// mapping they fall through to the status switch, become
    /// <c>BadRequest</c>, and reach the user as "lỗi máy chủ" when the real
    /// answer is "khai báo hồ sơ sức khỏe".
    /// </summary>
    [Theory]
    [InlineData("PROFILE_REQUIRED", MlFailureKind.ProfileRequired)]
    [InlineData("ONBOARDING_REQUIRED", MlFailureKind.OnboardingRequired)]
    public async Task The_plan_input_errors_keep_their_own_kind(
        string code, MlFailureKind expected)
    {
        var handler = new StubHandler(
            HttpStatusCode.UnprocessableEntity,
            Envelope(code, "Step 1 has never run for this user."));
        var client = Build(handler);

        var result = await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
        });

        Assert.False(result.Ok);
        Assert.Equal(expected, result.Failure!.Kind);
        Assert.Equal(code, result.Failure.Code);
        Assert.False(result.Failure.IsDegradable);
    }

    /// <summary>
    /// An empty <c>MealTypes</c> is not "all four": it is a caller that
    /// worked out a set of meals and got none. Sending it would have the
    /// service answer <c>400</c> for something this side already knows.
    /// </summary>
    [Fact]
    public async Task An_empty_meal_type_list_never_leaves_here()
    {
        var handler = new StubHandler(HttpStatusCode.OK, "{}");
        var client = Build(handler);

        var result = await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            MealTypes = [],
        });

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.Equal("EMPTY_MEAL_TYPES", result.Failure.Code);
        Assert.Equal(0, handler.Calls);
    }

    /// <summary>
    /// <c>null</c> is the whole day, and a named subset is sent as it
    /// stands. The field is the wire contract, so this also pins the name
    /// <c>ml/api.py</c> reads.
    /// </summary>
    [Fact]
    public async Task A_named_subset_of_meals_is_sent_as_it_is()
    {
        var handler = new StubHandler(
            HttpStatusCode.ServiceUnavailable, "{}");
        var client = Build(handler);

        await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            MealTypes = ["snack"],
        });

        Assert.Equal(1, handler.Calls);
        Assert.Contains("\"mealTypes\":[\"snack\"]", handler.LastBody);
    }

    /// <summary>
    /// <c>MEAL_PLAN_REQUIRED</c> means this backend asked for a meal of a day
    /// that has no plan — a bug on this side, not a step the user has to
    /// complete. It must NOT degrade, and it must not reach the user as
    /// "try again later".
    /// </summary>
    [Fact]
    public async Task A_meal_of_a_day_with_no_plan_is_a_bug_on_this_side()
    {
        var client = Build(new StubHandler(
            HttpStatusCode.UnprocessableEntity,
            Envelope("MEAL_PLAN_REQUIRED", "No plan for that date.")));

        var result = await client.PlanAsync(new MlPlanRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            MealTypes = ["snack"],
        });

        Assert.False(result.Ok);
        Assert.Equal(MlFailureKind.BadRequest, result.Failure!.Kind);
        Assert.False(result.Failure.IsDegradable);
    }

    /// <summary>
    /// The deck's reply reaches this side with the field names
    /// <c>ml/api.py</c> sends — the contract is the property names, and a
    /// rename on either side is a silent null here.
    /// </summary>
    [Fact]
    public async Task The_deck_reply_is_read_field_for_field()
    {
        const string body = """
        {
          "userId": "00000001-0000-4000-8000-000000000000",
          "foodIds": ["f1", "f2"],
          "totalItems": 2,
          "minRequired": 2,
          "nFoodsBeforeF1": 318,
          "nFoodsAfterF1": 204,
          "nCategories": 11,
          "nCategoriesTotal": 12,
          "featureVersion": "v2",
          "warnings": ["27 of 30 foods in this deck are at spice level 0"],
          "elapsedMs": 180
        }
        """;
        var client = Build(new StubHandler(HttpStatusCode.OK, body));

        var result = await client.SurveyDeckAsync(new MlSurveyDeckRequest
        {
            UserId = "00000001-0000-4000-8000-000000000000",
            Size = 30,
        });

        Assert.True(result.Ok);
        var deck = result.Required;
        Assert.Equal(["f1", "f2"], deck.FoodIds);
        Assert.Equal(2, deck.MinRequired);
        Assert.Equal(318, deck.NFoodsBeforeF1);
        Assert.Equal(204, deck.NFoodsAfterF1);
        Assert.Equal(11, deck.NCategories);
        Assert.Equal("v2", deck.FeatureVersion);
        Assert.Single(deck.Warnings);
    }

    /// <summary>
    /// The four values <c>db/schema.sql</c> declares for
    /// <c>meal_plans.generation_source</c>, and nothing else: an invalid
    /// value is a rejected write, or a silent truncation outside strict mode.
    /// </summary>
    [Fact]
    public void GenerationSource_matches_the_column()
    {
        Assert.True(GenerationSource.IsValid("rule_based"));
        Assert.True(GenerationSource.IsValid("content_based"));
        Assert.True(GenerationSource.IsValid("ml"));
        Assert.True(GenerationSource.IsValid("hybrid"));
        Assert.False(GenerationSource.IsValid("ml_based"));
        Assert.False(GenerationSource.IsValid(null));

        // The three `ml/serve.py` actually emits (SOURCE_BY_STAGE).
        Assert.True(GenerationSource.IsValid(GenerationSource.RuleBased));
        Assert.True(GenerationSource.IsValid(GenerationSource.ContentBased));
        Assert.True(GenerationSource.IsValid(GenerationSource.Hybrid));
    }
}
