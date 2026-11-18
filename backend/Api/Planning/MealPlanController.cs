using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Profile;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Planning;

/// <summary>
/// The meal plan — specification §7.6.1, §7.6.2 and §7.6.3.
///
/// <para>This is where the whole algorithm becomes something a user can see.
/// Step 1 lives in <c>Api.Nutrition</c>, Steps 2 to 4 live in the ML service;
/// this controller asks for a day, writes it down, and owns it afterwards.
/// Until it existed, <c>meal_plans</c> had no rows at all: plans could be
/// assembled but not kept, which also meant none of the signals §4.6 learns
/// from — kept, replaced, eaten — could ever be recorded.</para>
///
/// <para><b>Who writes what.</b> The ML service writes the <c>ml_*</c>
/// tables and reads everything else; <c>meal_plans</c> and
/// <c>meal_plan_items</c> are written only here. That is what lets the
/// <c>409 MEAL_PLAN_EXISTS</c> rule, the ownership check and the
/// authentication sit in one place instead of being enforced twice.</para>
///
/// <para><b>No soft degradation.</b> §7.6.2 describes a backend that answers
/// <c>200</c> with <c>generationSource = "rule_based"</c> when the ML service
/// is silent. That was dropped deliberately: a rule-based plan looks exactly
/// like a real one, so a server quietly serving them is indistinguishable
/// from a working one — to the user, and to anyone reading the logs. An
/// unreachable ML service now produces <c>503 ML_UNAVAILABLE</c> and the app
/// shows "thử lại sau". <c>Api.Ml.MlFailureResponse</c> is where that
/// mapping lives, and <c>db/schema.sql</c> still accepts
/// <c>rule_based</c>.</para>
///
/// <para>Note on language: every <c>message</c> here is Vietnamese — the
/// <c>error.message</c> of §2.5 that users read — while <c>error.code</c> is
/// the stable string the app branches on.</para>
/// </summary>
[ApiController]
[Route("api/v1/meal-plans")]
[Authorize]
public sealed class MealPlanController(
    AppDbContext db,
    IMlClient ml,
    ILogger<MealPlanController> log) : ControllerBase
{
    /// <summary>
    /// The 70-30 mechanism's default target share — §4.6. Overridable per
    /// request for the Chapter 3 experiments.
    /// </summary>
    public const double DefaultExplorationRatio = 0.3;

    /// <summary>
    /// How far the energy a plan was built with may differ from what this
    /// backend recomputes from the stored portions before it is called a
    /// disagreement, in kcal.
    ///
    /// <para>One kcal, because the two numbers are the same sum of the same
    /// column and should differ only by rounding. See the note in
    /// <see cref="GenerateAsync"/> on why the macronutrients are
    /// <b>not</b> compared this way.</para>
    /// </summary>
    private const decimal EnergyAgreementKcal = 1m;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.6.1 The plan for one day ───────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> GetByDate(
        [FromQuery] DateOnly? date,
        [FromQuery] bool autoGenerate = true,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        if (date is not { } day)
        {
            return Invalid("date", "Thiếu ngày, định dạng YYYY-MM-DD");
        }

        var plan = await db.MealPlans
            .FirstOrDefaultAsync(p => p.UserId == uid && p.PlanDate == day,
                                 ct);
        if (plan is not null)
        {
            // `null` violations, not an empty list: nobody checked the
            // thresholds for THIS response. See the field's own note.
            return Ok(await MealPlanMapper.BuildAsync(db, plan, null, ct));
        }

        if (!autoGenerate)
        {
            return Fail(404, ErrorCode.NotFound,
                        "Chưa có thực đơn cho ngày này");
        }

        var (built, problem) = await GenerateAsync(
            uid, day, DefaultExplorationRatio, ct);
        return problem ?? Ok(built);
    }

    // ── 7.6.2 Generate a plan ────────────────────────────────────────────

    [HttpPost]
    public async Task<IActionResult> Generate(
        GeneratePlanRequest req, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var day = req.PlanDate!.Value;

        if (req.MealTypes is { } requested)
        {
            var unknown = requested
                .Where(m => !Enums.MealType.Contains(m))
                .ToList();
            if (unknown.Count > 0)
            {
                return Invalid(
                    "mealTypes",
                    "Bữa không hợp lệ: " + string.Join(", ", unknown));
            }

            // Refused rather than honoured. The reason is in
            // `GeneratePlanRequest.MealTypes`: phase 5 of Step 4 repairs the
            // plan at DAY level, so a single meal has no day to be measured
            // against, and `calorie_deviation_pct` would then record a
            // deviation from part of a target as though it were the whole.
            if (requested.Distinct().Count() != Enums.MealType.Length)
            {
                return Invalid(
                    "mealTypes",
                    "Hiện chỉ sinh được cả bốn bữa cùng lúc, vì hạn mức "
                    + "năng lượng và các ngưỡng dinh dưỡng được kiểm theo "
                    + "ngày, không theo từng bữa");
            }
        }

        var existing = await db.MealPlans
            .FirstOrDefaultAsync(p => p.UserId == uid && p.PlanDate == day,
                                 ct);
        if (existing is not null)
        {
            if (!req.Regenerate)
            {
                return Fail(409, ErrorCode.MealPlanExists,
                            "Đã có thực đơn cho ngày này");
            }

            // `ON DELETE CASCADE` on `meal_plan_items.meal_plan_id` takes the
            // dishes with it. Deliberate: the old plan's `kept`/`replaced`
            // rows are preference signals, and regenerating discards them —
            // which is why `regenerate` is not the default and the app should
            // ask first.
            db.MealPlans.Remove(existing);
            await db.SaveChangesAsync(ct);
            log.LogInformation(
                "Regenerated the plan of {Day} for {User}: the previous plan "
                + "{PlanId} and its items were deleted.",
                day, uid, existing.Id);
        }

        var (built, problem) = await GenerateAsync(
            uid, day, req.ExplorationRatio ?? DefaultExplorationRatio, ct);
        if (problem is not null)
        {
            return problem;
        }

        return StatusCode(StatusCodes.Status201Created, built);
    }

    // ── 7.6.3 One plan by id ─────────────────────────────────────────────

    [HttpGet("{id}")]
    public async Task<IActionResult> GetById(
        string id, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var plan = await db.MealPlans.FirstOrDefaultAsync(p => p.Id == id, ct);
        if (plan is null)
        {
            return Fail(404, ErrorCode.NotFound, "Không tìm thấy thực đơn");
        }
        if (plan.UserId != uid)
        {
            // 403 and not 404 — §7.6.3 is explicit: the plan exists, it is
            // simply not this user's. A 404 here would be the more private
            // answer, but the specification chose the honest one, and the id
            // is a UUID that cannot be guessed anyway.
            return Fail(403, ErrorCode.Forbidden,
                        "Thực đơn này không thuộc tài khoản của bạn");
        }

        return Ok(await MealPlanMapper.BuildAsync(db, plan, null, ct));
    }

    // ── generation ───────────────────────────────────────────────────────

    /// <summary>
    /// Asks the ML service for a day, writes it down, and returns §7.6.1's
    /// response for it.
    ///
    /// <para>One transaction for the plan and its dishes. Half a plan — a
    /// <c>meal_plans</c> row whose items failed to insert — would pass every
    /// later read as a real plan with an empty day in it, and
    /// <c>uq_user_date</c> would then block any attempt to build the day
    /// again.</para>
    /// </summary>
    private async Task<(MealPlanResponse? Built, ObjectResult? Problem)>
        GenerateAsync(
            string uid,
            DateOnly day,
            double explorationRatio,
            CancellationToken ct)
    {
        // What the user has already eaten today, so the plan does not suggest
        // a dish they have had. Only for today's plan in practice, but the
        // query is the same for any day the diary covers.
        var eaten = await db.FoodDiary
            .Where(d => d.UserId == uid && d.AteOn == day)
            .Select(d => d.FoodId)
            .Distinct()
            .ToListAsync(ct);

        var answer = await ml.PlanAsync(
            new MlPlanRequest
            {
                UserId = uid,
                PlanDate = day.ToString("yyyy-MM-dd"),
                ExcludeFoodIds = eaten,
                ExplorationRatio = explorationRatio,
            },
            ct);
        if (!answer.Ok)
        {
            return (null, Report(answer.Failure!));
        }

        var result = answer.Required;

        foreach (var warning in result.Warnings)
        {
            log.LogInformation(
                "Plan {Day} for {User}: {Warning}", day, uid, warning);
        }
        if (result.UnenforceableTargets.Count > 0)
        {
            // Error level: a threshold that cannot be measured is a safety
            // rule nothing enforces. Today that is `purine_mg` for gout —
            // the catalogue has no figures for it — and the plan says so
            // rather than reporting the targets as met.
            log.LogError(
                "Plan {Day} for {User} has {Count} nutrient threshold(s) on "
                + "an unmeasurable nutrient, so they were NOT checked: "
                + "{Targets}",
                day, uid, result.UnenforceableTargets.Count,
                string.Join(", ", result.UnenforceableTargets));
        }

        // `model_id` from the version string. A version that matches no row
        // means the model was deactivated between the plan being scored and
        // this query, which is not worth failing a write over — the column
        // stays NULL and `generation_source` still records that a model took
        // part.
        uint? modelId = null;
        if (result.ModelVersion is { } version)
        {
            modelId = await db.MlModels
                .Where(m => m.Version == version)
                .Select(m => (uint?)m.Id)
                .FirstOrDefaultAsync(ct);
            if (modelId is null)
            {
                log.LogWarning(
                    "The ML service scored plan {Day} with model {Version}, "
                    + "which is not in ml_models. meal_plans.model_id stays "
                    + "NULL.",
                    day, version);
            }
        }

        var now = Clock.Now;
        var plan = new MealPlans
        {
            Id = Guid.NewGuid().ToString(),
            UserId = uid,
            PlanDate = day,
            TargetCaloriesKcal = (ushort)Math.Clamp(
                Math.Round((decimal)result.TargetCaloriesKcal,
                           MidpointRounding.AwayFromZero),
                1, ushort.MaxValue),
            TargetProteinG = Round2(result.TargetProteinG),
            TargetCarbsG = Round2(result.TargetCarbsG),
            TargetFatG = Round2(result.TargetFatG),
            ExplorationRatio = Math.Round(
                (decimal)result.ExplorationRatio, 3,
                MidpointRounding.AwayFromZero),
            GenerationSource = GenerationSource.IsValid(
                result.GenerationSource)
                ? result.GenerationSource
                : Ml.GenerationSource.ContentBased,
            ModelId = modelId,
            Status = "active",
            GeneratedAt = now,
        };

        if (!GenerationSource.IsValid(result.GenerationSource))
        {
            log.LogError(
                "The ML service reported generationSource "
                + "'{Source}', which is not in the meal_plans ENUM. Stored "
                + "as '{Fallback}' so the write succeeds; the two sides "
                + "disagree about the §8 contract.",
                result.GenerationSource, Ml.GenerationSource.ContentBased);
        }

        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            db.MealPlans.Add(plan);

            // Saved on its own, BEFORE the items. The entities in
            // `Api/Entities` are generated from `db/schema.sql` and carry no
            // navigation properties, so EF Core does not know that an item
            // depends on its plan and is free to batch the inserts in the
            // other order — which MySQL then refuses on
            // `meal_plan_items_ibfk_1`. Two saves inside one transaction is
            // still one atomic write.
            await db.SaveChangesAsync(ct);

            foreach (var meal in result.Meals)
            {
                foreach (var item in meal.Items)
                {
                    db.MealPlanItems.Add(new MealPlanItems
                    {
                        Id = Guid.NewGuid().ToString(),
                        MealPlanId = plan.Id,
                        FoodId = item.FoodId,
                        MealType = meal.MealType,
                        // One standard serving. Step 4 chooses dishes, not
                        // portions: `ml/menu_builder.py` scores whole
                        // servings, and its energy figures are per serving.
                        // If it ever scales a portion, the energy check below
                        // is what reports it.
                        PortionMultiplier = 1.00m,
                        PredictedScore = Math.Round(
                            (decimal)item.PredictedScore, 4,
                            MidpointRounding.AwayFromZero),
                        Status = MealItemStatus.Suggested,
                        ExplorationDelta = item.ExplorationDelta is { } d
                            ? Math.Round((decimal)d, 3,
                                         MidpointRounding.AwayFromZero)
                            : null,
                        Position = (byte)Math.Clamp(item.Position, 0, 255),
                        CreatedAt = now,
                    });
                }
            }

            await db.SaveChangesAsync(ct);

            // Totals from the rows just written, not from the ML answer, so
            // that every later read and every replacement computes them the
            // same way. A plan whose stored totals came from one formula and
            // whose post-swap totals come from another would appear to change
            // energy for no reason the first time a dish was changed.
            await MealPlanMapper.RecomputeActualsAsync(db, plan, ct);
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        // The two sides should agree on energy to the rounding. They are NOT
        // compared on protein, carbohydrate or fat: `ml/features.py` imputes
        // a missing macronutrient from its category's median so that a food
        // can be scored at all, while this side sums the columns as they
        // stand. For a food with a NULL macro the two legitimately differ,
        // and `calories_kcal` is NOT NULL, so energy is the one honest
        // comparison.
        var mlKcal = Round2(result.ActualCaloriesKcal);
        if (plan.ActualCaloriesKcal is { } ours
            && Math.Abs(ours - mlKcal) > EnergyAgreementKcal)
        {
            log.LogError(
                "Plan {PlanId}: the ML service assembled {MlKcal} kcal but "
                + "the stored portions add up to {OurKcal} kcal. Step 4 may "
                + "be scaling portions, which this backend writes as 1.00 "
                + "servings; tools/smoke_backend.py checks this.",
                plan.Id, mlKcal, ours);
        }

        // `calorie_deviation_pct` is a GENERATED VIRTUAL column: the database
        // computes it on read, so the in-memory row still has the old value
        // (null) until it is reloaded.
        await db.Entry(plan).ReloadAsync(ct);

        var violations = result.NutrientViolations
            .Select(v => new NutrientViolationDto
            {
                Nutrient = v.Nutrient,
                Comparator = v.Comparator,
                Threshold = Round2(v.Threshold),
                Actual = Round2(v.Actual),
                Condition = v.Condition,
            })
            .ToList();

        if (violations.Count > 0)
        {
            log.LogWarning(
                "Plan {PlanId} breaches {Count} day-level nutrient "
                + "threshold(s): {Nutrients}. The plan is returned with them "
                + "listed rather than withheld.",
                plan.Id, violations.Count,
                string.Join(", ", violations.Select(v => v.Nutrient)));
        }

        return (
            await MealPlanMapper.BuildAsync(db, plan, violations, ct),
            null);
    }

    private ObjectResult Report(MlFailure failure)
    {
        if (failure.IsSystemFault())
        {
            log.LogError("Meal plan: {Detail}", failure.Detail);
        }
        else
        {
            log.LogInformation("Meal plan: {Detail}", failure.Detail);
        }
        return failure.ToActionResult(HttpContext.TraceIdentifier);
    }

    private static decimal Round2(double v)
        => Math.Round((decimal)v, 2, MidpointRounding.AwayFromZero);
}
