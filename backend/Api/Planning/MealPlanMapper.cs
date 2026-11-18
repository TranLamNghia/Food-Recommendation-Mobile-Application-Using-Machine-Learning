using Api.Catalogue;
using Api.Data;
using Api.Entities;
using Api.Nutrition;
using Microsoft.EntityFrameworkCore;

namespace Api.Planning;

/// <summary>
/// Reads a stored plan and builds §7.6.1's response, and recomputes a plan's
/// totals after it changes.
///
/// <para>Shared by both meal-plan controllers because §7.6.1, §7.6.2, §7.6.3
/// and §7.6.5 all answer with <b>the whole plan</b> — a dish swap changes the
/// day's totals and its deviation, so returning only the changed dish would
/// leave the app showing a stale figure next to a fresh one.</para>
///
/// <para><b>A replaced dish does not count.</b> Every total here is summed
/// over items whose status is not <c>replaced</c>. That status means "this
/// was swapped out"; the row stays so that §4.6 can learn from the rejection,
/// but the food is not on the plate. Counting it would inflate the day's
/// energy by one dish per swap, and <c>calorie_deviation_pct</c> — the figure
/// the thesis proposal commits to — would drift upwards every time a user
/// changed their mind.</para>
/// </summary>
public static class MealPlanMapper
{
    /// <summary>The ±10 % of the proposal, as one number in one place.</summary>
    public const decimal ToleranceP = 10m;

    /// <summary>
    /// One dish's nutrition, already multiplied by its portion.
    /// </summary>
    private sealed record Portion(
        decimal Kcal,
        decimal ProteinG,
        decimal CarbsG,
        decimal FatG);

    public static async Task<MealPlanResponse> BuildAsync(
        AppDbContext db,
        MealPlans plan,
        List<NutrientViolationDto>? violations,
        CancellationToken ct = default)
    {
        var items = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan.Id)
            .ToListAsync(ct);

        // The replacements' foods too: a replaced dish shows what it became.
        var foodIds = items.Select(i => i.FoodId)
            .Concat(items.Where(i => i.ReplacedByFoodId is not null)
                         .Select(i => i.ReplacedByFoodId!))
            .Distinct()
            .ToList();
        var cards = await FoodCardReader.ReadAsync(db, foodIds, ct);
        var nutrition = await NutritionByFood(db, foodIds, ct);

        var meals = new List<MealDto>();
        foreach (var (mealType, share) in NutritionTargets.MealShare)
        {
            var ofMeal = items
                .Where(i => i.MealType == mealType)
                // `position` is what the plan builder decided; a null sorts
                // last rather than first, so a row written without one does
                // not jump to the top of the meal.
                .OrderBy(i => i.Position ?? byte.MaxValue)
                .ThenBy(i => i.Id, StringComparer.Ordinal)
                .ToList();

            meals.Add(new MealDto
            {
                MealType = mealType,
                TargetCaloriesKcal = (int)Math.Round(
                    plan.TargetCaloriesKcal * share,
                    MidpointRounding.AwayFromZero),
                ActualCaloriesKcal = ofMeal
                    .Where(Counts)
                    .Sum(i => PortionOf(i, nutrition)?.Kcal ?? 0m),
                Items = ofMeal
                    .Select(i => Item(i, cards, nutrition))
                    .ToList(),
            });
        }

        var deviation = plan.CalorieDeviationPct;

        return new MealPlanResponse
        {
            Id = plan.Id,
            PlanDate = plan.PlanDate,
            Status = plan.Status,
            GenerationSource = plan.GenerationSource,
            ModelVersion = plan.ModelId is null
                ? null
                : await db.MlModels
                    .Where(m => m.Id == plan.ModelId)
                    .Select(m => m.Version)
                    .FirstOrDefaultAsync(ct),
            Targets = new MacrosDto
            {
                CaloriesKcal = plan.TargetCaloriesKcal,
                ProteinG = plan.TargetProteinG,
                CarbsG = plan.TargetCarbsG,
                FatG = plan.TargetFatG,
            },
            Actuals = plan.ActualCaloriesKcal is null
                ? null
                : new MacrosDto
                {
                    CaloriesKcal = plan.ActualCaloriesKcal.Value,
                    ProteinG = plan.ActualProteinG ?? 0m,
                    CarbsG = plan.ActualCarbsG ?? 0m,
                    FatG = plan.ActualFatG ?? 0m,
                },
            CalorieDeviationPct = deviation,
            WithinTolerance = deviation is null
                ? null
                : Math.Abs(deviation.Value) <= ToleranceP,
            TotalPreferenceScore = plan.TotalPreferenceScore,
            ExplorationRatio = plan.ExplorationRatio,
            Meals = meals,
            NutrientViolations = violations,
            GeneratedAt = plan.GeneratedAt,
        };
    }

    /// <summary>
    /// Recomputes <c>actual_*</c> and <c>total_preference_score</c> from the
    /// rows that are currently on the plate, and writes them onto
    /// <paramref name="plan"/>.
    ///
    /// <para>Does <b>not</b> save: the caller is inside a transaction that
    /// also writes the item rows, and the two have to land together or not at
    /// all. A plan whose totals disagree with its dishes reports a deviation
    /// for a day that was never served.</para>
    ///
    /// <para><c>calorie_deviation_pct</c> is not written, because it cannot
    /// be: it is a <c>GENERATED ALWAYS … VIRTUAL</c> column. The caller
    /// reloads the row to read it back.</para>
    /// </summary>
    public static async Task RecomputeActualsAsync(
        AppDbContext db,
        MealPlans plan,
        CancellationToken ct = default)
    {
        var items = await db.MealPlanItems
            .Where(i => i.MealPlanId == plan.Id)
            .ToListAsync(ct);

        var nutrition = await NutritionByFood(
            db, items.Select(i => i.FoodId).Distinct().ToList(), ct);

        var onPlate = items.Where(Counts).ToList();
        var portions = onPlate
            .Select(i => PortionOf(i, nutrition))
            .Where(p => p is not null)
            .Select(p => p!)
            .ToList();

        // Rounded to each column's own scale. Writing more decimals than the
        // column holds lets MySQL do the rounding, and then the value this
        // process returns to the client differs from the one the next read
        // produces.
        plan.ActualCaloriesKcal = Round2(portions.Sum(p => p.Kcal));
        plan.ActualProteinG = Round2(portions.Sum(p => p.ProteinG));
        plan.ActualCarbsG = Round2(portions.Sum(p => p.CarbsG));
        plan.ActualFatG = Round2(portions.Sum(p => p.FatG));

        var scores = onPlate
            .Where(i => i.PredictedScore is not null)
            .Select(i => i.PredictedScore!.Value)
            .ToList();
        plan.TotalPreferenceScore = scores.Count == 0
            ? null
            : Math.Round(scores.Sum(), 4, MidpointRounding.AwayFromZero);
    }

    /// <summary>
    /// Whether this row is food on the plate rather than a record of a swap.
    /// </summary>
    public static bool Counts(MealPlanItems item)
        => item.Status != MealItemStatus.Replaced;

    /// <summary>
    /// What the day currently adds up to, summed from the dishes on the
    /// plate rather than read from <c>actual_calories_kcal</c>.
    ///
    /// <para>Used when judging a swap <b>before</b> it happens (§7.6.4).
    /// Derived rather than read because the stored column is <c>NULL</c> on a
    /// plan whose Step 4 never finished, and a missing total read as 0 would
    /// make every candidate look like it keeps the day inside ±10 %.</para>
    /// </summary>
    public static async Task<decimal> EnergyOnPlateAsync(
        AppDbContext db, string planId, CancellationToken ct = default)
    {
        var items = await db.MealPlanItems
            .Where(i => i.MealPlanId == planId)
            .ToListAsync(ct);
        var nutrition = await NutritionByFood(
            db, items.Select(i => i.FoodId).Distinct().ToList(), ct);
        return items
            .Where(Counts)
            .Sum(i => PortionOf(i, nutrition)?.Kcal ?? 0m);
    }

    /// <summary>
    /// <c>portion_multiplier</c> for a dish asked for in grams, clamped to
    /// what <c>chk_item_portion</c> allows.
    ///
    /// <para>Returns <c>null</c> when the request is outside 0.1 to 5
    /// servings. Clamping silently would serve a different amount than the
    /// user asked for while reporting success — and the amount is what the
    /// whole energy calculation rests on.</para>
    /// </summary>
    public static decimal? PortionFromGrams(int grams, int servingSizeG)
    {
        if (servingSizeG <= 0)
        {
            return null;
        }
        var multiplier = Math.Round(
            (decimal)grams / servingSizeG, 2, MidpointRounding.AwayFromZero);
        return multiplier is < 0.1m or > 5m ? null : multiplier;
    }

    /// <summary>
    /// Energy, protein, carbohydrate and fat per food, for one standard
    /// serving, plus that serving's weight.
    /// </summary>
    public static async Task<Dictionary<string, FoodNutrition>>
        NutritionByFood(
            AppDbContext db,
            IReadOnlyCollection<string> foodIds,
            CancellationToken ct = default)
    {
        if (foodIds.Count == 0)
        {
            return [];
        }
        var ids = foodIds.Distinct().ToList();
        return await db.FoodNutrition
            .Where(n => ids.Contains(n.FoodId))
            .ToDictionaryAsync(n => n.FoodId, ct);
    }

    private static Portion? PortionOf(
        MealPlanItems item, Dictionary<string, FoodNutrition> nutrition)
    {
        // A dish whose food has no nutrition row contributes nothing and is
        // NOT counted as zero: `FoodCardReader` drops such a food from the
        // response too, so the day's total and the dishes shown agree with
        // each other. The hole is in the catalogue, and it is logged where
        // the plan is built.
        if (!nutrition.TryGetValue(item.FoodId, out var n))
        {
            return null;
        }
        var m = item.PortionMultiplier;
        return new Portion(
            n.CaloriesKcal * m, n.ProteinG * m, n.CarbsG * m, n.FatG * m);
    }

    private static MealItemDto Item(
        MealPlanItems item,
        Dictionary<string, FoodCard> cards,
        Dictionary<string, FoodNutrition> nutrition)
    {
        var serving = nutrition.TryGetValue(item.FoodId, out var n)
            ? (int)Math.Round(
                n.ServingSizeG * item.PortionMultiplier,
                MidpointRounding.AwayFromZero)
            : 0;

        return new MealItemDto
        {
            Id = item.Id,
            Food = Brief(item.FoodId, cards),
            ServingSizeG = serving,
            PredictedScore = item.PredictedScore,
            Status = item.Status,
            ReplacedByFood = item.ReplacedByFoodId is null
                ? null
                : Brief(item.ReplacedByFoodId, cards),
            ExplorationDelta = item.ExplorationDelta,
            Position = item.Position,
        };
    }

    public static FoodBriefDto Brief(
        string foodId, Dictionary<string, FoodCard> cards)
        => cards.TryGetValue(foodId, out var c)
            ? new FoodBriefDto
            {
                Id = c.Id,
                Name = c.Name,
                ImageUrl = c.ImageUrl,
                CategoryName = c.CategoryName,
                DishRole = c.DishRole,
                CaloriesKcal = c.CaloriesKcal,
            }
            // The id alone, rather than an exception: a food deactivated
            // after the plan was built still has to come back, because the
            // user is looking at a plan that contains it.
            : new FoodBriefDto { Id = foodId };

    private static decimal Round2(decimal v)
        => Math.Round(v, 2, MidpointRounding.AwayFromZero);
}
