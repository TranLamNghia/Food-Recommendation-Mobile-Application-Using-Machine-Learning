using Api.Ml;

namespace Api.Onboarding;

/// <summary>
/// The Vietnamese sentences the onboarding filter screen shows under its
/// number.
///
/// <para>Built from the counts rather than translated from the ML service's
/// warnings: those are written for a log and name column names, tag ids and
/// thresholds. Each sentence here answers a question the bare number
/// raises, and nothing is said when the number speaks for itself — the
/// normal case returns an empty list.</para>
///
/// <para>Pure, and in its own class, so <c>backend/Api.Tests</c> can state
/// what a given set of counts should say without a database or an HTTP
/// request. The thresholds below are the whole of the logic, and each of
/// them is a decision about when a user needs to be told something.</para>
/// </summary>
public static class CandidateNotes
{
    /// <summary>
    /// How few foods may remain in a role before the screen says the plans
    /// will be repetitive.
    ///
    /// <para>Two. With one or two foods in a required role, a plan is still
    /// assembled — Step 4 needs one — but every day draws the same dish,
    /// the replacement list comes back empty, and the 70-30 exploration has
    /// nothing to pick. Measured on the real catalogue: declaring both a
    /// vegan diet and a soy allergy leaves 102 foods, 2 of them in the
    /// <c>side_protein</c> role.</para>
    /// </summary>
    public const int ThinRole = 2;

    public static List<string> For(
        MlCandidateCountResponse counts, int declaredConditions)
    {
        var notes = new List<string>();

        if (declaredConditions > 0 && counts.NFoods == counts.NFoodsTotal)
        {
            // The question this answers: "I declared hypertension and the
            // number did not move — is it broken?" It is not. Four of the
            // thirteen conditions carry only soft or per-day rules, which
            // lower a food's score and leave it eligible.
            notes.Add(
                "Những khai báo này không loại bỏ món nào khỏi kho món. Một "
                + "số bệnh lý không chặn món cụ thể mà chỉ hạ điểm ưu tiên "
                + "của món đó, hoặc giới hạn theo tổng cả ngày.");
        }

        if (counts.EmptyRequiredRoles.Count > 0)
        {
            notes.Add(
                "Không còn món nào thuộc nhóm "
                + string.Join(", ", counts.EmptyRequiredRoles)
                + ", nên chưa dựng được thực đơn. Vui lòng xem lại phần khai "
                + "báo.");
        }
        else
        {
            // Only when no role is empty. Both notes at once would tell the
            // user their plan is impossible and then that it will be
            // repetitive, which reads as two problems where there is one.
            var thin = counts.ByRole
                .Where(kv => kv.Value > 0 && kv.Value <= ThinRole)
                .Select(kv => kv.Key)
                .OrderBy(r => r, StringComparer.Ordinal)
                .ToList();
            if (thin.Count > 0)
            {
                notes.Add(
                    $"Chỉ còn 1-{ThinRole} món thuộc nhóm "
                    + string.Join(", ", thin)
                    + ", nên thực đơn sẽ ít thay đổi giữa các ngày.");
            }
        }

        if (!counts.EnoughForDeck)
        {
            notes.Add(
                $"Còn {counts.NFoods} món, ít hơn {counts.DeckSize} món của "
                + "phiên khảo sát khẩu vị, nên phiên đó sẽ ngắn hơn.");
        }

        return notes;
    }
}
