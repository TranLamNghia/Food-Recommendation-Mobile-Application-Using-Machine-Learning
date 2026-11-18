using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Nutrition;
using Api.Planning;
using Api.Profile;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

namespace Api.Tests;

/// <summary>
/// The meal plan's pure parts — specification §7.6.
///
/// <para>Three things are checked here, and each one is a way the stored plan
/// could quietly stop meaning what it says: a replaced dish counted as food,
/// a portion in grams silently clamped to something the user did not ask
/// for, and a client allowed to set a status that only the system may
/// set.</para>
/// </summary>
public class MealPlanMapperTests
{
    private static MealPlanItems Item(
        string status = MealItemStatus.Suggested)
        => new()
        {
            Id = Guid.NewGuid().ToString(),
            MealPlanId = "plan",
            FoodId = "food",
            MealType = "lunch",
            PortionMultiplier = 1.00m,
            Status = status,
        };

    /// <summary>
    /// A replaced dish is history, not food. Counting it would add one
    /// dish's energy to the day on every swap, and
    /// <c>calorie_deviation_pct</c> — the figure the thesis proposal commits
    /// to — would drift upwards every time a user changed their mind.
    /// </summary>
    [Fact]
    public void A_replaced_dish_does_not_count_towards_the_day()
    {
        Assert.False(MealPlanMapper.Counts(Item(MealItemStatus.Replaced)));
    }

    [Theory]
    [InlineData(MealItemStatus.Suggested)]
    [InlineData(MealItemStatus.Kept)]
    [InlineData(MealItemStatus.Eaten)]
    [InlineData(MealItemStatus.Skipped)]
    public void Every_other_status_is_food_on_the_plate(string status)
    {
        // `skipped` included, deliberately: the plan's totals describe what
        // was PLANNED for the day. What was actually eaten is `food_diary`,
        // and §8.4's compliance query is what compares the two.
        Assert.True(MealPlanMapper.Counts(Item(status)));
    }

    [Fact]
    public void A_portion_in_grams_becomes_a_multiple_of_one_serving()
    {
        Assert.Equal(1.00m, MealPlanMapper.PortionFromGrams(200, 200));
        Assert.Equal(1.25m, MealPlanMapper.PortionFromGrams(250, 200));
        Assert.Equal(0.50m, MealPlanMapper.PortionFromGrams(100, 200));
    }

    /// <summary>
    /// Outside <c>chk_item_portion</c> the answer is <c>null</c> — a refusal
    /// — and not a clamp. Clamping would serve a different amount than the
    /// user asked for while reporting success, and the amount is what the
    /// whole energy calculation rests on.
    /// </summary>
    [Theory]
    [InlineData(10, 200)]     // 0.05 servings, under the 0.1 floor
    [InlineData(2000, 200)]   // 10 servings, over the 5 ceiling
    public void A_portion_outside_what_the_schema_allows_is_refused(
        int grams, int servingSizeG)
    {
        Assert.Null(MealPlanMapper.PortionFromGrams(grams, servingSizeG));
    }

    [Fact]
    public void A_food_with_no_serving_weight_cannot_be_portioned()
    {
        Assert.Null(MealPlanMapper.PortionFromGrams(200, 0));
    }

    /// <summary>
    /// The ±10 % lives in one place. Two copies of it would eventually
    /// disagree, and then <c>withinTolerance</c> and the candidate list's
    /// <c>keepsWithinTolerance</c> would answer differently about the same
    /// day.
    /// </summary>
    [Fact]
    public void The_tolerance_is_the_ten_percent_of_the_proposal()
    {
        Assert.Equal(10m, MealPlanMapper.ToleranceP);
    }
}

/// <summary>
/// Which statuses a client may set — §7.6.6.
/// </summary>
public class MealItemStatusTests
{
    /// <summary>
    /// The subset has to stay inside the column's ENUM.
    /// <c>tools/gen_entities.py</c> compares <see cref="Enums.MealItemStatus"/>
    /// against <c>db/schema.sql</c>, so this test plus that check means a
    /// value MySQL would refuse cannot survive both.
    /// </summary>
    [Fact]
    public void Client_settable_statuses_are_all_real_enum_values()
    {
        Assert.All(
            MealItemStatus.ClientSettable,
            s => Assert.Contains(s, Enums.MealItemStatus));
    }

    /// <summary>
    /// <c>suggested</c> and <c>replaced</c> are statements about what the
    /// SYSTEM did, and §4.6 computes label weights from them. A client able
    /// to send either could relabel its own training data.
    /// </summary>
    [Fact]
    public void The_two_system_statuses_are_not_client_settable()
    {
        Assert.DoesNotContain(
            MealItemStatus.Suggested, MealItemStatus.ClientSettable);
        Assert.DoesNotContain(
            MealItemStatus.Replaced, MealItemStatus.ClientSettable);
    }

    [Fact]
    public void Exactly_the_three_of_the_specification()
    {
        Assert.Equal(
            ["kept", "eaten", "skipped"], MealItemStatus.ClientSettable);
    }
}

/// <summary>
/// The four meals, and their shares of the day.
/// </summary>
public class MealShareTests
{
    /// <summary>
    /// The shares have to add up to the whole day, or a plan assembled from
    /// four meals could never reach its target no matter how well Step 4
    /// worked.
    /// </summary>
    [Fact]
    public void The_four_shares_add_up_to_one()
    {
        Assert.Equal(1.0m, NutritionTargets.MealShare.Values.Sum());
    }

    /// <summary>
    /// The response lists the meals in the order of
    /// <c>Enums.MealType</c>, which has to be the order of
    /// <c>NutritionTargets.MealShare</c> — the mapper walks the latter. If
    /// the two drifted apart, a response would list the meals in one order
    /// while <c>mealTypes</c> validation used another.
    /// </summary>
    [Fact]
    public void The_meal_order_is_the_same_on_both_sides()
    {
        Assert.Equal(
            Enums.MealType, NutritionTargets.MealShare.Keys.ToArray());
    }
}

/// <summary>
/// §7.6's two "you have a step to complete first" answers.
/// </summary>
public class MlPlanFailureTests
{
    private const string Trace = "trace-plan";

    private static MlFailure Failure(MlFailureKind kind)
        => new(kind, 422, null, "developer-facing detail");

    /// <summary>
    /// Both of these come back from <c>/plan</c> as <c>422</c> and must
    /// <b>not</b> become <c>ML_UNAVAILABLE</c>: nothing is unavailable, the
    /// user simply has no energy target yet. Told to "try again later" they
    /// would retry forever on a screen that can never succeed.
    /// </summary>
    [Theory]
    [InlineData(MlFailureKind.ProfileRequired, ErrorCode.ProfileRequired)]
    [InlineData(MlFailureKind.OnboardingRequired,
                ErrorCode.OnboardingRequired)]
    public void A_missing_profile_is_a_409_not_an_outage(
        MlFailureKind kind, string expectedCode)
    {
        var failure = Failure(kind);
        var result = failure.ToActionResult(Trace);
        var body = Assert.IsType<ApiError>(result.Value);

        Assert.False(failure.IsDegradable);
        Assert.False(failure.IsSystemFault());
        Assert.Equal(StatusCodes.Status409Conflict, result.StatusCode);
        Assert.Equal(expectedCode, body.Error.Code);
        Assert.NotEqual(ErrorCode.MlUnavailable, body.Error.Code);
        Assert.Equal(Trace, body.Error.TraceId);
    }
}
