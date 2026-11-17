---
name: progress
description: "Read-only developer-facing progress view across Project creation, this workspace instance, work-item/delivery state, and exact project-defined environment capabilities."
argument-hint: "[optional work-item ID or environment]"
user-invocable: true
disable-model-invocation: true
---

# Progress

Purpose: answer `What is complete, what is happening now, and who needs to act?`

Invocation is read-only. `/progress` is a navigation/status surface, not a second workflow database or central workstation registry.

## 1. Reconstruct progress from evidence

Inspect only the evidence needed for the current lifecycle position. Useful sources include:

- `PROJECT_BOOTSTRAP.json`, generated baselines, and repository history for project creation/provenance;
- `DEPLOYMENT_TOPOLOGY.json` as preferred project-owned mutable environment topology when present;
- `DEV_ENVIRONMENT.json`, generated setup scripts, workstation-local setup/developer-mode evidence, and safe setup checks for local readiness;
- observed OS/platform and machine-local evidence for **this workspace instance**;
- current Git branch/status/upstream and safe remote-tracking evidence;
- work-item docs, Reviewer evidence, PR/CI state, and default-branch evidence;
- environment proof/readiness/deployment evidence for exact project-defined environments.

If `DEPLOYMENT_TOPOLOGY.json` does not exist, use `PROJECT_BOOTSTRAP.json` deployment topology only as the initial topology fallback.

Never invent completion because a prior step normally happens. Prefer `UNKNOWN`/`NOT EVIDENCED` over false green state.

Do not mutate setup, Git, GitHub, target, deployment, or project state.

### GitHub-Issues tracking with local Markdown context

When `workItemSource: github-issues`, load the exact canonical GitHub Issue and actual PR/CI/default-branch evidence for current work-item tracking. Resolve any existing stable-ID `docs/work-items/` directory only through unambiguous Issue/document links and use it for approved requirement context, not current Issue status. Local `Status: APPROVED` is requirements maturity; a merged PR is not independently verified Production deployment. If the Issue cannot be fetched or uniquely mapped, show `NOT EVIDENCED` rather than inventing a local fallback authority. GitHub Projects is a derived planning view only.

## 2. Use a small status vocabulary

```text
✓ COMPLETE / READY
● IN PROGRESS
○ NOT STARTED
! ACTION NEEDED
✕ BLOCKED
– DEFERRED / NOT APPLICABLE
? NOT EVIDENCED
```

Do not use percentage-complete estimates.

## 3. Distinguish project state from this workspace instance

A **workspace instance** is one checkout of one Project Forge project on one developer workstation. Multiple instances may be active at the same time.

When useful, report:

```text
THIS WORKSPACE

Platform ............. Windows / macOS
Local setup .......... READY / NOT CONFIGURED / BLOCKED
Branch ................ <branch>
Upstream .............. <remote branch or NONE>
Remote sync ........... UP TO DATE / AHEAD / BEHIND / DIVERGED / NOT EVIDENCED
Personal profile ...... READY / DEFERRED / BLOCKED
```

Do not imply another workstation is offline/idle/authoritative unless concrete evidence says so. Machine-local databases, Docker state, credentials, SSH private keys, and host trust are not project-shared state.

If another workspace advanced the same remote branch, report that as normal coordination evidence and recommend fetch/reconciliation before history-sensitive work. Never rebase/reset/force/stash/merge from `/progress`.

## 4. Show meaningful lifecycle milestones

Prefer milestones such as:

```text
Project creation
This workspace setup
Workspace acceptance
Current work item
Engineering delivery
Environment capabilities
```

Do not expose Bootstrap/package/control-plane plumbing unless a failure there is the actionable blocker.

## 5. Always identify ownership of the next action

Distinguish:

```text
Owner: Project Forge
Action from developer: None
```

from:

```text
Owner: Developer
Action: <one concrete action>
```

Never claim asynchronous/background work unless an actual current operation exists.

## 6. Local setup/readiness

Before first setup on this computer:

```text
PROJECT STATUS

✓ Project creation
○ This workspace setup
○ Workspace acceptance
○ First work item

THIS WORKSPACE
Platform ............. macOS
Local setup .......... NOT CONFIGURED

Next:
  /setup
```

After machine checks pass but before human acceptance, show setup ready and workspace acceptance as the developer action.

Do not treat deferred application scaffolding or optional remote environments as failed local setup.

## 7. Engineering/delivery progress

When implementation has begun, summarize the current work item and only delivery states supported by evidence.

Different workstations may work on independent work items/branches concurrently. Same-branch remote advancement is coordination evidence, not corruption.

If work is delivery-complete and deployment is the next useful action, identify the exact project-defined environment; do not assume Staging unless topology/policy says so.

## 8. Environment capabilities are topology-driven

Enumerate exact names from current project topology rather than a fixed Local/Staging/Production list.

A useful shape is:

```text
ENVIRONMENT CAPABILITIES — THIS WORKSTATION

Local ............ READY
Demo ............. PROVEN
QA ............... NOT CONFIGURED
prod-east ........ ACCESS READY
```

For each named environment distinguish evidence when useful:

```text
purpose/classification
placement/binding
target access from this workstation
environment proof deployment state
real project application deployment state
```

Example:

```text
Demo
  Purpose .............. demo
  Target access ........ READY
  Deployment path ...... PROVEN
  Project application .. NOT YET DEPLOYED
```

A setup-time disposable proof means the environment mechanics were proven from this workstation; it does not mean the real project application is deployed.

A custom name such as `prod-east` with purpose `production` must be presented as Production-class and retain stronger later gates.

`Production-class NOT CONFIGURED` does not make local/non-Production work incomplete.

Shared remote environments may be reachable from multiple workspace instances. Access/trust proof is per workstation; remote runtime/environment state is shared. Respect app/environment deployment locking when reporting concurrent mutations.

## 9. Handoff to `/next-step`

`/progress` answers where the developer is. `/next-step` recommends one sensible action.

Examples:

```text
Next:
  /setup
```

```text
Next:
  /start-work EN01
```

```text
Next:
  /setup demo
```

```text
Next:
  /deployment-readiness demo
```

```text
Next:
  /deploy demo
```

Do not perform that action from `/progress`.
