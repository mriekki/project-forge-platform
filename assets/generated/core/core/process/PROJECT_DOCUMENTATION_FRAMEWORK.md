# Project Forge Project Documentation Framework

Project Forge project documentation is a small, evidence-aware engineering system rather than a pile of unrelated Markdown files.

## Goals

- Keep a short, obvious root-level front door.
- Keep Markdown as the canonical human-readable source.
- Preserve one authority for product and work-item requirements.
- Separate project-owned prose from Project Forge-managed process material and disposable generated evidence.
- Make architecture, database, operations, learning, and decision context easy to find.
- Provide a local documentation website without requiring a documentation framework dependency.
- Make stale generated views visible instead of asking developers to maintain diagrams manually.
- Keep documentation support non-blocking for normal engineering delivery.

## Canonical shape

Greenfield Projects should normally converge on:

```text
README.md
PROJECT_BRIEF.md

docs/
  index.md
  project-forge-docs.json

  product/
    PRODUCT_BRIEF.md
    IMPLEMENTATION_ROADMAP.md

  architecture/
    OVERVIEW.md
    DATA.md
    RUNTIME_FLOWS.md
    decisions/
      README.md
      ADR-*.md

  engineering/
    DEVELOPMENT.md
    TESTING.md
    DELIVERY.md

  operations/
    ENVIRONMENTS.md
    DEPLOYMENT.md
    TROUBLESHOOTING.md

  learning/
    OVERVIEW.md
    DATABASE.md
    SYSTEM_DESIGN.md

  generated/
    README.md

  project-forge/
    PROJECT_FORGE_ENGINEERING_GUIDE.md

tools/
  project-forge-docs/
    docs-site.py
```

The exact set may vary for an adopted repository, but ownership and authority rules should remain explicit.

## Root-level front doors

### `README.md`

Keep it short. It should answer:

- what the repository is;
- where to start;
- how to set up/run the project;
- where the authoritative product/work-item docs live;
- how to open project documentation;
- what the first approved work item is when applicable.

### `PROJECT_BRIEF.md`

`PROJECT_BRIEF.md` is the integrated project briefing and navigation surface. It may summarize approved product scope, stack, environments, initial work items, learning goals, and important documentation links.

It is **not** a second requirements authority. In a normal Project Forge greenfield Project:

- `docs/product/PRODUCT_BRIEF.md` remains product authority;
- approved work-item briefs/requirements remain work-item authority;
- `PROJECT_BRIEF.md` summarizes and links to those authorities.

If a repository already has a different accepted authority model, preserve it.

## Ownership classes

Each document in `docs/project-forge-docs.json` should identify one of these ownership classes.

### `project`

Project-owned material. It may be created by Bootstrap and then evolve with the application.

Examples:

- `PROJECT_BRIEF.md`
- product/architecture/engineering/operations/learning docs
- ADRs

Do not overwrite project-owned prose during Project Forge package updates merely because a newer template exists.

### `project-forge`

Reusable Project Forge-managed material whose source lives in a reusable platform repository and whose accepted bytes/provenance are controlled through the package/baseline mechanism.

Examples:

- Project Forge process guides
- `docs/project-forge/PROJECT_FORGE_ENGINEERING_GUIDE.md`
- the local documentation viewer
- reusable templates

### `generated-evidence`

Disposable projections reconstructed from current repository/database evidence.

Examples:

- System Lab workbench snapshots
- DB Lab workbench snapshots
- local documentation site output

Generated evidence is not authoritative prose and should not normally be committed. The default local cache is:

```text
.project-forge/docs-cache/
```

## Documentation manifest

`docs/project-forge-docs.json` is a small project-owned index, not a competing content store.

Recommended schema:

```json
{
  "schemaVersion": 1,
  "site": {
    "title": "Example Project",
    "entry": "PROJECT_BRIEF.md"
  },
  "documents": [
    {
      "path": "PROJECT_BRIEF.md",
      "section": "Overview",
      "type": "project-brief",
      "ownership": "project",
      "authority": "navigation"
    },
    {
      "path": "docs/product/PRODUCT_BRIEF.md",
      "section": "Product",
      "type": "product-brief",
      "ownership": "project",
      "authority": "product"
    },
    {
      "path": "docs/project-forge/PROJECT_FORGE_ENGINEERING_GUIDE.md",
      "section": "Project Forge",
      "type": "platform-guide",
      "ownership": "project-forge",
      "authority": "reference"
    }
  ]
}
```

The site renderer should tolerate missing optional documents so Bootstrap and reusable-package application can remain separate deterministic phases.

## Local documentation website

The reusable viewer is intentionally dependency-free and local-only.

Normal command:

```powershell
python .\tools\project-forge-docs\docs-site.py serve --root .
```

Build-only mode:

```powershell
python .\tools\project-forge-docs\docs-site.py build --root . --out .\.project-forge\docs-site
```

The builder protects existing data: it refuses the repository root, paths overlapping either lab cache, linked paths, and non-empty output directories without its `.project-forge-docs-site` ownership marker. Existing unmarked output from an older viewer must be inspected and moved or a new output path selected before rebuilding.

The viewer should:

- bind to loopback only;
- discover `docs/project-forge-docs.json` when present;
- fall back to safe Markdown discovery for adopted repositories;
- provide section navigation and full-text search;
- render common Markdown without external dependencies;
- render the simple `flowchart` Mermaid subset used by the Project Forge engineering guide and preserve unsupported Mermaid source visibly rather than failing;
- show document ownership/authority metadata when known;
- show the current Git commit when available;
- show DB/System Lab cache availability and freshness where evidence permits;
- never mutate project prose merely by being opened.

The HTML/site is a projection. Markdown remains canonical.

## Lab integration

Use the standard local cache paths:

```text
.project-forge/docs-cache/system/
.project-forge/docs-cache/database/
```

### System Lab

Because System Lab can reconstruct its model from repository evidence, the docs viewer may best-effort prepare the current System Lab projection when it starts and the tool is available:

```powershell
python .\tools\project-forge-system-lab\system-workbench.py export --repo . --out .\.project-forge\docs-cache\system
```

This is read-only and non-blocking.

### DB Lab

Do not guess a database path. The docs viewer may surface an existing DB Lab projection and the `/db-lab` entry point. Automatic DB Lab generation is allowed only when a safe local development/test database path is already explicit in project configuration/evidence.

Never create a database, apply migrations, mutate data, or inspect Production to make documentation look current.

## Freshness model

Generated views should report one of:

```text
CURRENT
STALE
AVAILABLE / FRESHNESS UNKNOWN
NOT GENERATED
```

For System Lab, compare its recorded repository commit/fingerprint with the current checkout when possible.

For DB Lab, freshness is evidence-dependent. Do not call a DB projection current merely because the HTML exists when no repository/schema binding proves it.

Tracked narrative docs are not automatically rewritten based on file timestamps. Instead, delivery/change analysis should identify likely documentation impact.

## Delivery-completion behavior

After engineering delivery is complete, classify documentation impact separately from delivery state.

Examples of likely impact:

- public API/contract change → architecture/API/runtime docs;
- new service/dependency/queue/cache → architecture/runtime/system evidence;
- schema/migration/query/index change → data/database evidence;
- environment/deployment change → operations docs;
- new architectural tradeoff → possible ADR;
- test strategy or developer workflow change → engineering docs.

Safe generated projections may be rebuilt automatically. Human/project-authored prose should not be silently rewritten merely because the code changed.

A useful completion surface is:

```text
DOCUMENTATION IMPACT

✓ Project brief: no material change detected
★ System evidence: changed; current projection prepared
★ Database evidence: changed; /db-lab recommended
○ ADR consideration: new synchronous external dependency introduced
```

This is informative and non-blocking.

## ADRs

Use ADRs for consequential architecture decisions that benefit from preserving context and tradeoffs.

An ADR should record:

- status;
- context;
- decision;
- alternatives considered;
- tradeoffs/consequences;
- evidence/links.

Do not create an ADR for every implementation detail. Do not silently invent a decision on the human's behalf. When delivery evidence reveals a material architectural choice without an ADR, surface the opportunity rather than auto-approving prose.

## Evidence and safety

- Never put secret values in tracked Markdown or generated site data.
- Do not infer runtime behavior from architecture prose alone.
- Label architecture claims with evidence provenance where appropriate.
- Repository and runtime/database evidence outrank stale generated diagrams.
- A generated site build failure must not invalidate otherwise successful engineering delivery.
- Production access is never required merely to render documentation.

## Relationship to learning

Project documentation is a learning surface, not just reference material.

The site should keep these entry points visible when available:

```text
/db-lab
/system-lab
/code-walkthrough
/learning-review
/coach
```

System/database diagrams remain current-by-default projections. The learner should think “open the lab,” not “maintain the diagram.”

## Relationship to Project Forge updates

Project Forge-managed files may be updated through the controlled Project Forge package/baseline path.

Project-owned docs and ADRs must be preserved unless a change explicitly owns them. Generated evidence/cache is reconstructed instead of merged.

This keeps package updates deterministic without turning documentation into a regeneration hazard.