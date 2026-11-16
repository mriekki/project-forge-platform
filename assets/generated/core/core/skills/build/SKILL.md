---
name: build
description: "Build the current project through its repository-owned build command without turning local compilation into setup, testing, delivery, or deployment."
argument-hint: "[target|all]"
user-invocable: true
disable-model-invocation: true
---

# Build

`/build` is a thin local helper. Core stays stack-neutral; the Project becomes deterministic by exposing a repository-owned build command once executable application topology exists. Follow `docs/process/LOCAL_DEVELOPMENT_COMMANDS.md` when present.

## Contract

Invoking `/build` authorizes one bounded local build attempt for the requested target. It does not authorize setup, dependency upgrades, source edits, delivery, release publication, deployment, or Production access.

Resolve the build command from current repository evidence in this order:

1. an explicit developer-selected supported build target, when one was supplied;
2. an explicit repository-owned build wrapper or documented command;
3. an explicit package/task script whose purpose is build;
4. an unambiguous ecosystem-native build entry point already present in the repository, but only when the Project has not yet established a repository-owned build contract.

Do not invent a command because a framework is recognizable. If multiple materially different build targets exist and no default is documented, require a target such as `/build web`, `/build api`, or `/build all`.

Once an executable Project has an established repository-owned build command, treat that command as authoritative. If it is missing, stale, or fails because the Project topology changed, report the contract problem; do not silently bypass it with a framework-native fallback. The work item that materially changes build topology should maintain the Project-owned build command in the same accepted change.

During an intentionally deferred or first-scaffold phase, ecosystem-native inference remains a fallback. Repeated inference is not the preferred mature Project state.

## Preconditions

Before execution:

- identify the repository root and current Git state;
- inspect `PROJECT_BOOTSTRAP.json` and scaffold/readiness evidence when present;
- verify that the selected build entry point exists;
- do not create an intentionally deferred scaffold merely to make `/build` succeed.

If the approved scaffold is deferred or required build markers do not exist, return `BUILD NOT AVAILABLE` with the smallest relevant reason. Do not run installation/scaffolding commands as an implicit repair.

If dependencies or workstation tools are missing, recommend `/setup` rather than broadening `/build`.

## Execution

Run the selected build visibly and report:

- target;
- resolved repository-owned command identity, or clearly labeled inference fallback when no Project-owned command exists yet;
- success/failure and exit code when available;
- produced artifact/output locations when the build contract makes them explicit;
- effective application release/build identity when the build exposes it;
- a concise actionable failure summary.

Do not add linting, tests, formatting, packaging, container publishing, or code generation unless the repository's selected build command already defines them as part of that build.

When the project implements `docs/process/APPLICATION_VERSIONING.md`, report observed version evidence from the build output/artifact metadata. Do not synthesize a build number, commit, or display version when the repository did not produce it.

## Operation journal

A consequential build may write a concise sanitized journal under `.project-forge/logs/build/` following `docs/process/OPERATION_JOURNAL.md`.

Record the command identity, target, timestamps, exit status, explicit artifact paths, and observed application version/build identity when available. Do not blindly capture unlimited compiler/application output or secrets.

## Git and lifecycle boundary

`/build` must not:

- edit source or configuration to fix a build;
- stage, commit, push, open/update PRs, merge, or clean branches;
- mark a work item accepted or delivered;
- bump the application's release version merely to create a unique build;
- publish a package/image/release;
- deploy locally or remotely.

A successful build is local machine evidence only.
