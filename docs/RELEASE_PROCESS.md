# npm Release Process

`@mriekki/project-forge` is the public npm distribution assembled from exact accepted revisions of private canonical Project Forge component sources.

Release preparation and npm publication are automated, but publication remains an explicit decision for one exact package/version/source tuple. Public package metadata records logical component IDs and opaque exact revisions; private source repository locations remain protected configuration.

## Normal operator workflow

Use the repository-local skill:

```text
/release-project-forge
```

The normal flow is:

```text
accepted component revisions + Platform package drift
→ choose package version
→ CLOUD or LOCAL deterministic preparation
→ release branch
→ release PR + PR CI
→ ONE PACKAGE PR MERGE GATE
→ post-merge main CI
→ ONE EXACT NPM PUBLISH GATE
→ GitHub OIDC direct publish
→ registry + neutral npx verification
→ public ChatGPT contract alignment
```

Publishing the package does not update consumers. Existing package-managed Projects adopt it separately through `/project-forge-update`.

## Two first-class preparation modes

Release preparation supports both cloud and local execution. They are alternative ways to supply the same deterministic scripts with exact accepted component sources; neither changes release semantics or publication authorization.

### Cloud preparation

Cloud preparation is preferred when a GitHub-connected agent can read the Platform and canonical component repositories. It does not require or modify Developer working copies.

The agent resolves:

- exact current Platform `main` SHA;
- exact accepted Core `main` revision and successful post-merge CI;
- exact accepted Deployment `main` revision and successful post-merge CI;
- exact next package version selected from the complete consumer-visible change set.

`.github/workflows/prepare-package-release.yml` then materializes the exact private sources using protected repository mappings and the read-only source credential, runs `scripts/prepare-package-update.mjs`, exact asset assembly/verification, package tests, `git diff --check`, and release-diff scope validation, then pushes `release/project-forge-<version>`.

The workflow may be started by `workflow_dispatch` with the exact version/source/revision tuple. A cloud agent without workflow-dispatch capability may instead create an owner-authored issue titled:

```text
[project-forge-release] <version>
```

whose body contains only:

```json
{
  "version": "<version>",
  "sourceCommit": "<exact-platform-main-sha>",
  "coreRevision": "<exact-core-main-sha>",
  "deploymentRevision": "<exact-deployment-main-sha>"
}
```

The issue-triggered workflow ignores requests not authored by the repository owner. Request bodies must never contain private repository names, credentials, or secrets.

The preparation workflow deliberately pushes the release branch but does not create the pull request with `GITHUB_TOKEN`. The cloud agent creates the normal PR afterward using its GitHub identity so ordinary `pull_request` CI remains authoritative.

### Local preparation

Local preparation remains fully supported for a Developer working from canonical source checkouts. The Platform checkout must be clean and refreshed from `main`; Core and Deployment checkouts must be clean exact accepted `origin/main` revisions with green post-merge CI.

The local path creates `release/project-forge-<version>` and runs:

```text
scripts/prepare-package-update.mjs
→ exact asset assembly/verification
→ npm test
→ git diff --check
→ meaningful diff review
→ commit/push
→ normal release PR
```

Dirty or stale local component checkouts block only local preparation. If authoritative GitHub sources are available, the release skill may switch to cloud preparation rather than requiring the Developer to disturb unrelated local work.

## Release invariants

Before npm publication:

- Project Forge Platform publication source is an exact clean `main` commit;
- `assets/components.json` uses schema v2 and pins exact opaque component revisions;
- accepted component revisions equal authoritative canonical `main` and have green post-merge CI;
- local canonical component checkouts are clean exact accepted `origin/main` states when local preparation is used;
- cloud preparation materializes exact accepted canonical `main` sources when cloud preparation is used;
- packaged distribution descriptors exactly match the pinned source descriptors;
- all package tests pass;
- generated assets verify against the assembly ledger;
- two independent `npm pack` runs produce the same SHA-256;
- a clean temporary install can run `project-forge version`, `project-forge install`, and `project-forge check` successfully;
- the npm version does not already exist;
- the exact Platform source commit and package version are revalidated by the publication workflow.

`scripts/prepare-release.mjs` enforces release-candidate checks and writes ignored release artifacts under `dist/release/` and ignored generated package assets under `assets/generated/`.

## Privacy-safe component provenance

`assets/components.json` schema v2 contains only:

- logical component IDs such as `core` and `deployment`;
- exact opaque `revision` values;
- public compatibility/version and distribution metadata;
- packaged descriptor/source-root paths.

It must not publish private source repository identities. New consumer baselines use schema v2 with the same logical-ID + opaque-revision model. Package runtime remains backward-compatible with schema v1 baselines so an existing Project can upgrade in place; the next successful apply rewrites its package provenance as schema v2 without changing clean managed files solely for the migration.

## Deterministic package-update preparation

Both preparation modes ultimately run `scripts/prepare-package-update.mjs` against exact canonical source checkouts. The script refuses Platform `main`, requires clean exact component `origin/main` checkouts, validates canonical descriptors, and updates only:

- `package.json` version;
- `package-lock.json` version metadata;
- `assets/components.json` package version and exact component revisions/versions;
- packaged component distribution descriptors copied from those exact source checkouts.

Asset assembly then rebuilds `assets/generated/` from exact pinned Git blobs. Private source repository names are not encoded in package metadata or required as public command arguments.

## Package version policy

For `1.0.0` and later, use conventional semantic versioning:

- patch — backward-compatible corrections;
- minor — backward-compatible consumer-visible features;
- major — breaking consumer contracts.

Release need is the union of accepted component changes and Platform-owned npm payload drift. Unchanged component revisions are not evidence that no release is needed when shipped Platform files changed.

## Protected source-repository mappings

Cloud preparation and publication resolve private source locations only from protected Actions secrets on Project Forge Platform:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

Values are exact `owner/repository` mappings. Do not print them, commit them, place them in public package metadata, or include them in cloud release request issues. Workflows validate their shape, mask resolved values in logs, and use `PROJECT_FORGE_SOURCE_TOKEN` only for read access to exact private sources needed by the release.

## Trusted Publishing

Normal releases use npm Trusted Publishing (OIDC) from:

```text
GitHub owner: mriekki
Repository: project-forge-platform
Workflow: npm-publish.yml
Allowed action: npm publish
```

Routine releases do not require local npm login. Inspect or change npm trust only during initial setup, migration, repository/workflow identity changes, or a reported trust error.

For one-time trust administration, use npmjs.com or, when needed:

```powershell
npm login --auth-type=web --registry=https://registry.npmjs.org/
npm trust list @mriekki/project-forge --json
```

If npm returns `EOTP`, complete the browser authorization locally. Never paste or store its one-time URL or OTP in chat, repository files, or CI.

## Exact release gates

A green release PR stops at one package merge gate. Merging does not authorize publication.

After the merged exact Platform `main` commit passes post-merge CI and the target npm version is confirmed unused, stop at one exact npm publication gate naming:

- package/version;
- Platform main SHA;
- exact logical component revisions (and Core version where applicable);
- green post-merge CI;
- GitHub OIDC / `npm-publish.yml` publisher.

If approved, trigger:

```powershell
gh workflow run npm-publish.yml --ref main `
  -f version=<version> `
  -f source_commit=<exact-main-sha>
```

The workflow refuses stale or changed evidence.

## Publication workflow behavior

`.github/workflows/npm-publish.yml`:

1. checks out exact Project Forge Platform source;
2. verifies the authorized Platform SHA and package version;
3. refuses an already-published version;
4. resolves exact component revisions from schema-v2 `assets/components.json`;
5. resolves private component source locations from protected source-repository mappings and masks them;
6. checks out each exact component revision with read-only source credentials;
7. runs `scripts/prepare-release.mjs` and verifies the release manifest;
8. publishes the exact tarball with OIDC;
9. verifies registry version/integrity/shasum with bounded retry;
10. runs a neutral-directory `npx` smoke check.

If a pre-publication step fails, npm is not published. If publication succeeds but post-publish verification fails, report the published state accurately and never republish the same version.

## Public ChatGPT contract alignment

After registry verification, compare live `chatgpt/current.json` with the exact published package. Never point stable to an unpublished version. If only the mutable package/revision pointer is stale and the immutable operating contract is unchanged, prepare the smallest follow-up PR; otherwise create a new immutable snapshot as required by the live contract rules.

## What release does not imply

Preparing or publishing `@mriekki/project-forge` does not regenerate existing Projects, update consumers, deploy an application, publish component GitHub releases/tags, or perform Production changes. Those remain separately authorized actions.
