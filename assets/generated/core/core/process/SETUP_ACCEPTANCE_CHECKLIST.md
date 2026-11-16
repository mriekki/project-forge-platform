# Setup Acceptance Checklist

Do not confuse generated files, installed tools, operational dependencies, editor/agent discovery, AI execution-surface discovery, and human acceptance.

Use this checklist after creating or adopting a Project Forge workspace and before beginning the first substantive work item.

## Workstation

- [ ] All required tools declared by the workspace environment are installed at acceptable versions.
- [ ] Required external CLIs are authenticated to the intended account when authentication is part of the workflow.
- [ ] Required local services or engines are actually running, not merely installed.
- [ ] Container tooling and Compose work when the selected stack declares containers.
- [ ] Repository-pinned runtimes are active.
- [ ] Optional tools are either available or consciously deferred.
- [ ] For browser-facing Projects, the exact Modern Web Guidance CLI/Node prerequisites are verified or explicitly deferred; telemetry is disabled without third-party agent-file overwrites.

## Ongoing tool maintenance (optional)

- [ ] `/setup status` can report known installed versions and catalog update eligibility without any write.
- [ ] `/setup update` requires an exact reviewed plan before upgrading selected tools; pinned Project dependencies and managed Project Forge profiles are excluded.

## Repository / workspace

- [ ] Git repository and remote state are understood.
- [ ] `AGENTS.md` is present and identifies the repository source-of-truth hierarchy.
- [ ] `.github/project-forge-workspace.json` is present.
- [ ] expected Project Forge agents, instructions, and skills are present.
- [ ] product/work-item source documents needed for the next work item are present.
- [ ] CI configuration is present when CI is part of the workspace contract.
- [ ] Core baseline integrity passes when `CORE_BASELINE.json` is present.

## Editor / agentic AI discovery

After opening/reloading the intended editor workspace:

- [ ] the selected AI coding assistant is signed in and usable when required.
- [ ] `Reviewer` is discoverable.
- [ ] `Coach` is discoverable when the workspace includes coaching.
- [ ] expected Project Forge skills are discoverable, including `/start-work`, `/deliver`, and `/wait-what` when included by the distribution/capability set.
- [ ] `/ux-review` is discoverable and agent-invoked `web-guidance` is available for relevant frontend work when included.
- [ ] when local `docs/work-items` folders exist, the Project Forge Work Item Status extension is installed/updated by setup and its Explorer decoration is available after any requested one-time VS Code reload; otherwise this check is not applicable.
- [ ] path-specific instructions are present when the workspace declares them.
- [ ] path-specific instructions are recognized/applied for matching files when the host supports them.
- [ ] the human controls the routine model/tier; the workspace does not silently pin or upgrade it.

The work-item Explorer decoration is an evidence-derived editor view, not a workflow authority. Its installation/readiness is reported separately from application runtime/build readiness.

## Copilot CLI + VS Code discovery

When GitHub Copilot CLI is an intended execution surface:

- [ ] `copilot` starts successfully from the repository checkout without requiring `--allow-all` or `--yolo`.
- [ ] `/user` reports the intended GitHub identity.
- [ ] `/skills list` shows the expected repository-local Project Forge skills from `.github/skills/`.
- [ ] the expected custom agents are selectable, including `Reviewer` and `Coach` when included by the distribution/capability set.
- [ ] `/ide` is connected to the intended trusted VS Code workspace when editor/CLI integration is desired.
- [ ] CLI-proposed edits can be reviewed through the configured approval flow; when VS Code diff integration is enabled, proposed file edits appear as editor diffs rather than being silently applied.
- [ ] the `Reviewer` agent exposes only the intended `read`, `search`, and `execute` tool classes and remains non-mutating in practice.
- [ ] Project Forge human gates behave the same whether the interaction starts in Copilot Chat or Copilot CLI.

Copilot CLI is an additional supported execution surface, not a separate Project Forge workflow. Normal Project Forge use must not require blanket tool approval. Autopilot/delegated execution is outside the default Project Forge delivery lifecycle unless a repository explicitly defines and accepts that behavior.

## Application stage

- [ ] application scaffold is either intentionally absent for the current stage or present as expected.
- [ ] declared restore/build/test commands succeed for the artifacts that currently exist.
- [ ] deferred scaffold-dependent checks are clearly identified rather than reported as passed.

## Smoke test

- [ ] static workspace diagnostics pass when provided.
- [ ] normal AI chat can summarize the approved product/work-item intent without inventing scope.
- [ ] a read-only challenge/review capability can be invoked without editing files.
- [ ] `/wait-what` can re-explain a prior response without changing repository state when the workspace includes it.
- [ ] the Reviewer remains review-focused when selected.
- [ ] when Copilot CLI is enabled, invoking a Project Forge skill there preserves the same scope, source-of-truth, and Human-in-the-Loop rules as the editor chat surface.

## Human acceptance

Setup is accepted only when the human confirms this checkout is usable for the next intended work item.

A successful generator, installer, static file check, tool-version probe, CLI connection, or agent/skill discovery check alone is not human acceptance.
