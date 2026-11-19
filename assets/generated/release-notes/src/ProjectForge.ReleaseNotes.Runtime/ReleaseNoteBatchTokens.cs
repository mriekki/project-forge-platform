using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ProjectForge.ReleaseNotes.Runtime;

/// <summary>
/// Authentication-independent HMAC token for an exact server-authorized batch.
/// The application provides the verified, active release and Auth Kit principal.
/// Signing does NOT verify a deployment or replace CSRF/session validation.
/// </summary>
public sealed class ReleaseNoteBatchTokens
{
    private static readonly Regex DigestPattern = new("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex IdPattern = new("^[a-z0-9][a-z0-9-]{2,119}$", RegexOptions.CultureInvariant);
    private static readonly Regex KeyPattern = new("^[a-z0-9][a-z0-9-]{2,79}$", RegexOptions.CultureInvariant);
    private const int MaximumTokenLength = 18_000;
    private static readonly TimeSpan ValidFor = TimeSpan.FromMinutes(20);
    private readonly byte[] _key;

    private sealed record Payload(
        int Version,
        string AccountBinding,
        string ManifestSha256,
        string ReleaseKey,
        string[] AnnouncementIds,
        long IssuedAtUnixSeconds);

    public ReleaseNoteBatchTokens(byte[] protectedServerKey)
    {
        if (protectedServerKey is null || protectedServerKey.Length < 32)
            throw new ReleaseNoteContractException("Batch signing requires a protected key of at least 32 bytes.");
        _key = protectedServerKey.ToArray();
    }

    /// <summary>
    /// Caller MUST supply all currently eligible, verified active, meaningful
    /// unacknowledged IDs for a session-derived account. The token is not a
    /// browser-chosen authorization list.
    /// </summary>
    public string Issue(string authenticatedAccountKey, string activeManifestSha256,
        string activeReleaseKey, IReadOnlyCollection<string> verifiedEligibleIds, DateTimeOffset nowUtc)
    {
        ValidateInputs(authenticatedAccountKey, activeManifestSha256, activeReleaseKey,
            verifiedEligibleIds, nowUtc);
        var ids = verifiedEligibleIds.Order(StringComparer.Ordinal).ToArray();
        var payload = new Payload(1, BindAccount(authenticatedAccountKey),
            activeManifestSha256, activeReleaseKey, ids, nowUtc.ToUnixTimeSeconds());
        var bytes = JsonSerializer.SerializeToUtf8Bytes(payload);
        var signature = HMACSHA256.HashData(_key, bytes);
        var token = $"v1.{Encode(bytes)}.{Encode(signature)}";
        if (token.Length > MaximumTokenLength)
            throw new ReleaseNoteContractException("Authenticated release-note batch is too large.");
        return token;
    }

    /// <summary>
    /// Only accept the exact currently eligible batch for the current verified
    /// release and authenticated account. Logout/session revocation is owned
    /// by the host Auth Kit guard, not this account-bound token. Rollback,
    /// mismatch, expiry or cross-account reuse fails closed without affecting sign-in.
    /// </summary>
    public bool TryValidate(string? token, string authenticatedAccountKey,
        string activeManifestSha256, string activeReleaseKey,
        IReadOnlyCollection<string> currentlyEligibleIds, DateTimeOffset nowUtc,
        out IReadOnlyList<string> validatedAnnouncementIds)
    {
        validatedAnnouncementIds = Array.Empty<string>();
        if (string.IsNullOrWhiteSpace(token) || token.Length > MaximumTokenLength)
            return false;
        try
        {
            ValidateInputs(authenticatedAccountKey, activeManifestSha256,
                activeReleaseKey, currentlyEligibleIds, nowUtc);
            var parts = token.Split('.');
            if (parts.Length != 3 || parts[0] != "v1")
                return false;
            byte[] payloadBytes = Decode(parts[1]);
            byte[] signature = Decode(parts[2]);
            if (signature.Length != 32 ||
                !CryptographicOperations.FixedTimeEquals(
                    HMACSHA256.HashData(_key, payloadBytes), signature))
                return false;
            var payload = JsonSerializer.Deserialize<Payload>(payloadBytes);
            if (payload is null || payload.Version != 1 ||
                payload.AccountBinding != BindAccount(authenticatedAccountKey) ||
                payload.ManifestSha256 != activeManifestSha256 ||
                payload.ReleaseKey != activeReleaseKey ||
                payload.AnnouncementIds is null ||
                payload.AnnouncementIds.Length != currentlyEligibleIds.Count ||
                payload.IssuedAtUnixSeconds > nowUtc.ToUnixTimeSeconds() ||
                nowUtc.ToUnixTimeSeconds() - payload.IssuedAtUnixSeconds > ValidFor.TotalSeconds)
                return false;
            var sorted = currentlyEligibleIds.Order(StringComparer.Ordinal).ToArray();
            if (!payload.AnnouncementIds.SequenceEqual(sorted, StringComparer.Ordinal))
                return false;
            validatedAnnouncementIds = sorted;
            return true;
        }
        catch (Exception error) when (error is JsonException or FormatException or
            OverflowException or ArgumentException or ReleaseNoteContractException)
        {
            return false;
        }
    }

    private static string Encode(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static byte[] Decode(string value)
    {
        if (value.Length == 0 || value.Length % 4 == 1 ||
            value.Any(ch => !char.IsAsciiLetterOrDigit(ch) && ch is not '-' and not '_'))
            throw new FormatException("Invalid signed batch encoding.");
        return Convert.FromBase64String(value.Replace('-', '+').Replace('_', '/') +
            new string('=', (4 - value.Length % 4) % 4));
    }

    private string BindAccount(string key) =>
        Convert.ToHexStringLower(HMACSHA256.HashData(_key,
            Encoding.UTF8.GetBytes("project-forge-release-notes-account:" + key)));

    private static void ValidateInputs(string account, string digest, string release,
        IReadOnlyCollection<string> ids, DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(account) || account.Length > 128 ||
            account != account.Trim() || !DigestPattern.IsMatch(digest) ||
            !KeyPattern.IsMatch(release) || ids is null ||
            ids.Count is < 1 or > 100 || now.Offset != TimeSpan.Zero ||
            ids.Any(id => id is null || !IdPattern.IsMatch(id)) ||
            ids.Distinct(StringComparer.Ordinal).Count() != ids.Count)
            throw new ReleaseNoteContractException("A bounded, current and exact active release-note batch is required.");
    }
}
