using System.ComponentModel.DataAnnotations;
using Api.Catalogue;
using Api.Diary;
using Api.Entities;
using Api.Onboarding;
using Api.Profile;

namespace Api.Tests;

/// <summary>
/// The nutrient vocabulary §7.7.5 sums the day with.
///
/// <para>The table lives in <c>NutrientAmounts</c> rather than inside the
/// controller for exactly these tests. A nutrient that the recommended-intake
/// table knows and this one does not is <b>silently skipped</b> — the summary
/// screen would be missing a row with no error raised anywhere, which is the
/// kind of gap only an assertion finds.</para>
/// </summary>
public class NutrientAmountsTests
{
    private static FoodNutrition Row(
        decimal calories = 200m,
        decimal? calcium = 120m,
        decimal? purine = null)
        => new()
        {
            Id = "n1",
            FoodId = "f1",
            ServingSizeG = 150,
            CaloriesKcal = calories,
            ProteinG = 10m,
            CarbsG = 30m,
            FatG = 5m,
            CalciumMg = calcium,
            PurineMg = purine,
        };

    /// <summary>
    /// The two tables that name nutrients have to name the <b>same</b> ones:
    /// this one reads the figure, <c>NutrientLabels</c> gives it a Vietnamese
    /// word, and §7.7.5 needs both for every row it shows. Either table
    /// growing alone is the failure this catches.
    /// </summary>
    [Fact]
    public void The_vocabulary_matches_the_label_table_exactly()
    {
        Assert.Equal(
            NutrientLabels.Vi.Keys.OrderBy(k => k, StringComparer.Ordinal),
            NutrientAmounts.Vocabulary.Keys.OrderBy(
                k => k, StringComparer.Ordinal));
    }

    [Fact]
    public void The_fourteen_of_the_enum_and_nothing_else()
    {
        Assert.Equal(14, NutrientAmounts.Vocabulary.Count);
    }

    [Fact]
    public void Every_macro_can_be_read()
    {
        foreach (var macro in NutrientAmounts.Macros)
        {
            Assert.True(
                NutrientAmounts.Vocabulary.ContainsKey(macro),
                $"`{macro}` is reported as a macro but cannot be read");
        }
    }

    [Fact]
    public void The_four_macros_are_the_four_of_the_summary()
    {
        Assert.Equal(
            new[] { "calories_kcal", "carbs_g", "fat_g", "protein_g" },
            NutrientAmounts.Macros.OrderBy(m => m, StringComparer.Ordinal));
    }

    [Fact]
    public void A_measured_figure_comes_back()
    {
        Assert.Equal(120m, NutrientAmounts.Of("calcium_mg", Row()));
        Assert.Equal(200m, NutrientAmounts.Of("calories_kcal", Row()));
    }

    /// <summary>
    /// The distinction the whole summary rests on. A food with no purine
    /// figure must not contribute zero, because zero is a measurement and
    /// this is the absence of one — §7.7.5 calls its totals a lower bound on
    /// the strength of that difference.
    /// </summary>
    [Fact]
    public void A_missing_figure_is_null_and_not_zero()
    {
        var amount = NutrientAmounts.Of("purine_mg", Row(purine: null));

        Assert.Null(amount);
        Assert.NotEqual(0m, amount);
    }

    /// <summary>
    /// Zero is kept as zero, in the other direction: a savoury dish really
    /// does have 0 g of sugar, and turning that into "no data" would be the
    /// same error read backwards.
    /// </summary>
    [Fact]
    public void A_measured_zero_stays_zero()
    {
        Assert.Equal(0m, NutrientAmounts.Of("calcium_mg", Row(calcium: 0m)));
    }

    /// <summary>
    /// A nutrient added to the database ENUM and not to this table reads as
    /// missing rather than throwing. The summary then leaves that row out,
    /// which <see cref="The_vocabulary_matches_the_label_table_exactly"/> is
    /// there to catch at build time.
    /// </summary>
    [Fact]
    public void A_nutrient_this_table_does_not_know_reads_as_missing()
    {
        Assert.Null(NutrientAmounts.Of("omega_3_g", Row()));
    }

    [Fact]
    public void Only_the_macros_are_macros()
    {
        Assert.True(NutrientAmounts.IsMacro("protein_g"));
        Assert.False(NutrientAmounts.IsMacro("calcium_mg"));
        Assert.False(NutrientAmounts.IsMacro("omega_3_g"));
    }
}

/// <summary>
/// <c>[InEnum]</c> and the field that may be left out.
///
/// <para>Every use of the attribute until now sat next to a
/// <c>[Required]</c>, so a null never reached it and the fact that it refused
/// one went unnoticed. <c>ConditionChoiceDto.Severity</c> is declared
/// <c>string?</c> and is the first optional one: before the fix, a client
/// that omitted the severity was told its request was invalid, with a message
/// listing the three values the field could have had.</para>
/// </summary>
public class InEnumTests
{
    private static List<ValidationResult> Validate(object instance)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(
            instance, new ValidationContext(instance), results,
            validateAllProperties: true);
        return results;
    }

    [Fact]
    public void A_value_in_the_list_passes()
    {
        var attribute = new InEnumAttribute(nameof(Enums.Severity));

        Assert.True(attribute.IsValid("mild"));
    }

    [Fact]
    public void A_value_outside_the_list_is_refused()
    {
        var attribute = new InEnumAttribute(nameof(Enums.Severity));

        Assert.False(attribute.IsValid("enormous"));
    }

    /// <summary>
    /// Presence is <c>[Required]</c>'s question. This is how <c>[Range]</c>
    /// and <c>[StringLength]</c> behave, and the only way an optional ENUM
    /// field can exist.
    /// </summary>
    [Fact]
    public void A_null_passes_because_presence_is_a_different_question()
    {
        var attribute = new InEnumAttribute(nameof(Enums.Severity));

        Assert.True(attribute.IsValid(null));
    }

    [Fact]
    public void Something_that_is_not_a_string_is_still_refused()
    {
        var attribute = new InEnumAttribute(nameof(Enums.Severity));

        Assert.False(attribute.IsValid(7));
    }

    [Fact]
    public void A_list_name_that_does_not_exist_fails_at_construction()
    {
        Assert.Throws<ArgumentException>(
            () => new InEnumAttribute("NotAList"));
    }

    /// <summary>The regression itself, through the real DTO.</summary>
    [Fact]
    public void A_condition_without_a_severity_is_accepted()
    {
        var choice = new ConditionChoiceDto { ConditionId = 3 };

        Assert.Empty(Validate(choice));
    }

    [Fact]
    public void A_condition_with_a_made_up_severity_is_not()
    {
        var choice = new ConditionChoiceDto
        {
            ConditionId = 3,
            Severity = "enormous",
        };

        var problems = Validate(choice);

        Assert.Single(problems);
        Assert.Contains("mild", problems[0].ErrorMessage);
    }

    /// <summary>
    /// §7.7.3's body is all optional — a client correcting only the portion
    /// sends only the portion, and the meal it does not mention must not be
    /// read as an empty one.
    /// </summary>
    [Fact]
    public void A_diary_edit_may_carry_the_portion_alone()
    {
        var edit = new UpdateDiaryEntryRequest { ServingSizeG = 75 };

        Assert.Empty(Validate(edit));
    }

    [Fact]
    public void A_diary_entry_still_needs_its_three_required_fields()
    {
        var problems = Validate(new CreateDiaryEntryRequest());

        Assert.Equal(3, problems.Count);
    }
}

/// <summary>
/// The <c>decimal</c> fields with a range, and the rounding that let bad
/// values through.
///
/// <para><c>[Range(20, 300)]</c> picks <c>RangeAttribute(int, int)</c>, which
/// converts the value to <c>int</c> before comparing. A weight of
/// <c>19.6</c> became <c>20</c> and passed — then <c>chk_weight</c> in MySQL
/// refused the insert, and the user got <c>500 INTERNAL_ERROR</c> instead of
/// a message naming the field. The bounds are typed <c>decimal</c> now, and
/// these tests are what stop the integer form coming back.</para>
///
/// <para>Found by driving the real server from the Flutter app's own
/// client: a height of <c>49.6</c> cm answered <c>500</c>.</para>
/// </summary>
public class ProfileRangeTests
{
    private static UpsertProfileRequest Request(
        decimal heightCm = 172m,
        decimal weightKg = 68.5m)
        => new()
        {
            Gender = "male",
            DateOfBirth = new DateOnly(2004, 11, 4),
            HeightCm = heightCm,
            WeightKg = weightKg,
            ActivityLevel = "moderate",
            Goal = "maintain",
        };

    private static List<ValidationResult> Validate(object instance)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(
            instance, new ValidationContext(instance), results,
            validateAllProperties: true);
        return results;
    }

    /// <summary>
    /// The exact values that used to slip through, one tenth inside the
    /// bound the database enforces.
    /// </summary>
    [Theory]
    [InlineData(49.6, 68.5)]
    [InlineData(250.4, 68.5)]
    [InlineData(172, 19.6)]
    [InlineData(172, 300.4)]
    public void A_fraction_outside_the_bound_is_refused_here_not_by_mysql(
        double heightCm, double weightKg)
    {
        var problems = Validate(
            Request((decimal)heightCm, (decimal)weightKg));

        Assert.NotEmpty(problems);
    }

    [Theory]
    [InlineData(50, 20)]
    [InlineData(250, 300)]
    [InlineData(172.5, 68.5)]
    public void And_the_bounds_themselves_are_still_allowed(
        double heightCm, double weightKg)
    {
        var problems = Validate(
            Request((decimal)heightCm, (decimal)weightKg));

        Assert.Empty(problems);
    }
}
