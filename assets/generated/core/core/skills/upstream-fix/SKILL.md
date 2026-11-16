---
name: upstream-fix
description: Route reusable bugs discovered in a consumer to the canonical shared repository, allow bounded upstream implementation, preserve a portable handoff, and let consumer work continue with explicitly acknowledged temporary Project Forge drift.
argument-hint: "[optional problem summary]"
user-invocable: true
disable-model-invocation: true
---

# Upstream Fix

`/upstream-fix` is for a problem discovered while working in a consumer repository when the likely owner is shared Project Forge code rather than consumer product code.

The governing rule is:

```text
discover in consumer
→ diagnose/prove in consumer
→ classify canonical owner
→ preserve a portable upstream handoff
→ optionally continue consumer work with acknowledged temporary drift
→ fix/deliver in owning canonical repository
→ adopt through the consumer's recorded distribution boundary
→ verify again in consumer
```

A temporary edit to a shared-managed file inside a consumer may be useful as diagnosis/proof, but it is never the canonical delivered fix.

## 1. Invocation authorization

Invoking `/upstream-fix` authorizes:

- read-only ownership/provenance inspection in the consumer;
- classification to the smallest canonical owner;
- creation/update of the ignored local handoff artifact `.project-forge/UPSTREAM_FIX_HANDOFF.md`;
- inspection of already-available local canonical repository candidates;
- when ownership and the bounded patch are clear and a canonical checkout is safe, routine creation/use of one short-lived canonical work branch and application of only that bounded fix plus focused tests/docs.

Invocation does **not** authorize commit, push, PR creation, merge, release publication, package publication, deployment, rewriting/discarding consumer work, changing multiple canonical repositories in one bounded fix, or committing a temporary shared-managed consumer workaround.

Normal review and `/deliver` occur later while focused on the owning canonical repository.

## 2. Establish consumer provenance

From the consumer root inspect, when present:

- `PROJECT_FORGE_BASELINE.json`;
- `CORE_BASELINE.json`;
- `DEPLOYMENT_BASELINE.json`;
- `.github/project-forge-workspace.json`;
- current Git branch/status/diff;
- the files involved in the reported problem or temporary proof.

Run repository-local managed-baseline checks when available.

Do not assume every generated-looking file is shared-owned. Use baseline managed-path records as the primary ownership evidence, and use `PROJECT_FORGE_BASELINE.json` to determine whether component baselines are managed together by an umbrella package.

## 3. Classify the owner

Use the smallest owning layer that would need the same fix for another consumer.

### Consumer-owned

Application domain logic, UI behavior, app-specific configuration, product tests, and consumer architecture normally remain consumer-owned.

Result:

```text
CONSUMER FIX
Owner: current repository
```

Return to the consumer's normal `/start-work` / implementation / review / `/deliver` flow.

### Core-owned

Evidence includes a path managed by `CORE_BASELINE.json` or behavior defined by reusable Core workflow assets.

```text
CORE BUG
Owner: <repository recorded by CORE_BASELINE.json>
```

### Deployment-Kit-owned

Evidence includes a path managed by `DEPLOYMENT_BASELINE.json` or reusable deployment mechanics owned by that recorded Kit.

```text
DEPLOYMENT BUG
Owner: <repository recorded by DEPLOYMENT_BASELINE.json>
```

### Package assembly / Project Forge Platform-owned

When canonical component source is correct but the published package bytes, component pins, package engine, or umbrella baseline behavior is wrong:

```text
PROJECT FORGE PLATFORM BUG
Owner: package/platform repository supported by evidence
```

### Generator/control-plane owned

If the package payload is correct but generation/publication/orchestration materializes it incorrectly, classify Bootstrap/control-plane ownership from evidence rather than patching a generated consumer.

If ownership is genuinely ambiguous, report `UPSTREAM OWNER UNCLEAR`. Preserve the observed evidence in the handoff artifact, but do not write to multiple repositories speculatively.

## 4. Temporary consumer proof

A temporary consumer edit to a shared-managed path is allowed for diagnosis when it proves the fix in real application context.

Report it explicitly:

```text
TEMPORARY SHARED-MANAGED PROOF
Consumer path: <path>
Canonical owner: <repo>
Do not deliver this consumer copy as product code.
```

Do not silently discard the proof and do not stage/commit it as ordinary consumer implementation.

## 5. Preserve a portable handoff

Once a likely shared owner exists, create or refresh:

```text
.project-forge/UPSTREAM_FIX_HANDOFF.md
```

This file is workstation/session evidence for transfer into ChatGPT or another canonical-owner workspace. It is not product documentation and must remain unstaged/uncommitted. Generated Project Forge projects normally ignore `.project-forge/`; if repository policy does not ignore it, keep the handoff out of the consumer delivery diff.

Include only observed/non-secret evidence:

```markdown
# Project Forge Upstream Fix Handoff

## Consumer context
- Repository: <owner/repo or local identity>
- Branch/work item: <observed>
- Project Forge package/baseline: <observed version/commit/profile>

## Classification
- Owner: <Core | Deployment Kit | Platform | Bootstrap | Control Plane | unclear>
- Canonical repository: <repo when known>
- Managed consumer paths involved: <paths>

## Problem
<concise symptom and expected behavior>

## Reproduction
<minimal observed reproduction>

## Temporary consumer proof
- Status: <none | local proof present>
- Paths: <paths>
- Diff summary: <summary, not secrets>
- Validation: <observed checks>

## Recommended upstream scope
<smallest reusable change and focused regression coverage>

## Adoption boundary
<package release / component sync / regeneration / other evidence-backed path>

## Consumer continuation
- Override: <not requested | accepted>
- Managed workaround must remain unstaged/uncommitted: yes
- Known dependency of current consumer checks on workaround: <yes/no/unknown>
```

The handoff is useful even when a canonical checkout is unavailable or the upstream fix will be handled later.

## 6. Consumer continuation override

A reusable-platform defect is **not automatically a reason to halt the consumer work item**.

After classification/handoff, when the current consumer work can still proceed without committing the temporary shared-managed workaround, present one bounded single-select choice through the host-native question UI when available:

- `Continue consumer work with acknowledged Project Forge drift` — permits the current consumer session/work item to continue while the shared-managed workaround remains local and excluded from delivery. **RECOMMENDED** when the workaround is isolated and continuing will produce useful consumer-owned work.
- `Resolve the upstream fix now` — switch focus to the canonical owner and continue the upstream workflow.
- `Stop here` — preserve state without further writes.

Use a numbered text list only when native structured choice UI is unavailable.

Selecting the continuation option means:

```text
PROJECT FORGE DRIFT OVERRIDE ACCEPTED
```

Record that choice in `.project-forge/UPSTREAM_FIX_HANDOFF.md` and continue normal consumer implementation. Do not repeatedly ask the same override question in the same unchanged session/work-item state.

The override authorizes **continuation only**. It does not authorize:

- staging/committing/pushing shared-managed drift;
- editing baselines to bless the drift;
- bypassing required CI, Reviewer, merge, release, or Production gates;
- destructive cleanup of the workaround;
- claiming the consumer has adopted the canonical fix.

If consumer-owned implementation genuinely cannot be separated from the modified managed file, report that dependency clearly. The human may still continue exploratory/product work under the override, but normal delivery can only stage consumer-owned paths and required CI/policy may still fail until the upstream fix is distributed.

Unexplained managed drift, suspected secrets, ambiguous ownership, or a staged/shared-managed workaround remains a stop condition until classified or removed from the proposed consumer delivery scope.

## 7. Resolve a safe canonical checkout

For the classified owner consider, in order:

1. an explicit path supplied by the human;
2. an already-open workspace folder with the expected Git remote;
3. a normal sibling checkout derived from the canonical repository name.

Do not broadly scan the filesystem and do not clone automatically merely to continue.

A candidate is safe only when it is the expected repository, has no merge/rebase/cherry-pick in progress, has no unrelated local work, and does not require stash/reset/rebase/force/discard operations.

If no safe canonical checkout is available, the handoff plus continuation override is a valid outcome; do not block consumer implementation solely because canonical work cannot start immediately.

## 8. Port the bounded fix upstream

When a safe canonical checkout exists and the equivalent reusable fix is clear:

1. inspect canonical implementation/tests before editing;
2. create/use one repository-appropriate short-lived branch;
3. reproduce the root cause canonically where practical;
4. apply the reusable fix without consumer-specific names/configuration;
5. add/update focused tests that would have caught the defect;
6. update canonical docs when the contract changed;
7. run relevant local checks;
8. show the meaningful canonical diff and observed validation.

If the consumer proof cannot be generalized safely, reclassify and update the handoff rather than forcing it upstream.

## 9. Handoff to canonical delivery

When the upstream implementation is ready:

```text
UPSTREAM FIX READY

Owner: <canonical repo>
Branch: <branch>
Consumer proof: <path/status>
Portable handoff: .project-forge/UPSTREAM_FIX_HANDOFF.md
Validation: <observed checks>
Next: focus the canonical repository and run /deliver
```

`/upstream-fix` does not commit/push/open/merge the canonical PR itself.

If the consumer continuation override was accepted, returning to consumer work does not wait for canonical delivery unless current work truly requires the distributed fix.

## 10. Adopt the accepted fix through the right boundary

After the canonical PR is merged and required default-branch CI is green, re-read the consumer provenance before choosing adoption.

### Package-managed consumer (`PROJECT_FORGE_BASELINE.json` present)

Do **not** direct-sync Core or Deployment Kit into the consumer.

The accepted component fix must first become part of an accepted published Project Forge package:

```text
canonical Core/Deployment fix merged
→ Project Forge Platform pins the exact accepted component commit
→ Project Forge Platform PR + CI
→ explicit package publication gate
→ published exact @mriekki/project-forge version
→ consumer /project-forge-update <version>
```

Until that package exists, report:

```text
PACKAGE RELEASE REQUIRED
Canonical consumer adoption requires a Project Forge package that contains the accepted upstream commit.
Consumer work may continue under an accepted drift override as long as shared-managed workaround paths remain outside consumer delivery.
```

Do not silently patch `PROJECT_FORGE_BASELINE.json`, `CORE_BASELINE.json`, or `DEPLOYMENT_BASELINE.json` to pretend the package contains the new component.

### Component-only Core consumer (`PROJECT_FORGE_BASELINE.json` absent)

A Core-owned fix may return through `/core-sync` using the exact accepted Core commit/distribution.

### Component-only Deployment consumer (`PROJECT_FORGE_BASELINE.json` absent)

A Deployment-owned fix may return through the canonical Deployment Kit component sync and refresh `DEPLOYMENT_BASELINE.json`.

### Generator/control-plane fix

Validate through that platform's canonical regeneration/update path, never by manually editing generated managed files.

Then rerun the original reproduction and baseline checks in the consumer when adoption actually occurs.

## 11. Consumer delivery guard

Before consumer `/deliver`, distinguish **unexplained managed drift** from **explained/acknowledged temporary upstream proof**.

### Unexplained managed drift

If `/deliver` finds Core-, Deployment-, or Project Forge-package-managed drift with no matching upstream classification/handoff/override, stop before staging/commit/push and route through `/upstream-fix`.

### Explained drift with accepted continuation override

When `.project-forge/UPSTREAM_FIX_HANDOFF.md` records the current managed paths and the human accepted continuation for the unchanged issue:

1. warn prominently that Project Forge managed drift is still present;
2. keep all shared-managed drift and the handoff file unstaged/uncommitted;
3. selectively stage only the human-accepted consumer-owned implementation;
4. disclose in the PR body that local validation may have used an acknowledged Project Forge workaround when that is true;
5. proceed with normal PR/CI mechanics rather than hard-stopping solely because the local workaround exists.

Use a compact warning such as:

```text
PROJECT FORGE DRIFT WARNING
Upstream handoff: .project-forge/UPSTREAM_FIX_HANDOFF.md
Managed workaround: present locally, excluded from consumer delivery
Consumer delivery: continuing under accepted override
```

Required CI/policy remains authoritative. Do not waive a failing required check because the failure is caused by the absent upstream fix.

If any shared-managed path is already staged, appears in the proposed consumer commit/PR, no longer matches the handoff, or ownership becomes ambiguous, stop and re-evaluate before writing.

## 12. Boundaries

`/upstream-fix` never:

- merges changes;
- publishes releases/tags/packages;
- deploys production;
- commits one bounded fix across multiple repositories;
- auto-stashes, resets, rebases, force-pushes, or discards work;
- requires ordinary consumer users to clone shared repositories;
- treats a temporary managed consumer edit as a permanent fork;
- bypasses `PROJECT_FORGE_BASELINE.json` with component-only sync;
- treats the continuation override as authorization to commit shared-managed drift;
- treats the continuation override as a waiver of required CI or merge policy.
