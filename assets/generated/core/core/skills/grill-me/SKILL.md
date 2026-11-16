---
name: grill-me
description: Continuously challenge requirements, architecture, plans, implementation assumptions, or work-item coverage, with optional session-level reconciliation of resolved decisions into permitted authorities.
argument-hint: "<work-item ID, external key, document, plan, or topic>"
user-invocable: true
disable-model-invocation: true
---

# Grill Me

Purpose: improve reasoning by challenging the highest-value uncertainty without adding process overhead or forcing the developer to choose a separate documentation-aware grilling command.

Invocation begins read-only.

## 1. Resolve authority and minimum context

Read `.github/project-forge-workspace.json` when present and only the minimum relevant context.

Determine when applicable:
- the authoritative work-item source;
- which local documents are authoritative, supplemental, read-only, or not used;
- relevant accepted ADR/design rules;
- whether an external write integration is actually available and permitted.

Never assume Product/Feature Briefs exist. Never assume `Jira Epic == Feature Brief`. Do not claim external Jira/Issue content was read unless it was actually available.

## 2. Continuous grilling

Ask one material question at a time. Explain briefly why the question matters. Challenge vague answers, hidden scope, contradictions, and weak assumptions.

Challenge areas may include:
- missing acceptance behavior;
- cross-work-item/Epic gaps;
- domain/business rules;
- lifecycle/state transitions;
- validation/failure behavior;
- data integrity;
- concurrency/transactions;
- destructive/reversible actions;
- architecture assumptions;
- security/operational risk;
- accessibility/UX implications when relevant;
- testability.

When the purpose is to expose or strengthen the human's reasoning, ask open-ended first. For a bounded decision with a small credible option set, follow `INTERACTIVE_SESSION_GUIDE.md`: use host-native single-select structured choice UI for mutually exclusive alternatives when available, multi-select only when several selections are valid together, and preserve free-text/`Other / specify` when choices may be incomplete.

Recommend at most one answer/option only when current evidence or a clear engineering tradeoff supports it. A recommendation is advice, not an accepted decision.

Cadence:

```text
question
→ human answer
→ challenge/analyze the answer
→ explain implications when useful
→ reconcile the resolved decision when the session is authorized to do so
→ next material question
```

Do not ask `Do you want to continue?` after each answer. The human already entered a continuous grilling mode.

## 3. Optional decision reconciliation

Grilling does not require document writes. When resolved decisions would benefit from durable reconciliation, present one session-level **single-select structured choice** through the host UI when available. In VS Code use the native question surface such as `vscode_askQuestions`.

Offer:
- `Continue grilling only` `[READ ONLY]` — default when no durable update is needed;
- `Reconcile resolved decisions during this session` `[MODIFIES DOCS]`;
- `Stop` `[NO ACTION]`.

Use a numbered text list only when structured choice UI is unavailable.

Selecting `Reconcile resolved decisions during this session` authorizes only focused updates to the permitted current work-item documents for this active session. Do not ask again after every answer.

When a decision is resolved:
- update an existing permitted local authority/supplement only when this session has document-write authorization;
- if Jira/GitHub/another external system is authoritative and no permitted write integration is available, accumulate a concise `PROPOSED EXTERNAL WORK-ITEM UPDATE`;
- if a permitted external write integration exists, require an explicit `[EXTERNAL WRITE]` choice before writing externally;
- never create a competing local source merely to store an answer.

For local-document models, common homes are:
- brief: high-level scope/outcome/major rule;
- combined requirements: detailed user/engineering behavior and testable scenarios;
- decisions: resolved work-item decision/basis;
- ADR: only a meaningful cross-cutting architecture decision.

Pause reconciliation when an answer would materially change higher-level approved scope, contradict another authority/ADR, or require a new cross-cutting decision. Continue read-only grilling when appropriate.

## 4. Boundaries

Do not:
- implement production code;
- invoke subagents;
- create artifacts merely because grilling occurred;
- infer approval from an answer;
- silently write local or external authorities without the applicable session/write authorization.

Stop when:
- the human says stop/done/pause;
- no material issues remain;
- a true scope/decision/action gate appears;
- the human switches workflow.

## 5. Natural completion

Summarize once:
- decisions strengthened;
- documents or proposed external updates changed, if any;
- unresolved issues/conflicts;
- recommended next workflow.

Typical next workflows:
- `/refine-requirements` for systematic detailed coverage;
- `/start-work` when the item is ready;
- normal review/approval when a material requirement gate remains.
