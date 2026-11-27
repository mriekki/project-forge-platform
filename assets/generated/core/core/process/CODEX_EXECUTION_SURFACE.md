# Codex in Project Forge workspaces

Project Forge keeps **one canonical workflow** across ChatGPT, GitHub Copilot, and the native OpenAI Codex extension in VS Code. The repository, not the assistant conversation, is the durable handoff. Codex is optional: not installing it must not prevent setup or Copilot workflows.

## Source and discovery

- Canonical source: Project Forge Core `core/skills/<name>/SKILL.md`.
- Copilot project skill: `.github/skills/<name>/SKILL.md`; invoke `/brainstorm`, `/start-work`, `/deliver`.
- Native Codex project skill: `.agents/skills/<name>/SKILL.md`; use `/skills` or `$brainstorm`, `$start-work`, `$deliver`. The prefixes are host-specific, **not equivalent parser syntax**.
- Distribution copies the same canonical Core source into both paths; `CORE_BASELINE.json` / package provenance records both managed paths. Do not manually maintain or fork either distributed copy.
- The Codex `agents/openai.yaml` policy disables implicit activation for human-invocable Project Forge workflows. `web-guidance` remains an agent-invoked skill and is not given that restriction.
- `AGENTS.md` is the common repository instruction anchor. `.github/copilot-instructions.md` remains Copilot-specific.
- Read `.github/instructions/project-forge-workflow.instructions.md` for shared delivery priorities and workflow guidance.
- Codex `$reviewer` is a read-only skill fallback that reads the existing Copilot Reviewer agent's standards; it **does not claim** native subagent equivalence.

## Workflow behavior

Read the configured `.github/project-forge-workspace.json`, exact Issue/work-item authority, approved requirements, relevant design and code. `brainstorm` itself is exploratory; Issue writes require bounded authorization. `start-work` on STANDARD/ELEVATED work requires the final implementation plan and separate human authorization **before branch or code writes**. Reviewer and human meaningful-diff acceptance precede `deliver`. Delivery has one merge/finalize gate; releases and Production deployments retain their separate gates.

Use native host surfaces only when actually available. If the Codex extension cannot expose a specialized Copilot question, editor focus/review, agent or GitHub action, provide the full substantive material, exact relative links/paths and an explicit textual human gate; never pretend a provider action occurred.

If local command execution is available, use repository-owned operations and validate current Git/gh identity/permissions. If not, stop at the corresponding action and provide a grounded handoff. Never treat a skill as authentication or as blanket permission to execute Production operations.

## Optional setup check (the Builder's VS Code machine)

1. Open the intended repository in native Codex (including the intended WSL remote, if applicable). Sign in through the selected subscription.
2. Confirm `AGENTS.md` is read and `/skills` finds `brainstorm`, `start-work`, `deliver` and `reviewer` from `.agents/skills/`. Restart the agent if newly installed skills do not appear.
3. Read-only probe: “Read AGENTS.md, identify this Project's configured work-item authority, list Project Forge skills Codex can discover, and explain the human gates. Do not edit files or write to GitHub.”
4. Test `$brainstorm` in read-only mode; verify it can resolve an exact GitHub Issue/plan but does not write without permission.
5. If intended for implementation, check that workspace-local build/test commands, `git`, and optional `gh auth status` work in the correct runtime. Test actual review and diff acceptance before relying on `$deliver`.
6. Repeat with Copilot's existing `.github/skills/` path. Missing optional Codex integration is an advisory, not setup failure.

**Not yet proven by file tests alone:** the installed native Codex extension and host UI/approval integrations. Report that as requiring workstation acceptance rather than pretending static distribution is end-to-end qualification.

## Efficiency

Codex/ChatGPT usage is model- and plan-dependent and can change. Prefer scoped work items, progressive context loading, separate conversations for unrelated tasks and measured reasoning effort. This does not change package dependencies, grant API credits or imply unlimited usage.
