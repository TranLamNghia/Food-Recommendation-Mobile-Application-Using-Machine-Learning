using Api.Catalogue;
using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Planning;

/// <summary>
/// One dish inside a plan — specification §7.6.4, §7.6.5 and §7.6.6.
///
/// <para>These three are where the feedback loop of §4.6 actually closes.
/// Until they existed the model could only ever learn from the onboarding
/// swipes, which carry the lowest label weight of the four sources (0.7);
/// what a user <b>keeps</b>, <b>replaces</b> and <b>eats</b> carries 0.6, and
/// eating plus rating carries 0.9 and 1.0. A plan that cannot be edited
/// produces no signal at all.</para>
///
/// <para><b>Every endpoint checks ownership.</b> The id in the route is a
/// <c>meal_plan_items.id</c>, which says nothing about who owns it, so each
/// one walks up to the plan and compares <c>user_id</c> with the token's
/// <c>sub</c> — §2.4. <see cref="Locate"/> is that walk, written once.</para>
///
/// <para>Note on language: every <c>message</c> is Vietnamese — §2.5's
/// <c>error.message</c>, which users read — and every value compared or
/// stored (<c>status</c>, <c>meal_type</c>, <c>dish_role</c>) is an ENUM code
/// that is never translated here.</para>
/// </summary>
[ApiController]
[Route("api/v1/meal-plan-items")]
[Authorize]
public sealed class MealPlanItemController(
    AppDbContext db,
    IMlClient ml,
    ILogger<MealPlanItemController> log) : ControllerBase
{
    /// <summary>§7.6.4's defaults.</summary>
    public const int AlternativesDefaultLimit = 10;
    public const int AlternativesMaxLimit = 30;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.6.4 What could go in its place ─────────────────────────────────

    [HttpGet("{id}/alternatives")]
    public async Task<IActionResult> Alternatives(
        string id,
        [FromQuery] int limit = AlternativesDefaultLimit,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        if (limit is < 1 or > AlternativesMaxLimit)
        {
            return Invalid(
                "limit",
                $"limit phải trong khoảng 1 đến {AlternativesMaxLimit}");
        }

        var (item, plan, problem) = await Locate(id, uid, ct);
        if (problem is not null)
        {
            return problem;
        }

        var nutrition = await MealPlanMapper.NutritionByFood(
            db, [item!.FoodId], ct);
        if (!nutrition.TryGetValue(item.FoodId, out var originalNutrition))
        {
            // The dish's own food has no nutrition row, so there is nothing
            // to compare a candidate's energy against. A 404 on the item
            // would be wrong — the item exists — and inventing 0 kcal would
            // make every candidate look like a large change.
            log.LogError(
                "Meal plan item {Item} points at food {Food}, which has no "
                + "food_nutrition row.", item.Id, item.FoodId);
            return Fail(500, ErrorCode.InternalError,
                        "Lỗi máy chủ, vui lòng thử lại");
        }

        var originalKcal = originalNutrition.CaloriesKcal
            * item.PortionMultiplier;

        // Dishes already in this plan are excluded: suggesting a dish the
        // user is eating in another meal today would put it on the plate
        // twice, which Step 4 spends its whole `usedIds` bookkeeping
        // avoiding.
        var inPlan = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan!.Id)
            .Select(i => i.FoodId)
            .Distinct()
            .ToListAsync(ct);

        // The whole catalogue, scored. `null` candidates means "score
        // everything you are allowed to" — the F1 filter runs inside the ML
        // service, so what comes back is already safe for this user, and that
        // filter is not reimplemented here.
        var scored = await ml.PredictAsync(
            new MlPredictRequest
            {
                UserId = uid,
                ExcludeFoodIds = inPlan,
                ContextMealType = item.MealType,
            },
            ct);
        if (!scored.Ok)
        {
            return Report(scored.Failure!);
        }

        var scores = scored.Required.Scores
            .GroupBy(s => s.FoodId)
            .ToDictionary(g => g.Key, g => g.First().Score);

        // Same role, and visible to this user. The role is what makes a dish
        // interchangeable: `MEAL_STRUCTURE` in `ml/menu_builder.py` fills a
        // meal by role, so a soup can only be replaced by a soup — otherwise
        // a lunch ends up with two mains and no vegetable.
        // `?? string.Empty` only to satisfy nullability: the row cannot be
        // missing, because `meal_plan_items.food_id` is a foreign key.
        var role = await db.Foods
            .Where(f => f.Id == item.FoodId)
            .Select(f => f.DishRole)
            .FirstOrDefaultAsync(ct) ?? string.Empty;
        var sameRole = await db.Foods
            .Where(f => f.DishRole == role
                        && f.IsActive
                        && f.Id != item.FoodId
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Select(f => f.Id)
            .ToListAsync(ct);

        var ranked = sameRole
            .Where(scores.ContainsKey)
            .OrderByDescending(fid => scores[fid])
            // A second key so that two foods with the same score always come
            // back in the same order; without it the list reshuffles between
            // two identical requests.
            .ThenBy(fid => fid, StringComparer.Ordinal)
            .Take(limit)
            .ToList();

        var cards = await FoodCardReader.ReadAsync(db, ranked, ct);
        var candidateNutrition = await MealPlanMapper.NutritionByFood(
            db, ranked, ct);

        var dayKcal = await MealPlanMapper.EnergyOnPlateAsync(
            db, plan!.Id, ct);
        var target = (decimal)plan.TargetCaloriesKcal;

        var alternatives = new List<AlternativeDto>();
        foreach (var fid in ranked)
        {
            if (!cards.TryGetValue(fid, out var card)
                || !candidateNutrition.TryGetValue(fid, out var n))
            {
                continue;
            }

            // One standard serving of the candidate. Not the original's
            // portion: a user swapping rice for soup is not asking for 400 g
            // of soup, and `food_nutrition.serving_size_g` is what one
            // serving of that dish actually is.
            var candidateKcal = n.CaloriesKcal;
            var afterSwap = dayKcal - originalKcal + candidateKcal;
            var deviation = target <= 0
                ? 0m
                : 100m * (afterSwap - target) / target;

            alternatives.Add(new AlternativeDto
            {
                Food = MealPlanMapper.Brief(fid, cards),
                ServingSizeG = n.ServingSizeG,
                PredictedScore = Math.Round(
                    (decimal)scores[fid], 4, MidpointRounding.AwayFromZero),
                CalorieDeltaKcal = Math.Round(
                    candidateKcal - originalKcal, 2,
                    MidpointRounding.AwayFromZero),
                KeepsWithinTolerance =
                    Math.Abs(deviation) <= MealPlanMapper.ToleranceP,
            });
        }

        var originalCard = await FoodCardReader.ReadAsync(
            db, [item.FoodId], ct);
        originalCard.TryGetValue(item.FoodId, out var original);

        return Ok(new AlternativesResponse
        {
            OriginalItem = new AlternativeOriginalDto
            {
                Id = item.Id,
                FoodName = original?.Name ?? string.Empty,
                CaloriesKcal = Math.Round(
                    originalKcal, 2, MidpointRounding.AwayFromZero),
                DishRole = role,
            },
            Alternatives = alternatives,
        });
    }

    // ── 7.6.5 Replace it ─────────────────────────────────────────────────

    [HttpPut("{id}/replace")]
    public async Task<IActionResult> Replace(
        string id,
        ReplaceItemRequest req,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var (item, plan, problem) = await Locate(id, uid, ct);
        if (problem is not null)
        {
            return problem;
        }

        if (item!.Status == MealItemStatus.Replaced)
        {
            // The row is a record of a swap that already happened. Replacing
            // it again would chain `replaced_by_food_id` through a dish that
            // was never on the plate, and §4.6 reads that column as "what
            // this user chose instead".
            return Invalid(
                "id",
                "Món này đã được thay thế trước đó, hãy thao tác trên món "
                + "đang có trong thực đơn");
        }

        var newFoodId = req.NewFoodId!;
        if (newFoodId == item.FoodId)
        {
            return Invalid("newFoodId",
                           "Món mới trùng với món đang có trong thực đơn");
        }

        var newFood = await db.Foods
            .Where(f => f.Id == newFoodId
                        && f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid))
            .FirstOrDefaultAsync(ct);
        if (newFood is null)
        {
            return Invalid("newFoodId", "Không tìm thấy món ăn này");
        }

        var nutrition = await MealPlanMapper.NutritionByFood(
            db, [newFoodId], ct);
        if (!nutrition.TryGetValue(newFoodId, out var newNutrition))
        {
            log.LogError(
                "Food {Food} has no food_nutrition row, so it cannot be put "
                + "into a meal plan.", newFoodId);
            return Invalid(
                "newFoodId",
                "Món ăn này chưa có dữ liệu dinh dưỡng, chưa dùng được");
        }

        var portion = req.ServingSizeG is { } grams
            ? MealPlanMapper.PortionFromGrams(grams, newNutrition.ServingSizeG)
            : 1.00m;
        if (portion is null)
        {
            return Invalid(
                "servingSizeG",
                $"Khối lượng phải từ {newNutrition.ServingSizeG / 10} đến "
                + $"{newNutrition.ServingSizeG * 5} gam (0,1 đến 5 suất của "
                + "món này)");
        }

        // The F1 safety filter, asked of the one layer that implements it.
        // A single-food candidate set: the answer is either a score, which
        // means this user may eat it, or `NO_SCOREABLE_CANDIDATE`, which
        // means they may not. Checking the condition rules here instead would
        // be a second implementation of the filter that decides whether
        // someone with gout is served offal.
        var checked_ = await ml.PredictAsync(
            new MlPredictRequest
            {
                UserId = uid,
                CandidateFoodIds = [newFoodId],
                ContextMealType = item.MealType,
            },
            ct);
        if (!checked_.Ok)
        {
            if (checked_.Failure!.Kind
                is MlFailureKind.NoScoreableCandidate)
            {
                return Fail(
                    422, ErrorCode.ValidationFailed,
                    "Món này không phù hợp với tình trạng sức khỏe bạn đã "
                    + "khai báo");
            }
            return Report(checked_.Failure!);
        }

        var score = checked_.Required.Scores
            .FirstOrDefault(s => s.FoodId == newFoodId);
        if (score is null)
        {
            // Scored successfully, but this food is not in the answer — it is
            // in `skippedFoodIds`, which is the F1 filter having removed it.
            // The same refusal as above: a `200` whose body omits the food is
            // still the safety layer saying no.
            return Fail(
                422, ErrorCode.ValidationFailed,
                "Món này không phù hợp với tình trạng sức khỏe bạn đã khai "
                + "báo");
        }

        var now = Clock.Now;
        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            item.Status = MealItemStatus.Replaced;
            item.ReplacedByFoodId = newFoodId;
            item.ReplacedAt = now;

            db.MealPlanItems.Add(new MealPlanItems
            {
                Id = Guid.NewGuid().ToString(),
                MealPlanId = plan!.Id,
                FoodId = newFoodId,
                MealType = item.MealType,
                PortionMultiplier = portion.Value,
                PredictedScore = Math.Round(
                    (decimal)score.Score, 4, MidpointRounding.AwayFromZero),
                Status = MealItemStatus.Suggested,
                // NULL, not the old dish's δ. The 70-30 measurement counts
                // servings the SYSTEM drew from the noised vector; this one
                // the user picked by hand, and copying δ across would credit
                // the exploration mechanism with a choice it did not make.
                ExplorationDelta = null,
                Position = item.Position,
                CreatedAt = now,
            });

            await db.SaveChangesAsync(ct);

            // The day's totals change with the dish, which is why §7.6.5
            // answers with the whole plan rather than the new item.
            await MealPlanMapper.RecomputeActualsAsync(db, plan, ct);
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        log.LogInformation(
            "Plan {PlanId}: {Old} replaced by {New} in {Meal}. This is a "
            + "preference signal — label weight 0.6 in §4.6.",
            plan!.Id, item.FoodId, newFoodId, item.MealType);

        // `calorie_deviation_pct` is GENERATED VIRTUAL, so the new value
        // exists only after a reload.
        await db.Entry(plan).ReloadAsync(ct);

        return Ok(await MealPlanMapper.BuildAsync(db, plan, null, ct));
    }

    // ── 7.6.6 Mark what happened to it ───────────────────────────────────

    [HttpPatch("{id}/status")]
    public async Task<IActionResult> UpdateStatus(
        string id,
        UpdateItemStatusRequest req,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var status = req.Status!;
        if (!MealItemStatus.ClientSettable.Contains(status))
        {
            // The attribute on the DTO only checks the value is in the
            // column's ENUM. `suggested` and `replaced` pass that and are
            // still refused here: they are statements about what the system
            // did, and §4.6 computes label weights from them.
            return Invalid(
                "status",
                "Chỉ nhận: "
                + string.Join(" · ", MealItemStatus.ClientSettable));
        }

        var (item, plan, problem) = await Locate(id, uid, ct);
        if (problem is not null)
        {
            return problem;
        }

        if (item!.Status == MealItemStatus.Replaced)
        {
            return Invalid(
                "id",
                "Món này đã được thay thế, hãy cập nhật trạng thái của món "
                + "thay thế nó");
        }

        var created = false;
        string? diaryId = null;

        var now = Clock.Now;
        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            item.Status = status;

            if (status == MealItemStatus.Eaten)
            {
                // §7.6.6: marking a dish eaten writes the diary entry too, so
                // the user does not enter the same meal twice.
                //
                // Matched on the natural key — user, day, meal, food — which
                // is exactly what `idx_compliance` indexes and what the
                // compliance query of §8.4 joins on. `food_diary` has no
                // `meal_plan_item_id` column on purpose (a user eats things
                // that were never in a plan), so this is the only join there
                // is, and a second row would count one meal twice in every
                // compliance figure.
                var already = await db.FoodDiary
                    .FirstOrDefaultAsync(
                        d => d.UserId == uid
                             && d.FoodId == item.FoodId
                             && d.AteOn == plan!.PlanDate
                             && d.MealType == item.MealType,
                        ct);

                if (already is null)
                {
                    var entry = new FoodDiary
                    {
                        Id = Guid.NewGuid().ToString(),
                        UserId = uid,
                        FoodId = item.FoodId,
                        AteOn = plan!.PlanDate,
                        MealType = item.MealType,
                        // The portion the plan suggested. The user can
                        // correct it from the diary screen (§7.7) — guessing
                        // that they ate exactly what was planned is better
                        // than recording nothing, and it is what they tapped.
                        PortionMultiplier = item.PortionMultiplier,
                        CreatedAt = now,
                    };
                    db.FoodDiary.Add(entry);
                    created = true;
                    diaryId = entry.Id;
                }
                else
                {
                    diaryId = already.Id;
                }
            }

            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        log.LogInformation(
            "Plan {PlanId}: item {Item} is now '{Status}'"
            + "{Diary}. Preference signal — §4.6.",
            plan!.Id, item.Id, status,
            created ? ", diary entry created" : string.Empty);

        return Ok(new UpdateItemStatusResponse
        {
            Id = item.Id,
            Status = item.Status,
            DiaryEntryCreated = created,
            DiaryEntryId = diaryId,
        });
    }

    // ── shared ───────────────────────────────────────────────────────────

    /// <summary>
    /// Finds the item and the plan it belongs to, and refuses anything that
    /// is not this user's.
    ///
    /// <para>The <c>403</c>-not-<c>404</c> choice is §7.6.3's and applies
    /// here too: the row exists, it is simply someone else's. The ids are
    /// UUIDs, so confirming existence tells an attacker nothing they could
    /// act on.</para>
    /// </summary>
    private async Task<(MealPlanItems? Item, MealPlans? Plan,
        ObjectResult? Problem)> Locate(
            string id, string uid, CancellationToken ct)
    {
        var item = await db.MealPlanItems
            .FirstOrDefaultAsync(i => i.Id == id, ct);
        if (item is null)
        {
            return (null, null,
                    Fail(404, ErrorCode.NotFound,
                         "Không tìm thấy món trong thực đơn"));
        }

        var plan = await db.MealPlans
            .FirstOrDefaultAsync(p => p.Id == item.MealPlanId, ct);
        if (plan is null)
        {
            // Unreachable while the foreign key is in place; reported rather
            // than dereferenced, because the alternative is a
            // NullReferenceException that says nothing about which row is
            // orphaned.
            log.LogError(
                "Meal plan item {Item} references plan {Plan}, which does "
                + "not exist.", item.Id, item.MealPlanId);
            return (null, null,
                    Fail(500, ErrorCode.InternalError,
                         "Lỗi máy chủ, vui lòng thử lại"));
        }

        if (plan.UserId != uid)
        {
            return (null, null,
                    Fail(403, ErrorCode.Forbidden,
                         "Món này không thuộc thực đơn của bạn"));
        }

        return (item, plan, null);
    }

    private ObjectResult Report(MlFailure failure)
    {
        if (failure.IsSystemFault())
        {
            log.LogError("Meal plan item: {Detail}", failure.Detail);
        }
        else
        {
            log.LogInformation("Meal plan item: {Detail}", failure.Detail);
        }
        return failure.ToActionResult(HttpContext.TraceIdentifier);
    }
}
