using System.ComponentModel.DataAnnotations;
using System.Reflection;

namespace Api.Profile;

/// <summary>
/// The lists of valid values — specification §5.1, matching the database's
/// ENUMs word for word.
///
/// <para>Validated against a list at this layer rather than mapped onto a C#
/// <c>enum</c>: a wrong value has to come out as <c>400 VALIDATION_FAILED</c>
/// naming the field, not as a JSON deserialization error carrying the
/// library's own wording.</para>
///
/// <para><b>These four arrays are the single source.</b> An earlier version
/// declared them here and then repeated them verbatim inside every
/// <c>[InEnum("male", …)]</c>, because an attribute argument has to be a
/// compile-time constant and a <c>string[]</c> cannot be passed in. The
/// consequence: nothing in the class was ever read, and adding a value here
/// would NOT change validation at all — and would not report an error either.
/// <c>InEnumAttribute</c> now takes the <b>name</b> of a list and looks it up
/// in <see cref="ByName"/> at run time, so
/// <c>[InEnum(nameof(Enums.Gender))]</c> is both a compile-time constant and
/// a real reference to the array below.</para>
///
/// <para><c>tools/gen_entities.py</c> compares these four arrays against the
/// ENUM value sets in <c>db/schema.sql</c>, in both directions — see check 5
/// there. It matches them by the regular expression
/// <c>public static readonly string[] (\w+) = [...]</c>, so the four field
/// names and that declaration shape have to stay as they are.</para>
///
/// <para>Note on language: the values inside the arrays are ENUM values of
/// the schema and of specification §5.1, so they are compared against the
/// database and never translated. The message returned by
/// <see cref="InEnumAttribute.FormatErrorMessage"/> and every
/// <c>ErrorMessage</c> below stay in Vietnamese — they are the
/// <c>error.details[].message</c> strings of §2.5, which end users
/// read.</para>
/// </summary>
public static class Enums
{
    public static readonly string[] Gender = ["male", "female", "other"];

    public static readonly string[] ActivityLevel =
        ["sedentary", "light", "moderate", "active", "very_active"];

    public static readonly string[] Goal =
        ["lose_weight", "maintain", "gain_weight", "healthy_eating"];

    public static readonly string[] Severity = ["mild", "moderate", "severe"];

    /// <summary>
    /// <c>interactions.action</c> — the four answers to one swipe card of
    /// §7.4. <c>unknown</c> is "chưa từng ăn": stored, but carrying no taste
    /// information, so it does not count towards <c>minRequired</c>.
    /// </summary>
    public static readonly string[] SwipeAction =
        ["like", "dislike", "neutral", "unknown"];

    /// <summary>
    /// <c>meal_plan_items.meal_type</c> — the four meals of a day, in the
    /// order they are eaten. The order matters: a response listing the meals
    /// is built from this array.
    /// </summary>
    public static readonly string[] MealType =
        ["breakfast", "lunch", "dinner", "snack"];

    /// <summary>
    /// <c>meal_plan_items.status</c>, the whole ENUM.
    ///
    /// <para>Only three of the five may be SET by a client —
    /// <c>Api.Planning.MealItemStatus.ClientSettable</c> holds that subset,
    /// and a test asserts it stays a subset of this array. <c>suggested</c>
    /// is what the backend writes when it generates the plan and
    /// <c>replaced</c> is what it writes when a dish is swapped; letting a
    /// client send either would let it rewrite history that the label
    /// weights of §4.6 are computed from.</para>
    /// </summary>
    public static readonly string[] MealItemStatus =
        ["suggested", "kept", "replaced", "eaten", "skipped"];

    /// <summary>
    /// <c>conditions.condition_type</c> — what kind of thing the user
    /// declared. The F1 filter treats all four the same way (a hard rule is
    /// a hard rule); the type exists so the app can group the list on the
    /// declaration screen.
    /// </summary>
    public static readonly string[] ConditionType =
        ["disease", "allergy", "intolerance", "diet"];

    /// <summary>
    /// <c>tags.tag_type</c>. No <c>taste</c> value: salty and sweet became
    /// measured vector dimensions computed from <c>sodium_mg</c> and
    /// <c>sugar_g</c>, and sour and bitter are not published by any source
    /// this project uses — so the whole group was dropped rather than mixing
    /// hand-written labels in among measurements.
    /// </summary>
    public static readonly string[] TagType =
        ["allergen", "diet", "nutrition"];

    /// <summary>
    /// <c>foods.dish_role</c> — what part of a meal a dish plays, which is
    /// what makes two dishes interchangeable. <c>MEAL_STRUCTURE</c> in
    /// <c>ml/menu_builder.py</c> fills a meal by role, and
    /// <c>Api.Planning.MealStructure</c> mirrors which roles belong to which
    /// meal.
    ///
    /// <para><c>dessert</c> and <c>drink</c> are in the column and in no
    /// meal: 46 of the 318 foods carry them, and no meal has a slot that
    /// could hold one. That is an open product question, not an oversight —
    /// <c>DailyPlan.warnings</c> reports it on every plan.</para>
    /// </summary>
    public static readonly string[] DishRole =
        ["main", "side_protein", "side_veg", "soup", "snack", "dessert",
         "drink"];

    /// <summary>
    /// {field name: list}, built by reflection over the fields above rather
    /// than written out by hand, so the dictionary cannot drift away from
    /// them.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, string[]> ByName =
        typeof(Enums)
            .GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.FieldType == typeof(string[]))
            .ToDictionary(f => f.Name, f => (string[])f.GetValue(null)!);
}

/// <summary>
/// The value has to be in one of <see cref="Enums"/>' lists.
///
/// <para>Used with <c>nameof</c>: <c>[InEnum(nameof(Enums.Gender))]</c>.
/// Rename the field and <c>nameof</c> follows, and reflection rebuilds the
/// matching key — so there is no way for a name here to point at a list that
/// does not exist and still compile.</para>
/// </summary>
public sealed class InEnumAttribute : ValidationAttribute
{
    private readonly string[] _allowed;

    public InEnumAttribute(string listName)
    {
        if (!Enums.ByName.TryGetValue(listName, out var values))
        {
            throw new ArgumentException(
                $"`{listName}` is not the name of a list in Api.Profile.Enums",
                nameof(listName));
        }
        _allowed = values;
    }

    public override bool IsValid(object? value)
        => value is string s && _allowed.Contains(s);

    public override string FormatErrorMessage(string name)
        => "Giá trị không nằm trong danh sách cho phép: "
            + string.Join(" · ", _allowed);
}

/// <summary>Body of <c>PUT /profile</c> — specification §7.2.2.</summary>
public sealed class UpsertProfileRequest
{
    [Required(ErrorMessage = "Thiếu giới tính")]
    [InEnum(nameof(Enums.Gender))]
    public string Gender { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu ngày sinh")]
    public DateOnly? DateOfBirth { get; set; }

    // The range matches `chk_height CHECK (height_cm BETWEEN 50 AND 250)`.
    // Checked at both layers, deliberately: the database constraint is the
    // last line of defence, while this layer is the only place that can tell
    // the user *which field* is wrong — a `MySqlException` cannot.
    [Required(ErrorMessage = "Thiếu chiều cao")]
    [Range(50, 250, ErrorMessage = "Chiều cao phải trong khoảng 50 đến 250 cm")]
    public decimal? HeightCm { get; set; }

    [Required(ErrorMessage = "Thiếu cân nặng")]
    [Range(20, 300, ErrorMessage = "Cân nặng phải trong khoảng 20 đến 300 kg")]
    public decimal? WeightKg { get; set; }

    [Required(ErrorMessage = "Thiếu mức vận động")]
    [InEnum(nameof(Enums.ActivityLevel))]
    public string ActivityLevel { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu mục tiêu")]
    [InEnum(nameof(Enums.Goal))]
    public string Goal { get; set; } = string.Empty;
}

/// <summary>One of the user's medical conditions — §7.2.4.</summary>
public sealed class UserConditionDto
{
    public uint ConditionId { get; init; }
    public string NameVi { get; init; } = string.Empty;
    public string ConditionType { get; init; } = string.Empty;
    public string Severity { get; init; } = string.Empty;
    public string? Note { get; init; }
}

/// <summary>The complete health profile — §7.2.1.</summary>
public sealed class ProfileResponse
{
    public string Gender { get; init; } = string.Empty;
    public DateOnly DateOfBirth { get; init; }
    public int Age { get; init; }
    public decimal HeightCm { get; init; }
    public decimal WeightKg { get; init; }
    public decimal Bmi { get; init; }
    public string BmiCategory { get; init; } = string.Empty;
    public string ActivityLevel { get; init; } = string.Empty;
    public string Goal { get; init; } = string.Empty;
    public List<UserConditionDto> Conditions { get; init; } = [];
    public DateTime CreatedAt { get; init; }
    public DateTime UpdatedAt { get; init; }
}

/// <summary>One energy-bearing macronutrient in the targets — §7.2.3.</summary>
public sealed class MacroTargetsDto
{
    public byte ProteinPct { get; init; }
    public decimal ProteinG { get; init; }
    public byte CarbsPct { get; init; }
    public decimal CarbsG { get; init; }
    public byte FatPct { get; init; }
    public decimal FatG { get; init; }
}

/// <summary>One meal in the energy split — §7.2.3.</summary>
public sealed class MealShareDto
{
    public string MealType { get; init; } = string.Empty;
    public decimal Pct { get; init; }
    public int CaloriesKcal { get; init; }
}

/// <summary>The BMR formula, so the profile screen can say where the number
/// came from — §7.2.3.</summary>
public sealed class FormulaDto
{
    public string Bmr { get; init; } = "Mifflin-St Jeor";
    public string Expression { get; init; } = string.Empty;
}

/// <summary>Step 1's output — §7.2.3.</summary>
public sealed class NutritionTargetsResponse
{
    public decimal Bmi { get; init; }
    public string BmiCategory { get; init; } = string.Empty;
    public int BmrKcal { get; init; }
    public int TdeeKcal { get; init; }
    public decimal ActivityFactor { get; init; }
    public int DailyCaloriesTarget { get; init; }
    public int GoalAdjustmentKcal { get; init; }
    public MacroTargetsDto MacroTargets { get; init; } = new();
    public List<MealShareDto> MealDistribution { get; init; } = [];
    public FormulaDto Formula { get; init; } = new();
}

/// <summary>
/// The <c>PUT /profile</c> response — §7.2.2 returns the profile
/// <b>together with</b> the freshly recomputed targets, so the frontend does
/// not need a second round trip.
/// </summary>
public sealed class UpsertProfileResponse
{
    public ProfileResponse Profile { get; init; } = new();
    public NutritionTargetsResponse NutritionTargets { get; init; } = new();
}

/// <summary>One element of the <c>PUT /profile/conditions</c> body.</summary>
public sealed class ConditionInput
{
    [Required(ErrorMessage = "Thiếu conditionId")]
    public uint? ConditionId { get; set; }

    [Required(ErrorMessage = "Thiếu mức độ")]
    [InEnum(nameof(Enums.Severity))]
    public string Severity { get; set; } = string.Empty;

    [MaxLength(255, ErrorMessage = "Ghi chú tối đa 255 ký tự")]
    public string? Note { get; set; }
}

/// <summary>Body of <c>PUT /profile/conditions</c> — §7.2.5.</summary>
public sealed class UpsertConditionsRequest
{
    /// <summary>
    /// Replaces the <b>whole</b> list. Send an empty array to clear it.
    ///
    /// <para><c>Required</c> rather than defaulting to empty: a body of
    /// <c>{}</c> and a body of <c>{"conditions": []}</c> have to mean
    /// different things. The second one is "I have no conditions"; the first
    /// is a request with a field missing, and treating it as an empty array
    /// would let a frontend bug silently wipe out the user's
    /// conditions.</para>
    /// </summary>
    [Required(ErrorMessage = "Thiếu danh sách `conditions`")]
    public List<ConditionInput>? Conditions { get; set; }
}
