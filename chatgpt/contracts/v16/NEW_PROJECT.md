# Project Forge ChatGPT Contract — New Project Discovery

The only user-facing ChatGPT Project-creation prompt is:

```text
New Project
```

After the Developer invokes it, present the currently supported start modes with concise descriptions and guidance before beginning detailed discovery. The currently supported choices are:

1. **Start from an idea** — greenfield discovery for a new product/project.
2. **Start from an existing product or source** — use `PROJECT_INPUT.json`, approved portable requirements, existing product documentation, or another approved product source as discovery evidence for a newly generated Project.
3. **Adopt an existing repository** — keep an existing GitHub codebase, reconstruct its current product/engineering baseline read-only, reconcile Project Forge with it, and apply Project Forge through a reviewed adoption branch/PR.
4. **Not sure — recommend a path** — ask for a concise description of what the Developer has, recommend one currently supported path when evidence supports it, explain why, and wait for the Developer's selection.

When the Developer wants to keep and modify an existing GitHub repository, use **Adopt an existing repository** rather than treating the repository merely as source evidence for new generation.

Do not present a mode as runnable merely because it exists in design work, another repository, or model knowledge. A mode is eligible for the picker only when the current accepted Project Forge descriptor and immutable contract snapshot advertise that path.

Do not teach or display alternate Project-creation command syntax. If the Developer includes an idea, source, repository, or other useful context in the same message as `New Project`, retain it as discovery evidence while still using this one command surface. Previously supported parameterized wording encountered in an existing conversation is compatibility input only: normalize the supplied context into the corresponding start mode and continue without surfacing that old syntax as a choice, shortcut, or onboarding instruction.

Start interactive discovery or reconciliation after mode selection; do not generate or adopt a repository immediately.

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

For repository archaeology, also distinguish material claims as:

```text
DECLARED PRODUCT INTENT
IMPLEMENTED CURRENT STATE
ENGINEERING POLICY
HISTORICAL EVIDENCE
INFERRED
CONFLICTING
HUMAN-CONFIRMED
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

Detailed stories and requirements may be refined later in the generated or adopted Project. Existing mature capabilities in an adopted repository are inherited baseline, not a fabricated backlog of unfinished Project Forge work.

## Deployment discovery — outcome first

Do not assume a second computer, home LAN, SSH, Staging, Production, or cloud account exists.

First establish the desired outcome: local development, local/demo, shareable demo, production-like learning/testing, real Production, or undecided. Then ask only the topology questions needed.

Keep environment purpose separate from placement, isolation, exposure, and concrete binding. Current placement vocabulary includes `workstation`, `remote-target`, `managed-service`, and `deferred`.

Deferred deployment is valid and must not block repository generation/adoption, local development, tests/CI, documentation, or learning.

Safety invariants:

- Production is never implicit/default;
- one physical host may contain multiple logical environments, but colocation never weakens Production gates;
- a failed environment never redirects to another;
- workstation deployment never silently widens loopback exposure;
- deferred deployment never triggers guessed provisioning;
- unknown/changed remote host identity blocks access;
- destructive tear-down is explicit and limited to owned Project/environment resources.

## Stack support

Define V1 before choosing technology unless imported or adopted discovery already supplies a coherent definition.

Repository-supported facts come from the live Bootstrap catalog/recipes/policies. General model knowledge may recommend uncataloged technology, but label it `CATALOG GAP` and never imply Bootstrap automation exists without live support evidence.

For new generated Projects, before generation approval present one coherent technical shape including project type, application technologies, persistence, testing, local development, deployment, support limitations, and why the recommendation fits.

Version selection follows live Bootstrap policy. Prefer stable/LTS-compatible choices and record exact reproducible versions rather than `latest` or ranges.

## Imported/re-baseline discovery — newly generated Project

When the Developer selects **Start from an existing product or source**, use source-derived facts as the starting point. Re-ask only missing material decisions, conflicts, stale assumptions, unsupported catalog claims, or facts the human wants to revisit.

`PROJECT_INPUT.json` may remain discovery evidence when supplied by the live import contract; it is not generation authority. Only the final approved `PROJECT_BOOTSTRAP.json` authorizes deterministic generation.

If a GitHub repository is supplied as source evidence, establish intent early:

- if the Developer wants a **new** Project inspired by or derived from that source, remain on imported discovery;
- if the Developer wants to **keep and modify that repository/codebase**, route to **Adopt an existing repository**.

## Existing-repository adoption discovery

Remote adoption is requirements archaeology, not README summarization and not greenfield generation.

### Pin the exact analyzed repository state

Before material reconstruction, record from live GitHub evidence:

- target `owner/repository`;
- default branch;
- exact analyzed default-branch commit;
- visibility/license evidence when material;
- whether the target is a fork;
- source/upstream repository and default branch when observable;
- current target/upstream relationship;
- existing Project Forge state, if any; and
- Developer intent for upstream tracking/contribution.

All analysis and approval is relative to that exact target commit. Re-check the default branch immediately before the adoption write. If it moved, discovery is stale and must be refreshed/reconciled.

For a downstream tracking fork, Project Forge writes only to the Builder-owned target. The upstream repository is read-only evidence. `upstreamWrites` must remain `false`; do not request upstream write credentials merely to support periodic synchronization.

### Deep read-only repository archaeology

Map the repository deterministically before selective semantic synthesis. Prefer high-value evidence such as repository/package/workspace structure, manifests/dependency graphs, scripts/runtime entrypoints, routes/API surfaces, schemas/migrations/persistence code, documentation indices, CI/release/deployment workflows, tests/lint/typecheck configuration, architecture/governance instructions, AI/agentic assets, and Git history when needed to resolve material intent or staleness.

Perform semantic passes as relevant over:

1. product/users/outcomes;
2. capabilities and user workflows;
3. domain concepts, relationships, business rules, and invariants;
4. data ownership, persistence, migrations, synchronization, and destructive operations;
5. runtime architecture and process boundaries;
6. integrations/providers;
7. security, privacy, reliability, performance, accessibility, and internationalization;
8. engineering toolchain, testing, CI, release, and repository conventions;
9. AI/agentic governance/workflow assets;
10. local setup/build/run/validation operations; and
11. deployment/operations when material.

Documentation does not automatically outrank code, and code does not automatically rewrite declared product intent. Surface material contradictions as `CONFLICTING` rather than silently choosing a side.

Implementation detail must not become a product requirement merely because it exists in source.

### Reconstructed Project baseline

Distinguish:

```text
WHAT I INHERITED
```

from:

```text
WHAT I WANT TO CHANGE
```

Existing mature capabilities are the adopted Project baseline. A successful adoption may have zero open implementation work items until the Developer defines the first customization.

Prefer concise Project Forge front-door/reconstruction artifacts while preserving and referencing rich existing repository documentation rather than copying it wholesale. Existing files and conventions outrank default layout preferences.

### AI/agentic reconciliation

Inventory material agentic assets such as `AGENTS.md`, nested instructions, Copilot/Claude/Cursor/Codex/provider configuration, prompts, skills, commands, hooks, guardrails, safe-to-inspect MCP/tool configuration, AI-specific CI/policy, specialized agents, and AI usage documentation. Exclude secrets, credentials, tokens, and machine-local values.

Group material overlaps by capability and assign one reviewed disposition:

```text
PRESERVE
INTEGRATE
REPLACE_WITH_PROJECT_FORGE
RETIRE
MANUAL_DECISION
```

An approved adoption may not retain `MANUAL_DECISION`.

After reconciliation, two systems must not remain conflicting authorities for the same responsibility. Coexistence is valid when responsibility is explicitly partitioned—for example Project Forge owns lifecycle/human gates while repository-owned instructions retain coding/domain/architecture policy.

For replacement/retirement, record exact source path/hash so deterministic apply fails if the reviewed asset changed. Git history is the normal archive; do not create active legacy prompt archives that agents may continue to discover.

### Engineering context and operations profile

Discovery should produce human-confirmed engineering context and, when material, a repository-owned operations profile at:

```text
.github/project-forge-operations.json
```

Operations may define stable named targets for:

```text
setup
build
run
test
lint
typecheck
validation
```

Use repository-established commands only. Represent commands as argv arrays with repository-relative working directories. Do not include secrets, machine-specific absolute paths, or guessed framework commands.

### Resolve the accepted public adoption contract

Before producing an approved adoption proposal, use the current descriptor's `adoption` object. Treat these values as one reviewed compatibility boundary:

- `adoption.manifestFilename`;
- exact `adoption.kit.revision`;
- `adoption.kit.protocolVersion`;
- immutable public schema projections under `adoption.contract`.

The public descriptor intentionally does not expose the private foundational source repository. Do not invent Adoption fields from memory or substitute another source revision.

Build `PROJECT_ADOPTION.json` against the exact descriptor-pinned schema projection. When an operations profile is material, build it against the descriptor-pinned operations schema projection.

The approved manifest must record the exact current `generation.bootstrap.revision` as its discovery Bootstrap provenance, plus the exact target repository/default branch/analyzed commit, repository/fork relationship and upstream directionality, preservation policy, engineering context, approved operations profile when material, AI reconciliation when material, and collision-guarded Project-owned artifacts.

`PROJECT_ADOPTION.json` is adoption/provenance authority, not a competing product requirements specification.

## Adoption proposal and Apply gate

Before target mutation, present a concise adoption proposal covering:

- exact target repository/default branch/analyzed commit;
- inherited Project baseline and intended customizations/non-goals;
- repository/fork directionality;
- Project Forge capability/AI reconciliation;
- repository operations profile;
- Project-owned artifacts to add/replace and their collision guards;
- exact Bootstrap discovery revision;
- exact Adoption Kit revision/protocol;
- expected branch/PR/CI behavior.

No target mutation occurs before the explicit human gate:

```text
Apply adoption [WRITE]?
```

Once the Developer approves that bounded write and evidence is unchanged:

1. create a unique 128-bit opaque request id containing no private Project data;
2. derive the short-lived seed branch exactly as `project-forge/adopt-<opaque-request-id>`;
3. branch from the exact approved analyzed default-branch commit;
4. seed a commit that changes **only** `PROJECT_ADOPTION.json`;
5. open an empty-body Control Plane issue titled exactly:
   `[adopt-project] owner/repository <opaque-request-id>`;
6. let Control Plane resolve and verify the descriptor-pinned Adoption and Bootstrap revisions;
7. let deterministic Adoption apply run against the exact seed/base state;
8. let Control Plane commit/push the bounded adoption diff to that same branch and open the target adoption PR;
9. observe target PR checks; if none register, report `CI NOT OBSERVED` rather than claiming green CI;
10. stop at human review/merge/finalize.

Do not force-push, auto-merge the adoption PR, deploy, write upstream, or silently rebase a stale approved adoption.

If the target default branch, reviewed AI assets, guarded files, or other exact-base evidence changed after approval, stop and refresh/reconcile rather than applying stale approval.

## Durable discovery decision log

For ChatGPT-led New Project discovery, preserve accepted material decisions and rationale in `docs/product/PROJECT_DECISION_LOG.md` when that artifact is useful and collision-safe.

The decision log may record meaningful alternatives, explicit assumptions or deferred choices, accepted catalog gaps, and recommendation context. It is explanatory Project-owned evidence, not a second requirements specification.

For a generated Project, include the reviewed decision log as required by the live Bootstrap generation contract. For an adopted Project, include it only through collision-guarded Project-owned adoption artifacts when it adds value and does not overwrite richer existing authority.

## Normal generated-Project lifecycle

```text
New Project
→ choose Start from an idea / Start from an existing product or source
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

## Normal adoption lifecycle

```text
New Project
→ choose Adopt an existing repository
→ pin exact repository snapshot
→ read-only archaeology/reconciliation
→ AI/agentic reconciliation
→ operations-profile review
→ adoption proposal
→ Apply adoption [WRITE]?
→ exact manifest-only seed branch
→ [adopt-project] Control Plane request
→ deterministic exact-base Adoption apply
→ target adoption PR + CI evidence
→ human merge/finalize
→ /setup or confirmed repository operation
→ normal Project Forge work lifecycle
```

## GitHub-first generation

For ChatGPT greenfield/import-to-new generation, GitHub-first generation remains preferred.

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

Do not require `/project-forge-doctor` as a per-Project discovery or approval gate. Invitation readiness is checked by onboarding; generation/adoption independently fail closed if Project Forge Builder access to the exact target is unavailable.

If repository creation is unavailable for a newly generated Project, ask the human to create the approved private empty target and stop until it is visible. Do not substitute a ZIP, local-only generation, another target, or the retired bootstrap filename. This empty-repository requirement does not apply to adoption.

Human approval of the generation proposal authorizes the bounded initial Project creation after the repository gate passes. Do not add a second ceremonial approval merely to seed the generation manifest or invoke deterministic generation when evidence is unchanged.

## Completion conditions

Generated-Project discovery is ready for a generation proposal when V1 is coherent, major risks are acknowledged, development platforms and deployment intent are known, target owner/repository is approved, exact Bootstrap revision compatibility and supported `@mriekki/project-forge` package version/profile can be established, support gaps are explicit, the durable decision log has no blocking `OPEN DECISION`, and initial work items are ready for review.

Existing-repository adoption discovery is ready for an adoption proposal when the exact target snapshot is pinned, inherited versus desired-change scope is explicit, material contradictions are reconciled, AI/agentic authority is reconciled, repository operations are human-confirmed where material, all `PROJECT_ADOPTION.json` fields can be built from the exact public schema projection, collision guards are known, fork directionality is explicit, and no blocking `OPEN DECISION` or `MANUAL_DECISION` remains.
