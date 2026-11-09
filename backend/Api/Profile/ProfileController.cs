using Api.Data;
using Api.Entities;
using Api.Http;
using Api.Nutrition;
using Api.Time;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace Api.Profile;

/// <summary>
/// Nhóm Hồ sơ sức khỏe — đặc tả §7.2.1 đến §7.2.5.
///
/// <para>Đợt 2 trong thứ tự hiện thực ở §10.2: đây là <b>Bước 1</b> của thuật
/// toán khuyến nghị, và nó không phụ thuộc ML Service.</para>
///
/// <para>Mọi endpoint ở đây chỉ thao tác trên dữ liệu của chính người đang
/// đăng nhập. <c>userId</c> lấy từ claim <c>sub</c> của token, <b>không bao
/// giờ</b> từ tham số — đặc tả §2.4.</para>
/// </summary>
[ApiController]
[Route("api/v1/profile")]
[Authorize]
public sealed class ProfileController(AppDbContext db) : ControllerBase
{
    private ObjectResult Loi(int status, string code, string message)
        => ApiProblem.Make(status, code, message, HttpContext.TraceIdentifier);

    private string? UserId => User.FindFirst("sub")?.Value;

    // ── 7.2.1 Xem hồ sơ ──────────────────────────────────────────────────

    [HttpGet]
    public async Task<IActionResult> Get()
    {
        if (UserId is not { } uid)
        {
            return Loi(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var ho_so = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        if (ho_so is null)
        {
            // 404, không phải 200 với thân rỗng: Frontend dùng chính mã này
            // để quyết định đẩy người dùng vào màn khai báo hồ sơ.
            return Loi(404, ErrorCode.NotFound, "Chưa khai báo hồ sơ sức khỏe");
        }

        return Ok(await DungHoSo(ho_so));
    }

    // ── 7.2.2 Tạo hoặc cập nhật hồ sơ ────────────────────────────────────

    [HttpPut]
    public async Task<IActionResult> Upsert(UpsertProfileRequest req)
    {
        if (UserId is not { } uid)
        {
            return Loi(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var ngay_sinh = req.DateOfBirth!.Value;
        var hom_nay = DongHo.HomNay;
        var tuoi = NutritionTargets.Age(ngay_sinh, hom_nay);

        // Khoảng tuổi 13–100 ở §7.2.2 KHÔNG có ràng buộc CSDL tương ứng —
        // `health_profiles` chỉ có chk_height và chk_weight. Nên phép kiểm
        // này là tầng duy nhất chặn nó, và bỏ nó đi thì công thức Mifflin sẽ
        // được áp cho một đứa trẻ 5 tuổi, nơi nó không có hiệu lực.
        if (tuoi is < 13 or > 100)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "dateOfBirth",
                    Message = $"Tuổi tính ra {tuoi}, phải trong khoảng 13 đến 100",
                }]);
        }

        var ho_so = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        var tao_moi = ho_so is null;

        if (ho_so is null)
        {
            ho_so = new HealthProfiles
            {
                Id = Guid.NewGuid().ToString(),
                UserId = uid,
                // Ba tỷ lệ macro lấy MẶC ĐỊNH CỦA LƯỢC ĐỒ, không cứng hóa ở
                // đây. 15/60/25 là `DEFAULT` của ba cột target_*_pct, và
                // `chk_macro_sum` buộc chúng cộng đúng 100.
                TargetProteinPct = 15,
                TargetCarbsPct = 60,
                TargetFatPct = 25,
                CreatedAt = DongHo.BayGio,
            };
            db.HealthProfiles.Add(ho_so);
        }

        ho_so.Gender = req.Gender;
        ho_so.DateOfBirth = ngay_sinh;
        ho_so.HeightCm = req.HeightCm!.Value;
        ho_so.WeightKg = req.WeightKg!.Value;
        ho_so.ActivityLevel = req.ActivityLevel;
        ho_so.Goal = req.Goal;
        ho_so.UpdatedAt = DongHo.BayGio;

        // Tính lại Bước 1 ở MỌI lần gọi. Cả sáu trường người dùng sửa được
        // đều chảy vào công thức, nên không có trường hợp nào sửa mà hạn mức
        // giữ nguyên — xem ghi chú "không có cột computed_at" trong
        // db/schema.sql.
        var buoc1 = TinhBuoc1(ho_so, hom_nay);
        ho_so.BmrKcal = LamTron(buoc1.BmrKcal);
        ho_so.TdeeKcal = LamTron(buoc1.TdeeKcal);
        ho_so.DailyCaloriesTarget = LamTron(buoc1.DailyCaloriesTarget);

        await db.SaveChangesAsync();

        // `bmi` là cột GENERATED VIRTUAL — CSDL tính lúc đọc, nên giá trị
        // trong bộ nhớ vẫn là của lần đọc trước. Nạp lại để phản hồi mang
        // đúng con số mà CSDL sẽ trả về sau này.
        await db.Entry(ho_so).ReloadAsync();

        var than = new UpsertProfileResponse
        {
            Profile = await DungHoSo(ho_so),
            NutritionTargets = DungHanMuc(ho_so, buoc1),
        };

        return tao_moi
            ? StatusCode(StatusCodes.Status201Created, than)
            : Ok(than);
    }

    // ── 7.2.3 Xem hạn mức dinh dưỡng ─────────────────────────────────────

    [HttpGet("nutrition-targets")]
    public async Task<IActionResult> GetTargets()
    {
        if (UserId is not { } uid)
        {
            return Loi(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var ho_so = await db.HealthProfiles
            .FirstOrDefaultAsync(h => h.UserId == uid);
        if (ho_so is null)
        {
            // 409 PROFILE_REQUIRED, không 404: tài nguyên "hạn mức" không
            // phải là thứ bị thiếu — nó không tính được vì thiếu một bước
            // trước. Đặc tả §4 nói Frontend phải chuyển tới màn khai báo
            // hồ sơ.
            return Loi(409, ErrorCode.ProfileRequired,
                       "Chưa khai báo hồ sơ sức khỏe");
        }

        // Tính lại chứ không đọc ba cột đã lưu. Ba cột đó là BẢN CHỤP cho
        // thực đơn cũ giữ đúng hạn mức cũ; còn endpoint này trả hạn mức
        // HIỆN TẠI, và nó phải bao gồm cả phần không được lưu — gram macro
        // và phân bổ bữa đều không có cột nào.
        var buoc1 = TinhBuoc1(ho_so, DongHo.HomNay);
        return Ok(DungHanMuc(ho_so, buoc1));
    }

    // ── 7.2.4 Xem bệnh lý của tôi ────────────────────────────────────────

    [HttpGet("conditions")]
    public async Task<IActionResult> GetConditions()
    {
        if (UserId is not { } uid)
        {
            return Loi(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }
        // Mảng thuần, không phân trang — danh sách này tối đa vài phần tử.
        return Ok(await DocBenhLy(uid));
    }

    // ── 7.2.5 Cập nhật bệnh lý ───────────────────────────────────────────

    [HttpPut("conditions")]
    public async Task<IActionResult> PutConditions(
        UpsertConditionsRequest req)
    {
        if (UserId is not { } uid)
        {
            return Loi(401, ErrorCode.TokenInvalid, "Token thiếu `sub`");
        }

        var muon = req.Conditions!;

        // Trùng `conditionId` trong cùng một yêu cầu: `uq_user_condition`
        // sẽ chặn, nhưng bằng một `MySqlException` không nói được trường nào.
        var trung = muon.GroupBy(c => c.ConditionId)
            .Where(g => g.Count() > 1)
            .Select(g => g.Key!.Value)
            .ToList();
        if (trung.Count > 0)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "conditions",
                    Message = "conditionId lặp lại: "
                        + string.Join(", ", trung),
                }]);
        }

        var ma = muon.Select(c => c.ConditionId!.Value).ToList();
        var co_that = await db.Conditions
            .Where(c => ma.Contains(c.Id))
            .Select(c => c.Id)
            .ToListAsync();
        var khong_co = ma.Except(co_that).ToList();
        if (khong_co.Count > 0)
        {
            return ApiProblem.Make(
                400, ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                HttpContext.TraceIdentifier,
                [new ApiError.FieldError
                {
                    Field = "conditions",
                    Message = "conditionId không tồn tại: "
                        + string.Join(", ", khong_co),
                }]);
        }

        // "Thay thế toàn bộ danh sách" (§7.2.5) phải là MỘT giao dịch. Xóa
        // rồi chèn mà không có giao dịch thì một lỗi ở bước chèn sẽ để người
        // dùng ở trạng thái không có bệnh lý nào — nghĩa là Bộ lọc F1 ngừng
        // loại món, và một người dị ứng hải sản sẽ được gợi ý tôm.
        await using var gd = await db.Database.BeginTransactionAsync();

        await db.UserConditions.Where(x => x.UserId == uid)
            .ExecuteDeleteAsync();

        foreach (var c in muon)
        {
            db.UserConditions.Add(new UserConditions
            {
                Id = Guid.NewGuid().ToString(),
                UserId = uid,
                ConditionId = c.ConditionId!.Value,
                Severity = c.Severity,
                Note = string.IsNullOrWhiteSpace(c.Note) ? null : c.Note,
                CreatedAt = DongHo.BayGio,
            });
        }

        await db.SaveChangesAsync();
        await gd.CommitAsync();

        return Ok(await DocBenhLy(uid));
    }

    // ── chung ────────────────────────────────────────────────────────────

    private static Step1Result TinhBuoc1(HealthProfiles h, DateOnly hom_nay)
        => NutritionTargets.Compute(
            h.Gender, h.DateOfBirth, h.HeightCm, h.WeightKg,
            h.ActivityLevel, h.Goal,
            h.TargetProteinPct, h.TargetCarbsPct, h.TargetFatPct,
            hom_nay);

    /// <summary>
    /// Làm tròn về <c>SMALLINT UNSIGNED</c> của lược đồ.
    ///
    /// <para><c>MidpointRounding.AwayFromZero</c> chứ không mặc định:
    /// <c>Math.Round</c> của .NET mặc định làm tròn về số chẵn (2.5 thành 2),
    /// trong khi Dart và Python đều làm tròn ra xa 0. Khác biệt đó chỉ hiện
    /// ra ở đúng những ca .5 — hiếm, nên nó sẽ lọt qua mọi lần thử tay và
    /// chỉ bị bộ kiểm parity bắt.</para>
    /// </summary>
    private static ushort LamTron(decimal v)
        => (ushort)Math.Clamp(
            Math.Round(v, MidpointRounding.AwayFromZero), 0, ushort.MaxValue);

    private async Task<ProfileResponse> DungHoSo(HealthProfiles h)
    {
        var hom_nay = DongHo.HomNay;
        // `bmi` của CSDL là DECIMAL(5,2) đã làm tròn. Dùng nó nếu có, để
        // phản hồi khớp đúng thứ một truy vấn SQL trả về; tính lại chỉ khi
        // dòng chưa qua CSDL.
        var bmi = h.Bmi ?? NutritionTargets.Bmi(h.WeightKg, h.HeightCm);
        return new ProfileResponse
        {
            Gender = h.Gender,
            DateOfBirth = h.DateOfBirth,
            Age = NutritionTargets.Age(h.DateOfBirth, hom_nay),
            HeightCm = h.HeightCm,
            WeightKg = h.WeightKg,
            Bmi = bmi,
            BmiCategory = NutritionTargets.BmiCategory(bmi),
            ActivityLevel = h.ActivityLevel,
            Goal = h.Goal,
            Conditions = await DocBenhLy(h.UserId),
            CreatedAt = h.CreatedAt,
            UpdatedAt = h.UpdatedAt,
        };
    }

    private Task<List<UserConditionDto>> DocBenhLy(string uid)
        => db.UserConditions
            .Where(uc => uc.UserId == uid)
            .Join(db.Conditions, uc => uc.ConditionId, c => c.Id,
                  (uc, c) => new UserConditionDto
                  {
                      ConditionId = c.Id,
                      NameVi = c.NameVi,
                      ConditionType = c.ConditionType,
                      Severity = uc.Severity,
                      Note = uc.Note,
                  })
            .OrderBy(x => x.ConditionId)
            .ToListAsync();

    private static NutritionTargetsResponse DungHanMuc(
        HealthProfiles h, Step1Result k)
        => new()
        {
            Bmi = h.Bmi ?? Math.Round(k.Bmi, 2,
                                      MidpointRounding.AwayFromZero),
            BmiCategory = k.BmiCategory,
            BmrKcal = LamTron(k.BmrKcal),
            TdeeKcal = LamTron(k.TdeeKcal),
            ActivityFactor = k.ActivityFactorValue,
            DailyCaloriesTarget = LamTron(k.DailyCaloriesTarget),
            GoalAdjustmentKcal = (int)Math.Round(
                k.GoalAdjustmentKcal, MidpointRounding.AwayFromZero),
            MacroTargets = new MacroTargetsDto
            {
                ProteinPct = k.ProteinPct,
                // Một chữ số thập phân, như JSON mẫu ở §7.2.3. Gram không
                // cần chính xác hơn thế: bảng thành phần thực phẩm cũng chỉ
                // có một chữ số.
                ProteinG = Math.Round(k.ProteinG, 1,
                                      MidpointRounding.AwayFromZero),
                CarbsPct = k.CarbsPct,
                CarbsG = Math.Round(k.CarbsG, 1,
                                    MidpointRounding.AwayFromZero),
                FatPct = k.FatPct,
                FatG = Math.Round(k.FatG, 1, MidpointRounding.AwayFromZero),
            },
            MealDistribution = k.MealDistribution()
                .Select(m => new MealShareDto
                {
                    MealType = m.MealType,
                    Pct = m.Pct,
                    CaloriesKcal = (int)Math.Round(
                        m.Kcal, MidpointRounding.AwayFromZero),
                })
                .ToList(),
            Formula = new FormulaDto
            {
                Expression = k.FormulaExpression(
                    h.Gender, h.WeightKg, h.HeightCm),
            },
        };
}
