namespace Api.Time;

/// <summary>
/// The system clock. <b>One single time zone: Asia/Ho_Chi_Minh.</b>
///
/// <para>It exists because the project's three layers used to read three
/// different clocks:</para>
///
/// <list type="bullet">
/// <item>The database: 27 <c>DEFAULT CURRENT_TIMESTAMP</c> columns, and every
/// <c>INSERT … NOW()</c> in <c>tools/*.py</c>. Both return
/// <c>@@session.time_zone</c>, which defaults to <c>SYSTEM</c> — that is, the
/// machine's time, that is, Vietnam time.</item>
/// <item>The Flutter app: <c>DateTime.now()</c>, local time.</item>
/// <item>The backend: <c>DateTime.UtcNow</c> — <b>7 hours off from both</b>.</item>
/// </list>
///
/// <para>The consequences were silent. A <c>users.created_at</c> written by the
/// backend was 7 hours behind a row written by <c>check_ml_e2e.py</c>, so
/// sorting by <c>created_at</c> mixed two clocks. And worse: "today" computed
/// from <c>UtcNow</c> was a DAY behind the app between 00:00 and 07:00 every
/// night, so on their actual birthday the app showed 23 while
/// <c>GET /profile</c> returned <c>age: 22</c>, which moved the BMR by 5 kcal
/// because Mifflin has a <c>− 5 × age</c> term.</para>
///
/// <para><b>The parity checker could not catch that</b>: it pins <c>today</c>
/// in all three implementations, exactly as it must in order to lock the
/// formula down — but the clock source sits outside what is locked.</para>
///
/// <para>Vietnam time rather than UTC, because that is what the database
/// ALREADY stores: switching to UTC would mean changing the schema's 27
/// defaults, every <c>NOW()</c> in <c>tools/</c>, and the data already
/// written. The users are all in one time zone too.</para>
/// </summary>
public static class Clock
{
    /// <summary>
    /// Vietnam has had no daylight saving since 1975, so this zone is a fixed
    /// <c>+07:00</c>. It is still looked up by NAME rather than hard-coding
    /// the offset, so that if that ever changes, only the system's time zone
    /// database needs updating.
    /// </summary>
    public static readonly TimeZoneInfo Zone = Resolve();

    private static TimeZoneInfo Resolve()
    {
        // The IANA name is what .NET uses on Linux and, since .NET 6, on
        // Windows too via ICU. The old Windows name is a fallback for a
        // machine running in globalization-invariant mode, where looking up
        // the IANA name throws.
        foreach (var name in new[] { "Asia/Ho_Chi_Minh", "SE Asia Standard Time" })
        {
            try
            {
                return TimeZoneInfo.FindSystemTimeZoneById(name);
            }
            catch (TimeZoneNotFoundException) { }
            catch (InvalidTimeZoneException) { }
        }
        throw new InvalidOperationException(
            "Time zone Asia/Ho_Chi_Minh not found. The server is missing its "
            + "time zone database (tzdata), or is running in "
            + "globalization-invariant mode.");
    }

    /// <summary>
    /// The current moment in Vietnam time — used for EVERY <c>DATETIME</c>
    /// column, to match the schema's <c>CURRENT_TIMESTAMP</c>.
    /// </summary>
    public static DateTime Now
        => TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, Zone);

    /// <summary>
    /// Today's date in Vietnam time — used for EVERY <c>DATE</c> column and
    /// for every calendar-day calculation: age, <c>food_diary.ate_on</c>,
    /// <c>body_logs.logged_on</c>.
    /// </summary>
    public static DateOnly Today => DateOnly.FromDateTime(Now);
}
