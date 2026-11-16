using System.Text.RegularExpressions;

namespace ProjectForge.Feedback.GitHub;

/// <summary>Server-owned GitHub repository and a secret, keyed reporter association.
/// No credentials or identity identifiers may be exposed to a browser.</summary>
public sealed record GitHubFeedbackConfig(
    string Owner, string Repository, long InstallationId, string AppId, byte[] ReporterHmacKey)
{
    private static readonly Regex Identifier = new(
        @"\A[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}\z", RegexOptions.CultureInvariant);

    public void Validate()
    {
        if (!Identifier.IsMatch(Owner) || !Identifier.IsMatch(Repository) ||
            InstallationId <= 0 || !long.TryParse(AppId, out var appId) || appId <= 0 ||
            ReporterHmacKey is null || ReporterHmacKey.Length < 32)
            throw new ArgumentException("Invalid server-owned GitHub Feedback configuration");
    }

    public Uri IssueUri(int number) => new(
        $"https://github.com/{Owner}/{Repository}/issues/{number}");
}

public sealed record FeedbackDraft(
    string Kind, string Title, string Description, string IdempotencyKey);

public sealed record FeedbackIssue(
    int Number, string Url, string Title, string Description, string Kind,
    string Status, DateTimeOffset CreatedAt);

public enum FeedbackErrorKind
{
    InvalidInput, Conflict, ProviderUnavailable, OutcomeUnknown, IncompleteRead, InvalidProviderResponse
}

public sealed class FeedbackProviderException(FeedbackErrorKind kind, string message) : Exception(message)
{
    public FeedbackErrorKind Kind { get; } = kind;
}

/// <summary>Only a trusted backend calls this. The browser never receives installation credentials.</summary>
public interface IGitHubIssueTokenSource
{
    Task<string> GetInstallationTokenAsync(bool write, CancellationToken cancellationToken);
}
