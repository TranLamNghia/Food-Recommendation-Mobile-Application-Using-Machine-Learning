namespace Api.Ml;

/// <summary>
/// The request and response bodies of specification §8, mirroring the
/// Pydantic models of <c>ml/api.py</c> field for field.
///
/// <para>The property names are the JSON names: the ML service speaks
/// camelCase (<c>userId</c>, <c>candidateFoodIds</c>), and
/// <see cref="MlClient"/> serialises with
/// <c>JsonNamingPolicy.CamelCase</c>, so a C# <c>UserId</c> lands as
/// <c>userId</c>. Renaming a property here therefore changes the wire
/// contract — <c>ml/api.py</c> has to change in the same commit, and
/// <c>tools/smoke_ml_api.py</c> proves the pair still agree.</para>
///
/// <para>Note on language: nothing in this file is user-facing. The strings
/// that travel in <see cref="MlPredictResponse.Warnings"/> come from
/// <c>ml/serve.py</c> and are developer-facing English, for the log — they
/// are not an <c>error.message</c>.</para>
/// </summary>
public sealed record MlPredictRequest
{
    public required string UserId { get; init; }

    /// <summary>
    /// <b>Leave this null.</b> The ML service then reads the whole active
    /// catalogue itself, applies the F1 filter and scores what remains.
    ///
    /// <para>That is the point of the current design: the backend used to
    /// assemble a candidate set and ask for scores on it, which put two
    /// layers in charge of which foods exist. A food the backend forgot to
    /// send then looked exactly like a food the F1 filter removed, and
    /// nothing could tell the two apart. The backend now has exactly one say
    /// in the candidate set — <see cref="ExcludeFoodIds"/>, which is the
    /// part the ML service cannot know.</para>
    ///
    /// <para>A list is for debugging and for scoring a known handful. An
    /// EMPTY list is rejected before the request leaves — "score nothing" is
    /// never the question, so it is a bug upstream.</para>
    /// </summary>
    public IReadOnlyList<string>? CandidateFoodIds { get; init; }

    /// <summary>
    /// The foods already used today, so a plan does not repeat a dish. The
    /// one piece of the candidate set this backend knows and the ML service
    /// does not.
    /// </summary>
    public IReadOnlyList<string> ExcludeFoodIds { get; init; } = [];

    /// <summary>
    /// <c>breakfast</c> | <c>lunch</c> | <c>dinner</c> | <c>snack</c>, or
    /// <c>null</c>.
    /// </summary>
    public string? ContextMealType { get; init; }

    /// <summary>
    /// Optional, and <b>not</b> what the service scores from: it reads
    /// <c>health_profiles</c> itself and returns any disagreement in
    /// <see cref="MlPredictResponse.Warnings"/>. Sending it is therefore a
    /// cross-check of this backend's own view of the user, which is worth
    /// more than the handful of bytes it costs.
    /// </summary>
    public MlUserFeatures? UserFeatures { get; init; }
}

public sealed record MlUserFeatures
{
    public int? Age { get; init; }
    public string? Gender { get; init; }
    public double? Bmi { get; init; }
    public string? ActivityLevel { get; init; }
    public string? Goal { get; init; }
    public double? RemainingCaloriesKcal { get; init; }
}

public sealed record MlFoodScore
{
    public string FoodId { get; init; } = string.Empty;

    /// <summary>The blended score Step 4 ranks by.</summary>
    public double Score { get; init; }

    public double ScoreContent { get; init; }

    /// <summary>
    /// <c>null</c> below Stage 2 — there is no model term to report. Not 0:
    /// a 0 would rank the food last instead of saying "this layer did not
    /// run", which is the same mistake as reading a missing nutrient as 0.
    /// </summary>
    public double? ScoreMl { get; init; }

    public double ScoreRule { get; init; }
}

public sealed record MlPredictResponse
{
    /// <summary><c>null</c> when no model took part.</summary>
    public string? ModelVersion { get; init; }

    /// <summary>
    /// The feature space the scores were produced in. <b>Compare it</b>
    /// against what this backend expects before storing a plan: training in
    /// one space and inferring in another errors nowhere, it just returns
    /// numbers that are wrong.
    /// </summary>
    public string FeatureVersion { get; init; } = string.Empty;

    /// <summary><c>cold</c> | <c>content</c> | <c>hybrid</c>.</summary>
    public string Stage { get; init; } = string.Empty;

    /// <summary>
    /// The ML weight actually used. 0 means the answer is pure
    /// content/rule scoring — a <c>200</c> can still be a degraded answer,
    /// which is why <see cref="GenerationSource"/> travels with it.
    /// </summary>
    public double Alpha { get; init; }

    /// <summary>
    /// What to write into <c>meal_plans.generation_source</c>:
    /// <c>rule_based</c> | <c>content_based</c> | <c>hybrid</c>. Take it
    /// from here rather than deriving it from <see cref="Stage"/> — the
    /// mapping lives in <c>ml/serve.py</c> (<c>SOURCE_BY_STAGE</c>) and
    /// deriving it again here is a second copy that can drift.
    ///
    /// <para>The column also accepts <c>ml</c>, which the service never
    /// emits today.</para>
    /// </summary>
    public string GenerationSource { get; init; } = string.Empty;

    public IReadOnlyList<MlFoodScore> Scores { get; init; } = [];

    /// <summary>
    /// Candidates that were asked for and came back unscored, because the F1
    /// filter removed them. Empty when
    /// <see cref="MlPredictRequest.CandidateFoodIds"/> was null, which is the
    /// normal case — nothing specific was asked for, so use
    /// <see cref="NFoodsBeforeF1"/> and <see cref="NFoodsAfterF1"/> instead.
    /// </summary>
    public IReadOnlyList<string> SkippedFoodIds { get; init; } = [];

    /// <summary>
    /// How many active foods existed before the F1 filter, and how many
    /// survived it for this user.
    ///
    /// <para>This backend can no longer work the pair out for itself, since
    /// it does not assemble the candidate set. It is what an honest
    /// <c>RULE_TOO_RESTRICTIVE</c> answer is built from: "318 foods, 2 left"
    /// explains something, "no feasible plan" does not. It is not the
    /// per-role <c>foodsRemaining</c> breakdown of §7.6 — Step 4 knows the
    /// roles, the ML service does not.</para>
    /// </summary>
    public int NFoodsBeforeF1 { get; init; }

    /// <inheritdoc cref="NFoodsBeforeF1"/>
    public int NFoodsAfterF1 { get; init; }

    /// <summary>
    /// Developer-facing English, including any mismatch between
    /// <see cref="MlPredictRequest.UserFeatures"/> and the database. Log
    /// these; a non-empty list means two layers disagree about one user.
    /// </summary>
    public IReadOnlyList<string> Warnings { get; init; } = [];

    public int ElapsedMs { get; init; }
}

public sealed record MlRebuildResponse
{
    public string UserId { get; init; } = string.Empty;
    public string FeatureVersion { get; init; } = string.Empty;

    /// <summary>
    /// How many usable signals the vector was built from. This is what
    /// decides the stage, so it is also the number to log when a
    /// recommendation looks oddly generic.
    /// </summary>
    public int NSignals { get; init; }

    public double SumAbsWeight { get; init; }
    public string Stage { get; init; } = string.Empty;
    public double Alpha { get; init; }

    /// <summary>
    /// Asia/Ho_Chi_Minh, like every other timestamp in this system except
    /// JWT <c>nbf</c>/<c>exp</c>. Kept as the string the service sent
    /// rather than parsed into a <c>DateTime</c>, which would silently
    /// convert it to the server's local zone.
    /// </summary>
    public string UpdatedAt { get; init; } = string.Empty;
}

public sealed record MlTrainRequest
{
    public required string DatasetVersion { get; init; }

    /// <summary>
    /// <c>logistic_regression</c> | <c>random_forest</c> |
    /// <c>gradient_boosting</c> — exactly the three <c>ml/train.py</c>
    /// implements. See <see cref="MlAlgorithm"/>.
    /// </summary>
    public string Algorithm { get; init; } = MlAlgorithm.GradientBoosting;

    /// <summary>
    /// Whether the new model becomes <c>is_active = 1</c> at once. Defaults
    /// to <c>false</c>: a model goes live after <c>ml/evaluate.py</c> has
    /// something to say about it, not because training finished.
    /// </summary>
    public bool Activate { get; init; }
}

/// <summary>
/// The three algorithm names, as constants. Same reasoning as
/// <c>ErrorCode</c>: a typo in a hand-typed string is a rejected request at
/// runtime, found by whoever next runs a retrain.
/// </summary>
public static class MlAlgorithm
{
    public const string LogisticRegression = "logistic_regression";
    public const string RandomForest = "random_forest";
    public const string GradientBoosting = "gradient_boosting";

    public static readonly string[] All =
        [LogisticRegression, RandomForest, GradientBoosting];
}

public sealed record MlTrainResponse
{
    public string JobId { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
    public string StartedAt { get; init; } = string.Empty;
}

public sealed record MlHealthModel
{
    public string Version { get; init; } = string.Empty;
    public string Algorithm { get; init; } = string.Empty;
    public string? TrainedAt { get; init; }
}

public sealed record MlHealthResponse
{
    /// <summary>
    /// <c>healthy</c> or <c>degraded</c>. <c>degraded</c> is a <c>200</c>:
    /// the service is up, there is just no active model, and scoring still
    /// works at Stage 1.
    /// </summary>
    public string Status { get; init; } = string.Empty;

    public MlHealthModel? ActiveModel { get; init; }
    public string FeatureVersion { get; init; } = string.Empty;

    /// <summary>Why it is degraded, when it is.</summary>
    public string? Reason { get; init; }
}

/// <summary>
/// The <c>meal_plans.generation_source</c> values, as constants.
/// <c>db/schema.sql</c> declares the column
/// <c>ENUM('rule_based','content_based','ml','hybrid')</c>, so a value not in
/// this list is a write MySQL rejects — or, outside strict mode, truncates to
/// the empty string.
/// </summary>
public static class GenerationSource
{
    /// <summary>
    /// Also what to record when the ML service could not be reached and the
    /// plan was built from rules alone — specification §8.1.
    /// </summary>
    public const string RuleBased = "rule_based";

    public const string ContentBased = "content_based";
    public const string Ml = "ml";
    public const string Hybrid = "hybrid";

    public static bool IsValid(string? value) => value is RuleBased
        or ContentBased or Ml or Hybrid;
}
