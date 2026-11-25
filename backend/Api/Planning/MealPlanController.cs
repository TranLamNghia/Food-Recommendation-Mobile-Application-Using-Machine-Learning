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

            // One meal at a time has its own endpoint, because it is a
            // different operation: it rebuilds a meal INSIDE an existing
            // day, so the day stays the unit the ±10 % and every per-day
            // threshold are measured over. Creating a plan that contains
            // only a snack would instead make `calorie_deviation_pct` a
            // deviation from the whole day's target with one dish against
            // it — about −92 % for a 150 kcal snack, recorded in the column
            // Chapter 3 reads.
            if (requested.Distinct().Count() != Enums.MealType.Length)
            {
                return Invalid(
                    "mealTypes",
                    "Sinh cả bốn bữa thì gọi endpoint này; sinh lại một bữa "
                    + "thì gọi POST /meal-plans/{id}/meals/{mealType}, vì "
                    + "một bữa chỉ sinh được bên trong thực đơn của ngày");
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

            // How much of the day is still the system's to decide.
            //
            // Regenerating used to delete the whole plan and build a fresh
            // day at the FULL energy target, whatever had been eaten from
            // the old one. The eaten dishes were excluded from the candidate
            // set — so the new day did not repeat them — but nothing
            // subtracted their energy, and nothing anywhere added the diary
            // to the plan. A user who ate their 2 542 kcal day and pressed
            // the button got a second whole day, reporting itself at −1 %
            // of target, for an actual ~5 100 kcal. The ±10 % commitment was
            // being measured on the plan rather than on the day.
            //
            // So the SCOPE now follows the state of the day, and the request
            // body is unchanged: one call still replaces a whole untouched
            // day, which is what the button is for.
            var eatenMeals = await db.MealPlanItems
                .Where(i => i.MealPlanId == existing.Id
                            && i.Status == MealItemStatus.Eaten)
                .Select(i => i.MealType)
                .Distinct()
                .ToListAsync(ct);

            if (eatenMeals.Count > 0)
            {
                var untouched = Enums.MealType
                    .Where(m => !eatenMeals.Contains(m))
                    .ToList();

                if (untouched.Count == 0)
                {
                    // Every meal has something eaten in it. There is no part
                    // of the day left to plan, and planning another whole
                    // one would be the bug this branch exists to close.
                    return ApiProblem.Make(
                        409, ErrorCode.ValidationFailed,
                        "Cả bốn bữa hôm nay đều đã có món được đánh dấu là "
                        + "đã ăn, nên không còn phần nào để sinh lại",
                        HttpContext.TraceIdentifier,
                        [new ApiError.FieldError
                        {
                            Field = "regenerate",
                            Message = "Hãy bỏ đánh dấu đã ăn ở bữa muốn "
                                + "đổi, hoặc đổi từng món bằng chức năng "
                                + "thay thế món",
                        }]);
                }

                log.LogInformation(
                    "Plan {PlanId} of {Day} for {User}: {Eaten} already has "
                    + "eaten dishes, so the regenerate rebuilds {Untouched} "
                    + "only and the day is measured around what was eaten.",
                    existing.Id, day, uid, string.Join("+", eatenMeals),
                    string.Join("+", untouched));

                return await RebuildMealsAsync(existing, untouched, ct);
            }

            // Nothing eaten: the whole day is still the system's to decide,
            // and this is the path the button was designed for.
            //
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

    // ── 7.6.2b Rebuild one meal of a day ─────────────────────────────────

    /// <summary>
    /// Rebuilds one meal inside an existing plan, keeping the other three.
    ///
    /// <para>Not in the specification, and it is what §7.6.2's
    /// <c>mealTypes</c> was asking for. The difference that matters is where
    /// the figures are measured: the plan row stays the <b>day's</b> row,
    /// its target stays the day's target, and <c>actual_*</c> is recomputed
    /// over all four meals — so <c>calorie_deviation_pct</c> keeps meaning
    /// what the column means. Exceeding ±10 % is allowed and reported
    /// (<c>withinTolerance = false</c> plus a log line), not refused: a user
    /// who wants another snack may have it, and the figure stays
    /// honest.</para>
    ///
    /// <para>A meal with a dish already marked <c>eaten</c> cannot be
    /// rebuilt. That dish is in the food diary and is a preference signal of
    /// weight 0.9; replanning around it would mean deleting a record of
    /// something that happened.</para>
    /// </summary>
    [HttpPost("{id}/meals/{mealType}")]
    public async Task<IActionResult> RegenerateMeal(
        string id,
        string mealType,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        if (!Enums.MealType.Contains(mealType))
        {
            return Invalid(
                "mealType",
                "Bữa không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.MealType));
        }

        var plan = await db.MealPlans.FirstOrDefaultAsync(p => p.Id == id, ct);
        if (plan is null)
        {
            return Fail(404, ErrorCode.NotFound, "Không tìm thấy thực đơn");
        }
        if (plan.UserId != uid)
        {
            return Fail(403, ErrorCode.Forbidden,
                        "Thực đơn này không thuộc tài khoản của bạn");
        }

        var ofMeal = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan.Id && i.MealType == mealType)
            .ToListAsync(ct);

        if (ofMeal.Any(i => i.Status == MealItemStatus.Eaten))
        {
            // `409`, not `400`: the request is well formed and the state of
            // the resource is what refuses it. §4's catalogue has no code
            // for this case, so it reuses VALIDATION_FAILED with the field
            // named — which is the only code §2.5 sends `details` with.
            return ApiProblem.Make(
                409, ErrorCode.ValidationFailed,
                "Bữa này đã có món được đánh dấu là đã ăn, nên không sinh "
                + "lại được",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "mealType",
                    Message = "Hãy bỏ đánh dấu đã ăn, hoặc đổi từng món "
                        + "bằng chức năng thay thế món",
                }]);
        }

        // The dishes currently in this meal are excluded, so "sinh lại" is
        // a DIFFERENT meal and not the same one again. Without this the
        // answer is identical: `_greedy_pick` is deterministic, and a
        // one-serving meal draws no exploration serving either
        // (`round(1 * 0.3) == 0`), so the same food wins every time. Forcing
        // an exploration serving instead would make that meal 100 %
        // exploration and move a figure Chapter 3 measures.
        return await RebuildMealsAsync(plan, [mealType], ct);
    }

    /// <summary>
    /// Rebuilds <paramref name="mealTypes"/> inside <paramref name="plan"/>,
    /// leaving every other meal exactly as it is.
    ///
    /// <para>One body for two callers: §7.6's per-meal endpoint passes one
    /// meal, and a full-day regenerate passes the meals that have nothing
    /// eaten in them. They were the same operation all along — the only
    /// difference was the length of the list — and writing it twice is how
    /// the two would start disagreeing about what a rebuild does to the old
    /// rows.</para>
    ///
    /// <para><b>The day stays the unit of measurement.</b> The ML service is
    /// asked for a subset of an existing day, so it keeps the meals it was
    /// not asked about and measures the ±10 % and every per-day threshold
    /// over the whole thing. A meal rebuilt around servings the user has
    /// already eaten is fitted into what is left of the day's budget, and if
    /// there is not enough left the day reports
    /// <c>withinTolerance = false</c> — which is the honest answer and the
    /// reason this is not a silent recalculation.</para>
    /// </summary>
    private async Task<IActionResult> RebuildMealsAsync(
        Entities.MealPlans plan,
        IReadOnlyList<string> mealTypes,
        CancellationToken ct)
    {
        var ofMeals = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan.Id
                        && mealTypes.Contains(i.MealType))
            .ToListAsync(ct);

        // The dishes currently in these meals are excluded, so "sinh lại" is
        // a DIFFERENT meal and not the same one again. Without this the
        // answer is identical: `_greedy_pick` is deterministic, and a
        // one-serving meal draws no exploration serving either
        // (`round(1 * 0.3) == 0`), so the same food wins every time. Forcing
        // an exploration serving instead would make that meal 100 %
        // exploration and move a figure Chapter 3 measures.
        var current = ofMeals
            .Where(i => i.Status != MealItemStatus.Replaced)
            .Select(i => i.FoodId)
            .Distinct()
            .ToList();

        var asked = await AskPlanAsync(
            plan.UserId, plan.PlanDate,
            (double?)plan.ExplorationRatio ?? DefaultExplorationRatio,
            mealTypes, ct, alsoExclude: current);
        if (asked.Problem is not null)
        {
            return asked.Problem;
        }
        var result = asked.Result!;

        var rebuilt = result.Meals
            .Where(m => mealTypes.Contains(m.MealType))
            .SelectMany(m => m.Items)
            .ToList();
        if (rebuilt.Count == 0)
        {
            // Nothing else fits these meals' roles once the current dishes
            // are excluded. The old meals are left exactly as they were: an
            // empty meal would be a worse answer than the one the user
            // already had, and deleting the rows first and discovering this
            // afterwards is how a plan ends up with a hole in it.
            return ApiProblem.Make(
                409, ErrorCode.NoFeasiblePlan,
                mealTypes.Count == 1
                    ? "Không còn món nào khác phù hợp cho bữa này, nên thực "
                      + "đơn được giữ nguyên"
                    : "Không còn món nào khác phù hợp cho những bữa chưa ăn, "
                      + "nên thực đơn được giữ nguyên",
                HttpContext.TraceIdentifier);
        }

        var now = Clock.Now;
        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            // The `replaced` rows of these meals stay. They are the record
            // of a swap the user made, and §4.6 reads them as a rejection of
            // the old dish — deleting them would erase a training signal
            // because the meal was re-rolled afterwards.
            var drop = ofMeals
                .Where(i => i.Status != MealItemStatus.Replaced)
                .ToList();
            db.MealPlanItems.RemoveRange(drop);
            await db.SaveChangesAsync(ct);

            WriteItems(plan, result, mealTypes, now);
            await db.SaveChangesAsync(ct);

            await MealPlanMapper.RecomputeActualsAsync(db, plan, ct);
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        await db.Entry(plan).ReloadAsync(ct);

        var violations = Violations(result);
        if (plan.CalorieDeviationPct is { } deviation
            && Math.Abs(deviation) > MealPlanMapper.ToleranceP)
        {
            // Allowed, and written down. The user asked for this rebuild;
            // the day's figure is what it is, and a plan that quietly
            // reported itself as within tolerance would be the dishonest
            // option. It is also the state a user who has already eaten
            // their whole target lands in, which is exactly when they most
            // need to be told.
            log.LogInformation(
                "Plan {PlanId}: {Meals} rebuilt and the day is now "
                + "{Deviation} % from its energy target, outside the ±10 % "
                + "the proposal commits to. The plan is kept and reports "
                + "withinTolerance = false.",
                plan.Id, string.Join("+", mealTypes), deviation);
        }

        return Ok(await MealPlanMapper.BuildAsync(db, plan, violations, ct));
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
        var asked = await AskPlanAsync(
            uid, day, explorationRatio, mealTypes: null, ct);
        if (asked.Problem is not null)
        {
            return (null, asked.Problem);
        }
        var result = asked.Result!;

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

            WriteItems(plan, result, Enums.MealType, now);
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

        var violations = Violations(result);
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

    /// <summary>
    /// Asks the ML service for a day, or for some meals of one, and logs
    /// what the answer says about itself.
    ///
    /// <para>Shared by the whole-day build and the one-meal rebuild so that
    /// the two cannot start reporting different things about the same
    /// answer — above all the unmeasurable thresholds, which are the line in
    /// the log that says a safety rule went unchecked.</para>
    /// </summary>
    private async Task<(MlPlanResponse? Result, ObjectResult? Problem)>
        AskPlanAsync(
            string uid,
            DateOnly day,
            double explorationRatio,
            IReadOnlyList<string>? mealTypes,
            CancellationToken ct,
            IReadOnlyCollection<string>? alsoExclude = null)
    {
        // What the user has already eaten today, so the plan does not
        // suggest a dish they have had. Only today's plan in practice, but
        // the query is the same for any day the diary covers.
        var eaten = await db.FoodDiary
            .Where(d => d.UserId == uid && d.AteOn == day)
            .Select(d => d.FoodId)
            .Distinct()
            .ToListAsync(ct);

        var exclude = alsoExclude is null
            ? eaten
            : eaten.Concat(alsoExclude).Distinct().ToList();

        var answer = await ml.PlanAsync(
            new MlPlanRequest
            {
                UserId = uid,
                PlanDate = day.ToString("yyyy-MM-dd"),
                ExcludeFoodIds = exclude,
                ExplorationRatio = explorationRatio,
                MealTypes = mealTypes,
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

        return (result, null);
    }

    /// <summary>
    /// Adds the <c>meal_plan_items</c> rows for <paramref name="meals"/>.
    /// Does not save: the caller is inside the transaction that also writes
    /// the plan's totals.
    /// </summary>
    private void WriteItems(
        MealPlans plan,
        MlPlanResponse result,
        IReadOnlyCollection<string> meals,
        DateTime now)
    {
        foreach (var meal in result.Meals.Where(m => meals.Contains(m.MealType)))
        {
            foreach (var item in meal.Items)
            {
                db.MealPlanItems.Add(new MealPlanItems
                {
                    Id = Guid.NewGuid().ToString(),
                    MealPlanId = plan.Id,
                    FoodId = item.FoodId,
                    MealType = meal.MealType,
                    // Taken from the answer rather than hard-coded to 1.00.
                    // Step 4 chooses dishes and not portions, so it is 1.00
                    // for everything it picks; reading the field keeps that
                    // a fact about the answer instead of an assumption, and
                    // the energy check in GenerateAsync is what reports a
                    // disagreement.
                    PortionMultiplier = Math.Clamp(
                        Math.Round((decimal)item.Portion, 2,
                                   MidpointRounding.AwayFromZero),
                        0.1m, 5m),
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
    }

    private static List<NutrientViolationDto> Violations(
        MlPlanResponse result)
        => result.NutrientViolations
            .Select(v => new NutrientViolationDto
            {
                Nutrient = v.Nutrient,
                Comparator = v.Comparator,
                Threshold = Round2(v.Threshold),
                Actual = Round2(v.Actual),
                Condition = v.Condition,
            })
            .ToList();

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
