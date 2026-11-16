# System Design Learning Workbench

Use this only when advanced system-design learning would help. It is read-only, optional, and non-blocking.

`/coach system design` teaches and assesses concepts adaptively. `/system-lab` grounds those concepts in the current repository and a disposable interactive model.

## Quick start

```text
/coach system design
/system-lab
/system-lab architecture
/system-lab runtime <scenario>
/system-lab changes <work-item>
/system-lab failure
/system-lab capacity
/system-lab performance
/system-lab observability
/system-lab security
/system-lab messaging
/system-lab deployment
/system-lab testing
/system-lab debug <symptom>
/system-lab evolve <constraint>
/system-lab compare <choice-a> <choice-b>
/system-lab interview
```

Running the lab means **inspect current evidence and show the current view**. The learner should not need to remember to refresh, rebuild, or manually maintain generated diagrams.

## What the lab teaches

Treat system design as independent competencies:

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

Use L1-L6 per competency rather than one generic system-design score.

## Current-by-default artifact lifecycle

Generated HTML/JSON is a disposable projection:

```text
current repository evidence
→ discover components/dependencies/provenance
→ merge optional explicit architecture evidence
→ calculate evidence fingerprint
→ compare prior disposable snapshot when present
→ generate current workbench
```

The workbench always regenerates when invoked. Reusing a stable temp output directory is useful because the previous `workbench.json` can act as a disposable comparison baseline before being replaced.

This avoids the stale-diagram problem without turning diagrams into tracked documentation.

## Evidence labels

Use:

```text
CONFIRMED BY CODE
CONFIRMED BY RUNTIME
DOCUMENTED INTENT
INFERRED
UNKNOWN
LEARNER ASSUMPTION
```

Static package references, config, naming, or topology can support an inference without proving a runtime call occurred. Make that visible.

## Interactive workbench

Greenfield consumers receive:

```text
tools/project-forge-system-lab/system-workbench.py
```

It uses only the Python standard library.

PowerShell:

```powershell
Set-Location D:\Projects\<repo>
$out = Join-Path $env:TEMP "project-forge-system-lab"
python .\tools\project-forge-system-lab\system-workbench.py export `
  --repo . `
  --out $out
Start-Process (Join-Path $out "index.html")
```

macOS/Linux:

```bash
cd /path/to/repo
out="${TMPDIR:-/tmp}/project-forge-system-lab"
python3 tools/project-forge-system-lab/system-workbench.py export \
  --repo . \
  --out "$out"
open "$out/index.html" 2>/dev/null || xdg-open "$out/index.html"
```

The output directory contains:

```text
index.html
workbench.json
```

The generated viewer supports:

- draggable architecture nodes;
- zoom/reset and component search;
- clickable nodes and dependency edges;
- architecture/runtime/API/data/failure/capacity/performance/observability/security/messaging/deployment/testing/changes/evolution/interview lenses;
- scenario-to-architecture highlighting;
- topological failure-blast-radius exploration with prediction-before-reveal;
- current-vs-prior snapshot change highlighting;
- work-item changed-file overlays;
- capacity estimation from learner assumptions;
- latency-budget exploration;
- scale/evolution prompts;
- tradeoff and "why not?" drills;
- interview perturbations;
- evidence/provenance detail;
- visible handoff to `/db-lab` for database internals.

## Automatic repository evidence

The scanner deliberately stays conservative. It can recognize evidence such as:

- `.csproj`, `package.json`, `pyproject.toml`, `pom.xml`, Gradle and Go module roots;
- common web/API framework signals;
- SQLite/PostgreSQL/SQL Server/MySQL persistence references;
- Redis/cache references;
- Kafka/RabbitMQ/MassTransit/Azure Service Bus/SQS-style messaging signals;
- outbound HTTP client signals;
- Dockerfiles and Compose service/dependency topology;
- common Kubernetes manifests;
- authentication/authorization signals;
- common OpenTelemetry/logging/metrics signals;
- tests near a component;
- ADR/documented-decision files.

This is evidence discovery, not a general-purpose static analyzer. Ambiguous findings stay `INFERRED` or `UNKNOWN`.

The tool must never emit secret/config values merely because it scanned a configuration file.

## Optional explicit system model

For richer learning, provide an optional JSON file:

```powershell
python .\tools\project-forge-system-lab\system-workbench.py export `
  --repo . `
  --out $out `
  --model .\docs\system-learning-model.json
```

Example:

```json
{
  "components": [
    {
      "id": "web",
      "name": "Web App",
      "kind": "frontend",
      "responsibilities": ["Collect checkout input"],
      "interfaces": ["POST /api/orders"],
      "security": ["Public browser boundary"]
    },
    {
      "id": "orders",
      "name": "Order Service",
      "kind": "service",
      "responsibilities": ["Validate and create orders"],
      "telemetry": ["request latency", "order failures"]
    },
    {
      "id": "orders-db",
      "name": "Orders DB",
      "kind": "database",
      "state": ["Orders", "OrderItems"]
    }
  ],
  "edges": [
    {
      "id": "web-orders",
      "from": "web",
      "to": "orders",
      "kind": "http",
      "protocol": "HTTPS"
    },
    {
      "id": "orders-db",
      "from": "orders",
      "to": "orders-db",
      "kind": "data",
      "protocol": "SQL"
    }
  ],
  "scenarios": [
    {
      "id": "checkout",
      "name": "User checks out",
      "components": ["web", "orders", "orders-db"],
      "edges": ["web-orders", "orders-db"],
      "steps": [
        "Browser submits order",
        "Order Service validates request",
        "Order state is persisted"
      ]
    }
  ],
  "failures": [
    {
      "id": "orders-db-down",
      "name": "Orders DB unavailable",
      "startComponent": "orders-db",
      "notes": ["Order creation cannot complete"]
    }
  ],
  "decisions": [
    {
      "title": "Keep order creation synchronous",
      "context": "Caller requires immediate validation result",
      "tradeoffs": ["simpler semantics", "downstream latency is user-visible"],
      "revisitWhen": "external dependency latency dominates the SLO"
    }
  ]
}
```

Explicit model data supplements discovered evidence. It should represent known project facts or clearly labeled design assumptions; do not use it to launder guesses into `CONFIRMED` claims.

## Work-item change overlay

When the accepted PR/work-item file list is known, pass paths repeatedly:

```powershell
python .\tools\project-forge-system-lab\system-workbench.py export `
  --repo . `
  --out $out `
  --changed-file src\Orders\OrderService.cs `
  --changed-file docker-compose.yml
```

The tool maps changed paths to discovered components and marks those components as touched. This means **the component was changed**, not that every runtime characteristic changed.

`/system-lab changes <work-item>` should combine this with actual diff/PR evidence and explain architecture implications conservatively.

## Scenario-to-architecture highlighting

A selected scenario should dim unrelated nodes and emphasize the participating nodes/edges. Beside the graph, explain the sequence and provenance.

Runtime evidence is stronger than topology inference. For example:

```text
captured distributed trace        → CONFIRMED BY RUNTIME
controller → service call in code → CONFIRMED BY CODE
package/config dependency only    → INFERRED topology
```

## Failure exploration

The viewer may compute graph reachability from a failed component to propose a **topological blast-radius hypothesis**.

The learner should predict first. Revealing the graph traversal does not prove production behavior; retries, bulkheads, caches, fallbacks, queues, timeouts, and user behavior may change the real outcome.

Use richer explicit failure metadata or safe runtime evidence when available.

## Capacity playground

The viewer accepts learner assumptions such as:

```text
DAU
requests/user/day
peak multiplier
write ratio
average payload size
retention days
```

It derives approximate:

```text
average RPS
peak RPS
peak write RPS
bandwidth
write-data growth
retained write-data footprint
```

These are teaching calculations. State simplifying assumptions and do not present them as measured production capacity.

## Latency-budget playground

Start with a learner-supplied p95/p99 target and stage estimates:

```text
network
edge/gateway
application
primary datastore
external dependency
```

Compare the total with the target and discuss parallelism, fan-out, caching, queuing, timeout budgets, tail latency, and whether work belongs on the synchronous path.

## Scale/evolution mode

The scale control is a reasoning prompt rather than an automatic technology recommender.

At each larger workload ask:

- Which observed bottleneck appears first?
- What evidence would justify another component?
- Can the current relational database continue to satisfy the workload?
- Does caching reduce the actual constrained resource?
- Is asynchronous work justified?
- What new failure modes/costs does the change introduce?
- Can the system stay simpler?

## Consistency and messaging timelines

For event-driven work, use sequence/timeline reasoning around:

```text
write state
→ publish event
→ consume event
→ duplicate/delay/reorder/failure
→ retry or compensation
```

Ask what is durable at each point, what can happen twice, what can be observed out of order, and where idempotency/deduplication belongs.

## API lens

Trace:

```text
caller
→ route/contract
→ validation/auth
→ application boundary
→ downstream dependencies
→ response/error behavior
```

Discuss versioning, pagination, idempotency, partial failure, coupling, and compatibility where relevant.

## Security lens

Overlay available evidence for:

- public/private boundaries;
- authentication;
- authorization;
- secrets/config boundaries;
- PII/data classification;
- replay/abuse/rate limits;
- dependency trust.

Missing controls are questions first, not automatic vulnerabilities.

## Observability lens

Connect architecture to operational evidence:

```text
request/event
→ trace/span boundaries
→ component metrics
→ structured logs
→ dependency health
→ saturation/queue depth
→ SLO/user impact
```

Ask which signals distinguish competing hypotheses.

## Testing lens

Map available tests to components/boundaries and ask:

- Which contracts have integration/contract coverage?
- Which failure paths are exercised?
- Where would a unit test give false confidence?
- Which architecture risk requires an end-to-end or fault-oriented test?

Do not infer behavioral coverage solely from a test filename.

## Architecture decisions and counterfactuals

Use ADRs when they exist. Otherwise keep design explorations disposable.

Good prompts:

```text
What if we removed Redis?
What if this path became asynchronous?
What if traffic increased 100x?
What if SQLite moved to PostgreSQL?
What if one dependency became unreliable?
What if p99 must be below 200 ms?
Why not keep this a monolith?
Why not use a queue?
Why not shard yet?
```

For every proposed change explain the benefit, added complexity, new failure modes, migration path, and trigger that would justify it.

## Interview mode

A strong interview loop is:

```text
requirements
→ scale assumptions
→ API/contracts
→ data model/storage
→ architecture
→ one deep dive
→ bottleneck/failure
→ consistency/reliability
→ security/observability
→ evolution
→ defense
```

Perturb constraints after the learner commits to a design. Do not let the learner reproduce the current repository verbatim when the exercise should test transfer.

## Cross-lab learning

Use System Lab for system context and Database Lab for database depth.

Examples:

```text
/system-lab runtime checkout
→ identify Orders DB
→ /db-lab trace <order query>

/db-lab plan <query>
→ database is healthy but end-to-end latency is high
→ /system-lab performance checkout
```

## Delivery-completion learning reminder

Successful engineering delivery may end with a visible optional learning section:

```text
OPTIONAL LEARNING — recommended while this change is fresh

★ /system-lab changes WI-17
  This work changed system structure or runtime behavior.
  Explore affected components, flows, dependencies, tradeoffs, and failure modes.

★ /db-lab changes WI-17
  This work changed database structure or behavior.
  Explore affected relationships, queries, indexes, constraints, and ORM behavior.

○ /code-walkthrough WI-17
  Walk through the implementation.

○ /learning-review WI-17
  Test your understanding.
```

Only mark a lab with `★` when the accepted change actually provides relevant evidence. Otherwise keep it available with `○` or omit it to stay concise.

Do not say "rebuild" or "refresh" in the learner-facing reminder. Current evidence is already part of invoking the lab.

## Best-effort automatic artifact generation after delivery

After merge + satisfactory post-merge evidence, `/deliver` may generate disposable learning workbenches automatically when the accepted change is relevant and the required local evidence is safely available.

Rules:

- write only to temp/cache output;
- never commit generated workbench output;
- never inspect Production credentials/data;
- system-workbench generation may run against the updated default-branch checkout;
- DB workbench generation requires a known safe development/test database; do not guess a database path or create/apply migrations just to generate it;
- artifact generation failure must not change `DELIVERY COMPLETE`;
- generation is not evidence that the human learned or reviewed anything.

## Safety and fallbacks

If the interactive tool is unavailable, use ephemeral Mermaid/text diagrams and the same evidence labels.

If repository evidence is insufficient, say what is unknown and convert the gap into a design question.

Never use System Lab to perform production deployment, mutate infrastructure, change data, apply migrations, run destructive fault injection, or silently fix discovered defects.
