using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Planning;
using Api.Profile;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Catalogue;

/// <summary>
/// Browsing and looking up foods — specification §7.5.1 and §7.5.2.
///
/// <para>Wave 3 of §10.2, built after waves 4 and 5. It is what the food
/// diary needs: "thêm món đã ăn" has to find a dish before it can record
/// one.</para>
///
/// <para><b>Safety comes from the ML service, always.</b> Both endpoints ask
/// <c>POST /foods/safety</c> which dishes this user may eat and why not.
/// That call is cheap — nothing is scored and no model is loaded — and it
/// keeps the F1 filter in the one place that implements it.
/// <c>cross_check_f1</c> exists because even the two SQL queries inside that
/// service can drift; a third version in C# would be the one nothing
/// compares.</para>
///
/// <para><b>When the ML service is unreachable, neither endpoint answers.</b>
/// A browse list that cannot say which dish is unsafe is worse than no list:
/// with <c>excludeUnsafe=true</c> it would be a list claiming to be filtered
/// when it is not, and with <c>false</c> every <c>isSafeForUser</c> would be
/// a guess. So both return <c>503 ML_UNAVAILABLE</c>, the same screen the
/// meal plan shows.</para>
///
/// <para>Note on language: <c>message</c> strings are Vietnamese — §2.5's
/// <c>error.message</c>, and §7.5.2's warnings, which users read.</para>
/// </summary>
[ApiController]
[Route("api/v1/foods")]
[Authorize]
public sealed class FoodController(
    AppDbContext db,
    IMlClient ml,
    ILogger<FoodController> log) : ControllerBase
{
    public const int DefaultPageSize = 20;
    public const int MaxPageSize = 100;

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    /// <summary>
    /// The foods this user may <b>eat</b>, out of a safety answer.
    ///
    /// <para>Not simply <c>SafeFoodIds</c>. Since the F1 filter also subtracts
    /// the dishes the user asked not to be suggested, a dish whose only
    /// reason is <c>userChoice</c> comes back "unsafe" while being perfectly
    /// safe to eat. These two endpoints are about health — one hides dishes,
    /// the other prints a warning — so they have to look past that reason, or
    /// blocking a dish would delete it from search and the screen that
    /// unblocks it is the one it disappeared from.</para>
    /// </summary>
    private static HashSet<string> EdibleIds(MlFoodSafetyResponse answer)
    {
        var ids = answer.SafeFoodIds.ToHashSet();
        foreach (var entry in answer.Unsafe)
        {
            if (entry.Reasons.Count > 0 && entry.Reasons.All(r => r.UserChoice))
            {
                ids.Add(entry.FoodId);
            }
        }
        return ids;
    }

    // ── 7.5.1 Search and browse ──────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> Search(
        [FromQuery] string? q,
        [FromQuery] string? categoryId,
        [FromQuery] string? mealType,
        [FromQuery] string? dishRole,
        [FromQuery] decimal? maxCalories,
        [FromQuery] string? mark = null,
        [FromQuery] bool excludeUnsafe = true,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = DefaultPageSize,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        if (page < 1)
        {
            return Invalid("page", "Trang phải từ 1 trở lên");
        }
        if (pageSize is < 1 or > MaxPageSize)
        {
            return Invalid(
                "pageSize", $"Số món mỗi trang phải từ 1 đến {MaxPageSize}");
        }
        if (mealType is not null && !Enums.MealType.Contains(mealType))
        {
            return Invalid(
                "mealType",
                "Bữa không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.MealType));
        }
        if (dishRole is not null && !Enums.DishRole.Contains(dishRole))
        {
            return Invalid(
                "dishRole",
                "Vai trò món không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.DishRole));
        }
        if (maxCalories is <= 0)
        {
            return Invalid("maxCalories", "Trần năng lượng phải lớn hơn 0");
        }
        if (mark is not null && !Enums.MarkKind.Contains(mark))
        {
            return Invalid(
                "mark",
                "Dấu món không hợp lệ, phải là một trong: "
                + string.Join(" · ", Enums.MarkKind));
        }

        var safety = await ml.FoodSafetyAsync(
            new MlFoodSafetyRequest { UserId = uid }, ct);
        if (safety.Failure is { } failure)
        {
            return Report(failure);
        }
        var safeIds = EdibleIds(safety.Required);

        var rows = db.Foods
            .Where(f => f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid));

        if (!string.IsNullOrWhiteSpace(q))
        {
            // `Contains` becomes `LIKE '%…%'`. Whether it matches across
            // diacritics is the column's collation's business, not this
            // layer's: `utf8mb4_unicode_ci` treats "pho" and "phở" as equal,
            // which is what a user typing without tone marks expects.
            var needle = q.Trim();
            rows = rows.Where(f => f.Name.Contains(needle));
        }
        if (!string.IsNullOrWhiteSpace(categoryId))
        {
            rows = rows.Where(f => f.CategoryId == categoryId);
        }
        if (dishRole is not null)
        {
            rows = rows.Where(f => f.DishRole == dishRole);
        }
        if (mealType is not null)
        {
            // The roles that meal can hold, from `Api.Planning.MealStructure`
            // — a mirror of the ML service's `MEAL_STRUCTURE` that section 15
            // of tools/check_step4.py compares against it.
            // `.ToList()` is not decoration. With a `string[]`, overload
            // resolution inside the query picks
            // `MemoryExtensions.Contains(ReadOnlySpan<T>, T)` instead of
            // `Enumerable.Contains`, and EF Core throws while translating —
            // a TypeLoadException about ReadOnlySpan, which says nothing
            // about meals. A List has only the LINQ overload.
            var roles = MealStructure.For(mealType).ToList();
            rows = rows.Where(f => roles.Contains(f.DishRole));
        }
        if (mark is not null)
        {
            // `EXISTS`, not a join: a food has at most one mark, and a join
            // would still have to be left-outer for the unfiltered case, so
            // the two shapes would differ for no gain.
            rows = rows.Where(f => db.UserFoodMarks.Any(
                m => m.UserId == uid && m.FoodId == f.Id && m.Kind == mark));
        }
        if (excludeUnsafe)
        {
            rows = rows.Where(f => safeIds.Contains(f.Id));
        }

        var joined = rows
            .Join(db.FoodNutrition, f => f.Id, n => n.FoodId,
                  (f, n) => new { Food = f, Nutrition = n })
            .Join(db.FoodCategories, x => x.Food.CategoryId, c => c.Id,
                  (x, c) => new
                  {
                      x.Food.Id,
                      x.Food.Name,
                      x.Food.ImageUrl,
                      CategoryName = c.Name,
                      x.Food.DishRole,
                      x.Food.SpiceLevel,
                      x.Nutrition.CaloriesKcal,
                      x.Nutrition.ServingSizeG,
                  });

        if (maxCalories is { } cap)
        {
            joined = joined.Where(x => x.CaloriesKcal <= cap);
        }

        var total = await joined.CountAsync(ct);

        var items = await joined
            // By name, then by id: without the second key two foods with the
            // same name could swap places between page 1 and page 2, and one
            // of them would never be seen.
            .OrderBy(x => x.Name)
            .ThenBy(x => x.Id)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(x => new FoodListItemDto
            {
                Id = x.Id,
                Name = x.Name,
                ImageUrl = x.ImageUrl,
                CategoryName = x.CategoryName,
                DishRole = x.DishRole,
                SpiceLevel = x.SpiceLevel,
                CaloriesKcal = x.CaloriesKcal,
                ServingSizeG = x.ServingSizeG,
                IsSafeForUser = safeIds.Contains(x.Id),
                // A correlated subquery rather than a second round trip: at
                // most 100 rows come back, and the mark has to arrive with
                // the row or the bookmark draws itself empty for a moment on
                // a list the user has already saved from.
                Mark = db.UserFoodMarks
                    .Where(m => m.UserId == uid && m.FoodId == x.Id)
                    .Select(m => m.Kind)
                    .FirstOrDefault(),
            })
            .ToListAsync(ct);

        return Ok(new FoodPageResponse
        {
            Items = items,
            Page = page,
            PageSize = pageSize,
            TotalItems = total,
            // Ceiling division, and 0 pages for 0 items rather than 1: an
            // empty result has no page to ask for.
            TotalPages = total == 0 ? 0 : (total + pageSize - 1) / pageSize,
        });
    }

    // ── 7.5.2 One food in full ───────────────────────────────────────────

    [HttpGet("{id}")]
    public async Task<IActionResult> Detail(
        string id, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var (body, problem) = await DetailAsync(id, uid, safetyRequired: true, ct);
        return problem ?? Ok(body);
    }

    /// <summary>
    /// §7.5.2's body for one food this user can see.
    /// </summary>
    /// <param name="safetyRequired">
    /// <c>false</c> only for §7.5.3, which has already written the dish when
    /// it gets here: answering <c>503</c> then would send the app to retry a
    /// create that succeeded, and the retry would be a
    /// <c>409 FOOD_ALREADY_EXISTS</c>. So the dish comes back with
    /// <c>isSafeForUser: false</c> and no warnings — the cautious reading —
    /// and the detail screen asks again when it opens.
    /// </param>
    private async Task<(FoodDetailResponse? Body, ObjectResult? Problem)>
        DetailAsync(string id, string uid, bool safetyRequired,
                    CancellationToken ct)
    {
        var row = await db.Foods
            .Where(f => f.Id == id
                        && f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Join(db.FoodCategories, f => f.CategoryId, c => c.Id,
                  (f, c) => new { Food = f, Category = c })
            .FirstOrDefaultAsync(ct);
        if (row is null)
        {
            return (null, Fail(404, ErrorCode.NotFound, "Không tìm thấy món ăn"));
        }

        var nutrition = await db.FoodNutrition
            .FirstOrDefaultAsync(n => n.FoodId == id, ct);
        if (nutrition is null)
        {
            // The food exists but has no nutrition row, so there is nothing
            // to show and nothing to judge it by. A 404 would be wrong — the
            // dish is there — and inventing zeros would make it look like
            // the safest food in the catalogue.
            log.LogError(
                "Food {Food} has no food_nutrition row, so its detail cannot "
                + "be built.", id);
            return (null, Fail(500, ErrorCode.InternalError,
                               "Lỗi máy chủ, vui lòng thử lại"));
        }

        var safety = await ml.FoodSafetyAsync(
            new MlFoodSafetyRequest { UserId = uid, FoodIds = [id] }, ct);
        MlFoodSafetyItem? unsafeEntry = null;
        var isSafe = false;
        if (safety.Failure is { } failure)
        {
            if (safetyRequired) return (null, Report(failure));
            log.LogWarning(
                "Food {Food} was created, but its safety is unknown: {Detail}",
                id, failure.Detail);
        }
        else
        {
            var answer = safety.Required;
            unsafeEntry = answer.Unsafe.FirstOrDefault(u => u.FoodId == id);
            isSafe = EdibleIds(answer).Contains(id);
        }

        var mark = await db.UserFoodMarks
            .Where(m => m.UserId == uid && m.FoodId == id)
            .Select(m => m.Kind)
            .FirstOrDefaultAsync(ct);

        var tags = await db.FoodTags
            .Where(ft => ft.FoodId == id)
            .Join(db.Tags, ft => ft.TagId, t => t.Id,
                  (ft, t) => new FoodTagDto
                  {
                      Id = t.Id,
                      NameVi = t.NameVi,
                      TagType = t.TagType,
                  })
            .OrderBy(t => t.TagType)
            .ThenBy(t => t.NameVi)
            .ToListAsync(ct);

        // The condition names come back from the ML service as
        // `conditions.name_vi`; the ids are looked up here so the app can act
        // on a warning — open the declaration screen at the right row.
        var byName = await db.Conditions
            .ToDictionaryAsync(c => c.NameVi, c => new { c.Id, c.Code }, ct);

        var warnings = (unsafeEntry?.Reasons ?? [])
            // The user's own block is not a warning. It reaches the screen as
            // `mark` instead, so the switch can be drawn on without the page
            // also claiming a health reason that does not exist.
            .Where(r => !r.UserChoice)
            .Select(r => new FoodWarningDto
            {
                ConditionId = byName.TryGetValue(r.Condition, out var c)
                    ? c.Id
                    : null,
                // The code §7.5.2's example shows. Added by migration 008;
                // until then there was no `conditions.code` and the id went
                // out in its place.
                ConditionCode = byName.TryGetValue(r.Condition, out var cc)
                    ? cc.Code
                    : null,
                ConditionName = r.Condition,
                RuleType = r.RuleType,
                Message = FoodWarnings.Message(r),
                IsHard = true,
                MissingData = r.MissingData,
            })
            .ToList();

        var mine = await db.Feedbacks
            .Where(fb => fb.UserId == uid && fb.FoodId == id)
            // The most recent one. `idx_user_food_time` indexes exactly this
            // ordering, and the column has no unique key on purpose: taste
            // changes, and both ratings are kept.
            .OrderByDescending(fb => fb.CreatedAt)
            .ThenByDescending(fb => fb.Id)
            .Select(fb => new MyFeedbackDto
            {
                Id = fb.Id,
                Rating = fb.Rating,
                Comment = fb.Comment,
                CreatedAt = fb.CreatedAt,
            })
            .FirstOrDefaultAsync(ct);

        return (new FoodDetailResponse
        {
            Id = row.Food.Id,
            OwnerId = row.Food.OwnerId,
            Name = row.Food.Name,
            Description = row.Food.Description,
            ImageUrl = row.Food.ImageUrl,
            Category = new FoodCategoryRefDto
            {
                Id = row.Category.Id,
                Name = row.Category.Name,
            },
            SpiceLevel = row.Food.SpiceLevel,
            DishRole = row.Food.DishRole,
            Nutrition = new FoodNutritionDto
            {
                ServingSizeG = nutrition.ServingSizeG,
                CaloriesKcal = nutrition.CaloriesKcal,
                ProteinG = nutrition.ProteinG,
                CarbsG = nutrition.CarbsG,
                FatG = nutrition.FatG,
                FiberG = nutrition.FiberG,
                SugarG = nutrition.SugarG,
                SodiumMg = nutrition.SodiumMg,
                CholesterolMg = nutrition.CholesterolMg,
                PurineMg = nutrition.PurineMg,
                CalciumMg = nutrition.CalciumMg,
                IronMg = nutrition.IronMg,
                ZincMg = nutrition.ZincMg,
                VitaminAMcg = nutrition.VitaminAMcg,
                VitaminCMg = nutrition.VitaminCMg,
            },
            Tags = tags,
            IsSafeForUser = isSafe,
            Mark = mark,
            Warnings = warnings,
            MyFeedback = mine,
        }, null);
    }

    // ── 7.5.3 A dish of one's own ────────────────────────────────────────

    /// <summary>
    /// Adds a dish only its creator sees — what makes a diary line possible
    /// for something the catalogue does not have.
    ///
    /// <para><b><c>owner_id</c> is always the caller.</b> <c>NULL</c> is the
    /// shared catalogue, which only an administrator fills; letting a user
    /// write it would let them publish to everyone.</para>
    ///
    /// <para><b>A nutrient not given stays <c>NULL</c>.</b> The F1 filter
    /// then excludes the dish wherever one of this user's conditions needs
    /// that figure, and flags it <c>missingData</c> — it can still be logged
    /// as eaten, it just is never suggested on a guess.</para>
    ///
    /// <para>It is not part of the feature space's scale: the ML service
    /// builds the min–max bounds and the imputation medians from the shared
    /// catalogue only (<c>ml/features.py</c>), so one user's 4000-kcal entry
    /// cannot move everyone else's vectors.</para>
    /// </summary>
    [HttpPost]
    public async Task<IActionResult> Create(
        CreateFoodRequest req, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var name = req.Name!.Trim();
        if (name.Length < 2)
        {
            return Invalid("name", "Tên món dài từ 2 đến 200 ký tự");
        }

        var categoryId = req.CategoryId!.Trim();
        if (!await db.FoodCategories.AnyAsync(c => c.Id == categoryId, ct))
        {
            return Invalid("categoryId", "Nhóm món không tồn tại");
        }

        var tagIds = (req.TagIds ?? []).Distinct().ToList();
        if (tagIds.Count > 0)
        {
            var usable = await db.Tags
                .Where(t => tagIds.Contains(t.Id)
                            && (t.TagType == "allergen" || t.TagType == "diet"))
                .Select(t => t.Id)
                .ToListAsync(ct);
            var refused = tagIds.Except(usable).ToList();
            if (refused.Count > 0)
            {
                return Invalid(
                    "tagIds",
                    "Nhãn không tồn tại hoặc không phải nhãn dị ứng / chế độ "
                    + "ăn: " + string.Join(", ", refused));
            }
        }

        // The name is unique per owner on `uq_owner_name`, which compares
        // under the column's collation — so the check here uses the database
        // too, rather than a C# comparison that would disagree on case and
        // accents.
        if (await db.Foods.AnyAsync(
                f => f.OwnerId == uid && f.Name == name, ct))
        {
            return Fail(409, ErrorCode.FoodAlreadyExists,
                        "Bạn đã có một món riêng trùng tên");
        }

        var n = req.Nutrition!;
        var now = Clock.Now;
        var food = new Foods
        {
            Id = Guid.NewGuid().ToString(),
            CategoryId = categoryId,
            Name = name,
            SpiceLevel = (byte)(req.SpiceLevel ?? 0),
            DishRole = req.DishRole!,
            PopularityScore = 0m,
            IsActive = true,
            OwnerId = uid,
            CreatedAt = now,
            UpdatedAt = now,
        };

        // Two saves in one transaction, the dish first. The entities carry
        // no navigation between them, so EF does not know `food_nutrition`
        // depends on `foods` and may insert it first — which the foreign key
        // refuses.
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        db.Foods.Add(food);
        try
        {
            await db.SaveChangesAsync(ct);
        }
        catch (DbUpdateException)
        {
            // Two requests with the same name, both past the check above;
            // `uq_owner_name` let one in. Anything else is rethrown.
            await tx.RollbackAsync(ct);
            db.ChangeTracker.Clear();
            if (await db.Foods.AnyAsync(
                    f => f.OwnerId == uid && f.Name == name, ct))
            {
                return Fail(409, ErrorCode.FoodAlreadyExists,
                            "Bạn đã có một món riêng trùng tên");
            }
            throw;
        }

        db.FoodNutrition.Add(new FoodNutrition
        {
            Id = Guid.NewGuid().ToString(),
            FoodId = food.Id,
            ServingSizeG = (ushort)req.ServingSizeG!.Value,
            CaloriesKcal = Round2(n.Calories!.Value),
            ProteinG = Round2(n.ProteinG ?? 0m),
            CarbsG = Round2(n.CarbsG ?? 0m),
            FatG = Round2(n.FatG ?? 0m),
            FiberG = Round2(n.FiberG),
            SugarG = Round2(n.SugarG),
            SodiumMg = Round2(n.SodiumMg),
            PurineMg = Round2(n.PurineMg),
            UpdatedAt = now,
        });
        foreach (var tag in tagIds)
        {
            db.FoodTags.Add(new FoodTags { FoodId = food.Id, TagId = tag });
        }
        await db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);

        var (body, problem) = await DetailAsync(
            food.Id, uid, safetyRequired: false, ct);
        return problem ?? StatusCode(StatusCodes.Status201Created, body);
    }

    private static decimal Round2(decimal v)
        => Math.Round(v, 2, MidpointRounding.AwayFromZero);

    private static decimal? Round2(decimal? v)
        => v is { } x ? Round2(x) : null;

    // ── Bookmark a dish, or ask for it not to be suggested ───────────────

    /// <summary>
    /// Sets or clears this user's mark on a food.
    ///
    /// <para><b>Not in §6's list of seven.</b> The specification has no place
    /// for an opinion about a dish the user has never eaten: §7.8.1 requires
    /// a feedback's food to have been in one of their plans <b>and</b> in
    /// their diary, deliberately, so a rating always rests on a meal. The
    /// bookmark and the "không gợi ý món này nữa" switch are both opinions
    /// about a dish that may never have been cooked, so they need a table and
    /// an endpoint of their own.</para>
    ///
    /// <para><b>Idempotent.</b> Sending the same <c>kind</c> twice answers
    /// <c>200</c> twice with the same body; the toggle in the app is free to
    /// re-send rather than track what it already sent.</para>
    ///
    /// <para><b>The two marks are exclusive.</b> One row per (user, food), so
    /// bookmarking a blocked dish unblocks it and vice versa — "saved to try"
    /// and "never suggest this" cannot both be true.</para>
    ///
    /// <para>Status codes: <c>404 NOT_FOUND</c> for a dish this user cannot
    /// see, <c>409 BLOCK_WOULD_EMPTY_MEAL</c> when blocking it would leave a
    /// meal with nothing to put in a role it needs, and
    /// <c>503 ML_UNAVAILABLE</c> when that last question cannot be
    /// answered.</para>
    /// </summary>
    [HttpPut("{id}/mark")]
    public async Task<IActionResult> SetMark(
        string id,
        [FromBody] FoodMarkRequest? body,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var kind = body?.Kind;

        var food = await db.Foods
            .Where(f => f.Id == id
                        && f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Select(f => new { f.Id, f.DishRole })
            .FirstOrDefaultAsync(ct);
        if (food is null)
        {
            return Fail(404, ErrorCode.NotFound, "Không tìm thấy món ăn");
        }

        if (kind == "blocked")
        {
            var refusal = await WouldEmptyAMeal(uid, food.Id, food.DishRole, ct);
            if (refusal is not null)
            {
                return refusal;
            }
        }

        var existing = await db.UserFoodMarks
            .FirstOrDefaultAsync(m => m.UserId == uid && m.FoodId == id, ct);

        if (kind is null)
        {
            if (existing is not null)
            {
                db.UserFoodMarks.Remove(existing);
                await db.SaveChangesAsync(ct);
            }
            return Ok(new FoodMarkResponse { FoodId = id, Kind = null });
        }

        if (existing is null)
        {
            existing = new UserFoodMarks
            {
                UserId = uid,
                FoodId = id,
                Kind = kind,
                CreatedAt = Clock.Now,
            };
            db.UserFoodMarks.Add(existing);
            await db.SaveChangesAsync(ct);
        }
        else if (existing.Kind != kind)
        {
            existing.Kind = kind;
            // The timestamp moves with the kind. It records when the mark now
            // showing was made, and a block carrying the date the user
            // bookmarked the dish would be a false record of a decision they
            // reversed.
            existing.CreatedAt = Clock.Now;
            await db.SaveChangesAsync(ct);
        }

        return Ok(new FoodMarkResponse
        {
            FoodId = id,
            Kind = existing.Kind,
            MarkedAt = existing.CreatedAt,
        });
    }

    /// <summary>
    /// Whether blocking <paramref name="foodId"/> would leave a meal unable
    /// to be assembled — and the refusal to send back if so.
    ///
    /// <para>Blocking a dish can only empty <b>its own</b> role, so the
    /// question is narrow: is this the last dish left in a role that some
    /// meal requires? The count of what is left comes from the ML service,
    /// which owns the F1 filter and has already subtracted the dishes this
    /// user blocked before; this method only groups that answer by a column
    /// of its own table.</para>
    ///
    /// <para>A dish F1 already excludes is never refused. It is not in the
    /// pool, so blocking it removes nothing — and refusing would tell the
    /// user they cannot reject a dish the system was never going to offer
    /// them.</para>
    ///
    /// <para>The threshold is <b>zero left</b>, not "few left". That is the
    /// decided behaviour: blocking a dish the user has not eaten costs them
    /// that dish for the day and nothing replaces it automatically — a
    /// thinner day is theirs to choose. A day with no <c>main</c> at all is
    /// not a thinner day; it is a plan that cannot be built.</para>
    /// </summary>
    private async Task<ObjectResult?> WouldEmptyAMeal(
        string uid, string foodId, string dishRole, CancellationToken ct)
    {
        var meals = MealStructure.MealsRequiring(dishRole);
        if (meals.Length == 0)
        {
            // `soup`, `dessert` and `drink`: no meal is assembled around
            // them, so none can be emptied by losing one.
            return null;
        }

        var safety = await ml.FoodSafetyAsync(
            new MlFoodSafetyRequest { UserId = uid }, ct);
        if (safety.Failure is { } failure)
        {
            return Report(failure);
        }

        var pool = safety.Required.SafeFoodIds.ToHashSet();
        if (!pool.Contains(foodId))
        {
            return null;
        }

        // The role's ids first, then the intersection in memory. The other
        // way round — sending the pool into the query — puts a couple of
        // hundred UUIDs into an `IN` list to answer a question about one
        // role, which holds well under two hundred foods of the 318.
        var inRole = await db.Foods
            .Where(f => f.IsActive
                        && f.DishRole == dishRole
                        && f.Id != foodId
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Select(f => f.Id)
            .ToListAsync(ct);
        if (inRole.Any(pool.Contains))
        {
            return null;
        }

        return Fail(
            409, ErrorCode.BlockWouldEmptyMeal,
            $"Đây là món cuối cùng còn lại cho {MealLabels.Join(meals)}. "
            + "Bỏ gợi ý món này thì không dựng được thực đơn. Hãy khai báo "
            + "lại tình trạng sức khỏe, hoặc bỏ chặn một món khác cùng loại.");
    }

    private ObjectResult Report(MlFailure failure)
    {
        if (failure.IsSystemFault())
        {
            log.LogError("Food catalogue: {Detail}", failure.Detail);
        }
        else
        {
            log.LogInformation("Food catalogue: {Detail}", failure.Detail);
        }
        return failure.ToActionResult(HttpContext.TraceIdentifier);
    }
}
