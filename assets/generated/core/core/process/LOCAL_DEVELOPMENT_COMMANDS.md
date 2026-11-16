# Local Development Command Contract

## Principle

Project Forge Core is generic; each executable Project should become deterministic.

Bootstrap and early discovery do not need to know framework-specific build/run mechanics. Once an Engineering Enabler or equivalent foundational work item establishes executable application topology, the Project should expose unambiguous repository-owned commands for normal developer build and run behavior.

This contract does not require literal `build.ps1` or `run.ps1` files and does not introduce a `PROJECT_COMMANDS.json` registry. A repository-owned command may be a wrapper script, package/task script, Compose command, build-tool target, Make target, or another deterministic command already owned by the Project.

## Establishment

When the first foundational Engineering Enabler makes the application executable, establish the normal local developer contract as applicable:

```text
Build ........ authoritative Project-owned build command
Run .......... authoritative Project-owned developer runtime command
Persistence .. runtime-associated developer persistence, when applicable
Stop ......... how the normal developer runtime is stopped
Readiness .... what proves the selected runtime is actually ready
Transport .... required local HTTP/HTTPS/authentication properties when applicable
```

If application scaffolding or runtime is intentionally deferred, do not create placeholder commands merely to satisfy this contract. Ecosystem-native inference may remain a temporary fallback until executable topology exists.

## Default runtime and persistence

For Feature Brief and Engineering Enabler implementation/validation, use the established Project-owned local developer runtime and its associated persistence by default unless the developer explicitly selects a supported alternative.

When the Project defines a local container and associated database as its developer topology, that container/database pair is the default. Do not silently substitute a native process or separate checkout database merely because an ecosystem-native command is easier to invoke.

If the default runtime is absent, stopped, stale, or blocked by missing/pending schema prerequisites, route through `/setup local` or the repository-owned repair workflow. Do not bypass the problem by selecting another runtime/database.

An explicit developer selection may authorize a supported alternative within the relevant operation's existing boundaries. Once selected, inspect and operate only against that runtime and its persistence.

Automated tests remain separate: preserve isolated/disposable test databases or runtimes required by the repository's test contract. Never redirect tests into mutable developer data merely to reuse the developer run contract.

## Build command lifecycle

`/build` prefers the established Project-owned build command. Once that command exists, it is authoritative for the normal build target; a failing or stale wrapper is a Project contract problem, not permission to silently bypass it with framework-native fallback.

Where practical, CI should invoke the same underlying repository-owned build entry point so local and CI build semantics do not drift.

A work item that materially changes build topology should assess and update the build contract in the same accepted change. Examples include:

- changing build systems or package managers;
- splitting/combining application components;
- changing generated artifacts or build outputs;
- moving from native build orchestration to containerized build orchestration;
- changing required build-time configuration or dependency preparation.

## Run command lifecycle

`/run` prefers the established Project-owned runtime and associated persistence. A work item that materially changes local runtime topology should assess and update the run contract in the same accepted change. Examples include:

- native/container topology changes;
- frontend/backend composition changes;
- persistence engine/path/volume changes;
- launch-profile or port changes;
- HTTP/HTTPS or authentication transport changes;
- required initialization/migration/readiness behavior;
- stop/cleanup mechanics.

The run command must not hide setup or destructive repair. `/run` may perform read-only prerequisite checks, but normal installation, forward initialization/migration, container convergence, or repair remain owned by `/setup` or repository-specific setup tooling.

## Readiness semantics

Process startup is not application readiness.

Keep these dimensions distinct:

```text
Process startup
Artifact/version identity
Persistence/schema readiness
Transport readiness
Functional checks actually performed
```

A successful `/version` call, open database connection, or connection-only health endpoint does not prove schema compatibility, authentication usability, OAuth readiness, or another user workflow unless that condition is independently verified.

When safe non-mutating verification is unavailable, report the gap instead of inventing confidence.

## Command resolution fallback

Core remains stack-neutral. `/build` and `/run` may still infer an unambiguous ecosystem-native command when no Project-owned command exists yet. That is a fallback for early/incomplete Projects, not the preferred mature state.

Once a Project-owned command exists, do not silently fall through to a different native command because the authoritative command fails. Fix or explicitly change the Project contract through the relevant accepted work item.

## Work-item maintenance rule

For Feature Brief and Engineering Enabler work that materially changes executable application topology, the implementation/review should assess these impacts before delivery:

```text
BUILD CONTRACT IMPACT
RUN CONTRACT IMPACT
SETUP CONTRACT IMPACT
CI CONTRACT IMPACT
```

Update affected Project-owned commands and documentation in the same work item rather than leaving them for rediscovery in a later session.

This is an engineering-interface maintenance rule, not a requirement that every work item touch build/run files.
