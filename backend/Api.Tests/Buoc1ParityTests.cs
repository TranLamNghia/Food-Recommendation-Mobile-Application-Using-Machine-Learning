using System.Globalization;
using System.Text.Json;
using Api.Nutrition;

namespace Api.Tests;

/// <summary>
/// Bản C# của Bước 1 phải khớp bản tham chiếu Python, từng con số.
///
/// <para>Ca thử nằm ở <c>data/buoc1_cases.json</c>, sinh bởi
/// <c>tools/gen_buoc1_cases.py</c>. Bản tham chiếu trong tệp đó được viết lại
/// từ <c>docs/SYSTEM_ARCHITECTURE.md</c> §3.1, <b>không</b> chép từ lớp này —
/// nếu chép thì nó chỉ xác nhận rằng hai bản cùng sai một kiểu.</para>
///
/// <para>Bài kiểm này KHÔNG cần CSDL và KHÔNG cần máy chủ: lớp
/// <see cref="NutritionTargets"/> là hàm thuần trên số. Phần cần CSDL do
/// <c>tools/smoke_backend.py</c> lo.</para>
/// </summary>
public class Buoc1ParityTests
{
    private static readonly JsonDocument Mau = NapMau();

    private static JsonDocument NapMau()
    {
        // Lần từ thư mục chạy lên gốc repo. `AppContext.BaseDirectory` nằm
        // sâu trong bin/Debug/netX, và độ sâu đó đổi theo cấu hình build —
        // nên tìm theo DẤU HIỆU (có thư mục `db` và tệp `db/schema.sql`)
        // chứ không đếm số bậc.
        var d = new DirectoryInfo(AppContext.BaseDirectory);
        while (d is not null
               && !File.Exists(Path.Combine(d.FullName, "db", "schema.sql")))
        {
            d = d.Parent;
        }
        if (d is null)
        {
            throw new InvalidOperationException(
                "Không tìm thấy gốc repo (dấu hiệu: db/schema.sql) từ "
                + AppContext.BaseDirectory);
        }

        var tep = Path.Combine(d.FullName, "data", "buoc1_cases.json");
        if (!File.Exists(tep))
        {
            throw new FileNotFoundException(
                $"Thiếu {tep}. Sinh bằng: python tools/gen_buoc1_cases.py");
        }
        return JsonDocument.Parse(File.ReadAllText(tep));
    }

    public static TheoryData<string> TenCac_Ca()
    {
        var ra = new TheoryData<string>();
        foreach (var c in Mau.RootElement.GetProperty("cases").EnumerateArray())
        {
            ra.Add(c.GetProperty("ten").GetString()!);
        }
        return ra;
    }

    private static JsonElement Ca(string ten)
        => Mau.RootElement.GetProperty("cases").EnumerateArray()
            .First(c => c.GetProperty("ten").GetString() == ten);

    /// <summary>Làm tròn ra xa 0, như bản Python và như Dart.</summary>
    private static decimal Tron(decimal v, int le = 0)
        => Math.Round(v, le, MidpointRounding.AwayFromZero);

    [Theory]
    [MemberData(nameof(TenCac_Ca))]
    public void Khop_ban_tham_chieu(string ten)
    {
        var ca = Ca(ten);
        var vao = ca.GetProperty("vao");
        var mong = ca.GetProperty("ra");

        var gioi = vao.GetProperty("gender").GetString()!;
        var cao = vao.GetProperty("heightCm").GetDecimal();
        var can = vao.GetProperty("weightKg").GetDecimal();
        var ngay_sinh = DateOnly.Parse(
            vao.GetProperty("dateOfBirth").GetString()!,
            CultureInfo.InvariantCulture);
        var hom_nay = DateOnly.Parse(
            vao.GetProperty("today").GetString()!,
            CultureInfo.InvariantCulture);

        var k = NutritionTargets.Compute(
            gioi,
            ngay_sinh,
            cao,
            can,
            vao.GetProperty("activityLevel").GetString()!,
            vao.GetProperty("goal").GetString()!,
            (byte)vao.GetProperty("proteinPct").GetInt32(),
            (byte)vao.GetProperty("carbsPct").GetInt32(),
            (byte)vao.GetProperty("fatPct").GetInt32(),
            hom_nay);

        Assert.Equal(mong.GetProperty("age").GetInt32(), k.Age);
        Assert.Equal(mong.GetProperty("bmi").GetDecimal(), Tron(k.Bmi, 2));
        Assert.Equal(mong.GetProperty("bmiCategory").GetString(),
                     k.BmiCategory);
        Assert.Equal(mong.GetProperty("bmrKcal").GetDecimal(),
                     Tron(k.BmrKcal));
        Assert.Equal(mong.GetProperty("tdeeKcal").GetDecimal(),
                     Tron(k.TdeeKcal));
        Assert.Equal(mong.GetProperty("activityFactor").GetDecimal(),
                     k.ActivityFactorValue);
        Assert.Equal(mong.GetProperty("dailyCaloriesTarget").GetDecimal(),
                     Tron(k.DailyCaloriesTarget));
        Assert.Equal(mong.GetProperty("goalAdjustmentKcal").GetDecimal(),
                     Tron(k.GoalAdjustmentKcal));
        Assert.Equal(mong.GetProperty("proteinG").GetDecimal(),
                     Tron(k.ProteinG, 1));
        Assert.Equal(mong.GetProperty("carbsG").GetDecimal(),
                     Tron(k.CarbsG, 1));
        Assert.Equal(mong.GetProperty("fatG").GetDecimal(),
                     Tron(k.FatG, 1));

        var bua = k.MealDistribution()
            .ToDictionary(m => m.MealType, m => Tron(m.Kcal));
        foreach (var kv in mong.GetProperty("mealKcal").EnumerateObject())
        {
            Assert.Equal(kv.Value.GetDecimal(), bua[kv.Name]);
        }
    }

    /// <summary>
    /// Hệ số vận động và tỷ lệ bữa phải khớp bảng trong tệp mẫu, cả hai
    /// chiều — thêm một mức vận động vào một bên mà quên bên kia thì mọi ca
    /// thử cũ vẫn đạt.
    /// </summary>
    [Fact]
    public void Bang_he_so_khop_hai_chieu()
    {
        var hs = Mau.RootElement.GetProperty("activityFactor");
        Assert.Equal(
            hs.EnumerateObject().Select(p => p.Name).OrderBy(x => x),
            NutritionTargets.ActivityFactor.Keys.OrderBy(x => x));
        foreach (var p in hs.EnumerateObject())
        {
            Assert.Equal(p.Value.GetDecimal(),
                         NutritionTargets.ActivityFactor[p.Name]);
        }

        var tl = Mau.RootElement.GetProperty("mealShare");
        Assert.Equal(
            tl.EnumerateObject().Select(p => p.Name).OrderBy(x => x),
            NutritionTargets.MealShare.Keys.OrderBy(x => x));
        foreach (var p in tl.EnumerateObject())
        {
            Assert.Equal(p.Value.GetDecimal(),
                         NutritionTargets.MealShare[p.Name]);
        }

        // Bốn tỷ lệ bữa phải cộng đúng 1. Một bộ cộng 0.95 không gây lỗi
        // nào — Bước 4 chỉ đơn giản phân bổ thiếu 5 % năng lượng mỗi ngày.
        Assert.Equal(1.000m, NutritionTargets.MealShare.Values.Sum());
    }

    /// <summary>
    /// Giá trị ngoài ENUM phải NÉM, không được trả về một con số.
    ///
    /// <para>Trả giá trị mặc định thì một chuỗi sai chính tả — `"Male"` thay
    /// vì `"male"` — sẽ cho ra một hạn mức trông hợp lý, tính bằng hằng số
    /// của nhóm khác.</para>
    /// </summary>
    [Theory]
    [InlineData("Male")]
    [InlineData("nam")]
    [InlineData("")]
    public void Gioi_tinh_ngoai_enum_thi_nem(string gioi)
        => Assert.Throws<ArgumentOutOfRangeException>(
            () => NutritionTargets.Bmr(gioi, 68.5m, 172m, 22));

    [Theory]
    [InlineData("Moderate")]
    [InlineData("veryactive")]
    public void Muc_van_dong_ngoai_enum_thi_nem(string v)
        => Assert.Throws<ArgumentOutOfRangeException>(
            () => NutritionTargets.Tdee(1655m, v));

    [Theory]
    [InlineData("lose")]
    [InlineData("maintain_weight")]
    public void Muc_tieu_ngoai_enum_thi_nem(string m)
        => Assert.Throws<ArgumentOutOfRangeException>(
            () => NutritionTargets.EnergyTarget(2565m, 1655m, m));

    /// <summary>
    /// Ba tỷ lệ macro không cộng đủ 100 % thì ném, không âm thầm phân bổ
    /// thiếu năng lượng — `chk_macro_sum` trong lược đồ giữ cùng bất biến.
    /// </summary>
    [Theory]
    [InlineData(15, 60, 24)]
    [InlineData(15, 60, 26)]
    [InlineData(0, 0, 0)]
    public void Macro_khong_cong_100_thi_nem(int p, int c, int f)
        => Assert.Throws<ArgumentException>(() => NutritionTargets.Compute(
            "male", new DateOnly(2004, 1, 1), 172m, 68.5m,
            "moderate", "maintain", (byte)p, (byte)c, (byte)f,
            new DateOnly(2026, 11, 8)));

    /// <summary>
    /// `lose_weight` không bao giờ cho ra hạn mức dưới BMR, với mọi mức vận
    /// động — ăn dưới mức chuyển hóa cơ bản không phải một chế độ giảm cân.
    /// </summary>
    [Fact]
    public void Giam_can_khong_bao_gio_duoi_bmr()
    {
        foreach (var v in NutritionTargets.ActivityFactor.Keys)
        {
            foreach (var g in new[] { "male", "female", "other" })
            {
                var bmr = NutritionTargets.Bmr(g, 45m, 150m, 60);
                var tdee = NutritionTargets.Tdee(bmr, v);
                var hm = NutritionTargets.EnergyTarget(
                    tdee, bmr, "lose_weight");
                Assert.True(hm >= bmr,
                            $"{g}/{v}: hạn mức {hm} thấp hơn BMR {bmr}");
            }
        }
    }
}
