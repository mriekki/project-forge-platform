---
name: next-step
description: Read-only orientation over setup, work-item, Git, review, PR, PR CI, merge, post-merge default-branch CI, deployment readiness, deployment handoff state, and optional documentation/learning surfaces.
argument-hint: "[optional work-item ID or external key]"
user-invocable: true
disable-model-invocation: true
---

# Next Step

Purpose: answer `Where am I, and what is the sensible next action?`

Invocation is read-only. `/progress` gives the broader milestone/status view; `/next-step` recommends one useful action from current evidence.

## 1. Resolve minimum context

Before assuming implementation has started, inspect enough workspace evidence to determine whether this checkout has completed local setup and human workspace acceptance. Useful setup evidence may include `DEV_ENVIRONMENT.json`, generated setup/doctor outputs, workstation-local developer-mode evidence, and the current session's acceptance state.

Read `.github/project-forge-workspace.json` when present and use the optional work-item key or infer from current branch/session context.

Inspect only what is needed. Never invent setup/Jira/Issue/PR/CI/review/merge/readiness/deployment state.

Local Git examples:

```text
git branch --show-current
git status --short --branch
git diff --stat
git diff --cached --stat
git log -1 --oneline
```

When GitHub CLI is available/authenticated:

```text
gh pr status
gh pr view
gh pr checks
```

When post-merge CI matters, inspect the configured default branch/workflow rather than assuming it is named `main`.

## 2. Setup comes before implementation

When the repository is generated but this workstation is not ready, recommend:

```text
/setup
```

Do not make the developer manually sequence tool installation, dependency restore, local mode convergence, doctor, or remote-target setup when `/setup` can route those concerns.

Typical pre-work states:

```text
LOCAL_SETUP_PENDING
LOCAL_SETUP_BLOCKED
WORKSPACE_ACCEPTANCE_PENDING
READY_FOR_FIRST_WORK_ITEM
```

Rules:

- local readiness is the first success target;
- intentionally unconfigured/deferred Staging or Production does not block local coding;
- a deferred application scaffold may still have a ready workspace;
- machine checks do not accept the editor/workspace experience on the human's behalf.

When deterministic setup passes but human workspace acceptance is still needed, recommend the smallest meaningful acceptance check using `docs/process/SETUP_ACCEPTANCE_CHECKLIST.md` and current editor/agent evidence. Do not rerun setup without evidence it is needed.

When the workspace is accepted and the first approved work item is clear, recommend `/start-work <ID>`.

If the developer wants the broader status instead of one action, offer `/progress` as a read-only choice.

## 3. Engineering/delivery states

Examples:

```text
IMPLEMENTING
LOCAL_REVIEW_PENDING
REVIEW_CHANGES_REQUIRED
REVIEW_READY
HUMAN_LOCAL_ACCEPTANCE_PENDING
DELIVERY_READY
PUSHED_NO_PR
PR_CI_PENDING
PR_CI_FAILED
PR_CI_GREEN
MERGE_READY
MERGED_DEFAULT_BRANCH_CI_PENDING
MERGED_DEFAULT_BRANCH_CI_FAILED
DELIVERY_COMPLETE
ENVIRONMENT_READINESS_PENDING
ENVIRONMENT_READY_TO_DEPLOY
DEPLOYMENT_VALIDATION_PENDING
```

Use only states supported by observed evidence.

Do not add a separate final-PR-acceptance state when the PR still exactly matches the already accepted local implementation. In that normal case, `/deliver` combines final acceptance and merge into the single `MERGE_READY` decision. If PR evidence changed materially, describe the required final PR review explicitly before returning to `MERGE_READY`.

Do not add learning- or documentation-only states. Optional coaching, labs, and project documentation do not change engineering delivery state unless the approved work item explicitly makes documentation acceptance evidence.

## 4. Output

```text
CURRENT STATE
<evidence-backed summary>

RECOMMENDED NEXT STEP
<one action and why>

CHOICES
<only relevant bounded actions, rendered through structured choice UI when available>
```

When there is more than one relevant action, use the host's native **single-select structured choice UI** following `INTERACTIVE_SESSION_GUIDE.md`. In VS Code, use the question surface such as `vscode_askQuestions` when available. Keep consequence labels visible, mark the recommended choice where evidence supports one, and include `Other / specify` or free-text only when the action space may be incomplete. Use multi-select only for an explicitly multi-action workflow; ordinary `/next-step` choices are mutually exclusive.

A textual numbered `OPTIONS` list is only the fallback when no structured choice UI is available. Only show relevant choices. `/next-step` orients; it does not become another workflow database.

For an unprepared generated workspace, a good result is simply:

```text
CURRENT STATE
Local setup has not been completed on this computer.

RECOMMENDED NEXT STEP
/setup
```

If useful, offer `/progress` `[READ ONLY]` and `Stop` `[NO ACTION]` through the structured selector; do not print a numbered menu in normal VS Code use.

## 5. Optional documentation and learning choices

When implementation is stable enough to understand or document, `/next-step` may offer these choices without making them gates:

```text
/docs [open|check|build]
/code-walkthrough <scope>
/learning-review <scope>
/coach <topic>
/db-lab [changes <work-item>]
/system-lab [changes <work-item>]
```

If the human is being asked to select one of these bounded next actions, use the same single-select structured-choice rule. The command list above is descriptive, not a required numbered menu.

Prefer `/docs` for the coherent project briefing/document map, `/code-walkthrough` for implementation flow, `/db-lab` for concrete schema/query/index/ORM evidence, and `/system-lab` for architecture/runtime/failure/scale evidence.

Safe generated projections may be prepared automatically. Do not silently rewrite project-owned prose, accept an ADR, or make learning mandatory before `/deliver` unless the approved work item explicitly requires it.

## 6. Delivery handoff

When all are ready:

```text
implementation complete
local verification satisfactory
Reviewer READY
human meaningful-diff approval complete
```

recommend `/deliver` rather than separate branch/commit/push/create-PR confirmations.

`/deliver` owns the compound delivery action:

```text
short-lived branch setup/recovery when needed
→ selective stage
→ verify staged diff
→ commit
→ push
→ create/update PR
→ PR CI
→ one Merge and finalize delivery decision
→ merge
→ post-merge default-branch CI
→ safe delivered-branch finalization
```

Because `/deliver` is manually invoked, do not insert another permission menu merely to begin those routine mechanics. It will stop itself for changed evidence, ambiguity/risk, CI failure requiring code changes, or the merge/finalize decision.

If PR CI failed, recommend inspect/diagnose/targeted fix. Do not silently change code. If PR CI is green and evidence still matches the accepted implementation, return to `/deliver` for the single merge/finalize gate. Never merge from `/next-step` merely because CI is green.

After merge, return to `/deliver` while required default-branch CI/finalization is incomplete; otherwise report delivery complete and only optional relevant documentation/learning follow-ups.

## 7. Deployment handoff

For release/deployment engineering after engineering delivery is complete, recommend the selected environment's state-driven readiness workflow:

```text
/deployment-readiness <environment>
```

Use the same command whether the environment still needs initial discovery, prerequisite setup, repair, or final pre-deploy verification. Readiness re-discovers current state and resumes automatically; do not tell the human to choose discovery/enable/resume modes.

When evidence shows a configured named environment is ready to deploy, recommend:

```text
/deploy <environment>
```

`ENVIRONMENT_READY_TO_DEPLOY` means pre-deploy prerequisites are satisfied. It does not require live application health, smoke, route resolution, or release-specific rollback evidence that can only be established by deploying the selected artifact.

After `/deploy`, use repository/tool evidence to distinguish a successfully validated deployment from `DEPLOYMENT_VALIDATION_PENDING` or a deployment failure.

For a read-only overview across configured environments recommend:

```text
/deployment-readiness status
```

Do not infer readiness of one environment from another. Production is never an implicit/default environment, and `/next-step` never authorizes a remote or production deployment merely by recommending `/deploy`.

## 8. Keep it focused

Do not auto-run Reviewer, auto-run learning activities, auto-merge, auto-deploy, pin/select a model, or maintain duplicate workflow state outside Git/GitHub and the configured work-item/readiness authority.

Generating a disposable read-only documentation or learning workbench is not the same as performing a learning activity, approving documentation prose, or proving understanding.
