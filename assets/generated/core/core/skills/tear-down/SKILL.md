---
name: tear-down
description: "List target-owned Project environments and guide destructive cleanup for local state, one exact named environment, or all explicitly configured Project environments. Preserves ownership boundaries, shared Project Forge infrastructure, and separate Production/public-ingress authorization."
argument-hint: "[list [<target>]|local|<environment>|all]"
user-invocable: true
disable-model-invocation: true
---

# Tear Down

`/tear-down` is the human-facing inventory and destructive-cleanup workflow for Project-owned deployment state.

Logical environment names are data-driven and are not limited to Staging/Production:

```text
/tear-down list production
/tear-down demo
/tear-down qa
/tear-down staging
/tear-down prod-east
```

The skill owns target selection, exact scope selection, read-only inventory/preflight, destructive preview, and Human-in-the-Loop authorization. Deployment Kit deterministic tooling owns inventory and deletion mechanics.

## 0. List what is installed before destructive selection

When the Builder asks what is deployed, what can be removed, or invokes `list`, use the Deployment Kit read-only target inventory:

```text
project-forge-deploy target inventory <target> --json
```

This is the canonical application-cleanup inventory. It correlates the target's managed runtime, trusted-LAN route, and managed public-ingress ownership into application/environment tear-down candidates while reporting the shared host platform separately.

The command is intentionally independent of the consumer repository. If a consumer checkout or even its GitHub repository has already been deleted, the same installed/standalone Deployment Kit command may still inventory the target from host-owned metadata and user-scoped target access configuration.

Inside a consumer repository, use the repository-provided Deployment Kit launcher when that is the installed contract. Detect the current platform/runtime and invoke the portable Python entrypoint or installed `project-forge-deploy`; do not assume PowerShell syntax or Windows-only paths. macOS/Linux shells and Windows/PowerShell must reach the same deterministic CLI semantics.

Do not reconstruct inventory by ad-hoc `ssh`, `docker ps`, filesystem listing, or Cloudflare commands when Deployment Kit target inventory is available.

If a public-ingress scope cannot be inferred from the application/environment name, pass only the exact additional scope established by repository topology or trusted operator evidence:

```text
--ingress-scope <scope>
```

Listing is read-only. It does not authorize later deletion.

## 1. Resolve exact project topology when the repository exists

Prefer:

```text
DEPLOYMENT_TOPOLOGY.json
```

Use `PROJECT_BOOTSTRAP.json` deployment topology only as the initial topology fallback.

Resolve only configured logical environments and their current purpose/Production classification, placement/target binding, repository/application identity, and ownership evidence.

If `demo` is configured, `/tear-down demo` means exactly `demo`. If `prod-east` has purpose `production`, it remains Production-class regardless of its literal name.

Never guess a similar environment and never widen scope after failure.

When the repository no longer exists, use target inventory only for target-owned application identity and resource ownership. Do not invent repository-only topology facts. In particular, if a non-literal custom environment's Production classification cannot be established from trusted evidence, stop before destructive authorization rather than weakening the Production-data gate.

## 2. Select exact destructive scope

The destructive scope contract remains exactly `[local|<environment>|all]`; `list` is a separate read-only discovery mode and never becomes a destructive scope.

```text
local
<one exact repository-defined named environment>
all
```

If no scope is named, present only scopes the repository actually supports; never silently default to a Production environment or `all`.

For orphaned deployments where the consumer repository is unavailable, present only exact application/environment candidates returned by target inventory.

`all` means only all explicitly configured scopes for this Project; it never means machine-wide cleanup.

Selecting scope does not authorize deletion. Physical colocation never merges ownership: deleting `demo` must not remove `staging` or `prod-east` merely because they share hardware.

If the requested name is absent from project topology or target inventory, stop. Do not substitute another environment.

## 3. Resolve Production and public-ingress classification from the deletion set

For each selected environment identify:

```text
environment name
purpose / Production classification
placement / target
repository/application identity
trusted-LAN route
managed public-ingress scope/hostname, when present
ownership markers required by installed tooling
```

For current Deployment Kit consumers, custom Production names may be passed explicitly, for example:

```text
--production-environment prod-east
```

When target inventory reports an owned public route, preserve its exact environment-to-ingress-scope binding for cleanup, conceptually:

```text
--public-ingress-scope production=production
```

Use actual installed help/version evidence. If the installed tool cannot preserve a custom Production classification or exact public-ingress ownership, stop rather than downgrading the destructive gate.

## 4. Present an exact destructive preview

Show what will be removed and what will be preserved.

```text
TEAR-DOWN READY

Scope: <local|demo|qa|staging|prod-east|all>
Repository/app: <verified identity>
Selected environments:
  <name> → <placement/target> — <purpose/classification>

Will remove:
  owned public hostname/DNS + tunnel rule, when selected
  owned trusted-LAN route
  owned application container/runtime
  owned releases, evidence, persistent data, and backups
  remote immutable image only when no other managed release/container still references it

Will preserve:
  shared Project Forge Caddy/network/platform
  shared Cloudflare tunnel/runtime
  unrelated Projects/environments
  remote images still referenced by another managed release/container
```

Do not promise deletion of named/shared Docker volumes unless the installed deterministic contract proves exact ownership and explicitly includes them. Do not promise deletion of any shared/unrelated resource whose ownership cannot be proven.

## 5. Authorization gates

Every modifying tear-down requires the installed normal authorization, conceptually:

```text
[PROJECT TEAR DOWN]
```

whenever **any selected environment is Production-class**, require the stronger Production-data deletion authorization, conceptually:

```text
[PRODUCTION DATA DELETE]
```

Whenever the reviewed deletion set includes an owned public-ingress route, also require the separate public-ingress removal authorization, conceptually:

```text
[PUBLIC INGRESS ROUTE REMOVE]
```

Resolve exact phrases from the installed tool/version. Do not tie the Production-data gate only to literal scope strings such as `production` or `all`; it depends on the actual resolved deletion set.

A prior `/setup`, environment proof, `/deploy`, merge, CI, public-route registration, or other approval never authorizes destructive cleanup.

If identity, selected environment set, classification, binding, ownership evidence, public-ingress scope, or deletion set changes after preview, require renewed review/authorization.

## 6. Execute only Deployment Kit deterministic cleanup

After authorization, invoke only the approved tear-down command with exact named scopes/bindings. Do not improvise shell commands.

For a generalized current Deployment Kit invocation, exact bindings may look conceptually like:

```text
--environment-target staging=<target>
--environment-target production=<target>
--public-ingress-scope production=production
--production-environment prod-east
```

Use target inventory output and the installed contract rather than inventing flags for older versions.

Public ingress must be removed before the trusted-LAN route/runtime so a public hostname is never deliberately left pointing at a removed origin. The shared Cloudflare tunnel/runtime is host infrastructure and must remain.

Remote image cleanup is bounded: remove only the selected environment's immutable image when no other managed release metadata or container still references it. Never use Docker system/image/volume prune.

Never add machine-wide Docker prune, shared platform/network removal, unrelated environment cleanup, host reprovisioning, target rebinding, credential/trust deletion, registry-package deletion, or shared Cloudflare tunnel deletion unless a separate lifecycle operation explicitly owns and authorizes it.

If aggregate `all` cleanup stops partway, report completed and remaining scopes. Do not manually compensate by deleting the rest.

## 7. Verify and report outcome

Re-run target inventory after cleanup when available. Report only observed evidence: requested scope, exact environment names/targets processed, Production-class environments included, public routes removed/already absent, trusted-LAN routes removed/already absent, runtime/data removal, remote image removed/retained, local state processed, and any remaining scopes after a partial stop.

Shared Project Forge platform state and unrelated application candidates should remain present and unchanged.

When the installed deterministic contract is idempotent, already-absent owned resources should remain safe to re-check/re-run without broadening scope.
