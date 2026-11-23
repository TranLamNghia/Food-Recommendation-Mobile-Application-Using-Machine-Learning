namespace Api.Planning;

/// <summary>
/// Which dish roles belong to which meal — a mirror of
/// <c>MEAL_STRUCTURE</c> in <c>ml/menu_builder.py</c>.
///
/// <para><b>Why a copy exists at all.</b> §7.5.1's <c>mealType</c> filter
/// asks for "only dishes that fit this meal", and answering it in SQL needs
/// the role sets here rather than a round trip to the ML service for a
/// constant. The copy is the price; the drift is what has to be prevented.</para>
///
/// <para><b>How the drift is prevented.</b> Section 15 of
/// <c>tools/check_step4.py</c> reads the four arrays below out of this file
/// and compares them against <c>MEAL_STRUCTURE</c>, required plus optional,
/// in order. So the arrays have to keep this exact declaration shape —
/// <c>public static readonly string[] Name = [...]</c> — which is the same
/// shape <c>tools/gen_entities.py</c> matches in <c>Api.Profile.Enums</c>,
/// and for the same reason: three implementations of Step 1 once drifted
/// apart with nothing reporting it.</para>
///
/// <para>Each of the four plain arrays is that meal's <b>required</b> roles
/// followed by its <b>optional</b> ones, because §7.5.1's question — "may
/// this dish appear in this meal" — has the same answer for both.</para>
///
/// <para><b>The four <c>…Required</c> arrays are a second question, asked
/// later.</b> Blocking a dish is refused when it is the last one left in a
/// role a meal cannot be assembled without, and that answer needs the split:
/// a day with no soup is a poorer day, a day with no <c>main</c> is not a
/// day. Section 15 of the checker audits these four against
/// <c>MealShape.required</c> separately, so neither group can drift.</para>
/// </summary>
public static class MealStructure
{
    public static readonly string[] Breakfast = ["main", "snack"];

    public static readonly string[] Lunch =
        ["main", "side_protein", "soup"];

    public static readonly string[] Dinner =
        ["main", "side_veg", "side_protein"];

    public static readonly string[] Snack = ["snack"];

    public static readonly string[] BreakfastRequired = ["main"];

    public static readonly string[] LunchRequired = ["main", "side_protein"];

    public static readonly string[] DinnerRequired = ["main", "side_veg"];

    public static readonly string[] SnackRequired = ["snack"];

    /// <summary>
    /// {meal type: the roles it can hold}, built from the four arrays rather
    /// than written out again, so the dictionary cannot drift away from the
    /// arrays the checker audits.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, string[]> RolesOf =
        new Dictionary<string, string[]>
        {
            ["breakfast"] = Breakfast,
            ["lunch"] = Lunch,
            ["dinner"] = Dinner,
            ["snack"] = Snack,
        };

    /// <summary>
    /// The roles that fit <paramref name="mealType"/>, or an empty array for
    /// a meal that does not exist — the caller validates the name first.
    /// </summary>
    public static string[] For(string mealType)
        => RolesOf.TryGetValue(mealType, out var roles) ? roles : [];

    /// <summary>
    /// {meal type: the roles it cannot be assembled without}, built from the
    /// four <c>…Required</c> arrays for the same reason as
    /// <see cref="RolesOf"/>.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, string[]> RequiredOf =
        new Dictionary<string, string[]>
        {
            ["breakfast"] = BreakfastRequired,
            ["lunch"] = LunchRequired,
            ["dinner"] = DinnerRequired,
            ["snack"] = SnackRequired,
        };

    /// <summary>
    /// Every role some meal requires, deduplicated and sorted — the mirror
    /// of <c>ml/survey.REQUIRED_ROLES</c>. Derived, so adding a required role
    /// to a meal cannot leave this list behind.
    ///
    /// <para><c>soup</c> is deliberately absent: it is optional in the one
    /// meal that has it, so a catalogue with no soup left still assembles a
    /// day. So are <c>dessert</c> and <c>drink</c>, which no meal asks for at
    /// all.</para>
    /// </summary>
    /// <para>Typed <c>IReadOnlyList</c> and not <c>string[]</c> on purpose:
    /// section 15 of the checker finds the arrays it audits by the
    /// declaration shape <c>public static readonly string[] … = [ … ]</c>,
    /// and a derived list holds no role name of its own to audit.</para>
    public static readonly IReadOnlyList<string> RequiredRoles =
        [.. RequiredOf.Values.SelectMany(r => r).Distinct().Order()];

    /// <summary>
    /// The meals that cannot be assembled without <paramref name="role"/>,
    /// in the order a day is eaten. Empty when no meal requires it, which is
    /// the answer for <c>soup</c>, <c>dessert</c> and <c>drink</c>.
    ///
    /// <para>Ordered by the day rather than alphabetically because the one
    /// caller puts the result in a sentence a user reads: "bữa trưa và bữa
    /// tối" reads as a day, "bữa tối và bữa trưa" reads as a list.</para>
    /// </summary>
    public static string[] MealsRequiring(string role)
        => [.. MealOrder.Where(meal => RequiredOf[meal].Contains(role))];

    /// <summary>
    /// The four meals in the order they are eaten — <c>MEAL_TYPES</c> of
    /// <c>ml/menu_builder.py</c>, which is in that same order.
    /// </summary>
    public static readonly IReadOnlyList<string> MealOrder =
        ["breakfast", "lunch", "dinner", "snack"];
}

/// <summary>
/// What each meal is called in Vietnamese.
///
/// <para>Here and not in the ML service for the reason every sentence in
/// this project follows: the service sends codes, the layer that talks to
/// the user writes the words. The one caller is the refusal to block the
/// last dish of a required role, which has to name the meal that would
/// break.</para>
/// </summary>
public static class MealLabels
{
    private static readonly IReadOnlyDictionary<string, string> Vi =
        new Dictionary<string, string>
        {
            ["breakfast"] = "bữa sáng",
            ["lunch"] = "bữa trưa",
            ["dinner"] = "bữa tối",
            ["snack"] = "bữa phụ",
        };

    /// <summary>
    /// Lower-case, because every use is mid-sentence. A meal type the table
    /// does not know returns its own code: ugly on screen, which is how a
    /// missing row gets noticed, and never wrong.
    /// </summary>
    public static string Name(string mealType)
        => Vi.TryGetValue(mealType, out var name) ? name : mealType;

    /// <summary>
    /// The meals joined the way Vietnamese joins a list — "bữa trưa và bữa
    /// tối", with "và" before the last one rather than a trailing comma.
    /// </summary>
    public static string Join(IEnumerable<string> mealTypes)
    {
        var names = mealTypes.Select(Name).ToList();
        return names.Count switch
        {
            0 => string.Empty,
            1 => names[0],
            _ => string.Join(", ", names.Take(names.Count - 1))
                 + " và " + names[^1],
        };
    }
}
