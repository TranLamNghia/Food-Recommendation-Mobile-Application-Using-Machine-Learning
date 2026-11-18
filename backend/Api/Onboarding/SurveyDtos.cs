using System.ComponentModel.DataAnnotations;
using Api.Profile;

namespace Api.Onboarding;

/// <summary>
/// The bodies of the taste survey — specification §7.4.
///
/// <para>Note on language: every <c>ErrorMessage</c> here is Vietnamese,
/// because they become the <c>error.details[].message</c> of §2.5 that end
/// users read. The <b>values</b> that travel in
/// <see cref="SurveySwipeDto.Action"/> are <c>interactions.action</c> ENUM
/// codes and are never translated; so is
/// <see cref="SurveyFoodDto.DishRole"/>. What <i>is</i> Vietnamese in a
/// response is free text out of the database —
/// <see cref="SurveyFoodDto.Name"/>, <see cref="SurveyFoodDto.CategoryName"/>
/// and the tag names — because that is how it is stored, for the screen to
/// show directly.</para>
/// </summary>
public sealed class SurveySubmitRequest
{
    /// <summary>
    /// The id handed out by <c>GET /onboarding/survey</c>. Every
    /// <c>interactions</c> row of this session shares it, which is what makes
    /// a repeated submission recognisable as the same event rather than a
    /// second one.
    /// </summary>
    [Required(ErrorMessage = "Thiếu mã phiên khảo sát")]
    public string? SessionId { get; init; }

    [Required(ErrorMessage = "Thiếu danh sách lượt vuốt")]
    [MinLength(1, ErrorMessage = "Danh sách lượt vuốt không được để trống")]
    [MaxLength(50, ErrorMessage = "Một phiên khảo sát tối đa 50 món")]
    public List<SurveySwipeDto>? Swipes { get; init; }
}

/// <summary>One swipe: a food, and what the user thought of it.</summary>
public sealed class SurveySwipeDto
{
    [Required(ErrorMessage = "Thiếu mã món ăn")]
    public string? FoodId { get; init; }

    /// <summary>
    /// <c>like</c> · <c>dislike</c> · <c>neutral</c> · <c>unknown</c> —
    /// the <c>interactions.action</c> ENUM.
    ///
    /// <para><c>unknown</c> ("chưa từng ăn") is stored like the rest but
    /// carries no taste information, so it does not count towards
    /// <c>minRequired</c> and <c>ml/rocchio.py</c> leaves it out of the
    /// vector. Dropping it instead would lose the fact that the user was
    /// asked at all.</para>
    /// </summary>
    [Required(ErrorMessage = "Thiếu lựa chọn cho món ăn")]
    [InEnum(nameof(Enums.SwipeAction))]
    public string? Action { get; init; }
}

/// <summary>§7.4.1 — the deck, with everything a swipe card needs.</summary>
public sealed class SurveyDeckResponse
{
    public string SessionId { get; init; } = string.Empty;

    /// <summary>
    /// The denominator of the progress bar. It can be smaller than the
    /// requested size when the F1 filter leaves fewer safe foods than that.
    /// </summary>
    public int TotalItems { get; init; }

    /// <summary>
    /// How many <b>opinionated</b> swipes finish the survey.
    /// <c>unknown</c> does not count.
    /// </summary>
    public int MinRequired { get; init; }

    public List<SurveyFoodDto> Items { get; init; } = [];
}

/// <summary>One swipe card.</summary>
public sealed class SurveyFoodDto
{
    public string Id { get; init; } = string.Empty;

    /// <summary>Vietnamese, exactly as <c>foods.name</c> stores it.</summary>
    public string Name { get; init; } = string.Empty;

    public string? ImageUrl { get; init; }

    /// <summary>
    /// <c>food_categories.name</c> — Vietnamese free text, not an ENUM, so
    /// it goes to the screen as it stands.
    /// </summary>
    public string CategoryName { get; init; } = string.Empty;

    public int SpiceLevel { get; init; }

    /// <summary>
    /// A <c>foods.dish_role</c> ENUM code (<c>main</c>, <c>side_protein</c>,
    /// …). The app turns it into a Vietnamese label right before the UI; the
    /// API never does.
    /// </summary>
    public string DishRole { get; init; } = string.Empty;

    public decimal CaloriesKcal { get; init; }
    public int ServingSizeG { get; init; }

    /// <summary>
    /// <c>tags.name_vi</c> for this food — allergen, diet and nutrition
    /// labels, in Vietnamese.
    ///
    /// <para>§7.4.1's example shows taste tags (<c>salty</c>,
    /// <c>high_fiber</c>). The schema dropped the whole <c>taste</c> tag type
    /// deliberately: salty and sweet became measured vector dimensions
    /// computed from <c>sodium_mg</c> and <c>sugar_g</c>, and sour and bitter
    /// are not published by any source this project uses. So what comes back
    /// here are the tag types that exist.</para>
    /// </summary>
    public List<string> Tags { get; init; } = [];
}

/// <summary>§7.4.2 — what the survey produced.</summary>
public sealed class SurveySubmitResponse
{
    public string SessionId { get; init; } = string.Empty;
    public DateTime OnboardingCompletedAt { get; init; }
    public SurveyRecordedDto Recorded { get; init; } = new();
    public SurveyProfileDto PreferenceProfile { get; init; } = new();
    public TasteSummaryDto TasteSummary { get; init; } = new();
}

/// <summary>How many swipes were stored, and of what kind.</summary>
public sealed class SurveyRecordedDto
{
    /// <summary>Rows written to <c>interactions</c>.</summary>
    public int Total { get; init; }

    /// <summary><c>like</c>, <c>dislike</c> and <c>neutral</c>.</summary>
    public int Opinionated { get; init; }

    /// <summary><c>unknown</c> — stored, but left out of the vector.</summary>
    public int Skipped { get; init; }

    /// <summary>
    /// Swipes on a food this user may not eat, counted rather than hidden.
    ///
    /// <para>Not in §7.4.2, and added because the number is otherwise
    /// invisible: the swipes are stored as the user made them — the table is
    /// a record of what happened — and the F1 filter is applied when the
    /// preference vector is built, inside the ML service, which is the one
    /// layer that implements it. So <see cref="Total"/> can exceed the signal
    /// count in <see cref="SurveyProfileDto.NSignals"/>, and without this
    /// field that gap would look like a bug.</para>
    /// </summary>
    public int DroppedUnsafe { get; init; }
}

/// <summary>The preference vector that now exists, in summary.</summary>
public sealed class SurveyProfileDto
{
    /// <summary><c>cold</c> · <c>content</c> · <c>hybrid</c> · <c>ml</c>.</summary>
    public string Stage { get; init; } = string.Empty;

    /// <summary>
    /// Usable signals behind the vector — after the F1 filter and after
    /// <c>unknown</c> swipes are removed.
    /// </summary>
    public int NSignals { get; init; }

    /// <summary>
    /// How much the model will be allowed to say, 0 to 1. Right after
    /// onboarding this is 0: 30 swipes is below the threshold where a
    /// supervised model starts to earn its weight.
    /// </summary>
    public double Alpha { get; init; }

    public string FeatureVersion { get; init; } = string.Empty;
}

/// <summary>
/// A readable summary of the vector, for the closing screen — §7.4.2's
/// "Có vẻ bạn thích món nước và đồ chiên, ăn cay được ở mức vừa".
/// </summary>
public sealed class TasteSummaryDto
{
    /// <summary>
    /// <c>food_categories.name</c>, Vietnamese, most-liked first.
    /// </summary>
    public List<string> TopLikedCategories { get; init; } = [];

    /// <summary>
    /// Taste axes this user leans towards: <c>salty</c>, <c>sweet</c>,
    /// <c>fatty</c>. Stable codes, translated by the app — the same rule as
    /// every ENUM in this API.
    ///
    /// <para>Three axes and not five. They are computed from
    /// <c>sodium_mg</c>, <c>sugar_g</c> and the fat share of energy, which
    /// are measurements; sour and bitter would have to be hand-labelled, and
    /// the schema removed that tag type rather than mix guesses in with
    /// numbers.</para>
    /// </summary>
    public List<string> TopLikedTastes { get; init; } = [];

    /// <summary>The same axes, leaning the other way.</summary>
    public List<string> AvoidedTastes { get; init; } = [];

    /// <summary>
    /// The highest <c>spice_level</c> among the foods they liked, 0 to 3.
    /// <c>null</c> when they liked nothing — which is not the same as "cannot
    /// take any spice", and a 0 there would say the wrong thing.
    /// </summary>
    public int? SpiceTolerance { get; init; }
}
