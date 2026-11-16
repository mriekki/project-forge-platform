# Engineering Learning Workbook

This is an optional, repository-neutral learning scaffold.

Use the actual project first. The goal is to understand, trace, debug, defend, and explain real engineering work rather than memorize a generic curriculum.

## Learning tools

Use the learning tools for different purposes:

```text
/code-walkthrough — instructional walkthrough of actual implementation changes
/learning-review   — assessment of whether the developer can explain and defend the implementation
/coach             — targeted concept learning, debugging practice, design discussion, drills, and deeper follow-up
/db-lab            — evidence-backed database/schema/ORM/query-plan/change exploration and database interview practice
/system-lab        — evidence-backed architecture/runtime/failure/scale/change exploration and system-design interview practice
```

All learning activity is optional and never an engineering delivery gate.

For database usage examples, see `docs/process/DATABASE_LEARNING_WORKBENCH.md` in a greenfield consumer. For advanced system-design usage, see `docs/process/SYSTEM_DESIGN_LEARNING_WORKBENCH.md`.

## Preferred project-first sequence

When an implementation is stable enough to study, a useful optional sequence is:

```text
implementation
→ /code-walkthrough
→ /learning-review
→ targeted /coach, /db-lab, or /system-lab where gaps remain
```

After successful delivery, the workflow may surface the relevant evidence labs again while the change is fresh. A work item that changed persistence may make `/db-lab changes <work-item>` especially useful; one that changed APIs, dependencies, messaging, runtime topology, security, observability, performance or failure behavior may make `/system-lab changes <work-item>` especially useful. These are recommendations, not gates.

A code walkthrough should connect two views of every meaningful change:

```text
FUNCTIONAL
What behavior changed? What can the user/system do now?

TECHNICAL
Which files, classes, functions, data structures, framework mechanisms, tests, and dependencies make that behavior work?
```

Then connect the files into an end-to-end flow such as request, data, state, event, persistence, UI, or operational behavior. Use the repository's actual architecture rather than forcing a generic sequence.

During a walkthrough, deeper learning can branch into tracing, interactive diagrams, debugging discussion, design tradeoffs, quizzes, capacity/failure reasoning, or interview-style explanation. The walkthrough and labs remain read-only; discovered implementation issues return to the normal engineering workflow rather than being silently fixed inside learning mode.

## Advanced learning pattern

Evidence labs should favor active reasoning:

```text
current evidence
→ learner prediction/assumption
→ reveal strongest available evidence
→ explain discrepancy
→ trace/apply/debug
→ defend tradeoff
→ change one constraint
→ reason again
```

Use explanation-first when the human asks for it. Do not turn every learning interaction into a quiz.

Generated workbench diagrams are disposable projections. The repository/database/runtime evidence remains authoritative, and invoking a lab should rebuild its view from current evidence automatically.

## Suggested practice loop

```text
concept or changed code
→ project example
→ developer explains in own words
→ trace/apply/debug
→ tradeoff/failure-mode follow-up
→ interview-style explanation when useful
```

## Core areas

- language/framework fundamentals,
- application/request/data flow,
- APIs and integration boundaries,
- database/SQL/ORM behavior,
- frontend state/validation/accessibility when relevant,
- testing/debugging/observability,
- messaging/distributed systems when relevant,
- CI/CD/deployment/operations,
- security and data protection,
- architecture/system design,
- capacity/performance/reliability,
- coding/DSA interview patterns.

Use `LEARNING_MAP.md` to choose a small number of high-value topics and the drill files for focused practice. Database and system-design depth should be tracked by independent competencies rather than one broad score. Learning progress is optional and never an engineering gate.

## Experience credibility

Keep these categories distinct:

```text
actually implemented/used
AI-generated but reviewed/understood
studied/practiced
not yet understood
```

A code walkthrough or lab can help move AI-assisted implementation toward reviewed/understood code, but it does not by itself prove mastery or professional experience. Generated diagrams and completed exercises must not become false claims of professional experience.
