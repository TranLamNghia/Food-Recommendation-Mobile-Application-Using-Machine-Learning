using System.ComponentModel.DataAnnotations;
using Api.Auth;
using Microsoft.Extensions.Configuration;

namespace Api.Tests;

/// <summary>
/// The parts of §7.1.5 – §7.1.7 that need no database. The flows themselves
/// run against MySQL in <c>tools/smoke_backend.py</c>.
/// </summary>
public class PasswordTests
{
    private static List<ValidationResult> Validate(object model)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(
            model, new ValidationContext(model), results,
            validateAllProperties: true);
        return results;
    }

    [Theory]
    [InlineData("ngan1")]            // too short
    [InlineData("chiCoChuThoi")]     // no digit
    [InlineData("12345678")]         // no letter
    public void A_reset_refuses_what_registration_refuses(string password)
    {
        Assert.NotEmpty(Validate(
            new ResetPasswordRequest { Token = "x", NewPassword = password }));
        Assert.NotEmpty(Validate(new ChangePasswordRequest
        {
            CurrentPassword = "MatKhau123",
            NewPassword = password,
        }));
        Assert.NotEmpty(Validate(new RegisterRequest
        {
            Email = "a@b.vn",
            DisplayName = "Nghĩa",
            Password = password,
        }));
    }

    [Fact]
    public void A_good_new_password_passes()
    {
        Assert.Empty(Validate(new ResetPasswordRequest
        {
            Token = "abc",
            NewPassword = "MatKhauMoi456",
        }));
    }

    /// <summary>
    /// BCrypt reads 72 bytes. Vietnamese letters take two or three, so a
    /// password of 30 accented letters is over the limit while being far
    /// under any character count.
    /// </summary>
    [Fact]
    public void The_byte_cap_applies_to_a_new_password_too()
    {
        var accented = new string('ữ', 30) + "1";
        Assert.Contains(
            Validate(new ChangePasswordRequest
            {
                CurrentPassword = "x",
                NewPassword = accented,
            }),
            r => r.MemberNames.Contains(nameof(ChangePasswordRequest.NewPassword)));
    }

    [Fact]
    public void The_current_password_is_only_required_not_judged()
    {
        // A password set before a rule existed must still be able to prove
        // itself; only the hash decides whether it is right.
        Assert.Empty(Validate(new ChangePasswordRequest
        {
            CurrentPassword = "abc",
            NewPassword = "MatKhauMoi456",
        }));
    }

    [Fact]
    public void A_code_is_long_random_and_url_safe()
    {
        var a = TokenService.NewRefreshToken();
        var b = TokenService.NewRefreshToken();
        Assert.NotEqual(a, b);
        // 32 bytes in unpadded base64url.
        Assert.Equal(43, a.Length);
        Assert.Matches("^[A-Za-z0-9_-]+$", a);
        // Stored as SHA-256 hex, which is what `token_hash CHAR(64)` holds.
        Assert.Equal(64, TokenService.Hash(a).Length);
    }

    [Fact]
    public void The_mail_carries_the_code_on_its_labelled_line()
    {
        var mail = new ResetMail(
            "nghia@example.com", "Nghĩa", "CODE123",
            new DateTime(2026, 11, 26, 9, 30, 0));
        var body = mail.Body();

        Assert.Contains(ResetMail.TokenLabel + "CODE123", body);
        Assert.Contains("Nghĩa", body);
        Assert.Contains("09:30 ngày 26/11/2026", body);
    }

    [Fact]
    public async Task The_outbox_writes_one_readable_file_per_mail()
    {
        var dir = Path.Combine(Path.GetTempPath(), "outbox-" + Guid.NewGuid());
        try
        {
            var sender = new OutboxResetMailSender(new MailOptions
            {
                OutboxDir = dir,
            });
            await sender.SendAsync(
                new ResetMail("a@b.vn", "A", "TOKEN-1", DateTime.Now),
                CancellationToken.None);

            var file = Assert.Single(Directory.GetFiles(dir));
            var text = await File.ReadAllTextAsync(file);
            Assert.StartsWith("To: a@b.vn", text);
            // The first BYTE too. `ReadAllTextAsync` hides a byte-order mark,
            // and the smoke test, reading line by line, did not.
            Assert.Equal((byte)'T', (await File.ReadAllBytesAsync(file))[0]);
            Assert.Contains(ResetMail.TokenLabel + "TOKEN-1", text);
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, recursive: true);
        }
    }

    [Fact]
    public void Without_an_smtp_host_mail_goes_to_the_outbox()
    {
        var opt = MailOptions.FromConfiguration(
            new ConfigurationBuilder().Build(), "/app");
        // Unless the machine running the tests has SMTP_HOST set.
        if (Environment.GetEnvironmentVariable("SMTP_HOST") is null)
        {
            Assert.False(opt.SendsForReal);
        }
        if (Environment.GetEnvironmentVariable("MAIL_OUTBOX_DIR") is null)
        {
            Assert.Equal(Path.Combine("/app", ".mail-outbox"), opt.OutboxDir);
        }
    }
}
