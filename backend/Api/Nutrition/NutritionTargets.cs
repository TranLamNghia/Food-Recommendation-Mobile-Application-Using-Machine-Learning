namespace Api.Nutrition;

/// <summary>
/// Step 1 of the recommendation algorithm — the energy and nutrient targets.
///
/// <para>The formulas come from <c>docs/SYSTEM_ARCHITECTURE.md</c> §3.1. This
/// is the <b>third</b> implementation of that same calculation: the other two
/// are <c>mobile/lib/data/models/health_profile.dart</c> and this class. All
/// three have to produce the same numbers, and
/// <c>tools/check_be_parity.py</c> checks that over 30 test cases — without
/// that suite they would drift apart with nobody noticing, because each one
/// runs in a different layer and they never meet.</para>
///
/// <para><b>This class never touches the database.</b> Pure functions over
/// numbers, so it can be checked without a MySQL server — which is what makes
/// it possible to run the parity suite in a test project that has no
/// database.</para>
/// </summary>
public static class NutritionTargets
{
    // ── Activity factors (SYSTEM_ARCHITECTURE §3.1) ──────────────────────
    //
    // Declared as strings matching the `health_profiles.activity_level` ENUM
    // exactly, not as a C# `enum`. The reason is the same as in the entity
    // generator: if the database gains an activity level the code does not
    // know about, that has to be reported by the validation layer, not thrown
    // while reading a perfectly valid row of data.
    public static readonly IReadOnlyDictionary<string, decimal> ActivityFactor =
        new Dictionary<string, decimal>
        {
            ["sedentary"] = 1.200m,
            ["light"] = 1.375m,
            ["moderate"] = 1.550m,
            ["active"] = 1.725m,
            ["very_active"] = 1.900m,
        };

    /// <summary>
    /// Each meal's share of the day's energy, taken as the <b>midpoint</b> of
    /// the ranges in SYSTEM_ARCHITECTURE §3.1: breakfast 25–30, lunch 35–40,
    /// dinner 25–30, snack 5–10.
    ///
    /// <para>Midpoints rather than hand-picked numbers, because a hand-picked
    /// number cannot be derived from anything and the two implementations
    /// would each pick their own set — which is exactly what happened: the API
    /// specification once said 25/40/27/8 while <c>meal_plan.dart</c> used the
    /// midpoints. The four midpoints add up to exactly 100 %.</para>
    /// </summary>
    public static readonly IReadOnlyDictionary<string, decimal> MealShare =
        new Dictionary<string, decimal>
        {
            ["breakfast"] = 0.275m,
            ["lunch"] = 0.375m,
            ["dinner"] = 0.275m,
            ["snack"] = 0.075m,
        };

    /// <summary>BMI thresholds per the WHO 2004 advice for Asian
    /// populations.</summary>
    //
    // 23 and 25 rather than the international 25 and 30: at the same BMI,
    // Asian populations carry a higher body-fat percentage and a higher
    // metabolic risk. Using the international thresholds for Vietnamese users
    // would place a genuinely overweight person in the "normal" group, and
    // the system would not suggest reducing their energy intake.
    public const decimal BmiOverweightAsia = 23.0m;
    public const decimal BmiObeseAsia = 25.0m;

    /// <summary>Whole years old at <paramref name="on"/>, from the date of
    /// birth.</summary>
    //
    // Not `(today - dateOfBirth).Days / 365.25`: that returns 22 for someone
    // whose birthday is one day away, and the BMR is then off by 5 kcal under
    // the Mifflin formula. Small, but it makes the C# implementation disagree
    // with the Dart one — which compares the month and then the day.
    public static int Age(DateOnly dateOfBirth, DateOnly on)
    {
        var years = on.Year - dateOfBirth.Year;
        if (on.Month < dateOfBirth.Month
            || (on.Month == dateOfBirth.Month && on.Day < dateOfBirth.Day))
        {
            years--;
        }
        return years;
    }

    /// <summary>BMI = weight(kg) / height(m)².</summary>
    public static decimal Bmi(decimal weightKg, decimal heightCm)
    {
        var m = heightCm / 100m;
        return weightKg / (m * m);
    }

    /// <summary>
    /// The BMI group by the Asian thresholds: <c>underweight</c> ·
    /// <c>normal</c> · <c>overweight</c> · <c>obese</c>.
    /// </summary>
    public static string BmiCategory(decimal bmi) => bmi switch
    {
        < 18.5m => "underweight",
        < BmiOverweightAsia => "normal",
        < BmiObeseAsia => "overweight",
        _ => "obese",
    };

    /// <summary>
    /// Basal metabolic rate by Mifflin-St Jeor.
    ///
    /// <para>Male: <c>10W + 6.25H − 5A + 5</c>; female: <c>… − 161</c>.</para>
    /// </summary>
    //
    // ── `gender = 'other'`: no published constant exists ──
    //
    // The `health_profiles.gender` ENUM takes three values, but Mifflin-St
    // Jeor was only validated on two groups, male and female — no published
    // work gives a constant for a third group. Four ways to handle it, and
    // why the last one was chosen:
    //
    //   1. Reject with `VALIDATION_FAILED`. No: the database allows that
    //      value, so the API has to accept what the schema permits.
    //   2. Use the male constant (+5). No: that gives a higher target, and
    //      erring towards feeding someone more than they need is the worse
    //      direction to err in.
    //   3. Use the female constant (−161). It is safe for someone losing
    //      weight, but short on energy for someone trying to gain.
    //   4. The midpoint of the two: (+5 + −161) / 2 = −78.
    //
    // (4) was chosen, and it has to be stated plainly that this is a DERIVED
    // number with no source — exactly what `evidence_level = 'derived'`
    // already means for `condition_rules` in the schema. This is a real
    // limitation and has to be named in the report.
    //
    // The right long-term fix is to separate "the sex used for the metabolic
    // formula" from "the gender the user identifies as", because those are two
    // different questions. That needs another column, so it is not done in
    // this slice.
    public const decimal MifflinMale = 5m;
    public const decimal MifflinFemale = -161m;
    public const decimal MifflinOther = (MifflinMale + MifflinFemale) / 2m;

    public static decimal Bmr(
        string gender, decimal weightKg, decimal heightCm, int age)
    {
        var baseValue = 10m * weightKg + 6.25m * heightCm - 5m * age;
        return baseValue + gender switch
        {
            "male" => MifflinMale,
            "female" => MifflinFemale,
            "other" => MifflinOther,
            _ => throw new ArgumentOutOfRangeException(
                nameof(gender),
                $"`{gender}` is not in the health_profiles.gender ENUM"),
        };
    }

    /// <summary>TDEE = BMR × the activity factor.</summary>
    public static decimal Tdee(decimal bmr, string activityLevel)
    {
        if (!ActivityFactor.TryGetValue(activityLevel, out var factor))
        {
            throw new ArgumentOutOfRangeException(
                nameof(activityLevel),
                $"`{activityLevel}` is not in the "
                + "health_profiles.activity_level ENUM");
        }
        return bmr * factor;
    }

    /// <summary>
    /// The energy target for the goal, with its safety constraint.
    ///
    /// <para><c>lose_weight</c> subtracts 500 kcal but <b>never goes below
    /// the BMR</b>: eating less than the basal metabolic rate is not enough
    /// energy for staying alive, which is not a weight-loss plan.</para>
    /// </summary>
    public static decimal EnergyTarget(
        decimal tdee, decimal bmr, string goal) => goal switch
        {
            "lose_weight" => Math.Max(tdee - 500m, bmr),
            "gain_weight" => tdee + 500m,
            "maintain" or "healthy_eating" => tdee,
            _ => throw new ArgumentOutOfRangeException(
                nameof(goal),
                $"`{goal}` is not in the health_profiles.goal ENUM"),
        };

    /// <summary>The gap between the target and the TDEE, for the interface to
    /// explain.</summary>
    public static decimal GoalAdjustment(decimal energyTarget, decimal tdee)
        => energyTarget - tdee;

    /// <summary>
    /// The grams of a macronutrient, from its percentage of the energy and
    /// its kcal per gram.
    /// </summary>
    //
    // 4 kcal/g for protein and carbohydrate, 9 kcal/g for fat — the Atwater
    // factors, the same ones `tools/validate_foods.py` uses to check the
    // composition table.
    public const int KcalPerGramProtein = 4;
    public const int KcalPerGramCarbs = 4;
    public const int KcalPerGramFat = 9;

    public static decimal Grams(decimal energyKcal, byte pct, int kcalPerGram)
        => energyKcal * pct / 100m / kcalPerGram;

    /// <summary>
    /// The whole of Step 1's output for one profile.
    ///
    /// <para>The three macro percentages are <b>parameters</b>, read from the
    /// three <c>health_profiles.target_*_pct</c> columns. Hard-coding them
    /// here would mean editing a row in the database has no effect at all —
    /// and reports no error either.</para>
    /// </summary>
    public static Step1Result Compute(
        string gender,
        DateOnly dateOfBirth,
        decimal heightCm,
        decimal weightKg,
        string activityLevel,
        string goal,
        byte proteinPct,
        byte carbsPct,
        byte fatPct,
        DateOnly today)
    {
        // `chk_macro_sum` in the schema already enforces this, but this class
        // is also called with numbers that never went through the database —
        // from the parity suite, and from PUT /profile before the write.
        // Checking again here stops a wrong triple from quietly producing
        // targets that do not add up to 100 % of the energy.
        if (proteinPct + carbsPct + fatPct != 100)
        {
            throw new ArgumentException(
                $"the three macro percentages add up to "
                + $"{proteinPct + carbsPct + fatPct}%, and must be exactly "
                + "100% — see chk_macro_sum");
        }

        var age = Age(dateOfBirth, today);
        var bmi = Bmi(weightKg, heightCm);
        var bmr = Bmr(gender, weightKg, heightCm, age);
        var tdee = Tdee(bmr, activityLevel);
        var target = EnergyTarget(tdee, bmr, goal);

        return new Step1Result
        {
            Age = age,
            Bmi = bmi,
            BmiCategory = BmiCategory(bmi),
            BmrKcal = bmr,
            TdeeKcal = tdee,
            ActivityFactorValue = ActivityFactor[activityLevel],
            DailyCaloriesTarget = target,
            GoalAdjustmentKcal = GoalAdjustment(target, tdee),
            ProteinPct = proteinPct,
            CarbsPct = carbsPct,
            FatPct = fatPct,
            ProteinG = Grams(target, proteinPct, KcalPerGramProtein),
            CarbsG = Grams(target, carbsPct, KcalPerGramCarbs),
            FatG = Grams(target, fatPct, KcalPerGramFat),
        };
    }
}

/// <summary>
/// Step 1's output, at <b>full precision</b>.
///
/// <para>Deliberately not rounded. The schema stores <c>bmr_kcal</c>,
/// <c>tdee_kcal</c> and <c>daily_calories_target</c> as <c>SMALLINT</c>, so
/// they get rounded on the way in — but the intermediate arithmetic must not
/// be rounded, and Step 4 has to split the target by <b>ratio</b> rather than
/// by four already-rounded integers. Those four integers can add up to 1–2
/// kcal less than the daily target, and if Step 4 treats both as hard
/// constraints then no combination of dishes satisfies them both.</para>
/// </summary>
public sealed class Step1Result
{
    public int Age { get; init; }
    public decimal Bmi { get; init; }
    public string BmiCategory { get; init; } = string.Empty;
    public decimal BmrKcal { get; init; }
    public decimal TdeeKcal { get; init; }
    public decimal ActivityFactorValue { get; init; }
    public decimal DailyCaloriesTarget { get; init; }
    public decimal GoalAdjustmentKcal { get; init; }
    public byte ProteinPct { get; init; }
    public byte CarbsPct { get; init; }
    public byte FatPct { get; init; }
    public decimal ProteinG { get; init; }
    public decimal CarbsG { get; init; }
    public decimal FatG { get; init; }

    /// <summary>The per-meal energy split, at full precision.</summary>
    public IEnumerable<(string MealType, decimal Pct, decimal Kcal)>
        MealDistribution()
        => NutritionTargets.MealShare.Select(
            kv => (kv.Key, kv.Value * 100m, DailyCaloriesTarget * kv.Value));

    /// <summary>The BMR formula written out, so the profile screen can say
    /// where the number came from.</summary>
    public string FormulaExpression(
        string gender, decimal weightKg, decimal heightCm)
    {
        var constant = gender switch
        {
            "male" => NutritionTargets.MifflinMale,
            "female" => NutritionTargets.MifflinFemale,
            _ => NutritionTargets.MifflinOther,
        };
        var sign = constant < 0 ? "−" : "+";
        return $"10 × {weightKg:0.##} + 6.25 × {heightCm:0.##} "
            + $"− 5 × {Age} {sign} {Math.Abs(constant):0.##} "
            + $"= {Math.Round(BmrKcal, MidpointRounding.AwayFromZero):0}";
    }
}
