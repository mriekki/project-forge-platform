# Workspace Instances

Status: **SUPPORTED MODEL — ONE PROJECT MAY HAVE MULTIPLE INDEPENDENT WORKSTATION CHECKOUTS**

A **workspace instance** is one checkout of one Project Forge on one developer workstation. A project may have multiple workspace instances active at the same time, including different operating systems for the same developer.

Examples:

```text
family-meal-planner-v3
├─ Mark Windows workspace
└─ Mark macOS workspace
```

Neither workstation is primary. One does not need to be online for the other to work.

## Shared project state

Git/GitHub is the normal shared source-code coordination boundary. The repository owns project facts such as:

- source code and tests;
- exact project technology/version choices;
- Project Forge package/baseline state;
- work-item and architecture documentation;
- project-owned deployment topology and environment references.

Independent workstreams should normally use independent short-lived branches. Different work items may be active from different workstations at the same time.

Using the same branch from more than one workstation is allowed but requires ordinary Git coordination. A workspace must treat a remote branch that advanced elsewhere as new evidence and must not resolve divergence with force/reset/history rewriting automatically.

## Portable personal state

The authenticated developer's private `<login>/project-forge-profile` is portable, non-secret state shared across the developer's workstations.

It may carry target definitions/preferences such as logical target, hostname, SSH user/port, OS profile, and stable host alias.

It must not carry:

- SSH private keys or passphrases;
- passwords/PATs/tokens;
- `known_hosts` contents;
- machine-specific credential paths;
- local databases or application runtime data;
- Docker credential state;
- workstation readiness claims.

A new workstation may sync/apply this profile and then establish its own machine-specific identity/trust.

## Machine-local workspace state

Each workspace instance independently owns:

- OS/tool installations;
- VS Code/editor extensions;
- local dependency caches;
- local Docker/runtime state;
- local development database/data;
- SSH private key and host trust;
- GitHub/Docker/registry credentials;
- repository-scoped developer-mode/readiness evidence.

Local mutable application data is not synchronized between workstations by Project Forge. Projects should reproduce schema/migrations/seed behavior rather than silently copying a workstation's development database to another computer.

## Setup on another workstation

The normal flow for an existing generated Project is:

```text
clone repository
→ open generated VS Code workspace
→ /setup
```

`/setup` detects the current OS automatically and chooses the generated launcher:

```text
Windows  .\scripts\setup.ps1
macOS    ./scripts/setup.sh
```

When repository/project evidence exists but workstation-local readiness evidence does not, the developer-facing state is:

```text
EXISTING PROJECT — NEW WORKSTATION
```

Setup should reuse the project definition and portable personal profile, install/verify only missing safe machine capabilities, restore project dependencies, and converge local readiness. Remote access remains optional until needed.

OS-specific project limitations remain real. For example, a Windows workspace may edit shared Swift source but cannot claim native iOS build readiness when the selected toolchain requires macOS/Xcode.

## Concurrent source work

Recommended shape:

```text
Windows → feature/work-item-a
macOS   → feature/work-item-b
```

Both workspaces can build/test/run locally at the same time using independent local runtime/data.

If both use the same branch, source coordination remains Git-based:

```text
local branch SHA
vs
remote branch SHA
```

Before history-sensitive work/delivery, fetch/inspect current remote evidence. If another workspace advanced the branch, reconcile explicitly. Never use `git stash` as cross-workstation transport and never force-push merely to make two clones agree.

## Concurrent remote environment operations

A shared Staging or Production application is different from independent local development. Multiple workstations may have access to the same logical remote environment, but only one mutating application operation for the same app/environment may proceed at a time.

The Deployment Kit remote application runtime already acquires a non-blocking per-application/per-environment lock. If another deployment holds the lock, a concurrent deployment exits rather than racing the same runtime. Persistence operations use the same app/environment lock boundary.

Conceptually:

```text
Windows  ─┐
          ├─> same app / staging ─> one active mutation
macOS    ─┘                       └> second mutation blocked
```

Readiness/access on each workstation remains machine-specific because credentials/trust are machine-local. Remote environment state itself is shared.

## What Project Forge does not need

Multi-workstation support does **not** require:

- a central device registry;
- one primary developer computer;
- another workstation to be online;
- shared private keys;
- shared mutable local databases;
- proprietary file synchronization outside Git;
- automatic worktree transfer between computers.

A friendly machine/workspace label may be shown locally when useful, but it is descriptive only and not a project authority.

## Developer-facing commands

The normal surface remains small:

```text
/setup
/progress
/next-step
/start-work <ID>
/deliver
```

`/setup` prepares **this** workspace instance. `/progress` reports **this** workspace instance plus shared project/environment evidence. Normal Git/work-item and delivery rules coordinate source changes across workstations.
