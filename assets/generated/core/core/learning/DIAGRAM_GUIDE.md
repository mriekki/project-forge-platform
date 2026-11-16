# Diagram Guide

Diagrams are learning views, not architecture authorities.

Use current repository/runtime/database evidence first. Generated diagrams are disposable projections and should normally be regenerated from current evidence when the relevant lab is invoked rather than manually maintained.

## Lightweight diagrams

Coach may use ephemeral Mermaid/text diagrams in chat for:

- architecture,
- request flow,
- sequence,
- state machine,
- ER/data relationships,
- CI/CD,
- deployment,
- concurrency,
- messaging timelines,
- failure propagation.

Only save them as durable project artifacts when explicitly requested.

## Interactive diagrams

Prefer `/db-lab` when the learning question needs schema/query/index/ORM/plan evidence. Prefer `/system-lab` when it needs architecture/runtime/API/dependency/failure/scale/observability/security/deployment evidence.

Interactive views should support learning, not merely look attractive. Useful interactions include:

- select a scenario and highlight participating nodes/edges;
- click a component/table/dependency for evidence and responsibilities;
- show query/index/plan relationships;
- show work-item change overlays;
- show failure or scale perturbations;
- link system database nodes to `/db-lab` depth;
- distinguish current evidence from inferred topology.

## Evidence provenance

Use explicit labels where ambiguity matters:

```text
CONFIRMED BY CODE
CONFIRMED BY RUNTIME
DOCUMENTED INTENT
INFERRED
UNKNOWN
LEARNER ASSUMPTION
```

A static dependency edge is not automatically proof that the call occurred at runtime. A generated ERD is not more authoritative than the physical database metadata from which it was generated.

## Learning behavior

After a diagram, ask the developer to explain the relevant flow, state, failure path, boundary, scaling concern, or tradeoff.

For advanced exercises, ask the learner to predict a failure/plan/scale consequence before revealing the overlay when useful.

Never require the human to "refresh" or "rebuild" a learning diagram as routine maintenance. Running the lab means inspect current evidence and create/show the current view.
