---
name: release-project-forge
description: Prepare, deliver, publish, and verify an exact @mriekki/project-forge package release from accepted Project Forge component revisions and Platform-owned package changes.
user-invocable: true
disable-model-invocation: true
---

# Release Project Forge

`/release-project-forge` owns the Platform package transport workflow. Canonical private component sources own reusable behavior; public package metadata exposes logical component IDs plus exact opaque revisions, not private repository topology.

## 1. Resume from observed state

Inspect current Platform Git/GitHub state, package metadata, component revisions, open release PRs, CI, registry state, live `chatgpt/current.json`, and the local canonical component checkouts supplied by the operator environment. Use repository facts rather than memory.

Before declaring that no package release is needed, resolve the exact published Platform source for the current npm version:

1. read the current published version with `npm view @mriekki/project-forge version`;
2. inspect successful `npm-publish.yml` runs on `main`, newest first;
3. for each candidate run, inspect `package.json` at the run's exact `head_sha`; the first run whose package version equals the current published npm version is the exact published Platform source;
4. require that exact 40-character source SHA and run `node scripts/check-package-release-drift.mjs --baseline <published-source-sha> --json` from clean Platform `main`.

The drift check compares the current npm payload owned by the Platform (`package.json`, npm-always-included metadata such as README/LICENSE, and every current `package.json#files` entry) against the exact source that was actually published. If the exact published source cannot be resolved or the drift check cannot prove its baseline, fail closed and do not claim that no release is warranted.

If an open/prepared release already advances source package metadata beyond npm latest, resume that release state instead of treating the prepared branch as an unpublished-drift baseline.

Routine releases do not require a local npm login. GitHub Actions uses OIDC. Inspect npm trusted-publisher settings only for initial setup/migration, workflow or repository identity changes, or an OIDC trust failure; a successful exact workflow publish is sufficient evidence for later routine releases. Do not query `npm trust list` on every routine release.

Private source locations belong only in local checkout configuration and protected source-repository mappings. Never add them to public package metadata, public baselines, release prose, or workflow literals.

## 2. Resolve accepted component revisions

For each logical component in `assets/components.json`:

- require the corresponding canonical source checkout;
- fetch its default branch and require a clean tracked working tree at exact `origin/main` before release preparation;
- verify the selected revision is the accepted merged revision intended for the package;
- verify configured post-merge CI for that exact revision succeeded;
- read canonical version metadata when the component defines one.

Do not pin an unmerged branch, dirty checkout, guessed revision, or revision with failing/pending default-branch CI. A component unchanged since the installed package stays on its existing exact revision.

Treat checkout validity and release-need detection as separate facts. A dirty or non-`origin/main` local component checkout may block deterministic release preparation, but it must not erase or downgrade evidence that a release is needed because the published package payload or an accepted component revision changed.

## 3. Determine release need and select the package version automatically

Default invocation is `/release-project-forge` with no version argument.

A release is needed when **either** of these is true:

- an accepted component revision/version differs from the current published package; or
- `scripts/check-package-release-drift.mjs` reports shipped Platform payload drift from the exact published Platform source.

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

If a release is needed but local canonical component checkouts are dirty, stale, or otherwise invalid for deterministic preparation, report the release need first and stop with an actionable blocker instead of saying no release is warranted:

```text
PACKAGE RELEASE PREPARATION BLOCKED

Proposed version: <version>
Release reason: <Platform payload drift | component revision change | both>
Published Platform source: <exact sha>
Platform payload changes: <files or NONE>
Component checkout blockers: <exact blockers>
```

## 4. Prepare the release PR automatically

Invoking `/release-project-forge` authorizes safe release-preparation mechanics but does **not** authorize npm publication.

When preparation has not happened:

1. require Platform tracked state clean and refresh `main` fast-forward-only;
2. create/switch to `release/project-forge-<version>` unless it already exists safely;
3. run `scripts/prepare-package-update.mjs` with `--version`, `--core-root`, and `--deployment-root` pointing to the operator's canonical source checkouts;
4. run `npm test`, asset assembly/verification, `git diff --check`, and meaningful diff review.

The deterministic preparation script updates only package version metadata, exact component revisions/versions, and packaged descriptors copied from exact accepted source revisions. Component revisions may legitimately remain unchanged for a Platform-only package release.

After successful verification, routine branch/stage/commit/push/PR creation and PR-CI observation are authorized. Do not publish npm from a release branch or PR.

## 5. Package PR merge gate

When PR CI is green and the diff matches the verified release preparation, stop once at:

```text
PACKAGE RELEASE PR READY

Version: <version>
Core: <exact revision/version>
Deployment: <exact revision>
PR CI: GREEN
Diff: expected release-preparation files only

1. Merge and finalize package release PR [GITHUB WRITE]
2. Review PR diff [READ ONLY]
3. Leave open [NO ACTION]
```

Merge authorization does not authorize npm publication. After merge, verify exact Platform `main` and post-merge CI.

## 6. Protected source mappings and trusted publishing

The public publish workflow resolves private source repositories only from protected Actions secrets:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

These protected source-repository mappings must contain exact `owner/repository` values. The workflow validates and masks them. It uses the existing read-only source credential only to fetch exact revisions.

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
Publish workflow: GREEN
Registry verification: GREEN
Neutral npx smoke: GREEN
Public ChatGPT contract: ALIGNED | FOLLOW-UP PR REQUIRED
```

Publishing does not update existing consumers; they adopt separately through `/project-forge-update`. Do not regenerate Projects, deploy applications, publish component tags/releases, or update consumers as an implicit release side effect.
