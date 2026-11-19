using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ProjectForge.ReleaseNotes.Runtime;

public sealed record Announcement(
    string AnnouncementId,
    string Category,
    string Title,
    string Summary,
    string? Details,
    string Visibility,
    int Priority,
    int Revision);

public sealed record ApprovedManifest(string ReleaseKey, string ReleaseVersion,
    IReadOnlyList<Announcement> Entries, string Sha256);

public sealed record RunningRelease(
    string ProjectId, string Environment, string SourceCommit,
    string ImageDigest, string ReleaseVersion);

/// <summary>
/// Must come ONLY from an application-authorized Deployment Kit evidence reader,
/// never HTTP headers, cookies, query parameters or an app-bundled static file.
/// This value is not itself a cryptographic signature.
/// </summary>
public sealed record TrustedVerifiedActivation(
    int SchemaVersion, string ProjectId, string Environment,
    string SourceCommit, string ImageDigest, string ManifestSha256,
    string ReleaseVersion, DateTimeOffset VerifiedAtUtc, string Outcome);

public sealed class ReleaseNoteContractException(string message) : Exception(message);

public static class ReleaseNotesContracts
{
    private static readonly Regex ReleaseKeyPattern = new("^[a-z0-9][a-z0-9-]{2,79}$", RegexOptions.CultureInvariant);
    private static readonly Regex AnnouncementIdPattern = new("^[a-z0-9][a-z0-9-]{2,119}$", RegexOptions.CultureInvariant);
    private static readonly Regex VersionPattern = new(@"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$", RegexOptions.CultureInvariant);
    private static readonly Regex ShaPattern = new("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex CommitPattern = new("^[0-9a-f]{40}$", RegexOptions.CultureInvariant);
    private static readonly HashSet<string> Categories = ["feature", "improvement", "fix", "security", "other"];
    private static readonly HashSet<string> Visibilities = ["popup-and-history", "history-only"];
    private static readonly HashSet<string> RootFields = ["schemaVersion", "releaseKey", "releaseVersion", "releasedAtUtc", "entries"];
    private static readonly HashSet<string> EntryFields = ["announcementId", "category", "title", "summary", "details", "visibility", "priority", "revision"];
    private static readonly HashSet<string> RequiredEntryFields = ["announcementId", "category", "title", "summary", "visibility", "priority", "revision"];

    public static ApprovedManifest ParseReviewedManifest(ReadOnlySpan<byte> bytes)
    {
        if (bytes.Length == 0 || bytes.Length > 128 * 1024)
            throw new ReleaseNoteContractException("Approved manifest must contain 1–131072 UTF-8 bytes.");
        using var document = JsonDocument.Parse(bytes.ToArray(), new JsonDocumentOptions { MaxDepth = 12, CommentHandling = JsonCommentHandling.Disallow });
        var root = document.RootElement;
        RequireFields(root, RootFields, RootFields, "Manifest");
        if (Int(root, "schemaVersion") != 1)
            throw new ReleaseNoteContractException("Unsupported Release Notes manifest schema.");
        string releaseKey = String(root, "releaseKey");
        string version = String(root, "releaseVersion");
        if (!ReleaseKeyPattern.IsMatch(releaseKey) || !VersionPattern.IsMatch(version))
            throw new ReleaseNoteContractException("Invalid release identity.");
        if (root.GetProperty("releasedAtUtc").ValueKind != JsonValueKind.Null)
            throw new ReleaseNoteContractException("Source files cannot claim a verified deployment date.");
        var content = root.GetProperty("entries");
        if (content.ValueKind != JsonValueKind.Array || content.GetArrayLength() > 100)
            throw new ReleaseNoteContractException("Invalid bounded approved entry list.");
        var notes = new List<Announcement>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var raw in content.EnumerateArray())
        {
            RequireFields(raw, EntryFields, RequiredEntryFields, "Announcement");
            var id = String(raw, "announcementId");
            var category = String(raw, "category");
            var visibility = String(raw, "visibility");
            if (!AnnouncementIdPattern.IsMatch(id) || !ids.Add(id)
                || !Categories.Contains(category) || !Visibilities.Contains(visibility))
                throw new ReleaseNoteContractException("Unknown or duplicated announcement identity/category.");
            int priority = Int(raw, "priority");
            int revision = Int(raw, "revision");
            if (priority is < 0 or > 100 || revision is < 1 or > 100000)
                throw new ReleaseNoteContractException("Invalid announcement priority/revision.");
            var title = CheckedText(raw, "title", 120);
            var summary = CheckedText(raw, "summary", 350);
            var details = raw.TryGetProperty("details", out _) ? CheckedText(raw, "details", 2000, allowNewlines: true) : null;
            notes.Add(new Announcement(id, category, title, summary, details, visibility, priority, revision));
        }
        return new ApprovedManifest(releaseKey, version, notes, Convert.ToHexStringLower(SHA256.HashData(bytes)));
    }

    /// <summary>
    /// No release notes can be served unless the trusted, post-Production receipt
    /// matches all observed runtime facts and the exact reviewed manifest bytes.
    /// </summary>
    public static bool IsVerifiedActive(ApprovedManifest manifest, RunningRelease running,
        TrustedVerifiedActivation? evidence)
    {
        if (evidence is null || evidence.SchemaVersion != 1 || evidence.Outcome != "verified"
            || evidence.Environment != "production" || running.Environment != "production")
            return false;
        if (!ShaPattern.IsMatch(manifest.Sha256) || !ShaPattern.IsMatch(evidence.ManifestSha256)
            || !CommitPattern.IsMatch(running.SourceCommit)
            || !CommitPattern.IsMatch(evidence.SourceCommit)
            || !running.ImageDigest.StartsWith("sha256:", StringComparison.Ordinal)
            || !ShaPattern.IsMatch(running.ImageDigest[7..])
            || !evidence.ImageDigest.StartsWith("sha256:", StringComparison.Ordinal)
            || !ShaPattern.IsMatch(evidence.ImageDigest[7..]))
            return false;
        if (evidence.ProjectId != running.ProjectId
            || evidence.SourceCommit != running.SourceCommit
            || evidence.ImageDigest != running.ImageDigest
            || evidence.ManifestSha256 != manifest.Sha256
            || evidence.ReleaseVersion != manifest.ReleaseVersion
            || running.ReleaseVersion != manifest.ReleaseVersion)
            return false;
        if (evidence.VerifiedAtUtc.Offset != TimeSpan.Zero || evidence.VerifiedAtUtc > DateTimeOffset.UtcNow)
            return false;
        return true;
    }

    private static string CheckedText(JsonElement value, string key, int max, bool allowNewlines = false)
    {
        var text = String(value, key);
        if (text.Length == 0 || text.Length > max || text != text.Trim()
            || text.Contains('<') || text.Contains('>')
            || text.Contains("NEEDS HUMAN DESCRIPTION", StringComparison.OrdinalIgnoreCase)
            || text.Contains("http://", StringComparison.OrdinalIgnoreCase)
            || text.Contains("https://", StringComparison.OrdinalIgnoreCase)
            || text.Contains("www.", StringComparison.OrdinalIgnoreCase)
            || text.Contains("](", StringComparison.Ordinal)
            || text.Any(c => char.IsControl(c) && (c != '\n' || !allowNewlines))
            || (text.Contains('\n') && !allowNewlines))
            throw new ReleaseNoteContractException("Unsafe or unreviewed human-facing text.");
        return text;
    }

    private static string String(JsonElement value, string key)
    {
        var x = value.GetProperty(key);
        if (x.ValueKind != JsonValueKind.String)
            throw new ReleaseNoteContractException("Wrong field type in release manifest.");
        return x.GetString() ?? throw new ReleaseNoteContractException("Missing content field.");
    }

    private static int Int(JsonElement value, string key)
    {
        var x = value.GetProperty(key);
        if (x.ValueKind != JsonValueKind.Number || !x.TryGetInt32(out var number))
            throw new ReleaseNoteContractException("Wrong integer field in release manifest.");
        return number;
    }

    private static void RequireFields(JsonElement value, HashSet<string> allowed,
        HashSet<string> required, string name)
    {
        if (value.ValueKind != JsonValueKind.Object)
            throw new ReleaseNoteContractException($"{name} must be a JSON object.");
        var properties = value.EnumerateObject().Select(x => x.Name).ToList();
        if (properties.Count != properties.Distinct(StringComparer.Ordinal).Count()
            || properties.Any(x => !allowed.Contains(x))
            || required.Any(x => !properties.Contains(x, StringComparer.Ordinal)))
            throw new ReleaseNoteContractException($"{name} contains unexpected, duplicated or missing fields.");
    }
}
