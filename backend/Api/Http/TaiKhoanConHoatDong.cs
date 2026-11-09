using Api.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;
using Microsoft.EntityFrameworkCore;

namespace Api.Http;

/// <summary>
/// Chặn mọi yêu cầu đã xác thực của một tài khoản <b>không còn hoạt động</b>
/// hoặc đã bị xóa.
///
/// <para><b>Vì sao là bộ lọc toàn cục chứ không phải một phép kiểm trong
/// từng controller.</b> Bản trước kiểm <c>IsActive</c> ở
/// <c>/auth/login</c>, <c>/auth/refresh</c> và <c>/auth/me</c> — bốn chỗ —
/// nhưng KHÔNG kiểm ở bất cứ endpoint nào của <c>/profile</c>. Tài khoản bị
/// khóa vẫn đọc và ghi hồ sơ được tới một giờ, tức tới khi accessToken hết
/// hạn. Còn 34 endpoint công khai và 4 endpoint nội bộ chưa làm; một phép
/// kiểm phải nhớ gõ lại ở từng endpoint là một phép kiểm sẽ bị quên, và lúc
/// quên thì không có gì báo ra.</para>
///
/// <para>Đăng ký toàn cục trong <c>Program.cs</c> nên endpoint mới được bảo
/// vệ <b>mặc định</b>, không cần ai nhớ gì. Bỏ bảo vệ phải là hành động
/// tường minh: thêm <c>[AllowAnonymous]</c>.</para>
///
/// <para><b>Không áp cho <c>/auth/login</c> và <c>/auth/refresh</c></b>: hai
/// endpoint đó <c>[AllowAnonymous]</c> và xác thực bằng mật khẩu hoặc bằng
/// refreshToken, không bằng accessToken, nên không có claim <c>sub</c> để
/// tra. Chúng giữ phép kiểm <c>IsActive</c> riêng, và đó không phải trùng
/// lặp — đó là hai đường vào khác nhau.</para>
///
/// <para>Chi phí: một <c>SELECT is_active FROM users WHERE id = ?</c> theo
/// khóa chính cho mỗi yêu cầu đã xác thực. Đổi lấy việc không thể quên thì
/// đáng.</para>
/// </summary>
public sealed class TaiKhoanConHoatDongFilter(AppDbContext db)
    : IAsyncAuthorizationFilter
{
    public async Task OnAuthorizationAsync(AuthorizationFilterContext ctx)
    {
        // `[AllowAnonymous]` thì không có gì để tra. Kiểm cả metadata của
        // endpoint, vì đó là chỗ `[AllowAnonymous]` thật sự nằm sau khi
        // routing đã chạy.
        var endpoint = ctx.HttpContext.GetEndpoint();
        if (endpoint?.Metadata.GetMetadata<IAllowAnonymous>() is not null)
        {
            return;
        }

        // Chưa xác thực được thì để tầng JwtBearer trả 401 với đúng mã
        // TOKEN_EXPIRED / TOKEN_INVALID — xem `OnChallenge` ở Program.cs.
        if (ctx.HttpContext.User.Identity?.IsAuthenticated is not true)
        {
            return;
        }

        var uid = ctx.HttpContext.User.FindFirst("sub")?.Value;
        if (string.IsNullOrEmpty(uid))
        {
            ctx.Result = Tra(ctx, StatusCodes.Status401Unauthorized,
                             ErrorCode.TokenInvalid, "Token thiếu `sub`");
            return;
        }

        // Một cột, không cả dòng. `bool?` phân biệt được ba trạng thái:
        // không có dòng nào (null), có mà bị khóa (false), bình thường
        // (true).
        var con = await db.Users
            .Where(u => u.Id == uid)
            .Select(u => (bool?)u.IsActive)
            .FirstOrDefaultAsync();

        if (con is null)
        {
            // Token hợp lệ về chữ ký nhưng người dùng đã bị xóa khỏi CSDL.
            // 401 chứ không 403: không còn tài khoản nào để nói là bị khóa.
            ctx.Result = Tra(ctx, StatusCodes.Status401Unauthorized,
                             ErrorCode.TokenInvalid,
                             "Tài khoản không còn tồn tại");
            return;
        }

        if (con is false)
        {
            ctx.Result = Tra(ctx, StatusCodes.Status403Forbidden,
                             ErrorCode.AccountDisabled,
                             "Tài khoản đã bị khóa, vui lòng liên hệ quản trị");
        }
    }

    private static ObjectResult Tra(
        AuthorizationFilterContext ctx, int status, string code, string message)
        => ApiProblem.Make(status, code, message,
                           ctx.HttpContext.TraceIdentifier);
}
