using System.ComponentModel.DataAnnotations;
using System.Reflection;

namespace Api.Profile;

/// <summary>
/// Danh sách giá trị hợp lệ — đặc tả §5.1, trùng khớp từng chữ với ENUM
/// trong CSDL.
///
/// <para>Kiểm bằng danh sách ở tầng này chứ không ánh xạ sang <c>enum</c> của
/// C#: giá trị sai phải ra <c>400 VALIDATION_FAILED</c> kèm tên trường, không
/// phải một lỗi khử tuần tự JSON với thông báo của thư viện.</para>
///
/// <para><b>Bốn danh sách này là nguồn duy nhất.</b> Bản trước khai chúng ở
/// đây rồi viết lại nguyên văn trong từng <c>[InEnum("male", …)]</c>, vì tham
/// số attribute phải là hằng biên dịch nên không truyền được một
/// <c>string[]</c> vào. Hệ quả: lớp này không có chỗ nào đọc, và thêm một giá
/// trị vào đây sẽ KHÔNG đổi gì trong validation mà cũng không báo lỗi.
/// <c>InEnumAttribute</c> giờ nhận <b>tên</b> của danh sách và tra
/// <see cref="Theo_ten"/> lúc chạy, nên <c>[InEnum(nameof(Enums.Gender))]</c>
/// vừa là hằng biên dịch vừa trỏ thật vào mảng ở dưới.</para>
///
/// <para><c>tools/gen_entities.py</c> đối chiếu bốn mảng này với tập giá trị
/// ENUM trong <c>db/schema.sql</c>, cả hai chiều — xem phép kiểm 5 ở đó.</para>
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
    /// {tên trường: danh sách}, dựng bằng phản chiếu từ chính các trường ở
    /// trên — không viết tay, để từ điển không thể lệch khỏi chúng.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, string[]> Theo_ten =
        typeof(Enums)
            .GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(f => f.FieldType == typeof(string[]))
            .ToDictionary(f => f.Name, f => (string[])f.GetValue(null)!);
}

/// <summary>
/// Giá trị phải nằm trong một danh sách của <see cref="Enums"/>.
///
/// <para>Dùng với <c>nameof</c>: <c>[InEnum(nameof(Enums.Gender))]</c>. Đổi
/// tên trường thì <c>nameof</c> đi theo, và phản chiếu dựng lại khóa tương
/// ứng — nên không có cách nào để tên ở đây trỏ vào một danh sách không tồn
/// tại mà vẫn biên dịch được.</para>
/// </summary>
public sealed class InEnumAttribute : ValidationAttribute
{
    private readonly string[] _cho_phep;

    public InEnumAttribute(string ten)
    {
        if (!Enums.Theo_ten.TryGetValue(ten, out var ds))
        {
            throw new ArgumentException(
                $"`{ten}` không phải tên một danh sách trong Api.Profile.Enums",
                nameof(ten));
        }
        _cho_phep = ds;
    }

    public override bool IsValid(object? value)
        => value is string s && _cho_phep.Contains(s);

    public override string FormatErrorMessage(string name)
        => "Giá trị không nằm trong danh sách cho phép: "
            + string.Join(" · ", _cho_phep);
}

/// <summary>Thân của <c>PUT /profile</c> — đặc tả §7.2.2.</summary>
public sealed class UpsertProfileRequest
{
    [Required(ErrorMessage = "Thiếu giới tính")]
    [InEnum(nameof(Enums.Gender))]
    public string Gender { get; set; } = string.Empty;

    [Required(ErrorMessage = "Thiếu ngày sinh")]
    public DateOnly? DateOfBirth { get; set; }

    // Khoảng trùng với `chk_height CHECK (height_cm BETWEEN 50 AND 250)`.
    // Kiểm ở cả hai tầng, có chủ ý: ràng buộc CSDL là tầng bảo đảm cuối, còn
    // tầng này là chỗ duy nhất nói được *trường nào* sai cho người dùng —
    // một `MySqlException` thì không.
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

/// <summary>Một bệnh lý của người dùng — §7.2.4.</summary>
public sealed class UserConditionDto
{
    public uint ConditionId { get; init; }
    public string NameVi { get; init; } = string.Empty;
    public string ConditionType { get; init; } = string.Empty;
    public string Severity { get; init; } = string.Empty;
    public string? Note { get; init; }
}

/// <summary>Hồ sơ sức khỏe đầy đủ — §7.2.1.</summary>
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

/// <summary>Một chất sinh năng lượng trong hạn mức — §7.2.3.</summary>
public sealed class MacroTargetsDto
{
    public byte ProteinPct { get; init; }
    public decimal ProteinG { get; init; }
    public byte CarbsPct { get; init; }
    public decimal CarbsG { get; init; }
    public byte FatPct { get; init; }
    public decimal FatG { get; init; }
}

/// <summary>Một bữa trong phân bổ năng lượng — §7.2.3.</summary>
public sealed class MealShareDto
{
    public string MealType { get; init; } = string.Empty;
    public decimal Pct { get; init; }
    public int CaloriesKcal { get; init; }
}

/// <summary>Công thức BMR, để màn hồ sơ nói con số đến từ đâu — §7.2.3.</summary>
public sealed class FormulaDto
{
    public string Bmr { get; init; } = "Mifflin-St Jeor";
    public string Expression { get; init; } = string.Empty;
}

/// <summary>Đầu ra Bước 1 — §7.2.3.</summary>
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
/// Phản hồi của <c>PUT /profile</c> — §7.2.2 trả hồ sơ <b>kèm</b> hạn mức
/// vừa tính lại, để Frontend không phải gọi thêm một lượt.
/// </summary>
public sealed class UpsertProfileResponse
{
    public ProfileResponse Profile { get; init; } = new();
    public NutritionTargetsResponse NutritionTargets { get; init; } = new();
}

/// <summary>Một phần tử trong thân của <c>PUT /profile/conditions</c>.</summary>
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

/// <summary>Thân của <c>PUT /profile/conditions</c> — §7.2.5.</summary>
public sealed class UpsertConditionsRequest
{
    /// <summary>
    /// Thay thế <b>toàn bộ</b> danh sách. Gửi mảng rỗng để xóa hết.
    ///
    /// <para><c>Required</c> chứ không để mặc định rỗng: thân
    /// <c>{}</c> và thân <c>{"conditions": []}</c> phải khác nhau. Cái thứ
    /// hai là "tôi không có bệnh gì"; cái thứ nhất là một yêu cầu thiếu
    /// trường, và nếu coi nó là mảng rỗng thì một lỗi phía Frontend sẽ âm
    /// thầm xóa sạch bệnh lý của người dùng.</para>
    /// </summary>
    [Required(ErrorMessage = "Thiếu danh sách `conditions`")]
    public List<ConditionInput>? Conditions { get; set; }
}
