# Optional Engineering Learning Map

Use only when useful.

Tracks:

- language/framework fundamentals,
- application architecture,
- APIs/HTTP,
- databases/SQL/ORM,
- frontend,
- testing/debugging,
- messaging/event-driven systems,
- Docker/CI/CD/operations,
- security,
- system design,
- coding/DSA,
- interview communication.

Levels:

```text
L1 Recognize
L2 Explain
L3 Trace
L4 Apply / Debug
L5 Defend / Design
L6 Interview Ready
```

## Database learning is multi-dimensional

Do not reduce database learning to one "SQL" level. When database depth matters, assess the relevant areas independently:

```text
relational modeling
keys + integrity constraints
normalization + anomalies
SQL query construction
indexes + access patterns
query plans + performance reasoning
transactions + concurrency
ORM translation
schema evolution + migrations
database debugging
design defense / interview communication
```

Use `/db-lab` for evidence-backed exploration of the current project's schema, queries, ORM translation, query plans, migrations, change impact, and query-to-ERD relationships. Invoking the lab means inspect current evidence; generated views are disposable rather than manually maintained diagrams. Use `/coach` for adaptive teaching and reinforcement.

## System-design learning is multi-dimensional

Do not reduce system design to one generic architecture score. Assess the relevant areas independently:

```text
requirements + scope framing
capacity estimation + workload modeling
API + contract design
service/module decomposition
data/storage selection
caching
messaging + asynchronous workflows
consistency + distributed coordination
scaling + partitioning
availability + fault tolerance
latency + performance
runtime/deployment topology
observability + SLO reasoning
security + abuse resistance
cost/complexity awareness
architecture evolution
incident/debug reasoning
testing/verification strategy
tradeoff defense
interview communication
```

Use `/system-lab` for evidence-backed exploration of the current project's architecture, runtime/data/event flows, dependencies, failure behavior, capacity/performance, observability, security, messaging, deployment, testing, work-item architecture impact, evolution, and interview practice. Generated interactive diagrams are disposable projections of current evidence; they are not a second architecture authority and should be regenerated from current evidence when the lab is invoked.

Use `/coach system design` for conceptual teaching, adaptive questions, and transfer practice. Prefer prediction-before-reveal for plans, failures, scale changes, consistency situations, and design perturbations when that improves learning.

## How real-code learning maps to the levels

A structured `/code-walkthrough` is especially useful for the first three levels:

```text
L1 Recognize — identify important changed files, responsibilities, and concepts
L2 Explain   — describe the functional and technical changes in own words
L3 Trace     — follow request/data/state/event flow across the implementation
```

Deeper follow-up can move into:

```text
L4 Apply / Debug   — reason through failure modes, evidence, and debugging approach
L5 Defend / Design — explain choices, alternatives, tradeoffs, and architecture
L6 Interview Ready — explain the implementation clearly under follow-up questioning
```

For database work, L4-L6 should include evidence-based reasoning about schema choices, constraints, access patterns, indexes/plans, transactions, ORM behavior, migration safety, and credible alternatives where relevant.

For system-design work, L4-L6 should include evidence-based reasoning about workload assumptions, boundaries, APIs/data flows, failure propagation, consistency, latency, scaling, reliability, observability, security, deployment, testing, cost/complexity, architecture evolution, and credible simpler alternatives.

A learner can be L5 in API design and L2 in distributed consistency, or strong in SQL construction and weak in indexing. Preserve that shape instead of averaging it away.

Use `/learning-review` to assess understanding after a walkthrough. Use `/coach` for targeted reinforcement, practice, or deeper exploration. Use `/db-lab` and `/system-lab` when concrete project evidence is the learning material. These activities are optional and do not affect engineering delivery state.

Coach should recommend only a small number of next topics based on the actual repository/work item.
