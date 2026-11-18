using Api.Catalogue;
using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Ml;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Onboarding;

/// <summary>
/// The taste survey — specification §7.4.
///
/// <para>This is the cold-start answer: a new account has no history, so the
/// system asks. It runs <b>once in the lifetime of an account</b>; after it,
/// preference signals come from the daily meal plan itself — what the user
/// keeps, replaces, eats and rates (§7.6, §7.7, §7.8).</para>
///
/// <para><b>Two calls, not thirty.</b> The deck is fixed for the session, so
/// the app loads it once, swipes entirely offline, and sends the whole
/// session back in one request. There is deliberately no per-swipe endpoint
/// and no progress endpoint: the app already holds that state, and the
/// session is one event in the data.</para>
///
/// <para><b>Which layer does what.</b> The ML service picks the deck
/// (§7.4.1's "maximum diversity" is a traversal of the feature space, and
/// the F1 filter decides eligibility — both live in <c>ml/</c>) and builds
/// the preference vector with Rocchio (§8.2). This controller owns the
/// session id, the <c>interactions</c> rows, the
/// <c>onboarding_completed_at</c> stamp and everything the user sees. No F1
/// filter and no Rocchio is reimplemented here.</para>
///
/// <para><b>Where this departs from §7.4.2, and why.</b> The specification
/// asks for ① write the swipes, ② build the vector, ③ stamp the account, all
/// in <b>one transaction</b>. Step ② happens in another process with its own
/// database connection, which cannot see this one's uncommitted rows — so a
/// single transaction spanning all three is not available, whatever the code
/// looks like. What replaces it:</para>
///
/// <list type="bullet">
/// <item>the swipes are written and committed first, in one transaction, and
/// a re-submission of <b>the same</b> <c>sessionId</c> replaces them rather
/// than adding a second copy, so a retry is safe;</item>
/// <item>the account is stamped <b>only after</b> the vector exists. So the
/// state the specification was protecting against — an account marked as
/// onboarded with no preference profile — cannot occur. The state that can
/// occur is swipes stored with no stamp, which is the recoverable one: the
/// client sends the same body again.</item>
/// </list>
///
/// <para>Note on language: every <c>message</c> passed to <see cref="Fail"/>
/// is Vietnamese — it is the <c>error.message</c> of §2.5 that users read,
/// while <c>error.code</c> is the stable string the app branches on.</para>
/// </summary>
[ApiController]
[Route("api/v1/onboarding/survey")]
[Authorize]
public sealed class SurveyController(
    AppDbContext db,
    IMlClient ml,
    ILogger<SurveyController> log) : ControllerBase
{
    /// <summary>§7.4.1's deck size range, and its default.</summary>
    public const int DeckSizeMin = 20;
    public const int DeckSizeMax = 50;
    public const int DeckSizeDefault = 30;

    /// <summary>
    /// How many <b>opinionated</b> swipes finish the survey.
    ///
    /// <para>The same number as <see cref="DeckSizeMin"/> and not by
    /// accident: below about twenty usable signals the Rocchio vector is
    /// mostly the direction of whichever few foods were swiped, and
    /// <c>ml.rocchio.stage</c> keeps such a user at <c>content</c>
    /// anyway.</para>
    ///
    /// <para>It is a <b>ceiling</b> on the requirement, not the requirement
    /// itself: a user whose conditions leave fewer than twenty safe foods is
    /// asked for all of them instead. See <see cref="RequiredOpinionated"/>
    /// — a fixed twenty would lock that user out of onboarding, and out of
    /// the app, permanently.</para>
    /// </summary>
    public const int MinOpinionated = 20;

    /// <summary>
    /// The <c>interactions.action</c> value that carries no taste
    /// information: "chưa từng ăn". Stored, but not counted and not fed to
    /// the vector.
    /// </summary>
    private const string ActionUnknown = "unknown";

    private ObjectResult Fail(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private ObjectResult Invalid(string field, string message)
        => ApiProblem.Make(
            400, ErrorCode.ValidationFailed, "Dữ liệu gửi lên không hợp lệ",
            HttpContext.TraceIdentifier,
            [new ApiError.FieldError { Field = field, Message = message }]);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.4.1 Get the deck ───────────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> GetDeck(
        [FromQuery] int size = DeckSizeDefault,
        CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        if (size is < DeckSizeMin or > DeckSizeMax)
        {
            return Invalid(
                "size",
                $"Số món phải trong khoảng {DeckSizeMin} đến {DeckSizeMax}");
        }

        if (await Blocked(uid, ct) is { } blocked)
        {
            return blocked;
        }

        var deck = await ml.SurveyDeckAsync(
            new MlSurveyDeckRequest { UserId = uid, Size = size }, ct);
        if (!deck.Ok)
        {
            return Report(deck.Failure!);
        }

        var ids = deck.Required.FoodIds;
        var cards = await FoodCardReader.ReadAsync(db, ids, ct);

        if (cards.Count < ids.Count)
        {
            // A food the ML service chose but this side cannot describe means
            // it has no `food_nutrition` row. Logged with the ids rather than
            // swallowed: the deck is still usable, but the catalogue has a
            // hole, and the same hole makes that food unusable in a meal plan
            // too.
            log.LogWarning(
                "Survey deck: {Missing} of {Total} foods have no "
                + "food_nutrition row and were dropped from the deck: {Ids}",
                ids.Count - cards.Count, ids.Count,
                string.Join(", ", ids.Where(i => !cards.ContainsKey(i))));
        }

        // The ML service's order IS the answer — the first food is the most
        // typical of the catalogue, the later ones progressively more
        // distinctive — so the deck is rebuilt in that order rather than in
        // whatever order the rows came back.
        var items = ids
            .Where(cards.ContainsKey)
            .Select(id => cards[id])
            .Select(c => new SurveyFoodDto
            {
                Id = c.Id,
                Name = c.Name,
                ImageUrl = c.ImageUrl,
                CategoryName = c.CategoryName,
                SpiceLevel = c.SpiceLevel,
                DishRole = c.DishRole,
                CaloriesKcal = c.CaloriesKcal,
                ServingSizeG = c.ServingSizeG,
                Tags = c.Tags,
            })
            .ToList();

        foreach (var warning in deck.Required.Warnings)
        {
            // Information, not warning: these describe the catalogue (294 of
            // 318 foods are not spicy), and they are true on every call. At
            // warning level they would train everyone to ignore the log.
            log.LogInformation("Survey deck for {User}: {Warning}",
                               uid, warning);
        }

        return Ok(new SurveyDeckResponse
        {
            // Minted here, not by the ML service: the session is this
            // backend's unit of work — it is what ties the `interactions`
            // rows together and what makes a re-submission recognisable.
            SessionId = Guid.NewGuid().ToString(),
            TotalItems = items.Count,
            MinRequired = Math.Min(MinOpinionated, items.Count),
            Items = items,
        });
    }

    // ── 7.4.2 Submit the session ─────────────────────────────────────────

    [HttpPost]
    public async Task<IActionResult> Submit(
        SurveySubmitRequest req, CancellationToken ct = default)
    {
        if (UserId is not { } uid)
        {
            return Fail(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        // `sessionId` goes into a CHAR(36) column and is compared as a
        // string. Checked for the UUID shape here so a client sending
        // something else gets a named field back instead of a MySQL
        // truncation error — or, worse, a row that silently stores the first
        // 36 characters of whatever was sent.
        if (!Guid.TryParse(req.SessionId, out var session))
        {
            return Invalid("sessionId", "Mã phiên khảo sát không hợp lệ");
        }

        var swipes = req.Swipes!;

        // `uq_user_condition` has no equivalent here on purpose — the schema
        // deliberately allows a user to swipe the same food twice, in two
        // different survey sessions, so that two sessions can be compared.
        // Within ONE session it is a client bug, and it has to be named: the
        // two answers would both be stored, and Rocchio would count that food
        // twice.
        var duplicates = swipes
            .GroupBy(s => s.FoodId)
            .Where(g => g.Count() > 1)
            .Select(g => g.Key!)
            .ToList();
        if (duplicates.Count > 0)
        {
            return Invalid(
                "swipes",
                "foodId lặp lại: " + string.Join(", ", duplicates));
        }

        var user = await db.Users
            .FirstOrDefaultAsync(u => u.Id == uid, ct);
        if (user is null)
        {
            return Fail(401, ErrorCode.TokenInvalid,
                        "Tài khoản không còn tồn tại");
        }
        if (user.OnboardingCompletedAt is not null)
        {
            return Fail(409, ErrorCode.OnboardingAlreadyCompleted,
                        "Bạn đã hoàn tất khảo sát khẩu vị trước đó");
        }

        var ids = swipes.Select(s => s.FoodId!).ToList();
        var visible = await db.Foods
            .Where(f => ids.Contains(f.Id)
                        && f.IsActive
                        && (f.OwnerId == null || f.OwnerId == uid))
            .Select(f => f.Id)
            .ToListAsync(ct);
        var missing = ids.Except(visible).ToList();
        if (missing.Count > 0)
        {
            // 404 rather than 400: §7.4.2 gives this case `NOT_FOUND`. The
            // ids are echoed back because a deck cached on the device can
            // outlive a food being deactivated, and then the app has to know
            // which card to drop.
            return Fail(404, ErrorCode.NotFound,
                        "Không tìm thấy món ăn: "
                        + string.Join(", ", missing));
        }

        var opinionated = swipes.Count(s => s.Action != ActionUnknown);
        var required = await RequiredOpinionated(uid, opinionated, ct);
        if (required.Problem is { } problem)
        {
            return problem;
        }
        if (opinionated < required.Count)
        {
            return ApiProblem.Make(
                422, ErrorCode.OnboardingInsufficient,
                $"Cần vuốt thêm {required.Count - opinionated} món nữa để "
                + "hoàn tất khảo sát",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "swipes",
                    Message = $"Có {opinionated} lượt có ý kiến, cần tối "
                        + $"thiểu {required.Count}",
                }]);
        }

        // ── ① the swipes, in one transaction ──
        var sessionId = session.ToString();
        var now = Clock.Now;
        await using (var tx = await db.Database.BeginTransactionAsync(ct))
        {
            // Makes a retry of the same session idempotent. Without it, a
            // client that re-sends after the ML service timed out would store
            // every swipe twice and double that food's weight in the vector.
            await db.Interactions
                .Where(i => i.UserId == uid && i.SessionId == sessionId)
                .ExecuteDeleteAsync(ct);

            foreach (var swipe in swipes)
            {
                db.Interactions.Add(new Interactions
                {
                    Id = Guid.NewGuid().ToString(),
                    UserId = uid,
                    FoodId = swipe.FoodId!,
                    Action = swipe.Action!,
                    SessionId = sessionId,
                    // One timestamp for the whole session: §7.4.2 says the
                    // client does not send per-swipe times, because this is
                    // one event in the data.
                    InteractedAt = now,
                });
            }

            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }

        // ── ② the preference vector, in the ML service ──
        //
        // After the commit, necessarily: that service reads the rows over its
        // own connection and cannot see an open transaction's writes.
        var rebuilt = await ml.RebuildProfileAsync(uid, ct);
        if (!rebuilt.Ok)
        {
            // The swipes stay. `onboarding_completed_at` is still NULL, so
            // the client can send exactly this body again and the session
            // replaces itself. Nothing has to be undone, which is why the
            // order is this way round.
            log.LogWarning(
                "Onboarding for {User}: {Count} swipes are stored but the "
                + "preference vector could not be built, so the account is "
                + "NOT marked as onboarded. The same request can be retried. "
                + "{Detail}",
                uid, swipes.Count, rebuilt.Failure!.Detail);
            return Report(rebuilt.Failure!);
        }

        // ── ③ the stamp, last ──
        user.OnboardingCompletedAt = now;
        user.UpdatedAt = now;
        await db.SaveChangesAsync(ct);

        var profile = rebuilt.Required;
        var summary = await BuildTasteSummary(uid, swipes, ct);

        return Ok(new SurveySubmitResponse
        {
            SessionId = sessionId,
            OnboardingCompletedAt = now,
            Recorded = new SurveyRecordedDto
            {
                Total = swipes.Count,
                Opinionated = opinionated,
                Skipped = swipes.Count - opinionated,
                // What the F1 filter removed, derived rather than guessed:
                // the ML service reports how many signals it could actually
                // use, and the gap is the foods this user may not eat.
                // Clamped at 0 because the two numbers come from two
                // processes — a food deactivated between the write and the
                // rebuild would otherwise produce a negative count.
                DroppedUnsafe = Math.Max(
                    0, opinionated - (int)profile.NSignals),
            },
            PreferenceProfile = new SurveyProfileDto
            {
                Stage = profile.Stage,
                NSignals = (int)profile.NSignals,
                Alpha = profile.Alpha,
                FeatureVersion = profile.FeatureVersion,
            },
            TasteSummary = summary,
        });
    }

    // ── shared ───────────────────────────────────────────────────────────

    /// <summary>
    /// The two states that stop a survey before it starts, in the order §4
    /// expects the frontend to resolve them.
    /// </summary>
    private async Task<ObjectResult?> Blocked(
        string uid, CancellationToken ct)
    {
        var completedAt = await db.Users
            .Where(u => u.Id == uid)
            .Select(u => u.OnboardingCompletedAt)
            .FirstOrDefaultAsync(ct);
        if (completedAt is not null)
        {
            return Fail(409, ErrorCode.OnboardingAlreadyCompleted,
                        "Bạn đã hoàn tất khảo sát khẩu vị trước đó");
        }

        // The deck itself needs the user's CONDITIONS, not their profile. The
        // health profile is required because §7.4.1 says so, and because the
        // screen after this one cannot work without Step 1's energy target
        // anyway — finding that out after thirty swipes would waste them.
        var hasProfile = await db.HealthProfiles
            .AnyAsync(h => h.UserId == uid, ct);
        if (!hasProfile)
        {
            return Fail(409, ErrorCode.ProfileRequired,
                        "Chưa khai báo hồ sơ sức khỏe");
        }

        return null;
    }

    /// <summary>
    /// How many opinionated swipes this user has to send:
    /// <see cref="MinOpinionated"/>, or every safe food they have if that is
    /// fewer.
    ///
    /// <para>The ML service is asked only when the submission is already
    /// short, since the answer can never exceed <see cref="MinOpinionated"/>
    /// — so a session with twenty or more opinionated swipes needs no call at
    /// all, and the happy path costs nothing. <c>size</c> is the maximum,
    /// which makes <c>nFoodsAfterF1</c> the true size of this user's safe
    /// pool regardless of what size the deck was fetched with.</para>
    /// </summary>
    private async Task<(int Count, ObjectResult? Problem)>
        RequiredOpinionated(string uid, int opinionated, CancellationToken ct)
    {
        if (opinionated >= MinOpinionated)
        {
            return (MinOpinionated, null);
        }

        var deck = await ml.SurveyDeckAsync(
            new MlSurveyDeckRequest { UserId = uid, Size = DeckSizeMax }, ct);
        if (!deck.Ok)
        {
            return (MinOpinionated, Report(deck.Failure!));
        }

        return (Math.Min(MinOpinionated, deck.Required.NFoodsAfterF1), null);
    }

    /// <summary>
    /// Logs the failure at the level it deserves, then returns the §2.5
    /// envelope for it.
    /// </summary>
    private ObjectResult Report(MlFailure failure)
    {
        if (failure.IsSystemFault())
        {
            log.LogError("Onboarding survey: {Detail}", failure.Detail);
        }
        else
        {
            log.LogInformation("Onboarding survey: {Detail}", failure.Detail);
        }
        return failure.ToActionResult(HttpContext.TraceIdentifier);
    }

    /// <summary>
    /// Reads the nutrition behind this session's swipes and the catalogue's
    /// own averages, and hands both to <see cref="TasteSummaryBuilder"/>.
    ///
    /// <para>Both sides go through <see cref="Facts"/>, so the user's average
    /// and the reference it is compared against are computed by the same
    /// arithmetic. Two expressions for "sodium per gram" is how a comparison
    /// ends up measuring the difference between two formulas.</para>
    /// </summary>
    private async Task<TasteSummaryDto> BuildTasteSummary(
        string uid, List<SurveySwipeDto> swipes, CancellationToken ct)
    {
        var ids = swipes.Select(s => s.FoodId!).ToList();

        var swiped = await NutritionRows(f =>
                ids.Contains(f.Id)
                && (f.OwnerId == null || f.OwnerId == uid))
            .ToListAsync(ct);

        // The reference is the SHARED catalogue only. A private food's
        // figures are self-declared, so letting them move the average would
        // let one user's data change what every other user is told.
        var catalogue = await NutritionRows(f => f.IsActive
                                                 && f.OwnerId == null)
            .ToListAsync(ct);

        var factsById = swiped.ToDictionary(r => r.Id, Facts);
        var pairs = swipes
            .Where(s => factsById.ContainsKey(s.FoodId!))
            .Select(s => (s.Action!, factsById[s.FoodId!]))
            .ToList();

        var reference = catalogue.Select(Facts).ToList();
        var means = new TasteAxisMeans(
            Mean(reference, f => f.SaltyDensity),
            Mean(reference, f => f.SweetDensity),
            Mean(reference, f => f.FattyShare));

        return TasteSummaryBuilder.Build(pairs, means);
    }

    private IQueryable<NutritionRow> NutritionRows(
        System.Linq.Expressions.Expression<Func<Foods, bool>> where)
        => db.Foods
            .Where(where)
            .Join(db.FoodNutrition, f => f.Id, n => n.FoodId,
                  (f, n) => new { Food = f, Nutrition = n })
            .Join(db.FoodCategories, x => x.Food.CategoryId, c => c.Id,
                  (x, c) => new NutritionRow
                  {
                      Id = x.Food.Id,
                      CategoryName = c.Name,
                      SpiceLevel = x.Food.SpiceLevel,
                      ServingSizeG = x.Nutrition.ServingSizeG,
                      ProteinG = x.Nutrition.ProteinG,
                      CarbsG = x.Nutrition.CarbsG,
                      FatG = x.Nutrition.FatG,
                      SugarG = x.Nutrition.SugarG,
                      SodiumMg = x.Nutrition.SodiumMg,
                  });

    private sealed record NutritionRow
    {
        public string Id { get; init; } = string.Empty;
        public string CategoryName { get; init; } = string.Empty;
        public byte SpiceLevel { get; init; }
        public ushort ServingSizeG { get; init; }
        public decimal ProteinG { get; init; }
        public decimal CarbsG { get; init; }
        public decimal FatG { get; init; }
        public decimal? SugarG { get; init; }
        public decimal? SodiumMg { get; init; }
    }

    /// <summary>
    /// One row reduced to the three measured taste axes.
    ///
    /// <para>A <c>null</c> stays <c>null</c>: a food with no sodium figure is
    /// left out of the salt average rather than counted as unsalted. Same for
    /// a zero serving weight, which would otherwise divide by zero and give
    /// an infinity that propagates through every later average.</para>
    /// </summary>
    private static TasteFacts Facts(NutritionRow r)
    {
        var grams = (double)r.ServingSizeG;
        var energy = (double)(r.ProteinG * 4 + r.CarbsG * 4 + r.FatG * 9);
        return new TasteFacts(
            CategoryName: r.CategoryName,
            SpiceLevel: r.SpiceLevel,
            SaltyDensity: grams > 0 && r.SodiumMg is { } sodium
                ? (double)sodium / grams
                : null,
            SweetDensity: grams > 0 && r.SugarG is { } sugar
                ? (double)sugar / grams
                : null,
            FattyShare: energy > 0
                ? (double)r.FatG * 9 / energy
                : null);
    }

    private static double? Mean(
        IReadOnlyList<TasteFacts> foods, Func<TasteFacts, double?> pick)
    {
        var values = foods.Select(pick)
            .Where(v => v is not null)
            .Select(v => v!.Value)
            .ToList();
        return values.Count == 0 ? null : values.Average();
    }
}
