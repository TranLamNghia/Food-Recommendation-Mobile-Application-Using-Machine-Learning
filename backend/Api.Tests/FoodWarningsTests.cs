using Api.Catalogue;
using Api.Ml;

namespace Api.Tests;

/// <summary>
/// The sentence a user reads when a dish is not safe for them — §7.5.2.
///
/// <para>These are not tests of string formatting for its own sake. The
/// warning is the one place the system explains a safety decision to the
/// person it protects, and each case below is a way of explaining it wrongly:
/// stating a measurement the catalogue does not have, describing a floor as
/// a ceiling, or printing a tag name twice over.</para>
/// </summary>
public class FoodWarningsTests
{
    private static MlExclusionReason Reason(
        string ruleType = "nutrient_limit",
        string condition = "Tăng huyết áp",
        string? tag = null,
        string? nutrient = "sodium_mg",
        string? comparator = "lte",
        double? threshold = 600,
        double? value = 650,
        bool missingData = false)
        => new()
        {
            RuleType = ruleType,
            Condition = condition,
            SeverityMin = "mild",
            Tag = tag,
            Nutrient = nutrient,
            Comparator = comparator,
            Threshold = threshold,
            Value = value,
            MissingData = missingData,
            EvidenceLevel = "guideline",
            Citable = true,
        };

    [Fact]
    public void A_ceiling_the_food_went_over()
    {
        var message = FoodWarnings.Message(Reason());

        Assert.Equal(
            "Natri 650 mg vượt ngưỡng 600 mg mỗi khẩu phần (Tăng huyết áp)",
            message);
    }

    /// <summary>
    /// <c>gte</c> is a floor the food fell under. Saying "vượt ngưỡng" for
    /// both comparators would describe the opposite problem half the time.
    /// </summary>
    [Fact]
    public void A_floor_the_food_fell_under()
    {
        var message = FoodWarnings.Message(Reason(
            nutrient: "fiber_g", comparator: "gte", threshold: 5, value: 1.8,
            condition: "Táo bón"));

        Assert.Contains("thấp hơn ngưỡng", message);
        Assert.DoesNotContain("vượt ngưỡng", message);
        Assert.Contains("Chất xơ 1.8 g", message);
    }

    /// <summary>
    /// The case that matters most. F1 excludes a food whose figure is
    /// missing at a per-serving threshold, because it cannot be shown to be
    /// safe — and "Purin 0 mg vượt ngưỡng 150 mg" would be false twice over:
    /// the food's purine is unknown, not zero, and zero would not exceed
    /// anything.
    /// </summary>
    [Fact]
    public void A_missing_measurement_is_not_reported_as_zero()
    {
        var message = FoodWarnings.Message(Reason(
            nutrient: "purine_mg", threshold: 150, value: null,
            missingData: true, condition: "Gút"));

        Assert.Contains("Chưa có số liệu", message);
        Assert.Contains("purin", message);
        Assert.Contains("Gút", message);
        Assert.DoesNotContain("0", message);
        Assert.DoesNotContain("vượt ngưỡng", message);
    }

    /// <summary>
    /// A null value with <c>missingData</c> unset gets the same treatment:
    /// the two always travel together today, and trusting only the flag
    /// would print an empty number if they ever did not.
    /// </summary>
    [Fact]
    public void A_null_value_alone_is_enough_to_take_that_path()
    {
        var message = FoodWarnings.Message(Reason(
            value: null, missingData: false));

        Assert.Contains("Chưa có số liệu", message);
    }

    /// <summary>
    /// Tags are phrased as a statement already — "Có hải sản" — so a prefix
    /// verb produces "Món có có hải sản". The name is quoted instead, and
    /// kept in its own case.
    /// </summary>
    [Fact]
    public void A_tag_name_is_quoted_rather_than_glued_to_a_verb()
    {
        var message = FoodWarnings.Message(Reason(
            ruleType: "exclude_tag", tag: "Có hải sản",
            nutrient: null, comparator: null, threshold: null, value: null,
            condition: "Dị ứng hải sản"));

        Assert.DoesNotContain("có có", message);
        Assert.Contains("Có hải sản", message);
        Assert.Contains("Dị ứng hải sản", message);
    }

    [Fact]
    public void A_required_tag_the_food_lacks()
    {
        var message = FoodWarnings.Message(Reason(
            ruleType: "require_tag", tag: "Món chay",
            nutrient: null, comparator: null, threshold: null, value: null,
            condition: "Ăn chay"));

        Assert.Contains("không có nhãn", message);
        Assert.Contains("Món chay", message);
    }

    /// <summary>
    /// A rule type this version does not know still names the condition. The
    /// one thing the user must not lose is that the dish was flagged.
    /// </summary>
    [Fact]
    public void An_unknown_rule_type_still_names_the_condition()
    {
        var message = FoodWarnings.Message(Reason(ruleType: "something_new"));

        Assert.Contains("Tăng huyết áp", message);
        Assert.NotEmpty(message);
    }

    /// <summary>
    /// The figures arrive as decimals with two or three places. "Natri
    /// 650.00 mg" reads like a bug.
    /// </summary>
    [Fact]
    public void Whole_numbers_print_without_decimals()
    {
        Assert.Contains("650 mg", FoodWarnings.Message(Reason(value: 650.00)));
        Assert.Contains(
            "1.8 g",
            FoodWarnings.Message(Reason(
                nutrient: "fiber_g", value: 1.800, threshold: 5,
                comparator: "gte")));
    }

    /// <summary>
    /// Every nutrient the two ENUM columns allow has a Vietnamese name, or a
    /// warning would show the user a column name.
    /// </summary>
    [Theory]
    [InlineData("calories_kcal")]
    [InlineData("protein_g")]
    [InlineData("carbs_g")]
    [InlineData("fat_g")]
    [InlineData("fiber_g")]
    [InlineData("sugar_g")]
    [InlineData("sodium_mg")]
    [InlineData("cholesterol_mg")]
    [InlineData("purine_mg")]
    [InlineData("calcium_mg")]
    [InlineData("iron_mg")]
    [InlineData("zinc_mg")]
    [InlineData("vitamin_a_mcg")]
    [InlineData("vitamin_c_mg")]
    public void Every_nutrient_of_the_enum_has_a_name_and_a_unit(
        string nutrient)
    {
        Assert.NotEqual(nutrient, NutrientLabels.Name(nutrient));
        Assert.NotEmpty(NutrientLabels.Unit(nutrient));
    }

    [Fact]
    public void The_table_covers_the_enum_and_nothing_else()
    {
        Assert.Equal(14, NutrientLabels.Vi.Count);
    }

    /// <summary>
    /// A nutrient the table does not know returns the code itself: ugly on
    /// screen, which is how a missing row gets noticed, and never wrong.
    /// </summary>
    [Fact]
    public void An_unknown_nutrient_falls_back_to_its_code()
    {
        Assert.Equal("omega_3_g", NutrientLabels.Name("omega_3_g"));
        Assert.Empty(NutrientLabels.Unit("omega_3_g"));
    }
}
