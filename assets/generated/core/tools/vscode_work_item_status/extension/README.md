# Project Forge Work Item Status

This optional local VS Code extension decorates Project Forge work-item folders in the Explorer from repository evidence and provides read-only helpers for Project Forge human-review surfaces.

## Installation and activation

Project Forge installs this extension into the VS Code extension-host directory selected by `tools/project-forge-vscode/work-item-status/install.py`.

For Remote - WSL, the installer preserves explicit `--extensions-dir` and `VSCODE_EXTENSIONS` overrides, prefers the active VS Code Server root exposed by `VSCODE_AGENT_FOLDER`, and otherwise distinguishes stable from Insiders server roots without silently choosing between ambiguous existing hosts.

Installer status describes file placement only. `FILES PRESENT` does not prove that the active VS Code host has discovered or activated the extension. After an install/update reports `reloadRequired: true`, reload the actual VS Code window and verify a Project Forge command from that window when activation evidence is required.

## Work-item status

- `●` — in progress, supported by the current work-item branch or an open pull request.
- `✓` — complete, supported by a merged pull request to the repository default branch.
- no badge — no status is asserted.

The status decoration is evidence-derived and non-authoritative. It does not rename or edit work-item folders/documents and does not maintain a second status database. It reads local Git state and, when available, GitHub CLI pull-request metadata. Project Forge's normal repository/PR/CI evidence remains authoritative.

Use **Project Forge: Refresh Work Item Status** from the Command Palette to refresh immediately. The extension also refreshes periodically and when common local Git/work-item evidence changes.

## Human review artifact helper

Project Forge workflows may use **Project Forge: Open Review Artifact** immediately before a human approval gate.

The command accepts an exact workspace-relative repository artifact path when invoked programmatically. When run manually from the Command Palette without a path, it asks for the workspace-relative path.

On VS Code hosts that support the Language Model Tool API, the extension also contributes the read-only `projectForge_openReviewArtifact` tool so an agent can request the same exact presentation operation without arbitrary command execution. Older supported VS Code hosts keep the command/manual fallback.

Behavior:

- Markdown files request rendered Markdown Preview first;
- when Markdown Preview is unavailable, the helper reports that fact and falls back to normal editor preview;
- other repository artifacts open in the normal VS Code editor preview;
- targets outside the currently open workspace are rejected;
- missing or ambiguous multi-root targets are reported rather than guessed from active editor focus;
- the presentation result distinguishes the resolved URI, requested mode, actual opened mode, cancellation, and failure;
- opening/previewing an artifact is read-only presentation and never records approval.

Project Forge should foreground only the exact PRIMARY review subject automatically. Supporting CONTEXT and TRACEABILITY documents remain available without stealing focus unless the human chooses to open them. The approval question itself must still identify and link the same artifact; a successful open is presentation evidence only.
