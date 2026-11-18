using Api.Onboarding;
using Api.Profile;

namespace Api.Tests;

/// <summary>
/// The taste survey's pure parts — specification §7.4.
///
/// <para>What is testable here is what was written to be testable:
/// <see cref="TasteSummaryBuilder"/> takes facts and returns a DTO, with no
/// database and no clock. The controller's own path needs MySQL and the ML
/// service, and <c>tools/smoke_backend.py</c> is what exercises that.</para>
///
/// <para>These are not tests of arithmetic for its own sake. The closing
/// screen tells the user what the system thinks of their taste, and three of
/// the cases below are ways of being confidently wrong: calling half the
/// population salt-lovers by definition, reading a missing measurement as
/// zero, and saying "no spice at all" to someone who was simply never
/// asked.</para>
/// </summary>
public class TasteSummaryTests
{
    private const string Like = "like";
    private const string Dislike = "dislike";
    private const string Neutral = "neutral";

    /// <summary>
    /// The catalogue's averages used throughout: 1 mg sodium per gram,
    /// 0.1 g sugar per gram, fat at 30 % of energy.
    /// </summary>
    private static readonly TasteAxisMeans Catalogue = new(1.0, 0.1, 0.30);

    private static TasteFacts Food(
        string category = "Cơm",
        int spice = 0,
        double? salty = null,
        double? sweet = null,
        double? fatty = null)
        => new(category, spice, salty, sweet, fatty);

    [Fact]
    public void A_food_only_a_little_above_average_is_not_a_preference()
    {
        // 5 % above the catalogue, under the 10 % margin.
        var swipes = new[] { (Like, Food(salty: 1.05)) };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Empty(summary.TopLikedTastes);
    }

    /// <summary>
    /// The margin is the whole point: with a plain <c>&gt;</c> comparison,
    /// anyone whose liked foods land a hair above the mean — which is half of
    /// everyone — would be told they like salty food.
    /// </summary>
    [Fact]
    public void Well_above_average_is_a_preference()
    {
        var swipes = new[]
        {
            (Like, Food(salty: 2.0)),
            (Like, Food(salty: 1.8)),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Equal([TasteAxis.Salty], summary.TopLikedTastes);
    }

    [Fact]
    public void The_strongest_axis_comes_first()
    {
        // Salty at 3x the average, fatty at 1.5x.
        var swipes = new[] { (Like, Food(salty: 3.0, fatty: 0.45)) };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Equal(
            [TasteAxis.Salty, TasteAxis.Fatty], summary.TopLikedTastes);
    }

    /// <summary>
    /// A missing measurement is not a zero. If <c>null</c> were read as 0 the
    /// average here would be 1.0 — exactly the catalogue mean — and the user
    /// would be told nothing, when in fact every food they liked that HAS a
    /// figure is twice as salty as average.
    /// </summary>
    [Fact]
    public void A_null_measurement_is_left_out_rather_than_counted_as_zero()
    {
        var swipes = new[]
        {
            (Like, Food(salty: 2.0)),
            (Like, Food(salty: null)),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Equal([TasteAxis.Salty], summary.TopLikedTastes);
    }

    [Fact]
    public void An_axis_the_catalogue_cannot_measure_is_left_out()
    {
        var swipes = new[] { (Like, Food(sweet: 99.0)) };

        var summary = TasteSummaryBuilder.Build(
            swipes, new TasteAxisMeans(1.0, null, 0.30));

        Assert.Empty(summary.TopLikedTastes);
    }

    [Fact]
    public void What_they_disliked_is_what_they_avoid()
    {
        var swipes = new[]
        {
            (Like, Food(salty: 0.2)),
            (Dislike, Food(salty: 3.0)),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Empty(summary.TopLikedTastes);
        Assert.Equal([TasteAxis.Salty], summary.AvoidedTastes);
    }

    [Fact]
    public void Only_liked_foods_decide_the_categories()
    {
        var swipes = new[]
        {
            (Like, Food(category: "Món nước")),
            (Like, Food(category: "Món nước")),
            (Like, Food(category: "Món chiên rán")),
            (Dislike, Food(category: "Món gỏi / nộm")),
            (Neutral, Food(category: "Món gỏi / nộm")),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Equal(
            ["Món nước", "Món chiên rán"], summary.TopLikedCategories);
    }

    /// <summary>
    /// Two categories with the same count have to come back in a fixed order,
    /// or the same session produces a different sentence on every read.
    /// </summary>
    [Fact]
    public void A_tie_between_categories_is_broken_the_same_way_every_time()
    {
        var swipes = new[]
        {
            (Like, Food(category: "Cơm")),
            (Like, Food(category: "Bún")),
        };

        var first = TasteSummaryBuilder.Build(swipes, Catalogue);
        var second = TasteSummaryBuilder.Build(
            swipes.Reverse().ToArray(), Catalogue);

        Assert.Equal(first.TopLikedCategories, second.TopLikedCategories);
    }

    [Fact]
    public void Spice_tolerance_is_the_spiciest_thing_they_liked()
    {
        var swipes = new[]
        {
            (Like, Food(spice: 1)),
            (Like, Food(spice: 3)),
            (Dislike, Food(spice: 2)),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Equal(3, summary.SpiceTolerance);
    }

    /// <summary>
    /// <c>null</c>, not 0. "We never found out" and "cannot take any spice"
    /// are different answers, and a 0 on the closing screen states the
    /// second one.
    /// </summary>
    [Fact]
    public void Liking_nothing_leaves_spice_tolerance_unknown()
    {
        var swipes = new[]
        {
            (Dislike, Food(spice: 3)),
            (Neutral, Food(spice: 2)),
        };

        var summary = TasteSummaryBuilder.Build(swipes, Catalogue);

        Assert.Null(summary.SpiceTolerance);
        Assert.Empty(summary.TopLikedCategories);
        Assert.Empty(summary.TopLikedTastes);
    }
}

/// <summary>
/// The constants the survey endpoints agree on.
/// </summary>
public class SurveyConstantTests
{
    /// <summary>
    /// The deck can be as small as 20 and the survey needs 20 opinionated
    /// swipes, so a full deck of the minimum size is exactly enough. If these
    /// two ever drift apart in the wrong direction, the smallest allowed deck
    /// could not complete the survey it was drawn for.
    /// </summary>
    [Fact]
    public void The_smallest_deck_can_still_finish_the_survey()
    {
        Assert.True(
            SurveyController.MinOpinionated <= SurveyController.DeckSizeMin);
    }

    [Fact]
    public void The_default_deck_size_is_inside_the_allowed_range()
    {
        Assert.InRange(
            SurveyController.DeckSizeDefault,
            SurveyController.DeckSizeMin,
            SurveyController.DeckSizeMax);
    }

    /// <summary>
    /// The four swipe answers are the <c>interactions.action</c> ENUM, and
    /// <c>tools/gen_entities.py</c> compares that array against
    /// <c>db/schema.sql</c>. This asserts the one value the API treats
    /// specially is actually in it — a rename of <c>unknown</c> would
    /// otherwise make every swipe count as opinionated, silently.
    /// </summary>
    [Fact]
    public void Unknown_is_one_of_the_swipe_actions()
    {
        Assert.Contains("unknown", Enums.SwipeAction);
        Assert.Equal(4, Enums.SwipeAction.Length);
    }
}
