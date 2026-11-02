---
name: release-project-forge
description: Prepare, deliver, publish, recover verification for, and verify an exact @mriekki/project-forge package release from accepted Project Forge component revisions and Platform-owned package changes.
user-invocable: true
disable-model-invocation: true
---

# Release Project Forge

`/release-project-forge` owns the Platform package transport workflow. Canonical component sources own reusable behavior; the public package exposes logical component IDs plus exact opaque revisions without publishing private repository topology.

Release preparation has two first-class execution modes:

- **Cloud preparation** — a GitHub-connected cloud agent resolves authoritative component `main` revisions and CI, then uses `.github/workflows/prepare-package-release.yml` to materialize exact protected sources and prepare a release branch without relying on the Developer's local working copies.
- **Local preparation** — a Developer uses clean canonical local component checkouts and `scripts/prepare-package-update.mjs` directly.

Both modes must produce equivalent package metadata/assets, use the same exact accepted component revisions, pass the same package tests and asset verification, and create a normal release PR. Prefer the mode that is available and least disruptive; local checkout dirtiness must not block cloud preparation.

## Authorization modes

Project Forge supports two release-authorization modes.

**End-to-end release authorization** is the normal mode when the Developer authorizes the full release lifecycle, including when a normal Project Forge bug/enhancement/change request is already covered by the public default full-lifecycle contract. That single bounded approval authorizes routine mechanics for the same reviewed release scope through preparation, exact PR merge after green CI, publication, verification, receipt/stable alignment, exact alignment merge after green CI, and final verification.

Do not ask for repeated ceremonial confirmations inside an active end-to-end authorization. The authorization remains valid only while the reviewed scope and evidence remain materially unchanged. Stop for renewed review when the release class/version, component revision, package diff, source relationship, publication identity, trust root, or expected alignment scope changes unexpectedly.

**Granular authorization** remains available when the Developer explicitly narrows the request to preparation, merge, publication, or another bounded stage. Do not infer broader permission in that case.

A bare `/release-project-forge` invocation authorizes safe release-preparation mechanics but not npm publication unless the surrounding user instruction or the normal Project Forge full-lifecycle default already supplies publication authorization.

## 1. Resume from observed state

Inspect current Platform Git/GitHub state, package metadata, component revisions, open release PRs, CI, registry state, live `chatgpt/current.json`, durable receipts, and any in-flight or failed publication run. Repository facts outrank memory.

Before declaring that no release is needed, resolve the exact published Platform source for npm latest:

1. read `npm view @mriekki/project-forge version`;
2. validate `release/receipts/<version>.json` with `node scripts/release-receipt.mjs --version <version> --json` when present;
3. prefer a valid durable receipt's exact `platformSource` over historical Actions retention;
4. only for a legacy version without a receipt, resolve the exact successful historical publication source from workflow evidence;
5. run `node scripts/check-package-release-drift.mjs --baseline <published-source-sha> --json`, or reproduce the same exact comparison through GitHub facts.

Historical Actions runs are supporting evidence, not the durable release ledger. If a receipt exists but conflicts with registry/package evidence, fail closed rather than silently ignoring it.

Routine releases do not require a local npm login. GitHub Actions uses OIDC. Inspect npm trusted-publisher settings only for initial setup/migration, workflow/repository identity changes, or an OIDC trust failure. Do not query `npm trust list` on every routine release.

Private source locations belong only in protected source-repository mappings and local checkout configuration. Never put private repository names, credentials, or other secrets into public package metadata, receipts, issue request bodies, or release prose.

## 2. Resolve accepted component revisions

For each logical component in `assets/components.json`, resolve the accepted revision from the canonical source repository's authoritative default branch.

A changed component revision must have live green post-merge CI for that exact current `main` revision before release preparation. An unchanged component revision that exactly matches the current published package may use its validated durable receipt as historical acceptance evidence when the old Actions run has expired, provided canonical current `main` still equals that exact revision.

In cloud mode, the cloud agent's GitHub connection is the live CI-evidence authority for changed private components. `PROJECT_FORGE_SOURCE_TOKEN` is only a least-privilege private-source checkout credential and does not need private Actions API access.

In local mode, require clean canonical component checkouts at exact accepted `origin/main` revisions. Dirty or stale local component checkouts block only local preparation; they must not block cloud preparation when authoritative GitHub sources are accessible.

Never pin an unmerged branch, dirty checkout, guessed revision, or changed component revision with failing/pending default-branch CI.

## 3. Determine release need and version

Default invocation is `/release-project-forge` with no version argument.

A release is needed when either an accepted component revision/version differs from the current published package or `scripts/check-package-release-drift.mjs` reports shipped Platform payload drift from the exact published Platform source.

Choose the next package version automatically. Do not require the user to choose `patch`, `minor`, or `major` when the classification is clear. Explicit bump or exact-version arguments are optional overrides and must not understate the change. Never reuse an npm version.

For 1.0.0 and later:

- `patch` — backward-compatible corrections;
- `minor` — backward-compatible features;
- `major` — incompatible consumer contract changes.

Use the highest applicable class across component and Platform-owned changes. Only report `NO PACKAGE RELEASE NEEDED` when exact published-source comparison and component revisions all agree.

## 4. Prepare the release PR

Use the active authorization mode. Preparation never publishes npm.

### Cloud preparation

Use `.github/workflows/prepare-package-release.yml` when GitHub/cloud access is available. Before starting it, require exact current Platform `main`, exact accepted Core/Deployment revisions, and their acceptance evidence. Changed component revisions require live green CI; unchanged revisions may use the validated current-published durable receipt only under Section 2.

The workflow independently verifies the exact tuple, resolves private repositories only from protected mappings, materializes exact sources, runs `scripts/prepare-package-update.mjs`, asset assembly/verification, package tests, `git diff --check`, release-diff scope checks, and pushes `release/project-forge-<version>`. It does not publish npm or create the PR.

When direct workflow dispatch is unavailable, the cloud agent may create the owner-authored issue:

```text
[project-forge-release] <version>
```

with only:

```json
{
  "version": "<version>",
  "sourceCommit": "<exact-platform-main-sha>",
  "coreRevision": "<exact-core-main-sha>",
  "deploymentRevision": "<exact-deployment-main-sha>"
}
```

After the cloud workflow pushes the branch, create the normal PR and observe ordinary PR CI.

### Local preparation

When local preparation is selected:

1. require clean Platform and component tracked state at exact accepted revisions;
2. create/switch to `release/project-forge-<version>`;
3. run `scripts/prepare-package-update.mjs --version <version> --core-root <core> --deployment-root <deployment>`;
4. run package tests, asset verification, `git diff --check`, and meaningful diff review;
5. commit/push, create the normal release PR, and observe PR CI.

If local preparation is blocked by unrelated dirtiness but cloud preparation is available, use cloud preparation rather than asking the Developer to disturb unrelated work.

## 5. Package PR merge

When PR CI is green and the diff matches verified preparation:

- with active end-to-end authorization, re-read the PR head/mergeability, require the exact reviewed head, merge normally, and verify exact post-merge Platform `main` CI without another prompt;
- with granular authorization, stop at the explicit package-release PR merge gate.

Merge authorization alone does not imply npm publication in granular mode.

## 6. Protected sources and trusted publishing

Cloud preparation and publication resolve private source repositories only from protected Actions secrets:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

Normal publication uses `mriekki/project-forge-platform/.github/workflows/npm-publish.yml` with npm Trusted Publishing (OIDC) and direct `npm publish`; no long-lived npm publish token or duplicate GitHub Environment reviewer is required.

For trust inspection/setup only:

```powershell
npm login --auth-type=web --registry=https://registry.npmjs.org/
npm trust list @mriekki/project-forge --json
```

If npm returns `EOTP`, complete browser authorization locally. Never request or store the one-time URL/OTP.

Changing the trusted publisher is a separate trust-root action and requires:

```text
[NPM TRUST WRITE]
Replace/configure the @mriekki/project-forge trusted publisher for direct publish from mriekki/project-forge-platform/.github/workflows/npm-publish.yml?
```

End-to-end release authorization does not silently authorize changing this trust root.

## 7. Exact npm publication trigger

Once the release PR is merged, exact `main` and post-merge CI are green, metadata/component pins are internally consistent, the target version is unused, protected mappings exist, and the trusted publisher is valid:

- under active end-to-end authorization, create the owner-authored publication request and monitor it automatically;
- under granular authorization, present `NPM PUBLISH READY` with the exact version/source/component tuple and require `[NPM PUBLISH]` authorization.

Preferred cloud trigger:

```text
[project-forge-publish] <version>
```

with only:

```json
{
  "version": "<version>",
  "sourceCommit": "<exact-current-platform-main-sha>"
}
```

`workflow_dispatch` remains an administrative fallback:

```powershell
gh workflow run npm-publish.yml --ref main `
  -f version=<version> `
  -f source_commit=<exact-main-sha>
```

The workflow independently verifies the exact source and exact post-merge CI before publishing.

## 8. Publication and verification contract

For normal publish mode, `npm-publish.yml` fails closed unless the request is exact and owner-authorized (or exact `workflow_dispatch`), source equals current `main`, exact source CI is green, package/component metadata is valid, protected sources resolve, exact component revisions materialize, reproducible preparation passes, and the npm version is unused.

The workflow publishes the exact tarball with OIDC, verifies registry version/integrity/shasum, verifies signed npm provenance, and runs a neutral-directory `npx` smoke. Registry propagation and the neutral npm install are separate propagation surfaces: the neutral smoke must retry with bounded backoff and a fresh npm cache until the exact version becomes installable or the verification timeout expires.

For issue-triggered success, persist machine-readable publication evidence as an issue comment and close the issue only after all verification succeeds.

### Post-publication verification recovery

A failed verification after `npm publish` has succeeded is not permission to publish again. **Never republish the same npm version.** First prove whether npm accepted the version and whether registry identity matches the rebuilt exact release candidate.

When the version already exists and publication failed only after publish (for example, neutral-install propagation lag), recover through the owner-authored request:

```text
[project-forge-publish-verify] <version>
```

with exactly:

```json
{
  "version": "<version>",
  "sourceCommit": "<original-published-platform-source-sha>",
  "publicationRunId": <original-publish-workflow-run-id>,
  "provenanceUrl": "https://search.sigstore.dev/?logIndex=<original-log-index>"
}
```

Recovery must fail closed unless:

- the exact version is already published;
- the original source commit is still an ancestor of current Platform `main`;
- `scripts/check-package-release-drift.mjs --baseline <sourceCommit> --json` proves **no shipped package payload drift** since that source;
- the original exact source has successful post-merge Platform CI;
- current package/component metadata still describes that same version and component tuple;
- a reproducibly rebuilt candidate has registry integrity/shasum identical to the already-published package;
- the supplied provenance URL is the exact signed-provenance URL observed from the original successful publish step; and
- the neutral `npx` verification succeeds through the same bounded retry policy.

Recovery skips `npm publish` entirely and records publication evidence using the **original** publication workflow run ID/source/provenance, not the recovery run as if it had published the package. If shipped payload drift exists after the original source, stop and resolve the release state explicitly rather than verifying from a changed candidate.

Do not use `npm stage publish`, `npm stage approve`, or a long-lived npm publish token.

## 9. Public ChatGPT contract alignment and durable receipt

After successful publication, inspect live `chatgpt/current.json` and compare `generation.package` / `generation.packageVersion` plus the accepted Bootstrap revision/compatibility. Never point stable at an unpublished package.

For every newly published package, require `release/receipts/<version>.json` and validate it with `node scripts/release-receipt.mjs --version <version> --json`. The receipt is privacy-safe historical evidence and must contain no private repository identities or credentials.

If the receipt is missing, create it in the smallest alignment PR that advances the stable package/revision pointers. If a receipt exists but conflicts with verified publication facts, stop and resolve the conflict explicitly.

If only mutable package/revision pointers are stale and the immutable operating contract remains valid, update the pointers/assertions and missing receipt only. If operating behavior changed materially, create a new immutable contract snapshot. Never edit a published immutable snapshot in place.

The stable alignment guard requires a valid receipt for the package selected by `chatgpt/current.json`.

- with active end-to-end authorization, create the smallest alignment PR, verify its exact diff/required CI, then merge the unchanged reviewed head automatically and verify post-merge CI plus `Public ChatGPT Contract Alignment`;
- with granular authorization, the follow-up PR has its normal human merge/finalize gate and publication alone does not authorize merging it.

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
Public ChatGPT contract: ALIGNED
```

Publishing does not update existing consumers; they adopt separately through `/project-forge-update`. Do not regenerate Projects, deploy applications, publish component tags/releases, or update consumers as an implicit release side effect.
