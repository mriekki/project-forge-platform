# Project Forge ChatGPT Contract — New Project Discovery

Supported triggers:

```text
New Project: <idea>
```

```text
New Project from: <PROJECT_INPUT.json or existing product source>
```

Both enter the same Project Forge discovery/catalog/generation protocol. Start interactive discovery or reconciliation; do not generate a repository immediately.

## Conversation behavior

Ask one material question at a time whenever practical.

For genuinely bounded decisions, prefer concise choices, including `Other / specify` and `Not sure — recommend one` when useful. Use the host's native structured choice UI when available; use a numbered or lettered text menu only as a fallback.

Make a recommendation only when current discovery evidence, live repository/catalog evidence, or a clear engineering tradeoff supports one. Mark exactly one supported choice using the host's recommendation indicator when available; otherwise append `[RECOMMENDED]` to exactly one option label. Keep a brief rationale visible. A default/preselected value may match the recommendation, but a default alone never communicates advice or human approval. If no option is clearly better, do not mark one recommended and do not use a default that implies a preference.

Keep factual values and questions where the human's own framing, reasoning, desired outcomes, workflows, success criteria, or non-goals matter genuinely open-ended unless choices later become useful as scaffolding.

Useful decision labels:

```text
CONFIRMED
RECOMMENDED
ASSUMED
OPEN DECISION
FUTURE IDEA
REPO-SUPPORTED
MODEL RECOMMENDATION
CATALOG GAP
CORE BUG
```

Do not silently turn recommendations into requirements. Record only the human's selected or confirmed answer as the operative decision.

## Core discovery

Gather only what is material to a credible V1:

- target users and problem/opportunity;
- desired V1 outcome and primary workflow;
- success criteria and explicit non-goals;
- learning/demonstration goals;
- supported development operating systems;
- approved GitHub owner/repository;
- deployment outcome/intent.

Ask conditionally when relevant about data/persistence, security/privacy, destructive actions, integrations, event/background work, environment topology, team constraints, stack preferences, and imported-source maturity.

## Work-item decomposition

Initial Feature Briefs should be capability-sized coherent slices suitable for a bounded implementation period.

Split when work represents independently valuable workflows, distinct domain concerns, or work that should reasonably be delivered in separate sessions. Do not split merely by screen, business rule, entity, CRUD step, or implementation layer. Engineering Enablers remain appropriate for foundational or cross-cutting technical work that does not independently deliver a user-valued capability.

Detailed stories and requirements may be refined later in the generated Project; generation-time work items establish useful delivery boundaries without pretending every implementation detail is already known.

## Deployment discovery — outcome first

Do not assume a second computer, home LAN, SSH, Staging, Production, or cloud account exists.

First establish the desired outcome: local development, local/demo, shareable demo, production-like learning/testing, real Production, or undecided. Then ask only the topology questions needed.

Keep environment purpose separate from placement, isolation, exposure, and concrete binding. Current placement vocabulary includes `workstation`, `remote-target`, `managed-service`, and `deferred`.

Deferred deployment is valid and must not block repository generation, local development, scaffolding, tests/CI, documentation, or learning.

Safety invariants:

- Production is never implicit/default;
- one physical host may contain multiple logical environments, but colocation never weakens Production gates;
- a failed environment never redirects to another;
- workstation deployment never silently widens loopback exposure;
- deferred deployment never triggers guessed provisioning;
- unknown/changed remote host identity blocks access;
- destructive tear-down is explicit and limited to owned Project/environment resources.

## Stack support

Define V1 before choosing technology unless imported discovery already supplies a coherent definition.

Repository-supported facts come from the live Bootstrap catalog/recipes/policies. General model knowledge may recommend uncataloged technology, but label it `CATALOG GAP` and never imply Bootstrap automation exists without live support evidence.

Before generation approval, present one coherent technical shape including project type, application technologies, persistence, testing, local development, deployment, support limitations, and why the recommendation fits.

Version selection follows live Bootstrap policy. Prefer stable/LTS-compatible choices and record exact reproducible versions rather than `latest` or ranges.

## Imported/re-baseline discovery

`New Project from:` uses source-derived facts as the starting point. Re-ask only missing material decisions, conflicts, stale assumptions, unsupported catalog claims, or facts the human wants to revisit.

`PROJECT_INPUT.json` may remain discovery evidence when supplied by the live import contract; it is not generation authority. Only the final approved `PROJECT_BOOTSTRAP.json` authorizes deterministic generation.

## Durable discovery decision log

For ChatGPT-led New Project discovery, preserve accepted material decisions and rationale in generated `docs/product/PROJECT_DECISION_LOG.md`.

The decision log may record meaningful alternatives, explicit assumptions or deferred choices, accepted catalog gaps, and recommendation context. It is explanatory Project-owned evidence, not a second requirements specification, and it does not override `PROJECT_BOOTSTRAP.json`, `PRODUCT_BRIEF.md`, or approved work-item requirements.

Before generation, include the reviewed decision log as the Bootstrap-owned `generation.projectArtifacts` entry required by the live discovery contract, with no blocking `OPEN DECISION` remaining.

## Normal lifecycle

```text
idea/imported facts
→ Project Discovery/reconciliation
→ V1 scope / non-goals
→ stack recommendation + support-state check
→ work-item decomposition
→ generation proposal
→ exact Bootstrap + @mriekki/project-forge package provenance selection
→ human approval
→ approved PROJECT_BOOTSTRAP.json
→ target repository gate
→ deterministic generation/publication
→ target default-branch CI
→ developer clone
→ /setup
→ doctor/readiness
→ human editor/workspace acceptance
→ /start-work <ID>
```

Generation, workstation setup, doctor/readiness, application scaffold, and human workspace acceptance are distinct states. Machine success is evidence, not human acceptance.

## GitHub-first generation

For ChatGPT, GitHub-first generation is preferred.

For the stable public contract, the accepted Bootstrap generation revision comes from the mutable `generation.bootstrap` object in `chatgpt/current.json`. Treat its exact `revision`, protocol version, and catalog version as one reviewed generation pin. The public descriptor intentionally does not expose the private foundational repository that supplies that revision.

Control Plane resolves the private Bootstrap source through protected configuration, checks out the exact accepted `generation.bootstrap.revision`, verifies that checkout reports the same protocol/catalog versions, and validates the private approved `PROJECT_BOOTSTRAP.json` against that exact revision before generation. Do not silently substitute a newer source revision after human approval.

Before generation confirm:

- approved target owner/repository;
- exact accepted Bootstrap revision and compatibility versions;
- exact public `@mriekki/project-forge` package version/profile required by the live Bootstrap protocol;
- `generation.project-forge.integrity` uses normal machine resolution (`registry`) unless an exact trusted SHA-512 value is already available;
- authenticated identity matches the approved target owner;
- target repository is safe for first publication.

Do not ask the human to look up, paste, or approve npm `dist.integrity`. Package/version/profile are the meaningful approval surface; Bootstrap resolves exact SHA-512 provenance before reusable mutation and records it in generated state.

Do not require `/project-forge-doctor` as a per-Project discovery or approval gate. Invitation readiness is checked by onboarding; generation independently fails closed if Project Forge Builder access to the exact target is unavailable.

If repository creation is unavailable, ask the human to create the approved private empty target and stop until it is visible. Do not substitute a ZIP, local-only generation, another target, or the retired bootstrap filename.

Human approval of the generation proposal authorizes the bounded initial Project creation after the repository gate passes. Do not add a second ceremonial approval merely to seed the manifest or invoke deterministic generation when evidence is unchanged.

## Completion condition

Discovery is ready for a generation proposal when V1 is coherent, major risks are acknowledged, development platforms and deployment intent are known, target owner/repository is approved, exact Bootstrap revision compatibility and supported `@mriekki/project-forge` package version/profile can be established, support gaps are explicit, the durable decision log has no blocking `OPEN DECISION`, and initial work items are ready for review.
