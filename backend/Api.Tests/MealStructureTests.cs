using Api.Planning;

namespace Api.Tests;

/// <summary>
/// Which roles a day cannot be assembled without, and how that is said in
/// Vietnamese.
///
/// <para>These back one decision: the refusal to let a user block the last
/// dish left in a role some meal requires. Getting the role set wrong fails
/// in both directions, and both are bad — too wide and the user is refused
/// over a soup nobody needs, too narrow and the plan builder is handed a day
/// it cannot build and answers <c>NO_FEASIBLE_PLAN</c> with no explanation
/// the user can act on.</para>
///
/// <para>The arrays themselves are audited against the ML service's
/// <c>MEAL_STRUCTURE</c> by section 15 of <c>tools/check_step4.py</c>. What
/// is checked here is what this side derives from them.</para>
/// </summary>
public class MealStructureTests
{
    [Fact]
    public void The_required_roles_are_the_four_a_day_needs()
    {
        Assert.Equal(
            ["main", "side_protein", "side_veg", "snack"],
            MealStructure.RequiredRoles);
    }

    /// <summary>
    /// <c>soup</c> is the role the split exists for. It appears in lunch, so
    /// a filter built on the plain arrays would call it needed; it is
    /// lunch's <b>optional</b> serving, so a catalogue with no soup left
    /// still assembles a day.
    /// </summary>
    [Fact]
    public void Soup_is_not_required_by_any_meal()
    {
        Assert.Contains("soup", MealStructure.Lunch);
        Assert.DoesNotContain("soup", MealStructure.RequiredRoles);
        Assert.Empty(MealStructure.MealsRequiring("soup"));
    }

    /// <summary>
    /// The two roles no meal asks for at all. Blocking the last dessert can
    /// break nothing, because nothing is built from desserts.
    /// </summary>
    [Theory]
    [InlineData("dessert")]
    [InlineData("drink")]
    public void An_unused_role_is_required_by_no_meal(string role)
    {
        Assert.Empty(MealStructure.MealsRequiring(role));
    }

    [Fact]
    public void Main_is_required_by_three_meals_in_the_order_of_the_day()
    {
        Assert.Equal(
            ["breakfast", "lunch", "dinner"],
            MealStructure.MealsRequiring("main"));
    }

    [Theory]
    [InlineData("side_protein", "lunch")]
    [InlineData("side_veg", "dinner")]
    [InlineData("snack", "snack")]
    public void The_other_three_roles_each_hold_up_one_meal(
        string role, string meal)
    {
        Assert.Equal([meal], MealStructure.MealsRequiring(role));
    }

    /// <summary>
    /// Breakfast's <c>snack</c> serving is optional, so losing every snack
    /// costs the snack meal and leaves breakfast standing. The plain array
    /// cannot tell the two apart, which is the whole reason for the split.
    /// </summary>
    [Fact]
    public void Breakfast_can_do_without_its_snack()
    {
        Assert.Contains("snack", MealStructure.Breakfast);
        Assert.DoesNotContain("breakfast", MealStructure.MealsRequiring("snack"));
    }

    [Fact]
    public void A_role_that_does_not_exist_breaks_nothing_and_throws_nothing()
    {
        Assert.Empty(MealStructure.MealsRequiring("not_a_role"));
    }
}

/// <summary>
/// The Vietnamese names of the meals, and how a list of them is joined.
///
/// <para>Prose, and checked as prose: the one caller puts the result inside
/// a refusal the user reads, and "bữa sáng, bữa trưa, bữa tối" with a
/// trailing comma instead of "và" reads as a machine talking.</para>
/// </summary>
public class MealLabelsTests
{
    [Theory]
    [InlineData("breakfast", "bữa sáng")]
    [InlineData("lunch", "bữa trưa")]
    [InlineData("dinner", "bữa tối")]
    [InlineData("snack", "bữa phụ")]
    public void Every_meal_of_the_enum_has_a_name(string meal, string expected)
    {
        Assert.Equal(expected, MealLabels.Name(meal));
    }

    /// <summary>
    /// A meal the table does not know returns its own code: ugly on screen,
    /// which is how a missing row gets noticed, and never wrong.
    /// </summary>
    [Fact]
    public void An_unknown_meal_falls_back_to_its_code()
    {
        Assert.Equal("brunch", MealLabels.Name("brunch"));
    }

    [Fact]
    public void One_meal_is_named_on_its_own()
    {
        Assert.Equal("bữa trưa", MealLabels.Join(["lunch"]));
    }

    [Fact]
    public void Two_meals_are_joined_with_va_and_no_comma()
    {
        Assert.Equal("bữa trưa và bữa tối", MealLabels.Join(["lunch", "dinner"]));
    }

    [Fact]
    public void Three_meals_take_commas_and_one_va_before_the_last()
    {
        Assert.Equal(
            "bữa sáng, bữa trưa và bữa tối",
            MealLabels.Join(["breakfast", "lunch", "dinner"]));
    }

    [Fact]
    public void No_meals_joins_to_nothing_rather_than_throwing()
    {
        Assert.Equal(string.Empty, MealLabels.Join([]));
    }

    /// <summary>
    /// The sentence the refusal is built from, assembled here so that a
    /// change to either half is read as the user would read it.
    /// </summary>
    [Fact]
    public void The_refusal_reads_as_a_sentence_for_the_role_that_costs_most()
    {
        var meals = MealStructure.MealsRequiring("main");

        Assert.Equal(
            "Đây là món cuối cùng còn lại cho bữa sáng, bữa trưa và bữa tối.",
            $"Đây là món cuối cùng còn lại cho {MealLabels.Join(meals)}.");
    }
}
