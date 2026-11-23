using Api.Profile;

namespace Api.Catalogue;

/// <summary>
/// The bodies of the food endpoints — specification §7.5.
///
/// <para>Note on language: <c>name</c>, <c>description</c>,
/// <c>categoryName</c>, the tag names and every <c>warnings[].message</c> are
/// Vietnamese, because they are either data stored that way or prose written
/// for the user. <c>dishRole</c>, <c>tagType</c> and the nutrient keys are
/// ENUM codes and are never translated here.</para>
/// </summary>
public sealed class FoodPageResponse
{
    public List<FoodListItemDto> Items { get; init; } = [];
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int TotalItems { get; init; }
    public int TotalPages { get; init; }
}

/// <summary>One row of the browse list.</summary>
public sealed class FoodListItemDto
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string? ImageUrl { get; init; }
    public string CategoryName { get; init; } = string.Empty;
    public string DishRole { get; init; } = string.Empty;
    public int SpiceLevel { get; init; }
    public decimal CaloriesKcal { get; init; }
    public int ServingSizeG { get; init; }

    /// <summary>
    /// Whether this user may <b>eat</b> it — the medical half of the F1
    /// filter.
    ///
    /// <para>With <c>excludeUnsafe=true</c> (the default) every row is
    /// <c>true</c>, because the unsafe ones are gone. With <c>false</c> the
    /// list is the whole catalogue and this is what the app shows a warning
    /// on — §7.5.1 asks for a warning rather than hiding the dish, so that
    /// someone can still look a food up.</para>
    ///
    /// <para>A dish the user <b>blocked</b> is still <c>true</c> here, and is
    /// not hidden by <c>excludeUnsafe</c>. F1 removes it from what gets
    /// <i>suggested</i>, which is a different question from whether it is
    /// safe — see <see cref="Mark"/>. Were it otherwise, blocking a dish
    /// would make it vanish from search, and the screen that unblocks it is
    /// the one it vanished from.</para>
    /// </summary>
    public bool IsSafeForUser { get; init; }

    /// <summary>
    /// <c>loved</c> when the user bookmarked it, <c>blocked</c> when they
    /// asked for it not to be suggested, <c>null</c> for neither.
    ///
    /// <para>One value and not two flags, because <c>user_food_marks</c> has
    /// one row per (user, food): "saved to try" and "never suggest this"
    /// contradict each other, so setting one clears the other.</para>
    /// </summary>
    public string? Mark { get; init; }
}

/// <summary>§7.5.2 — one food in full.</summary>
public sealed class FoodDetailResponse
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public string? ImageUrl { get; init; }
    public FoodCategoryRefDto Category { get; init; } = new();
    public int SpiceLevel { get; init; }
    public string DishRole { get; init; } = string.Empty;
    public FoodNutritionDto Nutrition { get; init; } = new();
    public List<FoodTagDto> Tags { get; init; } = [];

    /// <summary>
    /// Whether this user may <b>eat</b> it. A dish they blocked is still
    /// <c>true</c>: see <see cref="FoodListItemDto.IsSafeForUser"/>.
    /// </summary>
    public bool IsSafeForUser { get; init; }

    /// <summary>
    /// <c>loved</c> · <c>blocked</c> · <c>null</c> — see
    /// <see cref="FoodListItemDto.Mark"/>. This is what the detail screen
    /// draws the bookmark and the "không gợi ý món này nữa" switch from, and
    /// it is deliberately <b>not</b> a row in <see cref="Warnings"/>: a block
    /// is a preference, and mixing it into the medical warnings would have
    /// the screen state a health reason the system does not have.
    /// </summary>
    public string? Mark { get; init; }

    /// <summary>
    /// Every hard <b>medical</b> rule this food breaks for this user, each
    /// with a sentence to show. Empty when the food is safe to eat, even if
    /// the user has blocked it.
    /// </summary>
    public List<FoodWarningDto> Warnings { get; init; } = [];

    /// <summary>
    /// This user's <b>most recent</b> rating of the food, or <c>null</c> if
    /// they have never rated it.
    ///
    /// <para>The most recent and not the only one: <c>feedbacks</c> has no
    /// unique key on (user, food) on purpose — taste changes, and a 5-star
    /// dish can be a 2-star dish next month. Both rows are kept, and
    /// comparing them is a signal in itself.</para>
    /// </summary>
    public MyFeedbackDto? MyFeedback { get; init; }
}

/// <summary>Just enough of a category to label a food.</summary>
public sealed class FoodCategoryRefDto
{
    public string Id { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
}

/// <summary>
/// One serving's nutrition.
///
/// <para>Every micronutrient is nullable and a missing one stays
/// <c>null</c> — §10.3's rule, and here it carries weight beyond tidiness:
/// the F1 filter <b>excludes</b> a food whose figure is missing at a
/// per-serving threshold, because it cannot be shown to be safe. A 0 in this
/// object would say the opposite of what the filter concluded.</para>
/// </summary>
public sealed class FoodNutritionDto
{
    public int ServingSizeG { get; init; }
    public decimal CaloriesKcal { get; init; }
    public decimal ProteinG { get; init; }
    public decimal CarbsG { get; init; }
    public decimal FatG { get; init; }
    public decimal? FiberG { get; init; }
    public decimal? SugarG { get; init; }
    public decimal? SodiumMg { get; init; }
    public decimal? CholesterolMg { get; init; }
    public decimal? PurineMg { get; init; }
    public decimal? CalciumMg { get; init; }
    public decimal? IronMg { get; init; }
    public decimal? ZincMg { get; init; }
    public decimal? VitaminAMcg { get; init; }
    public decimal? VitaminCMg { get; init; }
}

/// <summary>One tag on a food.</summary>
public sealed class FoodTagDto
{
    public uint Id { get; init; }

    /// <summary>Vietnamese, from <c>tags.name_vi</c>.</summary>
    public string NameVi { get; init; } = string.Empty;

    /// <summary><c>allergen</c> · <c>diet</c> · <c>nutrition</c>.</summary>
    public string TagType { get; init; } = string.Empty;
}

/// <summary>Why this food is not safe for this user.</summary>
public sealed class FoodWarningDto
{
    /// <summary>
    /// <c>conditions.id</c>.
    ///
    /// <para>§7.5.2's example shows a <c>conditionCode</c> such as
    /// <c>"hypertension"</c>. The <c>conditions</c> table has no such column
    /// — it carries <c>name_vi</c> and <c>condition_type</c> — so the id is
    /// sent instead, which is what every other endpoint takes.</para>
    /// </summary>
    public uint? ConditionId { get; init; }

    /// <summary>
    /// <c>conditions.code</c> — the stable one, and the field §7.5.2's
    /// example actually shows. <c>conditionId</c> stays alongside it because
    /// writing a declaration back takes the id.
    /// </summary>
    public string? ConditionCode { get; init; }

    /// <summary>Vietnamese, from <c>conditions.name_vi</c>.</summary>
    public string ConditionName { get; init; } = string.Empty;

    /// <summary>
    /// <c>exclude_tag</c> · <c>require_tag</c> · <c>nutrient_limit</c>.
    /// </summary>
    public string RuleType { get; init; } = string.Empty;

    /// <summary>The sentence to show, in Vietnamese.</summary>
    public string Message { get; init; } = string.Empty;

    /// <summary>
    /// Always <c>true</c> here. Only hard rules exclude a food; a soft rule
    /// lowers its score and leaves it in the plan, so it is not a warning
    /// about safety. The field is kept because §7.5.2 declares it, and so
    /// that a later soft-rule hint can arrive as <c>false</c> without
    /// changing the shape.
    /// </summary>
    public bool IsHard { get; init; } = true;

    /// <summary>
    /// <c>true</c> when the food was excluded for a <b>missing</b>
    /// measurement rather than for exceeding one. Not in §7.5.2, and added
    /// because the two cases deserve different treatment on screen: one is
    /// the dish being unsuitable, the other is the catalogue not knowing.
    /// </summary>
    public bool MissingData { get; init; }
}

/// <summary>This user's latest rating of a food.</summary>
public sealed class MyFeedbackDto
{
    public string Id { get; init; } = string.Empty;
    public int Rating { get; init; }
    public string? Comment { get; init; }
    public DateTime CreatedAt { get; init; }
}

/// <summary>
/// The body of <c>PUT /foods/{id}/mark</c> — bookmark a dish, or ask for it
/// not to be suggested again.
///
/// <para><c>kind</c> is <b>nullable on purpose</b>, and <c>null</c> means
/// "no mark": it is how both the bookmark and the switch are turned off. A
/// separate <c>DELETE</c> would be the alternative, and would make the app
/// choose between two verbs for one toggle.</para>
///
/// <para>Note that <see cref="InEnumAttribute"/> accepts <c>null</c> and
/// there is no <c>[Required]</c> here, which is the combination that lets an
/// absent <c>kind</c> through. An empty body therefore clears the mark, same
/// as <c>{"kind": null}</c>.</para>
/// </summary>
public sealed class FoodMarkRequest
{
    [InEnum(nameof(Enums.MarkKind))]
    public string? Kind { get; init; }
}

/// <summary>
/// What <c>PUT /foods/{id}/mark</c> answers with: the mark as it now stands.
///
/// <para>The state and not just an acknowledgement, so the app renders from
/// the server's answer rather than from what it hoped would happen. It
/// matters here because the two marks are mutually exclusive: bookmarking a
/// dish that was blocked comes back as <c>loved</c>, and a screen that
/// assumed otherwise would draw both controls on.</para>
/// </summary>
public sealed class FoodMarkResponse
{
    public string FoodId { get; init; } = string.Empty;

    /// <summary><c>loved</c> · <c>blocked</c> · <c>null</c> for cleared.</summary>
    public string? Kind { get; init; }

    /// <summary>When the mark was made, or <c>null</c> once cleared.</summary>
    public DateTime? MarkedAt { get; init; }
}
