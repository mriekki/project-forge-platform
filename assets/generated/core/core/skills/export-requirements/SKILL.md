---
name: export-requirements
description: "Export the workspace's durable product, domain, UX, roadmap, and approved feature intent into canonical PROJECT_REQUIREMENTS.json without copying stack-specific implementation choices."
argument-hint: "[review|approve]"
user-invocable: true
disable-model-invocation: true
---

# Export Project Requirements

`/export-requirements` creates the portable Project Forge requirements interchange artifact:

```text
PROJECT_REQUIREMENTS.json
```

It is a derived export of the workspace's existing authorities. It is not a competing requirements database and it never outranks the source Product Brief, Feature Briefs, approved detailed requirements, accepted product/domain decisions, or other repository authorities.

## Purpose

Use this export when the same product/system intent should be carried into a new implementation, especially `/replatform`.

The export answers:

> What must remain true about the product, domain, user experience, roadmap, and accepted cross-cutting behavior independent of this implementation stack?

It must not answer:

> Which framework, language, ORM, build tool, folder layout, or CI implementation should the next repository use?

## Canonical Bootstrap contract preflight

Before constructing or refreshing `PROJECT_REQUIREMENTS.json`, resolve the current stable Project Forge descriptor from:

```text
https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json
```

Use the exact `generation.bootstrap.revision` from that descriptor as the Bootstrap contract authority for this export session. Do not use a remembered schema, an older generated example, or this skill's prose as a substitute for the current Bootstrap-owned portable-requirements contract.

The stable descriptor must provide `generation.bootstrap.portableRequirements` with public immutable locators for the canonical schema and validator. Require all of the following before continuing:

- `portableRequirements.bootstrapRevision` exactly equals `generation.bootstrap.revision`;
- `portableRequirements.schema.path` equals `schemas/project-requirements.schema.json`;
- `portableRequirements.validator.path` equals `tools/project_requirements.py`;
- both locator URLs resolve from an immutable public Platform commit rather than a mutable branch;
- both advertised SHA-256 values match the retrieved bytes.

Fetch and inspect the schema and validator through those public locators. Do not infer or expose the private foundational repository from the bare Bootstrap revision, and do not substitute similarly named files discovered through code search.

Bootstrap owns the schema/validator. Platform publishes the reviewed public immutable mirrors/locators. Core owns this orchestration. Do not copy the Bootstrap schema into Core, invent a parallel validator, or infer a compatibility transform for a shape that the canonical validator rejects.

If the stable descriptor, exact Bootstrap revision, public locator metadata, canonical schema, canonical validator, or digest verification cannot be resolved and inspected, stop with:

```text
PORTABLE REQUIREMENTS VALIDATION REQUIRED
```

Do not create an approval-ready export and do not ask for portable-requirements approval while canonical validation is unavailable.

## Source model

Start from the workspace's declared authority model. In a normal generated Project Forge workspace, inspect as applicable:

1. `docs/product/PRODUCT_BRIEF.md` as product authority;
2. `docs/product/IMPLEMENTATION_ROADMAP.md` for milestone/feature maturity and product sequencing facts;
3. Product Feature folders under `docs/work-items/`, including `brief.md` and approved `requirements.md`;
4. product/domain portions of architecture or system-design documents;
5. durable domain concepts, relationships, invariants, and business rules;
6. product-level design principles, accessibility/responsive requirements, and relevant interaction patterns;
7. accepted ADRs/decisions that constrain product/domain behavior;
8. approved cross-cutting security/privacy, reliability, performance, and data requirements;
9. learning goals/future ideas when they are explicitly part of project intent, preserving their non-authorizing status.

Treat summaries such as AI context briefs as reference/navigation unless the repository declares them authoritative.

## Preserve authority and maturity

Do not flatten roadmap maturity.

Preserve distinctions such as:

```text
V1 / committed / approved
V2 / planned / roadmap
V3 / directional / roadmap
```

A directional Feature remains directional in the export. Exporting it must not promote it into implementation scope.

## Classification

Classify source material before export.

### Preserve

Normally portable:

- product problem, goals, users, outcomes, scope/non-scope;
- Feature Brief intent and product dependencies;
- approved functional/domain requirements and acceptance criteria;
- domain concepts, relationships, invariants, lifecycle/state semantics, business rules;
- security/privacy outcomes and constraints;
- accessibility/responsive/product-experience requirements;
- product-level design principles and interaction intent;
- milestone/roadmap target and maturity;
- learning intent when explicitly part of the project.

### Reconcile

Require human review when a durable requirement is mixed with implementation detail, for example:

- API/persistence semantics expressed using a current framework;
- architecture documents containing both domain invariants and technology topology;
- ADRs that combine product consequences with stack choices;
- UX patterns containing both user behavior and component-library detail.

Preserve the durable intent and exclude/rephrase the implementation-specific mechanism.

### Exclude / re-derive

Do not export as portable requirements:

- React, Angular, Blazor, Java, C#, Spring Boot, ASP.NET Core, ORM, package-manager, or build-tool choices unless they are explicitly approved product constraints;
- source directory/project layout;
- framework/component-library implementation details;
- stack-specific Engineering Enablers;
- CI implementation commands;
- deployment scripts/bindings/credentials;
- implementation plans, code, review history, branch/PR/CI evidence;
- generated Project Forge/Core provenance.

## Canonical validation before human review

Default `/export-requirements` writes or refreshes `PROJECT_REQUIREMENTS.json` with `state: "review"` and exact source repository/commit provenance, using the current Bootstrap schema as the structural contract.

Before presenting any approval question, validate that exact file with the canonical Bootstrap validator retrieved and digest-verified from the public locator for the exact revision resolved during preflight. The equivalent canonical source-layout invocation is:

```text
python tools/project_requirements.py <path-to-PROJECT_REQUIREMENTS.json>
```

The actual local path may differ by host, but the validator bytes and Bootstrap revision must be the same canonical ones resolved and verified during preflight.

If validation fails:

1. report the validator errors;
2. repair only the derived export using existing source authorities and the canonical schema;
3. preserve source authority, maturity, provenance, open decisions, and non-authorizing roadmap intent;
4. rerun canonical validation;
5. do not ask for approval until validation passes.

Do not silently reinterpret a rejected legacy/export shape, rename fields from memory, promote unresolved decisions, or treat prior human approval of structurally different JSON as approval of a normalized replacement.

Before calling a valid export approved, present a compact reconciliation summary:

```text
PROJECT REQUIREMENTS EXPORT

Bootstrap revision: <exact revision>
Canonical validation: PASS
Preserved product/features: ...
Preserved domain rules: ...
Preserved UX/cross-cutting constraints: ...
Roadmap maturity retained: ...
Implementation-specific material excluded: ...
Items requiring reconciliation: ...
```

Then make the artifact itself the PRIMARY review subject. Before asking for approval:
1. identify `PROJECT_REQUIREMENTS.json` explicitly;
2. foreground/open the formatted JSON in the best available editor/preview surface when the host supports it;
3. keep source authorities and Bootstrap validation evidence as CONTEXT/TRACEABILITY rather than opening them all;
4. only then ask the approval question.

In VS Code, when available, use `projectForge.openReviewArtifact` with `PROJECT_REQUIREMENTS.json`. Opening the file is read-only presentation and never changes its state.

Present a gate equivalent to:

```text
HUMAN REVIEW REQUIRED

Gate: PORTABLE REQUIREMENTS APPROVAL
Primary artifact: PROJECT_REQUIREMENTS.json
Opened: formatted editor preview / <fallback surface>
Canonical Bootstrap validation: PASS @ <exact revision>
Items requiring reconciliation: NONE / list

Approve PROJECT_REQUIREMENTS.json as the portable requirements baseline?
```

Only explicit human approval may set `state: "approved"`.

`/export-requirements approve` may perform only that bounded finalization after confirming the reviewed content/evidence has not materially changed. After changing `state` to `approved`, rerun the same canonical Bootstrap validator with the equivalent of:

```text
python tools/project_requirements.py <path-to-PROJECT_REQUIREMENTS.json> --require-approved
```

If final validation fails, restore/report review state as applicable and do not claim the portable baseline is approved. If the artifact changed materially since review for any reason beyond the bounded approval-state transition, reopen the review surface and require approval again.

## Safety and scope

The skill may create/update only `PROJECT_REQUIREMENTS.json` unless the human separately authorizes source-document edits.

It must not silently rewrite source Product/Feature Briefs, requirements, architecture, ADRs, roadmap, or design documents to make export easier.

Do not export secrets, credentials, production values, personal runtime data, or machine-local bindings.
