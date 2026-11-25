---
name: project-forge-update
description: Guided whole-profile update for package-managed Project Forge consumers using the exact published @mriekki/project-forge artifact while preserving Core, Deployment, umbrella, and generated-consumer provenance integrity.
argument-hint: "[optional exact package version]"
user-invocable: true
disable-model-invocation: true
---

# Project Forge Update

`/project-forge-update` is the normal update workflow for consumers that contain `PROJECT_FORGE_BASELINE.json` and were installed/generated from the public Project Forge package.

The governing rule is:

```text
package-managed consumer
→ update the whole Project Forge profile through the published package
→ keep PROJECT_FORGE_BASELINE.json + component baselines coherent
→ when the consumer is Bootstrap-generated, keep approved generation metadata and generated package-verification surfaces coherent too
```

Do not replace this with direct Core-only or Deployment-Kit-only synchronization when `PROJECT_FORGE_BASELINE.json` is present.

Invocation starts read-only. One explicit update choice may authorize safe branch setup plus the exact package apply, generated-consumer companion metadata updates when applicable, and verification. `/deliver`, merge, release publication, and production deployment remain separate.

## 1. Establish package-managed provenance

From the consumer root read:

- `PROJECT_FORGE_BASELINE.json`;
- `CORE_BASELINE.json` when present;
- `DEPLOYMENT_BASELINE.json` when present;
- `PROJECT_BOOTSTRAP.json` when present;
- current Git status, branch, remotes, and default branch when observable.

Require `PROJECT_FORGE_BASELINE.json` to identify:

- package name;
- installed package version;
- profile;
- recorded Core component commit/version/distribution;
- recorded Deployment component commit/distribution when that component is present.

If `PROJECT_FORGE_BASELINE.json` is absent, report `NOT A PACKAGE-MANAGED PROJECT FORGE CONSUMER` and stop. A Core-only consumer may use `/core-sync`; another component-only consumer must use that component's canonical component update path.

Do not synthesize or repair missing umbrella provenance by hand.

### Bootstrap-generated consumers

If `PROJECT_BOOTSTRAP.json` exists, treat it as approved generated-consumer provenance, not unrelated product data.

Before planning an update, require `generation["project-forge"].package`, `generation["project-forge"].version`, and `generation["project-forge"].profile` to agree exactly with the installed `PROJECT_FORGE_BASELINE.json`. Require `generation["project-forge"].integrity` to be a non-empty exact registry integrity value for that installed package/version. Verify that integrity read-only from the registry when registry access is available.

If those values disagree before the update, report `GENERATED PROJECT FORGE METADATA DRIFT` and stop. Do not use `/project-forge-update` to silently reconcile an already-incoherent generated consumer.

Also inspect generated package-verification surfaces such as `.github/workflows/ci.yml` when present. If they duplicate the approved package version/integrity literally, record that current shape as companion generated metadata that must remain coherent with `PROJECT_BOOTSTRAP.json` during the update. Do not rewrite locally customized or unrecognized generated surfaces by guesswork.

## 2. Verify the installed package baseline first

Before planning an update, verify that the current managed state still matches the exact installed package version recorded in `PROJECT_FORGE_BASELINE.json`.

For the standard package this is equivalent to:

```text
npx --yes @mriekki/project-forge@<installed-version> check
```

Use the package identity recorded by the baseline rather than silently substituting another package.

If the exact installed package cannot be obtained, or `check` reports stale/drifted Core, Deployment, or umbrella metadata, stop. Do not use an update as a way to overwrite unexplained managed drift.

Also inspect Git state. Preserve unrelated consumer work; never auto-stash, reset, clean, rebase, force-update, or discard it.

## 3. Resolve one exact target package

Resolve the supported stable package from the public Project Forge bootstrap
descriptor, not the registry's publication channel:

```text
https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json
```

Pin the public Platform default-branch commit used to retrieve the descriptor
and its matching release receipt. Require the supported descriptor schema,
channel `stable`, the exact `generation.package` matching the installed package,
and an exact `generation.packageVersion`. Resolve and verify the immutable
contract documents referenced by that descriptor as required by the Project
Forge bootstrap contract. If these authorities cannot be verified, report
`STABLE PACKAGE EVIDENCE UNAVAILABLE` and stop before target preview or apply.

If the human supplied an exact version, it must equal this verified stable
version for the normal Builder update. An explicitly requested different
version is not implicitly supported merely because it exists in npm; report
`REQUESTED PACKAGE IS NOT CURRENT STABLE` and stop. Candidate qualification
or separately authorized historical-version recovery belongs to a separate
reviewed maintainer/recovery workflow, not this ordinary update. Do not
silently replace a supplied version with another.

Publication and stable support are distinct: npm's `latest` may advance before
the stable descriptor. Do not select the target from npm latest, even if that
version is newer than the installed package.

At the pinned public Platform commit, obtain
`release/receipts/<target-version>.json` and validate it with the existing
public Platform receipt validator (`scripts/release-receipt.mjs --version <target-version> --json`)
from a trusted checkout of that exact commit. No private Platform implementation
repository or additional credentials are needed. A missing, unsupported or
conflicting receipt blocks the ordinary update. The validated receipt records
historical publication evidence; its signed-provenance flag is not itself an
independent cryptographic signature verification.

Query the exact registry version without executing the target package:

```text
npm view @mriekki/project-forge@<target-version> version --json
npm view @mriekki/project-forge@<target-version> dist.integrity --json
npm view @mriekki/project-forge@<target-version> dist.shasum --json
```

Require the exact version, nonempty integrity and registry shasum matching the
validated receipt. Capture the full exact `dist.integrity` for the reviewed
generated-consumer companion metadata. If registry or receipt evidence
conflicts or is unavailable, stop. Do not represent structural receipt
validation or registry hash agreement as independent signed-provenance
verification. Preserve the same pinned package identity, version, integrity
and receipt throughout preview, apply and final check; recheck the stable
selection and exact registry identity before apply and stop on material change.

Do not use a moving `@latest` reference for the modifying apply after preview.
Use the same exact package version for preview, apply, and final check.

If the resolved version equals the installed version and the exact-version check passes, report `PROJECT FORGE ALREADY CURRENT` and stop without creating a branch or commit.

If the resolved target is semantically older than the installed package, report `PROJECT FORGE DOWNGRADE REQUESTED` and stop. Normal `/project-forge-update` does not authorize a downgrade or rollback; that requires a separate explicit recovery/rollback decision with repository-specific evidence.

## 4. Preview the whole-profile update

Run the target package's update command without `--apply` and inspect the complete plan. For the standard package:

```text
npx --yes @mriekki/project-forge@<target-version> update
```

Do not approve the package's interactive apply prompt during preview. When needed, invoke preview in the environment's non-interactive/read-only form so the printed plan is observed without applying it.

The preview must cover every component in the installed profile together. A managed conflict/drift in any component blocks the whole update.

Stop on unsafe states such as:

- `LOCAL_DRIFT`;
- `CONFLICT`;
- `LOCAL_MISSING`;
- `UNTRACKED_CONFLICT`;
- path collisions/conflicts;
- Core `RETIRED_DRIFT` when the retired file no longer matches its recorded managed hash.

A package-managed retired path that is unchanged from its recorded baseline may be classified as `REMOVE` and deleted safely; an already-missing retired path may be classified as `RETIRED_MISSING`. These states do not require a separate ownership decision because the baseline proves there is no consumer edit to preserve.

A modified retired Core path is different: never auto-add `--accept-retired core:<path>` merely to make the update pass. Explain that the file differs from its recorded Core-managed hash and require a separate explicit ownership-transfer decision before re-previewing it. When that exact transfer is accepted, the package updater preserves the file as consumer-owned content and drops it from the new Core baseline.

For a Bootstrap-generated consumer, also preview the companion generated-consumer changes:

- `PROJECT_BOOTSTRAP.json` keeps the same package/profile but changes `generation["project-forge"].version` and `generation["project-forge"].integrity` to the exact reviewed target;
- generated package-verification surfaces should consume `PROJECT_BOOTSTRAP.json` dynamically when the accepted Bootstrap contract supports that form;
- a recognized older Bootstrap-generated verification block may be migrated only when its embedded old package/version/integrity exactly match the currently approved manifest metadata;
- an unrecognized or locally modified generated verification surface is a stop condition, not permission to reconstruct Bootstrap output by hand.

### Optional Auth Kit passkey capability and upgrade checks

For an Auth-enabled consumer, compare both installed and target **exact**
package authentication profiles before applying changes:

- A packaged `docs/PASSKEY_SUPPORT.json` marker in `candidate` state, or
  source files without that marker, does **not** mean passkeys can be enabled.
  Qualified support additionally requires the verified exact managed-source
  set, original per-Project Google recovery, RP ID/UV policy and approved
  release receipt. A normal Google-only Project remains Google-only.
- Preserve any existing `generation.householdAuth.passkeys` intent and
  consumer-owned Auth configuration **without changing the account authority,
  `applicationOrigin`, RP ID, Google issuer/subject links or credentials**.
  The update changes the pinned package and managed baselines only; it is not
  a passkey enrollment, Provider setup, auth DB migration, feature enablement,
  or Production deployment.
- Compare `AUTHENTICATION_BASELINE.json` and the umbrella baseline as
  applicable. All additional/retired managed WebAuthn files must follow the
  same exact-managed-set/drift and retirement rules as the other components;
  never silently replace Project-owned React UI or persistence.
- Where a new package introduces a versioned Auth DB schema, plan an
  **independently approved** backup, disposable restore, old Google login and
  rollback compatibility test before changing runtime config. Do not
  downgrade the database or delete credential material to simplify an update.
- After applying, verify `project-forge check`, profile/manifest integrity,
  Google recovery, and that `Passkeys:Enabled` is still off unless a
  separately approved Project deployment intentionally selected activation.
  An iPhone Safari/installed-PWA run is separate from CI and must be marked
  `NOT VERIFIED` until actually observed.

This is a conditional part of `/project-forge-update`, not a separate
passkey update command or authorization to publish a Kit/package.

## 5. Present one bounded update choice

When the exact target package plan and any generated-consumer companion plan are safe, show the reviewed evidence:

```text
PROJECT FORGE UPDATE READY

Installed: <package>@<installed-version>
Target: <package>@<target-version>
Target integrity: <exact dist.integrity>
Stable authority: <pinned public Platform commit and validated receipt>
Profile: <profile>
Core: <old> → <new>
Deployment: <old> → <new> / unchanged
Generated consumer metadata: <not present / coherent update planned>
Managed drift/conflicts: NONE
```

Then use the host-native **single-select structured choice UI** when available; in VS Code use the native question surface such as `vscode_askQuestions`. Offer:

- `Apply the exact Project Forge package update` `[GIT + FILE WRITE]` — `RECOMMENDED`
- `Keep inspecting only` `[READ ONLY]`
- `Stop` `[NO ACTION]`

Use a numbered text menu only when structured choice UI is unavailable.

Choosing `Apply the exact Project Forge package update` authorizes only:

- creation/switch to one repository-appropriate short-lived update branch when needed;
- exact target package apply;
- removal of unchanged retired package-managed files that the reviewed preview classified as `REMOVE`;
- when `PROJECT_BOOTSTRAP.json` is present, update of its exact `generation["project-forge"].version` and `generation["project-forge"].integrity` to the reviewed target while preserving package/profile;
- migration of a recognized Bootstrap-generated package-verification block from duplicated current literals to the accepted manifest-driven form, only when the existing block still exactly matches the current approved metadata;
- package/baseline/generated-consumer verification;
- inspection of the resulting meaningful diff.

It does not authorize `/deliver`, merge, npm/Core/Deployment/Bootstrap release publication, arbitrary regeneration, or deployment.

## 6. Apply only the exact previewed package

If the consumer is on its default branch, create/switch to a short-lived branch such as:

```text
chore/update-project-forge-<target-version>
```

Branch setup is routine inside the selected bounded update action when safe and unambiguous.

Apply using the same exact package version that was previewed, for example:

```text
npx --yes @mriekki/project-forge@<target-version> update --apply
```

If explicit Core retired-path ownership transfer was separately approved, pass only the exact reviewed modified paths using the package's `--accept-retired core:<path>` contract. Never widen that set implicitly. Unchanged retired managed paths do not need this flag; the package updater removes them according to the reviewed `REMOVE` plan.

For a Bootstrap-generated consumer, complete the reviewed companion metadata changes in the same bounded update before declaring success. Preserve every unrelated `PROJECT_BOOTSTRAP.json` field. Never change package identity or profile as an incidental version update.

Do not run direct `tools/package/sync.py`, Deployment Kit sync, or a remote `[sync-core]` request as part of a package-managed update.

## 7. Verify all baselines, generated metadata, and the diff

After apply, run the exact target package check:

```text
npx --yes @mriekki/project-forge@<target-version> check
```

Then inspect:

```text
git status --short --branch
git diff --stat
git diff -- PROJECT_FORGE_BASELINE.json CORE_BASELINE.json DEPLOYMENT_BASELINE.json PROJECT_BOOTSTRAP.json .github/workflows/ci.yml
```

Confirm:

- `PROJECT_FORGE_BASELINE.json` records the exact target package/version/profile;
- component baseline commits/distributions match the umbrella baseline;
- package check passes for the whole profile;
- unchanged retired managed files shown as `REMOVE` in the preview are actually absent after apply, while any explicitly transferred modified retired Core file remains present and is no longer Core-managed;
- when `PROJECT_BOOTSTRAP.json` exists, its package/version/profile agree with `PROJECT_FORGE_BASELINE.json` and its integrity equals the exact reviewed target registry integrity;
- when the repository contains `tools/project-forge-package/check-managed-baselines.py`, that generated baseline checker passes after all companion metadata changes;
- generated package-verification surfaces no longer contradict the approved manifest metadata;
- consumer-owned content was not overwritten;
- only intended package-managed changes, reviewed generated-consumer companion changes, reviewed removals, and reviewed ownership transfers occurred.

If generated CI still embeds a different package version/integrity after the update, report `GENERATED PROJECT FORGE VERIFICATION DRIFT` and stop before delivery.

Present the meaningful diff for human review. After acceptance, recommend `/deliver` for normal commit/push/PR/CI mechanics.

### Resume a consumer dependency after accepted adoption

When the update was selected to resolve an upstream dependency, preserve the original work-item reference, approved scope and independent work. Verify the exact published target contains the required capability/fix before recommending the preview; do not assume the latest version resolves it. After normal update acceptance/delivery, rerun the original reproduction, managed baseline and affected consumer integration tests. A failed check, conflict or unavailable evidence leaves the dependency unresolved. Record the verified result in the existing work-item authority when authorized; recommend original `/start-work` only after successful verification, without restarting discovery or reapproving unchanged decisions. Do not silently widen the update or bypass normal gates.

## 8. Boundaries

`/project-forge-update` never:

- updates only Core or only Deployment when `PROJECT_FORGE_BASELINE.json` manages them together;
- selects an ordinary update target from npm latest or an unsupported candidate;
- uses a different package version for apply than the reviewed preview;
- performs a downgrade/rollback as an ordinary update;
- overwrites unexplained managed drift;
- auto-accepts Core retired-path ownership transfer for a modified retired file;
- silently repairs a pre-existing mismatch between `PROJECT_BOOTSTRAP.json` and `PROJECT_FORGE_BASELINE.json`;
- changes a generated consumer's package identity/profile or regenerates the repository as an incidental version update;
- guesses at locally modified/unrecognized Bootstrap-generated verification logic;
- publishes npm/Core/Deployment/Bootstrap releases or tags;
- merges the consumer PR;
- deploys an environment.

If reusable shared content is wrong rather than merely outdated, route the defect through `/upstream-fix` first. Package-managed adoption of the accepted fix happens only after an accepted Project Forge package release contains that upstream commit.
