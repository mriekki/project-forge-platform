# Project Forge Operation Journal

Project Forge uses local operation journals to preserve durable, workstation-local evidence for consequential deterministic operations without turning normal read-only guidance into noisy state.

## Purpose

An operation journal answers:

- what deterministic operation ran;
- when it started and finished;
- which workspace/platform/provenance it used;
- which bounded steps ran and their outcomes;
- where a failure occurred;
- what final status was reached.

The journal is diagnostic evidence. It is not a second workflow database and it does not replace Git, GitHub, CI, deployment state, or human acceptance.

## Location

Store local journals under the ignored Project Forge cache:

```text
.project-forge/
  logs/
    <operation>/
      <timestamp>-<run-id>.log
      latest.log
```

Examples:

```text
.project-forge/logs/setup/2026-10-20T190523-0700-18432.log
.project-forge/logs/build/...
.project-forge/logs/run/...
.project-forge/logs/project-forge-update/...
.project-forge/logs/deployment-readiness/...
.project-forge/logs/deploy/...
.project-forge/logs/tear-down/...
```

`latest.log` may be a copied summary/current run for convenience. Implementations must not depend on symlink support.

Operation journals are workstation-local and must remain ignored by Git. They are never part of `CORE_BASELINE.json`, `PROJECT_FORGE_BASELINE.json`, or application provenance.

## Operations that should journal

Journal deterministic operations when durable local diagnostics materially help:

- `/setup` and repository-local setup/doctor execution, including local runtime convergence and remote-enabled environment preparation;
- `/build` when build diagnostics/artifact evidence are useful;
- `/run` as a concise startup/health receipt when useful, not as an unbounded application log sink;
- `/project-forge-update` apply/verification work;
- `/deployment-readiness` when it performs preparation or repair;
- environment proof operations;
- `/deploy` and `/tear-down`;
- other bounded deterministic operations that mutate workstation or remote environment state.

`/deliver` may write a concise local receipt, but Git commits, PRs, CI, and merge history remain its authoritative durable evidence.

Read-only orientation normally does **not** create a journal:

- `/progress`;
- `/next-step`;
- `/wait-what`;
- read-only documentation/learning navigation;
- read-only status checks unless a caller explicitly requests troubleshooting evidence.

Remote GitHub Actions already retain their own workflow logs. Do not duplicate complete remote logs locally; record only the local request/provenance/result receipt when useful.

## Minimum record

A journal should capture, when available:

```text
operation
run identifier
started/finished timestamps
workspace root or project identity
platform/architecture
relevant Project Forge/Core/Bootstrap/Deployment provenance
step name
step status
resolved tool/version evidence
sanitized command identity
exit code
sanitized failure summary
final status
```

For `/build`, include the requested target and explicit artifact/output paths when the repository build contract establishes them.

For `/run`, record only bounded startup evidence such as target, command identity, process/startup result, established local endpoint/health result, and stop guidance. Do not continuously tee long-running application output into the Project Forge journal.

Prefer stable event names and compact machine-readable fields inside a human-readable `.log`. JSON Lines is acceptable when the implementation already uses structured events.

At completion, report the journal path to the developer when the operation was consequential or when diagnostics were produced.

## Security and privacy boundary

Operation journals are diagnostic artifacts, not raw transcripts.

Never log:

- passwords, PATs, API keys, access tokens, private SSH keys, or secret values;
- credential-manager contents;
- full process environment dumps;
- request/response bodies that may contain credentials;
- arbitrary stdin or secure-prompt contents;
- known-host private material or mutable application data merely for convenience.

Prefer allowlisted structured fields over blind stdout/stderr capture.

When command arguments or error text may contain secrets, redact before writing. Implementations should log a command identity such as executable + safe arguments, step name, return code, and a bounded sanitized failure summary rather than blindly teeing every subprocess byte.

A local journal must not weaken an existing secure prompt, credential boundary, or Human-in-the-Loop gate.

## Lifecycle

For a mutating deterministic operation:

1. create the journal before the first material mutation;
2. record operation/provenance preflight;
3. append bounded step outcomes as work proceeds;
4. flush useful failure evidence before returning/raising;
5. record one final state such as `READY`, `SUCCESS`, `DEFERRED`, `BLOCKED`, `FAILED`, or a domain-specific equivalent;
6. refresh `latest.log` only after the run has a coherent record.

A failed operation keeps its timestamped journal. Do not erase failure evidence merely because a later retry succeeds.

## Retention

Journals are disposable local diagnostics. Project Forge may prune old logs using a conservative size/count policy, but must preserve the current run while it is active and should retain enough recent history to diagnose repeated failures.

Do not silently upload operation journals to GitHub, ChatGPT, telemetry, or another machine. A developer may explicitly choose to share a relevant sanitized excerpt when troubleshooting.

## Relationship to human acceptance

A successful journal entry is machine evidence only. It never marks editor/workspace acceptance, meaningful-diff acceptance, merge authorization, release publication, or production deployment approval on the human's behalf.
