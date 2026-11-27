using System.ComponentModel.DataAnnotations;
using Api.Catalogue;

namespace Api.Tests;

/// <summary>
/// The body rules of §7.5.3. The endpoint itself — ownership, the duplicate
/// name, the tags, the F1 answer — runs against MySQL in
/// <c>tools/smoke_backend.py</c>.
/// </summary>
public class CreateFoodTests
{
    private static CreateFoodRequest Valid(
        CreateFoodNutrition? nutrition = null,
        string name = "Bánh canh cua nhà nấu",
        int? serving = 450,
        int? spice = 1,
        string? role = "main")
        => new()
        {
            Name = name,
            CategoryId = "00000007-0000-4000-8000-000000000000",
            DishRole = role,
            ServingSizeG = serving,
            SpiceLevel = spice,
            Nutrition = nutrition ?? new CreateFoodNutrition { Calories = 480 },
        };

    /// <summary>
    /// What MVC does: the body, then each nested object. Validator alone does
    /// not descend into <see cref="CreateFoodRequest.Nutrition"/>.
    /// </summary>
    private static List<ValidationResult> Validate(CreateFoodRequest req)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(
            req, new ValidationContext(req), results,
            validateAllProperties: true);
        if (req.Nutrition is { } n)
        {
            Validator.TryValidateObject(
                n, new ValidationContext(n), results,
                validateAllProperties: true);
        }
        return results;
    }

    [Fact]
    public void Calories_alone_is_enough()
        => Assert.Empty(Validate(Valid()));

    [Theory]
    [InlineData(0)]
    [InlineData(-5)]
    [InlineData(0.001)]   // rounds to 0.00 in DECIMAL(7,2)
    [InlineData(5000.01)]
    public void Calories_must_be_above_zero_and_sane(double kcal)
        => Assert.NotEmpty(Validate(Valid(
            new CreateFoodNutrition { Calories = (decimal)kcal })));

    [Fact]
    public void Calories_are_required()
        => Assert.NotEmpty(Validate(Valid(new CreateFoodNutrition())));

    [Fact]
    public void A_negative_nutrient_is_refused()
        => Assert.NotEmpty(Validate(Valid(new CreateFoodNutrition
        {
            Calories = 480,
            SodiumMg = -1,
        })));

    [Theory]
    [InlineData(-1)]
    [InlineData(4)]
    public void Spice_runs_zero_to_three(int spice)
        => Assert.NotEmpty(Validate(Valid(spice: spice)));

    [Fact]
    public void Spice_may_be_left_out()
        => Assert.Empty(Validate(Valid(spice: null)));

    [Theory]
    [InlineData(0)]
    [InlineData(5001)]
    public void A_serving_has_a_real_weight(int grams)
        => Assert.NotEmpty(Validate(Valid(serving: grams)));

    [Theory]
    [InlineData("A")]
    [InlineData("")]
    public void A_name_has_two_characters_at_least(string name)
        => Assert.NotEmpty(Validate(Valid(name: name)));

    [Fact]
    public void A_name_is_capped_at_the_column_width()
        => Assert.NotEmpty(Validate(Valid(name: new string('a', 201))));

    [Fact]
    public void The_role_is_one_of_the_seven()
    {
        Assert.NotEmpty(Validate(Valid(role: "breakfast")));
        Assert.NotEmpty(Validate(Valid(role: null)));
        Assert.Empty(Validate(Valid(role: "side_veg")));
    }
}
