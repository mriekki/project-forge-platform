# Project Forge Release Notes Kit — consumer integration contract

**Status:** source-only, **default OFF**. This file describes the conditional
distribution layout, not an available/supported or automatically enabled feature.

The canonical source owner is `mriekki/project-forge-release-notes-kit`.
Project Forge Platform distributes selected version-pinned components within
`@mriekki/project-forge`; consumers do **not** need a separate npm publication
of this source Kit. The current source is reviewed in
[Kit PR #2](https://github.com/mriekki/project-forge-release-notes-kit/pull/2).
The build, publication and FMP Production gates remain independent.

## Opt-in distribution layout

The versioned `distributions/greenfield-project.json` maps only Kit-owned,
non-secret, reusable artifacts under:

- `tools/project-forge-release-notes-kit/ProjectForge.ReleaseNotes.Runtime/`
  — .NET 10 manifest parsing, verified-activation requirements, protected
  batch tokens, server-side unread selection, signed Release Kit verifier.
- `tools/project-forge-release-notes-kit/ui/` — React 19 dialog, persistent
  history, catch-up logic, CSS and dependency-lock/typecheck metadata.
- `tools/project-forge-release-notes-kit/contract/` — versioned JSON
  schemas for application-authored content and trusted release projection.
- `tools/project-forge-release-notes-kit/tools/validate_manifest.py`
  — manually invoked editorial shape validation.
- This document.

It **does not** copy app-specific migrations, authentication secrets, host
scripts, Production credentials, example/test data or a published announcements
file. There is **no** automatically executed startup hook, route, database
creation, deploy step or CI AI call. Platform packaging must qualify the source
pin and keep the component excluded from default profiles until the accepted
reference pilot.

## Consumer-owned requirements

The FMP pilot owns the web/API adapter and application data. Before enabling
any user-facing endpoint or popup:

1. **Content:** put human-reviewed approved manifests in application-owned
   source; map the **exact approved bytes** to a trusted immutable image
   release. Do not infer announcements from issue closures, a tag, CI or image
   publication.
2. **Verified Production:** obtain Deployment Kit's attested release and
   independently trusted current runtime identity/generation **after** the
   approved Production deployment, including rollback freshness. A JSON
   record named `TrustedVerifiedActivation` is not, on its own, trust.
3. **Authorization:** derive the account only from the existing server-side
   Auth Kit session. Check exact public HTTPS Origin and ASP.NET antiforgery
   for acknowledgement POST; never accept caller-provided account IDs or
   eligible announcement IDs. Sign the entire currently eligible batch and
   recompute it against currently active releases at POST time.
4. **Persistence:** FMP keeps `release-notes.sqlite` separate from
   authentication's exact-table `app.db`, with explicit migration,
   image-bound backup, isolated restore, and old-image rollback validation.
5. **UX:** use the Kit's dialog and history as imported source (or a
   properly source-pinned package mapping), with full mobile and keyboard
   accessibility, missed-release catch-up, acknowledged IDs retained across
   devices, no automatic read acknowledgement and no login blocker on errors.
6. **Testing and acceptance:** test missing/forged/rolled-back receipts;
   cross-account/CSRF failure; failed/duplicate writes; offline/old PWA;
   browser focus and iPhone installed PWA. Human meaningful-diff review,
   Kit/Platform package qualification, and Production authorization are
   separate gates.

## Version/ownership

Only Kit canonical PRs change shared `ProjectForge.ReleaseNotes.Runtime`,
React UI or schemas. App adaptations belong to the app; deployment truth
belongs to Deployment Kit; Platform owns assembly/public
`@mriekki/project-forge` publishing. Don't patch Platform-generated copies
as a replacement for upstream changes.

The distribution descriptor is **not** a reason to activate a new Project
profile until source, FMP E2E and rollback are verified and the Builder
approves packaging/release.
