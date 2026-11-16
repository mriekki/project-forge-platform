---
name: system-lab
description: "Optional evidence-backed advanced system-design lab for architecture, runtime flows, APIs, failures, capacity, performance, observability, security, messaging, deployment, testing, evolution, debugging, and interview practice."
argument-hint: "[architecture|runtime|api|failure|capacity|performance|observability|security|messaging|deployment|testing|debug|changes|evolve|compare|interview|topic] [work-item]"
user-invocable: true
disable-model-invocation: true
---

# System Lab

`/system-lab` is an optional advanced learning surface built from current repository/runtime evidence. It complements `/coach`; it does not replace the engineering workflow or authorize implementation changes.

For detailed usage, model semantics, and examples, read `docs/process/SYSTEM_DESIGN_LEARNING_WORKBENCH.md` in a greenfield consumer (or canonical `core/process/SYSTEM_DESIGN_LEARNING_WORKBENCH.md`).

## 1. Core contract

- Start from the current repository and the minimum safe evidence needed for the requested lens.
- Treat the repository/runtime/configuration evidence as authoritative; generated diagrams are disposable projections, never a second source of truth.
- Re-discover evidence whenever the lab is invoked. Do not make the human remember to refresh or rebuild a diagram.
- Prefer the distributed `tools/project-forge-system-lab/system-workbench.py` when present. It always rebuilds its model from current evidence and may compare with its prior disposable snapshot.
- Never inspect Production credentials, Production data, or secret values.
- Do not change production code, configuration, infrastructure, schemas, data, or deployment state while in System Lab mode.
- Do not claim runtime behavior from static topology alone. Label evidence precisely.
- Discovered implementation defects return to the normal engineering workflow; do not silently fix them here.
- Learning is optional and never blocks delivery.

## 2. Evidence labels

Use these labels consistently:

```text
CONFIRMED BY CODE       — directly observed in source/configuration/tests
CONFIRMED BY RUNTIME    — directly observed in safe runtime/telemetry evidence
DOCUMENTED INTENT       — stated in project documentation/ADR/requirements
INFERRED                — reasonable interpretation from incomplete evidence
UNKNOWN                 — evidence is insufficient
LEARNER ASSUMPTION      — value supplied for a design/capacity exercise
```

A diagram edge is not automatically proof that a runtime call occurred. A dependency discovered from configuration/package references may still be only structural evidence.

## 3. System-design competencies

Assess independently rather than using one generic "system design level":

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

Use the common L1-L6 levels, but record evidence per competency.

## 4. Architecture lenses

Treat one system model as the basis for multiple views:

```text
STRUCTURE      components and dependencies
RUNTIME        request/event path for a scenario
API            contracts, boundaries, callers, downstreams
DATA           stateful components and data movement
SCALE          load assumptions and bottleneck questions
FAILURE        failure domains and propagation hypotheses
CONSISTENCY    places state may disagree or ordering/idempotency matters
PERFORMANCE    latency budgets, fan-out, saturation, timeout/retry behavior
OBSERVABILITY  metrics/logs/traces/SLO evidence and gaps
SECURITY       trust boundaries, authn/authz, secrets/PII exposure, abuse controls
MESSAGING      producers/consumers, delivery semantics, ordering, retries, DLQ
DEPLOYMENT     processes/containers/nodes/environments and rollout concerns
TESTING        verification boundaries and untested risk
CHANGES        architecture impact of the current/recent work item
EVOLUTION      what complexity becomes justified as constraints change
```

If evidence for a lens is absent, show the gap instead of inventing detail.

## 5. Interactive workbench

When `tools/project-forge-system-lab/system-workbench.py` exists, prefer it for a current project snapshot.

The tool is read-only and dependency-free. It:

- scans current repository evidence for application/service/frontend/library/datastore/cache/messaging/external/deployment/test signals;
- records provenance for inferred components and dependencies;
- generates a stable evidence fingerprint and current Git commit when available;
- automatically compares with the prior disposable snapshot in the selected output directory;
- accepts optional explicit model JSON for richer known architecture, scenarios, failure behavior, decisions, SLOs, and metadata;
- accepts changed-file paths so a delivered work item can be overlaid on the architecture;
- creates self-contained `index.html` plus `workbench.json`;
- supports draggable nodes, search, zoom, clickable nodes/edges, scenario highlighting, lens switching, change overlays, failure exploration, capacity calculations, latency budgets, scale/evolution prompts, design drills, and interview perturbations.

Generate into a stable per-repository temp/cache directory so the prior disposable snapshot can be used for change comparison. Do not commit generated output unless explicitly requested.

## 6. Scenario-to-architecture tracing

For a scenario such as checkout, authentication, background processing, or notification:

```text
entry point
→ participating components
→ synchronous calls
→ state reads/writes
→ asynchronous messages
→ external dependencies
→ user-visible/result state
```

Highlight only evidence-backed participants. If the sequence is inferred from topology rather than captured runtime evidence, say so.

Ask the learner to explain the path before filling gaps when that improves learning.

## 7. Prediction before reveal

For advanced learning, default to making the human predict before revealing the explanation when practical.

Examples:

```text
What fails if this dependency times out?
Which component becomes the bottleneck at 10x traffic?
Where can duplicate delivery cause damage?
Which signal would distinguish database latency from downstream latency?
What consistency guarantee does the requirement actually need?
```

Do not turn every interaction into a quiz. Explanation-first remains valid when explicitly requested.

## 8. Failure and debugging mode

Failure mode should distinguish verified behavior from topological hypotheses.

```text
symptom/failure injection
→ learner predicts impact
→ identify failure boundary
→ likely propagation
→ distinguishing telemetry/evidence
→ resilience behavior
→ user-visible effect
→ prevention/design alternatives
```

Useful perturbations include database/cache/queue/dependency unavailability, slow dependency, duplicate/delayed/out-of-order messages, retry amplification, queue backlog, regional failure, network partition, bad deployment, and traffic spikes.

For `/system-lab debug`, reveal evidence incrementally and ask what evidence the learner would inspect next. Do not implement the fix in learning mode.

## 9. Capacity and performance mode

Use explicit learner/design assumptions, not invented production numbers.

Connect:

```text
DAU / active users
requests per user
peak multiplier
read/write mix
payload size
retention
fan-out
latency/SLO target
```

with derived average/peak RPS, write RPS, bandwidth, storage growth, and latency-budget reasoning. Explain simplifying assumptions.

A scale slider or changed workload is a prompt to re-evaluate bottlenecks and complexity; it is not proof that a specific technology is required.

## 10. Distributed-systems and messaging mode

Practice:

- strong/eventual/read-after-write consistency;
- optimistic concurrency and conflict handling;
- idempotency and deduplication;
- at-least-once delivery and the limits of "exactly once" claims;
- ordering and partitioning;
- retry/backoff/DLQ behavior;
- outbox/inbox patterns;
- sagas/compensation;
- distributed locks only when justified.

Use timelines when helpful. Make the learner reason about state before and after duplicate, delayed, failed, or reordered events.

## 11. API, security, observability, testing, and deployment lenses

API:
- contract shape, validation, versioning, auth, errors, pagination, idempotency, downstream coupling.

Security:
- trust boundaries, public exposure, authentication, authorization, secret handling, PII/data classification, replay/abuse/rate limiting.

Observability:
- logs, metrics, traces, SLOs, correlation, dependency health, saturation/queue depth, evidence gaps.

Testing:
- unit/integration/contract/e2e boundaries, failure-path coverage, architecture risks not currently exercised.

Deployment:
- artifact/process/container topology, environment/config boundaries, health/readiness, scaling, rollout/rollback, region/failure-domain assumptions.

Treat missing evidence as a learning question, not a defect by itself.

## 12. Architecture evolution and counterfactuals

Use the current system as the baseline and explore changes such as:

```text
remove the cache
make a synchronous path asynchronous
increase traffic 10x/100x
move from SQLite to a server database
introduce multi-region requirements
split or recombine a service
add a queue/search/object store/CDN
tighten latency/availability/privacy requirements
```

For each evolution:

```text
problem/evidence
→ change
→ expected benefit
→ new complexity/failure modes
→ migration path
→ when NOT to do it
```

Prefer evolutionary design over cargo-cult complexity.

## 13. Tradeoff and "why not?" drills

Challenge choices with credible alternatives:

```text
Why not a monolith?
Why not microservices?
Why not Kafka/a queue?
Why not synchronous HTTP?
Why not cache this?
Why not shard now?
Why not retry here?
Why not use the existing relational database?
```

The goal is to defend the simplest design that satisfies current constraints, then adapt when constraints materially change.

## 14. Architecture decisions

When ADRs or documented decisions exist, connect diagram components/edges to them. For each major choice discuss:

```text
context
chosen decision
alternatives
tradeoffs
consequences
revisit trigger
```

Do not silently create durable ADRs in learning mode.

## 15. Change-focused learning

`/system-lab changes <work-item>` should focus on the accepted/delivered change set when evidence is available.

Show:

- added/removed/changed components and dependencies;
- affected runtime/data/message paths;
- newly introduced or materially changed failure modes;
- new security/observability/performance/testing questions;
- architecture decisions or assumptions worth explaining.

A changed file is evidence that a component was touched, not proof that its runtime behavior changed. Keep that distinction visible.

## 16. Interview mode

Make the human drive:

```text
requirements
→ constraints + scale assumptions
→ API/contracts
→ data/storage
→ high-level architecture
→ deep dive
→ bottleneck/failure analysis
→ consistency/reliability
→ security/observability
→ evolution
→ tradeoff defense
```

Perturb one material constraint at a time: 20x traffic, multi-region, strict data residency, unreliable dependency, tighter p99, zero-downtime migration, duplicate delivery, cost pressure, or new abuse threat.

Score/coach the independent system-design competencies rather than assigning one generic score.

## 17. Cross-lab navigation

System Lab owns system context; Database Lab owns schema/query/ORM/plan depth.

When a system node represents a database, explicitly offer `/db-lab` for deeper relational/query evidence. When `/db-lab` reaches system-level concerns such as service boundaries, traffic, availability, or end-to-end runtime flow, offer `/system-lab`.

Do not duplicate database internals inside System Lab or architecture reasoning inside Database Lab.

## 18. Delivery-completion visibility

After successful delivery, Project Forge may recommend the labs as optional learning while the change is fresh.

- If database-related evidence changed, make `/db-lab` or `/db-lab changes <work-item>` visibly recommended.
- If architecture/runtime/API/messaging/deployment/security/observability behavior changed, make `/system-lab` or `/system-lab changes <work-item>` visibly recommended.
- If neither is especially relevant, the labs may remain visible as available options without claiming the ticket changed them.
- Never use user-facing wording such as "rebuild the diagram" or "refresh the database model". Running a lab already means inspect current evidence and generate the current view.
- Best-effort disposable artifact generation after delivery is allowed when safe and cheap, but failure to generate a learning artifact never changes delivery state.
