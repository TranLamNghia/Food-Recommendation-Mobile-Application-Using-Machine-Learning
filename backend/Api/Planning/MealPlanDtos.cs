using System.ComponentModel.DataAnnotations;
using Api.Profile;

namespace Api.Planning;

/// <summary>
/// Which <c>meal_plan_items.status</c> values a client may set.
///
/// <para>Three of the five. <c>suggested</c> is what this backend writes when
/// it generates a plan and <c>replaced</c> is what it writes when a dish is
/// swapped (§7.6.5). Both are statements about what the <b>system</b> did,
/// and §4.6 computes label weights from them — a client able to send either
/// could relabel its own training data: mark a dish <c>replaced</c> without
/// replacing it, and that food is taught to the model as a rejection.</para>
///
/// <para>A test asserts this stays a subset of
/// <c>Api.Profile.Enums.MealItemStatus</c>, which
/// <c>tools/gen_entities.py</c> in turn compares against the ENUM in
/// <c>db/schema.sql</c>. So a value here that MySQL would refuse cannot
/// survive both checks.</para>
/// </summary>
public static class MealItemStatus
{
    public const string Suggested = "suggested";
    public const string Kept = "kept";
    public const string Replaced = "replaced";
    public const string Eaten = "eaten";
    public const string Skipped = "skipped";

    /// <summary>What <c>PATCH .../status</c> accepts.</summary>
    public static readonly string[] ClientSettable = [Kept, Eaten, Skipped];
}

/// <summary>§7.6.2 — generate a plan for one day.</summary>
public sealed class GeneratePlanRequest
{
    [Required(ErrorMessage = "Thiếu ngày cần sinh thực đơn")]
    public DateOnly? PlanDate { get; init; }

    /// <summary>
    /// <c>true</c> deletes the existing plan for that day and builds a new
    /// one. Default <c>false</c>, which answers <c>409 MEAL_PLAN_EXISTS</c>
    /// instead — a plan the user has already started eating from should not
    /// vanish because a screen was reopened.
    /// </summary>
    public bool Regenerate { get; init; }

    /// <summary>
    /// §7.6.2 allows generating only some meals. <b>This API refuses
    /// anything but all four</b>, with a <c>400</c> that says why.
    ///
    /// <para>Phase 5 of Step 4 repairs the plan at <b>day</b> level: the
    /// ±10 % energy commitment and every <c>per_day</c> nutrient threshold —
    /// sodium for hypertension, for one — are properties of the whole day.
    /// Assembling lunch alone would have no day to measure, so the figure
    /// written into <c>calorie_deviation_pct</c> would be a deviation from
    /// 37.5 % of a target, reported as if it were the day's. The field is
    /// accepted and validated rather than ignored, so a client sending it
    /// learns that, instead of receiving a plan that quietly means something
    /// else.</para>
    /// </summary>
    public List<string>? MealTypes { get; init; }

    /// <summary>
    /// The 70-30 mechanism's target share, 0 to 0.5. Default 0.3.
    /// <c>chk_expl_ratio</c> is the same range in the database.
    /// </summary>
    [Range(0.0, 0.5,
           ErrorMessage = "Tỷ lệ thăm dò phải trong khoảng 0 đến 0.5")]
    public double? ExplorationRatio { get; init; }
}

/// <summary>§7.6.5 — swap one dish for another.</summary>
public sealed class ReplaceItemRequest
{
    [Required(ErrorMessage = "Thiếu mã món ăn mới")]
    public string? NewFoodId { get; init; }

    /// <summary>
    /// Grams. Omitted means one standard serving of the new food.
    ///
    /// <para>Stored as <c>portion_multiplier</c>, not as grams: the schema
    /// keeps servings because <c>food_nutrition.serving_size_g</c> already
    /// holds what one serving weighs, and storing both invites them to
    /// disagree. <c>chk_item_portion</c> allows 0.1 to 5 servings, so a gram
    /// figure outside that range of the new food's own serving is
    /// refused.</para>
    /// </summary>
    [Range(1, 5000, ErrorMessage = "Khối lượng phải từ 1 đến 5000 gam")]
    public int? ServingSizeG { get; init; }
}

/// <summary>§7.6.6 — mark what happened to a dish.</summary>
public sealed class UpdateItemStatusRequest
{
    /// <summary><c>kept</c> · <c>eaten</c> · <c>skipped</c>.</summary>
    [Required(ErrorMessage = "Thiếu trạng thái")]
    [InEnum(nameof(Enums.MealItemStatus))]
    public string? Status { get; init; }
}

/// <summary>§7.6.1 — one day's plan.</summary>
public sealed class MealPlanResponse
{
    public string Id { get; init; } = string.Empty;
    public DateOnly PlanDate { get; init; }

    /// <summary><c>draft</c> · <c>active</c> · <c>completed</c>.</summary>
    public string Status { get; init; } = string.Empty;

    /// <summary>
    /// <c>rule_based</c> · <c>content_based</c> · <c>ml</c> ·
    /// <c>hybrid</c> — which stage of §4.1 scored this plan.
    /// </summary>
    public string GenerationSource { get; init; } = string.Empty;

    /// <summary>
    /// <c>ml_models.version</c>, or <c>null</c> when no model took part.
    /// </summary>
    public string? ModelVersion { get; init; }

    public MacrosDto Targets { get; init; } = new();

    /// <summary>
    /// What the plan actually adds up to. <c>null</c> on a plan whose Step 4
    /// has not finished — the schema allows that state and deliberately has
    /// no <c>DEFAULT 0</c>, because a stored 0 would make
    /// <c>calorie_deviation_pct</c> read −100 % the moment the row appeared.
    /// </summary>
    public MacrosDto? Actuals { get; init; }

    public decimal? CalorieDeviationPct { get; init; }

    /// <summary>
    /// <c>|calorieDeviationPct| &lt;= 10</c> — the thesis proposal's
    /// commitment, and what the app shows as a green or amber mark.
    /// <c>null</c> when there are no actuals to compare.
    /// </summary>
    public bool? WithinTolerance { get; init; }

    public decimal? TotalPreferenceScore { get; init; }

    /// <summary>The 70-30 target share this plan was built with.</summary>
    public decimal? ExplorationRatio { get; init; }

    /// <summary>The four meals, in the order they are eaten.</summary>
    public List<MealDto> Meals { get; init; } = [];

    /// <summary>
    /// Day-level nutrient thresholds the plan does not meet.
    ///
    /// <para>Three states, and they are different answers: a <b>list</b> of
    /// breaches; an <b>empty list</b>, meaning phase 5 checked and the plan
    /// is clear; and <c>null</c>, meaning nobody has checked <i>this
    /// response</i>. <c>null</c> is what a plain read returns, because
    /// <c>meal_plans</c> has no column for the result and recomputing it from
    /// <c>condition_rules</c> here would be a second implementation of the
    /// check. A freshly generated plan carries the real answer.</para>
    /// </summary>
    public List<NutrientViolationDto>? NutrientViolations { get; init; }

    public DateTime GeneratedAt { get; init; }
}

/// <summary>Energy and the three macronutrients.</summary>
public sealed class MacrosDto
{
    public decimal CaloriesKcal { get; init; }
    public decimal ProteinG { get; init; }
    public decimal CarbsG { get; init; }
    public decimal FatG { get; init; }
}

/// <summary>One meal of the day.</summary>
public sealed class MealDto
{
    /// <summary><c>breakfast</c> · <c>lunch</c> · <c>dinner</c> · <c>snack</c>.</summary>
    public string MealType { get; init; } = string.Empty;

    /// <summary>
    /// This meal's share of the day's target — 27.5 / 37.5 / 27.5 / 7.5 %,
    /// from <c>Api.Nutrition.NutritionTargets.MealShare</c>. Computed from
    /// the plan's <b>stored</b> target, so it is the share of the target the
    /// plan was built against rather than of a target recomputed today.
    /// </summary>
    public int TargetCaloriesKcal { get; init; }

    /// <summary>
    /// What this meal adds up to. Dishes that were replaced do not count —
    /// they are history, not food on the plate.
    /// </summary>
    public decimal ActualCaloriesKcal { get; init; }

    public List<MealItemDto> Items { get; init; } = [];
}

/// <summary>One dish in one meal — a <c>meal_plan_items</c> row.</summary>
public sealed class MealItemDto
{
    public string Id { get; init; } = string.Empty;
    public FoodBriefDto Food { get; init; } = new();

    /// <summary>
    /// Grams on the plate: <c>portion_multiplier</c> times the food's
    /// standard serving. Rounded to a whole gram — a tenth of a gram of rice
    /// is not a thing anyone serves.
    /// </summary>
    public int ServingSizeG { get; init; }

    public decimal? PredictedScore { get; init; }

    /// <summary>
    /// <c>suggested</c> · <c>kept</c> · <c>replaced</c> · <c>eaten</c> ·
    /// <c>skipped</c>.
    /// </summary>
    public string Status { get; init; } = string.Empty;

    /// <summary>
    /// What this dish was replaced <b>by</b>, when it was. Present so the
    /// screen can show "đã đổi sang …" rather than making the old dish
    /// disappear.
    /// </summary>
    public FoodBriefDto? ReplacedByFood { get; init; }

    /// <summary>
    /// <c>null</c> means this dish was chosen by the preference vector
    /// (exploitation). A number means it came from the noised vector
    /// (exploration), and the number is the noise amplitude δ — the app can
    /// show a "Thử món mới" badge. There is no separate flag, by design:
    /// <c>exploration_delta IS NOT NULL</c> is the question.
    /// </summary>
    public decimal? ExplorationDelta { get; init; }

    public int? Position { get; init; }
}

/// <summary>A food, as it appears inside a plan.</summary>
public sealed class FoodBriefDto
{
    public string Id { get; init; } = string.Empty;

    /// <summary>Vietnamese, straight out of <c>foods.name</c>.</summary>
    public string Name { get; init; } = string.Empty;

    public string? ImageUrl { get; init; }

    /// <summary><c>food_categories.name</c> — Vietnamese free text.</summary>
    public string CategoryName { get; init; } = string.Empty;

    /// <summary>
    /// A <c>dish_role</c> ENUM code. The app translates it to a Vietnamese
    /// label right before the UI; this API never does.
    /// </summary>
    public string DishRole { get; init; } = string.Empty;

    /// <summary>Energy of <b>one standard serving</b>.</summary>
    public decimal CaloriesKcal { get; init; }
}

/// <summary>A day-level threshold the plan does not meet.</summary>
public sealed class NutrientViolationDto
{
    /// <summary>
    /// The nutrient key, shared with <c>condition_rules.nutrient</c> —
    /// <c>sodium_mg</c>, <c>sugar_g</c>, … A stable code.
    /// </summary>
    public string Nutrient { get; init; } = string.Empty;

    /// <summary><c>lte</c> or <c>gte</c>.</summary>
    public string Comparator { get; init; } = string.Empty;

    public decimal Threshold { get; init; }
    public decimal Actual { get; init; }

    /// <summary>
    /// Which condition the threshold comes from —
    /// <c>conditions.name_vi</c>, Vietnamese, and the one field here meant
    /// to be read by the user.
    /// </summary>
    public string Condition { get; init; } = string.Empty;
}

/// <summary>§7.6.4 — what could go in this dish's place.</summary>
public sealed class AlternativesResponse
{
    public AlternativeOriginalDto OriginalItem { get; init; } = new();
    public List<AlternativeDto> Alternatives { get; init; } = [];
}

/// <summary>The dish being replaced, for the screen's header.</summary>
public sealed class AlternativeOriginalDto
{
    public string Id { get; init; } = string.Empty;
    public string FoodName { get; init; } = string.Empty;
    public decimal CaloriesKcal { get; init; }
    public string DishRole { get; init; } = string.Empty;
}

/// <summary>One candidate.</summary>
public sealed class AlternativeDto
{
    public FoodBriefDto Food { get; init; } = new();

    /// <summary>
    /// Grams this candidate would be served at — one standard serving of it.
    /// </summary>
    public int ServingSizeG { get; init; }

    public decimal PredictedScore { get; init; }

    /// <summary>
    /// How the day's energy would move: the candidate's energy minus the
    /// current dish's, both at the portions that would actually be served.
    /// </summary>
    public decimal CalorieDeltaKcal { get; init; }

    /// <summary>
    /// Whether the whole day would still be inside ±10 % after the swap. The
    /// app dims or warns on <c>false</c> rather than hiding the option — a
    /// user may well prefer a dish that costs them a little accuracy.
    /// </summary>
    public bool KeepsWithinTolerance { get; init; }
}

/// <summary>§7.6.6's answer.</summary>
public sealed class UpdateItemStatusResponse
{
    public string Id { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;

    /// <summary>
    /// Whether this call created the diary entry. <c>false</c> on a repeat of
    /// <c>eaten</c>: the entry already exists and a second one would count
    /// the meal twice in every compliance figure.
    /// </summary>
    public bool DiaryEntryCreated { get; init; }

    /// <summary>
    /// <c>food_diary.id</c> — a UUID string, so the app can navigate to the
    /// rating screen. §7.6.6's example shows an integer; the column is
    /// <c>CHAR(36)</c>, like every other id in this schema.
    /// </summary>
    public string? DiaryEntryId { get; init; }
}
