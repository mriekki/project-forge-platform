---
name: wait-what
description: "The last explanation did not land. Re-explain it with enough context to understand where we are and what happens next."
argument-hint: "[optional note about what was unclear]"
user-invocable: true
disable-model-invocation: true
---

# Wait, What?

Purpose: repair communication when the immediately preceding explanation did not land.

This skill re-explains. It does not perform new engineering work.

## 1. Use existing context first

Re-pitch the immediately preceding explanation, or the specific unclear point named by the human.

Prefer already-available conversation/repository context. Do not run commands, inspect new Git/GitHub state, modify files, or take the next workflow action merely to explain the prior response.

If a safe explanation depends on information that is genuinely missing, say what is missing instead of inventing it.

## 2. Use plain technical English

Prefer:
- short, direct sentences;
- concrete nouns instead of vague pronouns;
- one idea per sentence when possible;
- familiar repository/work-item terminology;
- explicit cause-and-effect language;
- examples only when they make the explanation clearer.

Use a Simplified-Technical-English style, but do not claim formal ASD-STE100 compliance.

When repository glossary material exists, prefer its terminology. A glossary is helpful, not required.

## 3. Re-establish orientation

For a substantive explanation, cover only what helps:

```text
CURRENT CONTEXT
Where we are and what led here.

WHAT I MEANT
The important point in simpler language.

WHY IT MATTERS
Why the point affects the current work or decision.

WHAT HAPPENS NEXT
The immediate next step, if there is one.
```

Do not force all headings for a tiny clarification. Keep the response proportional to the confusion.

## 4. Respect human gates

If the unclear explanation immediately preceded a human approval or consequential-action gate, complete the re-explanation before asking for that approval again.

Do not treat `/wait-what` as approval to continue, write files, commit, push, merge, deploy, or call external systems.

## 5. Route deeper needs without changing modes silently

If the human actually needs:
- current workflow-state orientation, suggest `/next-step`;
- deeper concept teaching, suggest `/coach`;
- a structured explanation of implementation changes, suggest `/code-walkthrough`;
- an understanding check, suggest `/learning-review`.

Do not silently switch into those modes unless the human asks.

## 6. Boundaries

`/wait-what` is:
- read-only,
- user-invoked,
- non-blocking,
- communication-focused,
- usable during requirements, planning, implementation, review, delivery, setup, learning, or operations discussions.

It does not create a new engineering workflow state.

## Provenance

Inspired by Matt Pocock's `wait-what` productivity skill in `mattpocock/skills` (MIT licensed). This Project Forge Core version is independently rewritten for repository-agnostic Human-in-the-Loop engineering workflows.
