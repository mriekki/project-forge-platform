# Project Requirements Export

`PROJECT_REQUIREMENTS.json` is the canonical portable Project Forge interchange artifact for durable product, domain, experience, roadmap, and approved cross-cutting intent.

It exists to support workflows such as replatforming the same product onto a different implementation stack without treating the source repository's framework/tool choices as product requirements.

## Authority

The JSON file is a **derived export**, not a competing source of truth.

Repository authorities continue to own their facts. In a normal generated workspace that commonly means:

```text
docs/product/PRODUCT_BRIEF.md
→ docs/work-items/<FB-...>/brief.md
→ approved requirements.md when present
```

Additional product/domain authorities may include roadmap, system-design/domain invariants, product-level design/accessibility guidance, accepted ADR consequences, and project-owned decisions.

The export must retain source paths/authority/provenance so a consumer can trace normalized facts back to their repository authorities.

## Canonical contract authority

Core owns the `/export-requirements` workflow and Human-in-the-Loop gate. Bootstrap owns the accepted portable-requirements schema and validator.

At the start of an export session, resolve the current stable Project Forge descriptor:

```text
https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json
```

Use the exact immutable `generation.bootstrap.revision` selected there. Through authorized Project Forge/GitHub access, inspect that revision's canonical:

```text
schemas/project-requirements.schema.json
tools/project_requirements.py
```

Do not maintain a competing schema in Core and do not use remembered field shapes, generated examples, or a legacy export as structural authority.

If the stable descriptor, exact Bootstrap revision, schema, or validator cannot be resolved, stop before portable-requirements approval with:

```text
PORTABLE REQUIREMENTS VALIDATION REQUIRED
```

Unavailability of canonical validation is not permission to infer a compatible shape.

## Canonical filename and state

Only this filename is canonical:

```text
PROJECT_REQUIREMENTS.json
```

The contract has no compatibility alias or alternate export filename.

State is explicit:

```text
draft
review
approved
```

Only `approved` may be consumed as replatform input.

## Portable content model

The exact JSON structure comes from the current Bootstrap schema. Within that structure, the export should represent, when present:

- project/product identity;
- problem, users/stakeholders, desired outcomes, scope/non-scope;
- product workflows/capabilities and success measures;
- Feature Briefs with source ID, title, target milestone, target disposition, authority/status/maturity, outcomes, scope/non-scope, workflows, business/domain rules, dependencies, acceptance criteria, learning objectives, and open questions;
- domain concepts and relationships;
- domain invariants, lifecycle/state semantics, and business rules;
- cross-cutting security/privacy, accessibility, reliability, performance, and data requirements;
- portable product/UX principles, responsive constraints, and interaction intent;
- roadmap milestones/sequencing facts that express product intent;
- accepted decisions whose consequences are portable;
- explicit learning intent/future ideas while preserving their non-authorizing maturity;
- exact source repository/commit and contributing artifact paths.

## Product Brief model

Project Forge generated workspaces currently use one canonical product authority:

```text
docs/product/PRODUCT_BRIEF.md
```

The export therefore uses one normalized `product` object rather than inventing a multi-Product-Brief hierarchy.

If a non-generated/adopted workspace declares a different authority model, export only what that model actually establishes. Do not manufacture a second Product Brief merely to fit Project Forge defaults.

## Work-item maturity

Preserve maturity exactly.

Typical generated-project semantics include:

```text
V1 + committed
V2 + planned
V3 + directional
```

Presence in `PROJECT_REQUIREMENTS.json` is never implementation authorization. A roadmap Feature remains roadmap/directional until separately promoted through the normal requirements/work-item process.

## Engineering Enablers

Engineering Enablers are usually implementation-specific and are not portable product requirements.

The export may retain an enabler in source traceability when it establishes a durable cross-cutting requirement, but replatforming normally re-derives stack-specific enablers rather than copying their IDs/scope.

Examples:

```text
PRESERVE: secure individual authentication is required for remote internet use
RE-DERIVE: configure ASP.NET authentication middleware

PRESERVE: database schema changes must be reproducible and controlled
RE-DERIVE: use EF Core migrations
```

## Mixed authorities

Some documents mix durable intent with implementation choices. Treat these as classification inputs rather than all-or-nothing copies.

Examples:

- a Project Blueprint may contain product/domain facts plus current technology baseline;
- a System Design may contain portable domain invariants plus React/.NET/SQLite topology;
- a UX pattern may contain portable interaction behavior plus component-library detail;
- an ADR may establish both a product/security consequence and a stack-specific mechanism.

Extract the portable fact, retain source traceability, and exclude/reconcile the mechanism.

## Exclusions

Do not export as portable requirements unless the repository explicitly makes them true product constraints:

- programming languages/frameworks/component libraries;
- ORMs, package managers, build tools, test runners;
- repository/project directory layouts;
- generated client/tooling mechanisms;
- CI implementation commands;
- current deployment host/provider bindings;
- secrets/credentials/private runtime values;
- application source code;
- work-item plans/review/delivery history;
- Git/PR/CI evidence;
- Project Forge/Core/Bootstrap baseline state.

## Validation and approval boundary

Create or refresh the derived artifact in `state: "review"`, then validate the exact file with the canonical Bootstrap validator from the exact revision resolved for the session.

Equivalent validation commands are:

```text
python tools/project_requirements.py PROJECT_REQUIREMENTS.json
python tools/project_requirements.py PROJECT_REQUIREMENTS.json --require-approved
```

The first is required before the human review/approval gate. The second is required after the bounded approval-state transition.

If review-state validation fails, repair only the derived export from existing authorities and the canonical schema, then rerun validation. Do not ask for approval until it passes.

If an older or malformed export was previously approved but does not validate now, that earlier approval does not automatically authorize a normalized replacement. Preserve the underlying source authority/maturity/provenance, produce a valid `state: "review"` artifact, and obtain a fresh human approval of that exact artifact.

## Replatform relationship

The canonical flow is:

```text
project authorities
→ /export-requirements
→ current stable Bootstrap contract resolution
→ PROJECT_REQUIREMENTS.json state=review
→ canonical Bootstrap validation PASS
→ human approval
→ PROJECT_REQUIREMENTS.json state=approved
→ canonical Bootstrap validation --require-approved PASS
→ /replatform <target-stack>
→ current Bootstrap catalog reconciliation
→ PROJECT_BOOTSTRAP.json state=review
→ human Bootstrap approval
→ deterministic generation into a new repository
```

`PROJECT_BOOTSTRAP.json` remains the generation/provenance contract for one implementation. `PROJECT_REQUIREMENTS.json` remains the portable product/domain interchange contract.

## No in-place replatforming

Replatforming creates a sibling/new implementation repository. It never rewrites the source application in place.

This preserves historical truth and allows multiple implementations of the same product intent to coexist, such as:

```text
Family Meal Planner requirements
├── React + ASP.NET Core implementation
├── Angular + Spring Boot implementation
└── Blazor + ASP.NET Core implementation
```

## Security

The export must not contain secrets, credentials, private keys, access tokens, production data, machine-local bindings, or arbitrary runtime/log transcripts.
