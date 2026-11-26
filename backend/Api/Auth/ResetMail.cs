using System.Globalization;
using System.Net;
using System.Net.Mail;
using System.Text;
using System.Threading.Channels;

namespace Api.Auth;

/// <summary>
/// Where reset emails go, read from configuration or the environment.
///
/// <para><b>Two modes, chosen by whether an SMTP host is set.</b> With
/// <c>SMTP_HOST</c> the mail is sent. Without it, each mail is written as a
/// text file into <see cref="OutboxDir"/> — which is what development and
/// <c>tools/smoke_backend.py</c> use, since nobody should need a mail account
/// to run the test suite.</para>
///
/// <para>Not a startup check, for the same reason as <c>MlOptions</c>: the
/// rest of the API works without mail, and refusing to start would turn one
/// feature's dependency into everyone's. The missing host is logged at error
/// level at startup instead, outside Development.</para>
/// </summary>
public sealed class MailOptions
{
    public string? SmtpHost { get; init; }
    public int SmtpPort { get; init; } = 587;
    public string? SmtpUser { get; init; }
    public string? SmtpPassword { get; init; }
    public bool SmtpSsl { get; init; } = true;
    public string From { get; init; } = "no-reply@nutrition-rec.local";
    public string OutboxDir { get; init; } = ".mail-outbox";

    public bool SendsForReal => !string.IsNullOrWhiteSpace(SmtpHost);

    public static MailOptions FromConfiguration(
        IConfiguration config, string contentRoot)
    {
        string? Get(string key, string env)
            => config[key] ?? Environment.GetEnvironmentVariable(env);

        var outbox = Get("Mail:OutboxDir", "MAIL_OUTBOX_DIR");
        return new MailOptions
        {
            SmtpHost = Get("Mail:SmtpHost", "SMTP_HOST"),
            SmtpPort = int.TryParse(Get("Mail:SmtpPort", "SMTP_PORT"),
                                    out var port) ? port : 587,
            SmtpUser = Get("Mail:SmtpUser", "SMTP_USER"),
            SmtpPassword = Get("Mail:SmtpPassword", "SMTP_PASSWORD"),
            SmtpSsl = !string.Equals(Get("Mail:SmtpSsl", "SMTP_SSL"),
                                     "false",
                                     StringComparison.OrdinalIgnoreCase),
            From = Get("Mail:From", "MAIL_FROM")
                ?? "no-reply@nutrition-rec.local",
            OutboxDir = string.IsNullOrWhiteSpace(outbox)
                ? Path.Combine(contentRoot, ".mail-outbox")
                : outbox,
        };
    }
}

/// <summary>One reset mail waiting to go out.</summary>
public sealed record ResetMail(
    string To, string DisplayName, string Token, DateTime ExpiresAt)
{
    public const string Subject = "Đặt lại mật khẩu";

    /// <summary>
    /// The line the code sits on. A constant because
    /// <c>tools/smoke_backend.py</c> reads the code back from the outbox by
    /// it, and a reworded mail must not silently break that.
    /// </summary>
    public const string TokenLabel = "Mã đặt lại: ";

    /// <summary>
    /// The mail's text. Plain text only: the code has to survive being
    /// copied out of any mail client, and HTML gives a client room to wrap
    /// or restyle it.
    ///
    /// <para>No link, deliberately. The app has no deep link registered, so
    /// a link would open a browser on nothing; the code is pasted into the
    /// app's reset screen instead.</para>
    /// </summary>
    public string Body()
    {
        var expires = ExpiresAt.ToString(
            "HH:mm 'ngày' dd/MM/yyyy", CultureInfo.InvariantCulture);
        return new StringBuilder()
            .Append("Xin chào ").Append(DisplayName).AppendLine(",")
            .AppendLine()
            .Append("Có người vừa yêu cầu đặt lại mật khẩu cho tài khoản ")
            .Append(To).AppendLine(".")
            .AppendLine()
            .Append(TokenLabel).AppendLine(Token)
            .AppendLine()
            .AppendLine("Mở ứng dụng, vào \"Quên mật khẩu\" → \"Tôi đã có "
                        + "mã\" rồi dán mã trên. Mã chỉ dùng được một lần và "
                        + $"hết hạn lúc {expires}.")
            .AppendLine()
            .AppendLine("Nếu không phải bạn yêu cầu, hãy bỏ qua thư này: mật "
                        + "khẩu của bạn vẫn giữ nguyên.")
            .ToString();
    }
}

/// <summary>Sends one reset mail.</summary>
public interface IResetMailSender
{
    Task SendAsync(ResetMail mail, CancellationToken ct);
}

/// <summary>Sends through SMTP.</summary>
public sealed class SmtpResetMailSender(MailOptions opt) : IResetMailSender
{
    public async Task SendAsync(ResetMail mail, CancellationToken ct)
    {
        // `System.Net.Mail` rather than a package: one plain-text message
        // over an authenticated relay is all this needs, and it ships with
        // the runtime.
        using var client = new SmtpClient(opt.SmtpHost, opt.SmtpPort)
        {
            EnableSsl = opt.SmtpSsl,
            Credentials = string.IsNullOrEmpty(opt.SmtpUser)
                ? null
                : new NetworkCredential(opt.SmtpUser, opt.SmtpPassword),
        };
        using var message = new MailMessage(opt.From, mail.To)
        {
            Subject = ResetMail.Subject,
            Body = mail.Body(),
            BodyEncoding = Encoding.UTF8,
            SubjectEncoding = Encoding.UTF8,
            IsBodyHtml = false,
        };
        await client.SendMailAsync(message, ct);
    }
}

/// <summary>
/// Writes each mail as a text file — development and the smoke test.
/// </summary>
public sealed class OutboxResetMailSender(MailOptions opt) : IResetMailSender
{
    public async Task SendAsync(ResetMail mail, CancellationToken ct)
    {
        Directory.CreateDirectory(opt.OutboxDir);
        // Sortable by name, so "the newest mail" is the last file listed.
        var name = $"{DateTime.UtcNow:yyyyMMdd-HHmmss-fffffff}-"
            + $"{Guid.NewGuid():N}.txt";
        var text = $"To: {mail.To}\nSubject: {ResetMail.Subject}\n\n"
            + mail.Body();
        // No byte-order mark: `Encoding.UTF8` writes one, and a reader
        // matching the file's first line would then never see "To:".
        await File.WriteAllTextAsync(
            Path.Combine(opt.OutboxDir, name), text,
            new UTF8Encoding(encoderShouldEmitUTF8Identifier: false), ct);
    }
}

/// <summary>
/// The queue between <c>POST /auth/forgot-password</c> and the sender.
///
/// <para><b>Why the request does not send the mail itself.</b> §7.1.5
/// answers <c>202</c> for every address so it cannot be used to find out
/// which ones are registered. Sending inline would undo that through the
/// clock: a registered address would answer after an SMTP round trip, a
/// stranger's at once. Queuing makes both answer at the speed of a database
/// lookup.</para>
///
/// <para>Bounded: a queue that grows without limit is a memory leak the
/// first time the mail server is down. When full, the mail is dropped and
/// logged — the user can ask again, and the code already in the table is
/// harmless without the mail that carries it.</para>
/// </summary>
public sealed class ResetMailQueue
{
    private readonly Channel<ResetMail> _channel =
        Channel.CreateBounded<ResetMail>(new BoundedChannelOptions(100)
        {
            FullMode = BoundedChannelFullMode.DropWrite,
            SingleReader = true,
        });

    /// <summary><c>false</c> when the queue is full and the mail was
    /// dropped.</summary>
    public bool TryEnqueue(ResetMail mail) => _channel.Writer.TryWrite(mail);

    public IAsyncEnumerable<ResetMail> ReadAllAsync(CancellationToken ct)
        => _channel.Reader.ReadAllAsync(ct);
}

/// <summary>Drains <see cref="ResetMailQueue"/> in the background.</summary>
public sealed class ResetMailWorker(
    ResetMailQueue queue,
    IResetMailSender sender,
    ILogger<ResetMailWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await foreach (var mail in queue.ReadAllAsync(stoppingToken))
        {
            try
            {
                await sender.SendAsync(mail, stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                // Logged and dropped, never retried in a loop: a mail server
                // that refuses once usually refuses again, and the user can
                // simply ask for another code. The address is not logged —
                // a log full of who forgot their password is a list nobody
                // asked to keep.
                log.LogError(ex, "Could not send a password reset mail.");
            }
        }
    }
}
