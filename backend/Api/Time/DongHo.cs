namespace Api.Time;

/// <summary>
/// Đồng hồ của hệ thống. <b>Một múi giờ duy nhất: Asia/Ho_Chi_Minh.</b>
///
/// <para>Tồn tại vì ba tầng của đề tài từng đọc ba đồng hồ khác nhau:</para>
///
/// <list type="bullet">
/// <item>CSDL: 27 cột <c>DEFAULT CURRENT_TIMESTAMP</c>, và mọi câu
/// <c>INSERT … NOW()</c> trong <c>tools/*.py</c>. Cả hai trả theo
/// <c>@@session.time_zone</c>, mặc định là <c>SYSTEM</c> — tức giờ máy, tức
/// giờ Việt Nam.</item>
/// <item>Ứng dụng Flutter: <c>DateTime.now()</c>, giờ địa phương.</item>
/// <item>Backend: <c>DateTime.UtcNow</c> — <b>lệch 7 giờ so với cả hai</b>.</item>
/// </list>
///
/// <para>Hậu quả thì im lặng. <c>users.created_at</c> do Backend ghi lùi 7
/// giờ so với dòng do <c>check_ml_e2e.py</c> ghi, nên sắp theo
/// <c>created_at</c> là trộn hai đồng hồ. Và tệ hơn: "hôm nay" tính bằng
/// <c>UtcNow</c> lùi một NGÀY so với app trong khoảng 00:00–07:00 mỗi đêm,
/// nên đúng ngày sinh nhật app hiện 23 tuổi còn <c>GET /profile</c> trả
/// <c>age: 22</c>, kéo theo BMR lệch 5 kcal vì Mifflin có số hạng
/// <c>− 5 × tuổi</c>.</para>
///
/// <para><b>Bộ kiểm parity không bắt được chỗ đó</b>: nó ghim <c>today</c> ở
/// cả ba bản hiện thực, đúng như phải làm để khóa công thức — nhưng nguồn
/// đồng hồ nằm ngoài thứ được khóa.</para>
///
/// <para>Chọn giờ Việt Nam chứ không chọn UTC vì đó là thứ CSDL ĐANG lưu:
/// đổi sang UTC thì phải sửa 27 giá trị mặc định của lược đồ, mọi
/// <c>NOW()</c> trong <c>tools/</c>, và dữ liệu đã ghi. Người dùng cũng ở
/// một múi giờ duy nhất.</para>
/// </summary>
public static class DongHo
{
    /// <summary>
    /// Việt Nam không dùng giờ mùa hè từ 1975, nên múi giờ này cố định
    /// <c>+07:00</c>. Vẫn tra theo TÊN chứ không gán cứng độ lệch, để nếu
    /// điều đó đổi thì chỉ cần cập nhật cơ sở dữ liệu múi giờ của hệ thống.
    /// </summary>
    public static readonly TimeZoneInfo MuiGio = Tra();

    private static TimeZoneInfo Tra()
    {
        // Tên IANA là tên .NET dùng trên Linux và, từ .NET 6, cả trên
        // Windows qua ICU. Dự phòng tên Windows cũ cho máy chạy ở chế độ
        // globalization-invariant, nơi tra tên IANA sẽ ném.
        foreach (var ten in new[] { "Asia/Ho_Chi_Minh", "SE Asia Standard Time" })
        {
            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(ten);
            }
            catch (TimeZoneNotFoundException) { }
            catch (InvalidTimeZoneException) { }
        }
        throw new InvalidOperationException(
            "Không tìm thấy múi giờ Asia/Ho_Chi_Minh. Máy chủ thiếu cơ sở dữ "
            + "liệu múi giờ (tzdata), hoặc đang chạy ở chế độ "
            + "globalization-invariant.");
    }

    /// <summary>
    /// Thời điểm hiện tại theo giờ Việt Nam — dùng cho MỌI cột
    /// <c>DATETIME</c>, để khớp <c>CURRENT_TIMESTAMP</c> của lược đồ.
    /// </summary>
    public static DateTime BayGio
        => TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, MuiGio);

    /// <summary>
    /// Ngày hôm nay theo giờ Việt Nam — dùng cho MỌI cột <c>DATE</c> và cho
    /// mọi phép tính theo ngày lịch: tuổi, <c>food_diary.ate_on</c>,
    /// <c>body_logs.logged_on</c>.
    /// </summary>
    public static DateOnly HomNay => DateOnly.FromDateTime(BayGio);
}
