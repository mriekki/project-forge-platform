---
name: refine-requirements
description: Assess and continuously refine requirement coverage for the configured authoritative work-item source without forcing a local requirements hierarchy.
argument-hint: "<work-item ID, external key, or topic>"
user-invocable: true
disable-model-invocation: true
---

# Refine Requirements

Purpose: make requirements implementation-ready when the work benefits from detailed precision.

This skill is proportional; it is not mandatory for every change.

## 1. Resolve authority and context

Read `.github/project-forge-workspace.json` when present.

Determine:
- authoritative work-item source,
- parent/grouping context when actually available,
- permitted Product/Feature Brief roles,
- whether local detailed requirements are authoritative, supplemental, read-only, or not used,
- relevant accepted ADR/design rules.

Read only the minimum relevant context. Do not preload unrelated work items. Do not claim external content was read unless it is actually available.

Never assume `Jira Epic == Feature Brief`.

When review/approval will concern a local artifact, classify it as the PRIMARY review subject. Supporting Feature/Product briefs, ADRs, and design documents are CONTEXT or TRACEABILITY unless they are themselves the decision subject.

## 2. Decide whether detail is warranted

Detailed refinement is useful for behavior such as:
- lifecycle/state transitions,
- archive/delete/restore,
- validation/uniqueness,
- identity/permissions/attribution,
- data integrity,
- concurrency/transactions,
- destructive/reversible behavior,
- failure handling,
- multiple related workflows,
- cross-layer behavior needing testable boundaries.

For LIGHT/obvious work, say detailed refinement is unnecessary and return to `/start-work`.

## 3. Requirement shape depends on authority

### Local combined requirements permitted

Prefer one combined file rather than separate user-story/domain files.

Product Feature:

```text
requirements.md
├── User Stories
├── Domain Requirements
├── Acceptance / Validation Scenarios
├── Open Decisions
├── Traceability
└── Approval
```

Engineering Enabler:

```text
requirements.md
├── Engineering Requirements
├── Acceptance Criteria / Validation Scenarios
├── Open Decisions
├── Traceability
└── Approval
```

Do not invent personas for technical enablers.

### External work item is primary

If Jira/Issue/another external system is primary and local detailed requirements are not an approved supplement:
- assess the external content actually provided/accessible,
- maintain concise proposed external-work-item updates during the session,
- do not create `requirements.md` merely as a dumping ground.

## 4. Initial behavior is read-only

Report an evidence-backed coverage assessment first:

```text
REQUIREMENTS COVERAGE

User / engineering outcomes:
✓ ...
○ ...

Domain / engineering rules:
✓ ...
○ ...

Acceptance / validation:
✓ ...
○ ...

Cross-work-item/grouping context:
✓ / ○ / N/A

Open material decisions:
- ...

AUTHORITATIVE SOURCE
<source>

STATUS
<DRAFT / APPROVED / external status / not represented locally>
```

Then present only relevant actions as a **single-select structured choice** when the host supports it. In VS Code, use the native question surface such as `vscode_askQuestions` rather than printing a numbered menu. Conceptual choices may include:

- `Review outcomes` `[READ ONLY]`
- `Review rules` `[READ ONLY]`
- `Review acceptance scenarios` `[READ ONLY]`
- `Refine identified gaps` `[MODIFIES DOCS or PROPOSED EXTERNAL UPDATE]`
- `Grill an unresolved decision` `[READ ONLY]`
- `Review full requirements/work item` `[READ ONLY]`
- `Approve local requirements` `[REQUIREMENTS GATE]` when applicable
- `Stop` `[NO ACTION]`

When the human selects `Review full requirements/work item`, foreground the PRIMARY review surface when the host supports it. For local Markdown requirements, prefer rendered Markdown preview. In VS Code, use `projectForge.openReviewArtifact` with the exact workspace-relative path when available. For an external-primary work item, use the best available external issue/item surface instead of creating a local surrogate solely for preview.

Make a recommendation only when current requirement evidence or a clear engineering tradeoff supports one. If so, mark exactly one choice with the host's `recommended` indicator when that metadata exists; otherwise append `[RECOMMENDED]` to exactly one option label. Briefly explain why in the option description or surrounding prompt. A default/preselected value may match the recommendation, but a default alone must never communicate advice or approval. If there is no clear basis, show the choices without a recommendation and without a preference-implying default. The selected answer, not the recommendation, controls what the session does or records.

If the host has no structured choice UI, present the same relevant choices as a concise numbered or lettered text fallback, preserve `[RECOMMENDED]` on the evidence-backed option when applicable, and accept the number/letter, label, or free-form intent. Do not use the text fallback as the normal VS Code path.

## 5. Active refinement session

Once the human selects a modifying refinement choice, enter a bounded continuous session:

```text
ask one material requirement question
→ human answers
→ reconcile/update/propose only what was resolved
→ update directly affected validation scenario when useful
→ summarize exactly what changed
→ next material question
```

For bounded requirement decisions such as lifecycle policy, validation behavior, destructive/reversible handling, or a small set of credible alternatives, use the choice-first interaction guidance from `INTERACTIVE_SESSION_GUIDE.md`. Render mutually exclusive alternatives through host-native **single-select** controls when available. Use multi-select only when the requirement genuinely permits multiple simultaneous selections. Keep `Other / specify` or free-text available when the option set may be incomplete. Keep outcome wording, workflow descriptions, acceptance intent, and other human-authored framing open-ended when predefined choices would constrain the requirement.

Recommendation behavior follows the shared guide: recommend at most one option, only when evidence/tradeoffs support it; make the recommendation visibly distinguishable through native metadata or `[RECOMMENDED]`; give a concise rationale; never record the recommendation as accepted until the human selects or confirms it; and honor a `no recommendation` request for that question only.

Example of a supported recommendation:

```text
Decision: How should a browser-to-real-SQLite path be proven for a narrowly scoped work item?

Choices:
- Integration test against real SQLite
- Browser smoke check through the API
- Both [RECOMMENDED] — proves persistence and browser/API paths without implying a broad end-to-end suite
- Other / specify
```

Treat this as advice for the human to accept, change, or replace. Do not record `Both` as a requirement until the human selects or confirms it.

Do not ask after each answer whether to update.

For local combined requirements:
- preserve stable IDs,
- do not renumber approved IDs,
- keep implementation convenience out unless it is itself an approved requirement.

For external-primary requirements without write authorization:
- accumulate `PROPOSED EXTERNAL WORK-ITEM UPDATES`.

If a permitted external write integration exists, require explicit `[EXTERNAL WRITE]` authorization before applying those updates.

## 6. Pause only for material conflicts

Stop automatic reconciliation when an answer would:
- materially change approved higher-level scope,
- contradict an approved Product/Feature/Enabler rule,
- contradict an accepted ADR/design decision,
- require a cross-cutting architecture decision,
- remain too ambiguous to record faithfully.

Then present a small explicit choice using the same host-native structured-choice rule. Keep the question open-ended instead when the human needs to explain or reframe the conflict in their own words.

## 7. Approval gate

Local detailed requirements use only meaningful authoring states:

```text
DRAFT
APPROVED
```

Human approval is explicit. Do not infer approval from review/planning/implementation.

Before approval:
1. report coverage and open material decisions;
2. identify the exact PRIMARY local requirements artifact;
3. foreground/open that artifact in the best available review surface when the host supports it;
4. only then render the `[REQUIREMENTS GATE]` choice.

For Markdown requirements in VS Code, prefer rendered preview; when the Project Forge companion command is available, invoke `projectForge.openReviewArtifact` with the exact workspace-relative requirements path. If automatic opening is unavailable, provide the exact path/link and explicitly tell the human that this is the artifact being approved.

The gate should make the review subject unmistakable, for example:

```text
HUMAN REVIEW REQUIRED

Gate: REQUIREMENTS APPROVAL
Primary artifact: docs/work-items/<work-item>/requirements.md
Opened: Markdown Preview / <fallback surface>
Open material decisions: NONE / list
```

Only an explicit `[REQUIREMENTS GATE]` choice may change local status to `APPROVED`. Opening the document, viewing the preview, or selecting a read-only review action never changes approval state. When the host offers structured choices, render this approval gate as a single-select action, not a numbered chat menu.

External work-item status/approval follows the external team's conventions; Project Forge must not fabricate a local approval state.

## 8. Natural completion

Summarize:

```text
REQUIREMENTS REFINEMENT COMPLETE

Updated/proposed:
- <outcomes>
- <rules>
- <acceptance scenarios>

Open material decisions:
None / list

Authority/status:
<source and status>
```

Then offer review, more grilling/refinement, approval when applicable, or stop using the same structured-choice-first rule.

## 9. Stop boundary

Do not create implementation plans or production code.

When requirements are ready, recommend `/start-work <ID-or-key>`. That command may prepare the implementation plan, but STANDARD/ELEVATED implementation still requires the distinct plan-approval gate defined by `/start-work`.
