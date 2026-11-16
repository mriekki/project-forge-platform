---
name: replatform
description: "Create a new implementation proposal from approved PROJECT_REQUIREMENTS.json and a requested target stack without rewriting the source project in place."
argument-hint: "<target-stack-or-recipe>"
user-invocable: true
disable-model-invocation: true
---

# Replatform

`/replatform` creates a new implementation proposal for the same product/system intent using a different technology stack.

It never rewrites the source application in place.

## Required input

Use only the canonical portable export:

```text
PROJECT_REQUIREMENTS.json
```

The file must be `state: "approved"`. Do not accept alternate/legacy requirements-export filenames or infer approval from file existence.

Before consuming the export, validate it with the canonical Bootstrap portable-requirements validator resolved from the current stable Project Forge descriptor and its `generation.bootstrap.portableRequirements` metadata. Require `portableRequirements.bootstrapRevision` to equal `generation.bootstrap.revision`, fetch the canonical validator from the advertised immutable public locator, verify its advertised SHA-256, and validate the export with that exact validator using `--require-approved`.

Do not infer or expose the private foundational repository from the Bootstrap revision, and do not substitute similarly named files discovered through code search. If the public locator metadata, canonical validator, digest verification, or exact Bootstrap revision cannot be resolved, stop with `PORTABLE REQUIREMENTS VALIDATION REQUIRED`.

If canonical validation fails, stop and route back through `/export-requirements`; do not normalize, translate, alias, or repair the input inside `/replatform`.

A previously human-approved file that does not validate against the canonical portable contract is not valid replatform input until a canonical `state: "review"` export is produced and explicitly approved again.

If the export is missing or stale relative to material source-requirement changes, use `/export-requirements` first.

## Target

The invocation supplies a target stack or current Bootstrap recipe, for example:

```text
/replatform angular java
/replatform java-angular-sqlite
/replatform blazor sqlite
```

Resolve support against the current canonical Project Forge Bootstrap catalog. General model knowledge may explain an uncataloged technology, but label it `CATALOG GAP` and do not fabricate Bootstrap automation/support.

## Output boundary

The operation produces a new `PROJECT_BOOTSTRAP.json` proposal with `state: "review"` for a new target repository.

It must record derivation provenance back to the approved requirements export/source repository and identify the selected current Bootstrap catalog/protocol and Project Forge package provenance.

Do not generate application source or mutate the target repository until the normal Bootstrap manifest review/approval gate is complete.

## Reconciliation rules

Preserve from the approved requirements export:

- product problem/goals/users/outcomes;
- Product Feature intent and target maturity;
- approved functional/domain requirements and acceptance criteria;
- domain concepts, relationships, invariants, lifecycle/state semantics, and business rules;
- portable security/privacy/reliability/data constraints;
- portable design, accessibility, responsive, and interaction intent;
- roadmap maturity (`committed`, `planned`, `directional`);
- explicitly preserved learning intent.

Re-derive for the requested stack:

- Engineering Enablers;
- framework/application shell work;
- implementation architecture/topology;
- persistence/ORM implementation;
- API/client implementation choices;
- build/run/test commands and package tooling;
- stack-specific ADRs;
- CI implementation details;
- deployment mechanics that depend on the new architecture.

Do not automatically preserve source Engineering Enabler IDs. Product Feature IDs may remain traceable when the semantic Feature is unchanged; record source IDs even when the new implementation re-slices or renumbers work.

## Mandatory target reconciliation before proposal

Do not treat portable requirements as permission to silently choose implementation/deployment defaults. Before constructing the review manifest, explicitly reconcile the material target-specific choices needed by this Project.

At minimum:

1. propose the V1 Engineering Enablers required by the selected stack and approved cross-cutting requirements;
2. distinguish local development/runtime work from remote/Production readiness when both matter;
3. reconcile deployment outcome/topology using the normal Bootstrap discovery model instead of defaulting it to deferred;
4. account for approved operational success criteria such as backup/restore, public ingress, or Production availability with explicit enabler/deployment scope when they materially affect V1;
5. preserve unresolved product decisions as unresolved rather than inventing implementation policy.

A replatform proposal must not collapse materially distinct technical readiness responsibilities into one generic Engineering Enabler merely because application scaffolding is deferred.

When current Bootstrap replatform tooling requires an explicit reconciliation input, construct it only from the catalog-driven choices and human-approved decisions from this conversation. It must include a non-empty `engineeringEnablers` array and an explicit `deployment` object. Do not synthesize either from stale defaults.

If material target-specific choices remain unresolved, keep discovery/reconciliation open and do not manufacture a review-state manifest yet.

## New-repository rule

Replatforming requires a new target repository identity. The source repository is read-only evidence.

Never:

- overwrite the source repository;
- replace its `PROJECT_BOOTSTRAP.json`;
- delete or rewrite source implementation history;
- copy source application code by default;
- copy secrets, production data, credentials, machine bindings, or execution evidence.

## Bootstrap execution

Use the current canonical Bootstrap replatform tooling when available. The expected deterministic boundary is:

```text
approved + canonically valid PROJECT_REQUIREMENTS.json
+ requested current catalog recipe/stack
+ explicit reconciled Engineering Enablers
+ explicit reconciled deployment topology/outcome
+ target repository identity
→ PROJECT_BOOTSTRAP.json state=review
```

If canonical Bootstrap replatform tooling/current catalog evidence is unavailable in the current environment, stop with `REPLATFORM HANDOFF REQUIRED`. Do not invent a manifest from stale remembered catalog facts.

## Human gate

Before generation, summarize at minimum:

```text
SOURCE REQUIREMENTS
source repository/commit
portable requirements export provenance
canonical Bootstrap validation evidence

PRESERVED
product/features/domain/UX/cross-cutting intent
roadmap maturity

RE-DERIVED
stack-specific architecture and Engineering Enablers
local-development/runtime shape
deployment outcome/topology and material operational responsibilities

TARGET STACK
resolved current catalog recipe and support state

OUTPUT
PROJECT_BOOTSTRAP.json — REVIEW
```

Then make `PROJECT_BOOTSTRAP.json` the PRIMARY review subject. Before asking for Bootstrap approval:

1. identify the exact manifest path and target repository identity;
2. foreground/open the formatted manifest in the best available review/editor surface when the host supports it;
3. keep source requirements/catalog evidence as CONTEXT/TRACEABILITY rather than opening everything;
4. only then render the normal material Bootstrap manifest approval gate.

In VS Code, when available, use `projectForge.openReviewArtifact` with the exact workspace-relative `PROJECT_BOOTSTRAP.json` path. Opening the manifest is read-only presentation and never authorizes generation.

Present an explicit surface summary such as:

```text
HUMAN REVIEW REQUIRED

Gate: BOOTSTRAP MANIFEST APPROVAL
Primary artifact: PROJECT_BOOTSTRAP.json
State: REVIEW
Opened: formatted editor preview / <fallback surface>
Target: <owner/repository>
```

If the manifest changes materially after review, foreground the changed manifest and reopen approval rather than reusing stale authorization.

Approval of replatform intent or manifest review is not approval to merge, release, or deploy the resulting implementation.
