/** Pure, provider-neutral catch-up selection. Only call with server-verified active content. */
export function summarizeActiveAnnouncements(entries, acknowledged, maximumHighlights = 5) {
  if (!Array.isArray(entries) || !Array.isArray(acknowledged) || !Number.isInteger(maximumHighlights) ||
      maximumHighlights < 1 || maximumHighlights > 5) {
    throw new TypeError('Invalid bounded release announcement selection');
  }
  const seen = new Set(acknowledged);
  const ids = new Set();
  const active = [];
  for (const item of entries) {
    if (!item || typeof item.announcementId !== 'string' || ids.has(item.announcementId)) {
      throw new TypeError('Announcement IDs must be unique and verified');
    }
    ids.add(item.announcementId);
    if (item.visibility === 'popup-and-history' && !seen.has(item.announcementId)) {
      active.push(item);
    } else if (item.visibility !== 'popup-and-history' && item.visibility !== 'history-only') {
      throw new TypeError('Unsupported announcement visibility');
    }
  }
  active.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.announcementId.localeCompare(b.announcementId));
  return {
    unreadCount: active.length,
    batchIds: active.map((x) => x.announcementId),
    highlights: active.slice(0, maximumHighlights),
    moreCount: Math.max(0, active.length - maximumHighlights),
  };
}
