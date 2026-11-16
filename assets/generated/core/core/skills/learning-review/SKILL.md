---
name: learning-review
description: Optional structured post-build understanding check using actual implementation, tests, decisions, and work-item context.
argument-hint: "<work-item ID, external key, or topic>"
user-invocable: true
disable-model-invocation: true
---

# Learning Review

Default to post-build learning from real evidence.

`/learning-review` is primarily assessment. For an instructional changed-file walkthrough first, use `/code-walkthrough`.

## 1. Context

Read only relevant:
- work-item/requirements context,
- changed code/diff,
- tests and observed results,
- important decisions/architecture.

Identify 3–6 concepts the developer should understand.

## 2. Continuous cadence

Ask one question at a time:

```text
question
→ human answer
→ critique accuracy/depth/credibility
→ teach missing concept when useful
→ next question
```

Do not ask whether to continue after every answer.

Assess:
- architecture/request/data flow,
- technical decisions and alternatives,
- debugging/testing,
- failure modes/tradeoffs,
- interview explanation.

Do not edit production code while in learning-review mode.

## 3. Relationship to code walkthrough

Use `/code-walkthrough` when the primary need is:

```text
AI explains the actual implementation
→ developer explores changed files
→ developer builds a mental model
```

Use `/learning-review` when the primary need is:

```text
AI asks
→ developer explains
→ AI critiques
→ gaps become visible
```

A walkthrough may naturally hand off to a learning review, but neither is required for engineering completion or delivery.

## 4. Credibility

Explicitly distinguish:
- what the developer actually implemented/used,
- what AI generated but the developer reviewed/understands,
- what was studied/practiced,
- what remains a gap.

Do not manufacture professional experience.

## 5. Completion

Stop when the human stops/switches workflow, the planned check is complete, or no material learning gaps remain for this session.

Summarize:
- understood well,
- needs reinforcement,
- optional next target.

Then offer a small menu such as continue, optional learning notes/progress, return to engineering workflow, or stop.

`/learning-review` is optional and never blocks engineering completion/delivery.
