using Api.Data;
using Api.Http;
using Api.Ml;
using Api.Planning;
using Api.Profile;
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

    // ── 7.5.1 Search and browse ──────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> Search(
        [FromQuery] string? q,
        [FromQuery] string? categoryId,
        [FromQuery] string? mealType,
        [FromQuery] string? dishRole,
        [FromQuery] decimal? maxCalories,
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

        var safety = await ml.FoodSafetyAsync(
            new MlFoodSafetyRequest { UserId = uid }, ct);
        if (safety.Failure is { } failure)
        {
            return Report(failure);
        }
        var safeIds = safety.Required.SafeFoodIds.ToHashSet();

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

        var row = await db.Foods
            .Where(f => f.Id == id
                        && f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Join(db.FoodCategories, f => f.CategoryId, c => c.Id,
                  (f, c) => new { Food = f, Category = c })
            .FirstOrDefaultAsync(ct);
        if (row is null)
        {
            return Fail(404, ErrorCode.NotFound, "Không tìm thấy món ăn");
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
            return Fail(500, ErrorCode.InternalError,
                        "Lỗi máy chủ, vui lòng thử lại");
        }

        var safety = await ml.FoodSafetyAsync(
            new MlFoodSafetyRequest { UserId = uid, FoodIds = [id] }, ct);
        if (safety.Failure is { } failure)
        {
            return Report(failure);
        }

        var answer = safety.Required;
        var unsafeEntry = answer.Unsafe.FirstOrDefault(u => u.FoodId == id);
        var isSafe = answer.SafeFoodIds.Contains(id);

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

        return Ok(new FoodDetailResponse
        {
            Id = row.Food.Id,
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
            Warnings = warnings,
            MyFeedback = mine,
        });
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
