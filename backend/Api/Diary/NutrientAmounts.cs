using Api.Entities;

namespace Api.Diary;

/// <summary>
/// How to read each nutrient of the ENUM off a <c>food_nutrition</c> row.
///
/// <para>The vocabulary is the one <c>condition_rules.nutrient</c> and
/// <c>rda_reference.nutrient</c> share — the same fourteen names in both, and
/// the same fourteen <c>Api.Catalogue.NutrientLabels</c> gives Vietnamese
/// words to. Keeping the lookup here rather than inside the controller is
/// what lets <c>backend/Api.Tests</c> assert the table is complete: a
/// nutrient the recommended-intake table knows and this one does not is
/// silently dropped from §7.7.5's answer, with no error anywhere.</para>
///
/// <para>The ten nullable ones return <c>null</c> rather than zero when the
/// catalogue has no figure, which is what makes the day's totals an honest
/// lower bound instead of a number that counts missing data as nothing.</para>
/// </summary>
public static class NutrientAmounts
{
    /// <summary>
    /// The four §7.7.5 already reports as <c>targets</c> and
    /// <c>consumed</c>. They are left out of <c>micronutrients</c> so the
    /// same figure is not sent twice under two names.
    /// </summary>
    public static readonly string[] Macros =
        ["calories_kcal", "protein_g", "carbs_g", "fat_g"];

    public static readonly
        IReadOnlyDictionary<string, Func<FoodNutrition, decimal?>> Vocabulary =
            new Dictionary<string, Func<FoodNutrition, decimal?>>
            {
                ["calories_kcal"] = n => n.CaloriesKcal,
                ["protein_g"] = n => n.ProteinG,
                ["carbs_g"] = n => n.CarbsG,
                ["fat_g"] = n => n.FatG,
                ["fiber_g"] = n => n.FiberG,
                ["sugar_g"] = n => n.SugarG,
                ["sodium_mg"] = n => n.SodiumMg,
                ["cholesterol_mg"] = n => n.CholesterolMg,
                ["purine_mg"] = n => n.PurineMg,
                ["calcium_mg"] = n => n.CalciumMg,
                ["iron_mg"] = n => n.IronMg,
                ["zinc_mg"] = n => n.ZincMg,
                ["vitamin_a_mcg"] = n => n.VitaminAMcg,
                ["vitamin_c_mg"] = n => n.VitaminCMg,
            };

    /// <summary>
    /// The figure, or <c>null</c> when the catalogue does not have it — and
    /// <c>null</c> as well for a nutrient this table does not know, which is
    /// how a column added to the ENUM and not here shows up as missing data
    /// rather than as a crash.
    /// </summary>
    public static decimal? Of(string nutrient, FoodNutrition row)
        => Vocabulary.TryGetValue(nutrient, out var read) ? read(row) : null;

    public static bool IsMacro(string nutrient)
        => Macros.Contains(nutrient);
}
