using Api.Catalogue;
using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Nutrition;
using Api.Planning;
using Api.Profile;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Diary;

/// <summary>
/// What the user actually ate — specification §7.7.
///
/// <para>The plan and the diary are two different statements. The plan is
/// what the system suggested; the diary is what happened. Nothing a user does
/// here is filtered by F1 (§7.7.2 says so explicitly): a diary that refuses
/// to record an unsuitable dish is a diary that lies, and it would lose the
/// 0.9-weight label that is the second strongest signal the model gets.</para>
///
/// <para><b>Two kinds of delete.</b> A line the user got to by tapping "eaten"
/// on a planned dish is undone — the line goes and the dish returns to the
/// plan as <c>suggested</c>. A line the user typed in themselves is deleted.
/// Which one applies is read off <c>fromMealPlan</c>, the natural-key join
/// §8.4 already uses, so no new column is needed. The principle the two share
/// is that <b>only something that never happened can be removed</b>: a
/// mistaken tap and a mistyped snack, never a meal that was eaten.</para>
///
/// <para><b>And a lock.</b> Once the user has rated a food, the line that
/// could be the evidence for that rating can no longer be edited or deleted —
/// §7.8.1's two-part rule requires a diary entry to exist, and "I did not eat
/// this" cannot be true at the same time as "it was worth five stars". See
/// <see cref="LockedBy"/> for why the rule is written against timestamps
/// rather than as a plain "has been rated".</para>
/// </summary>
[ApiController]
[Route("api/v1/food-diary")]
[Authorize]
public sealed class FoodDiaryController(
    AppDbContext db,
    ILogger<FoodDiaryController> log) : ControllerBase
{
    /// <summary>§7.7.1's ceiling on the range.</summary>
    public const int MaxRangeDays = 90;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    /// <summary>
    /// A request that is well formed and refused by the state of the row —
    /// the locked line of <see cref="LockedBy"/>, and a second entry for a
    /// meal that already has one.
    ///
    /// <para><c>409</c> with <c>VALIDATION_FAILED</c> and the field named,
    /// which is the shape §2.5 allows <c>details</c> on. §4's catalogue has
    /// no code of its own for either case, and this follows what
    /// <c>POST /meal-plans/{id}/meals/{mealType}</c> already does rather
    /// than inventing a second convention for the same situation.</para>
    /// </summary>
    private ObjectResult Conflict(string field, string message, string why)
        => ApiProblem.Make(
            409, ErrorCode.ValidationFailed, why,
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.7.1 Read the diary ─────────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> List(
        [FromQuery] DateOnly? from,
        [FromQuery] DateOnly? to,
        [FromQuery] string? mealType,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        if (from is not { } start)
        {
            return Invalid("from", "Thiếu ngày bắt đầu");
        }
        if (to is not { } end)
        {
            return Invalid("to", "Thiếu ngày kết thúc");
        }
        if (end < start)
        {
            return Invalid(
                "to", "Ngày kết thúc phải từ ngày bắt đầu trở đi");
        }
        if (end.DayNumber - start.DayNumber > MaxRangeDays)
        {
            return Invalid(
                "to", $"Khoảng xem tối đa {MaxRangeDays} ngày");
        }
        if (mealType is not null && !Enums.MealType.Contains(mealType))
        {
            return Invalid(
                "mealType",
                "Bữa không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.MealType));
        }

        var q = db.FoodDiary.Where(
            d => d.UserId == uid && d.AteOn >= start && d.AteOn <= end);
        if (mealType is not null)
        {
            q = q.Where(d => d.MealType == mealType);
        }

        // `Id` last so the order is total: two entries written in the same
        // second would otherwise come back in whatever order the database
        // felt like, and a list that reshuffles between two identical
        // requests is the kind of thing that looks like a data bug.
        var rows = await q
            .OrderBy(d => d.AteOn)
            .ThenBy(d => d.CreatedAt)
            .ThenBy(d => d.Id)
            .ToListAsync(ct);

        var view = await ViewAsync(uid, rows, start, end, ct);

        var days = rows
            .GroupBy(r => r.AteOn)
            .OrderBy(g => g.Key)
            .Select(g => new DiaryDayDto
            {
                Date = g.Key,
                TotalCaloriesKcal = Round2(
                    g.Sum(r => view.Calories(r) ?? 0m)),
                Entries = g.Select(view.Entry).ToList(),
            })
            .ToList();

        return Ok(new FoodDiaryResponse
        {
            From = start,
            To = end,
            Days = days,
        });
    }

    // ── 7.7.2 Record something eaten ─────────────────────────────────────

    [HttpPost]
    public async Task<IActionResult> Create(
        CreateDiaryEntryRequest req,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var ateOn = req.AteOn!.Value;
        if (ateOn > Clock.Today)
        {
            // One clock, Asia/Ho_Chi_Minh — `Clock.Today`, not
            // `DateTime.UtcNow`, which between midnight and 07:00 would call
            // the user's own evening a future date and refuse it.
            return Invalid("ateOn", "Không ghi nhật ký cho ngày chưa tới");
        }

        var foodId = req.FoodId!;
        var mealType = req.MealType!;

        var nutrition = await db.FoodNutrition
            .FirstOrDefaultAsync(n => n.FoodId == foodId, ct);
        if (nutrition is null)
        {
            // Either the food does not exist, or it exists with no
            // composition row. Both are `404` and the message says which,
            // because the second is a hole in the catalogue and a user who
            // reports it precisely is doing the project a favour.
            var exists = await db.Foods.AnyAsync(f => f.Id == foodId, ct);
            return Fail(
                404, ErrorCode.NotFound,
                exists
                    ? "Món này chưa có số liệu dinh dưỡng nên chưa ghi được "
                      + "vào nhật ký"
                    : "Không tìm thấy món ăn");
        }

        var portion = Portion(req.ServingSizeG, nutrition);
        if (portion is null)
        {
            return Invalid("servingSizeG", GramRange(nutrition));
        }

        // One line per (day, meal, food). §8.4 counts a planned dish as
        // eaten by joining on exactly those four columns, so a second row
        // would count one meal twice in the compliance figure — the same
        // reason §7.6.6 looks for an existing entry before writing one.
        // Eating two servings is a portion, not a second line.
        var already = await db.FoodDiary.AnyAsync(
            d => d.UserId == uid
                 && d.FoodId == foodId
                 && d.AteOn == ateOn
                 && d.MealType == mealType,
            ct);
        if (already)
        {
            return Conflict(
                "foodId",
                "Hãy sửa khẩu phần của dòng đã có thay vì thêm dòng mới",
                "Món này đã có trong nhật ký của bữa đó");
        }

        var entry = new FoodDiary
        {
            Id = Guid.NewGuid().ToString(),
            UserId = uid,
            FoodId = foodId,
            AteOn = ateOn,
            MealType = mealType,
            PortionMultiplier = portion.Value,
            CreatedAt = Clock.Now,
        };
        db.FoodDiary.Add(entry);
        await db.SaveChangesAsync(ct);

        log.LogInformation(
            "Diary {Entry}: {Food} eaten at {Meal} on {Day}. Preference "
            + "signal — label weight 0.9 in §4.6.",
            entry.Id, foodId, mealType, ateOn);

        var view = await ViewAsync(uid, [entry], ateOn, ateOn, ct);
        return StatusCode(
            StatusCodes.Status201Created, view.Entry(entry));
    }

    // ── 7.7.3 Correct a line ─────────────────────────────────────────────

    [HttpPut("{id}")]
    public async Task<IActionResult> Update(
        string id,
        UpdateDiaryEntryRequest req,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var (entry, problem) = await LocateAsync(id, uid, ct);
        if (problem is not null)
        {
            return problem;
        }

        if (await LockedBy(uid, entry!, ct) is { } rated)
        {
            return Locked(rated);
        }

        // `foodId` and `ateOn` may be echoed back, and must match. Changing
        // the food in place would carry an existing rating over to a dish
        // the user never rated; changing the day would move the eating to a
        // day whose plan and whose energy limits are different ones.
        if (req.FoodId is { Length: > 0 } food && food != entry!.FoodId)
        {
            return Invalid(
                "foodId",
                "Không đổi được món của một dòng nhật ký, hãy xóa dòng này "
                + "và ghi lại món đúng");
        }
        if (req.AteOn is { } day && day != entry!.AteOn)
        {
            return Invalid(
                "ateOn",
                "Không đổi được ngày của một dòng nhật ký, hãy xóa dòng này "
                + "và ghi lại vào ngày đúng");
        }

        var mealType = req.MealType ?? entry!.MealType;

        if (req.ServingSizeG is { } grams)
        {
            var nutrition = await db.FoodNutrition
                .FirstOrDefaultAsync(n => n.FoodId == entry!.FoodId, ct);
            if (nutrition is null)
            {
                return Fail(
                    404, ErrorCode.NotFound,
                    "Món này chưa có số liệu dinh dưỡng nên không đổi được "
                    + "khẩu phần");
            }
            var portion = Portion(grams, nutrition);
            if (portion is null)
            {
                return Invalid("servingSizeG", GramRange(nutrition));
            }
            entry!.PortionMultiplier = portion.Value;
        }

        if (mealType != entry!.MealType)
        {
            var clash = await db.FoodDiary.AnyAsync(
                d => d.UserId == uid
                     && d.FoodId == entry.FoodId
                     && d.AteOn == entry.AteOn
                     && d.MealType == mealType
                     && d.Id != entry.Id,
                ct);
            if (clash)
            {
                return Conflict(
                    "mealType",
                    "Bữa đó đã có món này trong nhật ký",
                    "Món này đã có trong nhật ký của bữa đó");
            }
            entry.MealType = mealType;
        }

        await db.SaveChangesAsync(ct);

        var view = await ViewAsync(uid, [entry], entry.AteOn, entry.AteOn, ct);
        return Ok(view.Entry(entry));
    }

    // ── 7.7.4 Take a line back ───────────────────────────────────────────

    /// <summary>
    /// Undoes a mistaken "eaten", or deletes a line the user typed in.
    ///
    /// <para>Which one it is depends on whether the dish was in the plan for
    /// that day and meal. If it was, the line was created by §7.6.6 when the
    /// user tapped "eaten", so taking it back means <b>handing the dish back
    /// to the plan</b>: the <c>meal_plan_items</c> row goes from
    /// <c>eaten</c> to <c>suggested</c> and reappears on the plan screen. If
    /// it was not, there is nothing to hand back and the line simply
    /// goes.</para>
    ///
    /// <para><c>204</c> in both cases, as §7.7.4 specifies. The app knows
    /// which of the two it asked for before it asks, from
    /// <c>fromMealPlan</c>.</para>
    /// </summary>
    [HttpDelete("{id}")]
    public async Task<IActionResult> Delete(
        string id,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var (entry, problem) = await LocateAsync(id, uid, ct);
        if (problem is not null)
        {
            return problem;
        }

        if (await LockedBy(uid, entry!, ct) is { } rated)
        {
            return Locked(rated);
        }

        // Only the dishes marked `eaten` go back to `suggested`. A dish the
        // user had also marked `kept` or `skipped` is a separate statement
        // about the plan, and this request says nothing about it.
        var planned = await db.MealPlanItems
            .Join(db.MealPlans, i => i.MealPlanId, p => p.Id,
                  (i, p) => new { Item = i, Plan = p })
            .Where(x => x.Plan.UserId == uid
                        && x.Plan.PlanDate == entry!.AteOn
                        && x.Item.MealType == entry.MealType
                        && x.Item.FoodId == entry.FoodId
                        && x.Item.Status == MealItemStatus.Eaten)
            .Select(x => x.Item)
            .ToListAsync(ct);

        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            foreach (var item in planned)
            {
                item.Status = MealItemStatus.Suggested;
            }
            db.FoodDiary.Remove(entry!);
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        log.LogInformation(
            "Diary {Entry} removed. {Returned}",
            entry!.Id,
            planned.Count > 0
                ? $"{planned.Count} planned dish(es) returned to 'suggested'"
                : "It was not in the plan, so nothing was returned.");

        return NoContent();
    }

    // ── 7.7.5 The day against its limits ─────────────────────────────────

    [HttpGet("summary")]
    public async Task<IActionResult> Summary(
        [FromQuery] DateOnly? date,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        if (date is not { } day)
        {
            return Invalid("date", "Thiếu ngày cần tổng kết");
        }

        var profile = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid, ct);
        if (profile is null)
        {
            return Fail(409, ErrorCode.ProfileRequired,
                        "Chưa khai báo hồ sơ sức khỏe");
        }

        var plan = await db.MealPlans.FirstOrDefaultAsync(
            p => p.UserId == uid && p.PlanDate == day, ct);

        // The limits are READ, not recomputed. A plan for the day carries
        // the snapshot taken when it was generated, which is what actually
        // applied; without one, the three stored `health_profiles` columns
        // are the user's current limits. Recomputing from height and weight
        // would answer a past day with today's body.
        MacrosDto targets;
        if (plan is not null)
        {
            targets = new MacrosDto
            {
                CaloriesKcal = plan.TargetCaloriesKcal,
                ProteinG = plan.TargetProteinG,
                CarbsG = plan.TargetCarbsG,
                FatG = plan.TargetFatG,
            };
        }
        else if (profile.DailyCaloriesTarget is { } stored)
        {
            // Only the grams are derived, from the stored percentages and
            // the Atwater factors that `NutritionTargets` already holds —
            // the schema keeps the split as three percentages and no gram
            // column exists to read.
            targets = new MacrosDto
            {
                CaloriesKcal = stored,
                ProteinG = NutritionTargets.Grams(
                    stored, profile.TargetProteinPct,
                    NutritionTargets.KcalPerGramProtein),
                CarbsG = NutritionTargets.Grams(
                    stored, profile.TargetCarbsPct,
                    NutritionTargets.KcalPerGramCarbs),
                FatG = NutritionTargets.Grams(
                    stored, profile.TargetFatPct,
                    NutritionTargets.KcalPerGramFat),
            };
        }
        else
        {
            // The profile exists but Step 1 has never run for it, so there
            // is no limit to measure the day against. Same code as a missing
            // profile: §4 sends the user to the same screen.
            return Fail(409, ErrorCode.ProfileRequired,
                        "Hồ sơ sức khỏe chưa có hạn mức năng lượng");
        }

        var rows = await db.FoodDiary
            .Where(d => d.UserId == uid && d.AteOn == day)
            .ToListAsync(ct);

        var nutrition = await MealPlanMapper.NutritionByFood(
            db, rows.Select(r => r.FoodId).ToList(), ct);

        decimal Eaten(string nutrient)
            => rows.Sum(r =>
                nutrition.TryGetValue(r.FoodId, out var n)
                    ? (NutrientAmounts.Of(nutrient, n) ?? 0m)
                      * r.PortionMultiplier
                    : 0m);

        var consumed = new MacrosDto
        {
            CaloriesKcal = Round2(Eaten("calories_kcal")),
            ProteinG = Round2(Eaten("protein_g")),
            CarbsG = Round2(Eaten("carbs_g")),
            FatG = Round2(Eaten("fat_g")),
        };

        var byMeal = Enums.MealType
            .Select(meal => new MealEnergyDto
            {
                MealType = meal,
                CaloriesKcal = Round2(rows
                    .Where(r => r.MealType == meal)
                    .Sum(r => nutrition.TryGetValue(r.FoodId, out var n)
                        ? n.CaloriesKcal * r.PortionMultiplier
                        : 0m)),
                TargetCaloriesKcal = (int)Math.Round(
                    targets.CaloriesKcal * NutritionTargets.MealShare[meal],
                    MidpointRounding.AwayFromZero),
            })
            .ToList();

        return Ok(new DiarySummaryResponse
        {
            Date = day,
            Targets = targets,
            Consumed = consumed,
            Remaining = new MacrosDto
            {
                CaloriesKcal = Round2(
                    targets.CaloriesKcal - consumed.CaloriesKcal),
                ProteinG = Round2(targets.ProteinG - consumed.ProteinG),
                CarbsG = Round2(targets.CarbsG - consumed.CarbsG),
                FatG = Round2(targets.FatG - consumed.FatG),
            },
            ProgressPct = new ProgressPctDto
            {
                Calories = Pct(consumed.CaloriesKcal, targets.CaloriesKcal),
                Protein = Pct(consumed.ProteinG, targets.ProteinG),
                Carbs = Pct(consumed.CarbsG, targets.CarbsG),
                Fat = Pct(consumed.FatG, targets.FatG),
            },
            ByMeal = byMeal,
            Micronutrients = await MicronutrientsAsync(
                profile, day, rows, nutrition, ct),
            PlanCompliance = await ComplianceAsync(uid, day, plan, ct),
        });
    }

    /// <summary>
    /// Every nutrient with a recommended intake for this user, other than
    /// the four already in <c>targets</c>.
    ///
    /// <para>The list is driven by <c>rda_reference</c> rather than by a
    /// hard-coded set of micronutrients, so loading more of the source
    /// document widens this screen without a code change.</para>
    ///
    /// <para><b>Rows with a <c>qualifier</c> are skipped.</b> The source
    /// gives iron three values by dietary bioavailability and zinc three by
    /// absorption level — two different axes, which is why the schema keeps
    /// the label verbatim instead of ranking them. Picking one here would
    /// invent a conversion the document does not make, so a nutrient that
    /// only has qualified rows is left out rather than guessed at.</para>
    /// </summary>
    private async Task<List<MicronutrientDto>> MicronutrientsAsync(
        HealthProfiles profile,
        DateOnly day,
        List<FoodDiary> rows,
        Dictionary<string, FoodNutrition> nutrition,
        CancellationToken ct)
    {
        // The age the user was on the day being summarised, not today: a
        // summary of last year's diary belongs to last year's age band.
        var age = NutritionTargets.Age(profile.DateOfBirth, day);

        var reference = await db.RdaReference
            .Where(r => r.Qualifier == null
                        && (r.Gender == profile.Gender || r.Gender == "all")
                        && r.AgeMin <= age && age <= r.AgeMax)
            .ToListAsync(ct);

        var result = new List<MicronutrientDto>();
        foreach (var group in reference.GroupBy(r => r.Nutrient))
        {
            var nutrient = group.Key;
            if (NutrientAmounts.IsMacro(nutrient)
                || !NutrientAmounts.Vocabulary.ContainsKey(nutrient))
            {
                continue;
            }

            // A sex-specific row wins over an `all` row covering the same
            // age, which is how the source states the figures that differ
            // between men and women.
            var rda = group
                .OrderBy(r => r.Gender == "all" ? 1 : 0)
                .ThenBy(r => r.AgeMax - r.AgeMin)
                .First();

            var consumed = rows.Sum(r =>
                nutrition.TryGetValue(r.FoodId, out var n)
                    ? (NutrientAmounts.Of(nutrient, n) ?? 0m)
                      * r.PortionMultiplier
                    : 0m);

            result.Add(new MicronutrientDto
            {
                Nutrient = nutrient,
                NameVi = NutrientLabels.Name(nutrient),
                Consumed = Round2(consumed),
                Rda = rda.RdaValue,
                Pct = Pct(consumed, rda.RdaValue),
                Unit = rda.Unit,
            });
        }

        return result
            .OrderBy(m => m.Nutrient, StringComparer.Ordinal)
            .ToList();
    }

    /// <summary>
    /// §8.4's compliance figure, narrowed to one day: of the dishes the plan
    /// suggested, how many have a diary line on the natural key.
    /// </summary>
    private async Task<PlanComplianceDto> ComplianceAsync(
        string uid, DateOnly day, MealPlans? plan, CancellationToken ct)
    {
        if (plan is null)
        {
            return new PlanComplianceDto
            {
                SuggestedItems = 0,
                EatenItems = 0,
                CompliancePct = null,
            };
        }

        var items = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan.Id)
            .Select(i => new { i.MealType, i.FoodId })
            .ToListAsync(ct);

        var eatenKeys = await db.FoodDiary
            .Where(d => d.UserId == uid && d.AteOn == day)
            .Select(d => new { d.MealType, d.FoodId })
            .ToListAsync(ct);

        var eaten = eatenKeys
            .Select(k => (k.MealType, k.FoodId))
            .ToHashSet();

        var hit = items.Count(i => eaten.Contains((i.MealType, i.FoodId)));

        return new PlanComplianceDto
        {
            SuggestedItems = items.Count,
            EatenItems = hit,
            CompliancePct = items.Count == 0
                ? null
                : Round2(100m * hit / items.Count),
        };
    }

    // ── shared ───────────────────────────────────────────────────────────

    /// <summary>
    /// Finds the line and refuses anything that is not this user's.
    ///
    /// <para><c>403</c> rather than <c>404</c> for someone else's line, which
    /// is §7.6.3's choice and what §7.7.3 and §7.7.4 list. The id is a UUID,
    /// so confirming that it exists tells an attacker nothing they could
    /// act on.</para>
    /// </summary>
    private async Task<(FoodDiary? Entry, ObjectResult? Problem)> LocateAsync(
        string id, string uid, CancellationToken ct)
    {
        var entry = await db.FoodDiary.FirstOrDefaultAsync(
            d => d.Id == id, ct);
        if (entry is null)
        {
            return (null, Fail(404, ErrorCode.NotFound,
                               "Không tìm thấy dòng nhật ký"));
        }
        if (entry.UserId != uid)
        {
            return (null, Fail(403, ErrorCode.Forbidden,
                               "Dòng nhật ký này không thuộc tài khoản của "
                               + "bạn"));
        }
        return (entry, null);
    }

    /// <summary>
    /// The rating that locks this line, or <c>null</c> if it is still free.
    ///
    /// <para>The test is <b>not</b> "has this food been rated". It is
    /// "has it been rated at or after this line was written", and the
    /// difference matters: someone who rated a dish last week, eats it again
    /// today and taps "eaten" by mistake must still be able to undo today's
    /// tap. Last week's rating rests on last week's line, which stays
    /// locked.</para>
    ///
    /// <para>That also keeps §7.8.1's second condition true forever. A
    /// rating could only be written while a diary line for the food already
    /// existed, and every line older than the rating is locked by it — so no
    /// sequence of deletes can leave a rating with nothing behind it.</para>
    /// </summary>
    private async Task<DateTime?> LockedBy(
        string uid, FoodDiary entry, CancellationToken ct)
    {
        var at = await db.Feedbacks
            .Where(f => f.UserId == uid
                        && f.FoodId == entry.FoodId
                        && f.CreatedAt >= entry.CreatedAt)
            .OrderBy(f => f.CreatedAt)
            .Select(f => (DateTime?)f.CreatedAt)
            .FirstOrDefaultAsync(ct);
        return at;
    }

    private ObjectResult Locked(DateTime rated)
        => Conflict(
            "id",
            "Hãy xóa đánh giá trước nếu muốn sửa hoặc bỏ dòng nhật ký này",
            $"Bạn đã đánh giá món này lúc {rated:HH:mm 'ngày' dd/MM/yyyy}, "
            + "nên dòng nhật ký được giữ lại");

    /// <summary>
    /// The portion as a multiple of the food's standard serving, or
    /// <c>null</c> when the grams asked for fall outside
    /// <c>chk_diary_portion</c>. Omitting the grams means one serving.
    /// </summary>
    private static decimal? Portion(int? grams, FoodNutrition nutrition)
        => grams is { } g
            ? MealPlanMapper.PortionFromGrams(g, nutrition.ServingSizeG)
            : 1.00m;

    private static string GramRange(FoodNutrition nutrition)
        => $"Khối lượng phải từ {nutrition.ServingSizeG / 10} đến "
            + $"{nutrition.ServingSizeG * 5} gam (0,1 đến 5 suất của món "
            + "này)";

    private static decimal Round2(decimal value)
        => Math.Round(value, 2, MidpointRounding.AwayFromZero);

    private static decimal Pct(decimal part, decimal whole)
        => whole <= 0m
            ? 0m
            : Math.Round(100m * part / whole, 1, MidpointRounding.AwayFromZero);

    /// <summary>
    /// Everything the entries of a response need that is not on the row
    /// itself: the food card, the energy, whether the dish was planned, and
    /// whether a rating has locked the line.
    ///
    /// <para>Gathered once per request rather than per entry — a 90-day range
    /// is a few hundred lines, and four queries beat four hundred.</para>
    /// </summary>
    private async Task<DiaryView> ViewAsync(
        string uid,
        IReadOnlyCollection<FoodDiary> rows,
        DateOnly from,
        DateOnly to,
        CancellationToken ct)
    {
        var foodIds = rows.Select(r => r.FoodId).Distinct().ToList();

        var cards = await FoodCardReader.ReadAsync(db, foodIds, ct);
        var nutrition = await MealPlanMapper.NutritionByFood(
            db, foodIds, ct);

        var plannedRows = await db.MealPlanItems
            .Join(db.MealPlans, i => i.MealPlanId, p => p.Id,
                  (i, p) => new { Item = i, Plan = p })
            .Where(x => x.Plan.UserId == uid
                        && x.Plan.PlanDate >= from
                        && x.Plan.PlanDate <= to)
            .Select(x => new
            {
                x.Plan.PlanDate,
                x.Item.MealType,
                x.Item.FoodId,
            })
            .Distinct()
            .ToListAsync(ct);

        var planned = plannedRows
            .Select(x => (x.PlanDate, x.MealType, x.FoodId))
            .ToHashSet();

        // The latest rating per food, which answers both questions: whether
        // the food has ever been rated, and whether a rating is at or after
        // a given line — see `LockedBy` for why the comparison is on time.
        var ratedRows = await db.Feedbacks
            .Where(f => f.UserId == uid && foodIds.Contains(f.FoodId))
            .GroupBy(f => f.FoodId)
            .Select(g => new { FoodId = g.Key, Latest = g.Max(f => f.CreatedAt) })
            .ToListAsync(ct);

        var rated = ratedRows.ToDictionary(x => x.FoodId, x => x.Latest);

        return new DiaryView(cards, nutrition, planned, rated);
    }

    private sealed class DiaryView(
        Dictionary<string, FoodCard> cards,
        Dictionary<string, FoodNutrition> nutrition,
        HashSet<(DateOnly, string, string)> planned,
        Dictionary<string, DateTime> rated)
    {
        public decimal? Calories(FoodDiary row)
            => nutrition.TryGetValue(row.FoodId, out var n)
                ? n.CaloriesKcal * row.PortionMultiplier
                : null;

        public DiaryEntryDto Entry(FoodDiary row)
        {
            var serving = nutrition.TryGetValue(row.FoodId, out var n)
                ? (int)Math.Round(
                    n.ServingSizeG * row.PortionMultiplier,
                    MidpointRounding.AwayFromZero)
                : 0;

            var hasRating = rated.TryGetValue(row.FoodId, out var latest);

            return new DiaryEntryDto
            {
                Id = row.Id,
                Food = MealPlanMapper.Brief(row.FoodId, cards),
                MealType = row.MealType,
                ServingSizeG = serving,
                ActualCaloriesKcal = Round2(Calories(row) ?? 0m),
                FromMealPlan = planned.Contains(
                    (row.AteOn, row.MealType, row.FoodId)),
                HasFeedback = hasRating,
                Editable = !(hasRating && latest >= row.CreatedAt),
                CreatedAt = row.CreatedAt,
            };
        }
    }
}
