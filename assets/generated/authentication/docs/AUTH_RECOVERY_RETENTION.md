# Auth Kit recovery-set inventory and retention contract

This is an internal low-level Project recovery building block, not an
operator-ready Production backup command and **not** application recovery
qualification. The canonical generated Auth Kit helper is
`tools/project-forge-auth-kit/project_auth_recovery.py`.

## Inert backup set

The owner must first independently quiesce its *exact* application instance,
prove a stable stopped Docker container/image and stable private storage, and
checkpoint any SQLite WAL. The `capture_quiesced_set(source, destination,
declaration, runtime_guard)` helper cannot stop the app or prove that the
provided runtime guard is trustworthy.

Use a new private backup-set parent (0700 on POSIX), outside the live data
tree. Each set name must have form `YYYYMMDDTHHMMSSZ-<8..32 lowercase hex>`
with a valid UTC calendar timestamp and collision-resistant suffix. The set
contains exactly `auth.sqlite`, `keys/key-*.xml`, and `receipt.json`.
Capture publishes exclusively; an existing destination, even an empty one
created after the initial check, is never replaced. A failed capture cleans
only its newly created private staging directory.

The receipt contains only Project identifier, recovery policy, protector
generation and file digests. It is **not signed** and cannot establish
provenance against a privileged attacker capable of rewriting both data
and receipt. Provider credentials and application secrets are not stored
in it.

## Read-only inventory and retention

`plan_verified_retention(sets_root, declaration, keep_last=7)` inspects
every set before recommending **candidate names only**. It requires owner
private inventory storage, exact canonical names, valid receipts, complete
SQLite/key material, SHA-256 integrity, compatible Auth Kit schema and the
same declared Project, generation and authentication policy. Any
interrupted staging directory, symlink, missing/corrupt member, unknown
directory, or unexpected Project identity blocks the entire plan.

The function preserves at least two newest verified sets and at most
1,000 tracked sets; the **plan never deletes anything**. No background job,
notification, or email receipt is installed by this function.

## Explicit disposable-only deletion primitive (not a scheduled operation)

`apply_reviewed_disposable_retention(sets_root, lock_directory, declaration,
reviewed_plan, keep_last=7, environment="disposable",
authorize_disposable_delete=True)` is a Linux-only, low-level primitive.
It rejects every non-disposable environment, implicit authorization, unsafe
private directories, symlinks, corrupt sets, and inventory changes since the
complete **read-only plan** was reviewed. It preserves at least the latest two
verified recovery sets, bounds deletions to 32 per invocation, uses a private
nonblocking retention lock, and anchors unlink/rmdir operations to no-follow
directory descriptors instead of invoking recursive path deletion. After
each batch the operator must obtain and review a new read-only plan.

**This is not automatically called by capture or setup**, and is not a
Production retention CLI. The caller is responsible for proving the exact
generated Project's ownership, separation from live data, completed backup,
and the intended disposable environment. A directory deletion spanning
multiple files is **not atomic**; on a filesystem failure, a partially
pruned old candidate may need manual inspection/reconciliation before
any further retention or backup inventory planning. Do not treat a
partial failure as retention success.

Deployment Kit must still add and qualify a separately reviewed operator
driver coordinating the backup/recovery lifecycle lock, durable status and
receipts, persistent scheduling, recovery-point verification, escalation and
notification before automatic retention is permissible.

## Restore is isolated and not readiness

`materialize_disposable_restore` creates only a new separate directory
outside backup and live paths and rechecks the hashes. No live data
overwrite or application restart occurs. A separate disposable application
must demonstrate actual key-ring protector viability, session-preservation
or invalidation policy, provider configuration recovery and health before
`applicationRecoveryReady` can ever be true. Artifact inspection always
reports it as **false**.

## Running application health is not recovery readiness

The managed .NET Auth Kit maps `GET /health` **behind the exact trusted
Caddy peer/public-origin middleware**, not on an unprotected direct socket.
It performs a read-only check that the current per-Project Auth SQLite file
already exists with supported schema and expected account/session tables.
Missing, uninitialized or corrupt SQLite returns HTTP 503 without creating
a replacement identity database. An ordinary running instance with a
readable store returns 200. The endpoint exposes no account details,
filesystem paths, providers or session tokens.

This is an **application liveness signal only**, not a recovery completion
gate: even 200 does not prove that the restored DataProtection keyring
can decrypt historical state, that a prior session still authorizes,
that real Google/Resend work, that the backup set was preserved, that a
scheduled job/alert reached its target, or that normal routed traffic
is safe. All those remain independently proven acceptance requirements.

This material is not permission to change any PWA Production service, use
a household Provider credential, release the Authentication component to
npm, or label a generated Project ready for Production.
