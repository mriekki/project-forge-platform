# SQL / Database Learning and Drills

Use the actual repository and domain whenever possible. SQL syntax is only one database competency; do not let query fluency hide weak relational design, indexing, transaction, or ORM reasoning.

For evidence-backed hands-on exploration use `/db-lab`. For adaptive explanation, questioning, and reinforcement use `/coach`.

## Competencies

Assess independently using the common L1-L6 learning levels:

- relational modeling and cardinality;
- primary/foreign/candidate keys and integrity constraints;
- normalization, anomalies, and deliberate denormalization;
- query construction: joins, aggregates, GROUP BY/HAVING, subqueries/CTEs, pagination, deterministic sorting;
- indexes and access-pattern reasoning;
- query-plan interpretation and performance diagnosis;
- transactions, isolation, concurrency, and failure behavior;
- ORM translation, N+1 behavior, tracking/materialization, and abstraction leaks;
- schema evolution and migration safety;
- database debugging;
- design defense and interview communication.

## Query drill

```text
problem
→ developer writes/predicts SQL
→ correctness
→ edge cases
→ access pattern
→ indexing/query-plan follow-up
→ ORM translation when useful
→ interview-style defense when useful
```

Do not reveal the complete query immediately unless the developer asks for explanation-first teaching.

## Design drill

```text
requirements
→ entities
→ relationships/cardinality
→ keys
→ constraints
→ normalization
→ expected queries
→ indexes
→ transactions/concurrency
→ migration/evolution concerns
→ defend tradeoffs
```

Prefer practical anomaly questions over memorized normalization definitions.

## Debugging drill

```text
symptom
→ hypotheses
→ SQL + parameters
→ plan / constraints / transaction evidence
→ root cause
→ fix concept
→ prevention
```

Use provider-native plan evidence where available and distinguish candidate indexes from indexes actually selected by the planner.

## ORM drill

Trace both directions:

```text
ORM/LINQ expression → generated/captured SQL → plan → result materialization
SQL/schema constraint → ORM behavior/error → application-visible effect
```

When a framework exposes both a translation preview and actual executed commands, keep them distinct.

## Suggested interview prompts

- Model a many-to-many relationship that later needs attributes on the relationship itself.
- Explain where uniqueness, nullability, and referential-integrity rules should be enforced.
- Given three common queries, design only the indexes you can justify.
- Diagnose why a query performs a scan instead of the expected indexed search.
- Explain an N+1 problem and two credible fixes with tradeoffs.
- Design a safe migration from nullable to required data.
- Define a transaction boundary for a multi-table operation and discuss concurrency failure modes.
- Defend when a surrogate key is preferable to a natural/composite key and when it is not.
