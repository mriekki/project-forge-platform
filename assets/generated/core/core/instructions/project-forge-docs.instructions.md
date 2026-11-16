---
applyTo: "**/*.md"
---

# Project Forge Documentation Rules

Respect `.github/project-forge-workspace.json`, `docs/project-forge-docs.json` when present, and existing repository documentation.

## Authority

- Do not create Product/Feature Briefs when the profile says they are unused.
- Do not create duplicate requirement authorities.
- `PROJECT_BRIEF.md` is a project briefing/navigation surface unless the repository explicitly says otherwise; do not let it silently compete with the accepted product/work-item authority.
- Label experimental/supplemental briefs clearly.
- Do not assume a Jira Epic is a Feature Brief.
- Prefer one useful combined requirements artifact over a conveyor belt of docs when local requirements are appropriate.

## Ownership

When `docs/project-forge-docs.json` is present, preserve its ownership boundary:

- `project` — project-owned prose/decisions; update only when the current change actually owns that documentation.
- `project-forge` — reusable Project Forge-managed material; update through the controlled reusable-package/baseline path rather than hand-diverging it in consumers.
- `generated-evidence` — disposable projections reconstructed from current evidence; do not hand-edit or treat them as requirements.

ADRs are project-owned decisions. Do not create or approve an architectural decision on the human's behalf merely because implementation evidence suggests one.

## Generated views

- Markdown is canonical; the local documentation website is a projection.
- DB/System diagrams are current-by-default projections. Do not tell the developer to maintain, rebuild, or manually synchronize generated diagrams.
- Keep disposable site/lab output under `.project-forge/` or another repository-approved ignored cache path by default.
- A generated view may report `CURRENT`, `STALE`, `AVAILABLE / FRESHNESS UNKNOWN`, or `NOT GENERATED`; do not claim freshness without supporting evidence.
- Repository/runtime/database evidence outranks stale generated views.

## Change impact

When a change materially affects public contracts, architecture, persistence, deployment/environments, developer workflow, testing strategy, or an architectural tradeoff, surface the likely documentation impact. Safe generated projections may be rebuilt automatically; human/project-authored prose should not be silently rewritten merely because code changed.

Documentation follow-up is non-blocking unless the work item's acceptance criteria explicitly require documentation.

## Safety

- Keep sensitive values out of tracked Markdown, documentation manifests, and generated site data.
- Preserve evidence labels and uncertainty rather than turning inference into authoritative architecture facts.
