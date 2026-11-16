---
name: run
description: "Run the current project locally through its repository-owned runtime command without conflating local execution with deployment."
argument-hint: "[target|all]"
user-invocable: true
disable-model-invocation: true
---

# Run

`/run` is the normal convenience entry point for starting the project locally. Core stays stack-neutral; the Project becomes deterministic by exposing a repository-owned local runtime command and runtime/persistence pairing once executable application topology exists. Follow `docs/process/LOCAL_DEVELOPMENT_COMMANDS.md` when present.

## Contract

Invoking `/run` authorizes one bounded local start attempt for the requested target. It does not authorize setup, source edits, migrations, database reset/replacement, deployment, release publication, Production access, or persistent background services outside the repository's normal local-development contract.

Resolve the local runtime from current repository evidence in this order:

1. an explicit developer-selected supported runtime/target, when one was supplied;
2. the established Project-owned default local runtime and its associated persistence, including a project-owned local container/database when the repository defines that as the developer topology;
3. an explicit repository-owned run/dev wrapper or documented command for that selected runtime;
4. an explicit package/task script whose purpose is local run/dev;
5. an unambiguous ecosystem-native local entry point already present in the repository, but only when the Project has not yet established a repository-owned runtime contract.

Do not guess. If the repository has multiple independent runtimes and no documented default, require a target such as `/run web`, `/run api`, or `/run all`.

For normal Feature Brief and Engineering Enabler development/validation, default to the established Project-owned local runtime and associated persistence unless the developer explicitly selects an alternative. Do not silently start a native process or use a separate checkout database merely because an ecosystem-native command is convenient.

Once a repository-owned runtime command exists, treat it as authoritative for that runtime. If it is stale or fails because topology changed, report the contract problem; do not silently bypass it with another runtime/database.

## Preconditions

Before starting:

- identify repository root and current Git state;
- inspect `PROJECT_BOOTSTRAP.json` and scaffold/readiness evidence when present;
- resolve the exact selected runtime and, when applicable, the persistence instance it owns or uses;
- verify the selected runtime entry point exists;
- inspect documented local ports, health endpoints, launch profiles, and transport/authentication requirements;
- do not create an intentionally deferred scaffold merely to make `/run` succeed.

If runtime source is intentionally deferred or absent, return `RUN NOT AVAILABLE` and identify the owning work item or missing marker when repository evidence provides it.

If workstation tools or dependencies are missing, recommend `/setup` instead of silently installing them.

### Persistence and schema readiness

When the selected runtime requires persistence, inspect repository-owned non-mutating readiness evidence for the **exact selected persistence instance** before claiming functional readiness. This may include installed Project Forge/Deployment Kit status primitives, migration status commands, repository health/doctor commands, or other documented read-only checks.

- If initialization or required schema is known to be missing/stale, do not automatically migrate, reset, delete, replace, or switch databases. Report `PERSISTENCE BLOCKED` and route to `/setup local` or the repository-owned repair workflow.
- If the repository does not expose a safe way to establish schema compatibility, report `PERSISTENCE UNVERIFIED`. Do not turn a successful connection, process start, `/version`, or connection-only health check into an application-readiness claim.
- If the application has no persistence requirement for the selected runtime, report persistence as `N/A`; do not invent a database gate.

A stopped, absent, stale, or migration-pending Project-owned default container/database is a prerequisite problem, not permission to select a different runtime. An explicit developer selection may authorize a supported alternative within the existing `/run` boundary; inspect only that selected runtime and persistence.

### Transport/authentication readiness

Resolve documented transport prerequisites before choosing a launch profile. If normal authentication development requires HTTPS, secure cookies, or another repository-declared transport property, use the supported Project-owned profile/runtime when available or report the unresolved prerequisite. Do not disable secure-cookie policy, invent TLS/provider settings, or weaken authentication configuration to make `/run` succeed.

## Execution

Start the selected process/runtime in an observable developer-controlled terminal/process surface. Do not hide a long-running application in an unexplained background process.

Report these evidence dimensions separately:

- target and selected runtime identity;
- resolved command identity;
- process/startup result;
- effective application release/build identity when the running application exposes it;
- persistence readiness: `READY`, `BLOCKED`, `UNVERIFIED`, or `N/A`;
- local URL/port and transport evidence only when repository/runtime evidence establishes it;
- functional checks actually performed and their result;
- how to stop the process.

Do not equate startup, artifact identity, `/version`, or connection-only health with successful user workflows. Do not claim login, OAuth callback/provider readiness, or another functional path was verified unless that exact path was exercised successfully.

When `/run all` is explicitly supported, start only the repository-defined set of local components and make each process/endpoint visible.

When the project implements `docs/process/APPLICATION_VERSIONING.md`, prefer runtime-observed version evidence over a source-file guess. Do not synthesize a build number or claim that a static source label proves the running artifact's identity.

## Operation journal

`/run` may write a concise sanitized startup receipt under `.project-forge/logs/run/` following `docs/process/OPERATION_JOURNAL.md`.

Record selected runtime/persistence identity (without secrets), startup command identity, target, timestamps, process/startup result, persistence readiness, functional checks actually performed, observed application version/build identity, and endpoint when established. Do not duplicate or continuously capture unbounded application stdout/stderr into the Project Forge journal.

## Deployment boundary

`/run` is not `/deploy local`.

It must not:

- mutate remote environments;
- perform setup or migration writes implicitly;
- publish images/packages/releases;
- change deployment bindings;
- infer Production configuration;
- bump or rewrite release version state;
- stage, commit, push, merge, or clean branches.

A successful `/run` proves only the evidence dimensions actually observed for the selected local runtime in that session.
