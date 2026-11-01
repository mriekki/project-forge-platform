# Project Forge System Requirements

## Purpose

This document defines the **normative cross-repository requirements** for the Project Forge foundational system.

The companion [`PROJECT_FORGE_SYSTEM_DESIGN.md`](PROJECT_FORGE_SYSTEM_DESIGN.md) explains how the repositories fit together and where detailed implementation contracts live.

These requirements intentionally focus on stable system invariants. They do not encode current commit SHAs, package/catalog versions, issue status, support promotions, or detailed CLI/schema mechanics that belong to machine-readable state and owning repositories.

## Interpretation

- **MUST / MUST NOT** — required system behavior or boundary.
- **SHOULD / SHOULD NOT** — expected default; deviation requires a concrete documented reason.
- **MAY** — allowed but not required.
- **Foundational repository** — one of Core, Bootstrap, Deployment Kit, Adoption Kit, Platform, or Control Plane.
- **Consumer** — a generated or adopted software repository using Project Forge.
- **Production-class** — any environment classified by repository/system policy as Production, regardless of its literal name or physical placement.

### Normative vs current-state evidence

These requirements define intended system behavior. Live repository implementation, tests, machine-readable contracts, GitHub evidence, and registries show whether the system currently satisfies that behavior.

If implementation and a requirement disagree, the discrepancy MUST be surfaced. It MUST NOT be silently reconciled by treating implementation drift as a requirements change. Resolution requires either an implementation fix, an explicit requirements change, or a bounded documented migration state.

---

## A. Ownership and authority

### PF-SYS-001 — Single canonical owner

Every reusable Project Forge responsibility MUST have one canonical foundational owner. A sibling repository MAY orchestrate or distribute that capability, but MUST NOT silently become a second implementation authority for it.

### PF-SYS-002 — Core ownership

`project-forge-core` MUST own reusable engineering-workflow behavior, Human-in-the-Loop semantics, agents/skills/instructions/process guidance, workflow-level deployment orchestration, reusable learning behavior, portable requirements/replatform orchestration, and package-managed consumer update orchestration.

### PF-SYS-003 — Bootstrap ownership

`project-forge-bootstrap` MUST own New Project discovery, imported and portable-requirements reconciliation, catalog/support-state definitions, recipes, manifest/protocol/schema contracts, deterministic greenfield generation, and project-owned workspace/setup/scaffold shell generation.

### PF-SYS-004 — Deployment Kit ownership

`project-forge-deployment-kit` MUST own reusable deterministic deployment mechanics and deployment evidence, including placement-specific runtime, target/access, environment proof, isolation, route, persistence, binding, and scoped tear-down behavior.

### PF-SYS-005 — Adoption Kit ownership

`project-forge-adoption-kit` MUST own the existing-repository adoption product: discovery/preflight, adoption planning/apply/validation, adoption baselines, and adopted-repository update semantics.

### PF-SYS-006 — Platform ownership

`project-forge-platform` MUST own exact accepted reusable-component assembly, the public `@mriekki/project-forge` package, package release/publication mechanics, umbrella package baselines/update engine, and the public ChatGPT contract/descriptor.

### PF-SYS-007 — Control Plane ownership

`project-forge-control-plane` MUST own Builder authorization/onboarding, public GitHub request validation, GitHub App credential isolation, exact-target orchestration, and safe GitHub-first publication.

### PF-SYS-008 — Consumer ownership

A consumer MUST remain authoritative for its own product requirements, accepted decisions, application architecture/code/tests, work items, CI evidence, concrete deployment values/bindings, and implementation history.

### PF-SYS-009 — Existing conventions

For Adoption Kit consumers, existing repository engineering conventions MUST outrank Project Forge defaults unless the human explicitly chooses to replace or extend them.

---

## B. Discovery, definition, and generation

### PF-SYS-010 — Conversational discovery boundary

Product/project discovery MAY be conversational and judgment-driven, but material choices MUST be made explicit and human-approved before deterministic generation authority is established.

### PF-SYS-011 — Deterministic generation boundary

After `PROJECT_BOOTSTRAP.json` is approved, repository generation MUST be code-driven/deterministic rather than reconstructed ad hoc from conversation memory.

### PF-SYS-012 — Bootstrap authority

ChatGPT, editor agents, and the Control Plane MUST consume Bootstrap-owned protocol/catalog/schema contracts; they MUST NOT maintain an independent competing New Project methodology.

### PF-SYS-013 — Catalog honesty

Uncataloged or unproven technology/automation MAY be recommended as engineering advice, but MUST be identified as a catalog/support gap and MUST NOT be represented as supported automation.

### PF-SYS-014 — Exact package selection

Generation MUST select one exact public Project Forge package version and one named profile. Floating tags/ranges MUST NOT be generation authority.

### PF-SYS-015 — Package integrity before reusable mutation

The exact package artifact MUST be integrity-resolved and verified before reusable package-managed target mutation.

### PF-SYS-016 — Bootstrap writes project-owned state first

Bootstrap/project-owned generated content MUST be materialized before the reusable package profile is applied, so managed-path collisions can fail closed rather than silently overwrite project-owned content.

### PF-SYS-017 — Whole-profile preflight

Package-managed reusable application MUST perform a whole-profile preflight that classifies managed destinations and refuses unsafe collision/drift before apply.

### PF-SYS-018 — No silent generation fallback

Failure or unavailability of the approved GitHub-first generation path MUST NOT silently authorize local generation, ZIP reconstruction, alternate package substitution, alternate Bootstrap provenance, or another destination. A different path requires an explicit human choice.

### PF-SYS-019 — Self-contained generated consumer

A generated consumer MUST be self-contained for normal development and supported deployment behavior. Routine consumer work MUST NOT require sibling local clones or credentials for private foundational repositories.

---

## C. Provenance, packaging, and updates

### PF-SYS-020 — Exact component provenance

Platform package assembly MUST resolve reusable components from exact accepted canonical component revisions and canonical distribution descriptors.

### PF-SYS-021 — Package is delivery, not canonical implementation ownership

The public npm package MUST be treated as the consumer delivery boundary, not as a replacement canonical source for Core or Deployment Kit implementation.

### PF-SYS-022 — Platform component ledger

Current package component identity MUST be machine-resolvable from Platform-owned package metadata such as `assets/components.json`; cross-repo prose MUST NOT become a duplicate current-SHA ledger.

### PF-SYS-023 — Stable descriptor separation

The public ChatGPT descriptor MUST distinguish immutable resolved contract snapshot provenance from mutable current generation and adoption pointers.

### PF-SYS-024 — Consumer provenance layers

Generated consumers MUST preserve enough provenance to identify the approved Bootstrap generation authority, exact package artifact, package/profile identity, and component-managed baselines without unnecessarily duplicating the same version data in every layer.

### PF-SYS-025 — Package publication is separate

Merging component or Platform release-preparation work MUST NOT itself publish npm. Public package publication MUST remain a distinct exact-version/source authorization.

### PF-SYS-026 — Package release does not update consumers

Publishing a new public package MUST NOT silently mutate existing consumers. Consumer adoption of a newer reusable package MUST be a separately reviewed update action.

### PF-SYS-027 — Package-managed update boundary

A generated consumer carrying `PROJECT_FORGE_BASELINE.json` MUST use the public Project Forge package/update contract as its reusable update boundary rather than bypassing it with direct component synchronization.

### PF-SYS-028 — Baseline drift safety and Exact Managed Set

Reusable update/apply mechanics MUST detect managed local drift, deletion, retired-path conflicts, and ownership collisions and MUST fail closed unless the applicable contract explicitly resolves ownership.

After a successful package-managed apply or update, Project Forge MUST converge its owned files to the **Exact Managed Set**: every current managed path MUST match the selected package/profile, every previously managed path absent from the new distribution MUST be removed or explicitly transferred out of Project Forge ownership, and the new component baseline MUST enumerate exactly the current managed paths. Unmanaged consumer files MUST remain outside this convergence and MUST NOT be pruned merely because they are absent from the distribution.

### PF-SYS-029 — No republish of immutable npm version

If an npm version has been published, Project Forge MUST NOT attempt to replace or republish different bytes under that same version.

---

## D. Setup, readiness, scaffold, and acceptance

### PF-SYS-030 — Distinct lifecycle states

Generation, workstation setup, operational readiness/doctor, application scaffold, human workspace acceptance, deployment readiness, deployment proof, and application deployment MUST remain distinct states.

### PF-SYS-031 — Installed is not operational

A tool being installed or version-detectable MUST NOT by itself be treated as proof that the tool/runtime is operational for the required Project Forge action.

### PF-SYS-032 — Machine evidence is not human acceptance

Setup/doctor/readiness success MUST be treated as machine evidence. It MUST NOT mark a checkout human-accepted without the required human workspace acceptance.

### PF-SYS-033 — Scaffold is separate from setup

Application scaffold/source-structure mutation MUST remain a separate explicit phase from workstation/environment setup.

### PF-SYS-034 — Partial scaffold fails closed

When deterministic scaffold ownership markers show a partially materialized step, Project Forge MUST stop for review rather than guess whether replay is safe.

### PF-SYS-035 — Deferred deployment is valid state

A project MAY be development-ready while deployment binding remains explicitly deferred. Lack of a deployment target MUST NOT automatically make the development workspace invalid.

---

## E. Human authority and delivery

### PF-SYS-040 — Material requirements gate

Material scope/requirements decisions MUST remain human-controlled.

### PF-SYS-041 — Substantive plan gate

A substantive implementation plan, when warranted by the work, MUST remain a meaningful human gate rather than being inferred from unrelated prior approval.

### PF-SYS-042 — Meaningful implementation acceptance

Implementation MUST receive Reviewer/test evidence plus human meaningful-diff acceptance before final delivery/finalization proceeds.

### PF-SYS-043 — Bounded routine mechanics

Once a bounded implementation or delivery action is authorized, routine safe mechanics within that scope SHOULD proceed without ceremonial reconfirmation.

### PF-SYS-044 — Single merge/finalize gate

Normal `/deliver` flow MUST stop at one explicit final merge/finalize decision after PR/CI evidence is available. Materially changed evidence MUST reopen the relevant review gate.

### PF-SYS-045 — Merge is not Production authorization

Merge, post-merge CI, package publication, setup completion, and deployment proof MUST NOT imply Production deployment authorization.

### PF-SYS-046 — Safe delivered-branch cleanup

Post-merge cleanup MAY remove only the delivered short-lived branch when applicable evidence remains satisfied. It MUST NOT authorize unrelated branch deletion or history rewriting.

### PF-SYS-047 — No force/history rewrite by default

Normal Project Forge delivery/recovery MUST NOT force-push, rewrite accepted history, or reset unrelated work as a convenience mechanism.

---

## F. Deployment and environment safety

### PF-SYS-050 — Logical environment model

Environment purpose/role MUST be modeled separately from physical placement. Staging and Production MAY be colocated, but colocation MUST be surfaced as a shared physical failure domain.

### PF-SYS-051 — Colocation does not merge ownership

Colocated environments MUST retain separate runtime/data/evidence/authorization ownership. Staging evidence MUST NOT be treated as Production evidence merely because both run on one host.

### PF-SYS-052 — Production classification is semantic

Production policy MUST follow Production classification/role rather than relying only on one literal environment name.

### PF-SYS-053 — Readiness is not mutation authorization

Deployment readiness/isolation/proof results MUST be pre-deploy evidence only. They MUST NOT authorize application, route, persistence, migration, Production, or destructive writes.

### PF-SYS-054 — Deterministic collision/isolation evidence before real app mutation

For supported deployment paths, real application deployment MUST consume deterministic collision/isolation evidence appropriate to its placement and relevant managed footprint and MUST stop before mutation when that evidence is blocked or stale.

### PF-SYS-055 — Shared infrastructure protection

Project-scoped deploy/tear-down MUST NOT remove, take over, or broadly prune shared host infrastructure or another Project's routes/runtime/data.

### PF-SYS-056 — Scoped destructive authorization

Destructive Project/environment cleanup MUST be scoped to explicitly selected owned resources. Production/persistent-data deletion MUST require the distinct destructive authorization defined by the workflow contract.

### PF-SYS-057 — Production write authorization is distinct

Production application deployment MUST require explicit Production authorization distinct from target configuration, access repair, setup, proof, package publication, or merge authorization.

### PF-SYS-058 — Deployment implementation vs support claim

Implementation/source tests in Deployment Kit MUST NOT by themselves promote Bootstrap deployment support. Catalog support promotion MUST follow the evidence policy owned by Bootstrap.

### PF-SYS-059 — Provider support is adapter-specific

A managed/cloud provider MUST NOT be called supported merely because a Project could technically run there. Support requires the relevant implemented, cataloged, and proven adapter contract.

---

## G. Security and control-plane boundaries

### PF-SYS-060 — Private project definition stays private

Private product definitions, consumer source, secrets, and baseline detail MUST NOT be placed in public Control Plane request bodies.

### PF-SYS-061 — Request author/owner authorization

GitHub-first generation/adoption/update requests MUST validate the authorized requester and exact target ownership/capability before private target access or mutation.

### PF-SYS-062 — Short-lived scoped credentials

Control Plane access to private foundational source or private consumer targets MUST use the narrowest practical short-lived scoped credential boundary rather than exposing broad long-lived credentials to consumers.

### PF-SYS-063 — Exact target publication

Control Plane publication MUST be non-force and restricted to the validated exact target/destination; unavailable access MUST be a stop condition rather than permission to broaden scope.

### PF-SYS-064 — No foundational repo as generic consumer target

Foundational/platform repositories MUST NOT be valid generic greenfield-generation or generic consumer-update targets through the public Control Plane.

### PF-SYS-065 — Secrets are not documentation state

Secrets, private keys, one-time authentication URLs/OTPs, tokens, or passwords MUST NOT be persisted in Project Forge repository documentation, public issues, generated system-reference files, or consumer provenance ledgers.

---

## H. Existing-repository adoption

### PF-SYS-070 — Adoption is not greenfield generation

Adoption MUST preserve the distinction between installing Project Forge behavior into an existing repository and generating a new Bootstrap-owned greenfield repository.

### PF-SYS-071 — Read-only adoption discovery first

Adoption MUST perform target/preflight/engineering discovery without modifying the target before the explicit adoption apply gate.

### PF-SYS-072 — Adoption preserves existing assets by default

Adoption SHOULD preserve existing README, CI, PR templates, root instructions, branch conventions, coding standards, and test frameworks unless the human explicitly selects a change.

### PF-SYS-073 — Adoption baseline/update authority

Adopted repositories MUST use Adoption Kit's recorded adoption provenance/update boundary for Adoption-managed assets; generic Core or package sync MUST NOT silently replace that authority.

---

## I. Portable requirements and replatforming

### PF-SYS-074 — Portable requirements are derived interchange, not competing authority

`PROJECT_REQUIREMENTS.json` MUST be a derived, reviewable, stack-neutral interchange artifact with source provenance. It MUST NOT silently replace the source consumer's canonical product/domain requirement authorities.

### PF-SYS-075 — Replatform requires human-approved portable requirements

Same-product/new-stack replatforming MUST use human-approved portable requirements that are current relative to material source requirement changes before creating the target platform proposal.

### PF-SYS-076 — Replatform reconciles against current Bootstrap knowledge

A replatform target MUST be reconciled against the current Bootstrap discovery/catalog/protocol contracts rather than copying the source stack/platform choices as assumed requirements.

### PF-SYS-077 — Replatform creates a fresh target

Replatforming MUST produce a fresh approved `PROJECT_BOOTSTRAP.json` and a fresh target/sibling repository. It MUST NOT regenerate over or mutate the source repository as the normal same-product/new-stack path.

### PF-SYS-078 — Preserve product intent, not historical platform provenance

Portable requirements SHOULD preserve product/domain intent, requirement authority/maturity, and meaningful constraints while excluding source implementation/platform provenance or historical execution state unless that information is itself a genuine target requirement.

---

## J. Support, evidence, and current-state claims

### PF-SYS-080 — Evidence layers remain distinct

Project Forge MUST distinguish source implementation/tests, package assembly tests, package-delivered consumer proof, catalog support state, consumer readiness, and Production authorization. Evidence from one layer MUST NOT be silently promoted into another.

### PF-SYS-081 — Current-state claims use live evidence

Concrete claims about current package versions, component commits, catalog versions/support states, open work, CI, releases, or deployment proof MUST be verified from live owning-repository/machine-readable evidence when the claim matters to an action or decision.

### PF-SYS-082 — Historical material is subordinate

Historical migration handoffs, superseded examples, old consumer states, and retired namespace material MUST NOT override current requirements or live foundational repository evidence.

### PF-SYS-083 — Consumer example is not platform requirement

A consumer's topology, stack, product architecture, or historical workaround MUST NOT be generalized into a Project Forge system requirement without an explicit foundational design decision.

### PF-SYS-084 — Support promotion requires evidence

Bootstrap support-state promotion MUST identify and satisfy the relevant proof criteria. Plausibility, source mechanics, or one historical consumer MUST NOT substitute for required package-delivered proof.

---

## K. Cross-repository change governance

### PF-SYS-090 — Boundary changes require system review

A change that alters a foundational responsibility boundary, cross-repo interface, provenance model, Human-in-the-Loop invariant, or support-evidence rule MUST be reviewed against this requirements document.

### PF-SYS-091 — Companion system-reference update when needed

If an accepted change intentionally alters a requirement or the stable cross-repository design, the Platform system reference MUST be updated as part of the same bounded initiative or an explicitly linked companion change.

### PF-SYS-092 — Internal changes need not churn system docs

An owning repository's internal refactor/fix that preserves documented cross-repo behavior SHOULD NOT require system-reference edits merely to mirror implementation detail.

### PF-SYS-093 — No duplicated volatile ledgers

Cross-repository prose MUST NOT maintain duplicate current commit-SHA, package-version, catalog-version, issue-status, or support-status ledgers when an owning machine-readable source exists.

### PF-SYS-094 — Detailed mechanics stay with owner

The system reference SHOULD link to detailed owning-repository schemas, CLIs, workflows, distributions, and algorithms rather than copying them into Platform.

### PF-SYS-095 — Analysis starts broad, verifies narrow

For a thorough Project Forge system analysis, maintainers/agents SHOULD start from these system requirements/design documents, then verify only the relevant current-state details against live owning repositories and machine-readable evidence. The system reference MUST NOT be used as a substitute for live verification of mutable facts.

---

## L. Failure and recovery

### PF-SYS-100 — Fail closed on unsafe ambiguity

When exact provenance, ownership, target identity, managed drift, or destructive scope is materially ambiguous, Project Forge MUST stop or require explicit resolution rather than guess.

### PF-SYS-101 — Diagnose before repeating writes

When a deterministic diagnostic layer identifies the actual blocker, workflow orchestration SHOULD follow that evidence and avoid repeatedly attempting a write that cannot resolve the blocker.

### PF-SYS-102 — Upstream-first reusable defect handling

A reusable defect found in a consumer SHOULD be fixed in its canonical foundational owner. Consumer-local managed drift MAY continue only under an explicit bounded acknowledgment contract and MUST NOT be silently blessed into a new reusable baseline.

### PF-SYS-103 — Destructive recovery is separately authorized

Recovery that deletes persistent data, takes ownership of existing infrastructure, rewrites history, or performs another destructive/out-of-band action MUST require authorization appropriate to that action and MUST NOT be implied by a prior setup/deploy/delivery approval.

---

## M. Remote existing-repository adoption

### PF-SYS-110 — Deep imported-repository analysis

Imported discovery for in-place adoption MUST reconstruct material product/domain, technical, engineering, and repository-policy context from live source evidence and MUST surface material contradictions/uncertainty rather than silently resolving them.

### PF-SYS-111 — Adoption uses exact analyzed source state

An approved remote adoption MUST identify the exact analyzed target commit and MUST fail closed when the target source state changes materially before deterministic apply unless the analysis is explicitly refreshed/reconciled.

### PF-SYS-112 — AI/agentic assets require reconciliation

When an existing repository contains material AI/agentic workflow assets, adoption MUST inventory and reconcile their capabilities before installing overlapping Project Forge behavior.

### PF-SYS-113 — Single effective agentic authority

Adoption MUST NOT knowingly leave conflicting authoritative agentic workflows for the same responsibility. Hybrid coexistence MAY preserve both systems when effective responsibility/authority is explicitly partitioned.

### PF-SYS-114 — Existing AI asset retirement is explicit and traceable

Adoption MUST NOT silently remove or replace existing AI/agentic assets. Retirement/replacement MUST be human-approved, collision-guarded against the reviewed source state, and recoverable through repository history/provenance.

### PF-SYS-115 — Consumer agentic techniques do not silently redefine Project Forge

Discovery MAY identify generalizable AI/agentic techniques as Project Forge improvement candidates, but consumer techniques MUST NOT become reusable Project Forge behavior without independent review and implementation in the owning foundational repository.

### PF-SYS-116 — Adopted Projects have confirmed operational entry points

Adoption SHOULD establish a human-confirmed repository-owned operations profile for setup/build/run/validation when those operations are material, so routine Core skills can use approved Project-specific targets rather than repeatedly guessing repository commands.

### PF-SYS-117 — Operational profiles remain repository-owned and non-secret

Project-specific operations profiles MUST remain repository-owned, MUST resolve to repository-defined commands or wrappers, MUST NOT contain secrets or workstation-specific absolute paths, and MUST fail visibly when stale rather than silently substituting guessed commands.

### PF-SYS-118 — Fork directionality is explicit

For adopted forks, material upstream-tracking and contribution intent MUST be explicit. A downstream-only configuration MUST NOT grant or imply Project Forge write authority to the upstream repository.

### PF-SYS-119 — Remote adoption remains distinct from generation

GitHub-first existing-repository adoption MUST use Adoption-owned provenance/apply authority and a distinct Control Plane operation; it MUST NOT masquerade as successful greenfield generation merely to reuse `PROJECT_BOOTSTRAP.json` or `[generate-project]` semantics.

---

## Change policy

Requirement IDs are stable identifiers. Do not renumber existing requirements merely to close gaps in numbering.

A requirement may be:

- clarified without changing semantics;
- intentionally changed through reviewed system design work;
- deprecated with an explicit replacement/reference;
- supplemented with a new ID.

When a requirement changes materially, affected foundational repositories and live machine-readable contracts should be reviewed for conformance. The system requirements document is not a current-state checklist; deviations are allowed only when they are visible, bounded, and intentionally being resolved or when the requirement itself is changed.
