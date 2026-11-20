using Api.Ml;

namespace Api.Catalogue;

/// <summary>
/// The Vietnamese names and units of the fourteen nutrients the project
/// measures.
///
/// <para>The vocabulary is <c>condition_rules.nutrient</c> and
/// <c>rda_reference.nutrient</c> — the same ENUM in both, deliberately, so a
/// rule and a recommended intake can be compared without a translation
/// table. The Vietnamese words match
/// <c>mobile/lib/features/plan/widgets/day_budget_card.dart</c>, which has
/// its own copy for the offline screens; they are display labels, so the
/// cost of them differing is a word on screen rather than a wrong
/// number.</para>
/// </summary>
public static class NutrientLabels
{
    /// <summary>{code: (Vietnamese name, unit)}.</summary>
    public static readonly IReadOnlyDictionary<string, (string Name, string Unit)>
        Vi = new Dictionary<string, (string, string)>
        {
            ["calories_kcal"] = ("Năng lượng", "kcal"),
            ["protein_g"] = ("Đạm", "g"),
            ["carbs_g"] = ("Bột đường", "g"),
            ["fat_g"] = ("Chất béo", "g"),
            ["fiber_g"] = ("Chất xơ", "g"),
            ["sugar_g"] = ("Đường", "g"),
            ["sodium_mg"] = ("Natri", "mg"),
            ["cholesterol_mg"] = ("Cholesterol", "mg"),
            ["purine_mg"] = ("Purin", "mg"),
            ["calcium_mg"] = ("Canxi", "mg"),
            ["iron_mg"] = ("Sắt", "mg"),
            ["zinc_mg"] = ("Kẽm", "mg"),
            ["vitamin_a_mcg"] = ("Vitamin A", "mcg"),
            ["vitamin_c_mg"] = ("Vitamin C", "mg"),
        };

    /// <summary>
    /// The name, or the code itself when it is one this table does not know.
    /// Returning the code is deliberate: it is ugly on screen, which is how
    /// a missing row gets noticed, and it is never wrong.
    /// </summary>
    public static string Name(string? nutrient)
        => nutrient is not null && Vi.TryGetValue(nutrient, out var v)
            ? v.Name
            : nutrient ?? string.Empty;

    public static string Unit(string? nutrient)
        => nutrient is not null && Vi.TryGetValue(nutrient, out var v)
            ? v.Unit
            : string.Empty;
}

/// <summary>
/// Turns one F1 exclusion into the sentence a user reads — §7.5.2's
/// <c>warnings</c>.
///
/// <para>The ML service sends the parts: which rule, which condition, which
/// nutrient, the threshold and the food's own measurement. The words are
/// written here, because this is the layer that talks to the user. Pure, so
/// <c>backend/Api.Tests</c> can state what each kind of rule should say
/// without a database.</para>
///
/// <para><b>The case worth getting right</b> is a missing measurement. The
/// F1 filter excludes a food whose figure is absent at a per-serving
/// threshold, because it cannot be shown to be safe — and telling the user
/// "Purin 0 mg vượt ngưỡng 150 mg" would be false twice over. That case gets
/// its own sentence.</para>
/// </summary>
public static class FoodWarnings
{
    public static string Message(MlExclusionReason reason)
    {
        var condition = reason.Condition;

        switch (reason.RuleType)
        {
            // The tag name is quoted and not lower-cased. Tags are phrased
            // as a statement already — "Có hải sản" — so "Món có có hải
            // sản" is what a prefix verb produces. Quoting keeps the name
            // intact and reads as the label it is.
            case "exclude_tag":
                return reason.Tag is { Length: > 0 } tag
                    ? $"Món có nhãn “{tag}”, không phù hợp với "
                      + $"{condition}"
                    : $"Món không phù hợp với {condition}";

            case "require_tag":
                return reason.Tag is { Length: > 0 } needed
                    ? $"Món không có nhãn “{needed}”, không phù "
                      + $"hợp với {condition}"
                    : $"Món không phù hợp với {condition}";

            case "nutrient_limit":
                return NutrientMessage(reason, condition);

            default:
                // A rule type this version does not know. The condition is
                // still named, because the one thing the user must not lose
                // is that the dish was flagged at all.
                return $"Món không phù hợp với {condition}";
        }
    }

    private static string NutrientMessage(
        MlExclusionReason reason, string condition)
    {
        var name = NutrientLabels.Name(reason.Nutrient);
        var unit = NutrientLabels.Unit(reason.Nutrient);

        if (reason.MissingData || reason.Value is null)
        {
            // Not "0 mg". The figure is unknown, and F1 excluded the food
            // for that reason alone.
            return $"Chưa có số liệu {name.ToLowerInvariant()} của món này, "
                + $"nên không thể khẳng định là an toàn với {condition}";
        }

        var value = Number(reason.Value.Value);
        if (reason.Threshold is null)
        {
            return $"{name} {value} {unit} không phù hợp với {condition}";
        }

        var threshold = Number(reason.Threshold.Value);
        // `lte` is a ceiling the food went over; `gte` is a floor it fell
        // under. Saying "vượt ngưỡng" for both would describe the opposite
        // problem half the time.
        var verb = reason.Comparator == "gte"
            ? "thấp hơn ngưỡng"
            : "vượt ngưỡng";

        return $"{name} {value} {unit} {verb} {threshold} {unit} mỗi khẩu "
            + $"phần ({condition})";
    }

    /// <summary>
    /// A figure with no trailing zeros: 650 rather than 650.00, and 1.8 as
    /// 1.8. The numbers come from the database as decimals with two or three
    /// places, and a sentence reading "Natri 650.00 mg" looks like a bug.
    /// </summary>
    private static string Number(double value)
        => value == Math.Floor(value)
            ? ((long)value).ToString(
                System.Globalization.CultureInfo.InvariantCulture)
            : value.ToString(
                "0.###", System.Globalization.CultureInfo.InvariantCulture);
}
