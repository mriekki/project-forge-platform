using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ProjectForge.Feedback.GitHub;

/// <summary>
/// GitHub Issues is the only durable feedback record. All calls are backend-only;
/// the embedding Project must independently authenticate the session and check
/// reporter/admin grants plus CSRF/Origin for mutations. No repository name,
/// App credential, or reporter account ID comes from browser-supplied data.
/// </summary>
public sealed class GitHubFeedbackClient
{
    private const int MaxPages = 10;
    private const int PageSize = 100;
    private const int MaxResponseBytes = 4 * 1024 * 1024;
    // No durable external idempotency store: retain bounded local confirmations.
    // After this limit, fail closed rather than evicting known attempt receipts.
    private const int MaxConfirmedAttempts = 8192;
    private const int MaxRecentDirectReadbacks = 16;
    private static readonly TimeSpan RecentConfirmationWindow = TimeSpan.FromMinutes(3);
    private const string SourceLabel = "source:feedback";
    private static readonly Regex AttemptKeyPattern = new(
        @"\A[A-Za-z0-9][A-Za-z0-9._~-]{7,127}\z", RegexOptions.CultureInvariant);
    private static readonly Regex MarkerPattern = new(
        @"<!-- project-forge-feedback:v1\s+reporter=(?<reporter>[a-f0-9]{64})\s+attempt=(?<attempt>[a-f0-9]{64})\s+payload=(?<payload>[a-f0-9]{64})\s+kind=(?<kind>bug|enhancement|other)\s*-->",
        RegexOptions.CultureInvariant);
    private static readonly Regex SensitiveContent = new(
        @"(?:<!--\s*project-forge-feedback|-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE KEY-----|\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}|\bgithub_pat_[A-Za-z0-9_]{16,}|\b(?:bearer|password|access[_ -]?token|api[_ -]?key|client[_ -]?secret)\s*[:=]\s*\S+|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b)",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
    private static readonly HashSet<string> ValidStatuses =
        new(StringComparer.Ordinal) { "triage", "reviewed", "accepted", "declined" };
    private readonly GitHubFeedbackConfig _config;
    private readonly HttpClient _api;
    private readonly IGitHubIssueTokenSource _tokens;
    // Serializing creates prevents same-attempt races without accumulating one
    // permanent lock object per submission over the lifetime of a host.
    private readonly SemaphoreSlim _createGate = new(1, 1);
    private readonly ConcurrentDictionary<string, byte> _uncertainAttempts = new();
    // A newly created Issue may be temporarily absent from the filtered list
    // despite a confirmed POST result. ConcurrentDictionary allows readback
    // requests to consult receipts while a separate request is creating.
    // Creation and retention-capacity checks remain serialized by _createGate.
    private readonly ConcurrentDictionary<string, ConfirmedAttempt>
        _confirmedAttempts = new(StringComparer.Ordinal);

    public GitHubFeedbackClient(GitHubFeedbackConfig config, HttpClient api,
        IGitHubIssueTokenSource tokens)
    {
        config.Validate();
        _config = config;
        _api = api;
        _tokens = tokens;
    }

    /// <summary>Returns canonical GitHub Issue details only after provider confirmation.</summary>
    public async Task<FeedbackIssue> CreateAsync(string reporterAccountId,
        FeedbackDraft draft, CancellationToken ct = default)
    {
        ValidateReporter(reporterAccountId);
        ValidateDraft(draft);
        string reporter = Hmac("reporter:v1:" + reporterAccountId);
        string attempt = Hmac("attempt:v1:" + reporterAccountId + ":" + draft.IdempotencyKey);
        string digest = Digest(draft.Kind + "\n" + draft.Title + "\n" + draft.Description);
        var desired = new FeedbackMarker(reporter, attempt, digest, draft.Kind);
        await _createGate.WaitAsync(ct);
        try
        {
            if (_confirmedAttempts.TryGetValue(attempt, out var confirmed))
            {
                if (confirmed.Marker != desired)
                    throw new FeedbackProviderException(FeedbackErrorKind.Conflict,
                        "A previous attempt used this key with different content");
                return confirmed.Issue;
            }
            if (_confirmedAttempts.Count >= MaxConfirmedAttempts)
                throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                    "Feedback submission confirmation capacity reached; operator review required");
            // On an unconfirmed attempt, read back before POST. GH Issues does not offer an atomic
            // creation-idempotency API, so do not claim exactly-once.
            var matches = (await ReadFeedbackIssuesAsync(ct))
                .Where(i => i.Marker.Attempt == attempt).ToList();
            if (matches.Count > 1)
                throw new FeedbackProviderException(FeedbackErrorKind.OutcomeUnknown,
                    "Multiple Issues match this attempt; administrator review required");
            if (matches.Count == 1)
            {
                if (matches[0].Marker != desired)
                    throw new FeedbackProviderException(FeedbackErrorKind.Conflict,
                        "A previous attempt used this key with different content");
                _uncertainAttempts.TryRemove(attempt, out _);
                return RememberConfirmed(desired, Public(matches[0]));
            }
            // On an unknown previous POST, never automatically POST a second time
            // just because this bounded scan did not find a matching Issue.
            if (_uncertainAttempts.ContainsKey(attempt))
                throw new FeedbackProviderException(FeedbackErrorKind.OutcomeUnknown,
                    "Previous GitHub Issue creation cannot be confirmed; check before retry");

            // Required repository labels must already exist. GitHub can
            // silently drop labels during issue creation when permissions are
            // insufficient, so verify readiness before the first POST.
            await EnsureLabelAsync(SourceLabel, ct);
            await EnsureLabelAsync("status:triage", ct);
            await EnsureLabelAsync("kind:" + draft.Kind, ct);

            string body = "**Source:** Project Forge application feedback\n\n" +
                "**Kind:** " + draft.Kind + "\n\n**Description**\n\n" +
                draft.Description.Trim() + "\n\n" + MarkerText(desired);
            var requestBody = new
            {
                title = draft.Title.Trim(),
                body,
                labels = new[] { SourceLabel, "status:triage", "kind:" + draft.Kind }
            };
            try
            {
                using var json = await RequestAsync(HttpMethod.Post, "issues",
                    requestBody, HttpStatusCode.Created, ct);
                var created = ParseIssue(json.RootElement);
                if (created is null || created.Marker != desired ||
                    !created.Labels.Contains(SourceLabel, StringComparer.Ordinal) ||
                    !created.Labels.Contains("status:triage", StringComparer.Ordinal) ||
                    !created.Labels.Contains("kind:" + draft.Kind, StringComparer.Ordinal))
                    throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                        "GitHub did not confirm the requested Issue identity");
                return RememberConfirmed(desired, Public(created));
            }
            catch (Exception ex) when (ex is FeedbackProviderException or HttpRequestException
                                       or OperationCanceledException or JsonException)
            {
                _uncertainAttempts.TryAdd(attempt, 0);
                // The response could have been lost *after* GitHub committed
                // the Issue. Bounded readback is the only safe reconciliation.
                try
                {
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(12));
                    var recovered = (await ReadFeedbackIssuesAsync(timeout.Token))
                        .Where(i => i.Marker.Attempt == attempt).ToList();
                    if (recovered.Count == 1 && recovered[0].Marker == desired)
                    {
                        _uncertainAttempts.TryRemove(attempt, out _);
                        return RememberConfirmed(desired, Public(recovered[0]));
                    }
                }
                catch (Exception err) when (err is FeedbackProviderException
                                            or HttpRequestException
                                            or OperationCanceledException
                                            or JsonException) { /* fail closed */ }

                throw new FeedbackProviderException(FeedbackErrorKind.OutcomeUnknown,
                    "Issue creation result is uncertain; do not submit a new attempt");
            }
        }
        finally
        {
            _createGate.Release();
        }
    }

    // Called under _createGate. GitHub remains the canonical durable record.
    private FeedbackIssue RememberConfirmed(FeedbackMarker marker, FeedbackIssue issue)
    {
        _confirmedAttempts[marker.Attempt] =
            new ConfirmedAttempt(marker, issue, DateTimeOffset.UtcNow);
        return issue;
    }

    /// <summary>
    /// GitHub's label-filtered Issue listing may lag a confirmed create.
    /// For a small, bounded window, verify missing confirmed Issues directly
    /// by their immutable GitHub Issue number using read-scoped credentials.
    /// Never return an unverified local receipt as an Issue.
    /// </summary>
    private async Task<List<StoredIssue>> ReadWithRecentConfirmationsAsync(
        string? reporterHmac, CancellationToken ct)
    {
        var issues = await ReadFeedbackIssuesAsync(ct);
        var numbers = issues.Select(issue => issue.Number).ToHashSet();
        var cutoff = DateTimeOffset.UtcNow - RecentConfirmationWindow;
        var missing = _confirmedAttempts.Values
            .Where(receipt =>
                receipt.ConfirmedAt >= cutoff &&
                (reporterHmac is null || receipt.Marker.Reporter == reporterHmac) &&
                !numbers.Contains(receipt.Issue.Number))
            .GroupBy(receipt => receipt.Issue.Number)
            .Select(group => group.First())
            .ToArray();
        if (missing.Length > MaxRecentDirectReadbacks)
            throw new FeedbackProviderException(FeedbackErrorKind.IncompleteRead,
                "GitHub recent Issue readback exceeded the bounded limit");
        foreach (var receipt in missing)
        {
            using var document = await RequestAsync(
                HttpMethod.Get, $"issues/{receipt.Issue.Number}",
                null, HttpStatusCode.OK, ct);
            var observed = ParseIssue(document.RootElement);
            if (observed is null || observed.Marker != receipt.Marker ||
                !observed.Labels.Contains(SourceLabel, StringComparer.Ordinal))
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub direct Issue readback did not match the confirmed submission");
            if (numbers.Add(observed.Number))
                issues.Add(observed);
        }
        return issues;
    }

    /// <summary>Server-side ownership filtering, not a browser-supplied Issue query.</summary>
    public async Task<IReadOnlyList<FeedbackIssue>> ListMineAsync(
        string reporterAccountId, CancellationToken ct = default)
    {
        ValidateReporter(reporterAccountId);
        var reporter = Hmac("reporter:v1:" + reporterAccountId);
        return (await ReadWithRecentConfirmationsAsync(reporter, ct))
            .Where(i => i.Marker.Reporter == reporter)
            .OrderByDescending(i => i.Number)
            .Select(Public).ToArray();
    }

    /// <summary>Call only after an independent administrator-grant check.</summary>
    public async Task<IReadOnlyList<FeedbackIssue>> ListAdminAsync(
        CancellationToken ct = default) =>
        (await ReadWithRecentConfirmationsAsync(null, ct))
            .OrderByDescending(i => i.Number).Select(Public).ToArray();

    /// <summary>Only a verified application feedback administrator may invoke this.</summary>
    public async Task<FeedbackIssue> SetTriageStatusAsync(
        int issueNumber, string status, CancellationToken ct = default)
    {
        if (issueNumber <= 0 || !ValidStatuses.Contains(status))
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidInput,
                "Unsupported Issue or triage status");
        using var currentJson = await RequestAsync(
            HttpMethod.Get, $"issues/{issueNumber}", null, HttpStatusCode.OK, ct);
        var current = ParseIssue(currentJson.RootElement);
        if (current is null || current.Number != issueNumber)
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidInput,
                "Not a configured application feedback Issue");
        await EnsureLabelAsync("status:" + status, ct);
        var labels = current.Labels
            .Where(label => !label.StartsWith("status:", StringComparison.Ordinal))
            .Append("status:" + status).Distinct(StringComparer.Ordinal).ToArray();
        using var resultJson = await RequestAsync(
            HttpMethod.Patch, $"issues/{issueNumber}",
            new { labels }, HttpStatusCode.OK, ct);
        var result = ParseIssue(resultJson.RootElement);
        if (result is null || result.Number != issueNumber ||
            result.Marker != current.Marker || result.Status != status)
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                "GitHub did not confirm the feedback triage update");
        return Public(result);
    }

    private async Task EnsureLabelAsync(string name, CancellationToken ct)
    {
        using var response = await RequestAsync(HttpMethod.Get,
            "labels/" + Uri.EscapeDataString(name), null, HttpStatusCode.OK, ct);
        if (response.RootElement.ValueKind != JsonValueKind.Object ||
            !response.RootElement.TryGetProperty("name", out var found) ||
            found.ValueKind != JsonValueKind.String ||
            found.GetString() != name)
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                "Configured GitHub label was not verified");
    }

    private async Task<List<StoredIssue>> ReadFeedbackIssuesAsync(CancellationToken ct)
    {
        var issues = new List<StoredIssue>();
        for (int page = 1; page <= MaxPages; page++)
        {
            using var response = await RequestAsync(HttpMethod.Get,
                $"issues?state=all&labels=source%3Afeedback&sort=created&direction=desc&per_page={PageSize}&page={page}",
                null, HttpStatusCode.OK, ct);
            if (response.RootElement.ValueKind != JsonValueKind.Array)
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub Issue listing is invalid");
            var count = 0;
            foreach (var item in response.RootElement.EnumerateArray())
            {
                count++;
                var parsed = ParseIssue(item);
                if (parsed is not null)
                    issues.Add(parsed);
            }
            if (count < PageSize)
                return issues;
        }
        // Never silently show incomplete "My Feedback" / retry-reconciliation data.
        throw new FeedbackProviderException(FeedbackErrorKind.IncompleteRead,
            "GitHub Issue listing exceeded the bounded retrieval limit");
    }

    private async Task<JsonDocument> RequestAsync(
        HttpMethod method, string relativePath, object? body,
        HttpStatusCode expectedStatus, CancellationToken ct)
    {
        // Owner/repo are immutable, validated server configuration; path is
        // built by this class, not by browsers or feedback text.
        var uri = new Uri("https://api.github.com/repos/" +
            _config.Owner + "/" + _config.Repository + "/" + relativePath);
        using var request = new HttpRequestMessage(method, uri);
        request.Headers.Authorization = new AuthenticationHeaderValue(
            "Bearer", await _tokens.GetInstallationTokenAsync(method != HttpMethod.Get, ct));
        request.Headers.UserAgent.ParseAdd("ProjectForgeFeedback/1.0");
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        request.Headers.TryAddWithoutValidation("X-GitHub-Api-Version", "2022-11-28");
        if (body is not null)
            request.Content = new StringContent(JsonSerializer.Serialize(body),
                Encoding.UTF8, "application/json");
        try
        {
            using var response = await _api.SendAsync(
                request, HttpCompletionOption.ResponseHeadersRead, ct);
            if (response.StatusCode != expectedStatus)
                throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                    "GitHub Issue request failed");

            if (response.Content.Headers.ContentType?.MediaType is not
                ("application/json" or "application/vnd.github+json"))
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "Unexpected GitHub response content type");
            await using var stream = await response.Content.ReadAsStreamAsync(ct);
            using var buffer = new MemoryStream();
            var chunk = new byte[8192];
            int length;
            while ((length = await stream.ReadAsync(chunk, ct)) != 0)
            {
                if (buffer.Length + length > MaxResponseBytes)
                    throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                        "GitHub Issue response exceeds size limit");
                buffer.Write(chunk, 0, length);
            }
            return JsonDocument.Parse(buffer.ToArray());
        }
        catch (HttpRequestException)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                "GitHub Issue provider is unavailable");
        }
        catch (JsonException)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                "GitHub Issue provider returned invalid JSON");
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                "GitHub Issue provider timed out");
        }
    }

    private StoredIssue? ParseIssue(JsonElement item)
    {
        if (item.ValueKind != JsonValueKind.Object ||
            item.TryGetProperty("pull_request", out _) ||
            !item.TryGetProperty("number", out var num) ||
            !num.TryGetInt32(out var number) || number <= 0 ||
            !item.TryGetProperty("html_url", out var link) ||
            link.GetString() is not { } url ||
            !string.Equals(url, _config.IssueUri(number).ToString(),
                StringComparison.OrdinalIgnoreCase) ||
            !item.TryGetProperty("body", out var text) ||
            text.ValueKind != JsonValueKind.String ||
            text.GetString() is not { } body)
            return null;
        var matches = MarkerPattern.Matches(body);
        if (matches.Count != 1)
            return null;
        var matched = matches[0];
        var marker = new FeedbackMarker(
            matched.Groups["reporter"].Value, matched.Groups["attempt"].Value,
            matched.Groups["payload"].Value, matched.Groups["kind"].Value);
        var labels = new List<string>();
        if (item.TryGetProperty("labels", out var array) &&
            array.ValueKind == JsonValueKind.Array)
        {
            foreach (var entry in array.EnumerateArray())
                if (entry.ValueKind == JsonValueKind.Object &&
                    entry.TryGetProperty("name", out var name) &&
                    name.ValueKind == JsonValueKind.String &&
                    name.GetString() is { } value)
                    labels.Add(value);
        }
        if (!item.TryGetProperty("title", out var title) ||
            title.ValueKind != JsonValueKind.String ||
            title.GetString() is not { } titleText)
            return null;
        DateTimeOffset created = DateTimeOffset.MinValue;
        if (item.TryGetProperty("created_at", out var date) &&
            date.ValueKind == JsonValueKind.String)
            DateTimeOffset.TryParse(date.GetString(), out created);
        var start = body.IndexOf("**Description**\n\n", StringComparison.Ordinal);
        string description = start >= 0
            ? body[(start + "**Description**\n\n".Length)..matched.Index].Trim()
            : body[..matched.Index].Trim();
        string status = labels.FirstOrDefault(
            x => x.StartsWith("status:", StringComparison.Ordinal))?["status:".Length..]
            ?? "unlabeled";
        return new StoredIssue(number, url, titleText, description, marker,
            status, created, labels);
    }

    private static FeedbackIssue Public(StoredIssue issue) =>
        new(issue.Number, issue.Url, issue.Title, issue.Description,
            issue.Marker.Kind, issue.Status, issue.CreatedAt);

    private static string MarkerText(FeedbackMarker marker) =>
        "<!-- project-forge-feedback:v1\n" +
        "reporter=" + marker.Reporter + "\n" +
        "attempt=" + marker.Attempt + "\n" +
        "payload=" + marker.Payload + "\n" +
        "kind=" + marker.Kind + "\n-->";

    private static void ValidateReporter(string reporter)
    {
        if (string.IsNullOrWhiteSpace(reporter) || reporter.Length > 240 ||
            reporter.Any(c => char.IsControl(c) || char.IsWhiteSpace(c)))
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidInput,
                "Invalid authenticated reporter reference");
    }

    private static void ValidateDraft(FeedbackDraft draft)
    {
        if (draft is null || draft.Kind is not ("bug" or "enhancement" or "other") ||
            string.IsNullOrWhiteSpace(draft.Title) ||
            draft.Title.Trim().Length is < 5 or > 150 ||
            draft.Title.Any(c => char.IsControl(c)) ||
            string.IsNullOrWhiteSpace(draft.Description) ||
            draft.Description.Trim().Length is < 5 or > 10000 ||
            draft.Description.Any(c => char.IsControl(c) && c is not '\n' and not '\t') ||
            string.IsNullOrWhiteSpace(draft.IdempotencyKey) ||
            !AttemptKeyPattern.IsMatch(draft.IdempotencyKey) ||
            SensitiveContent.IsMatch(draft.Title) ||
            SensitiveContent.IsMatch(draft.Description))
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidInput,
                "Invalid feedback type, title, description or submission key");
    }

    private string Hmac(string value) =>
        Convert.ToHexString(HMACSHA256.HashData(
            _config.ReporterHmacKey, Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static string Digest(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private sealed record ConfirmedAttempt(FeedbackMarker Marker,
        FeedbackIssue Issue, DateTimeOffset ConfirmedAt);

    private sealed record FeedbackMarker(string Reporter, string Attempt,
        string Payload, string Kind);

    private sealed record StoredIssue(int Number, string Url, string Title,
        string Description, FeedbackMarker Marker, string Status,
        DateTimeOffset CreatedAt, List<string> Labels);
}
