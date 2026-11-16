---
name: start-work
description: Assess requirement readiness and implementation risk, prepare and review the implementation plan when warranted, then begin bounded implementation only after the required human authorization.
argument-hint: "<work-item ID, external key, or concise change>"
user-invocable: true
disable-model-invocation: true
---

# Start Work

## 0. Invocation and implementation boundary

`/start-work` is the orchestration entry point for preparing a work item to be implemented. Its invocation authorizes read-only context resolution, requirement-readiness assessment, risk classification, and implementation planning.

For **STANDARD** and **ELEVATED** work, invoking `/start-work` does **not** by itself authorize substantive implementation, code writes, or implementation branch setup. Those begin only after the human explicitly approves the final proposed implementation plan at the plan gate defined below.

For **LIGHT** work, there is no mandatory formal plan. The human-selected implementation action may authorize bounded implementation directly when the scope is tiny, obvious, and low-risk.

Never blur these states:

```text
/start-work invoked
≠ plan approved
≠ implementation authorized
```

## 1. Resolve the requested work

Read `.github/project-forge-workspace.json` when present.

Resolve only the context needed:
- authoritative work-item source,
- parent/grouping context when actually available,
- optional Product/Feature/Enabler briefs according to configured authority,
- local detailed requirements when permitted/present,
- relevant decisions/ADRs/architecture/standards,
- current code/tests and branch/diff when relevant.

Do not require local briefs when the repository uses Jira/Issues. Do not invent external content.

When the host can open repository review surfaces, foreground the PRIMARY authoritative requirement/work-item artifact when human review is needed. Treat additional briefs/ADRs/design documents as CONTEXT or TRACEABILITY unless they are themselves the approval subject.

## 2. Check requirement readiness before planning

Assess:
- outcome clarity,
- acceptance criteria/validation expectations,
- material domain/engineering rules,
- dependencies/cross-work-item context,
- unresolved human decisions,
- requirement authority/status.

Ask:

```text
Does detailed precision matter?
Does the authoritative source contain enough detail?
If local requirements exist, are they DRAFT or APPROVED?
Are material decisions unresolved?
```

If detailed precision is warranted but incomplete, recommend `/refine-requirements` or `/grill-me` rather than silently inventing behavior. `/grill-me` may remain read-only or, when the human selects its session-level reconciliation option, write resolved decisions into permitted authorities.

If local requirements are DRAFT and carry material behavior, human approval is the gate before substantive planning/implementation. Before that approval, follow `HUMAN_GATES.md`: identify and foreground the PRIMARY requirements review surface when the host supports it.

If requirements are already sufficient/approved under the configured model, do not force another refinement cycle.

### CI/policy evidence is not a start-work gate

When requirements say CI/checks must pass before a later merge, release, or deployment action, use repository-configured workflows/checks plus observable repository policy/mergeability as the planning evidence available now.

Do not interpret words such as `required CI` or `required checks` as a mandate to discover GitHub branch-protection/ruleset admin settings before implementation can begin. Those settings may provide additional evidence later when they are observable, but inability to read them is not by itself a blocker.

Do not ask the human to open GitHub Settings and transcribe required-check names merely to proceed with `/start-work`. Stop and ask only when actual evidence conflicts or missing policy information creates a concrete unresolved decision that materially affects implementation or the later consequential action.

## 3. Classify risk

### LIGHT

Tiny, obvious, low-risk; no meaningful schema/security/concurrency/deployment/major-UX implications.

```text
human selects bounded implementation action
→ short-lived branch setup when appropriate
→ Agent
→ relevant checks
→ human meaningful-diff review
```

No formal plan or detailed requirements are required.

### STANDARD

Meaningful multi-file work.

```text
requirements ready as needed
→ native plan
→ plan review surface foregrounded
→ HUMAN IMPLEMENTATION-PLAN APPROVAL
→ short-lived work branch setup
→ Agent implementation
→ checks
→ Reviewer
→ human meaningful-diff acceptance
```

### ELEVATED

Use for:
- schema/data-loss risk,
- authentication/security,
- concurrency/transactions,
- release/deployment/recovery,
- significant architecture,
- broad cross-layer changes,
- hard-to-reverse decisions.

```text
detailed approved requirements / ADR as needed
→ native plan
→ Reviewer challenges plan
→ Reviewer findings reconciled into final proposed plan
→ final plan review surface foregrounded
→ HUMAN IMPLEMENTATION-PLAN APPROVAL
→ short-lived work branch setup
→ implementation in small slices
→ stronger verification
→ Reviewer
→ human acceptance
```

Explain why the level was chosen.

## 4. Optional learning checkpoint

For STANDARD/ELEVATED work, once requirements are ready, coaching may be offered but is never required. When the human needs to choose, render a **single-select structured choice** through the host UI when available; in VS Code use the native question surface such as `vscode_askQuestions`.

Relevant choices are:
- `Continue without coaching` — `RECOMMENDED` default;
- `/coach` for a short pre-build concept review;
- `/grill-me` for challenge rather than teaching;
- `Stop`.

Use a numbered text list only when structured choice UI is unavailable. For LIGHT work, do not interrupt with coaching unless requested.

## 5. Planning rules and mandatory plan gate

For STANDARD/ELEVATED work:
- use the editor's current native planning capability;
- plan approach, affected areas, key decisions, risks, non-scope, and verification;
- do not auto-launch implementation subagents while planning;
- do not create mandatory `spec.md` or `tasks.md`;
- save a durable plan only when it is useful across sessions or for genuinely complex/risky work;
- require explicit human plan approval before implementation or implementation branch setup.

For ELEVATED work, Reviewer challenges the proposed plan before the human approval gate. Reconcile material Reviewer findings into the final proposed plan first. The human reviews that final plan, not an earlier plan plus unresolved reviewer objections.

### Present the review surface before asking for approval

Follow the human-review-surface contract from `HUMAN_GATES.md` and `INTERACTIVE_SESSION_GUIDE.md`.

PRIMARY review subject is the final proposed implementation plan. Prefer:
1. the host's native plan surface when it can be foregrounded;
2. a durable plan document when one exists and is useful;
3. otherwise the full substantive plan in the conversation.

If a durable plan is a repository artifact, resolve its exact work-item-specific path from the current work-item authority/gate state before opening it. Do not select a global plan, another work item's artifact, or a focus-derived file.

In VS Code, when the Project Forge companion review command/tool is available, request presentation of that exact artifact. Record the actual presentation outcome when the host reports one, including rendered Markdown vs editor fallback vs unavailable/failed. If the host exposes a stronger native plan/review surface, use that instead.

If automatic opening is unavailable or fails, keep the gate usable: include the exact plan link/path inside the question and provide a deterministic manual fallback. For Markdown in VS Code on Windows, tell the human to open the exact linked file and press `Ctrl+Shift+V`.

Before rendering the gate, state explicitly:

```text
Implementation has NOT started.
```

Then present a gate equivalent to:

```text
IMPLEMENTATION PLAN REVIEW REQUIRED

Work item: <ID / key / concise change>
Risk: <STANDARD | ELEVATED>
Approval subject: final proposed implementation plan
Primary artifact: <exact clickable work-item plan link/path | native plan surface>
Presentation: <rendered Markdown opened | editor fallback opened | automatic opening unavailable/failed | native plan foregrounded>

Plan covers:
- approach
- affected areas
- key technical decisions
- risks / mitigations
- verification strategy
- explicit non-scope

Open material decisions: <NONE | list>

Implementation has NOT started.

1. Approve plan and begin implementation [PLAN APPROVAL + CODE WRITE]
2. Request changes to the plan [PLAN ONLY]
3. Review assumptions / risks [READ ONLY]
4. Stop [NO ACTION]
```

The exact PRIMARY artifact link/path must be present in the approval question itself; do not rely on a link in earlier commentary. The artifact named in the gate must be the same artifact requested/opened for presentation.

When the host exposes structured choice UI, render the actions as a single-select control rather than a numbered menu while preserving the consequence labels and the same work-item/artifact context in the question. Do not preselect or infer `Approve plan and begin implementation` merely because the plan exists, was opened, or the human invoked `/start-work`.

Only option 1 (or equivalent explicit free-text authorization) authorizes substantive implementation. Options 2-4 do not. Preview, navigation, cancellation, or a question asking where the plan is never counts as approval.

### Material plan changes after approval

Routine implementation details may evolve inside the approved approach. Reopen the implementation-plan gate when new evidence requires a material change to any of:
- architecture or major component boundaries,
- approved scope/non-scope,
- schema/data handling or migration behavior,
- authentication/security/authorization model,
- externally visible behavior or contract,
- major dependencies/integration strategy,
- verification strategy when the change materially weakens or alters the approved proof.

Before continuing, show:

```text
APPROVED PLAN CHANGED

Material change: ...
Reason: ...
Revised PRIMARY artifact: <exact revised plan link/path | native plan surface>
Presentation: <actual presentation evidence>
```

Foreground the revised PRIMARY plan review surface when supported, then require renewed plan approval using the revised exact link/path inside the question. Do not silently continue implementation under stale authorization or reuse stale presentation evidence.

## 6. Working branch setup

Once implementation is authorized to begin, establish the repository-appropriate short-lived work branch as routine setup before substantive edits.

For STANDARD/ELEVATED work, **plan approval is the implementation authorization boundary**. Do not create/switch the implementation branch merely because `/start-work` was invoked or a plan was produced.

Do not ask a separate branch-creation permission when all of the following are true:
- implementation is already authorized under the applicable gate;
- the current branch is the default/integration branch and repository policy expects short-lived work branches;
- the work-item boundary is clear;
- the target branch name is unambiguous under repository convention or the Project Forge fallback below;
- creating/switching branches does not require history rewriting or discarding work.

Branch naming order:
1. repository/team convention when defined,
2. an already-existing branch clearly tied to the work item,
3. Project Forge fallback: `<lowercase-work-item-id>-<concise-slug>` for ID-backed work, or `work/<concise-slug>` for a concise ad hoc change.

Examples of the fallback shape are conceptual only; never invent a consumer-specific work-item ID in Core documentation or behavior.

If scoped uncommitted changes already exist on the default branch and clearly belong to this work item, preserve them while creating/switching to the short-lived branch when Git can do so safely. Verify that the worktree diff is unchanged after the branch switch.

Stop and ask only when branch policy/naming is materially ambiguous, the intended branch already exists with divergent work, unrelated changes are present, or the operation would require stash/reset/rebase/force/history rewriting.

For LIGHT work, branch setup is part of the human-selected implementation action. For STANDARD/ELEVATED work, it is part of the explicit approved implementation start after plan approval.

## 7. Deployment enabler

When a work item owns release/deployment engineering or environment enablement, classify it ELEVATED when the change materially affects deployment/recovery/security behavior.

Environment readiness may begin early with the normal state-driven interface:

```text
/deployment-readiness <environment>
```

It begins with existing local/repository configuration, shows simple known machine facts for confirmation, and continues only as far as current engineering/evidence safely allows. It does not authorize application deployment.

After implementation review/local acceptance, use `/deliver`. After `/deliver` reports the merge, default-branch CI, and applicable repository-policy evidence satisfied, return to the same state-driven readiness command for the selected environment:

```text
/deployment-readiness <environment>
```

The workflow re-discovers state and continues from the furthest safe point; do not require the human to switch from a discovery mode to an enable mode.

Production remains a role with stronger policy and deployment authorization; it does not use a separate readiness workflow.

## 8. Guided ending

Return:
- CURRENT STATE,
- risk level and why,
- requirement readiness,
- current review subject when a human gate is pending,
- branch state / expected short-lived branch only after implementation is authorized or about to begin,
- RECOMMENDED NEXT STEP,
- a small set of relevant action choices.

Render mutually exclusive next actions through the host's **single-select structured choice UI** when available, following `INTERACTIVE_SESSION_GUIDE.md`. In VS Code, use the native question surface such as `vscode_askQuestions`. Make the recommended action visible when evidence supports one, include `Other / specify` or free-text only when the action set may be incomplete, and use a numbered text menu only as the no-structured-UI fallback.

If the workflow has reached the STANDARD/ELEVATED plan gate, stop there until the human selects an explicit plan action. Do not include an alternate implementation action that bypasses the plan gate.

Do not skip an unresolved requirement/plan gate merely because implementation is technically possible. Once implementation is explicitly approved, do not insert a separate ceremonial branch-creation gate when the branch setup is safe and deterministic.
