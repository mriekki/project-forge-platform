---
name: define-feature
description: Define or clarify a feature, initiative, engineering enabler, or other work item while respecting the configured source-of-truth and optional brief model.
argument-hint: "<work-item ID, external key, idea, or topic>"
user-invocable: true
disable-model-invocation: true
---

# Define Feature

Keep discovery proportional. Do not turn a small change into a ceremony.

## 1. Resolve authority first

Read `.github/project-forge-workspace.json` when present before assuming a document hierarchy.

Possible authoritative sources include:
- Jira Story/Epic,
- GitHub Issue,
- local Product/Feature/Enabler brief,
- local requirements,
- another team work-item system,
- small session context for trivial work.

Use external work-item content only when it is actually available. Never claim a Jira/Issue was read when it was not.

Never assume `Jira Epic == Feature Brief`.

## 2. Classify the request

Classify as one of:
- Product Feature,
- Engineering Enabler,
- Small Change / Task,
- Cross-Cutting Requirement / Standard,
- ADR-worthy Architecture Decision,
- Future Roadmap Idea.

Do not invent user stories for technical foundation work.

## 3. Respect brief modes

Product/Feature Brief modes may be:

```text
not-used
read-existing
supplemental-experimental
authoritative
suggest-complex
```

Behavior:
- `not-used`: do not create the brief.
- `read-existing`: read when relevant; do not create/update.
- `supplemental-experimental`: an optional brief may be proposed, clearly labeled non-authoritative.
- `authoritative`: use/update the configured brief as authority.
- `suggest-complex`: recommend a brief only when cross-work-item or workflow complexity makes it useful.

Do not create a competing source of truth.

## 4. Discovery cadence

Ask one material question at a time when a real decision is unresolved.

For bounded decisions with a small credible answer space, use the choice-first interaction guidance from `INTERACTIVE_SESSION_GUIDE.md`. When the host exposes structured choice controls, render mutually exclusive alternatives through single-select UI rather than a plain numbered menu; use multi-select only when several simultaneous selections are actually valid. Keep `Other / specify` or free-text available when choices may be incomplete. Keep initial product/problem framing, desired outcomes, workflows, and other answers that need the human's own wording open-ended rather than constraining them to invented options.

Clarify only what matters, such as:
- user/engineering outcome,
- scope and non-scope,
- important workflows/lifecycle,
- domain/engineering invariants,
- destructive/reversible behavior,
- security/privacy expectations,
- dependencies,
- acceptance summary,
- open decisions.

Record unresolved decisions explicitly rather than inventing them.

## 5. Detailed requirements are proportional

Create/refine detailed requirements only when precision is useful.

When local detailed requirements are permitted and useful, prefer one combined file.

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

If the configured external work item is primary and local detailed requirements are not an approved supplement, propose updates to that external source instead of creating local duplicate authority.

## 6. Stop boundary

Stop before implementation.

Do not create an implementation plan or production code as part of `/define-feature`.

If systematic lower-level coverage is valuable, recommend:

```text
/refine-requirements <ID-or-key>
```

## 7. Guided ending

Use a small evidence-backed set of relevant actions. In VS Code, render them through the host-native **single-select structured choice UI** such as `vscode_askQuestions` when available. Conceptual choices may include:

- `Review definition` `[READ ONLY]`
- `Grill unresolved behavior` `[READ ONLY]`
- `Refine detailed requirements` `[READ ONLY initially]`
- `Approve requirements/scope` `[REQUIREMENTS GATE]` when applicable
- `Start work` `[READ ONLY]` when already ready
- `Stop` `[NO ACTION]`

Make the recommended next action visible when evidence supports one. Use a numbered text menu only when structured choice UI is unavailable. A file-changing choice authorizes only that bounded action/session.
