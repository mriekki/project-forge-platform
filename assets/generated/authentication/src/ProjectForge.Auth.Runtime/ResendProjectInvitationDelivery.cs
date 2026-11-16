using System;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Mail;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ProjectForge.Auth.Runtime;

/// <summary>
/// Optional per-Project Resend invitation delivery. Never uses a household
/// Registry token or stores the Resend API key in SQLite. Invitation tokens
/// are sent only in TLS request bodies, never URLs, query params or logs.
/// </summary>
public interface IProjectInvitationDelivery
{
    Task<bool> SendAsync(
        string recipientEmail, string invitationToken,
        DateTimeOffset expiresAt, CancellationToken cancellationToken);
}

public sealed class ResendProjectInvitationDelivery : IProjectInvitationDelivery, IDisposable
{
    private readonly HttpClient _client;
    private readonly string _apiKey;
    private readonly string _from;
    private readonly string _origin;

    public ResendProjectInvitationDelivery(
        HttpClient client, string apiKey, string fromEmail, string publicOrigin)
    {
        if (client is null || string.IsNullOrWhiteSpace(apiKey) || apiKey.Length < 12)
            throw new ArgumentException("Project-scoped Resend credential required.");
        _from = ValidateMail(fromEmail);
        if (!Uri.TryCreate(publicOrigin, UriKind.Absolute, out var origin) ||
            origin.Scheme != Uri.UriSchemeHttps ||
            origin.AbsolutePath != "/" ||
            !origin.IsDefaultPort ||
            !string.IsNullOrEmpty(origin.UserInfo) ||
            !string.IsNullOrEmpty(origin.Query) ||
            !string.IsNullOrEmpty(origin.Fragment))
            throw new ArgumentException("An exact HTTPS Project public origin is required.");
        _origin = origin.GetLeftPart(UriPartial.Authority);
        _apiKey = apiKey;
        _client = client;
    }

    private static string ValidateMail(string value)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 254 ||
            value.Any(char.IsWhiteSpace) || value.Contains('<') || value.Contains('>') ||
            value.Count(c => c == '@') != 1 ||
            !MailAddress.TryCreate(value, out var parsed) ||
            !string.Equals(parsed.Address, value, StringComparison.Ordinal))
            throw new ArgumentException("A single literal email address is required.");
        return value;
    }

    public async Task<bool> SendAsync(
        string recipientEmail, string invitationToken,
        DateTimeOffset expiresAt, CancellationToken cancellationToken)
    {
        var recipient = ValidateMail(recipientEmail);
        if (invitationToken is null || invitationToken.Length != 64 ||
            invitationToken.Any(c => !Uri.IsHexDigit(c) || char.IsUpper(c)))
            throw new ArgumentException("Invitation token must be the generated 32-byte lowercase value.");
        if (expiresAt <= DateTimeOffset.UtcNow)
            return false;

        // Resend's Idempotency-Key is deterministic for this specific
        // invitation without revealing the token. Never retry with a
        // different request body using the same key.
        var tokenFingerprint = Convert.ToHexString(
            SHA256.HashData(Encoding.ASCII.GetBytes(invitationToken))).ToLowerInvariant();
        var message = new
        {
            from = _from,
            to = new[] { recipient },
            subject = "Your Project invitation",
            text = $"You've been invited to use a Project Forge application.\n\n" +
                   $"Open {_origin} in your browser, then enter this one-time token:\n\n" +
                   $"{invitationToken}\n\nExpires: {expiresAt:O}\n\n" +
                   "Use the Google account that received this email. " +
                   "Household Registry membership alone does not grant Project access."
        };
        using var request = new HttpRequestMessage(HttpMethod.Post, "https://api.resend.com/emails");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
        request.Headers.TryAddWithoutValidation("Idempotency-Key", "project-invite-" + tokenFingerprint);
        request.Content = new StringContent(
            JsonSerializer.Serialize(message), Encoding.UTF8, "application/json");
        try
        {
            using var response = await _client.SendAsync(
                request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            // Do not read or log provider bodies/headers; 3xx is never a
            // delivery success and must not redirect with our bearer token.
            return response.StatusCode == HttpStatusCode.OK;
        }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested) { return false; }
    }

    public void Dispose() => _client.Dispose();
}
