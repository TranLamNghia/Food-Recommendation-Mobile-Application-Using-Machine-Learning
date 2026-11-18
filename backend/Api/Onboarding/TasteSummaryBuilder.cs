namespace Api.Onboarding;

/// <summary>
/// The three taste axes of <see cref="TasteSummaryDto"/>, as stable codes.
///
/// <para>Three and not five. Salty, sweet and fatty are <b>measured</b> — out
/// of <c>sodium_mg</c>, <c>sugar_g</c> and the fat share of energy. Sour and
/// bitter are not published by any source this project uses, and
/// <c>db/schema.sql</c> removed the whole <c>taste</c> tag type rather than
/// mix hand-written guesses in among numbers. §7.4.2's example happens to
/// show <c>sour</c>; that example predates the decision.</para>
/// </summary>
public static class TasteAxis
{
    public const string Salty = "salty";
    public const string Sweet = "sweet";
    public const string Fatty = "fatty";

    public static readonly string[] All = [Salty, Sweet, Fatty];
}

/// <summary>
/// One food reduced to what the summary needs.
///
/// <para>Every axis is <c>double?</c> and a missing value is <b>not</b> zero.
/// A food with no <c>sodium_mg</c> figure read as 0 becomes the blandest item
/// in the catalogue, which would drag a mean down and could produce the
/// opposite verdict — the same reasoning as the imputation note in
/// <c>ml/features.py</c>, except that here the honest move is to leave the
/// food out of that one axis rather than invent a value.</para>
/// </summary>
/// <param name="CategoryName">
/// <c>food_categories.name</c> — Vietnamese, and reported as it stands.
/// </param>
/// <param name="SaltyDensity">Sodium in mg per gram of food.</param>
/// <param name="SweetDensity">Sugar in g per gram of food.</param>
/// <param name="FattyShare">Fat's share of the food's energy, 0 to 1.</param>
public sealed record TasteFacts(
    string CategoryName,
    int SpiceLevel,
    double? SaltyDensity,
    double? SweetDensity,
    double? FattyShare);

/// <summary>The same three axes, averaged over the whole catalogue.</summary>
public sealed record TasteAxisMeans(
    double? Salty,
    double? Sweet,
    double? Fatty);

/// <summary>
/// Turns one survey session into the closing screen's sentence — §7.4.2.
///
/// <para>Pure on purpose: it takes facts and returns a DTO, with no database
/// and no clock, so <c>backend/Api.Tests</c> can state what a session of
/// swipes should produce without a MySQL server. The queries that produce
/// those facts live in <see cref="SurveyController"/>.</para>
/// </summary>
public static class TasteSummaryBuilder
{
    /// <summary>
    /// How far above the catalogue average an axis has to sit before it is
    /// called a preference: 10 %.
    ///
    /// <para>Not <c>&gt;</c> the average. Half the users would then be told
    /// they like salty food by definition, including someone whose swipes
    /// say nothing at all about salt. The margin makes the claim mean
    /// something; it is a readability threshold for one sentence on one
    /// screen, not a statistical test, and the preference vector itself —
    /// which is what actually drives recommendations — uses none of
    /// this.</para>
    /// </summary>
    public const double Margin = 1.10;

    /// <summary>How many categories the sentence names.</summary>
    public const int TopCategories = 2;

    public static TasteSummaryDto Build(
        IReadOnlyList<(string Action, TasteFacts Facts)> swipes,
        TasteAxisMeans catalogue)
    {
        var liked = swipes
            .Where(s => s.Action == "like")
            .Select(s => s.Facts)
            .ToList();
        var disliked = swipes
            .Where(s => s.Action == "dislike")
            .Select(s => s.Facts)
            .ToList();

        return new TasteSummaryDto
        {
            TopLikedCategories = liked
                .GroupBy(f => f.CategoryName)
                // Count first, then the name: without the second key two
                // categories with the same count would come back in whatever
                // order the rows arrived, and the same session would produce
                // two different sentences.
                .OrderByDescending(g => g.Count())
                .ThenBy(g => g.Key, StringComparer.Ordinal)
                .Take(TopCategories)
                .Select(g => g.Key)
                .ToList(),

            TopLikedTastes = Leaning(liked, catalogue),
            AvoidedTastes = Leaning(disliked, catalogue),

            // `null`, not 0, when they liked nothing: "I cannot take any
            // spice" and "we never found out" are different answers, and 0
            // states the first one.
            SpiceTolerance = liked.Count == 0
                ? null
                : liked.Max(f => f.SpiceLevel),
        };
    }

    /// <summary>
    /// Which axes this group of foods sits above the catalogue on, strongest
    /// first.
    /// </summary>
    private static List<string> Leaning(
        IReadOnlyList<TasteFacts> foods, TasteAxisMeans catalogue)
    {
        if (foods.Count == 0)
        {
            return [];
        }

        var ratios = new List<(string Axis, double Ratio)>();
        Consider(TasteAxis.Salty, f => f.SaltyDensity, catalogue.Salty);
        Consider(TasteAxis.Sweet, f => f.SweetDensity, catalogue.Sweet);
        Consider(TasteAxis.Fatty, f => f.FattyShare, catalogue.Fatty);

        return ratios
            .OrderByDescending(r => r.Ratio)
            .ThenBy(r => r.Axis, StringComparer.Ordinal)
            .Select(r => r.Axis)
            .ToList();

        void Consider(
            string axis, Func<TasteFacts, double?> pick, double? reference)
        {
            // No reference to compare against, or nothing measured in this
            // group: the axis is left out. An axis absent from the list means
            // "nothing to say", which is exactly right and is why the list is
            // not padded to three entries.
            if (reference is not { } mean || mean <= 0)
            {
                return;
            }

            var values = foods
                .Select(pick)
                .Where(v => v is not null)
                .Select(v => v!.Value)
                .ToList();
            if (values.Count == 0)
            {
                return;
            }

            var ratio = values.Average() / mean;
            if (ratio > Margin)
            {
                ratios.Add((axis, ratio));
            }
        }
    }
}
