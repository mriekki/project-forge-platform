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
→ registry + neutral npx + provenance verification
→ durable release receipt
→ public ChatGPT contract alignment
```

Publishing the package does not update consumers. Existing package-managed Projects adopt it separately through `/project-forge-update`.

## Durable published-source resolution

For a current published package version, Project Forge resolves historical publication evidence from the checked-in privacy-safe receipt at:

```text
release/receipts/<exact-semver>.json
```

Validate it with:

```text
node scripts/release-receipt.mjs --version <exact-semver> --json
```

A valid receipt supplies the exact published Platform source and historical release evidence without requiring its GitHub Actions runs to remain retained. Historical workflow/run IDs may be recorded for traceability, but they are references only. For a legacy package version that predates durable receipts, successful historical `npm-publish.yml` runs remain the fallback method for resolving the exact published Platform source.

If a receipt exists but is invalid or conflicts with registry/source facts, fail closed. Do not silently ignore it and reconstruct a different history from Actions.

## Two first-class preparation modes

Release preparation supports both cloud and local execution. They are alternative ways to supply the same deterministic scripts with exact accepted component sources; neither changes release semantics or publication authorization.

### Cloud preparation

Cloud preparation is preferred when a GitHub-connected agent can read the Platform and canonical component repositories. It does not require or modify Developer working copies.

The cloud agent resolves and verifies before creating the preparation request:

- exact current Platform `main` SHA;
- exact accepted Core `main` revision and acceptance evidence;
- exact accepted Deployment `main` revision and acceptance evidence;
- exact next package version selected from the complete consumer-visible change set.

A changed component revision requires successful live post-merge CI for that exact current `main` revision. An unchanged component revision that exactly matches the current published package may reuse its validated durable receipt as historical acceptance evidence if the older Actions run has expired, provided canonical `main` still equals that exact revision. A receipt never authorizes a different or newer component revision.

The cloud agent's GitHub connection is the live CI authority for changed private components. The durable receipt is historical evidence only for an unchanged revision already proven by the current published package. `.github/workflows/prepare-package-release.yml` then independently materializes the exact private `main` sources using protected repository mappings and the least-privilege read-only source credential, requires each checkout to match the requested SHA and current `origin/main`, and runs `scripts/prepare-package-update.mjs`, exact asset assembly/verification, package tests, `git diff --check`, and release-diff scope validation before pushing `release/project-forge-<version>`.

The source checkout credential does not need private Actions API access. Do not broaden it merely to repeat CI lookups already completed by the cloud agent or to compensate for expired historical Actions runs covered by a valid receipt.

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

The issue-triggered workflow ignores requests not authored by the repository owner. Request bodies must never contain private repository names, credentials, or secrets. The cloud agent creates the request only after exact component `main` revisions and their required acceptance evidence are verified.

The preparation workflow deliberately pushes the release branch but does not create the pull request with `GITHUB_TOKEN`. The cloud agent creates the normal PR afterward using its GitHub identity so ordinary `pull_request` CI remains authoritative.

### Local preparation

Local preparation remains fully supported for a Developer working from canonical source checkouts. The Platform checkout must be clean and refreshed from `main`; Core and Deployment checkouts must be clean exact accepted `origin/main` revisions with acceptance evidence under the same changed-versus-unchanged rule above.

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
- accepted component revisions equal authoritative canonical `main`;
- changed component revisions have live green post-merge CI;
- unchanged component revisions have either live green CI or valid historical acceptance evidence in the current published package receipt;
- local canonical component checkouts are clean exact accepted `origin/main` states when local preparation is used;
- cloud preparation materializes exact accepted canonical `main` sources after the cloud agent has verified the required acceptance evidence;
- packaged distribution descriptors exactly match the pinned source descriptors;
- all package tests pass;
- generated assets verify against the assembly ledger;
- two independent `npm pack` runs produce the same SHA-256;
- a clean temporary install can run `project-forge version`, `project-forge install`, and `project-forge check` successfully;
- the npm version does not already exist;
- the exact Platform source commit and package version are revalidated by the publication workflow.

`scripts/prepare-release.mjs` enforces release-candidate checks and writes ignored release artifacts under `dist/release/` and ignored generated package assets under `assets/generated/`.

After successful publication verification, a durable receipt is required before the new package becomes the stable public ChatGPT package pointer.

## Durable release receipts

Release receipts are append-only historical publication evidence stored under `release/receipts/`. Each receipt is named for one exact published semantic version and records only privacy-safe facts:

- exact package name/version and Platform publication source;
- logical Core/Deployment revisions and public compatibility/version metadata where applicable;
- release-candidate SHA-256 and npm registry shasum;
- publication timestamp and GitHub OIDC publisher identity;
- registry identity verification, neutral-directory `npx` smoke verification, and signed-provenance transparency-log reference;
- the successful component-main and Platform-main CI evidence used by that release.

Receipts do **not** replace mutable current-state authorities. Current package/component selection remains owned by `package.json`, `assets/components.json`, and `chatgpt/current.json`. Receipts must not contain private source-repository names, credentials, secrets, consumer data, environment bindings, or deployment state.

Workflow/run IDs in receipts are traceability references only. The durable facts remain usable after those Actions records expire under retention. Existing valid receipts are not silently rewritten in normal operation; a conflict is a release-evidence defect that must be resolved explicitly.

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

The exact published Platform baseline should be taken from the validated receipt for npm latest when one exists. Historical Actions runs are only the legacy fallback for versions without receipts.

## Protected source-repository mappings

Cloud preparation and publication resolve private source locations only from protected Actions secrets on Project Forge Platform:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

Values are exact `owner/repository` mappings. Do not print them, commit them, place them in public package metadata or durable receipts, or include them in cloud release request issues. Workflows validate their shape, mask resolved values in logs, and use `PROJECT_FORGE_SOURCE_TOKEN` only for read access to exact private sources needed by the release. The source token does not need private Actions API access; live changed-component CI evidence is resolved through the cloud agent's GitHub connection before the request is created.

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
8. publishes the exact tarball with OIDC and signed provenance;
9. verifies registry version/integrity/shasum with bounded retry;
10. runs a neutral-directory `npx` smoke check.

If a pre-publication step fails, npm is not published. If publication succeeds but post-publish verification fails, report the published state accurately and never republish the same version.

After successful verification, capture the receipt facts before aligning the stable public package pointer. The receipt is the durable repository-owned evidence; the workflow run remains useful operational detail while retained, but future release decisions must not depend on its indefinite availability.

## Public ChatGPT contract alignment

After registry verification, compare live `chatgpt/current.json` with the exact published package. Never point stable to an unpublished version.

For every newly published package, require and validate `release/receipts/<version>.json`. If the receipt is missing, add it in the same smallest follow-up PR that advances the stable package pointer. If only the mutable package/revision pointer is stale and the immutable operating contract is unchanged, that PR contains the pointer change, its matching assertion, and any missing receipt; otherwise create a new immutable snapshot as required by the live contract rules.

The stable alignment guard requires a valid receipt for the package version selected by `chatgpt/current.json`. A receipt that already exists and validates is not rewritten merely because historical Actions records later expire.

## Actions retention boundary

GitHub Actions remains the live execution and CI system. Durable receipts intentionally remove the release process's dependency on indefinite retention of historical successful runs. This makes shorter Actions retention operationally safe for historical release evidence, while changed component revisions and new Platform changes still require current live CI before acceptance.

Repository retention settings are administrative configuration and are not changed by this release process or by adding a receipt. They should be changed separately only after the receipt guardrails are merged and verified.

## What release does not imply

Preparing or publishing `@mriekki/project-forge` does not regenerate existing Projects, update consumers, deploy an application, publish component GitHub releases/tags, or perform Production changes. Those remain separately authorized actions.
