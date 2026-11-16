# Deployment Enablement

Deployment enablement is the guided operational lane between delivered deployment engineering and `/deploy`.

A **logical environment is not a physical computer**. A repository may define `demo`, `staging`, `production`, or other named environments; one developer may use only a workstation, several environments may share one VPS, or a desired deployment may remain explicitly deferred.

The normal human-facing entry point is state-driven:

```text
/deployment-readiness <environment>
```

Read-only overview:

```text
/deployment-readiness status [environment]
```

The workflow discovers current topology/state and continues from the furthest safe point. The human does not choose separate `discovery`, `enable`, or `resume` modes.

## Topology before machine questions

Resolve these independently when repository evidence provides them:

```text
environment name / role / purpose
placement
isolation
exposure
binding state
adapter
target/provider binding
failure domain
```

Current placement classes include:

- `workstation` — local execution; current reusable container adapter is loopback-only;
- `remote-target` — an explicitly bound remote machine/target;
- `managed-service` — only when a provider-specific adapter actually exists;
- `deferred` — desired deployment exists but no current target/provider binding is selected.

Do not ask remote-machine questions until `remote-target` is actually the selected placement.

## Workstation readiness

A one-machine local/demo topology is normal.

For current `workstation-container` support, readiness focuses on:

- local Docker/runtime availability;
- repository-distributed local deployment tooling;
- exact immutable artifact/image identity;
- local port/container ownership and health configuration;
- persistence prerequisites where relevant;
- Production policy if the logical environment is Production.

It does not require SSH, a hostname, target profile, host trust, Caddy, Avahi, or a second computer.

The adapter's current exposure is loopback. Do not silently widen it to LAN/public sharing.

## Remote-target readiness

For remote placement, retain the strict target/access model:

```text
named environment
→ explicit target binding
→ current address/discovery
→ independently verified host identity
```

Human-facing facts normally include hostname/IP, deployment user, non-default port, and target OS when relevant.

Internal target/profile/SSH/trust paths should be discovered, reused, or derived whenever possible rather than pushed onto the human as first questions.

If existing configuration is present, show known facts for confirmation. If partial, ask only for the smallest missing fact. If absent, start with the actual machine/address rather than an internal target identifier.

Remote probing requires explicit read-only authorization. Address discovery never substitutes for cryptographic host identity. Unknown/changed SSH identity fails closed.

### Real application isolation readiness

For supported remote application deployment, readiness should use the repository-distributed Deployment Kit launcher rather than infer collision safety from prose:

```text
tools/project-forge-deployment/project-forge-deploy.py app isolation ... --require-clear --json
```

The read-only check should be built from the exact known application footprint: target binding, owner repository, exact logical environment, resolved Production classification, app slug, container name, runtime port, persistence mode, optional SQLite database file, and intended route hostnames when applicable.

The deterministic result may prove the current managed application footprint is non-colliding across ownership, runtime/container identity, route hostnames/upstream ownership, SQLite identity, persistence root, and per-app/per-environment lock identity. It may also report colocated sibling environments and a shared physical failure domain.

A clear result is pre-deploy evidence only. It does not authorize application, route, persistence, migration, Production, or destructive writes. A blocked result means readiness must stop before the real application write gate and surface the structured conflict evidence.

If installed package tooling lacks the required isolation capability, require a Project Forge capability/update path rather than reconstructing equivalent checks from model knowledge.

When available, retain the isolation evidence fingerprint for human review. `/deploy` must still use the deterministic planner and current-state revalidation before mutation; a readiness fingerprint is not a durable write authorization.

## Deferred readiness

A deferred placement is intentional configuration state:

```text
DEPLOYMENT INTENTIONALLY DEFERRED
```

It must not block repository generation, local development, CI, documentation, or learning. Readiness should explain the next material decision—choose/configure a supported target/provider adapter—without guessing infrastructure or asking for secrets.

## Managed-service boundary

Managed hosting is adapter-specific. General model knowledge may recommend a provider, but absent a live catalog/implementation contract it remains `CATALOG GAP`/planned.

No provider credentials or provisioning should occur merely because a deployment outcome is public/shareable.

## Colocated environments

Two logical environments may intentionally share one physical failure domain.

Keep their targetable scope, runtime/container, route, data, readiness evidence, and authorization independent. When Staging and Production share one target, surface:

```text
TOPOLOGY NOTE

Staging and Production are logically isolated but share one physical
failure domain. This may fit Project cost/learning goals, but it does not
demonstrate host-level Production isolation.
```

A clear application isolation preflight confirms only the currently requested Deployment Kit-managed footprint is non-colliding. It does not demonstrate host-level Production isolation.

Production backup/recovery/security/deploy/destructive gates remain stronger regardless of colocation.

## Readiness cadence

```text
select environment
→ resolve topology
→ inspect placement-relevant local state
→ show/confirm known facts
→ authorize relevant read-only verification
→ run deterministic application isolation preflight when supported
→ repair only missing prerequisites under explicit write gates
→ ENVIRONMENT READY TO DEPLOY
→ /deploy <environment>
```

For workstation placement there is no remote-access stage. For deferred placement the workflow intentionally stops before verification/provisioning.

## Readiness writes versus deployment writes

Readiness may perform bounded setup writes when separately authorized and supported by installed tooling, such as local configuration, SSH key/agent/trust setup, target-side access setup, runtime/platform preparation, data/backup directories, firewall preparation, or registry/provider credential configuration.

Readiness does **not** hide application deployment inside setup.

Application runtime deployment, release-specific migration, route/port publication, live health/readiness, smoke validation, and release-specific evidence belong to `/deploy` when the installed adapter defines them.

The application isolation preflight is a remote read-only inspection and does not itself authorize any later write.

## Pre-deploy versus post-deploy evidence

Readiness proves only facts that can exist before deployment, such as:

- logical environment/topology selection;
- supported adapter availability;
- local Docker readiness or verified remote target/identity depending on placement;
- target OS/runtime when applicable;
- artifact identity/access;
- deterministic application isolation/collision evidence when supported;
- route/port ownership availability;
- persistence/backup/migration prerequisites;
- deployment lock/recovery capability;
- stronger Production prerequisites.

First-deploy live route, health, smoke, deployed-release identity, and release-specific rollback evidence are post-deploy facts owned by `/deploy`.

## Environment independence

Readiness of one logical environment never proves another environment ready—even if both share one physical target.

Failure of one environment never redirects to another environment, machine, provider, or wider exposure.

Production remains a logical role/policy with stronger gates, not a separate readiness command or a requirement for a dedicated physical computer.

Once ready:

```text
/deploy <environment>
```

`/deploy` verifies current topology/target/artifact evidence, presents the exact installed-tool authorization gate, delegates deterministic mechanics, requires current isolation evidence when the installed adapter defines it, and verifies placement-relevant live evidence.
