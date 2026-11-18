namespace Api.Ml;

/// <summary>
/// The bodies of <c>POST /plan</c> and <c>POST /survey-deck</c>, mirroring
/// the Pydantic models of <c>ml/api.py</c> field for field.
///
/// <para>Separate from <c>MlContracts.cs</c> only for size. The same rule
/// applies: the property names <b>are</b> the wire contract, because
/// <see cref="MlClient"/> serialises with
/// <c>JsonNamingPolicy.CamelCase</c>. Renaming one here means changing
/// <c>ml/api.py</c> in the same commit, and
/// <c>tools/smoke_ml_api.py</c> is what proves the pair still agree.</para>
///
/// <para>Note on language: nothing here is user-facing. The strings in the
/// <c>Warnings</c> lists are developer-facing English from <c>ml/</c>, for
/// the log — never an <c>error.message</c>.</para>
/// </summary>
public sealed record MlPlanRequest
{
    public required string UserId { get; init; }

    /// <summary>
    /// <c>YYYY-MM-DD</c>. Omitted means today in Asia/Ho_Chi_Minh, decided
    /// by the ML service — the one clock of this system.
    ///
    /// <para>A <c>string</c> rather than <c>DateOnly</c>: the ML service
    /// parses it itself and answers <c>400</c> for anything that is not an
    /// ISO date, and sending the day as the exact text received keeps the
    /// two sides from disagreeing about a time zone that is not in the
    /// value.</para>
    /// </summary>
    public string? PlanDate { get; init; }

    /// <summary>
    /// Foods not to use — what the user already ate today, so the plan does
    /// not repeat a dish they have had.
    /// </summary>
    public IReadOnlyList<string> ExcludeFoodIds { get; init; } = [];

    /// <summary>
    /// The 70-30 mechanism's target share. <c>chk_expl_ratio</c> caps it at
    /// 0.5 in the database and <c>MenuBuilder</c> caps it again.
    /// </summary>
    public double ExplorationRatio { get; init; } = 0.3;

    /// <summary>
    /// Fixes the exploration draw so two runs can be compared. A real
    /// request leaves it null and gets a fresh plan.
    /// </summary>
    public int? Seed { get; init; }
}

/// <summary>One serving of the plan — one row of <c>meal_plan_items</c>.</summary>
public sealed record MlPlanItem
{
    public string FoodId { get; init; } = string.Empty;

    /// <summary>
    /// The Vietnamese name, for the log and for an error message naming the
    /// dish. <b>Not</b> what the client is shown: the backend reads the name
    /// from its own <c>foods</c> row, so one layer decides what a food looks
    /// like on screen.
    /// </summary>
    public string FoodName { get; init; } = string.Empty;

    /// <summary>
    /// A <c>foods.dish_role</c> ENUM code — <c>main</c>,
    /// <c>side_protein</c>, … Never a Vietnamese label: translating a code
    /// to a label happens in the app, right before the UI.
    /// </summary>
    public string DishRole { get; init; } = string.Empty;

    public string MealType { get; init; } = string.Empty;
    public int Kcal { get; init; }
    public double PredictedScore { get; init; }

    /// <summary>
    /// <c>null</c> is an <b>exploitation</b> serving, a number is an
    /// exploration one — exactly what <c>meal_plan_items.exploration_delta</c>
    /// means, which is why there is no <c>isExploration</c> flag beside it.
    /// Writing <c>0</c> instead of <c>null</c> would move the serving into
    /// the exploration group and corrupt the 70-30 measurement.
    /// </summary>
    public double? ExplorationDelta { get; init; }

    public int Position { get; init; }
}

/// <summary>One meal of the plan.</summary>
public sealed record MlPlanMeal
{
    public string MealType { get; init; } = string.Empty;
    public double TargetKcal { get; init; }
    public double ActualKcal { get; init; }
    public double DeviationPct { get; init; }
    public IReadOnlyList<MlPlanItem> Items { get; init; } = [];
}

/// <summary>
/// A day-level nutrient threshold the assembled plan does not satisfy.
/// </summary>
public sealed record MlNutrientCheck
{
    public string Nutrient { get; init; } = string.Empty;

    /// <summary><c>lte</c> or <c>gte</c> — the comparator of the rule.</summary>
    public string Comparator { get; init; } = string.Empty;

    public double Threshold { get; init; }
    public double Actual { get; init; }

    /// <summary>
    /// The condition the rule came from, in Vietnamese
    /// (<c>conditions.name_vi</c>) — it is data, not prose, and it is the
    /// one field here that may be shown to the user.
    /// </summary>
    public string Condition { get; init; } = string.Empty;
}

/// <summary>
/// Step 4's answer: a whole day, assembled but <b>not written</b>. The ML
/// service writes no <c>meal_plans</c> row — that table belongs to this
/// backend, which holds the <c>409 MEAL_PLAN_EXISTS</c> rule and the
/// ownership check.
/// </summary>
public sealed record MlPlanResponse
{
    public string UserId { get; init; } = string.Empty;

    /// <summary>The day the plan is for, <c>YYYY-MM-DD</c>.</summary>
    public string PlanDate { get; init; } = string.Empty;

    /// <summary>
    /// Step 1's numbers as this backend computed and stored them, echoed
    /// back. They go into the <c>meal_plans</c> row beside the result, so the
    /// plan records the target it was actually built against rather than one
    /// recomputed later from a profile the user has since edited.
    /// </summary>
    public double TargetCaloriesKcal { get; init; }

    public double TargetProteinG { get; init; }
    public double TargetCarbsG { get; init; }
    public double TargetFatG { get; init; }

    public double ActualCaloriesKcal { get; init; }
    public double ActualProteinG { get; init; }
    public double ActualCarbsG { get; init; }
    public double ActualFatG { get; init; }

    /// <summary>
    /// What <c>meal_plans.calorie_deviation_pct</c> will compute once the row
    /// exists. Sent so the 10 % commitment can be checked before writing.
    /// </summary>
    public double CalorieDeviationPct { get; init; }

    public bool WithinTolerance { get; init; }

    public double TotalPreferenceScore { get; init; }

    /// <summary>The target share asked for.</summary>
    public double ExplorationRatio { get; init; }

    /// <summary>
    /// The share actually achieved. It can be lower than the target: a meal
    /// whose role has only one safe food left cannot spend a serving on
    /// exploration.
    /// </summary>
    public double ActualExplorationRatio { get; init; }

    /// <summary><c>cold</c>, <c>content</c>, <c>hybrid</c> or <c>ml</c>.</summary>
    public string Stage { get; init; } = string.Empty;

    /// <summary>The blend weight actually used, 0 to 1.</summary>
    public double Alpha { get; init; }

    /// <summary>
    /// One of <see cref="GenerationSource"/> — written straight into
    /// <c>meal_plans.generation_source</c>.
    /// </summary>
    public string GenerationSource { get; init; } = string.Empty;

    /// <summary>
    /// <c>ml_models.version</c>, or <c>null</c> when no model took part. The
    /// backend turns the version into <c>meal_plans.model_id</c>; a version
    /// string that matches no row means the model was deactivated between
    /// the two queries, and the column stays NULL rather than failing the
    /// write.
    /// </summary>
    public string? ModelVersion { get; init; }

    public string FeatureVersion { get; init; } = string.Empty;
    public int NFoodsBeforeF1 { get; init; }
    public int NFoodsAfterF1 { get; init; }

    public IReadOnlyList<MlPlanMeal> Meals { get; init; } = [];

    /// <summary>
    /// Day-level thresholds phase 5 could not satisfy. Empty is good; a
    /// non-empty list has to reach the user rather than hide behind a plan
    /// that looks ordinary.
    /// </summary>
    public IReadOnlyList<MlNutrientCheck> NutrientViolations { get; init; }
        = [];

    /// <summary>
    /// Thresholds on a nutrient the catalogue cannot measure — today only
    /// <c>purine_mg</c>. Kept apart from the violations so that an unchecked
    /// plan is never reported as satisfying them.
    /// </summary>
    public IReadOnlyList<string> UnenforceableTargets { get; init; } = [];

    public bool MeetsNutrientTargets { get; init; }

    public IReadOnlyList<string> Warnings { get; init; } = [];
    public int ElapsedMs { get; init; }
}

/// <summary>§7.4.1 — which foods to ask a new user about.</summary>
public sealed record MlSurveyDeckRequest
{
    public required string UserId { get; init; }

    /// <summary>
    /// 20 to 50. This backend validates the range itself and answers
    /// <c>400 VALIDATION_FAILED</c>, so a bad size never reaches the ML
    /// service; <c>ml/survey.py</c> guards it again anyway.
    /// </summary>
    public int Size { get; init; } = 30;
}

/// <summary>
/// The deck, as <b>ids only</b>.
///
/// <para>No name, image or category label comes back from the ML service:
/// this backend builds every user-facing field from its own tables. Two
/// layers formatting the same food is two places for a Vietnamese label to
/// drift apart.</para>
/// </summary>
public sealed record MlSurveyDeckResponse
{
    public string UserId { get; init; } = string.Empty;

    /// <summary>
    /// <b>In the order picked</b>, which is the order to swipe through: the
    /// first food is the most typical of the catalogue, the later ones
    /// progressively more distinctive.
    /// </summary>
    public IReadOnlyList<string> FoodIds { get; init; } = [];

    public int TotalItems { get; init; }

    /// <summary>
    /// How many <b>opinionated</b> swipes §7.4.1 requires. Never larger than
    /// the deck: when the F1 filter leaves fewer than 20 foods the deck is
    /// shorter, and a minimum nobody could reach would lock that user out of
    /// onboarding altogether.
    /// </summary>
    public int MinRequired { get; init; }

    public int NFoodsBeforeF1 { get; init; }
    public int NFoodsAfterF1 { get; init; }
    public int NCategories { get; init; }
    public int NCategoriesTotal { get; init; }

    public string FeatureVersion { get; init; } = string.Empty;
    public IReadOnlyList<string> Warnings { get; init; } = [];
    public int ElapsedMs { get; init; }
}
