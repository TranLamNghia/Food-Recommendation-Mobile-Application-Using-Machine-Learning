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

    /// <summary>
    /// Which meals to assemble. <c>null</c>, or all four, builds the whole
    /// day.
    ///
    /// <para>A subset rebuilds those meals <b>inside the plan already stored
    /// for that date</b> and keeps the rest — §7.6's "sinh lại một bữa". The
    /// ML service reads the kept servings from the database itself, so they
    /// are not sent here; it needs them to count the day's energy and every
    /// per-day threshold, which is what keeps
    /// <c>calorie_deviation_pct</c> a figure about a day.</para>
    ///
    /// <para>Without a stored plan for that date the answer is
    /// <c>MEAL_PLAN_REQUIRED</c>. This backend checks the plan exists first,
    /// so seeing that code means a bug on this side.</para>
    /// </summary>
    public IReadOnlyList<string>? MealTypes { get; init; }
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

    /// <summary>
    /// This serving's energy, <b>portion included</b>, so a meal's items add
    /// up to its <c>ActualKcal</c>. A <c>double</c> and not an <c>int</c>:
    /// a portion of 1.5 makes it fractional, and nine servings each rounded
    /// to a whole kcal would no longer sum to the total they are checked
    /// against.
    /// </summary>
    public double Kcal { get; init; }

    /// <summary>
    /// Servings on the plate, for <c>meal_plan_items.portion_multiplier</c>.
    /// Always 1.0 for a serving Step 4 picked — it chooses dishes, not
    /// portions. Another value belongs to a kept serving of a partly
    /// rebuilt day, because §7.6.5 lets a user ask for a different weight.
    /// </summary>
    public double Portion { get; init; } = 1.0;

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

/// <summary>§7.5 — which foods a user may not eat, and under which rule.</summary>
public sealed record MlFoodSafetyRequest
{
    public required string UserId { get; init; }

    /// <summary>
    /// <c>null</c> asks about every active food this user can see. A list
    /// narrows it, for a detail screen asking about one dish.
    /// </summary>
    public IReadOnlyList<string>? FoodIds { get; init; }
}

/// <summary>
/// One hard rule a food violates — the parts, not a sentence.
///
/// <para>The Vietnamese prose the user reads is composed on this side, from
/// these fields. The ML service sends codes, names and numbers; the layer
/// that talks to the user writes the words. <see cref="Condition"/> is the
/// exception and is already Vietnamese, because it is
/// <c>conditions.name_vi</c> — data, not prose.</para>
/// </summary>
public sealed record MlExclusionReason
{
    /// <summary>
    /// <c>exclude_tag</c> · <c>require_tag</c> · <c>nutrient_limit</c> — or
    /// <c>user_blocked</c>, which is not a value of
    /// <c>condition_rules.rule_type</c> at all: it is the user's own
    /// "do not suggest this", and it arrives with
    /// <see cref="Condition"/> empty.
    /// </summary>
    public string RuleType { get; init; } = string.Empty;

    /// <summary>
    /// Empty for <c>user_blocked</c>. There is no condition behind that one,
    /// and naming one would blame the user's own decision on a medical rule.
    /// </summary>
    public string Condition { get; init; } = string.Empty;
    public string SeverityMin { get; init; } = string.Empty;

    /// <summary>The tag that excluded it, for a tag rule.</summary>
    public string? Tag { get; init; }

    public string? Nutrient { get; init; }
    public string? Comparator { get; init; }
    public double? Threshold { get; init; }

    /// <summary>
    /// The food's own measurement. <c>null</c> means <b>no data</b>, not
    /// zero — and at a per-serving threshold, no data is itself the reason
    /// for exclusion, because the food cannot be shown to be safe.
    /// </summary>
    public double? Value { get; init; }

    /// <summary>
    /// <c>true</c> when the food was excluded for a MISSING measurement
    /// rather than for exceeding one. The two need different words on
    /// screen: "vượt ngưỡng" against "chưa có số liệu".
    /// </summary>
    public bool MissingData { get; init; }

    public string EvidenceLevel { get; init; } = string.Empty;

    /// <summary>Whether the threshold may be quoted as a sourced figure.</summary>
    public bool Citable { get; init; }

    public string Note { get; init; } = string.Empty;
}

/// <summary>One unsafe food, with every rule it breaks.</summary>
public sealed record MlFoodSafetyItem
{
    public string FoodId { get; init; } = string.Empty;

    /// <summary>
    /// All of them, not the first. Fixing one rule does not make the dish
    /// acceptable, so the user has to see them all.
    /// </summary>
    public IReadOnlyList<MlExclusionReason> Reasons { get; init; } = [];
}

/// <inheritdoc cref="MlFoodSafetyRequest"/>
public sealed record MlFoodSafetyResponse
{
    public string UserId { get; init; } = string.Empty;

    public IReadOnlyList<string> SafeFoodIds { get; init; } = [];
    public IReadOnlyList<MlFoodSafetyItem> Unsafe { get; init; } = [];

    public int NFoodsBeforeF1 { get; init; }
    public int NFoodsAfterF1 { get; init; }

    /// <summary>
    /// Ids asked about that are in neither list: inactive, deleted, or
    /// another user's private food. A detail screen needs the difference
    /// between "unsafe" and "not there".
    /// </summary>
    public IReadOnlyList<string> UnknownFoodIds { get; init; } = [];

    public int ElapsedMs { get; init; }
}

/// <summary>One condition ticked on the onboarding filter screen.</summary>
public sealed record MlCondition
{
    public required int ConditionId { get; init; }

    /// <summary>
    /// <c>mild</c> · <c>moderate</c> · <c>severe</c>. A rule applies only
    /// from its own <c>severity_min</c> upwards, so the same condition
    /// removes different foods at different severities.
    /// </summary>
    public string Severity { get; init; } = "moderate";
}

/// <summary>
/// §7.4 — how many foods would be left if these conditions were declared.
///
/// <para>Hypothetical on purpose: nothing is saved, and the ML service does
/// not read <c>user_conditions</c>. That is what the filter screen needs —
/// it asks the question while the user is still answering.</para>
/// </summary>
public sealed record MlCandidateCountRequest
{
    /// <summary>
    /// Optional, and it only widens the food <b>scope</b> so the user's own
    /// private foods become visible. The conditions applied are always the
    /// ones sent.
    /// </summary>
    public string? UserId { get; init; }

    public IReadOnlyList<MlCondition> Conditions { get; init; } = [];
}

/// <summary>What the filter screen shows after one answer.</summary>
public sealed record MlCandidateCountResponse
{
    public int NFoodsTotal { get; init; }
    public int NFoods { get; init; }

    /// <summary>
    /// The remainder by <c>dish_role</c>. Reported, never used to refuse
    /// anything: the filtering goes by the hard safety rules alone. It is
    /// here because the total is not the number that binds — 102 foods with
    /// 2 of them in the <c>side_protein</c> role still builds a lunch, with
    /// no alternative left to offer and nothing for the 70-30 mechanism to
    /// draw.
    /// </summary>
    public IReadOnlyDictionary<string, int> ByRole { get; init; }
        = new Dictionary<string, int>();

    /// <summary>
    /// Required roles of the meal structure with nothing left in them.
    /// Non-empty means no plan can be assembled at all, whatever the total.
    /// </summary>
    public IReadOnlyList<string> EmptyRequiredRoles { get; init; } = [];

    public bool EnoughForDeck { get; init; }
    public int DeckSize { get; init; }

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
