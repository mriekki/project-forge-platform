---
name: deploy
description: "Guided deployment orchestration for any exact project-defined logical environment. Reuses setup-time proof, preserves Production classification, and validates live application evidence."
argument-hint: "<environment> [release-or-artifact]"
user-invocable: true
disable-model-invocation: true
---

# Deploy

`/deploy <environment>` deploys the real project application to one exact configured logical environment.

```text
/deploy demo
/deploy staging
/deploy qa
/deploy prod-east
```

Core owns topology/policy resolution, Human-in-the-Loop authorization, and evidence-oriented orchestration. Repository-provided deterministic tooling owns deployment mechanics.

## 1. Resolve exact named topology

Prefer:

```text
DEPLOYMENT_TOPOLOGY.json
```

Use `PROJECT_BOOTSTRAP.json` deployment topology only as the initial topology fallback.

Resolve exact configured name, purpose/Production classification, placement, isolation, exposure, binding, adapter, target/provider, and failure domain.

If `demo` exists, `/deploy demo` targets exactly `demo`. If `prod-east` has purpose `production`, `/deploy prod-east` remains a Production deployment even though the literal name differs.

If no environment is named, enumerate configured environments and ask the human to choose through host-native **single-select structured choice UI** when available; in VS Code use the native question surface such as `vscode_askQuestions`; never silently default to Production. Do not recommend an environment unless current project evidence or the user's stated deployment goal clearly supports one. The deployment workflow must never fall back to another environment/placement/host/provider because deployment fails.

If the requested environment is missing or ambiguous, route to `/setup` rather than guessing.

## 2. Resolve baseline/readiness/proof evidence

Read only what is needed, including when present:

- `PROJECT_FORGE_BASELINE.json`;
- `DEPLOYMENT_BASELINE.json`;
- project topology and approved deployment/release requirements;
- `/deployment-readiness` evidence, including first-application outcome assessment and deterministic application isolation evidence when supported;
- fresh setup-time environment-proof evidence for this workstation;
- established application deployment facts.

For package-managed generated Projects, prefer the repository-distributed launcher:

```text
tools/project-forge-deployment/project-forge-deploy.py
```

Do not require a separate Deployment Kit checkout.

When a fresh setup-time proof already demonstrated target access, platform readiness, workstation-mediated image transfer, remote managed runtime, health, and cleanup from this workstation, do not repeat those environment-mechanics questions unless material evidence changed.

Proof does not establish the real application's image/release, persistence/migration contract, route/exposure, secrets, health contract, or release policy.

A prior readiness isolation fingerprint is review evidence only. It does not authorize deployment and does not replace the deterministic deployment planner's current isolation revalidation.

For a first real deployment, do not collapse a target/platform `READY` result into application deployability. Confirm that readiness established an actual artifact build/publication/acquisition path when that path is material. If artifact identity or acquisition is still hypothetical, return to the missing prerequisite rather than requesting the application write gate.

## 3. Preserve execution and credential context

When installed tooling exposes structured capability evidence, preserve its semantics exactly in the deployment assessment and preview. In particular, retain fields equivalent to:

```text
executionLocation
credentialContext
capabilityProved
capabilityAttempted
doesNotProve
```

A registry manifest check executed on a remote target proves only the capability reported for that target/context. Never describe it as workstation registry access. A workstation registry check proves only the workstation capability it reports. Neither implies Actions registry transport or package-metadata API access.

Do not infer provider-specific token scopes or error meaning from generic registry results. Provider-specific package metadata/publication behavior belongs to repository/provider tooling and its own evidence.

When a new credential is genuinely required, explain its purpose, execution context, storage location, retrievability, and rotation impact before asking the developer to create it. Credential values remain in the provider/local secret surface and never enter chat.

## 4. First real deployment asks only unresolved application questions

The first real `/deploy <environment>` after environment proof may need a small application-specific completion step. Ask only material unknowns not already answered by project evidence, such as:

```text
health endpoint/runtime port
persistence path/migration behavior
route/exposure
secret/non-secret runtime-value boundary
immutable application image/release policy
smoke validation
```

When a bounded choice is useful, follow `INTERACTIVE_SESSION_GUIDE.md`: use host-native structured choice UI when available, single-select for mutually exclusive values and multi-select only when several simultaneous selections are valid. Keep `Other / specify` or free-text available when the choices may be incomplete. Recommend at most one option, only when evidence or a clear engineering tradeoff supports it, and explain why briefly; otherwise show the choices without a recommendation. Record only the human's selected/confirmed answer.

Once these facts are durably established, later deployments should be routine rather than repeating onboarding.

## 5. Placement determines launcher

### Workstation container

For supported `workstation-container` placement, use the repository-distributed local adapter. Verify local Docker/runtime, exact immutable image, ports/health, ownership/collision plan, persistence, and resolved Production policy.

Current reusable workstation-container support is loopback-only. Do not widen it to LAN/public exposure as an implicit convenience.

### Remote target

Resolve the exact logical target established by topology/readiness, preserve verified host trust, and stop on unknown/changed identity.

Prefer workstation-mediated exact-image delivery when installed/supported unless the project explicitly requires target-side registry pulls:

```text
exact image acquired/built locally
→ exact immutable digest verified
→ image streamed over verified SSH
→ remote docker load
→ exact image verified remotely
→ managed application runtime deploys preloaded image
```

Do not copy a developer GitHub PAT/GHCR credential to the target as normal deployment behavior.

For installed Deployment Kit versions that expose real application isolation planning, require that capability rather than reconstructing collision checks from model knowledge. If the installed package lacks the capability required by current Core policy, stop with a Project Forge update/capability requirement before requesting the application write authorization.

### Managed service

Use only an installed repository/catalog provider adapter. If none exists, stop with `CATALOG GAP / PLANNED` rather than constructing provider commands from general knowledge.

### Deferred

Report `DEPLOYMENT NOT BOUND YET` and route to `/setup <environment>` or `/deployment-readiness <environment>`.

## 6. Preserve custom Production classification

Pass the exact configured environment name to the deterministic launcher.

When resolved purpose/classification is Production, use the installed tool's explicit Production classification mechanism even for a custom name. Current Deployment Kit versions may expose:

```text
--production
```

Inspect installed help/version evidence. If the installed tool cannot preserve Production classification for a custom name, stop rather than downgrading safety.

## 7. Build the deterministic plan

Use repository-provided tooling to construct/inspect the exact application deployment plan. Supported operations may include:

```text
optional backup/safety check
→ exact image transfer/acquisition
→ release-specific migration
→ application/container deployment
→ route/loopback publication
→ health/readiness verification
→ smoke validation
→ deployment evidence capture
```

For the standard remote Deployment Kit path, pass the intended application footprint needed by the installed planner's isolation contract, including exact target, owner repository, environment, Production classification, app slug, container name, runtime port, persistence mode, optional SQLite database file, and intended route hostnames when applicable.

When the deterministic application plan exposes reviewed isolation evidence (for example `isolationReview`), require a clear state and retain its evidence fingerprint for the human preview. A blocked plan is not deployable. Do not edit names/ports/routes/persistence identities automatically to make a blocked plan pass.

The deterministic deployment tool owns the final current-state recheck immediately before mutation. Core must not substitute a stale readiness fingerprint or prose-only reasoning for that revalidation.

Do not smuggle infrastructure provisioning, target/provider rebinding, destructive restore, or environment tear-down into the application plan.

### Remote runtime + route rollout preview

When the installed Deployment Kit exposes a deterministic read-only `app rollout` capability and the selected remote deployment has an intended route, prefer that capability for the final pre-write preview rather than independently narrating runtime and route consequences.

A current installed contract may expose a command shape similar to:

```text
project-forge-deploy app rollout <target>
  --owner-repo <owner/repository>
  --environment <exact environment>
  --app-slug <application slug>
  --container-name <container>
  --runtime-port <port>
  --persistence-mode <none|directory>
  --image <immutable digest>
  --health-path <path>
  --run-as <uid[:gid]>
  [--route-hostname <hostname> ...]
  [--production]
  --json
```

Inspect installed help/version rather than assuming this example exactly matches every package version.

Treat the returned staged rollout as **read-only review evidence**. Preserve:

```text
runtime plan + isolation evidence
route plan + route-inventory evidence
separate stage authorizations
endpoint state before runtime
after-runtime / before-route endpoint state
after-route verification state
```

If the installed package lacks this composite preview, retain the existing safe runtime and route planners and state their sequence explicitly. Do not invent a combined write command.

## 8. Preserve exact authorization contracts

Core consequence labels do not replace stricter installed-tool phrases.

The standard Deployment Kit may use exact phrases such as:

```text
[APP DEPLOY WRITE]
[PRODUCTION APP DEPLOY]
[ROUTE WRITE]
```

For Production-class environments also show `[PRODUCTION WRITE]` consequence visibility where Core policy calls for it.

Resolve the exact phrase from the installed tool/version. For a staged rollout, resolve it separately for each stage. Do not assume an example phrase when the installed contract differs.

Authorization applies only to the exact environment, resolved classification, placement/target/provider, artifact, reviewed plan/stage, current isolation evidence and route evidence, and evidence shown. Material changes require renewed review/authorization.

**Avoid duplicate terminal approval:** when the Builder has explicitly approved this exact current stage in VS Code Copilot Chat, the assistant may pass the installed Deployment Kit's supported `--yes` flag for **that stage only** instead of making the Builder type the displayed phrase again in Bash/PowerShell. `--yes` is an execution flag, not approval evidence; never use it because the human previously approved a different plan, artifact, target, route, session, or stage. If the installed command lacks the flag, preserve its normal gate. Destructive resets/restores and SSH trust/credential changes are independent consequences and are not authorized by a deployment approval.

Before unattended rollout, identify a concise reviewed-stage envelope:
exact target, immutable artifact, permitted operations, current plan/proof
identity and freshness, distinct runtime/route/data/trust boundaries, and any
remaining local secret or human approval stop. Do not promise to finish
unattended if those stops remain. Repeat safe mechanics within unchanged
authority; reopen only for changed evidence or a genuinely new consequence.
After two unchanged failures with no new evidence, change the method or
stop instead of repeatedly recreating the same plan. Apply the bounded
continuation policy in `core/process/INTERACTIVE_SESSION_GUIDE.md`.

A runtime authorization never authorizes the route stage. A route authorization never retroactively authorizes a changed runtime artifact. If the rollout contains both stages, preserve the separate gates even though the Builder reviewed one coherent outcome.

For authenticated public ingress relying on a pinned exact Caddy peer,
preserve current read-only managed peer evidence (when supported) as a
separate plan dimension from DNS, route and image readiness. If observed
Caddy container/network identity or peer IP changed from the reviewed
application binding, **do not silently update the trusted proxy**, change
the release image, or continue the public-authentication rollout. Prepare a
separate app-owned reviewed convergence/health/rollback stage.
Proxy observation alone neither authorizes runtime writes nor proves live end-to-end
OIDC/public-origin behavior. Follow the PF-06 producer's immutable identity
review boundary, or report the installed capability as unavailable.

## 9. Preview and execute only the approved contract

Before mutation, show concise non-secret evidence such as exact environment, purpose, placement, target/provider when applicable, proof freshness, immutable application artifact, persistence/migration, exposure/route, application isolation state/fingerprint when exposed, shared failure-domain note when relevant, planned stages, endpoint state at each stage, and the exact required authorization phrase for the next consequence only.

After authorization, invoke only the repository-provided deterministic launcher. For remote SSH placement, prefer the installed Deployment Kit's `target agent-session <target> -- <normal Deployment Kit command>` wrapper when supported; it reuses local SSH authentication across WSL/Linux, macOS, and native Windows VS Code sessions without copying long socket paths. For a Project-owned, repository-reviewed deployment script, use `target agent-run <target> -- <explicit local executable and argv>` when installed; it does not execute a shell, add `--yes`, or replace the script's approvals. Do not switch the workflow from VS Code Copilot Chat to Copilot CLI merely for terminal automation. A key passphrase, when required, stays in the developer-owned terminal and never in Chat. The session wrapper does not provide remote authorization or replace current plan/host checks. Never redirect to another environment/host/provider, weaken trust/exposure, force through lock contention, or invent recovery writes.

The deterministic launcher must revalidate current isolation immediately before real application mutation when the installed contract provides that capability. If current isolation changed or became blocked after review, stop and create/review a fresh plan rather than continuing under the old authorization.

Existing per-app/per-environment locks are normal concurrency protection when another workstation is deploying the same environment.

### Runtime succeeded but route is pending

A healthy application runtime is a valid intermediate outcome. When a requested route has not yet been registered, say this explicitly before showing the route gate:

```text
APPLICATION RUNTIME READY
Expected endpoint: <hostname/URL>
Endpoint state: NOT ACTIVE — ROUTE PENDING
Do not test this URL yet; the route write has not been authorized/applied.
```

Then, if the reviewed route plan is still current, present the route consequence directly. Do not require the developer to invoke `/deploy` or another slash command merely to rediscover the already reviewed route stage.

The runtime success does not consume or imply route authorization. If route evidence changed, rebuild/review the route plan first.

## 10. Resume the established outcome without navigation ceremony

Within the same conversation, if a bounded engineering/delivery correction or external prerequisite completes and the developer's requested deployment outcome remains unambiguous, automatically resume safe **read-only** reconstruction of readiness/deployment evidence from the repository, GitHub, installed tools, and runtime state.

Do not require the developer to type `/deliver`, `/deployment-readiness`, or `/deploy` merely as navigation to rediscover known state after that bounded action completes.

This continuation:

- never repeats a completed write;
- never reuses exhausted registry/Production/route/merge/migration/destructive authority;
- stops when the artifact, plan, target, consequence, or other material evidence changed;
- does not create a parallel persistent workflow database.

If `/deploy` is invoked again after an already validated deployment, first reconstruct current deployment evidence. If the same validated artifact/runtime/route remains current and no new deployment outcome is requested, report the existing validated state rather than proposing or performing a redundant redeployment.

## 11. Validate live evidence

After execution, use repository-provided inventory/health/route/smoke/evidence commands when available.

A successful result may be summarized as:

```text
DEPLOYMENT VALIDATED

Environment: <exact name>
Purpose: <...>
Artifact: <exact immutable identity>
Artifact delivery: <workstation-transfer|remote-registry|local-runtime|provider>
Endpoint/Route: READY / LOOPBACK / NOT APPLICABLE
Application health: READY
Workstation/browser verification: PASSED / NOT APPLICABLE / PENDING
Smoke: PASSED / NOT REQUIRED
Deployment evidence: RECORDED / VERIFIED
```

Do not report success merely because a container/process started when stronger health evidence is required. Do not report a route as user-accessible merely because registration returned; perform the repository-supported endpoint/workstation/browser verification when the requested outcome depends on it.

A setup-time disposable environment proof is not real application deployment evidence. A successful application deployment never authorizes a later Production write or destructive `/tear-down`.

Keep human access confirmation distinct from automated browser/health evidence. The developer saying they can reach the endpoint is useful observed human evidence; it is not automatically formal work-item acceptance.

## 12. Reconcile the durable outcome without asserting acceptance

After `DEPLOYMENT VALIDATED`, inspect the repository's configured work-item/operating authority. When an existing current-status or deployment-result section is stale and the observed deployment outcome is material, offer a bounded reconciliation containing only supported non-secret facts such as:

```text
exact environment
release/source/artifact identity
artifact delivery method
runtime health result
route/endpoint
workstation/browser validation
explicit human access confirmation, when actually stated
known limitations and evidence boundaries
```

Preserve historical approval records. Do not silently rewrite product requirements, broaden the milestone, mark formal acceptance, close the work item, or infer acceptance from browser accessibility.

If the human authorizes the bounded documentation update, use the repository's normal work-item/delivery workflow for that edit. Documentation reconciliation is not a reason to redeploy and does not create new Production write authority.
