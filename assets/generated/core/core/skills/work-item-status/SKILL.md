---
name: work-item-status
description: "Inspect or manage the optional VS Code Explorer decoration that shows evidence-backed Project Forge work-item progress without renaming or editing work-item tickets."
argument-hint: "[status|enable|disable]"
user-invocable: true
disable-model-invocation: true
---

# Work Item Status

Purpose: make local `docs/work-items/<ID>-...` folders easier to scan in VS Code without changing work-item paths, ticket content, or Project Forge workflow authority.

Normal `/setup` owns automatic installation/update of this Project Forge extension when local `docs/work-items` folders are present. This command remains the focused read-only inspection and manual enable/disable surface.

Normal use is read-only:

```text
/work-item-status
/work-item-status status
```

The optional editor decoration uses the existing Project Forge progress vocabulary:

```text
● IN PROGRESS
✓ COMPLETE
```

No badge means Project Forge is not asserting an execution state for that folder.

## 1. Authority boundary

The Explorer badge is a **view of repository evidence**, not a source of truth.

Never:
- rename a work-item folder to add status text or emoji;
- rewrite the work item's requirements/brief `Status:` field to represent execution progress;
- create a second tracked work-item status database merely for the badge;
- infer completion from an expected lifecycle step that was not observed.

Normal work-item docs, Git branches, pull requests, CI/review/default-branch evidence, and `/progress` remain authoritative.

## 2. Status evidence

The local VS Code extension is deliberately conservative.

`● IN PROGRESS` may be shown when the work-item ID is supported by:
- this checkout's current work branch; or
- an open pull request whose hidden Project Forge marker or work-item branch identifies the folder ID.

`✓ COMPLETE` may be shown when a merged pull request to the repository default branch identifies the work-item ID. New Project Forge delivery PRs should carry the hidden marker:

```html
<!-- project-forge-work-item: <ID> -->
```

At runtime, `<ID>` is replaced by the exact stable work-item ID already resolved for delivery. The marker is navigation metadata only. It does not prove acceptance, CI, deployment, or any other lifecycle gate. For older Project Forge PRs, the extension may use the repository's normal ID-backed branch naming as compatibility evidence.

When GitHub CLI evidence is unavailable, the extension may still show current-branch `IN PROGRESS` state but must not invent merged/completed state.

## 3. Inspect status

Locate the Core-managed installer when present:

```text
tools/project-forge-vscode/work-item-status/install.py
```

For `status`, run it read-only:

```text
python tools/project-forge-vscode/work-item-status/install.py status --json
```

Also check whether `docs/work-items` exists. If the Project uses an external-only work-item source with no local work-item folders, report the Explorer decoration as not applicable rather than creating a competing local hierarchy.

If local work-item folders are present but the package-managed installer is absent, route to `/project-forge-update`; do not clone Project Forge source repositories or download loose extension files as a workaround.

A useful result is:

```text
WORK-ITEM EXPLORER STATUS

Local work-item folders .... PRESENT / NOT PRESENT
VS Code decorator files .... FILES PRESENT / NOT INSTALLED / ERROR
Host activation ............ VERIFIED BY HUMAN / UNVERIFIED / NOT APPLICABLE
Project workflow authority . UNCHANGED
```

`FILES PRESENT` means only that the expected extension files exist in the resolved extension-host directory. It does not prove host discovery or activation. The installer must not report a generic `ready` result merely from file presence.

For Remote - WSL, resolve the extension root in this precedence order:

1. explicit `--extensions-dir`;
2. `VSCODE_EXTENSIONS`;
3. the active VS Code Server root exposed by `VSCODE_AGENT_FOLDER`;
4. an unambiguous existing stable (`~/.vscode-server`) or Insiders (`~/.vscode-server-insiders`) server root;
5. the normal stable WSL server root when no server root exists yet.

If both stable and Insiders roots exist and no active/explicit root identifies the intended host, stop with an actionable ambiguity instead of guessing. Do not generalize the WSL default to SSH, Dev Containers, custom server roots, or other remote hosts.

## 4. Enable

Outside `/setup`, `/work-item-status enable` is explicit authorization for one bounded local editor change: install/update the Project Forge-owned extension in this developer's VS Code extensions directory. Normal `/setup` and `/setup local` already authorize the same bounded install when local `docs/work-items` folders are present, so do not ask for a second confirmation in that flow.

Run:

```text
python tools/project-forge-vscode/work-item-status/install.py install --json
```

The installer may replace older versions of **this same Project Forge extension only**. It must not install unrelated extensions, alter Project files, change work-item docs, or change Git/GitHub state.

If installation changes the extension, tell the developer to reload VS Code once. The install result may confirm file placement and `reloadRequired: true`, but activation remains `unverified` until the actual editor host discovers the extension after reload. When activation matters, confirm command discovery in the active VS Code window rather than inferring it from file existence or from a `code --list-extensions` invocation whose host binding is unknown.

The decorator then refreshes automatically and also exposes:

```text
Project Forge: Refresh Work Item Status
```

through the VS Code Command Palette.

Failure to install this editor decoration does **not** make Project setup, implementation, review, delivery, or deployment unready. `/setup` reports the editor dimension separately as action-needed/error and gives the smallest repair/update action without erasing otherwise-valid application/runtime readiness.

## 5. Disable

`/work-item-status disable` is explicit authorization to remove only Project Forge's own work-item-status extension from this developer's local VS Code extensions directory.

Run:

```text
python tools/project-forge-vscode/work-item-status/install.py uninstall --json
```

Do not remove any other extension. If files were removed, tell the developer to reload VS Code once.

## 6. Guided ending

Return:
- decorator file-installation state;
- host activation state when actually verified;
- whether local `docs/work-items` folders are present;
- a reminder that badges are evidence-derived and non-authoritative;
- the smallest relevant next action.

Do not turn this editor convenience into a source of Project workflow authority.
