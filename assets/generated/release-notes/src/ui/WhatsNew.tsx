import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import './WhatsNew.css';

export type Announcement = {
  announcementId: string;
  title: string;
  summary: string;
  details?: string;
  category: 'feature' | 'improvement' | 'fix' | 'security' | 'other';
  visibility: 'popup-and-history' | 'history-only';
  priority: number;
  revision: number;
};

export type ActiveSummary = {
  batchToken: string; // Issued by the authenticated server; never guessed in the browser.
  manifestDigest: string;
  unreadCount: number;
  batchIds: string[]; // Entire disclosed batch, not only the visible highlights.
  highlights: Announcement[];
  moreCount: number;
};

export type HistoryRelease = {
  releaseKey: string;
  releaseVersion: string;
  verifiedAtUtc: string;
  entries: Announcement[];
};

/**
 * Only the application backend can decide whether a verified Production manifest
 * is active. Caller passes server-supplied summary and a CSRF-protected mutation.
 * No automatic acknowledgement on display, history, blur, backdrop or network loss.
 */
export function WhatsNewDialog({
  summary, onAcknowledge, onViewHistory,
}: {
  summary: ActiveSummary | null;
  onAcknowledge: (batchToken: string, batchIds: readonly string[]) => Promise<void>;
  onViewHistory: () => void;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const [closedBatch, setClosedBatch] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const open = !!summary && summary.unreadCount > 0 && closedBatch !== summary.batchToken;

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();
    return () => previouslyFocused.current?.focus();
  }, [open]);

  async function dismiss() {
    if (!summary || submitting) return;
    setSubmitting(true);
    try {
      await onAcknowledge(summary.batchToken, summary.batchIds);
    } catch {
      // Acknowledgement failures must not trap the user. It may show again
      // on a future session once the server can confirm persistence.
      setError('Could not save that you viewed these updates. They may appear again later.');
    } finally {
      setClosedBatch(summary.batchToken);
      setSubmitting(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      void dismiss();
    } else if (event.key === 'Tab') {
      const controls = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href]') ?? []);
      if (controls.length === 0) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  if (!open || !summary) return error ? <p role="status" className="pf-rn-status">{error}</p> : null;
  return (
    <div className="pf-rn-backdrop">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={titleId}
        tabIndex={-1} onKeyDown={handleKeyDown} className="pf-rn-dialog">
        <div className="pf-rn-heading">
          <h2 id={titleId}>What's New</h2>
          <button type="button" ref={closeButtonRef} disabled={submitting} aria-label="Close What's New"
            onClick={() => void dismiss()} className="pf-rn-icon-button">×</button>
        </div>
        <p>Here's what's improved since your last visit.</p>
        <ul className="pf-rn-list">
          {summary.highlights.map(item => (
            <li key={item.announcementId}>
              <strong>{item.title}</strong>
              <p>{item.summary}</p>
            </li>
          ))}
        </ul>
        {summary.moreCount > 0 && <p>{summary.moreCount} more update(s) are included.</p>}
        <div className="pf-rn-actions">
          <button type="button" onClick={() => {
            // History navigation is not acknowledgement. Only the local dialog closes.
            setClosedBatch(summary.batchToken);
            onViewHistory();
          }}>View all updates</button>
          <button type="button" disabled={submitting} onClick={() => void dismiss()}>
            {submitting ? 'Saving…' : 'Got it'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function WhatsNewHistory({ releases, onBack, meaningfulUnreadCount }: {
  releases: HistoryRelease[];
  onBack: () => void;
  meaningfulUnreadCount: number;
}) {
  return <section aria-label="What's New history" className="pf-rn-history">
    <div className="pf-rn-heading">
      <h2>What's New</h2>
      <button type="button" onClick={onBack}>Back</button>
    </div>
    {meaningfulUnreadCount > 0 && <p role="status">{meaningfulUnreadCount} unread announcement(s)</p>}
    {releases.length === 0 ? <p>No published updates yet.</p> : (
      releases.map(release => <article key={release.releaseKey}>
        <h3>Version {release.releaseVersion}</h3>
        <time dateTime={release.verifiedAtUtc}>{new Date(release.verifiedAtUtc).toLocaleDateString()}</time>
        <ul>
          {release.entries.map(entry => <li key={entry.announcementId}>
            <strong>{entry.title}</strong><p>{entry.summary}</p>
            {entry.details && <p>{entry.details}</p>}
          </li>)}
        </ul>
      </article>)
    )}
  </section>;
}
