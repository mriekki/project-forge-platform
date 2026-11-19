namespace ProjectForge.ReleaseNotes.Runtime;

public sealed record UnreadReleaseNoteBatch(
    int UnreadCount,
    IReadOnlyList<string> BatchIds,
    IReadOnlyList<Announcement> Highlights,
    int MoreCount);

/// <summary>
/// Pure server-side presentation selection for already-authorized, verified-active
/// announcements. The host MUST first validate Production activation, account
/// identity and the eligible set of historical releases. This class grants none.
/// </summary>
public static class ReleaseNotesSelection
{
    public static UnreadReleaseNoteBatch SelectUnread(
        IReadOnlyCollection<Announcement> verifiedActiveEntries,
        IReadOnlySet<string> acknowledgedIds,
        int maxHighlights = 5)
    {
        ArgumentNullException.ThrowIfNull(verifiedActiveEntries);
        ArgumentNullException.ThrowIfNull(acknowledgedIds);
        if (maxHighlights is < 1 or > 5 || verifiedActiveEntries.Count > 500)
            throw new ReleaseNoteContractException("Release-note selection exceeds approved bounds.");

        var names = new HashSet<string>(StringComparer.Ordinal);
        var unread = new List<Announcement>();
        foreach (var note in verifiedActiveEntries)
        {
            if (note is null || string.IsNullOrWhiteSpace(note.AnnouncementId) ||
                !names.Add(note.AnnouncementId))
                throw new ReleaseNoteContractException("Duplicate or missing verified announcement ID.");
            if (note.Visibility is not ("popup-and-history" or "history-only"))
                throw new ReleaseNoteContractException("Unknown verified announcement visibility.");
            if (note.Priority is < 0 or > 100)
                throw new ReleaseNoteContractException("Unreviewed verified announcement priority.");
            if (note.Visibility == "popup-and-history" &&
                !acknowledgedIds.Contains(note.AnnouncementId))
                unread.Add(note);
        }

        var prioritized = unread
            .OrderByDescending(note => note.Priority)
            .ThenBy(note => note.AnnouncementId, StringComparer.Ordinal)
            .ToList();

        return new UnreadReleaseNoteBatch(
            prioritized.Count,
            prioritized.Select(note => note.AnnouncementId).ToArray(),
            prioritized.Take(maxHighlights).ToArray(),
            Math.Max(0, prioritized.Count - maxHighlights));
    }
}
