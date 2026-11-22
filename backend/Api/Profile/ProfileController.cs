using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Nutrition;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Profile;

/// <summary>
/// The Health profile group — specification §7.2.1 through §7.2.5.
///
/// <para>Wave 2 in the implementation order of §10.2: this is <b>Step 1</b> of
/// the recommendation algorithm, and it does not depend on the ML
/// service.</para>
///
/// <para>Every endpoint here works only on the data of the person currently
/// logged in. <c>userId</c> comes from the token's <c>sub</c> claim and
/// <b>never</b> from a parameter — specification §2.4.</para>
///
/// <para>Note on language: every <c>message</c> passed to <see cref="Fail"/>
/// and every <c>FieldError.Message</c> stays in Vietnamese. Those are the
/// <c>error.message</c> and <c>error.details[].message</c> of specification
/// §2.5, which end users read; the stable string the frontend branches on is
/// <c>error.code</c>.</para>
/// </summary>
[ApiController]
[Route("api/v1/profile")]
[Authorize]
public sealed class ProfileController(AppDbContext db) : ControllerBase
{
    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.2.1 Read the profile ───────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> Get()
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var profile = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        if (profile is null)
        {
            // 404, not a 200 with an empty body: the frontend uses this very
            // code to decide whether to send the user to the profile form.
            return Fail(404, ErrorCode.NotFound,
                        "Chưa khai báo hồ sơ sức khỏe");
        }

        return Ok(await BuildProfile(profile));
    }

    // ── 7.2.2 Create or update the profile ───────────────────────────────

    [HttpPut]
    public async Task<IActionResult> Upsert(UpsertProfileRequest req)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var dateOfBirth = req.DateOfBirth!.Value;
        var today = Clock.Today;
        var age = NutritionTargets.Age(dateOfBirth, today);

        // The 13–100 age range in §7.2.2 has NO matching database constraint
        // — `health_profiles` only has chk_height and chk_weight. So this
        // check is the only layer stopping it, and dropping it would apply
        // the Mifflin formula to a five-year-old, where it does not hold.
        if (age is < 13 or > 100)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "dateOfBirth",
                    Message = $"Tuổi tính ra {age}, phải trong khoảng 13 đến 100",
                }]);
        }

        var profile = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        var isNew = profile is null;

        if (profile is null)
        {
            profile = new HealthProfiles
            {
                Id = Guid.NewGuid().ToString(),
                UserId = uid,
                // The three macro percentages take the SCHEMA'S DEFAULTS
                // rather than being hard-coded here. 15/60/25 is the
                // `DEFAULT` of the three target_*_pct columns, and
                // `chk_macro_sum` forces them to add up to exactly 100.
                TargetProteinPct = 15,
                TargetCarbsPct = 60,
                TargetFatPct = 25,
                CreatedAt = Clock.Now,
            };
            db.HealthProfiles.Add(profile);
        }

        profile.Gender = req.Gender;
        profile.DateOfBirth = dateOfBirth;
        profile.HeightCm = req.HeightCm!.Value;
        profile.WeightKg = req.WeightKg!.Value;
        // Assigned straight through, including a null: §7.2.2 replaces the
        // whole profile, so leaving the field out clears the target. That is
        // what the app does when the goal changes to one that has none.
        profile.TargetWeightKg = req.TargetWeightKg;
        profile.ActivityLevel = req.ActivityLevel;
        profile.Goal = req.Goal;
        profile.UpdatedAt = Clock.Now;

        // Step 1 is recomputed on EVERY call. All six fields the user can
        // edit feed into the formula, so there is no case where an edit
        // leaves the targets unchanged — see the note on "no computed_at
        // column" in db/schema.sql.
        var step1 = ComputeStep1(profile, today);
        profile.BmrKcal = Round(step1.BmrKcal);
        profile.TdeeKcal = Round(step1.TdeeKcal);
        profile.DailyCaloriesTarget = Round(step1.DailyCaloriesTarget);

        await db.SaveChangesAsync();

        // `bmi` is a GENERATED VIRTUAL column — the database computes it on
        // read, so the in-memory value is still the one from the previous
        // read. Reload so the response carries exactly the number the
        // database will return later.
        await db.Entry(profile).ReloadAsync();

        var body = new UpsertProfileResponse
        {
            Profile = await BuildProfile(profile),
            NutritionTargets = BuildTargets(profile, step1),
        };

        return isNew
            ? StatusCode(StatusCodes.Status201Created, body)
            : Ok(body);
    }

    // ── 7.2.3 Read the nutrition targets ─────────────────────────────────

    [HttpGet("nutrition-targets")]
    public async Task<IActionResult> GetTargets()
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var profile = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        if (profile is null)
        {
            // 409 PROFILE_REQUIRED rather than 404: the "targets" resource is
            // not the thing that is missing — it cannot be computed because
            // an earlier step is missing. Specification §4 says the frontend
            // has to send the user to the profile form.
            return Fail(409, ErrorCode.ProfileRequired,
                        "Chưa khai báo hồ sơ sức khỏe");
        }

        // Recomputed rather than read from the three stored columns. Those
        // three are a SNAPSHOT so that an older meal plan keeps its own
        // targets; this endpoint returns the CURRENT targets, and it has to
        // include the part that is not stored at all — neither the macro
        // grams nor the meal split has a column.
        var step1 = ComputeStep1(profile, Clock.Today);
        return Ok(BuildTargets(profile, step1));
    }

    // ── 7.2.4 Read my conditions ─────────────────────────────────────────

    [HttpGet("conditions")]
    public async Task<IActionResult> GetConditions()
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        // A plain array, not paginated — this list has at most a few items.
        return Ok(await ReadConditions(uid));
    }

    // ── 7.2.5 Update the conditions ──────────────────────────────────────

    [HttpPut("conditions")]
    public async Task<IActionResult> PutConditions(
        UpsertConditionsRequest req)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var incoming = req.Conditions!;

        // A repeated `conditionId` within one request: `uq_user_condition`
        // would stop it, but with a `MySqlException` that cannot say which
        // field was wrong.
        var duplicates = incoming.GroupBy(c => c.ConditionId)
            .Where(g => g.Count() > 1)
            .Select(g => g.Key!.Value)
            .ToList();
        if (duplicates.Count > 0)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "conditions",
                    Message = "conditionId lặp lại: "
                        + string.Join(", ", duplicates),
                }]);
        }

        var ids = incoming.Select(c => c.ConditionId!.Value).ToList();
        var existing = await db.Conditions
            .Where(c => ids.Contains(c.Id))
            .Select(c => c.Id)
            .ToListAsync();
        var missing = ids.Except(existing).ToList();
        if (missing.Count > 0)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "conditions",
                    Message = "conditionId không tồn tại: "
                        + string.Join(", ", missing),
                }]);
        }

        // "Replaces the whole list" (§7.2.5) has to be ONE transaction.
        // Deleting and then inserting without one would leave the user with
        // no conditions at all if the insert failed — which means the F1
        // filter stops excluding dishes, and someone allergic to seafood gets
        // recommended shrimp.
        await using var tx = await db.Database.BeginTransactionAsync();

        await db.UserConditions.Where(x => x.UserId == uid)
            .ExecuteDeleteAsync();

        foreach (var c in incoming)
        {
            db.UserConditions.Add(new UserConditions
            {
                Id = Guid.NewGuid().ToString(),
                UserId = uid,
                ConditionId = c.ConditionId!.Value,
                Severity = c.Severity,
                Note = string.IsNullOrWhiteSpace(c.Note) ? null : c.Note,
                CreatedAt = Clock.Now,
            });
        }

        await db.SaveChangesAsync();
        await tx.CommitAsync();

        return Ok(await ReadConditions(uid));
    }

    // ── shared ───────────────────────────────────────────────────────────

    private static Step1Result ComputeStep1(HealthProfiles h, DateOnly today)
        => NutritionTargets.Compute(
            h.Gender, h.DateOfBirth, h.HeightCm, h.WeightKg,
            h.ActivityLevel, h.Goal,
            h.TargetProteinPct, h.TargetCarbsPct, h.TargetFatPct,
            today);

    /// <summary>
    /// Rounds to the schema's <c>SMALLINT UNSIGNED</c>.
    ///
    /// <para><c>MidpointRounding.AwayFromZero</c> rather than the default:
    /// .NET's <c>Math.Round</c> rounds to even by default (2.5 becomes 2),
    /// while Dart and Python both round away from zero. That difference only
    /// shows up on exactly the .5 cases — rare, so it would slip past every
    /// manual trial and only the parity suite would catch it.</para>
    /// </summary>
    private static ushort Round(decimal v)
        => (ushort)Math.Clamp(
            Math.Round(v, MidpointRounding.AwayFromZero), 0, ushort.MaxValue);

    private async Task<ProfileResponse> BuildProfile(HealthProfiles h)
    {
        var today = Clock.Today;
        // The database's `bmi` is an already-rounded DECIMAL(5,2). Use it
        // when there is one, so the response matches exactly what an SQL
        // query returns; recompute only when the row has not been through the
        // database.
        var bmi = h.Bmi ?? NutritionTargets.Bmi(h.WeightKg, h.HeightCm);
        return new ProfileResponse
        {
            Gender = h.Gender,
            DateOfBirth = h.DateOfBirth,
            Age = NutritionTargets.Age(h.DateOfBirth, today),
            HeightCm = h.HeightCm,
            WeightKg = h.WeightKg,
            TargetWeightKg = h.TargetWeightKg,
            Bmi = bmi,
            BmiCategory = NutritionTargets.BmiCategory(bmi),
            ActivityLevel = h.ActivityLevel,
            Goal = h.Goal,
            Conditions = await ReadConditions(h.UserId),
            CreatedAt = h.CreatedAt,
            UpdatedAt = h.UpdatedAt,
        };
    }

    private Task<List<UserConditionDto>> ReadConditions(string uid)
        => db.UserConditions
            .Where(uc => uc.UserId == uid)
            .Join(db.Conditions, uc => uc.ConditionId, c => c.Id,
                  (uc, c) => new UserConditionDto
                  {
                      ConditionId = c.Id,
                      NameVi = c.NameVi,
                      ConditionType = c.ConditionType,
                      Severity = uc.Severity,
                      Note = uc.Note,
                  })
            .OrderBy(x => x.ConditionId)
            .ToListAsync();

    private static NutritionTargetsResponse BuildTargets(
        HealthProfiles h, Step1Result s)
        => new()
        {
            Bmi = h.Bmi ?? Math.Round(s.Bmi, 2,
                                      MidpointRounding.AwayFromZero),
            BmiCategory = s.BmiCategory,
            BmrKcal = Round(s.BmrKcal),
            TdeeKcal = Round(s.TdeeKcal),
            ActivityFactor = s.ActivityFactorValue,
            DailyCaloriesTarget = Round(s.DailyCaloriesTarget),
            GoalAdjustmentKcal = (int)Math.Round(
                s.GoalAdjustmentKcal, MidpointRounding.AwayFromZero),
            MacroTargets = new MacroTargetsDto
            {
                ProteinPct = s.ProteinPct,
                // One decimal place, like the sample JSON in §7.2.3. The
                // grams do not need to be more precise than that: the food
                // composition table only has one decimal either.
                ProteinG = Math.Round(s.ProteinG, 1,
                                      MidpointRounding.AwayFromZero),
                CarbsPct = s.CarbsPct,
                CarbsG = Math.Round(s.CarbsG, 1,
                                    MidpointRounding.AwayFromZero),
                FatPct = s.FatPct,
                FatG = Math.Round(s.FatG, 1, MidpointRounding.AwayFromZero),
            },
            MealDistribution = s.MealDistribution()
                .Select(m => new MealShareDto
                {
                    MealType = m.MealType,
                    Pct = m.Pct,
                    CaloriesKcal = (int)Math.Round(
                        m.Kcal, MidpointRounding.AwayFromZero),
                })
                .ToList(),
            Formula = new FormulaDto
            {
                Expression = s.FormulaExpression(
                    h.Gender, h.WeightKg, h.HeightCm),
            },
        };
}
