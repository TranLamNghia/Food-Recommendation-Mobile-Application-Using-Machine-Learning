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
/// <para>Each array is that meal's <b>required</b> roles followed by its
/// <b>optional</b> ones. This class does not keep the two apart, because the
/// only question asked of it is "may this dish appear in this meal", and the
/// answer is the same for both. Assembling a meal — where the difference
/// decides what has to be filled — happens in the ML service.</para>
/// </summary>
public static class MealStructure
{
    public static readonly string[] Breakfast = ["main", "snack"];

    public static readonly string[] Lunch =
        ["main", "side_protein", "soup"];

    public static readonly string[] Dinner =
        ["main", "side_veg", "side_protein"];

    public static readonly string[] Snack = ["snack"];

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
}
