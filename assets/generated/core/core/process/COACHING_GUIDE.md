# Optional Coaching Guide

Coaching is first-class but never required for engineering completion.

## Depth

```text
1. Light — quick explanation/check
2. Focused — one topic, moderate depth
3. Deep — trace/apply/debug/defend
4. Broad — survey related areas and identify gaps
5. Let Coach recommend
```

## Modes

```text
1. Learn a concept
2. Walk through real project code
3. Debugging exercise/review
4. Coding / DSA drill
5. SQL / database drill
6. Design defense
7. System-design exercise
8. Interview drill
9. Learning-gap assessment
10. Recommended learning path
11. Docs / tutorial / video resources
12. Return to engineering workflow
```

For a structured walkthrough of an implementation change set, use `/code-walkthrough`. It is the guided changed-file path under the coaching umbrella: resolve the actual Git/PR/commit diff, order files for understanding, explain functional and technical changes, and allow deeper tracing, diagrams, quizzes, debugging discussion, or interview practice without editing code.

Use `/coach` for broader or ad-hoc concept learning. Use `/learning-review` when the primary goal is to assess whether the developer can explain and defend what was built.

For hands-on database learning, `/db-lab` is the evidence-backed companion to Coach. Coach can teach database concepts, probe gaps, and run interview drills; Database Lab inspects the current project schema/ORM/query/migration/query-plan evidence, supports change-focused learning, and can drive query-to-ERD highlighting when an interactive workbench is installed. See `DATABASE_LEARNING_WORKBENCH.md`.

For hands-on system-design learning, `/system-lab` is the evidence-backed companion to Coach. Coach can teach architecture/distributed-systems concepts, challenge assumptions, and run interview drills; System Lab inspects the current project architecture/runtime/API/dependency/messaging/deployment evidence and supports interactive scenario, failure, capacity, latency, security, observability, testing, evolution, and change-focused learning. See `SYSTEM_DESIGN_LEARNING_WORKBENCH.md`.

Use the labs as siblings:

```text
system context / request-event flow / failure / scale
                    ↕
              /system-lab
                    ↕
          database component/node
                    ↕
                 /db-lab
                    ↕
schema / ORM / SQL / plans / migrations / constraints
```

Generated lab views are disposable projections of current evidence. Invoking a lab means re-discover the current evidence; the learner should not manually maintain or refresh diagrams.

## Levels

```text
L1 Recognize
L2 Explain
L3 Trace
L4 Apply / Debug
L5 Defend / Design
L6 Interview Ready
```

A useful optional sequence after stable implementation is:

```text
code walkthrough
→ learning review
→ targeted coaching / database lab / system lab as needed
```

After delivery, relevant labs may be surfaced again while the work-item change is fresh. The reminder is visible but never mandatory.

For advanced DB/System learning, prefer prediction before reveal when practical:

```text
learner predicts
→ reveal evidence
→ reconcile gap
→ apply/debug
→ defend tradeoff
→ change constraint
```

Explanation-first remains valid when requested.

None of those learning activities is an engineering delivery gate.

Once a coaching mode starts, continue automatically until stop or natural completion. Use the actual repository as the curriculum whenever possible. Learning trackers/resources remain optional.
