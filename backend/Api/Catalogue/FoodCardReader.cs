using Api.Data;
using Microsoft.EntityFrameworkCore;

namespace Api.Catalogue;

/// <summary>
/// Everything a food needs on screen, read once for a set of ids.
///
/// <para><b>Why one reader.</b> The taste survey (§7.4.1), the meal plan
/// (§7.6.1) and the replacement suggestions (§7.6.4) all show the same little
/// card: name, image, category, role, energy, serving. Written per endpoint,
/// that is the same four-table join three times, and three chances for one of
/// them to forget the category join and return an empty label.</para>
///
/// <para><b>Why the ML service does not send these fields.</b> It answers
/// with food <i>ids</i> only. The name and the category label are Vietnamese
/// free text in this database, and two layers formatting the same food is two
/// places for that text to drift. The ML service decides <i>which</i> foods;
/// this reader decides what they look like.</para>
///
/// <para>Note on language: <see cref="FoodCard.Name"/>,
/// <see cref="FoodCard.CategoryName"/> and <see cref="FoodCard.Tags"/> are
/// Vietnamese, because the columns behind them are
/// (<c>foods.name</c>, <c>food_categories.name</c>, <c>tags.name_vi</c>).
/// <see cref="FoodCard.DishRole"/> is an ENUM code and stays English — the
/// app translates it right before the UI.</para>
/// </summary>
public sealed record FoodCard
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string? ImageUrl { get; init; }
    public string CategoryName { get; init; } = string.Empty;
    public string DishRole { get; init; } = string.Empty;
    public int SpiceLevel { get; init; }
    public decimal CaloriesKcal { get; init; }
    public int ServingSizeG { get; init; }
    public List<string> Tags { get; init; } = [];
}

/// <inheritdoc cref="FoodCard"/>
public static class FoodCardReader
{
    /// <summary>
    /// Reads the cards for <paramref name="foodIds"/>, keyed by id.
    ///
    /// <para>A dictionary rather than a list, because every caller has its
    /// own order to preserve — the survey deck's order is the order the
    /// algorithm picked, and a meal's order is <c>position</c>. Returning a
    /// list would invite callers to use the database's order, which is
    /// neither.</para>
    ///
    /// <para>A food with no <c>food_nutrition</c> row is <b>left out</b>
    /// rather than returned with zeros. Energy is what Step 4 balances a day
    /// against, and a dish silently carrying 0 kcal would make a plan's total
    /// wrong while every number in the response still looked valid. Callers
    /// compare the count they asked for against the count they got.</para>
    /// </summary>
    public static async Task<Dictionary<string, FoodCard>> ReadAsync(
        AppDbContext db,
        IReadOnlyCollection<string> foodIds,
        CancellationToken ct = default)
    {
        if (foodIds.Count == 0)
        {
            return [];
        }

        var ids = foodIds.Distinct().ToList();

        var rows = await db.Foods
            .Where(f => ids.Contains(f.Id))
            .Join(db.FoodNutrition, f => f.Id, n => n.FoodId,
                  (f, n) => new { Food = f, Nutrition = n })
            .Join(db.FoodCategories, x => x.Food.CategoryId, c => c.Id,
                  (x, c) => new
                  {
                      x.Food.Id,
                      x.Food.Name,
                      x.Food.ImageUrl,
                      CategoryName = c.Name,
                      x.Food.DishRole,
                      x.Food.SpiceLevel,
                      x.Nutrition.CaloriesKcal,
                      x.Nutrition.ServingSizeG,
                  })
            .ToListAsync(ct);

        // The tags in a second query rather than a fourth join: joining them
        // in would multiply every food row by its tag count and make the
        // energy figures arrive several times over, which is how a SUM over
        // such a query silently doubles.
        var tags = await db.FoodTags
            .Where(ft => ids.Contains(ft.FoodId))
            .Join(db.Tags, ft => ft.TagId, t => t.Id,
                  (ft, t) => new { ft.FoodId, t.NameVi })
            .ToListAsync(ct);

        var tagsByFood = tags
            .GroupBy(t => t.FoodId)
            .ToDictionary(
                g => g.Key,
                g => g.Select(t => t.NameVi).OrderBy(n => n).ToList());

        return rows.ToDictionary(
            r => r.Id,
            r => new FoodCard
            {
                Id = r.Id,
                Name = r.Name,
                ImageUrl = r.ImageUrl,
                CategoryName = r.CategoryName,
                DishRole = r.DishRole,
                SpiceLevel = r.SpiceLevel,
                CaloriesKcal = r.CaloriesKcal,
                ServingSizeG = r.ServingSizeG,
                Tags = tagsByFood.TryGetValue(r.Id, out var t) ? t : [],
            });
    }
}
