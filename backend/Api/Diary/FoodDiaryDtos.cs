using System.ComponentModel.DataAnnotations;
using Api.Planning;
using Api.Profile;

namespace Api.Diary;

/// <summary>§7.7.1 — one range of days of the diary.</summary>
public sealed class FoodDiaryResponse
{
    public DateOnly From { get; init; }
    public DateOnly To { get; init; }

    /// <summary>
    /// Only the days that have something in them, oldest first. A range of
    /// 90 empty days is 90 objects saying nothing, and the app renders a day
    /// header from <see cref="DiaryDayDto.Date"/> either way.
    /// </summary>
    public List<DiaryDayDto> Days { get; init; } = [];
}

public sealed class DiaryDayDto
{
    public DateOnly Date { get; init; }

    /// <summary>
    /// The sum over the day's entries, each at the portion actually eaten. A
    /// food with no nutrition row contributes nothing and is not counted as
    /// zero — the same rule <c>MealPlanMapper.PortionOf</c> follows.
    /// </summary>
    public decimal TotalCaloriesKcal { get; init; }

    public List<DiaryEntryDto> Entries { get; init; } = [];
}

/// <summary>One line of the diary — one food, eaten once, at one meal.</summary>
public sealed class DiaryEntryDto
{
    public string Id { get; init; } = string.Empty;

    /// <summary>
    /// <c>Api.Planning.FoodBriefDto</c>, the same brief §7.6.1 sends for a
    /// dish in a plan. The two screens show the same card.
    /// </summary>
    public FoodBriefDto Food { get; init; } = new();

    public string MealType { get; init; } = string.Empty;

    /// <summary>
    /// Grams, derived from <c>portion_multiplier</c> and the food's standard
    /// serving. The column stores servings, not grams — see
    /// <c>db/schema.sql</c> on <c>food_diary.portion_multiplier</c>.
    /// </summary>
    public int ServingSizeG { get; init; }

    public decimal ActualCaloriesKcal { get; init; }

    /// <summary>
    /// Whether this food was in the user's own plan for this day and meal,
    /// matched on the natural key <c>(user_id, ate_on, meal_type,
    /// food_id)</c> — <c>idx_compliance</c>, and §8.4's join. There is no
    /// foreign key between the two tables on purpose.
    ///
    /// <para>It is also what tells the app which of the two deletes to
    /// offer: <c>true</c> means "I have not eaten this after all" and gives
    /// the dish back to the plan; <c>false</c> means "remove this line".
    /// </para>
    /// </summary>
    public bool FromMealPlan { get; init; }

    /// <summary>
    /// Whether the user has ever rated this food. §7.5.2's
    /// <c>myFeedback</c> is the rating itself.
    /// </summary>
    public bool HasFeedback { get; init; }

    /// <summary>
    /// <b>Not in the specification.</b> False once a rating exists that this
    /// line could be the evidence for, after which §7.7.3 and §7.7.4 both
    /// refuse it.
    ///
    /// <para>It is here because §7.8.1 tells the frontend to hide a button
    /// rather than let a user press it and read an error, and the same
    /// argument applies to a delete that is going to be refused. Without
    /// this field the app would have to work the rule out for itself from
    /// timestamps it is not given.</para>
    /// </summary>
    public bool Editable { get; init; }

    public DateTime CreatedAt { get; init; }
}

/// <summary>§7.7.2 — record something eaten.</summary>
public sealed class CreateDiaryEntryRequest
{
    [Required(ErrorMessage = "Thiếu mã món ăn")]
    public string? FoodId { get; init; }

    [Required(ErrorMessage = "Thiếu ngày ăn")]
    public DateOnly? AteOn { get; init; }

    [Required(ErrorMessage = "Thiếu bữa ăn")]
    [InEnum(nameof(Enums.MealType))]
    public string? MealType { get; init; }

    /// <summary>Grams. Omitted means one standard serving of the food.</summary>
    [Range(1, 5000, ErrorMessage = "Khối lượng phải từ 1 đến 5000 gam")]
    public int? ServingSizeG { get; init; }
}

/// <summary>
/// §7.7.3 — correct a line.
///
/// <para>Only the meal and the portion can change. <c>foodId</c> and
/// <c>ateOn</c> are accepted so a client can send the whole object back, but
/// they have to match what is stored: a different food or a different day is
/// a different eating, and changing them in place would move an existing
/// rating onto a dish the user never said anything about.</para>
/// </summary>
public sealed class UpdateDiaryEntryRequest
{
    public string? FoodId { get; init; }

    public DateOnly? AteOn { get; init; }

    [InEnum(nameof(Enums.MealType))]
    public string? MealType { get; init; }

    [Range(1, 5000, ErrorMessage = "Khối lượng phải từ 1 đến 5000 gam")]
    public int? ServingSizeG { get; init; }
}

/// <summary>§7.7.5 — one day against its limits.</summary>
public sealed class DiarySummaryResponse
{
    public DateOnly Date { get; init; }

    /// <summary>
    /// The limits that applied <b>on that day</b>: the snapshot in
    /// <c>meal_plans</c> when a plan exists for the date, and the stored
    /// <c>health_profiles</c> columns otherwise.
    ///
    /// <para><b>Read, never recomputed.</b> Step 1 already has three
    /// implementations held in parity, and recomputing here would invent a
    /// new answer for a past day — the day the user weighed 3 kg more.</para>
    /// </summary>
    public MacrosDto Targets { get; init; } = new();

    public MacrosDto Consumed { get; init; } = new();

    /// <summary>
    /// Target minus consumed, and <b>allowed to be negative</b>. Clamping it
    /// at zero would hide exactly what the screen exists to show.
    /// </summary>
    public MacrosDto Remaining { get; init; } = new();

    public ProgressPctDto ProgressPct { get; init; } = new();

    /// <summary>
    /// All four meals, in the order of the day, including the ones with
    /// nothing in them.
    /// </summary>
    public List<MealEnergyDto> ByMeal { get; init; } = [];

    /// <summary>
    /// Only the nutrients with a recommended intake for this user's sex and
    /// age band. Foods missing a figure are skipped rather than counted as
    /// zero, so every number here is a <b>lower bound</b>.
    /// </summary>
    public List<MicronutrientDto> Micronutrients { get; init; } = [];

    public PlanComplianceDto PlanCompliance { get; init; } = new();
}

public sealed class ProgressPctDto
{
    public decimal Calories { get; init; }
    public decimal Protein { get; init; }
    public decimal Carbs { get; init; }
    public decimal Fat { get; init; }
}

public sealed class MealEnergyDto
{
    public string MealType { get; init; } = string.Empty;
    public decimal CaloriesKcal { get; init; }

    /// <summary>
    /// The day's target times this meal's share — the same
    /// <c>NutritionTargets.MealShare</c> Step 4 splits by.
    /// </summary>
    public int TargetCaloriesKcal { get; init; }
}

public sealed class MicronutrientDto
{
    public string Nutrient { get; init; } = string.Empty;
    public string NameVi { get; init; } = string.Empty;
    public decimal Consumed { get; init; }
    public decimal Rda { get; init; }
    public decimal Pct { get; init; }
    public string Unit { get; init; } = string.Empty;
}

/// <summary>
/// §8.4's figure for one day: how much of what was suggested was actually
/// eaten.
/// </summary>
public sealed class PlanComplianceDto
{
    /// <summary>
    /// Every dish in the day's plan, <b>including</b> the ones that were
    /// replaced — §8.4 counts them and reports the replacement rate
    /// separately. Narrowing it here would make this endpoint disagree with
    /// the figure the report cites.
    /// </summary>
    public int SuggestedItems { get; init; }

    public int EatenItems { get; init; }

    /// <summary>
    /// <c>null</c> when there is no plan for the day. Zero would mean a plan
    /// the user ignored completely.
    /// </summary>
    public decimal? CompliancePct { get; init; }
}
