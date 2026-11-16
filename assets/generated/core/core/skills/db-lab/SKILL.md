---
name: db-lab
description: "Optional project-aware database learning lab using actual schema, ORM, migration, query, and query-plan evidence for SQL, relational design, debugging, change exploration, and interview practice."
argument-hint: "[schema|changes|trace|plan|debug|migration|interview|topic] [work-item] [light|focused|deep]"
user-invocable: true
disable-model-invocation: true
---

# Database Lab

`/db-lab` is an optional hands-on database learning surface. It complements `/coach`; it does not replace the engineering workflow or authorize implementation changes.

For detailed usage and examples, read `docs/process/DATABASE_LEARNING_WORKBENCH.md` in a greenfield consumer (or the canonical `core/process/DATABASE_LEARNING_WORKBENCH.md`).

## 1. Boundaries

- Start from the **current** repository and its documented development/test database configuration.
- Re-discover relevant database evidence whenever the lab is invoked. Running `/db-lab` means inspect current evidence and show the current view; do not make the human remember to refresh/rebuild an ERD.
- Prefer read-only inspection. Do not mutate application data, apply migrations, add/drop indexes, or change production code while in Database Lab mode.
- Never inspect Production credentials or Production data.
- Do not invent schema, SQL, query-plan behavior, ORM translation, or index usage. Distinguish inferred behavior from captured evidence.
- If safe local database/runtime evidence is unavailable, fall back to repository artifacts and say what could not be verified.
- Generated learning artifacts are disposable projections of current evidence. Generate in temp/cache output and do not commit them unless explicitly requested.
- Discovered implementation defects return to the normal engineering workflow; do not silently fix them here.
- Learning is optional and never blocks delivery.

## 2. Database competencies

Use the common L1-L6 learning levels across independent database areas:

```text
relational modeling
keys + integrity constraints
normalization + data anomalies
SQL query construction
indexes + access patterns
query plans + performance reasoning
transactions + concurrency
ORM translation + abstraction leaks
schema evolution + migrations
database debugging
design defense + interview communication
```

Do not collapse these into one generic "SQL level". A developer may be strong in query syntax and weak in relational design, indexing, transactions, or ORM translation.

## 3. Schema mode

Build an evidence-backed current view from the best available sources:

```text
physical database metadata
ORM model/configuration
migration history
schema SQL / DDL
project architecture and requirements
```

Show tables/entities, columns, types, nullability, primary keys, foreign keys, unique/check constraints, indexes, relationship cardinality, cascade behavior, and relevant ORM mappings when evidence exists.

When useful, distinguish:

```text
DOMAIN MODEL   — what the application/domain expresses
ORM MODEL      — what the ORM maps and tracks
PHYSICAL MODEL — what the relational database actually stores/enforces
```

## 4. Change-focused mode

`/db-lab changes <work-item>` should focus on the accepted/delivered change set when evidence is available.

Show relevant changes to:

- entities/tables and columns;
- keys, constraints, relationships and cascade behavior;
- indexes/access paths;
- ORM mappings and generated SQL behavior;
- migrations/schema evolution;
- affected query paths;
- transaction/concurrency assumptions.

Connect each material change to the learning implication. A changed ORM/model file is evidence that persistence code was touched, not proof that the physical database changed; verify against migrations/schema/database evidence.

When a previous disposable workbench snapshot exists, it may be used as a comparison aid. The current database/repository evidence remains authoritative.

## 5. Query trace mode

Trace a real application query without guessing:

```text
application/ORM expression
→ ORM translation preview when available
→ actual executed SQL when captured
→ parameters
→ tables/relationships touched
→ query plan when available
→ indexes actually chosen by the planner
→ materialized/application result
```

Keep translation preview and actual executed command distinct when the framework exposes both.

## 6. Query-to-ERD highlighting

When the distributed SQLite workbench or another compatible viewer is available, a selected query should drive a linked ERD view:

- highlight tables referenced by the SQL;
- highlight FK edges when both related tables participate in the selected query;
- highlight qualified query columns when they can be resolved to a table;
- distinguish candidate indexes from indexes actually selected by the query planner;
- show query-plan evidence alongside the diagram;
- allow table/column/index selection for deeper explanation.

Never claim the planner used an index merely because it exists or looks relevant.

If no interactive viewer is available, provide a temporary Mermaid/text diagram using the same evidence and clearly label it as a fallback rather than a live ERD.

## 7. SQLite workbench

When `tools/project-forge-db-lab/sqlite-workbench.py` exists and a safe local development/test SQLite database is known, prefer it for physical-schema and query-plan evidence.

The tool:

- opens the SQLite database in `mode=ro`;
- introspects tables/views, columns, primary keys, foreign keys, indexes, and DDL;
- accepts optional captured-query JSON containing `name`, `sql`, and optional `parameters`;
- uses `EXPLAIN QUERY PLAN` only for `SELECT`/`WITH` queries;
- generates self-contained `index.html` plus `workbench.json` learning artifacts;
- supports interactive table/index inspection and query-to-ERD highlighting.

Generate output in a stable per-repository disposable/temp location when practical. Running the lab should regenerate the current view; an already-open older browser tab is not authoritative.

The workbench analyzes captured SQL; it does not itself capture Entity Framework commands. Obtain translation/execution evidence through supported framework mechanisms first, then pass the captured SQL into the workbench when useful.

## 8. Query-plan/performance mode

Use provider-native plan evidence where safely available. Ask the developer to predict likely scans/searches/joins/index behavior before revealing the plan when that improves learning.

```text
query/access pattern
→ developer prediction
→ plan evidence
→ explain scan/search/join behavior
→ developer proposes index/query change
→ predict changed plan
→ compare evidence in a safe sandbox when available
```

Do not teach "add an index" without connecting it to a concrete access pattern, selectivity/order needs, write cost, and plan evidence.

## 9. Debug mode

```text
symptom
→ database hypotheses
→ distinguishing evidence
→ SQL / parameters
→ plan / constraints / transaction state
→ root cause
→ fix concept
→ prevention
```

The human should diagnose before the lab reveals the answer unless they explicitly request explanation-first coaching.

## 10. Migration mode

Connect:

```text
ORM migration/change
↔ generated DDL/SQL when available
↔ schema before
↔ schema after
↔ data-safety implications
```

Ask the developer to predict effects before showing generated SQL when useful. Discuss destructive changes, nullability transitions, backfills, constraint creation, and rollback limitations without applying migrations in learning mode.

## 11. Interview/design mode

Use the active project domain as context, but perturb requirements so the developer must reason rather than reproduce the existing schema.

Drive one material question at a time through:

```text
requirements clarification
→ entities
→ relationships/cardinality
→ keys
→ constraints
→ normalization
→ access patterns
→ indexes
→ transactions/concurrency
→ evolution/scaling
→ design defense
```

Challenge unsupported choices. Ask why a junction table exists, why a key was selected, what deletion means historically, which queries justify an index, and how changed requirements alter the design.

## 12. ORM-specific evidence

When Entity Framework Core is present, distinguish:

- LINQ/application expression;
- translation preview such as `ToQueryString()` when appropriate;
- actual executed `DbCommand` from supported logging/interception evidence;
- generated migration SQL;
- entity/change-tracking state versus physical SQL operations.

Do not present a translation preview as proof of the exact command that executed.

For other ORMs, apply the same principle using framework-supported evidence instead of guessing.

## 13. Cross-lab navigation

Database Lab owns database depth; System Lab owns end-to-end system context.

When database exploration reaches service boundaries, request/event flow, traffic, availability, security, deployment, or system-wide failure behavior, offer `/system-lab` when installed.

When `/system-lab` reaches a database node and the learner needs schema/query/index/ORM/plan depth, return to `/db-lab`.

## 14. Delivery-completion visibility

After successful delivery, Project Forge may visibly recommend `/db-lab` while the change is fresh when the accepted diff changed database-related evidence such as entities, migrations, schema, SQL/query code, repository/persistence behavior, indexes, constraints, or transaction logic.

Prefer learner-facing wording such as:

```text
★ /db-lab changes WI-24
  This work changed database structure or behavior.
  Explore affected relationships, queries, indexes, constraints, and ORM behavior.
```

Do **not** say "rebuild the database diagram" or "refresh the model". Current evidence is part of invoking the lab.

Best-effort disposable workbench generation after delivery is allowed only when a safe development/test database is already known. Do not guess a database path, create/apply migrations, or touch Production just to generate a learning artifact. Generation failure never changes delivery state.

## 15. Tooling

Optional IDE/database extensions may improve exploration but are not workflow authority and must not become a required dependency unless the project explicitly owns that requirement.

Prefer provider/framework-native inspection plus repository evidence. The SQLite workbench is a reusable read-only learning aid; future provider/ORM adapters should preserve the same evidence, current-by-default behavior, and safety contract.
