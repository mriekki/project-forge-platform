---
name: code-walkthrough
description: "Read-only guided walkthrough of an implementation diff, explaining changed files functionally and technically with optional deeper coaching, tracing, diagrams, quizzes, debugging discussion, and interview practice."
argument-hint: "[work-item|PR|commit|current] [light|focused|deep]"
user-invocable: true
disable-model-invocation: true
---

# Code Walkthrough

Purpose: help the developer understand an actual implementation by walking through the changed files in a sensible order and connecting functional behavior to technical design.

`/code-walkthrough` is optional, read-only, and never blocks review, delivery, merge, or work-item completion.

## 1. Boundaries

- Do not edit production code or tests.
- Do not implement fixes during the walkthrough.
- Do not commit, push, merge, or modify a PR.
- Do not update learning-progress files unless the human explicitly chooses that after the walkthrough.
- Do not invoke subagents.
- Do not silently broaden the implementation scope.
- Do not pin/request/switch to a premium model automatically.
- Distinguish observed implementation evidence from assumptions.
- Distinguish AI-generated code, developer-reviewed understanding, study, and actual implementation experience when credibility matters.

If a bug, design concern, or missing test is discovered, explain it and offer a return to the normal implementation/review workflow. Do not fix it while in walkthrough mode.

## 2. Resolve the change set

Use Git/GitHub evidence as the source of truth. VS Code Source Control/diff views are visual aids, not workflow state.

Resolve in this order when possible:

```text
explicit PR / commit / ref
→ work-item-associated branch or PR supported by evidence
→ current feature branch versus the merge-base of the configured default branch
→ current staged/unstaged tracked changes
→ ask one concise scope question when materially ambiguous
```

For an explicit PR, use the PR base/head change set and do not silently mix unrelated local changes.

For an active feature branch, prefer the branch change from the default-branch merge base. Identify relevant tracked working changes and call out untracked files explicitly rather than silently omitting them.

For merged work, use the PR, merge commit, or explicit historical commit range.

Never invent branch, work-item, PR, or commit associations.

## 3. Depth

```text
Light   — what changed, why, and major connections
Focused — default; behavior, important mechanics, relationships, tests, and learning hooks
Deep    — important methods/blocks, state/data flow, dependencies, edge cases, failure modes, tests, and tradeoffs
```

Depth may vary by file. Treat trivial configuration lightly unless it materially affects behavior; spend more depth on implementation anchors.

If the human needs to choose a depth, use host-native **single-select structured choice UI** when available. Do not recommend a depth unless the requested learning goal or change complexity clearly supports one; `Focused` is a descriptive default, not permission to manufacture a recommendation.

## 4. Build the walkthrough plan

Before explaining the first file:

1. identify the changed files and change types,
2. read only enough work-item/requirements context to understand intended behavior,
3. identify likely implementation anchors and relationships,
4. order files for understanding rather than alphabetically,
5. present a concise plan and start with the first meaningful file.

Use repository architecture rather than a fixed stack assumption. A common web-application order may be:

```text
domain/data model
→ persistence
→ service/business logic
→ API/controller
→ client model/service/state
→ UI/component
→ tests near the behavior they verify
→ configuration/operational files
```

An event-driven or systems repository may require a different path. Infer from actual imports, references, paths, changed symbols, tests, and architecture.

## 5. Per-file walkthrough

For each meaningful changed file, cover only what is useful:

```text
FILE <n> OF <total>
<path>

ROLE
Why this file exists in the system.

FUNCTIONAL CHANGE
What behavior or capability changed.

TECHNICAL CHANGE
Important classes/functions/data structures/framework mechanisms and how they changed.

HOW THIS CONNECTS
Upstream/downstream callers, data flow, state flow, persistence, UI, events, or other dependencies.

WHY THIS DESIGN
Important choice, convention, or tradeoff when evidence supports it.

TESTING
Relevant tests/evidence and what they do or do not prove. Never claim a test passed unless execution evidence was observed.

LEARNING HOOKS
Concepts worth understanding more deeply.
```

For change types:
- new file: explain why the responsibility now exists;
- modified file: explain meaningful before-versus-after behavior;
- deleted file: explain what responsibility disappeared or moved;
- renamed/moved file: distinguish structural movement from behavioral change.

Group trivial generated/configuration changes when that improves learning, but do not hide behaviorally important files.

## 6. Guided navigation

Default to one file or one tightly related file group at a time. Do not dump the whole implementation at once.

At a natural file boundary, a compact navigation cue may be shown:

```text
NEXT: <suggested file>
Use: next | deeper | explain this | trace | why this design | diagram | quiz | debug | interview | skip | stop
```

When the host exposes structured choice UI and the human is being asked to choose among these navigation actions, prefer a relevant **single-select** subset rather than forcing the human to type a token. Keep free-text commands valid. Do not turn the full command vocabulary into a large mandatory selector when the next action is already obvious.

Interpret these naturally:
- `next` — continue to the suggested next file;
- `deeper` — increase depth for the current file/topic;
- `explain this` — focus on the selected/current method, block, symbol, or diff hunk;
- `trace` — follow request/data/state/event flow across files;
- `why this design` — discuss alternatives and tradeoffs grounded in repository context;
- `diagram` — use an ephemeral Mermaid diagram when useful;
- `quiz` — briefly switch to adaptive Coach-style understanding questions;
- `debug` — discuss likely failure modes, evidence, and debugging approach without implementing a fix;
- `interview` — practice explaining or defending the implementation credibly;
- `skip` — cover the current file lightly and move on;
- `stop` — end without affecting engineering status.

Do not repeatedly ask whether to continue when the next action is obvious.

## 7. Tracing and learning depth

When tracing, connect actual call/data/state flow. Example shape only:

```text
UI/input
→ client/service
→ API/handler
→ application/service logic
→ persistence/event/system boundary
→ response/result
```

Map deeper exploration to the shared learning levels when useful:

```text
L1 Recognize
L2 Explain
L3 Trace
L4 Apply / Debug
L5 Defend / Design
L6 Interview Ready
```

Use `/coach` for broader concept learning and `/learning-review` for structured assessment after the walkthrough.

## 8. Completion

When the planned change set is covered or the human stops, summarize:

- end-to-end implementation flow,
- major functional changes,
- important technical decisions and connections,
- concepts explored deeply versus lightly,
- tests/evidence actually observed,
- learning gaps or topics worth revisiting,
- optional next learning actions.

When offering bounded next actions, use host-native **single-select structured choice UI** when available. Relevant choices may include:

- `/learning-review <same scope>` `[READ ONLY]`
- `/coach <specific concept>` `[READ ONLY]`
- `Return to engineering workflow` `[NO ACTION]`
- `Stop` `[NO ACTION]`

Recommend at most one only when the walkthrough evidence shows a clear learning gap or the engineering workflow is clearly the better next step; otherwise present the choices without a recommendation. Use a numbered text menu only when structured choice UI is unavailable.

Do not create a new engineering state such as `CODE_WALKTHROUGH_PENDING`. Walkthrough completion is learning evidence, not a delivery gate.
