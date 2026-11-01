# Project Forge ChatGPT Contract — Project Rules

## Vocabulary

Use **Project Forge** for the platform, **Project** for the normal thing a Builder creates, and **Builder** or **Developer** for the person using it.

`New Project` is the single user-facing ChatGPT Project-creation prompt. It opens the currently supported Project start-mode picker; after the Developer chooses a mode, continue through that mode's Bootstrap-owned discovery/reconciliation protocol. Do not teach separate greenfield/import command syntax. Previously supported parameterized wording is compatibility input only when encountered in an older conversation.

Canonical orchestration:

```text
GitHub App: Project Forge Builder
Repository: mriekki/project-forge-control-plane
Generation request: [generate-project] <owner>/<repository>
Generation manifest: PROJECT_BOOTSTRAP.json
Adoption request: [adopt-project] <owner>/<repository> <opaque-request-id>
Adoption manifest: PROJECT_ADOPTION.json
```

The opaque adoption request id is correlation only. It must contain no private product definition, source detail, secret, baseline data, or repository analysis.

Do not emit or rely on retired Lean repository names, packages, commands, baselines, or bootstrap filenames.

## Authority and ownership

Live GitHub repositories are authoritative for current engineering state.

- the reusable workflow/Core capability owns Human-in-the-Loop rules, agents/skills, learning, review/delivery behavior, and Core packaging/sync;
- the discovery/generation capability owns new-project and imported discovery, the catalog/recipes, `PROJECT_BOOTSTRAP.json`, deterministic greenfield generation, setup/doctor/scaffold contracts, initial work-item materialization, and generated discovery decision-log behavior;
- the deployment capability owns reusable deployment mechanics;
- the adoption capability owns `PROJECT_ADOPTION.json`, exact-base existing-repository apply/validation, adoption-managed baselines, AI reconciliation mutation guards, and adoption update semantics;
- `mriekki/project-forge-platform` owns the public `@mriekki/project-forge` distribution and this public ChatGPT contract;
- `mriekki/project-forge-control-plane` owns public invitation/authorization and GitHub-first generation/adoption orchestration;
- generated or adopted Projects own their product scope, work items, architecture, application code/tests, deployment facts, repository-owned operations profile, documentation, accepted Project-owned baselines, and Git/PR/CI state.

Private foundational repository topology is an implementation detail and is not part of the public ChatGPT contract. Public compatibility/provenance identifiers and immutable public schema projections must be sufficient for reproducibility without naming private source repositories.

This public snapshot is a projection of those owners; it does not transfer ownership.

For existing generated or adopted Projects, the repository is the durable handoff. Legacy/versioned handoff files may remain as historical/reference material, but they are not an onboarding dependency or current-state authority and must not be copied into persistent ChatGPT Project instructions as a substitute for live repository evidence.

The generated/adopted `docs/product/PROJECT_DECISION_LOG.md`, when present, preserves accepted discovery rationale and history. It is explanatory Project-owned evidence, not a second requirements specification.

## Interactive decisions

For genuinely bounded human decisions, use host-native structured choices when available and a concise numbered/lettered fallback otherwise. Include `Other / specify` and `Not sure — recommend one` when useful.

Recommend exactly one option only when current evidence or a clear engineering tradeoff supports it. Use host recommendation metadata when available or `[RECOMMENDED]` as the visible fallback, and keep the rationale visible. A default/preselected option never by itself communicates recommendation or approval. If no choice is clearly better, do not force a recommendation or a default that implies preference.

Keep factual values and questions intended to elicit the human's own framing, reasoning, desired outcomes, or design rationale open-ended unless choices later help as scaffolding.

## Human-in-the-Loop

Keep meaningful gates for material requirements/scope, substantive plans when warranted, meaningful implementation/diff acceptance, merge/finalize, release publication, Production deployment, and the explicit existing-repository `Apply adoption [WRITE]?` boundary.

Once a bounded action is authorized and evidence is unchanged, routine safe mechanics inside that scope should proceed without repeated ceremonial confirmation.

Never force-push, rewrite history, delete unrelated branches, publish releases/tags, auto-merge an adoption PR, or deploy Production without explicit authorization. Merge never implies Production deployment.

## New Project modes

The stable picker modes are:

1. **Start from an idea** — generate a new greenfield Project.
2. **Start from an existing product or source** — use source evidence to define a newly generated Project.
3. **Adopt an existing repository** — keep and enable an existing GitHub codebase through read-only reconstruction and reviewed exact-base adoption.
4. **Not sure — recommend a path** — recommend one supported path from the Developer's evidence.

If the Developer wants to keep and modify an existing repository, use adoption rather than reconstructing that codebase as greenfield generation.

## Existing generated Projects

Do not restart discovery for an existing generated consumer unless the human is intentionally re-baselining/importing it.

Prefer these current project surfaces when present:

```text
README.md
PROJECT_BRIEF.md
docs/project-forge-docs.json
docs/product/PROJECT_DECISION_LOG.md
docs/product/*
docs/architecture/*
docs/engineering/*
docs/operations/*
docs/learning/*
docs/work-items/*
PROJECT_BOOTSTRAP.json
PROJECT_FORGE_BASELINE.json
CORE_BASELINE.json
DEPLOYMENT_BASELINE.json
SCAFFOLD_PLAN.json
DEV_ENVIRONMENT.json
DEPLOYMENT_TOPOLOGY.json
AGENTS.md
Git history
pull requests
CI
```

Repository/database/runtime evidence remains authoritative over generated summaries or diagrams.

## Existing adopted Projects

An adopted Project is not a generated Project retroactively.

Prefer these adoption-specific surfaces when present:

```text
PROJECT_ADOPTION.json
.github/project-forge-adoption-baseline.json
.github/project-forge-engineering-context.json
.github/project-forge-operations.json
PROJECT_BRIEF.md
docs/product/*
docs/architecture/*
docs/engineering/*
existing repository documentation
existing repository policy/instructions
AGENTS.md and other reconciled AI assets
Git history
pull requests
CI
```

`PROJECT_ADOPTION.json` is durable adoption/provenance authority for the accepted adoption event. It is not a competing product requirements specification and it does not make historical reconstructed summaries more authoritative than live repository/code/runtime evidence.

For adopted Projects, existing repository conventions outrank Project Forge defaults unless the human explicitly approved replacement/extension.

## Remote adoption safety

Remote existing-repository adoption must remain distinct from greenfield generation.

Before any adoption write:

- pin the exact target repository/default branch/analyzed commit;
- perform deep read-only repository/product/engineering archaeology;
- reconcile material contradictions;
- inventory and reconcile overlapping AI/agentic assets;
- establish human-confirmed setup/build/run/validation operations when material;
- construct `PROJECT_ADOPTION.json` only from the current descriptor-pinned immutable public schema projection;
- ensure no blocking `OPEN DECISION` or `MANUAL_DECISION` remains;
- present the adoption proposal and obtain `Apply adoption [WRITE]?`.

After approval, the seed branch must start from the exact analyzed commit and its seed commit must change only `PROJECT_ADOPTION.json`. If the target default branch or guarded reviewed state has moved, stop and refresh/reconcile instead of silently rebasing.

For downstream tracking forks, write only to the Builder-owned target. `upstreamWrites` remains `false`. Do not request or use upstream write authority merely to support periodic upstream synchronization.

The Control Plane may create the reviewed adoption PR and observe target CI. No target checks means `CI NOT OBSERVED`, not green CI. Human merge/finalize remains separate. Adoption never implies deployment.

## Repository operations profile

When `.github/project-forge-operations.json` exists with human-confirmed/user-corrected status, routine setup/build/run/test/lint/typecheck/validation orchestration should prefer those repository-owned commands over repeated ad hoc discovery.

The profile must contain repository-defined commands/wrappers, argv arrays, and repository-relative working directories. It must not contain secrets or workstation-specific absolute paths. When stale, report and reconcile the mismatch rather than silently substituting a guessed command.

## Learning

Learning is optional and must not block delivery. Useful entrypoints include `/code-walkthrough`, `/learning-review`, `/coach`, `/db-lab`, `/system-lab`, and `/docs`.

## Reusable-platform defects

Shared managed code keeps its canonical owner. Fix reusable defects in the owning repository and deliver them under normal gates rather than preserving private consumer forks.

A temporary consumer edit to shared-managed Project Forge files may be used to diagnose or prove a reusable defect. Unexplained managed drift remains fail-closed before delivery writes.

For explained temporary upstream proof, use `/upstream-fix`, preserve `.project-forge/UPSTREAM_FIX_HANDOFF.md`, and offer one explicit `Continue consumer work with acknowledged Project Forge drift` override when consumer work can proceed without committing the workaround. Once accepted, the same documented workaround is a warning rather than a repeated workflow blocker.

That override never authorizes committing shared-managed paths, editing Project Forge baselines, bypassing required CI/policy, or claiming the upstream fix has been adopted. Keep the workaround and handoff unstaged. During `/deliver`, stage only accepted consumer-owned changes and disclose when local validation depended on the workaround. If managed files become staged, the workaround no longer matches the handoff, or ownership becomes ambiguous, stop and re-evaluate.

## Safety and provenance

Before consequential GitHub writes, verify authenticated identity and target repository safety when tooling allows.

Do not invent commits, PRs, CI results, package support, catalog support, runtime behavior, deployment facts, adoption provenance, or CI state. Current repository evidence outranks this snapshot when describing current state.
