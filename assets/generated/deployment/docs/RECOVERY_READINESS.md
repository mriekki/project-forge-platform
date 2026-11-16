# Recovery Readiness Contract V1

Project Forge distinguishes a verified database backup from verified application recovery. A successful SQLite backup proves only the database artifact created by the application's SQLite maintenance contract; it does not prove that every dependency required to recover authentication or the full application is available or usable.

## Recovery states

Reusable evidence must keep these concepts separate:

1. `databaseBackupVerified` — the SQLite database backup operation completed successfully.
2. `verifiedBackupScope` — currently `database` for SQLite backup evidence.
3. `recoveryScopeDeclared` — the consumer supplied a strict, non-secret recovery declaration.
4. `unresolvedRequiredDependencies` — required non-database dependencies that still need recovery-time verification.
5. `authenticationPolicyVerified` — the selected authentication recovery policy has been dynamically verified after restore.
6. `applicationRecoveryReady` — all required recovery dependencies and the selected policy have been verified for the restored application.

Current SQLite backup/import/migration commands never set `applicationRecoveryReady` to true. Deployment Kit does not yet provide a general restore engine.

## Recovery manifest

`sqlite backup` and existing-database `sqlite migrate` may receive `--recovery-manifest <path>` pointing to UTF-8 JSON with exactly this schema:

```json
{
  "schemaVersion": 1,
  "authenticationPolicy": "invalidate-authentication",
  "dependencies": [
    {
      "id": "data-protection-key-ring",
      "type": "cryptographic-key-ring",
      "required": true
    }
  ]
}
```

`authenticationPolicy` may be `preserve-authentication`, `invalidate-authentication`, or `null`. Dependency IDs/types are non-secret identifiers only. Unknown fields fail closed. Do not put paths, keys, credentials, cookies, tokens, passwords, action links, provider secrets, or secret values in the manifest.

The normalized manifest is fingerprinted deterministically and the privacy-safe declaration/readiness summary is included in SQLite evidence. Secret contents are neither archived nor printed by this contract. First-install migration, import, interrupted-import recovery, and rollback checking do not accept a recovery manifest in V1.

## Authentication recovery policies

`preserve-authentication` means a future recovery workflow must prove that required cryptographic/protector dependencies remain usable and that retaining historical authentication state is acceptable.

`invalidate-authentication` means a future recovery workflow must prove that sessions and action links from historical state cannot authenticate or mutate accounts after recovery. Merely replacing a key ring is not sufficient evidence because password hashes, security stamps, sessions, token expiry/consumption, and similar state may also exist in the restored database.

Neither policy is considered verified by a database backup alone.

## Pre-traffic invariant

A future restore operation must fail closed and keep the restored application unavailable to normal traffic until all required recovery dependencies and the selected authentication policy have been verified. Restore completion and database integrity must never be treated as equivalent to application recovery readiness.

## Requirements

- **PF-REC-001** — Database backup verification must never imply whole-application recovery readiness.
- **PF-REC-002** — Consumers may declare non-database recovery dependencies without exposing secret values.
- **PF-REC-003** — Required dependencies must be verified before application recovery readiness can pass.
- **PF-REC-004** — Authentication-bearing consumers must select an explicit post-restore authentication policy when they want application recovery readiness.
- **PF-REC-005** — Historical restore must remain unavailable to normal traffic until that policy is verified.
- **PF-REC-006** — Incomplete or failed recovery evidence fails closed.
- **PF-REC-007** — Existing SQLite-only consumers retain current database backup behavior and database-only success semantics.
- **PF-REC-008** — Read-only planning/readiness inspection performs no restore, key manipulation, revocation, rotation, or other destructive action.
- **PF-REC-009** — Dynamic recovery validation uses disposable fixtures and never logs secret material.


## Opt-in generated Auth Kit stopped-container capture adapter (pre-release)

Deployment Kit's internal `auth_recovery_capture.capture_reviewed_stopped_auth_project`
composes a separately reviewed, installed Authentication Kit helper with the
existing strict Linux Docker stopped-container guard. Before any backup
artifact write, it requires:

- exact public Auth Kit component revision and **independently reviewed**
  recovery-helper SHA-256, matching the generated Project's
  `AUTHENTICATION_BASELINE.json` and actual helper bytes;
- exactly reviewed Docker container name, owner/environment labels, immutable
  image digest, restart-disabled *exited* state and private bind-mounted data;
- explicit container Auth Kit SQLite path `<reviewed-data-mount>/auth.sqlite`
  and persistent DataProtection keys path `<reviewed-data-mount>/keys`;
- the Auth Kit helper's existing no-overwrite, quiescence-recheck, SQLite
  integrity and key-ring receipt checks.

This is an **internal, no-CLI** building block, not an operator-ready
scheduled backup or a service stop/start controller. It never stops,
starts or restarts a container, edits shared routing, reads provider
credentials, or reports application recovery readiness. Only the calling
approved Project workflow may establish and release service quiescence;
only disposable application startup and cryptographic/session policy tests
can later qualify application restoration.

This stricter Auth-specific contract does not change the existing
SQLite-only consumers or `PF-REC-001` through `PF-REC-009`.

## Explicit disposable Auth stop/capture/resume (pre-release)

The internal `auth_recovery_lifecycle.capture_with_disposable_service_pause`
function now coordinates the exact stopped-container capture adapter for
**disposable environment only**. It is *not* a Production or scheduled backup
command. The caller must independently approve the exact Docker container,
image digest, owner labels, data mount, public Auth Kit source revision, managed
helper SHA-256, and recovery declaration. An explicit
`authorize_disposable_stop=True` is required before Docker mutation.

Safety sequence:

1. Fail closed on unsupported platform, non-disposable environment, missing
   authorization, stale managed helper, invalid declaration/backup set name,
   data-path overlap, symlinks, unsafe private directories or bad auth mounts;
   do all these checks **before stopping a service**.
2. Acquire a nonblocking, OS-exclusive lock in an owner-private, separate
   directory. Recheck destination collision.
3. Inspect the exact *running*, restart-disabled, labeled Docker container,
   immutable image digest, mounted data and canonical DbPath/key-ring bindings.
4. Stop **only** its exact original container ID using a bounded Docker stop
   request; re-inspect and reject container/ownership/image drift.
5. Capture using the pinned Auth helper plus stopped-container guard, whose
   image/identity is rechecked throughout artifact capture.
6. Regardless of capture success or failure, attempt to resume only the same
   reviewed stopped Docker ID; if already running, verify it is exactly the
   expected original identity. Unknown/new/drifted containers are **never**
   started. Failure to prove resumption yields a manual-recovery-required
   outcome instead of a false backup success.
7. Report independent booleans: backup artifact integrity, resumed Docker
   runtime, application health, traffic readiness, scheduling, alert receipt
   and whole-application restore. **Resumed Docker does not establish health,
   application or session recovery.**

This limited stop/start helper cannot automatically recover from abrupt
host power loss or termination without an independently installed and
reviewed supervisor, which may invoke the journal recovery primitive below. It does not
configure retention deletion, scheduling, notification, backup off-host
replication, real providers, production ingress or a traffic health probe.
It is available for disposable qualification tests, not a general-purpose
operator command. A release-worthy scheduled workflow requires an external
restart fail-safe, verified post-start readiness, durable success/failure
receipts, and independently proven isolated full-application restore.

## Durable interrupted-disposable restart journal (pre-release)

The disposable Auth backup lifecycle now records a single owner-private,
fsync-committed `auth-backup-restart.json` inside its separate lock directory
**before** stopping Docker. The journal contains only an exact original
container ID, immutable image digest, SHA-256 of the reviewed binding, a
canonical backup-set name and contract metadata. It never contains raw
provider environment variables or secrets. A second backup is blocked while
the journal remains, even if the original worker died and released its OS
lock.

An independently invoked
`auth_recovery_lifecycle.recover_interrupted_disposable_auth` can, **with
explicit authorization**, take the same OS lock, compare the complete
independently reviewed disposable Docker identity to the journal, inspect
the current service and start **only** its original exact container ID when
stopped. An unknown/changed owner, name, image, mount, binding, or runtime
ID is never started. If the original is already running, only the valid
journal is cleared. Syncing the private directory before/after journal
creation/deletion protects against ordinary process interruption; an
uncertain journal write fails before any stop.

This is a crash recovery *primitive*, **not yet an installed supervisor**.
A process or host crash still requires a separate, reviewed host service to
invoke it. It neither automatically schedules backup capture nor establishes
application health or traffic readiness. A restarted Docker process may
still fail its HTTP health, authentication/session, provider or normal
traffic tests. The journal is owner-private evidence, not a
cryptographically authenticated receipt against a privileged host attacker.

## Non-scope

This contract does not implement generic secret archival, provider-specific secret storage, key transport, key rotation, session/token mutation, or a general database/application restore workflow. Those require separate requirements, plan approval, implementation review, and release/adoption gates.
