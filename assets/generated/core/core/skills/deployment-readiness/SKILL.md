---
name: deployment-readiness
description: Guided readiness for any exact project-defined deployment environment. Resolves logical topology first, reuses valid setup-time proof, and verifies only placement-relevant prerequisites.
argument-hint: "[environment] | status [environment]"
user-invocable: true
disable-model-invocation: true
---

# Deployment Readiness

`/deployment-readiness` prepares one exact named logical environment for later real application deployment.

```text
/deployment-readiness <environment>
/deployment-readiness status [environment]
```

Examples include `/deployment-readiness demo`, `/deployment-readiness qa`, and `/deployment-readiness prod-east`.

Production is a resolved purpose/policy classification with stronger gates, not a literal-name test. Do not silently default to Production.

Logical environment purpose/role, placement, isolation, exposure, and concrete target/provider binding are separate facts.

## 1. Resolve topology before machine questions

Prefer the project-owned mutable topology:

```text
DEPLOYMENT_TOPOLOGY.json
```

Use `PROJECT_BOOTSTRAP.json` deployment topology only as the initial topology fallback. Do not rewrite Bootstrap provenance merely because a later environment changes.

Resolve the exact configured environment name plus, when present:

```text
purpose / role
placement
isolation
exposure
binding state
adapter
target/provider binding
failure domain
```

If the requested name is absent, route to `/setup` to define/configure it. Never guess a similar environment or fall back to another one.

Do not assume:

- a second computer exists;
- the developer is on a trusted/home LAN;
- Staging or Production exists;
- Staging and Production use different physical machines;
- deployment uses SSH;
- a remote target exists;
- a managed provider is supported;
- a deferred binding is broken configuration.

A custom name such as `prod-east` remains Production when its resolved purpose is Production.

## 2. Reuse fresh setup-time environment proof

When `/setup` already completed a disposable environment proof from this workstation for the exact environment/target and material topology/trust/platform evidence is unchanged, reuse that proof.

It may establish:

```text
verified target access
ready shared host platform
workstation-mediated exact-image transfer
remote application-runtime mechanics
HTTP health verification
disposable probe cleanup
```

It does not prove final application artifact identity, persistence/migration behavior, route/exposure, project secrets, application health contract, or release policy.

If topology, target binding, host trust, platform state, or another material fact changes, treat the proof as stale and reverify the affected prerequisite.

## 3. First-application outcome assessment

For the first real application deployment to an environment, or whenever the developer's stated goal is a usable endpoint rather than only machine readiness, keep that requested outcome visible and assess the whole material path before declaring the application deploy-ready.

Inspect available non-secret repository, package/tool, workstation, target, and GitHub/CI evidence before asking for facts. Do not require a release workflow to fail merely to discover a prerequisite that can be identified read-only.

Build a compact prerequisite matrix with rows such as:

```text
requested outcome / expected endpoint
workstation architecture
required artifact/target architecture
immutable artifact or release identity policy
artifact destination / publication state when relevant
credential capability + execution location for each required operation
workstation artifact acquisition capability
target delivery method
current application isolation / footprint
runtime health contract
route / exposure mechanism
final workstation/browser verification
```

For each material row distinguish:

```text
evidence source
execution location / credential context
PROVEN / UNKNOWN / BLOCKED / NOT APPLICABLE
missing fact or prerequisite
exact consequential gate, if any
effect on the requested endpoint
```

Architecture is a portability fact, not an operating-system stereotype. For example, an ARM64 workstation targeting a Linux/x86-64 environment must surface the required artifact platform explicitly; do not label that generically as a macOS defect.

Do not report `ENVIRONMENT READY TO DEPLOY` for the first real application while its actual artifact build/publication/acquisition path is still hypothetical. Target/platform readiness and application-deployment readiness are different dimensions.

Keep these evidence dimensions separate in status language:

```text
static/review correctness
live external-contract confidence
credential capability in the exact execution context
immutable artifact provenance
environment/runtime readiness
route state
workstation/browser validation
human access confirmation
formal work-item acceptance
```

A green result in one dimension never proves another.

### Credential capability and lifecycle

Reason from **operation + execution context**, not from the existence of a generic token or successful access somewhere else. When installed tooling exposes structured registry capability evidence, preserve fields such as execution location, credential context, capability proved, and `doesNotProve` rather than paraphrasing a target result as workstation access.

Before asking the developer to create or rotate a credential, explain non-secret lifecycle facts first:

```text
purpose / capability
machine, workflow, or process where it is used
where the credential will be stored
whether its value can be retrieved again
rotation/regeneration impact on existing consumers
value must remain in the local/provider secret surface, never chat
```

Do not assume registry transport access proves package-metadata API access, that target registry access proves workstation access, or that a workstation login proves an Actions workflow capability. Provider-specific token types, scopes, and error-body strings belong to installed/provider-owned adapters or Project evidence, not generic Core invention.

## 4. Placement branches

### A. Workstation placement

For a supported `workstation-container` topology, inspect local Docker/runtime, immutable application image when available, ports/health, collision ownership, persistence prerequisites, and resolved Production policy.

Current reusable topology remains:

```text
placement: workstation
isolation: container
exposure: loopback
```

Do **not** ask for hostname, SSH user, SSH port, host keys, Caddy routes, or target profiles for a workstation environment. Current reusable workstation deployment is loopback-only and must not widen it to LAN/public exposure.

A ready result may be:

```text
ENVIRONMENT READY TO DEPLOY

Environment: Demo
Purpose: demo
Placement: workstation
Docker: READY
Application-specific blockers: NONE

POST-DEPLOY VALIDATION PENDING

NEXT
/deploy demo
```

### B. Remote-target placement

Keep these separate:

```text
named environment
→ logical target binding
→ current hostname or IP address
→ SSH/deployment user
→ independently verified host identity
```

The current address is connectivity information, not trusted identity. Preserve strict host identity verification and stop when unknown/changed host identity fails closed.

Before asking questions, inspect existing non-secret profile/target evidence. Classify the workstation's target setup as `CONFIGURED`, `PARTIAL`, or `NOT CONFIGURED` and ask only for the smallest missing fact.

Invoking `/deployment-readiness <environment>` or directly asking to check readiness authorizes bounded **read-only** diagnostics for the exact resolved environment/target. Do not ask for a second `[REMOTE READ ONLY]` typed phrase or chat approval for each check once that scope is established. The consequence label remains useful in the plan, but the workflow request is the read-only authorization. Never scan/select another host, expand to a different target, change target trust, or weaken host-key verification merely to get a green result.

When the installed Deployment Kit supports `target agent-session`, run supported remote checks via `target agent-session <target> -- <normal Deployment Kit command>` rather than copying `SSH_AUTH_SOCK` paths into each command. For existing Project-owned Python readiness scripts that use the same verified target, use the installed `target agent-run <target> -- <exact reviewed local executable and argv>` to inherit this SSH context without shell evaluation; do not invent script arguments or bypass their gates. This prepares only local SSH authentication (WSL/Linux stable private agent; macOS existing SSH agent or private fallback; native Windows OpenSSH agent service). It must not start or configure a Windows system service, enroll trust, skip an SSH passphrase, or authorize any remote write. If the key needs interactive local input, hand the exact non-secret command to the developer-owned terminal once and resume validation afterward. For older installed kits, use their supported SSH workflow and report the update opportunity rather than fabricating a command.

### Safe diagnostic continuation and no-progress bound

When the installed Deployment Kit exposes a recognized v1 `diagnosticSummary`,
read the fixed reasonCode, failure phase, independently proved/blocked/notChecked
dimensions, observedAt and mutation status **without** losing unrelated good
readiness evidence. Continue using the existing exact-target read-only
authorization. If schema/capability versions are unknown or no usable reason
is present, state that diagnosis is unclassified, not successful.
For `local-signing-unproven`, use the supported configured
`target agent-session` before investigating remote policy; a server's
preliminary key acceptance does not prove that the client signed. Older
installed kits may lack these fields: do not invent them.

Use the bounded retry and evidence-freshness policy in
`core/process/INTERACTIVE_SESSION_GUIDE.md`: after two unchanged,
no-information attempts at the same phase, change the diagnostic method or
report the exact evidence gap. Do not replay CI/reviewers or request the
same unchanged read authorization.

### Exact authenticated-origin peer convergence (PF-06)

For an application whose approved public-origin policy pins the managed Caddy
peer, use the **installed** Deployment Kit's read-only
`platform peer-inspect <target> --configured-peer <ip> --previous-container-id <full-id> --previous-network-id <full-id> --json`
when supported and the application's previously reviewed identity evidence
exists. Preserve the exact named target and classify a mismatch as a
**review-required stop**. A missing previous full identity is
`needs-reviewed-identity-baseline`, not established trust. Do not resolve a
missing baseline by assuming current Docker identity is implicitly approved.

This observation is not a token/certificate proving Caddy authenticity, not
permission to rewrite the application-configured peer, and not proof of
Cloudflare forwarding or of application middleware enforcement. Never trust
a Docker subnet or allow all LAN peers as a workaround. If the installed Kit
does not support this inspection, report the capability gap rather than
inventing a new script or changing Production.

#### Real application isolation preflight

For a supported remote application deployment, prefer the repository-distributed launcher:

```text
tools/project-forge-deployment/project-forge-deploy.py
```

Inspect installed help/version evidence before relying on a specific subcommand. When the installed contract exposes `app isolation`, use that deterministic read-only capability before declaring the application footprint ready. Do not reconstruct equivalent collision logic from model knowledge.

Build the check from exact project/topology/application evidence only:

```text
app isolation <target>
--owner-repo <owner/repository>
--environment <exact logical environment>
--app-slug <application slug>
--container-name <managed container name>
--runtime-port <container-scoped runtime port>
--persistence-mode <none|directory>
[--database-file <SQLite file when applicable>]
[--route-hostname <intended hostname> ...]
[--production when resolved purpose/classification is Production]
--require-clear
--json
```

Pass `--production` for custom Production names such as `prod-east`; never downgrade Production policy because the literal environment name differs.

The isolation check is remote read-only evidence. A clear result may establish that the requested Project/environment footprint does not collide with current Deployment Kit-managed application ownership, container identity, route hostnames/upstream ownership, SQLite identity, persistence root, or deployment-lock identity. It may also report a shared physical failure domain and sibling logical environments.

A blocked result or nonzero `--require-clear` outcome means the environment is **not ready to deploy**. Surface the structured collision codes/evidence and stop before any application write gate. Do not auto-rename the environment, container, route, database, target, or app merely to obtain a clear result.

If current installed tooling does not expose the required isolation capability, report an installed-capability / Project Forge update requirement. Do not silently fall back to prose-only collision reasoning.

Keep the returned isolation `evidenceSha256` with readiness evidence when available. It is review evidence, not a reusable write authorization; `/deploy` and the deterministic deployment tool must re-evaluate current state before mutation.

### C. Managed-service placement

Use only a repository/catalog-provided provider adapter. If none exists, report:

```text
DEPLOYMENT BINDING NOT YET SUPPORTED
Status: CATALOG GAP / PLANNED
No provider credentials requested.
```

Do not provision infrastructure, guess a provider, or invent provider commands from general model knowledge.

### D. Deferred placement

Deferred placement/binding is intentional state:

```text
DEPLOYMENT INTENTIONALLY DEFERRED
```

Do not mark workspace readiness failed. Route to `/setup <environment>` or `/setup remote` if the developer later wants to bind it.

## 5. Shared failure domains / colocated environments

Multiple logical environments may share physical failure domains, but they remain independently targetable and independently authorized. If environments share physical failure, state it explicitly.

A clear application isolation preflight means the current Deployment Kit-managed footprint is non-colliding; it does **not** demonstrate host-level Production isolation.

Colocation does not demonstrate host-level Production isolation. Never infer readiness for one logical environment from another merely because they share hardware.

## 6. State-driven cadence

Normal cadence is:

```text
select exact project-defined environment
→ read current topology
→ reuse fresh environment-proof evidence when valid
→ rediscover placement-relevant local state
→ for first real deployment, assess the complete artifact/credential/delivery/route/endpoint path
→ verify current application isolation when the installed adapter supports it
→ verify/repair only missing prerequisites under exact gates
→ ENVIRONMENT READY TO DEPLOY
→ /deploy <environment>
```

For remote placement, reuse valid existing target access rather than creating duplicate credentials simply because another Project/environment uses the same machine.

When a bounded engineering/delivery correction completes in the same conversation and the developer's deployment outcome is still clear, automatically resume safe read-only readiness reconstruction from current repository/tool evidence. Do not require the developer to type `/deployment-readiness` again merely as navigation. This continuation does not reuse an exhausted write authorization and does not authorize a new registry, Production, route, migration, merge, or other consequential write.

## 7. Read-only status

`/deployment-readiness status [environment]` performs no remote writes. Without a specific environment, summarize all known environments from project topology, including Placement and deferred state where evidenced.

Example:

```text
Environment   Purpose      Placement      This-workstation proof   Readiness
Demo          demo         remote-target  PROVEN                   READY
Staging       staging      remote-target  NOT PROVEN               PARTIAL
prod-east     production   remote-target  PROVEN                   READY
Archive       demo         deferred       NOT APPLICABLE           DEFERRED
```

Do not manufacture target/provider facts for deferred environments.

## 8. Bounded readiness writes

A missing prerequisite is not authorization to change it. Use the repository/tool's exact authorization phrase for key/trust/platform/provider mutations.

Do not hide the real application deployment inside readiness. Readiness may rely on the disposable setup-time proof, but it must not start/replace the real project runtime, register the final application route, perform release-specific migration, or claim project-release smoke validation.

The application isolation preflight itself is read-only and does not authorize later deployment, route, persistence, migration, Production, or destructive writes.

## 9. Pre-deploy versus post-deploy evidence

Readiness asks whether `/deploy <name>` can safely perform the real application deployment now.

Pre-deploy evidence may include topology, adapter availability, binding, local/remote identity and access, target platform, fresh proof evidence, artifact policy, actual artifact acquisition/publication capability when material, deterministic application isolation/collision evidence, route/port availability, persistence/backup/migration prerequisites, lock/recovery capability, and Production-specific safeguards.

Do not require first-deployment live route, deployed-release identity, application health, or smoke evidence before the application has ever been deployed. Those are post-deploy validation evidence owned by `/deploy`.

The intended endpoint may still be known before deployment. When the route does not yet exist, label it explicitly `NOT ACTIVE — ROUTE PENDING`; do not invite the developer to test it as though readiness had made it reachable.

## 10. Production policy

Production is logical policy, not hardware count and not the literal name `production`. A named environment such as `prod-east` with purpose `production` must retain Production readiness and later deployment gates.

Readiness never authorizes Production application deployment.

## 11. Final handoff

When pre-deploy requirements are satisfied:

```text
ENVIRONMENT READY TO DEPLOY

Environment: <exact name>
Purpose: <purpose>
Placement: <...>
Binding: VERIFIED / LOCAL / provider-specific
This-workstation environment proof: PROVEN / NOT REQUIRED / NOT AVAILABLE
Artifact path: PROVEN / NOT APPLICABLE
Credential contexts: PROVEN / NOT APPLICABLE
Application isolation: CLEAR / NOT APPLICABLE
Isolation evidence: <evidenceSha256 when exposed by installed tooling>
Platform prerequisites: READY
Application-specific prerequisites: READY / <remaining items>
Expected endpoint: <URL/route when known>
Endpoint state: NOT ACTIVE — ROUTE PENDING / LOOPBACK PENDING / provider-specific
Security blockers: NONE

POST-DEPLOY VALIDATION PENDING

NEXT
/deploy <exact-name>
```

This is evidence, not deployment authorization. `/deploy` owns the real application write gate for the exact named environment, resolved Production classification, placement, target/provider, artifact, and current evidence.
