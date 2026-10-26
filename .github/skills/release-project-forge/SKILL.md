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

Inspect current Platform Git/GitHub state, package metadata, component revisions, open release PRs, CI, registry state, live `chatgpt/current.json`, and available release-preparation mode. Use repository facts rather than memory.

Before declaring that no package release is needed, resolve the exact published Platform source for the current npm version:

1. read the current published version with `npm view @mriekki/project-forge version`;
2. inspect successful `npm-publish.yml` runs on `main`, newest first;
3. for each candidate run, inspect `package.json` at the run's exact `head_sha`; the first run whose package version equals the current published npm version is the exact published Platform source;
4. require that exact 40-character source SHA and run `node scripts/check-package-release-drift.mjs --baseline <published-source-sha> --json` from clean Platform `main` when a local shell is available, or reproduce the same repository comparison from GitHub facts in cloud mode.

The drift check compares the current npm payload owned by the Platform (`package.json`, npm-always-included metadata such as README/LICENSE, and every current `package.json#files` entry) against the exact source that was actually published. If the exact published source cannot be resolved or the drift check cannot prove its baseline, fail closed and do not claim that no release is warranted.

If an open/prepared release already advances source package metadata beyond npm latest, resume that release state instead of treating the prepared branch as an unpublished-drift baseline.

Routine releases do not require a local npm login. GitHub Actions uses OIDC. Inspect npm trusted-publisher settings only for initial setup/migration, workflow or repository identity changes, or an OIDC trust failure; a successful exact workflow publish is sufficient evidence for later routine releases. Do not query `npm trust list` on every routine release.

Private source locations belong only in local checkout configuration and protected source-repository mappings. Never add them to public package metadata, public baselines, release prose, cloud request bodies, or workflow literals.

## 2. Resolve accepted component revisions

For each logical component in `assets/components.json`, resolve the accepted revision from the canonical source repository's authoritative default branch and require green post-merge CI for that exact revision.

In cloud mode, use GitHub repository state directly:

- resolve canonical `main` HEAD;
- require the selected revision to equal that exact `main` HEAD;
- require configured post-merge CI for that exact revision to have completed successfully before creating the cloud preparation request;
- read canonical version metadata when the component defines one.

The cloud agent's GitHub connection is the CI-evidence authority for private components. The cloud executor re-verifies the exact source revisions against canonical `origin/main`, but its least-privilege source checkout credential does not need private Actions API access.

In local mode:

- require the corresponding canonical source checkout;
- fetch its default branch and require a clean tracked working tree at exact `origin/main` before release preparation;
- require local HEAD to equal the accepted authoritative revision;
- verify configured post-merge CI for that exact revision succeeded;
- read canonical version metadata when the component defines one.

Do not pin an unmerged branch, dirty checkout, guessed revision, or revision with failing/pending default-branch CI. A component unchanged since the installed package stays on its existing exact revision.

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
- exact accepted Core `main` revision and green CI;
- exact accepted Deployment `main` revision and green CI;
- exact next package version selected under Section 3.

Do not create or dispatch a cloud preparation request until those CI checks are complete and green. This preflight is performed through the cloud agent's GitHub connection, not through `PROJECT_FORGE_SOURCE_TOKEN`.

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

`PROJECT_FORGE_SOURCE_TOKEN` is a least-privilege private-source checkout credential. Do not require or broaden it merely to read private Actions/CI APIs; CI evidence is resolved before request creation by the cloud agent.

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

The workflow must ignore issue-triggered requests not authored by the repository owner. The request must never contain private repository names, credentials, or other secrets. The cloud agent may create this issue only after the exact private component `main` revisions and their green CI have been verified.

After the cloud workflow pushes the release branch, the cloud agent must create the normal pull request to `main` using its GitHub identity and observe PR CI. The workflow intentionally does not create the PR with `GITHUB_TOKEN`, so the ordinary `pull_request` CI trigger remains authoritative.

### Local preparation

When local preparation is selected:

1. require Platform tracked state clean and refresh `main` fast-forward-only;
2. require clean canonical component checkouts at the exact accepted `origin/main` revisions;
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

These protected source-repository mappings must contain exact `owner/repository` values. Workflows validate and mask them. They use `PROJECT_FORGE_SOURCE_TOKEN` only for read access to exact private sources. Cloud-preparation CI evidence is read by the cloud agent through its GitHub connection before the preparation request; source-token Actions API access is not required.

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

The workflow publishes the exact tarball with OIDC, verifies registry version/integrity/shasum, and runs a neutral-directory `npx` smoke check. Do not use `npm stage publish`, `npm stage approve`, or a long-lived npm publish token.

## 9. Public ChatGPT contract alignment

After successful publication, inspect live `chatgpt/current.json` and compare `generation.package` / `generation.packageVersion` plus the accepted Bootstrap revision/compatibility. Never point stable at an unpublished package.

If only mutable package/revision pointers are stale and the immutable operating contract remains valid, prepare the smallest follow-up PR. If the operating contract changed materially, create a new immutable snapshot. Never edit a published immutable snapshot in place.

The follow-up PR has its normal human merge/finalize gate; npm publication does not authorize merging it.

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
Public ChatGPT contract: ALIGNED | FOLLOW-UP PR REQUIRED
```

Publishing does not update existing consumers; they adopt separately through `/project-forge-update`. Do not regenerate Projects, deploy applications, publish component tags/releases, or update consumers as an implicit release side effect.
