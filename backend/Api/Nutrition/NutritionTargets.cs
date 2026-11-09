namespace Api.Nutrition;

/// <summary>
/// Bước 1 của thuật toán khuyến nghị — hạn mức năng lượng và dinh dưỡng.
///
/// <para>Nguồn công thức là <c>docs/SYSTEM_ARCHITECTURE.md</c> §3.1. Đây là
/// bản hiện thực <b>thứ ba</b> của cùng phép tính đó: hai bản kia là
/// <c>mobile/lib/data/models/health_profile.dart</c> và lớp này. Ba bản phải
/// cho ra cùng con số, và <c>tools/check_be_parity.py</c> kiểm điều đó trên
/// 30 ca thử — không có bộ kiểm ấy thì chúng sẽ lệch nhau mà không ai biết,
/// vì mỗi bản chạy ở một tầng khác nhau và không bao giờ gặp nhau.</para>
///
/// <para><b>Lớp này không chạm vào CSDL.</b> Thuần hàm trên số, nên kiểm được
/// mà không cần máy chủ MySQL — đó là điều kiện để bộ kiểm parity chạy được
/// trong một bộ kiểm không có CSDL.</para>
/// </summary>
public static class NutritionTargets
{
    // ── Hệ số vận động (SYSTEM_ARCHITECTURE §3.1) ────────────────────────
    //
    // Khai là chuỗi đúng bằng ENUM `health_profiles.activity_level`, không
    // phải `enum` của C#. Lý do giống chỗ sinh thực thể: CSDL thêm một mức
    // vận động mà mã chưa biết thì phải báo ra ở tầng validation, không phải
    // ném lỗi lúc đọc một dòng dữ liệu hợp lệ.
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
    /// Tỷ lệ năng lượng của từng bữa, theo <b>điểm giữa</b> các khoảng ở
    /// SYSTEM_ARCHITECTURE §3.1: sáng 25–30, trưa 35–40, tối 25–30, phụ 5–10.
    ///
    /// <para>Điểm giữa chứ không phải con số chọn tay, vì một con số chọn tay
    /// không suy ra được từ đâu và hai bên hiện thực sẽ chọn hai bộ khác nhau
    /// — đúng điều đã xảy ra: đặc tả API từng ghi 25/40/27/8 trong khi
    /// <c>meal_plan.dart</c> dùng điểm giữa. Bốn điểm giữa cộng đúng
    /// 100 %.</para>
    /// </summary>
    public static readonly IReadOnlyDictionary<string, decimal> MealShare =
        new Dictionary<string, decimal>
        {
            ["breakfast"] = 0.275m,
            ["lunch"] = 0.375m,
            ["dinner"] = 0.275m,
            ["snack"] = 0.075m,
        };

    /// <summary>Ngưỡng BMI theo khuyến cáo WHO 2004 cho người châu Á.</summary>
    //
    // 23 và 25 chứ không phải 25 và 30 của ngưỡng quốc tế: người châu Á có
    // tỷ lệ mỡ cơ thể và nguy cơ chuyển hóa cao hơn ở cùng một BMI. Dùng
    // ngưỡng quốc tế cho người Việt sẽ xếp một người thừa cân thật vào nhóm
    // "bình thường", và hệ thống sẽ không đề xuất giảm năng lượng.
    public const decimal BmiOverweightAsia = 23.0m;
    public const decimal BmiObeseAsia = 25.0m;

    /// <summary>Tuổi tròn tại <paramref name="on"/>, theo ngày sinh.</summary>
    //
    // Không dùng `(hôm nay - ngày sinh).Days / 365.25`: phép đó cho ra 22 cho
    // một người còn một ngày nữa mới sinh nhật, và BMR lệch 5 kcal theo công
    // thức Mifflin. Nhỏ, nhưng nó làm bản C# lệch bản Dart — bản Dart so
    // tháng rồi so ngày.
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

    /// <summary>BMI = cân nặng(kg) / chiều cao(m)².</summary>
    public static decimal Bmi(decimal weightKg, decimal heightCm)
    {
        var m = heightCm / 100m;
        return weightKg / (m * m);
    }

    /// <summary>
    /// Nhóm BMI theo ngưỡng châu Á: <c>underweight</c> · <c>normal</c> ·
    /// <c>overweight</c> · <c>obese</c>.
    /// </summary>
    public static string BmiCategory(decimal bmi) => bmi switch
    {
        < 18.5m => "underweight",
        < BmiOverweightAsia => "normal",
        < BmiObeseAsia => "overweight",
        _ => "obese",
    };

    /// <summary>
    /// Chuyển hóa cơ bản theo Mifflin-St Jeor.
    ///
    /// <para>Nam: <c>10W + 6.25H − 5A + 5</c>; nữ: <c>… − 161</c>.</para>
    /// </summary>
    //
    // ── `gender = 'other'`: không có hằng số nào được công bố ──
    //
    // ENUM `health_profiles.gender` nhận ba giá trị, nhưng Mifflin-St Jeor
    // chỉ được kiểm định trên hai nhóm nam và nữ — không có công trình nào
    // công bố hằng số cho nhóm thứ ba. Bốn cách xử lý, và vì sao chọn cách
    // cuối:
    //
    //   1. Từ chối với `VALIDATION_FAILED`. Không: CSDL cho phép giá trị đó,
    //      nên API phải nhận được thứ lược đồ cho phép.
    //   2. Dùng hằng số của nam (+5). Không: hạn mức cao hơn, mà sai theo
    //      hướng cho ăn nhiều hơn mức cần là hướng sai tệ hơn.
    //   3. Dùng hằng số của nữ (−161). Nó an toàn cho người giảm cân nhưng
    //      lại thiếu năng lượng cho người đang muốn tăng cân.
    //   4. Trung điểm hai hằng số: (+5 + −161) / 2 = −78.
    //
    // Chọn (4), và phải nói ra rằng đó là một con số SUY RA, không có nguồn
    // — đúng nghĩa `evidence_level = 'derived'` mà lược đồ đã dùng cho
    // `condition_rules`. Đây là một hạn chế thật, phải nêu trong báo cáo.
    //
    // Cách đúng về lâu dài là tách "giới tính dùng cho công thức chuyển hóa"
    // khỏi "giới tính người dùng tự nhận", vì đó là hai câu hỏi khác nhau.
    // Việc đó cần thêm một cột, nên không làm trong lát này.
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
                $"`{gender}` không nằm trong ENUM health_profiles.gender"),
        };
    }

    /// <summary>TDEE = BMR × hệ số vận động.</summary>
    public static decimal Tdee(decimal bmr, string activityLevel)
    {
        if (!ActivityFactor.TryGetValue(activityLevel, out var factor))
        {
            throw new ArgumentOutOfRangeException(
                nameof(activityLevel),
                $"`{activityLevel}` không nằm trong ENUM "
                + "health_profiles.activity_level");
        }
        return bmr * factor;
    }

    /// <summary>
    /// Hạn mức năng lượng theo mục tiêu, kèm ràng buộc an toàn.
    ///
    /// <para><c>lose_weight</c> trừ 500 kcal nhưng <b>không bao giờ xuống
    /// dưới BMR</b>: ăn dưới mức chuyển hóa cơ bản là thiếu năng lượng cho
    /// chính hoạt động sống, không phải một chế độ giảm cân.</para>
    /// </summary>
    public static decimal EnergyTarget(
        decimal tdee, decimal bmr, string goal) => goal switch
        {
            "lose_weight" => Math.Max(tdee - 500m, bmr),
            "gain_weight" => tdee + 500m,
            "maintain" or "healthy_eating" => tdee,
            _ => throw new ArgumentOutOfRangeException(
                nameof(goal),
                $"`{goal}` không nằm trong ENUM health_profiles.goal"),
        };

    /// <summary>Chênh lệch giữa hạn mức và TDEE, để giao diện giải thích.</summary>
    public static decimal GoalAdjustment(decimal energyTarget, decimal tdee)
        => energyTarget - tdee;

    /// <summary>
    /// Gram của một chất, từ phần trăm năng lượng và số kcal mỗi gram.
    /// </summary>
    //
    // 4 kcal/g cho đạm và bột đường, 9 kcal/g cho béo — hệ số Atwater, cũng
    // là hệ số `tools/validate_foods.py` dùng để soát bảng thành phần.
    public const int KcalPerGramProtein = 4;
    public const int KcalPerGramCarbs = 4;
    public const int KcalPerGramFat = 9;

    public static decimal Grams(decimal energyKcal, byte pct, int kcalPerGram)
        => energyKcal * pct / 100m / kcalPerGram;

    /// <summary>
    /// Toàn bộ đầu ra Bước 1 cho một hồ sơ.
    ///
    /// <para>Ba tỷ lệ macro là <b>tham số</b>, đọc từ ba cột
    /// <c>health_profiles.target_*_pct</c>. Cứng hóa chúng ở đây thì sửa một
    /// dòng trong CSDL sẽ không có tác dụng gì, mà cũng không báo lỗi.</para>
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
        // `chk_macro_sum` trong lược đồ đã buộc điều này, nhưng lớp này còn
        // được gọi với số liệu chưa qua CSDL — từ bộ kiểm parity, và từ
        // PUT /profile trước lúc ghi. Kiểm lại ở đây để một bộ ba sai không
        // lặng lẽ cho ra hạn mức không cộng đủ 100 % năng lượng.
        if (proteinPct + carbsPct + fatPct != 100)
        {
            throw new ArgumentException(
                $"ba tỷ lệ macro cộng {proteinPct + carbsPct + fatPct}%, "
                + "phải đúng 100% — xem chk_macro_sum");
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
/// Đầu ra Bước 1, ở <b>độ chính xác đầy đủ</b>.
///
/// <para>Chưa làm tròn, có chủ ý. Lược đồ lưu <c>bmr_kcal</c>,
/// <c>tdee_kcal</c> và <c>daily_calories_target</c> dưới dạng
/// <c>SMALLINT</c>, nên chúng sẽ được làm tròn khi ghi — nhưng phép tính
/// trung gian thì không được làm tròn, và Bước 4 phải chia hạn mức theo
/// <b>tỷ lệ</b> chứ không theo bốn số nguyên đã làm tròn. Tổng bốn số nguyên
/// đó có thể nhỏ hơn hạn mức ngày 1–2 kcal, và nếu Bước 4 coi cả hai là
/// ràng buộc cứng thì không tổ hợp món nào thỏa được cả hai.</para>
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

    /// <summary>Phân bổ năng lượng theo bữa, ở độ chính xác đầy đủ.</summary>
    public IEnumerable<(string MealType, decimal Pct, decimal Kcal)>
        MealDistribution()
        => NutritionTargets.MealShare.Select(
            kv => (kv.Key, kv.Value * 100m, DailyCaloriesTarget * kv.Value));

    /// <summary>Câu công thức BMR, để màn hồ sơ nói con số đến từ đâu.</summary>
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
