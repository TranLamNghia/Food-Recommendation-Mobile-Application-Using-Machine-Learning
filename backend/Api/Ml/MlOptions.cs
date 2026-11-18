namespace Api.Ml;

/// <summary>
/// Where the ML service is, and the shared secret that opens it —
/// specification §8.
///
/// <para>The key is read from the <c>ML_INTERNAL_KEY</c> environment
/// variable, the same name <c>ml/api.py</c> uses, and the same reason as
/// <c>JWT_SIGNING_KEY</c>: this repository is public, so a key in a
/// committed file lets anyone who can read the repo call a service that
/// reads the <c>users</c> table directly.</para>
///
/// <para><b>A missing key does not stop the server.</b> That is the one
/// deliberate difference from the JWT key, which throws at startup. The
/// backend has to keep producing a meal plan when the ML service is
/// unreachable — specification §8.1 calls it soft degradation — and "the key
/// was never configured" is just one more way for the service to be
/// unreachable. Crashing on it would turn an optional dependency into a
/// required one. Instead <see cref="Enabled"/> is <c>false</c>, every call
/// returns <see cref="MlFailureKind.Disabled"/>, and
/// <see cref="MlClient"/> logs that once at error level so it fails
/// LOUDLY in the log rather than silently in the scores.</para>
/// </summary>
public sealed class MlOptions
{
    public const string Section = "MlService";

    /// <summary>
    /// The root of the ML service. <c>tools/run_ml_service.py</c> binds
    /// <c>http://localhost:8000</c>.
    /// </summary>
    public string BaseUrl { get; set; } = "http://localhost:8000";

    /// <summary>
    /// The value sent as <c>X-Internal-Key</c>. Empty means "not
    /// configured" — see the note on the class.
    /// </summary>
    public string InternalKey { get; set; } = string.Empty;

    /// <summary>
    /// 2 000 ms, which is the budget specification §8.1 states in prose:
    /// "Backend đặt timeout 2 giây". Named here so the number lives in one
    /// place instead of at each call site.
    ///
    /// <para>The budget covers the WHOLE call, connect to last byte, and
    /// there is no retry. A retry would make the worst case 4 s while the
    /// user waits on a meal plan, and §8.1's answer to a slow service is to
    /// stop asking, not to ask again.</para>
    /// </summary>
    public int TimeoutMs { get; set; } = 2000;

    /// <summary>
    /// Whether the ML service can be called at all. A separate flag from
    /// "the call failed", because a missing key is a deployment fault that
    /// no amount of retrying will fix.
    /// </summary>
    public bool Enabled => !string.IsNullOrWhiteSpace(InternalKey);

    /// <summary>
    /// Reads the environment, config second. Mirrors how
    /// <c>Program.cs</c> resolves the JWT key and the connection string.
    /// </summary>
    public static MlOptions FromConfiguration(IConfiguration configuration)
    {
        var o = new MlOptions();
        configuration.GetSection(Section).Bind(o);

        // Configuration first, environment as the fallback — the same order
        // `Program.cs` resolves `Jwt:SigningKey` and the connection string
        // in. Reversing it for one setting would mean `appsettings` wins
        // here and loses there, which is the kind of difference nobody
        // remembers at three in the morning.
        var url = configuration[$"{Section}:BaseUrl"];
        if (string.IsNullOrWhiteSpace(url))
        {
            url = Environment.GetEnvironmentVariable("ML_SERVICE_URL");
        }
        if (!string.IsNullOrWhiteSpace(url))
        {
            o.BaseUrl = url.Trim();
        }

        var key = configuration[$"{Section}:InternalKey"];
        if (string.IsNullOrWhiteSpace(key))
        {
            // Where the key actually lives: `.env`, never a committed file.
            key = Environment.GetEnvironmentVariable("ML_INTERNAL_KEY");
        }
        o.InternalKey = (key ?? string.Empty).Trim();

        if (!o.BaseUrl.EndsWith('/'))
        {
            // `new Uri(base, "predict")` DROPS the last path segment of the
            // base when it does not end in a slash: a base of
            // `http://h/ml` would resolve to `http://h/predict`. Normalised
            // once here rather than relying on every call site to remember.
            o.BaseUrl += "/";
        }
        return o;
    }
}
