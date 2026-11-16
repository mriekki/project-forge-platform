---
name: docs
description: "Open or inspect the repository's current Project Forge project documentation site, ownership/authority map, and DB/System evidence freshness without creating a new workflow gate."
argument-hint: "[open|check|build]"
user-invocable: true
disable-model-invocation: true
---

# Project Docs

`/docs` is the front door to repository documentation. It is read-only with respect to project prose unless the human explicitly asks to edit documentation.

## Purpose

Use `/docs` to:

- open the local project documentation site;
- inspect documentation ownership/authority;
- find the correct product, architecture, engineering, operations, learning, or ADR document;
- see whether disposable System/DB evidence views are current, stale, unknown, or absent;
- keep `/db-lab` and `/system-lab` easy to discover.

Markdown remains canonical. The site is a generated local projection.

## Default behavior

When invoked without a mode:

1. Read `docs/project-forge-docs.json` when present.
2. Verify the documentation viewer exists at `tools/project-forge-docs/docs-site.py`.
3. If it exists, use the repository-local Python/runtime convention to run:

```text
python tools/project-forge-docs/docs-site.py serve --root .
```

The viewer binds to loopback only and writes disposable output under `.project-forge/`.

If the tool is unavailable, do not invent installation support. Fall back to a concise documentation map from repository Markdown and mention that the local viewer is unavailable in the current accepted baseline.

## Modes

### `/docs open`

Equivalent to the default behavior.

### `/docs check`

Do not open a browser. Inspect:

- `docs/project-forge-docs.json` validity when present;
- missing listed documents;
- ownership/authority declarations;
- current Git commit;
- System Lab cache freshness when evidence exists;
- DB Lab cache availability/freshness only when evidence supports a conclusion.

Do not treat a missing optional Project Forge-managed document as project corruption when Bootstrap generation and reusable-package application are still distinct phases.

### `/docs build`

Generate the disposable site without serving it:

```text
python tools/project-forge-docs/docs-site.py build --root . --out .project-forge/docs-site
```

This is a local derived artifact and should not normally be committed.

## Current-by-default evidence

System Lab can reconstruct architecture from repository evidence. The docs viewer may best-effort prepare the current System Lab projection when it starts and the tool is present.

Database Lab is stricter: do not guess a database path. Show an existing DB projection or hand off to `/db-lab`; automatic generation is allowed only when a safe local development/test database path is already explicit.

Never create a database, apply migrations, mutate application data, or inspect Production merely to populate documentation.

## Ownership

Respect `docs/project-forge-docs.json`:

- `project` — project-owned prose and ADRs;
- `project-forge` — reusable managed reference/process material;
- `generated-evidence` — disposable projections.

Do not silently rewrite `project` documents during `/docs` just because code changed. Surface likely documentation impact instead.

## ADR behavior

If current evidence reveals a consequential architecture choice that lacks a durable decision record, `/docs` may recommend creating an ADR from `docs/templates/ADR_TEMPLATE.md`.

Recommendation is not approval. Do not invent or accept the decision for the human.

## Output when not opening the site

Prefer a compact result such as:

```text
PROJECT DOCS

Entry: PROJECT_BRIEF.md
Product authority: docs/product/PRODUCT_BRIEF.md
Work-item authority: docs/work-items/...
Current commit: abc1234

System evidence: CURRENT / STALE / NOT GENERATED
Database evidence: CURRENT / STALE / AVAILABLE-FRESHNESS-UNKNOWN / NOT GENERATED

Useful:
- /system-lab
- /db-lab
- /code-walkthrough
- /learning-review
```

Documentation status is not a delivery gate unless an approved work item explicitly requires documentation as acceptance evidence.
