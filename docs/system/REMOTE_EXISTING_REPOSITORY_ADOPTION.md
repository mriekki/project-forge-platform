# Remote Existing-Repository Adoption — System Design Proposal

## Status

**Proposal for system review.**

This document defines the proposed cross-repository design for turning an existing GitHub repository into a Project Forge Project through ChatGPT without treating the existing application as greenfield-generated source.

It is intentionally a review surface before implementation. After acceptance, the stable invariants belong in `PROJECT_FORGE_SYSTEM_REQUIREMENTS.md` and `PROJECT_FORGE_SYSTEM_DESIGN.md`; detailed schemas, CLIs, analyzers, and workflows remain owned by their foundational repositories.

## Goals

The enhancement should let a Builder start from an existing GitHub repository, including a fork, and have Project Forge:

1. analyze the repository read-only and at a pinned commit;
2. reconstruct product/domain intent and current technical architecture from evidence;
3. surface contradictions and material uncertainty for human reconciliation;
4. inventory and reconcile existing AI/agentic assets with Project Forge capabilities;
5. identify useful agentic techniques that may improve Project Forge itself without silently importing them;
6. establish repository-specific setup/build/run/validation behavior during adoption so routine use does not require rediscovering commands later;
7. produce an approved deterministic adoption plan distinct from greenfield generation;
8. apply Project Forge remotely through the Control Plane on a short-lived branch and PR;
9. preserve existing repository conventions unless the Builder explicitly chooses otherwise; and
10. support downstream-only, periodically upstream-tracking forks without giving Project Forge upstream write authority.

The first high-complexity acceptance Project is intended to be a mature repository such as `mriekki/actualbudget`, but consumer-specific facts must not become platform requirements merely because that repository exercises them.

## Non-goals

This proposal does not:

- redefine existing-repository adoption as greenfield generation;
- authorize Bootstrap to overwrite populated repositories;
- make generated reverse-engineering summaries more authoritative than live repository evidence;
- import an upstream project's issue backlog as the Builder's Project Forge backlog by default;
- automatically contribute changes back to an upstream/source repository;
- automatically resolve upstream merge conflicts;
- copy every existing AI asset into Project Forge;
- make one consumer's agent framework a Project Forge standard without independent foundational review;
- change repository administration, branch protection, secrets, or Production infrastructure as part of adoption; or
- require exhaustive semantic reading of every file in a large repository when indexed evidence can establish the relevant system facts more safely and efficiently.

---

## 1. Ownership model

The user experience is one imported-discovery flow, but foundational ownership remains explicit.

| Responsibility | Owner |
| --- | --- |
| `New Project from:` conversation and imported discovery protocol | Bootstrap |
| deep repository/product/domain reconstruction | Bootstrap discovery capability |
| evidence reconciliation and material Builder questions | Bootstrap discovery capability |
| AI/agentic inventory and Project-specific reconciliation proposal | Bootstrap discovery capability, against Core/Adoption capability metadata |
| adoption collision/preflight/apply/validation | Adoption Kit |
| approved adoption manifest/schema/provenance | Adoption Kit |
| repository-specific engineering and operations profile materialization | Adoption Kit from human-approved discovery output |
| GitHub authorization and exact-target remote orchestration | Control Plane |
| reusable lifecycle skills such as `/setup`, `/build`, `/run`, `/start-work`, `/deliver` | Core |
| public compatibility projection | Platform |
| product, architecture, engineering context, accepted AI policy, application code/tests after adoption | adopted Project repository |

Bootstrap must not become the mutation owner for existing repositories. Adoption must not invent a second discovery methodology. Control Plane must not become product-definition authority.

---

## 2. User journey

```text
New Project from: <GitHub repository>
        |
        v
repository/fork classification + exact target commit
        |
        v
READ-ONLY DEEP ANALYSIS
        |
        +--> product/domain reconstruction
        +--> architecture/data/runtime/integration reconstruction
        +--> engineering/CI/release reconstruction
        +--> AI/agentic asset inventory
        +--> setup/build/run/validation discovery
        |
        v
evidence reconciliation
        |
        +--> contradictions / stale docs / unknown intent
        +--> AI capability overlap/conflict
        +--> Project Forge improvement candidates
        +--> ambiguous operational commands/targets
        |
        v
Builder review of reconstructed Project baseline
        |
        v
Builder review of AI/agentic reconciliation
        |
        v
Builder review of repository operations profile
        |
        v
approved adoption proposal
        |
        v
Apply adoption [WRITE]?
        |
        v
exact-base deterministic remote adoption
        |
        v
adoption branch + PR + CI evidence
        |
        v
human merge/finalize
        |
        v
normal Project Forge lifecycle
```

No target mutation occurs before the explicit adoption Apply gate.

---

## 3. Repository and fork classification

Discovery records at least:

- target repository identity;
- default branch;
- exact analyzed target commit;
- visibility and license evidence when relevant;
- repository shape and major package/workspace boundaries;
- existing Project Forge state, if any;
- whether the target is a GitHub fork;
- source/upstream repository identity and default branch when observable;
- current target/upstream relationship; and
- Builder intent for upstream tracking/contribution.

For a downstream-only tracking fork, the conceptual policy is:

```json
{
  "kind": "fork",
  "syncIntent": "manual-periodic",
  "contributionIntent": "downstream-only",
  "upstreamWrites": false,
  "integrationStrategy": "reviewed-merge"
}
```

Project Forge writes only to the Builder-owned target. The upstream repository is a read source. No upstream write credential or Project Forge App installation should be requested merely to support periodic upstream synchronization.

---

## 4. Deep repository analysis

Deep adoption is requirements archaeology, not README summarization.

Analysis should combine deterministic indexing with selective semantic inspection. A large monorepo should first be mapped through repository structure, manifests, package/workspace graphs, scripts, CI jobs, routes/API surfaces, database schemas/migrations, documentation indices, runtime entry points, agent instructions, and other high-value evidence before model synthesis.

Recommended semantic passes:

1. product/users/outcomes;
2. capabilities and user workflows;
3. domain concepts, relationships, business rules, and invariants;
4. data ownership, persistence, migrations, synchronization, and destructive operations;
5. runtime architecture and process boundaries;
6. integration/provider boundaries;
7. security, privacy, reliability, performance, accessibility, and internationalization;
8. engineering toolchain, testing, CI, release, and repository conventions;
9. AI/agentic governance and workflow assets;
10. local setup/build/run/validation operations; and
11. deployment/operations when material.

### Evidence classification

Material claims should distinguish at least:

```text
DECLARED PRODUCT INTENT
IMPLEMENTED CURRENT STATE
ENGINEERING POLICY
HISTORICAL EVIDENCE
INFERRED
CONFLICTING
HUMAN-CONFIRMED
```

Documentation does not automatically outrank code, and code does not automatically rewrite declared product intent. Contradictions become review questions rather than silently chosen truths.

Implementation detail must not automatically become a product requirement merely because it exists in source.

---

## 5. Reconstructed Project baseline

Adoption should distinguish:

```text
WHAT I INHERITED
```

from:

```text
WHAT I WANT TO CHANGE
```

Existing mature capabilities become the adopted Project baseline, not a fabricated backlog of unfinished Project Forge work items.

Builder customizations become future Feature Briefs or Engineering Enablers. A successful adoption may therefore have zero open implementation work items until the Builder defines the first customization.

Recommended Project-owned documentation may include:

- `PROJECT_BRIEF.md` as a Project Forge front door without replacing the existing README;
- `docs/product/PRODUCT_BRIEF.md`;
- `docs/product/CAPABILITY_BASELINE.md`;
- `docs/product/PROJECT_DECISION_LOG.md`;
- `docs/product/IMPLEMENTATION_ROADMAP.md` for fork-owned future work;
- `docs/architecture/OVERVIEW.md`;
- `docs/architecture/DATA.md`;
- `docs/architecture/RUNTIME_FLOWS.md`;
- `docs/architecture/INTEGRATIONS.md` when material;
- `docs/engineering/REPOSITORY_MAP.md`;
- `docs/engineering/VALIDATION.md`;
- `docs/engineering/UPSTREAM_SYNC.md` for tracking forks; and
- `docs/engineering/AI_ASSET_DECISIONS.md` when AI/agentic reconciliation is material.

Existing rich repository documentation should normally be referenced and preserved rather than copied wholesale.

`PROJECT_REQUIREMENTS.json` remains a derived reviewable stack-neutral interchange artifact when useful. It must not become competing authority over the adopted Project's accepted product/domain sources.

---

## 6. AI/Agentic asset reconciliation

Repositories increasingly contain substantial AI/agentic systems of their own. Adoption must not blindly layer a second competing framework on top.

### Inventory

Discovery should inventory relevant assets such as:

- `AGENTS.md` and nested agent instruction files;
- GitHub/Copilot agent definitions and instructions;
- `.agents`, `.claude`, `.cursor`, `.codex`, and similar provider/editor configuration;
- prompts, skills, commands, hooks, and guardrails;
- MCP/tool configuration that is safe to inspect;
- AI-specific CI/labeling/policy workflows;
- PR/commit/comment rules for agents;
- specialized review/domain agents; and
- AI usage policy/documentation.

Secrets, credentials, machine-local values, and private tokens remain excluded.

### Capability classification

Assets should be grouped by capability rather than reviewed as an undifferentiated file list. Useful groups include:

- repository governance;
- repository/product knowledge;
- lifecycle orchestration;
- specialized agents;
- provider/editor adapters;
- automation/guardrails;
- testing/evaluation techniques; and
- legacy/duplicative prompts.

### Dispositions

Each material capability receives one approved Project disposition:

```text
PRESERVE
INTEGRATE
REPLACE_WITH_PROJECT_FORGE
RETIRE
MANUAL_DECISION
```

`INTEGRATE` means both systems contribute without creating competing authority. For example, Project Forge may own delivery orchestration while existing repository policy owns required PR-title prefixes, PR-template behavior, issue-creation restrictions, or comment markers.

### Single effective authority

After reconciliation, two agentic systems must not remain authoritative for the same responsibility in conflicting ways.

Coexistence is valid when responsibility is partitioned, for example:

```text
Project Forge owns:
  work lifecycle
  human gates
  requirements workflow
  review/delivery orchestration

Existing repository owns:
  coding/domain rules
  architecture constraints
  repository-specific AI governance
  specialized domain/review agents
```

Conflicting duplicate lifecycle authorities must be resolved before adoption can be called reconciled.

### Retiring assets

Retirement should normally use Git history as the archive rather than moving obsolete prompts into an active `archive/` tree that agents may continue to discover.

An approved retirement records the original path, source commit/hash, disposition, and reason. Deterministic adoption may delete or replace an existing AI asset only when the exact expected source identity and human-approved disposition authorize it.

---

## 7. Agentic technique harvesting

AI/agentic analysis has a second independent output: useful techniques that may improve Project Forge itself.

Project disposition and Project Forge learning are separate axes. A technique may be retired from the adopted Project while still being a strong Project Forge improvement candidate, or preserved in the Project while being too repository-specific to generalize.

Recommended learning classification:

```text
NONE
INTERESTING
CANDIDATE_IMPROVEMENT
STRONG_CANDIDATE
```

For each candidate, analysis should capture:

- technique;
- problem it solves;
- why it appears useful;
- source evidence and exact source snapshot;
- generality versus repository specificity;
- overlap with current Project Forge behavior;
- human-gate/safety impact;
- portability across models/editors/providers;
- licensing/provenance considerations;
- recommended foundational owner; and
- recommendation such as investigate, prototype, reject, or already covered.

These findings do not silently change Project Forge. They become a separate **Project Forge Improvement Handoff** for later foundational review and normal component delivery.

The handoff is not adopted-Project product state and should not normally be committed into the consumer's permanent product documentation merely to preserve Project Forge development ideas.

Consumer repositories may teach Project Forge; they do not redefine it.

---

## 8. Repository-specific operations profile

A major adoption outcome is that the Builder should not have to repeatedly rediscover how to set up, build, run, or validate a mature repository.

Current generic Core skills may remain reusable orchestration, but adopted Projects should carry a **human-confirmed Project-owned operations profile** produced during analysis/adoption.

Proposed repository-owned artifact:

```text
.github/project-forge-operations.json
```

`.github/project-forge-engineering-context.json` remains descriptive engineering context. The operations profile is the actionable contract consumed by routine skills.

### Required operation classes

The profile should be able to describe:

- setup/restore;
- build;
- run/dev;
- test;
- lint;
- typecheck;
- focused validation targets when the repository has them; and
- optional health/readiness checks for local runtimes.

### Targeted operations

Large repositories may have multiple valid targets. The profile should expose stable target names and one reviewed default where appropriate, for example:

```text
/build web
/build server
/build desktop
/build all

/run web
/run server
/run desktop
```

The Builder should not be asked to remember framework-specific commands once adoption has established the mapping.

### Proposed shape

Conceptually:

```json
{
  "schemaVersion": 1,
  "status": "human-confirmed",
  "source": "project-forge-adoption-discovery",
  "setup": {
    "defaultTarget": "default",
    "targets": {
      "default": {
        "command": ["<executable>", "<arg>"],
        "workingDirectory": "."
      }
    }
  },
  "build": {
    "defaultTarget": "web",
    "targets": {
      "web": {
        "command": ["<executable>", "<arg>"],
        "workingDirectory": "."
      }
    }
  },
  "run": {
    "defaultTarget": "web",
    "targets": {
      "web": {
        "command": ["<executable>", "<arg>"],
        "workingDirectory": ".",
        "longRunning": true,
        "health": {
          "url": "<repository-established-local-url>"
        }
      }
    }
  }
}
```

The actual owning schema belongs to Adoption/Core design work and should avoid embedding secrets or workstation-specific absolute paths.

### Resolution rules

When a confirmed operations profile exists, `/setup`, `/build`, `/run`, and relevant validation orchestration should prefer it over ad hoc repeated command discovery.

The profile must still point to repository-owned commands/wrappers. Project Forge should not invent a build or run command solely because a framework is recognizable.

If a command becomes stale, the skill should report the profile mismatch and route to an explicit refresh/reconciliation path rather than silently substituting a guessed command.

This gives the desired balance:

```text
generic reusable Core skill
        +
Project-specific confirmed operations profile
        =
low-friction deterministic Project behavior
```

---

## 9. Adoption execution authority

Existing-repository adoption should use an Adoption-owned approved manifest rather than pretending the repository was greenfield-generated.

Proposed filename:

```text
PROJECT_ADOPTION.json
```

The exact schema is Adoption-owned, but the manifest should carry enough approved state to identify:

- accepted Adoption revision/protocol;
- discovery/Bootstrap provenance used to reconstruct the Project;
- target repository/default branch/exact analyzed base commit;
- repository/fork relationship;
- preservation policy;
- approved AI/agentic reconciliation;
- repository policy relevant to deterministic delivery;
- approved engineering context;
- approved operations profile;
- approved Project-owned artifact contents; and
- deterministic additions/replacements/retirements with collision guards.

`PROJECT_ADOPTION.json` is adoption/provenance authority, not a second product requirements specification.

After successful adoption it becomes durable historical/provenance evidence while live product/code/runtime evidence remains authoritative for current implementation state.

---

## 10. Exact analyzed snapshot

Remote adoption is valid only against the repository state that discovery analyzed and the Builder reviewed.

If the target default branch moves after approval, deterministic adoption must stop rather than silently applying stale reconstructed documentation or policies to a different repository snapshot.

The Builder may then refresh/reconcile the analysis against the new target head.

The same principle applies to material AI asset changes, operations-profile evidence, and managed-path collision state.

---

## 11. Remote Control Plane flow

A distinct public request should be used for adoption rather than overloading `[generate-project]`, because adoption and greenfield generation have different safety and provenance semantics.

Conceptually:

```text
[adopt-project] owner/repository <opaque-request-id>
```

The public request body remains empty. The opaque ID contains no source code, product definition, secret, private baseline detail, or repository analysis content.

The approved adoption manifest remains target-private.

A compatible flow is:

```text
approved target commit
→ short-lived target adoption branch
→ seed approved PROJECT_ADOPTION.json only
→ public target-only adoption request
→ author/owner/authorization validation
→ exact accepted Adoption source resolution
→ short-lived exact-target token
→ verify seed branch derives from approved base
→ verify target default branch still equals approved base
→ validate approved manifest
→ whole-plan collision/preflight
→ deterministic Project-owned artifacts + Adoption-managed assets
→ validate resulting adopted Project
→ commit/push adoption branch
→ create target PR
→ observe target PR CI when configured
→ human merge/finalize
```

Control Plane publication remains non-force and exact-target only.

If no target checks register, the result should be reported as `CI NOT OBSERVED`, not falsely called green.

---

## 12. Repository-specific delivery policy

Existing repository rules outrank generic delivery defaults unless the Builder explicitly replaces them.

Deep discovery should normalize material agent/delivery policy such as:

- commit/PR title prefixes;
- PR body/template strategy;
- whether agents may create issues;
- required comment/review markers;
- required validation commands;
- branch naming constraints; and
- other machine-enforceable delivery rules.

Normalized policy must be human-confirmed before deterministic remote delivery relies on it.

Project Forge lifecycle orchestration may remain authoritative while repository-specific policy governs how the resulting Git/PR actions are expressed.

---

## 13. Tracking-fork upstream synchronization

The existing Core `/pull-latest` fast-forward-only behavior should not be overloaded for customized forks that intentionally diverge from upstream.

A later Core capability such as `/sync-upstream` should consume the recorded repository relationship and perform a bounded, origin-only workflow:

```text
inspect configured fork/upstream relationship
→ verify clean state
→ fetch origin
→ fetch upstream read-only
→ calculate merge base/divergence
→ summarize upstream change set
→ human sync authorization
→ create origin-only sync branch
→ merge upstream default branch
→ stop on conflicts
→ run repository-defined validation from operations profile
→ push branch to origin only
→ create PR in origin only
→ observe CI
→ human merge
```

No automatic rebase, force push, history rewrite, or upstream push occurs.

For a long-lived tracking fork, retaining upstream ancestry through merge commits is generally preferable to repeatedly squashing upstream history, subject to the repository's own accepted merge policy.

For a newly selected fork with no downstream commits but a stale upstream position, discovery may recommend refreshing from upstream before adoption so the reconstructed baseline starts from the newest intended inherited state.

---

## 14. Proposed normative requirements

The following requirement concepts should be promoted into the canonical system requirements if this proposal is accepted. Final IDs/text are reviewable; numbers intentionally avoid renumbering existing requirements.

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

## 15. Proposed implementation sequence

1. **Platform system review** — accept/refine this design and promote stable invariants into the canonical system requirements/design.
2. **Adoption Kit contract** — define `PROJECT_ADOPTION.json`, exact-base preflight, project-artifact mutation semantics, AI reconciliation representation, operations-profile schema/materialization, validation, and provenance.
3. **Bootstrap imported discovery** — add deep GitHub repository archaeology, evidence reconciliation, AI/agentic analysis, operations-profile proposal, and routing to Adoption rather than greenfield generation for in-place adoption.
4. **Control Plane** — add an adoption request type and exact-target orchestration without exposing private project definition publicly.
5. **Core** — teach `/setup`, `/build`, `/run`, and validation flows to consume the confirmed operations profile; later add `/sync-upstream` for tracking forks.
6. **Platform public contract** — expose accepted Adoption compatibility/provenance and update immutable ChatGPT contract snapshots after owning capabilities are accepted.
7. **Acceptance** — prove small non-fork adoption, synthetic fork/divergence/policy-conflict cases, then exercise a mature repository such as Actual Budget.

Implementation should remain staged by canonical owner rather than landing one giant cross-repository change.

---

## 16. Acceptance scenarios

Before remote deep adoption is called supported, evidence should cover at least:

| Scenario | Expected behavior |
| --- | --- |
| mature non-fork repository | deep analysis + preserved repository + adoption PR |
| public or private fork | correct upstream provenance and explicit directionality |
| target moves after approval | exact-base gate blocks stale adoption |
| existing `AGENTS.md`/AI framework | capability inventory and human reconciliation |
| duplicate lifecycle prompt | one effective authority selected |
| useful specialized agent | preserve/integrate option available |
| retired AI asset | explicit traceability and Git-history recovery |
| useful novel AI technique | Project Forge improvement handoff without silent framework mutation |
| multiple build/run targets | stable named operations-profile targets |
| ambiguous build/run behavior | Builder reconciliation before adoption approval |
| stale operations profile later | visible stale-profile failure/refresh path, no guessed substitution |
| existing PR/commit agent policy | preserved and honored by Project Forge delivery |
| existing CI | preserved |
| no CI observed | report `CI NOT OBSERVED` |
| existing Project Forge-owned/config path | first-adoption collision stops |
| project-owned artifact collision | stops before apply unless explicitly reconciled |
| downstream-only fork | no supported operation can push to upstream |
| upstream sync conflict | stop for human resolution |
| private repository | no private product/source content leaks to public Control Plane request |

---

## 17. Design checkpoints before implementation

System review should explicitly confirm or revise these choices before detailed implementation starts:

1. `PROJECT_ADOPTION.json` is the distinct Adoption-owned deterministic authority for in-place adoption.
2. `.github/project-forge-operations.json` is the preferred Project-owned actionable setup/build/run/validation profile rather than overloading descriptive engineering context.
3. AI reconciliation is a required review stage when material existing agentic assets are present.
4. hybrid AI coexistence is supported when authority is explicitly partitioned.
5. retired AI assets use Git history/provenance as the normal archive rather than remaining discoverable in an active archive directory.
6. Project Forge technique harvesting produces a separate foundational improvement handoff, not automatic Core mutation.
7. downstream-only forks grant no upstream write authority.
8. remote adoption uses a distinct Control Plane request from greenfield generation.
9. operational targets are discovered/reviewed during adoption so `/setup`, `/build`, `/run`, and validation are low-friction immediately after adoption.

These decisions intentionally precede Bootstrap, Adoption Kit, Control Plane, or Core implementation changes.