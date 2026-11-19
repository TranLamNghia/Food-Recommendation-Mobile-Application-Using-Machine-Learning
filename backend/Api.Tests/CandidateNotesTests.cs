using Api.Onboarding;
using Api.Ml;

namespace Api.Tests;

/// <summary>
/// What the onboarding filter screen says under its number — §7.4.
///
/// <para>Each case below is a number that would otherwise look like a bug to
/// the person reading it: a condition that changes nothing, a role that has
/// run out, a pool too small for the survey. The sentences exist so the
/// screen is not silently wrong, and these tests say when each one
/// appears.</para>
/// </summary>
public class CandidateNotesTests
{
    private static MlCandidateCountResponse Counts(
        int total = 318,
        int remaining = 318,
        Dictionary<string, int>? byRole = null,
        string[]? emptyRoles = null,
        bool enoughForDeck = true)
        => new()
        {
            NFoodsTotal = total,
            NFoods = remaining,
            ByRole = byRole ?? new Dictionary<string, int>
            {
                ["main"] = 89,
                ["side_protein"] = 78,
                ["side_veg"] = 52,
                ["snack"] = 16,
            },
            EmptyRequiredRoles = emptyRoles ?? [],
            EnoughForDeck = enoughForDeck,
            DeckSize = 30,
        };

    [Fact]
    public void A_healthy_count_says_nothing()
    {
        Assert.Empty(CandidateNotes.For(Counts(), declaredConditions: 0));
    }

    /// <summary>
    /// The question this answers: "I declared hypertension and the number did
    /// not move — is it broken?" It is not. Four of the thirteen conditions
    /// carry only soft or per-day rules, which lower a food's score and leave
    /// it in the plan.
    /// </summary>
    [Fact]
    public void A_condition_that_removes_nothing_is_explained()
    {
        var notes = CandidateNotes.For(
            Counts(total: 318, remaining: 318), declaredConditions: 1);

        Assert.Single(notes);
        Assert.Contains("không loại bỏ món nào", notes[0]);
    }

    /// <summary>
    /// With nothing declared the same equality holds, and saying it then
    /// would be telling the user their empty selection filtered nothing.
    /// </summary>
    [Fact]
    public void But_not_before_anything_has_been_declared()
    {
        Assert.Empty(CandidateNotes.For(
            Counts(total: 318, remaining: 318), declaredConditions: 0));
    }

    [Fact]
    public void An_empty_required_role_means_no_plan_is_possible()
    {
        var notes = CandidateNotes.For(
            Counts(
                remaining: 40,
                byRole: new Dictionary<string, int>
                {
                    ["main"] = 12,
                    ["side_veg"] = 28,
                },
                emptyRoles: ["side_protein", "snack"]),
            declaredConditions: 3);

        Assert.Single(notes);
        Assert.Contains("side_protein", notes[0]);
        Assert.Contains("chưa dựng được thực đơn", notes[0]);
    }

    /// <summary>
    /// Measured on the real catalogue: a vegan diet plus a soy allergy leaves
    /// 102 foods, 2 of them in the <c>side_protein</c> role. A plan is still
    /// built — Step 4 needs one — but every day draws the same dish and the
    /// replacement list comes back empty.
    /// </summary>
    [Fact]
    public void A_role_down_to_two_foods_warns_about_repetition()
    {
        var notes = CandidateNotes.For(
            Counts(
                remaining: 102,
                byRole: new Dictionary<string, int>
                {
                    ["main"] = 16,
                    ["side_protein"] = 2,
                    ["side_veg"] = 27,
                    ["snack"] = 10,
                }),
            declaredConditions: 2);

        Assert.Single(notes);
        Assert.Contains("side_protein", notes[0]);
        Assert.Contains("ít thay đổi", notes[0]);
    }

    /// <summary>
    /// Not both at once. Telling the user their plan is impossible and then
    /// that it will be repetitive reads as two problems where there is one.
    /// </summary>
    [Fact]
    public void An_empty_role_silences_the_repetition_warning()
    {
        var notes = CandidateNotes.For(
            Counts(
                remaining: 20,
                byRole: new Dictionary<string, int>
                {
                    ["main"] = 1,
                    ["side_veg"] = 19,
                },
                emptyRoles: ["side_protein"]),
            declaredConditions: 4);

        Assert.Single(notes);
        Assert.Contains("chưa dựng được thực đơn", notes[0]);
    }

    [Fact]
    public void A_pool_too_small_for_the_survey_says_so()
    {
        var notes = CandidateNotes.For(
            Counts(
                remaining: 12,
                byRole: new Dictionary<string, int>
                {
                    ["main"] = 4,
                    ["side_protein"] = 4,
                    ["side_veg"] = 3,
                    ["snack"] = 1,
                },
                enoughForDeck: false),
            declaredConditions: 5);

        // Two notes: one about the thin `snack` role, one about the survey.
        Assert.Equal(2, notes.Count);
        Assert.Contains(notes, n => n.Contains("ít hơn 30 món"));
    }

    /// <summary>
    /// The roles are listed in a fixed order, or the same count would produce
    /// a different sentence on every call and the screen would appear to
    /// flicker between two answers.
    /// </summary>
    [Fact]
    public void Thin_roles_are_listed_in_a_stable_order()
    {
        var byRole = new Dictionary<string, int>
        {
            ["snack"] = 1,
            ["main"] = 40,
            ["side_protein"] = 2,
            ["side_veg"] = 30,
        };

        var first = CandidateNotes.For(
            Counts(remaining: 73, byRole: byRole), declaredConditions: 1);
        var second = CandidateNotes.For(
            Counts(
                remaining: 73,
                byRole: byRole.Reverse()
                    .ToDictionary(kv => kv.Key, kv => kv.Value)),
            declaredConditions: 1);

        Assert.Equal(first, second);
        Assert.Contains("side_protein, snack", first[0]);
    }
}
