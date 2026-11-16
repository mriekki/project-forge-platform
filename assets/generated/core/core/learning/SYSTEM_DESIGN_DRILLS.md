# System-Design Drills

Start from the actual repository whenever possible. Use `/system-lab` when concrete architecture/runtime evidence is needed and `/coach system design` for conceptual/adaptive practice.

Ask one material question at a time. Make the developer state assumptions and drive the design. For advanced exercises, prefer prediction before reveal.

## Requirements and scope

- Identify functional versus non-functional requirements.
- Separate must-have V1 constraints from future scale assumptions.
- Ask which guarantees actually matter: latency, availability, durability, consistency, privacy, cost, recovery.
- Challenge unstated assumptions.
- Ask what is explicitly out of scope.

## Capacity and workload

Give or elicit:

```text
users / active users
requests per user
peak multiplier
read/write mix
payload size
retention
fan-out
latency target
availability target
```

Have the learner estimate average/peak RPS, bandwidth, storage growth, and likely constrained resources before revealing calculated approximations.

Perturb the workload:
- 10x traffic;
- 100x traffic;
- read-heavy becomes write-heavy;
- one tenant dominates load;
- burst traffic replaces smooth traffic.

Ask which architectural change becomes justified first and what evidence would prove it.

## Architecture and decomposition

- Explain current architecture from repository evidence.
- Identify module/service boundaries and why they exist.
- Propose a simpler architecture and defend why it is or is not sufficient.
- Compare monolith/modular monolith/services for the current constraints.
- Ask what would trigger extraction of a service rather than assuming microservices.
- Identify stateful versus stateless components.
- Identify synchronous versus asynchronous dependencies.

## API and integration

- Trace one endpoint from caller to state/dependencies.
- Design request/response/error contracts.
- Discuss versioning and compatibility.
- Decide where validation/auth/idempotency belongs.
- Reason about pagination, partial failure, timeouts, cancellation and retries.
- Ask what happens when an external dependency is slow or unavailable.

## Data and storage

- Choose between relational, document, key-value, search and object storage based on access/integrity requirements.
- Explain why the existing datastore is or is not enough.
- Identify ownership of state across components.
- Explore read replicas, partitioning/sharding and their complexity triggers.
- Route schema/query/index deep dives to `/db-lab`.

## Caching

- What resource is the cache actually protecting?
- What is the cache key and eviction/invalidation strategy?
- What happens on stale data?
- What happens when the cache disappears?
- Could caching increase inconsistency or database stampede risk?
- Why not avoid the cache until measurement justifies it?

## Messaging and asynchronous workflows

Use a timeline:

```text
state change
→ publish
→ consume
→ side effect
→ acknowledge
```

Perturb with:
- duplicate message;
- delayed message;
- reordered message;
- poison message;
- consumer crash before/after side effect;
- broker unavailable;
- growing consumer lag.

Ask where idempotency/deduplication belongs, what is durable at each step, and how retries/DLQ/compensation work.

## Consistency and distributed coordination

Practice:
- strong versus eventual consistency;
- read-after-write requirements;
- optimistic concurrency;
- lost update/conflict handling;
- saga/compensation;
- transactional outbox/inbox;
- distributed locks only when justified;
- why "exactly once" claims need careful qualification.

Ask the learner to identify which business invariant requires which guarantee rather than choosing a consistency model by habit.

## Failure and resilience

Inject one failure at a time:

```text
database unavailable
cache unavailable
message delayed/duplicated
third party times out
one service becomes 5x slower
queue backs up
region unavailable
network partition
bad deployment
traffic spike
```

Sequence:

```text
learner predicts impact
→ identify propagation path
→ identify distinguishing evidence
→ discuss timeouts/retries/bulkheads/circuit breakers/fallbacks
→ user-visible effect
→ prevention/alternative
```

Challenge retry storms and hidden coupling.

## Performance and latency

Give a latency target and component estimates. Have the learner construct the budget.

Perturb:
- one dependency doubles latency;
- fan-out increases;
- p50 is fine but p99 regresses;
- DB queries are fast but request latency is high;
- synchronous work can become background work.

Discuss tail latency, timeout budgets, parallelism, batching, queuing, caching and saturation.

## Observability

Ask:
- Which metric detects the user-visible problem?
- Which signal distinguishes application, datastore and dependency latency?
- Where should trace spans exist?
- What identifiers correlate logs/events/requests?
- Which queue/saturation metrics matter?
- What SLO/error budget expresses the requirement?
- What cannot currently be diagnosed from available telemetry?

## Security

Map trust boundaries and ask:
- Where are authentication and authorization enforced?
- Where does PII/sensitive data flow?
- How are secrets supplied without exposing values?
- Can requests/messages be replayed?
- What abuse/rate-limit controls are justified?
- Which components should not be publicly reachable?
- What changes under multi-tenant or data-residency requirements?

Missing evidence is a question first, not automatic proof of a vulnerability.

## Deployment and operations

- Explain commit → CI → artifact → environment → running process/container.
- Identify health/readiness checks.
- Explain rollout and rollback strategy.
- Identify failure domains and scaling units.
- Explore regional deployment and recovery requirements.
- Ask what configuration is deployment-specific and how secrets differ from configuration.
- Separate merge from deployment authorization.

## Testing and verification

- Map tests to components/contracts.
- Decide where unit/integration/contract/e2e tests provide useful confidence.
- Identify failure paths that require more than unit tests.
- Design a test for duplicate messaging, dependency timeout, rollout compatibility, or migration compatibility.
- Ask which architecture risks are currently untested.

Do not infer behavioral coverage from filenames alone.

## Incident/debug drills

Begin with a symptom, then reveal evidence gradually.

Examples:
- checkout p95 rises from 250 ms to 3 s;
- error rate is stable but queue lag climbs;
- database CPU is normal while request timeouts rise;
- one region reports stale reads;
- duplicate notifications appear after retries.

Make the learner choose the next evidence source and explain what each observation rules in/out.

## Architecture evolution

Start from the current/simple system. Add complexity only in response to changed requirements/evidence.

Explore:

```text
monolith → horizontally scaled app
DB-only reads → justified cache
synchronous task → background job/queue
single DB → replicas/partitioning
single region → multi-region
shared module → extracted subsystem/service
```

For every step ask:

```text
What problem forces this change?
What evidence supports it?
What does it improve?
What complexity/failure modes does it add?
How would we migrate safely?
When should we NOT do it?
```

## Counterfactual and "why not?" drills

- What if Redis disappeared?
- What if this request became asynchronous?
- What if the queue were removed?
- What if everything stayed in the relational database?
- Why not keep a modular monolith?
- Why not Kafka?
- Why not retry here?
- Why not shard now?
- Why not cache everything?
- Why not make this strongly consistent?

The goal is to defend appropriate simplicity, not maximize the number of technologies.

## Work-item change drills

After a delivered ticket, use `/system-lab changes <work-item>` when relevant.

Ask:
- Which components were touched?
- Which runtime/data/event paths may be affected?
- What new or changed failure modes deserve attention?
- Did security, observability, performance or test obligations change?
- Which claim is confirmed versus inferred?
- What architecture decision could now be defended in an interview?

Use `/db-lab changes <work-item>` for database-specific consequences.

## Interview mode

Use a familiar project domain but change requirements enough that the learner cannot simply copy the repository.

Drive:

```text
requirements
→ scale assumptions
→ API/contracts
→ data/storage
→ high-level architecture
→ deep dive
→ bottleneck/failure
→ consistency/reliability
→ security/observability
→ evolution
→ tradeoff defense
```

Then perturb one constraint:
- traffic becomes 20x;
- multi-region required;
- data residency imposed;
- third party unreliable;
- p99 under 200 ms;
- zero-downtime schema evolution required;
- messages may duplicate;
- cost must materially fall;
- abuse threat increases.

Assess independent competencies, explanation quality, credibility and adaptability rather than one generic system-design score.
