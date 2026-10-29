---
name: release-project-forge
description: Prepare, deliver, publish, and verify an exact @mriekki/project-forge package release from accepted Project Forge component revisions and Platform-owned package changes.
user-invocable: true
disable-model-invocation: true
---

# Release Project Forge

`/release-project-forge` owns the Platform package transport workflow. Canonical private component sources own reusable behavior; public package metadata exposes logical component IDs plus exact opaque revisions, not private repository topology.

Release preparation has two first-class execution modes:

- **Cloud preparation** — a GitHub-connected cloud agent resolves authoritative component `main` revisions and CI, then uses `.github/workflows/prepare-package-release.yml` to materialize exact private sources and prepare a release branch without relying on the Developer's local working copies.
- **Local preparation** — a Developer uses clean canonical local component checkouts and `scripts/prepare-package-update.mjs` directly.

Both modes must produce equivalent package metadata/assets, use the same exact accepted component revisions, pass the same package tests and asset verification, create a normal release PR, and stop at the same merge and npm publication gates. Prefer the mode that is available and least disruptive; local checkout dirtiness must not block cloud preparation.

## 1. Resume from observed state

Inspect current Platform Git/GitHub state, package metadata, component revisions, open release PRs, CI, registry state, live `chatgpt/current.json`, durable release receipts, and available release-preparation mode. Use repository facts rather than memory.

Before declaring that no package release is needed, resolve the exact published Platform source for the current npm version:

1. read the current published version with `npm view @mriekki/project-forge version`;
2. look for the privacy-safe durable receipt at `release/receipts/<version>.json` and validate it with `node scripts/release-receipt.mjs --version <version> --json`;
3. when that receipt is valid, use its exact `platformSource` as the published Platform source and treat its component/CI/publication facts as durable historical release evidence;
4. only for a legacy package version with no durable receipt, inspect successful `npm-publish.yml` runs on `main`, newest first, inspect `package.json` at each run's exact `head_sha`, and use the first run whose package version equals npm latest;
5. require the resulting exact 40-character source SHA and run `node scripts/check-package-release-drift.mjs --baseline <published-source-sha> --json` from clean Platform `main` when a local shell is available, or reproduce the same repository comparison from GitHub facts in cloud mode.

Historical Actions runs are supporting evidence, not the durable release ledger. A valid checked-in receipt remains authoritative historical publication evidence after its referenced workflow runs expire under Actions retention. If a receipt exists but is invalid or conflicts with the registry/package source, fail closed; do not silently fall back to Actions and ignore the conflict.

The drift check compares the current npm payload owned by the Platform (`package.json`, npm-always-included metadata such as README/LICENSE, and every current `package.json#files` entry) against the exact source that was actually published. If the exact published source cannot be resolved or the drift check cannot prove its baseline, fail closed and do not claim that no release is warranted.

If an open/prepared release already advances source package metadata beyond npm latest, resume that release state instead of treating the prepared branch as an unpublished-drift baseline.

Routine releases do not require a local npm login. GitHub Actions uses OIDC. Inspect npm trusted-publisher settings only for initial setup/migration, workflow or repository identity changes, or an OIDC trust failure; a successful exact workflow publish plus its validated durable receipt is sufficient evidence for later routine releases. Do not query `npm trust list` on every routine release.

Private source locations belong only in local checkout configuration and protected source-repository mappings. Never add them to public package metadata, durable release receipts, public baselines, release prose, cloud request bodies, or workflow literals.

## 2. Resolve accepted component revisions

For each logical component in `assets/components.json`, resolve the accepted revision from the canonical source repository's authoritative default branch.

A **changed** component revision must have live green post-merge CI for that exact current `main` revision before release preparation. An **unchanged** component revision that exactly matches the current published package's validated durable receipt may reuse that receipt as historical acceptance evidence when its old Actions run has expired, provided the canonical repository's current `main` still equals that exact revision and the receipt records successful component-main CI plus successful package publication verification. Never use a receipt to bless a different or newer component revision.

In cloud mode, use GitHub repository state directly:

- resolve canonical `main` HEAD;
- require the selected revision to equal that exact `main` HEAD;
- for a changed revision, require configured post-merge CI for that exact revision to have completed successfully before creating the cloud preparation request;
- for an unchanged revision whose historical Actions run has expired, allow the validated current-published release receipt to satisfy the historical CI evidence requirement;
- read canonical version metadata when the component defines one.

The cloud agent's GitHub connection is the live CI-evidence authority for changed private components. The durable receipt is the historical release-evidence authority only for an unchanged revision already proven in the current published package. The cloud executor re-verifies exact source revisions against canonical `origin/main`, but its least-privilege source checkout credential does not need private Actions API access.

In local mode:

- require the corresponding canonical source checkout;
- fetch its default branch and require a clean tracked working tree at exact `origin/main` before release preparation;
- require local HEAD to equal the accepted authoritative revision;
- for a changed revision, verify configured post-merge CI for that exact revision succeeded;
- for an unchanged revision whose old Actions run has expired, allow the validated current-published release receipt to satisfy historical CI evidence;
- read canonical version metadata when the component defines one.

Do not pin an unmerged branch, dirty checkout, guessed revision, or changed revision with failing/pending default-branch CI. A component unchanged since the installed package stays on its existing exact revision.

Treat local checkout validity and release-need detection as separate facts. A dirty or non-`origin/main` local component checkout may block deterministic release preparation in local mode, but it must not erase or downgrade evidence that a release is needed and must not block **cloud** preparation when authoritative GitHub sources are accessible.

## 3. Determine release need and select the package version automatically

Default invocation is `/release-project-forge` with no version argument.

A release is needed when **either** of these is true:

- an accepted component revision/version differs from the current published package; or
- `scripts/check-package-release-drift.mjs` (or an equivalent exact GitHub comparison in cloud mode) reports shipped Platform payload drift from the exact published Platform source.

Never conclude that no release is warranted solely because Core and Deployment revisions are unchanged. Platform-owned CLI, updater, packaged assets, package metadata, or shipped README changes can independently require a package release.

Inspect the complete consumer-visible change set from both sources. Choose the next package version automatically. Do not require the user to choose `patch`, `minor`, or `major` when the classification is clear.

For 1.0.0 and later:

- `patch` — backward-compatible corrections;
- `minor` — backward-compatible features;
- `major` — incompatible consumer contract changes.

Use the highest applicable class across component changes and Platform-owned package changes. Explicit bump or exact-version arguments are optional overrides and must not understate the change. Never reuse an npm version.

A provenance-schema migration that keeps legacy baselines readable while writing privacy-safe v2 baselines is a backward-compatible feature and therefore a minor release.

Only report no release when all evidence agrees:

```text
NO PACKAGE RELEASE NEEDED

npm latest: <version>
Published Platform source: <exact sha>
Platform payload drift: NONE
Core: unchanged
Deployment: unchanged
```

## 4. Prepare the release PR automatically

Invoking `/release-project-forge` authorizes safe release-preparation mechanics in either preparation mode but does **not** authorize npm publication.

### Cloud preparation

Use cloud preparation when the runtime has GitHub access to the Platform and canonical component repositories. Do not require or mutate the Developer's local component checkouts.

Before starting the cloud executor, require:

- exact current Platform `main` SHA;
- exact accepted Core `main` revision and green acceptance evidence under Section 2;
- exact accepted Deployment `main` revision and green acceptance evidence under Section 2;
- exact next package version selected under Section 3.

Do not create or dispatch a cloud preparation request until those checks are complete. Changed component revisions require live green CI; unchanged revisions may use the validated current-published durable receipt only as defined in Section 2. This preflight is performed through the cloud agent's GitHub connection plus repository-owned durable receipt evidence, not through `PROJECT_FORGE_SOURCE_TOKEN`.

The cloud executor is `.github/workflows/prepare-package-release.yml`. It accepts only the exact version/source/revision tuple and independently:

1. requires the Platform checkout to equal current `origin/main` and the authorized source SHA;
2. refuses an already-published version;
3. resolves private source repositories only from protected mappings;
4. checks out canonical Core and Deployment `main` with the protected read-only source credential;
5. requires each checkout to equal both the authorized exact revision and current canonical `origin/main`, with a clean tracked tree;
6. creates a new `release/project-forge-<version>` branch from the exact Platform source;
7. runs `scripts/prepare-package-update.mjs`, exact asset assembly/verification, `npm test`, `git diff --check`, and release-diff scope validation;
8. commits and pushes the prepared release branch;
9. never publishes npm and never changes stable contract pointers.

`PROJECT_FORGE_SOURCE_TOKEN` is a least-privilege private-source checkout credential. Do not require or broaden it merely to read private Actions/CI APIs; live changed-component CI evidence is resolved before request creation by the cloud agent, and durable unchanged-component evidence is repository-owned.

A cloud runtime that can dispatch workflows may invoke `prepare-package-release.yml` directly with `version`, `source_commit`, `core_revision`, and `deployment_revision`.

A cloud runtime that cannot dispatch workflows but can create GitHub issues may open one owner-authored command issue with title:

```text
[project-forge-release] <version>
```

and body containing **only** this public-safe JSON shape:

```json
{
  "version": "<version>",
  "sourceCommit": "<exact-platform-main-sha>",
  "coreRevision": "<exact-core-main-sha>",
  "deploymentRevision": "<exact-deployment-main-sha>"
}
```

The workflow must ignore issue-triggered requests not authored by the repository owner. The request must never contain private repository names, credentials, or other secrets. The cloud agent may create this issue only after the exact private component `main` revisions and their acceptance evidence have been verified under Section 2.

After the cloud workflow pushes the release branch, the cloud agent must create the normal pull request to `main` using its GitHub identity and observe PR CI. The workflow intentionally does not create the PR with `GITHUB_TOKEN`, so the ordinary `pull_request` CI trigger remains authoritative.

### Local preparation

When local preparation is selected:

1. require Platform tracked state clean and refresh `main` fast-forward-only;
2. require clean canonical component checkouts at the exact accepted `origin/main` revisions with acceptance evidence under Section 2;
3. create/switch to `release/project-forge-<version>` unless it already exists safely;
4. run `scripts/prepare-package-update.mjs` with `--version`, `--core-root`, and `--deployment-root` pointing to those canonical source checkouts;
5. run package tests, exact asset assembly/verification, `git diff --check`, and meaningful diff review;
6. commit/push the branch, create the normal release PR, and observe PR CI.

The deterministic preparation script updates only package version metadata, exact component revisions/versions, and packaged descriptors copied from exact accepted source revisions. Component revisions may legitimately remain unchanged for a Platform-only package release.

If local preparation is blocked by dirty/stale component checkouts but cloud preparation is available, switch to cloud preparation rather than asking the Developer to clean unrelated local work. If neither mode can prove exact accepted sources, report:

```text
PACKAGE RELEASE PREPARATION BLOCKED

Proposed version: <version>
Release reason: <Platform payload drift | component revision change | both>
Published Platform source: <exact sha>
Platform payload changes: <files or NONE>
Cloud blocker: <exact blocker or NONE>
Local blocker: <exact blocker or NONE>
```

After successful verification, routine branch/stage/commit/push/PR creation and PR-CI observation are authorized. Do not publish npm from a release branch or PR.

## 5. Package PR merge gate

When PR CI is green and the diff matches the verified release preparation, stop once at:

```text
PACKAGE RELEASE PR READY

Version: <version>
Core: <exact revision/version>
Deployment: <exact revision>
Preparation: CLOUD | LOCAL
PR CI: GREEN
Diff: expected release-preparation files only

1. Merge and finalize package release PR [GITHUB WRITE]
2. Review PR diff [READ ONLY]
3. Leave open [NO ACTION]
```

Merge authorization does not authorize npm publication. After merge, verify exact Platform `main` and post-merge CI.

## 6. Protected source mappings and trusted publishing

Cloud preparation and publication resolve private source repositories only from protected Actions secrets:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

These protected source-repository mappings must contain exact `owner/repository` values. Workflows validate and mask them. They use `PROJECT_FORGE_SOURCE_TOKEN` only for read access to exact private sources. Cloud-preparation live CI evidence is read by the cloud agent through its GitHub connection before the preparation request; source-token Actions API access is not required.

Normal publication uses `.github/workflows/npm-publish.yml` with npm Trusted Publishing (OIDC) and direct `npm publish`. No long-lived npm publish token is used.

If npm trust setup/migration must be inspected, use npmjs.com or locally:

```powershell
npm login --auth-type=web --registry=https://registry.npmjs.org/
npm trust list @mriekki/project-forge --json
```

If the CLI returns `EOTP`, complete npm's browser authorization locally. Never request, paste, or store the one-time URL or OTP.

The required relationship is:

```text
provider: GitHub Actions
repository: mriekki/project-forge-platform
workflow file: npm-publish.yml
allowed action: npm publish
```

If a trust relationship must be created/replaced, require:

```text
[NPM TRUST WRITE]
Replace/configure the @mriekki/project-forge trusted publisher for direct publish from mriekki/project-forge-platform/.github/workflows/npm-publish.yml?
```

Only after approval may trust configuration be changed.

## 7. Exact npm publication gate

Once all are true:

- release PR merged;
- exact Platform `main` is verified;
- post-merge CI is green;
- package version and component revisions are internally consistent;
- target npm version is unused;
- required protected source mappings are configured;
- trusted publisher permits direct publish from `npm-publish.yml`;

present exactly:

```text
NPM PUBLISH READY

Package: @mriekki/project-forge@<version>
Project Forge Platform source: <exact main SHA>
Core: <exact revision/version>
Deployment: <exact revision>
Post-merge CI: GREEN
Publisher: GitHub OIDC / npm-publish.yml

1. Publish this exact package [NPM PUBLISH]
2. Stop [NO ACTION]
```

Selecting option 1 authorizes only that exact package/version/source/revision set.

Trigger:

```powershell
gh workflow run npm-publish.yml --ref main `
  -f version=<version> `
  -f source_commit=<exact-main-sha>
```

Monitor the exact run without another permission prompt. If evidence changes before publication, stop for renewed review.

## 8. Publication workflow contract

`npm-publish.yml` must fail closed before publish unless:

- checked-out Platform commit equals authorized `source_commit`;
- `package.json` equals authorized version;
- `assets/components.json` is privacy-safe schema v2 with exact revisions;
- protected source mappings are present and valid;
- exact component revisions can be checked out;
- `scripts/prepare-release.mjs` passes reproducibility, assembly, tests, and clean-install checks;
- target npm version is not already published.

The workflow publishes the exact tarball with OIDC, verifies registry version/integrity/shasum, runs a neutral-directory `npx` smoke check, and emits signed npm provenance. Do not use `npm stage publish`, `npm stage approve`, or a long-lived npm publish token.

After successful publication verification, capture the exact durable receipt facts needed by Section 9 before historical Actions evidence can become a dependency again: exact Platform source, logical component revisions/versions, release-candidate SHA-256, registry shasum, signed-provenance transparency-log reference, publication verification, and the component/Platform CI acceptance facts used by the release gate.

## 9. Public ChatGPT contract alignment and durable receipt

After successful publication, inspect live `chatgpt/current.json` and compare `generation.package` / `generation.packageVersion` plus the accepted Bootstrap revision/compatibility. Never point stable at an unpublished package.

For every newly published package, require `release/receipts/<version>.json`. Validate it with `node scripts/release-receipt.mjs --version <version> --json`. The receipt is privacy-safe historical evidence, not a mutable current-state pointer. It must contain no private source-repository names or credentials. Workflow/run IDs are historical references only and the receipt must remain useful after those Actions records expire.

If the receipt does not yet exist, create it in the same smallest follow-up PR that aligns the public stable package pointer. If a valid receipt already exists, do not rewrite it. If a receipt exists but conflicts with verified publication facts, stop and resolve the conflict explicitly rather than silently replacing it.

If only mutable package/revision pointers are stale and the immutable operating contract remains valid, prepare the smallest follow-up PR containing the pointer changes, matching contract assertions, and any missing receipt for that newly published version. If the operating contract changed materially, create a new immutable snapshot. Never edit a published immutable snapshot in place.

The stable alignment guard requires a valid durable receipt for the package version selected by `chatgpt/current.json`. The follow-up PR has its normal human merge/finalize gate; npm publication does not authorize merging it.

## 10. Completion

Report evidence-backed state:

```text
PROJECT_FORGE PACKAGE RELEASE COMPLETE

Package: @mriekki/project-forge@<version>
Project Forge Platform source: <sha>
Core: <revision/version>
Deployment: <revision>
Preparation: CLOUD | LOCAL
Publish workflow: GREEN
Registry verification: GREEN
Neutral npx smoke: GREEN
Durable release receipt: VERIFIED
Public ChatGPT contract: ALIGNED | FOLLOW-UP PR REQUIRED
```

Publishing does not update existing consumers; they adopt separately through `/project-forge-update`. Do not regenerate Projects, deploy applications, publish component tags/releases, or update consumers as an implicit release side effect.
