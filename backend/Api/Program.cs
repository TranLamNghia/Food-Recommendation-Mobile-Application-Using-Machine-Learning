using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Api.Auth;
using Api.Data;
using Api.Http;
using Api.Ml;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.JsonWebTokens;
using Microsoft.IdentityModel.Tokens;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args);

// ── Configuration ───────────────────────────────────────────────────────
//
// The connection string and the JWT signing key are read from environment
// variables, NOT from appsettings.json: this repository is public, and the
// project's `db/.env` already keeps MYSQL_USER / MYSQL_PASSWORD that way. A
// signing key sitting in a committed file means anyone who can read the
// repository can sign valid tokens.
//
// Note on language: every `Message` written into an `ApiError` below stays in
// Vietnamese. Those are the `error.message` of specification §2.5, which end
// users read; `error.code` is the stable string the frontend branches on.
// Startup exceptions and log lines are developer-facing, so they are in
// English.
var jwt = new JwtOptions();
builder.Configuration.GetSection(JwtOptions.Section).Bind(jwt);
jwt.SigningKey = builder.Configuration["Jwt:SigningKey"]
    ?? Environment.GetEnvironmentVariable("JWT_SIGNING_KEY")
    ?? string.Empty;

var connection = NormalizeConnectionString(
    builder.Configuration.GetConnectionString("MySql")
    ?? Environment.GetEnvironmentVariable("MYSQL_CONNECTION")
    ?? BuildConnectionFromEnv());

// Stop right at startup rather than waiting for the first call. Running
// without a signing key would have the server issue tokens signed with the
// empty string, and that looks perfectly normal until somebody tries it.
if (jwt.SigningKey.Length < 32)
{
    throw new InvalidOperationException(
        "The JWT signing key is missing, or shorter than 32 characters. Set "
        + "the JWT_SIGNING_KEY environment variable (HMAC-SHA256 needs at "
        + "least 256 bits). To generate one: openssl rand -base64 48");
}

builder.Services.AddSingleton(jwt);
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseMySql(connection, ServerVersion.AutoDetect(connection)));
builder.Services.AddScoped<TokenService>();

// ── The ML service client — specification §8 ────────────────────────────
//
// Deliberately NOT a startup check. `jwt.SigningKey` above throws when it is
// missing, because a server issuing tokens signed with the empty string is
// worse than a server that does not start. The ML key is the opposite case:
// §8.1 requires the backend to keep building meal plans when the ML service
// is unreachable, so refusing to start without the key would turn an
// optional dependency into a required one. A missing key instead makes every
// call return `MlFailureKind.Disabled`, and `MlClient` logs that once at
// error level — see the note on `MlOptions`.
var ml = MlOptions.FromConfiguration(builder.Configuration);
builder.Services.AddSingleton(ml);
builder.Services
    .AddHttpClient<IMlClient, MlClient>(c =>
    {
        c.BaseAddress = new Uri(ml.BaseUrl);
        // Belt as well as braces. `MlClient` enforces the §8.1 budget with a
        // linked CancellationTokenSource, which is what lets a timeout be
        // told apart from the caller giving up; this is the backstop for a
        // response that starts in time and then stalls mid-body, which the
        // token alone would not interrupt. Slightly longer, so that the
        // linked token stays the one that normally fires.
        c.Timeout = TimeSpan.FromMilliseconds(ml.TimeoutMs + 500);
    })
    // 2 minutes rather than the 5-minute default: the ML service runs from
    // `tools/run_ml_service.py` during development and is restarted often,
    // and a pooled connection to a process that has gone away fails the
    // first request after every restart.
    .SetHandlerLifetime(TimeSpan.FromMinutes(2));


builder.Services
    .AddControllers(o =>
    {
        // GLOBAL, deliberately. Every authenticated endpoint has to be
        // blocked when the account is disabled or deleted. 38 endpoints are
        // still to be built, and a check that has to be remembered at every
        // one of them is a check that will be forgotten. Removing the
        // protection has to be explicit, with `[AllowAnonymous]`.
        o.Filters.Add<ActiveAccountFilter>();
    })
    .AddJsonOptions(o =>
    {
        // camelCase is the ASP.NET Core default — specification §2.2 already
        // relies on that. Declared explicitly so that if a later .NET changes
        // the default, the API contract does not quietly change with it.
        o.JsonSerializerOptions.PropertyNamingPolicy =
            JsonNamingPolicy.CamelCase;
        // `null` rather than dropping the field — specification §2.3: "an
        // empty field is `null`, NOT an empty string". Dropping the field
        // altogether is not allowed either: the frontend distinguishes "not
        // filled in" from "none".
        o.JsonSerializerOptions.DefaultIgnoreCondition =
            JsonIgnoreCondition.Never;
    })
    .ConfigureApiBehaviorOptions(o =>
    {
        // By default ASP.NET Core returns an RFC 7807 ProblemDetails for a
        // ModelState error. Specification §2.5 uses a different envelope, so
        // it has to be replaced — otherwise validation errors would be the
        // ONLY endpoint answering in the wrong shape, and the frontend could
        // not read `error.code` out of them.
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
        // Keep the claim names as they are in the token. By default the
        // library maps `sub` onto a long WS-Federation URI, and then
        // `User.FindFirst("sub")` returns null — a silent failure that makes
        // every Protected endpoint believe there is no user.
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
            // No tolerance: the library's default is 5 minutes, which means a
            // "1 hour" accessToken really lives 65 minutes. Specification
            // §2.4 says one hour.
            ClockSkew = TimeSpan.Zero,
            NameClaimType = "sub",
            RoleClaimType = "role",
        };
        o.Events = new JwtBearerEvents
        {
            // Specification §4 distinguishes TOKEN_EXPIRED (call
            // /auth/refresh and retry) from TOKEN_INVALID (log out). Merging
            // the two into a bare 401 would have the frontend log the user
            // out every hour.
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

// Said at startup, not only on the first call that needs it. A deployment
// that forgot ML_INTERNAL_KEY otherwise looks healthy until somebody asks
// for a meal plan — and then still looks healthy, because a rule-based plan
// is a plan.
if (!ml.Enabled)
{
    app.Logger.LogError(
        "ML_INTERNAL_KEY is not set: the ML service at {BaseUrl} will not be "
        + "called, and every recommendation will fall back to rule-based "
        + "scoring (specification §8.1). This server still starts, because "
        + "§8.1 requires a plan to be produced with the ML layer down.",
        ml.BaseUrl);
}
else
{
    app.Logger.LogInformation(
        "ML service client ready: {BaseUrl}, timeout {Timeout} ms.",
        ml.BaseUrl, ml.TimeoutMs);
}

// ── An uncaught error also has to use the §2.5 envelope ─────────────────
//
// Without this, an unexpected exception returns Kestrel's HTML error page,
// and a frontend trying to read JSON out of it reports something entirely
// different from the real error.
app.UseExceptionHandler(branch => branch.Run(async ctx =>
{
    var error = ctx.Features.Get<IExceptionHandlerFeature>()?.Error;
    app.Logger.LogError(error, "Uncaught error at {Path}", ctx.Request.Path);

    ctx.Response.StatusCode = StatusCodes.Status500InternalServerError;
    ctx.Response.ContentType = "application/json; charset=utf-8";
    await ctx.Response.WriteAsync(JsonSerializer.Serialize(
        new ApiError
        {
            Error = new ApiError.ErrorBody
            {
                Code = ErrorCode.InternalError,
                // `error.Message` is never sent out: it can contain the
                // connection string, a table name, or an SQL statement.
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

// ── The connection string is built from the same environment variables
//    that tools/ already uses ────────────────────────────────────────────
//
// `tools/_env.py` reads MYSQL_HOST / MYSQL_PORT / MYSQL_USER /
// MYSQL_PASSWORD / MYSQL_DATABASE from `.env`. The same names are reused so
// that one database does not have to be declared in two places under two
// different sets of names.
/// <summary>
/// Forces <c>GuidFormat=None</c>, because MySqlConnector's default makes
/// every <c>CHAR(36)</c> column read back as a <c>System.Guid</c>.
/// </summary>
//
// The schema has 45 CHAR(36) columns, and all 45 are UUIDs: id, user_id,
// food_id, meal_plan_id, category_id, owner_id, session_id, batch_id,
// replaced_by, replaced_by_food_id. MySqlConnector defaults to
// `GuidFormat=Char36`, so it treats every CHAR(36) as a Guid and returns a
// `System.Guid` — while the entities declare `string`, so EF throws
// `InvalidCastException: Unable to cast object of type 'System.Guid' to type
// 'System.String'` on the FIRST read.
//
// Two ways to fix it, and why this one was chosen:
//
//   1. Declare the entities as `Guid`. A tighter type, but specification §2.3
//      states plainly that the primary keys are "36-character UUID strings",
//      and every query in the system — `tools/*.py` and `ml/*.py` included —
//      compares them as strings. Adding a conversion at the boundary adds one
//      more place where the two sides can disagree on the format.
//   2. `GuidFormat=None`: a CHAR(36) reads back as exactly a string. There is
//      no BINARY(16) column anywhere in the schema, so turning Guid support
//      off entirely costs nothing.
//
// Done here rather than only inside `BuildConnectionFromEnv`, so that a
// connection string the user supplies through `MYSQL_CONNECTION` is
// normalised too — otherwise that configuration would break in exactly this
// way with no sign of why.
//
// Through `MySqlConnectionStringBuilder` rather than string concatenation: an
// earlier version checked `raw.Contains("GuidFormat")` and then appended
// `;GuidFormat=None;`, so a string that already declared
// `GuidFormat=Char36` would be LEFT ALONE — the very configuration that makes
// every CHAR(36) column read back as `System.Guid` and break on the first
// read. The entities declare `string`, so this overrides rather than defers.
static string NormalizeConnectionString(string raw)
{
    MySqlConnectionStringBuilder b;
    try
    {
        b = new MySqlConnectionStringBuilder(raw);
    }
    catch (Exception ex)
    {
        throw new InvalidOperationException(
            "The MySQL connection string could not be parsed. A password "
            + "containing `;` or `\"` has to be wrapped in single quotes: "
            + "Password='a;b'.", ex);
    }
    b.GuidFormat = MySqlGuidFormat.None;
    return b.ConnectionString;
}

static string BuildConnectionFromEnv()
{
    string? Get(string name) => Environment.GetEnvironmentVariable(name);

    var user = Get("MYSQL_USER");
    var pass = Get("MYSQL_PASSWORD");

    if (string.IsNullOrEmpty(user) || string.IsNullOrEmpty(pass))
    {
        throw new InvalidOperationException(
            "The MySQL connection string is missing. Set "
            + "ConnectionStrings:MySql, or MYSQL_CONNECTION, or the "
            + "MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE set that "
            + "tools/_env.py uses.");
    }

    var port = Get("MYSQL_PORT");

    // A builder rather than string interpolation. A `;` in the password ends
    // one key-value pair, so concatenating by hand makes everything after it
    // read as a connection OPTION: the password `a;b` yields `Password=a`
    // plus an option named `b`. That bug does not show up today — it shows up
    // the day the database password changes.
    var b = new MySqlConnectionStringBuilder
    {
        Server = Get("MYSQL_HOST") ?? "localhost",
        Port = uint.TryParse(port, out var p) ? p : 3306u,
        Database = Get("MYSQL_DATABASE") ?? "nutrition_rec",
        UserID = user,
        Password = pass,
        CharacterSet = "utf8mb4",
    };
    return b.ConnectionString;
}
