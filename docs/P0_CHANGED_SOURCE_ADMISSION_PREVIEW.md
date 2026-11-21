# P0 read-only private-source changed-component admission preview

**Status:** Default remains historical 4.35.0 verification. This is an **extra, explicitly selected, nonpublishing** preview mode in the already-existing public Platform manual admission workflow, not a new publisher, release job, or npm version.

## What this validates

The public Platform workflow keeps its original protected-read-only PAT, private repo ID/mapping, authenticated GitHub REST repository/main/Actions evidence, exact merged-main private qualification, SHA-pinned checkout, byte-identical 4.35.0 historical rebuild and durable public receipt verification. These steps run **regardless of preview mode**.

The optional `candidate_mode=changed-feedback-4.36-preview` then:

1. Checks the same exact admitted private Git commit; independently runs the source candidate builder and verifier from that SHA. Source input/provenance checks remain private and fail closed.
2. Packages the output-only changed Feedback `4.36.0-preview.2` candidate and verifies its asset assembly. The preview source is a separately committed Feedback documentation file, **not** a changed live Feedback Kit release.
3. Executes the independently public-owned `scripts/verify-private-changed-source-preview.mjs` against the actual npm archive bytes and untrusted v1 sidecar. It checks the package/version, source commit ID, legacy component revision conservation, new Feedback Git-commit revision kind, output mapping hash, all five canonical mapped-input digest formats, and hard-negative publication/Production/ownership claims.
4. Re-reads protected private `main` after the preview, rejecting any source drift.

No new GitHub Actions job, credential, signing key, cross-repo artifact, npm token, tag, real Project change or new source owner is created. The live `npm-publish.yml` and public npm OIDC trust remain untouched.

## How to run after source main qualification

First the private source `main` HEAD needs a **new successful manual exact-main qualification run for the current SHA**, because changes made after the prior run invalidate that old same-SHA admission evidence.

Run the public [P0 Private Source Admission Preview](https://github.com/mriekki/project-forge-platform/actions/workflows/p0-monorepo-source-preview.yml) on `main` using:

- `exact_source_sha`: current successful private-source main SHA.
- `source_qualification_run_id`: successful full exact-main private qualification Actions run ID for that exact SHA.
- `candidate_mode`: `changed-feedback-4.36-preview` (the default `historical-4.35` remains unchanged).

Only the already-enabled protected `PF_MONOREPO_SOURCE_PREVIEW_ENABLED=true` variable and three existing protected `PF_MONOREPO_SOURCE_*` secrets are used. They must retain least privilege.

## Proof scope and remaining decisions

The public verifier owns a separate v1 package compatibility projection. It does not independently authenticate the sidecar as a signed receipt. Instead, the workflow authenticates the private GitHub identity and run and then executes private source-evidence verification, followed by public package projection checks. The sidecar's `sourceIdentityAuthenticated=false` is intentional.

Historical component `revision` strings continue to denote original-owner Git commits; the changed Feedback preview uses the exact immutable monorepo Git commit in its `revision` field, accompanied by explicit `revisionKind` **outside** the public npm artifact. The existing public publisher's original-owner checkouts must never resolve this as a legacy commit.

**Not yet accepted:** actual public component `revisionKind` and versioned published receipt extension, publisher adapter for a new stable version, canonical source owner transfer, real changed product functionality, real Project compatibility/Production, or first npm publication. Historical v1 signed receipts and the current public descriptor remain authoritative.

Tracking: [private source #39](https://github.com/mriekki/project-forge-source/issues/39), [source ownership #357](https://github.com/mriekki/project-forge-platform/issues/357).
