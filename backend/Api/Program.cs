using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Api.Auth;
using Api.Data;
using Api.Http;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args);

// ── Cấu hình ─────────────────────────────────────────────────────────────
//
// Chuỗi kết nối và khóa ký JWT đọc từ biến môi trường, KHÔNG từ
// appsettings.json: repo này là repo công khai, và `db/.env` của đề tài đã
// giữ MYSQL_USER / MYSQL_PASSWORD theo đúng cách đó. Một khóa ký nằm trong
// tệp được commit thì mọi ai đọc được repo đều ký được token hợp lệ.
var jwt = new JwtOptions();
builder.Configuration.GetSection(JwtOptions.Section).Bind(jwt);
jwt.SigningKey = builder.Configuration["Jwt:SigningKey"]
    ?? Environment.GetEnvironmentVariable("JWT_SIGNING_KEY")
    ?? string.Empty;

var connection = ChuanHoaChuoiKetNoi(
    builder.Configuration.GetConnectionString("MySql")
    ?? Environment.GetEnvironmentVariable("MYSQL_CONNECTION")
    ?? BuildConnectionFromEnv());

// Dừng ngay lúc khởi động, không chờ tới lượt gọi đầu tiên. Thiếu khóa ký
// mà vẫn chạy được thì máy chủ sẽ phát token ký bằng chuỗi rỗng, và điều đó
// trông hoàn toàn bình thường cho tới khi ai đó thử.
if (jwt.SigningKey.Length < 32)
{
    throw new InvalidOperationException(
        "Thiếu khóa ký JWT, hoặc khóa ngắn hơn 32 ký tự. Đặt biến môi "
        + "trường JWT_SIGNING_KEY (HMAC-SHA256 cần ít nhất 256 bit). "
        + "Sinh một khóa: openssl rand -base64 48");
}

builder.Services.AddSingleton(jwt);
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseMySql(connection, ServerVersion.AutoDetect(connection)));
builder.Services.AddScoped<TokenService>();

builder.Services
    .AddControllers(o =>
    {
        // TOÀN CỤC, có chủ ý. Mọi endpoint đã xác thực phải bị chặn khi tài
        // khoản bị khóa hoặc đã xóa. Còn 38 endpoint chưa làm, và một phép
        // kiểm phải nhớ gõ lại ở từng chỗ là một phép kiểm sẽ bị quên. Bỏ
        // bảo vệ phải tường minh bằng `[AllowAnonymous]`.
        o.Filters.Add<TaiKhoanConHoatDongFilter>();
    })
    .AddJsonOptions(o =>
    {
        // camelCase là mặc định của ASP.NET Core — đặc tả §2.2 đã dựa vào
        // điều đó. Khai tường minh để một bản .NET sau đổi mặc định thì hợp
        // đồng API không lặng lẽ đổi theo.
        o.JsonSerializerOptions.PropertyNamingPolicy =
            JsonNamingPolicy.CamelCase;
        // `null` chứ không phải bỏ trường — đặc tả §2.3: "Trường rỗng là
        // `null`, KHÔNG dùng chuỗi rỗng". Bỏ hẳn trường cũng không được:
        // Frontend phân biệt "chưa khai" với "không có".
        o.JsonSerializerOptions.DefaultIgnoreCondition =
            JsonIgnoreCondition.Never;
    })
    .ConfigureApiBehaviorOptions(o =>
    {
        // Mặc định ASP.NET Core trả RFC 7807 ProblemDetails cho lỗi
        // ModelState. Đặc tả §2.5 dùng một vỏ khác, nên phải thay — nếu
        // không thì lỗi validation là endpoint DUY NHẤT trả sai định dạng,
        // và Frontend sẽ không bóc được `error.code`.
        o.InvalidModelStateResponseFactory = ctx =>
        {
            var details = ctx.ModelState
                .Where(kv => kv.Value?.Errors.Count > 0)
                .SelectMany(kv => kv.Value!.Errors.Select(
                    e => new ApiError.FieldError
                    {
                        Field = JsonNamingPolicy.CamelCase.ConvertName(kv.Key),
                        Message = e.ErrorMessage,
                    }))
                .ToList();

            return ApiProblem.Make(
                StatusCodes.Status400BadRequest,
                ErrorCode.ValidationFailed,
                "Dữ liệu gửi lên không hợp lệ",
                ctx.HttpContext.TraceIdentifier,
                details);
        };
    });

builder.Services.AddOpenApi();

builder.Services
    .AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        // Giữ nguyên tên claim trong token. Mặc định thư viện ánh xạ `sub`
        // thành một URI dài của WS-Federation, và khi đó
        // `User.FindFirst("sub")` trả null — một lỗi im lặng khiến mọi
        // endpoint Protected tưởng không có người dùng nào.
        o.MapInboundClaims = false;
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidIssuer = jwt.Issuer,
            ValidateAudience = true,
            ValidAudience = jwt.Audience,
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(
                Encoding.UTF8.GetBytes(jwt.SigningKey)),
            ValidateLifetime = true,
            // Không có dung sai: mặc định của thư viện là 5 phút, nghĩa là
            // một accessToken "1 giờ" thật ra sống 65 phút. Đặc tả §2.4 nói
            // 1 giờ.
            ClockSkew = TimeSpan.Zero,
            NameClaimType = "sub",
            RoleClaimType = "role",
        };
        o.Events = new JwtBearerEvents
        {
            // Đặc tả §4 phân biệt TOKEN_EXPIRED (gọi /auth/refresh rồi thử
            // lại) với TOKEN_INVALID (đăng xuất). Gộp cả hai thành 401 trơn
            // thì Frontend sẽ đăng xuất người dùng mỗi giờ.
            OnChallenge = async ctx =>
            {
                ctx.HandleResponse();
                var expired = ctx.AuthenticateFailure
                    is SecurityTokenExpiredException;
                ctx.Response.StatusCode = StatusCodes.Status401Unauthorized;
                ctx.Response.ContentType = "application/json; charset=utf-8";
                await ctx.Response.WriteAsync(JsonSerializer.Serialize(
                    new ApiError
                    {
                        Error = new ApiError.ErrorBody
                        {
                            Code = expired
                                ? ErrorCode.TokenExpired
                                : ErrorCode.TokenInvalid,
                            Message = expired
                                ? "accessToken đã hết hạn"
                                : "Token không hợp lệ hoặc đã bị thu hồi",
                            TraceId = ctx.HttpContext.TraceIdentifier,
                        },
                    },
                    new JsonSerializerOptions
                    {
                        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                        DefaultIgnoreCondition =
                            JsonIgnoreCondition.WhenWritingNull,
                    }));
            },
        };
    });

builder.Services.AddAuthorization();

var app = builder.Build();

// ── Lỗi chưa bắt được cũng phải theo đúng vỏ §2.5 ────────────────────────
//
// Không có chỗ này thì một ngoại lệ bất ngờ trả về trang lỗi HTML của
// Kestrel, và Frontend cố bóc JSON từ nó sẽ báo một lỗi hoàn toàn khác với
// lỗi thật.
app.UseExceptionHandler(nhanh => nhanh.Run(async ctx =>
{
    var loi = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    app.Logger.LogError(loi, "Lỗi chưa bắt được ở {Path}", ctx.Request.Path);

    ctx.Response.StatusCode = StatusCodes.Status500InternalServerError;
    ctx.Response.ContentType = "application/json; charset=utf-8";
    await ctx.Response.WriteAsync(JsonSerializer.Serialize(
        new ApiError
        {
            Error = new ApiError.ErrorBody
            {
                Code = ErrorCode.InternalError,
                // Không trả `loi.Message` ra ngoài: nó có thể chứa chuỗi kết
                // nối, tên bảng hoặc câu SQL.
                Message = "Lỗi máy chủ, vui lòng thử lại",
                TraceId = ctx.TraceIdentifier,
            },
        },
        new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        }));
}));

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

app.Run();

// ── Chuỗi kết nối dựng từ cùng bộ biến môi trường mà tools/ đang dùng ────
//
// `tools/_env.py` đọc MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
// MYSQL_DATABASE từ `.env`. Dùng lại đúng bộ tên đó để không phải khai cùng
// một CSDL ở hai chỗ với hai cách gọi khác nhau.
/// <summary>
/// Buộc <c>GuidFormat=None</c>, vì mặc định của MySqlConnector làm mọi cột
/// <c>CHAR(36)</c> đọc ra thành <c>System.Guid</c>.
/// </summary>
//
// Lược đồ có 45 cột CHAR(36), và cả 45 đều là UUID: id, user_id, food_id,
// meal_plan_id, category_id, owner_id, session_id, batch_id, replaced_by,
// replaced_by_food_id. MySqlConnector mặc định `GuidFormat=Char36`, nên nó
// coi mọi CHAR(36) là một Guid và trả về `System.Guid` — còn thực thể khai
// `string`, nên EF ném `InvalidCastException: Unable to cast object of type
// 'System.Guid' to type 'System.String'` ở lượt ĐỌC đầu tiên.
//
// Hai cách sửa, và vì sao chọn cách này:
//
//   1. Khai thực thể là `Guid`. Kiểu chặt hơn, nhưng đặc tả §2.3 nói rõ khóa
//      chính là "chuỗi UUID 36 ký tự", và mọi truy vấn trong hệ thống — kể
//      cả `tools/*.py` và `ml/*.py` — so chúng như chuỗi. Thêm một phép quy
//      đổi ở biên là thêm một chỗ hai bên có thể lệch định dạng.
//   2. `GuidFormat=None`: CHAR(36) đọc ra đúng là chuỗi. Không có cột
//      BINARY(16) nào trong lược đồ, nên tắt hẳn hỗ trợ Guid không mất gì.
//
// Đặt ở đây chứ không chỉ trong `BuildConnectionFromEnv`, để chuỗi kết nối
// do người dùng tự khai qua `MYSQL_CONNECTION` cũng được chuẩn hóa — nếu
// không thì cấu hình đó sẽ vỡ theo đúng cách này mà không có dấu hiệu gì.
//
// Qua `MySqlConnectionStringBuilder` chứ không nối chuỗi: bản trước kiểm
// `chuoi.Contains("GuidFormat")` rồi dán thêm `;GuidFormat=None;` vào cuối,
// nên một chuỗi đã khai `GuidFormat=Char36` sẽ được GIỮ NGUYÊN — đúng cấu
// hình làm mọi cột CHAR(36) đọc ra `System.Guid` và vỡ ở lượt đọc đầu tiên.
// Thực thể khai `string`, nên ở đây ghi đè, không nhường.
static string ChuanHoaChuoiKetNoi(string chuoi)
{
    MySqlConnectionStringBuilder b;
    try
    {
        b = new MySqlConnectionStringBuilder(chuoi);
    }
    catch (Exception loi)
    {
        throw new InvalidOperationException(
            "Chuỗi kết nối MySQL không đọc được. Mật khẩu chứa `;` hoặc `\"` "
            + "thì phải bọc trong dấu nháy đơn: Password='a;b'.", loi);
    }
    b.GuidFormat = MySqlGuidFormat.None;
    return b.ConnectionString;
}

static string BuildConnectionFromEnv()
{
    string? Get(string ten) => Environment.GetEnvironmentVariable(ten);

    var user = Get("MYSQL_USER");
    var pass = Get("MYSQL_PASSWORD");

    if (string.IsNullOrEmpty(user) || string.IsNullOrEmpty(pass))
    {
        throw new InvalidOperationException(
            "Thiếu chuỗi kết nối MySQL. Đặt ConnectionStrings:MySql, hoặc "
            + "MYSQL_CONNECTION, hoặc bộ MYSQL_USER / MYSQL_PASSWORD / "
            + "MYSQL_DATABASE như tools/_env.py đang dùng.");
    }

    var cong = Get("MYSQL_PORT");

    // Builder chứ không nội suy chuỗi. `;` trong mật khẩu kết thúc một cặp
    // khóa–giá trị, nên nối tay thì phần sau dấu đó bị đọc thành TÙY CHỌN
    // kết nối: mật khẩu `a;b` cho ra `Password=a` rồi một tùy chọn tên `b`.
    // Lỗi đó không hiện ra hôm nay — nó hiện ra vào ngày đổi mật khẩu CSDL.
    var b = new MySqlConnectionStringBuilder
    {
        Server = Get("MYSQL_HOST") ?? "localhost",
        Port = uint.TryParse(cong, out var p) ? p : 3306u,
        Database = Get("MYSQL_DATABASE") ?? "nutrition_rec",
        UserID = user,
        Password = pass,
        CharacterSet = "utf8mb4",
    };
    return b.ConnectionString;
}
