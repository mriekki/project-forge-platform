# Cloudflare Tunnel public ingress

Status: **PARTIAL — IMPLEMENTED MECHANICS; LIVE DOMAIN/GENERATED-CONSUMER PROOF PENDING**

Project Forge models Cloudflare Tunnel as optional **public ingress**, not as a deployment target or remote-management transport.

The supported shape is:

```text
placement: remote-target
adapter: remote-ssh
exposure: public
ingress provider: cloudflare-tunnel
```

`remote-ssh` continues to own verified workstation-to-target management. Cloudflare Tunnel owns only internet-facing application ingress.

## Architecture

```text
Internet
  -> Cloudflare edge / public DNS / HTTPS
  -> remotely managed Cloudflare Tunnel
  -> cloudflared container on the selected Ubuntu target
  -> shared Project Forge caddy-net
  -> project-forge-caddy:80
  -> existing Project Forge application container
```

The cloudflared runtime publishes no host ports. It initiates outbound connections to Cloudflare and joins the existing shared Docker network.

Public routes do **not** replace the trusted-LAN Route Registry. Each public Cloudflare hostname forwards to the shared Caddy container while setting `originRequest.httpHostHeader` to an already-owned `.local` Project Forge hostname. Caddy therefore reuses the existing Project/environment route and upstream ownership contract.

Example:

```text
inventory.example.com
  -> Cloudflare Tunnel
  -> http://project-forge-caddy:80
     Host: inventory-production.local
  -> existing Caddy route
  -> inventory Production container
```

## Shared versus Project-owned state

The shared ingress scope owns:

- one remotely managed Cloudflare Tunnel identity;
- one cloudflared container;
- the host-side tunnel token;
- the Cloudflare account/zone/tunnel non-secret identifiers;
- the connector Compose definition;
- a host-side public-route ownership registry.

A Project/environment public route owns:

- exact `ownerRepo`, environment, app slug and route ID;
- one exact public hostname;
- one exact existing `.local` origin hostname;
- one exact Cloudflare tunnel ingress rule;
- one exact proxied Cloudflare CNAME record.

Removing a Project route must preserve the shared tunnel, cloudflared runtime, Caddy platform, unrelated DNS records and unrelated Projects.

## Secrets boundary

The Cloudflare API token is workstation-only. It is read from:

```text
PROJECT_FORGE_CLOUDFLARE_API_TOKEN
```

The token is never accepted as a CLI argument and is not written to:

- Git;
- `PROJECT_BOOTSTRAP.json`;
- `DEPLOYMENT_TOPOLOGY.json`;
- the portable Project Forge developer profile;
- the Production host;
- command-line process arguments.

The remotely managed Tunnel token is retrieved only when applying shared ingress. It is streamed through the existing verified SSH operation and written beneath the selected root-owned ingress scope. It is not printed or returned in plans/status.

Re-applying shared ingress force-recreates the cloudflared container after securely replacing the token file, so refreshed Tunnel credentials are actually consumed by the running connector.

## Shared runtime commands

Read-only:

```text
project-forge-deploy ingress cloudflare status <target> --scope production
project-forge-deploy ingress cloudflare doctor <target> --scope production
```

Configure/create/adopt the shared scope after the domain exists:

```text
project-forge-deploy ingress cloudflare configure <target> \
  --scope production \
  --zone example.com
```

The write requires:

```text
[HOST PUBLIC INGRESS WRITE]
```

The default tunnel name is:

```text
project-forge-<scope>
```

An existing tunnel is adopted only when it is remotely managed and has no application ingress rules beyond the final fail-closed `http_status:404` rule. Project Forge never silently takes over a tunnel with existing application configuration.

## Project public routes

Inventory:

```text
project-forge-deploy ingress cloudflare route inventory <target> --scope production
```

Register:

```text
project-forge-deploy ingress cloudflare route register <target> \
  --scope production \
  --owner-repo owner/repository \
  --environment production \
  --app-slug inventory \
  --public-hostname inventory.example.com \
  --origin-hostname inventory-production.local
```

Registration requires:

```text
[PUBLIC INGRESS ROUTE WRITE]
```

Route registration, removal, and post-write recovery hold the target's shared
per-scope lock across preflight and provider writes. This serializes Project
Forge route operations using the same target and prevents one operation's
whole-tunnel configuration rollback from replacing another concurrent managed
route change. Recovery also rechecks the reviewed host binding before reading
or changing provider state; if that binding changed or ownership is uncertain,
it stops and reports the state for inspection instead of attempting rollback.

The target lock coordinates Deployment Kit operations; it is not a Cloudflare
API compare-and-swap and cannot serialize manual or external dashboard/API
edits. Such drift is checked against the reviewed configuration and recovery
fails closed rather than restoring over an unrecognized configuration.

Remove:

```text
project-forge-deploy ingress cloudflare route remove <target> \
  --scope production \
  --owner-repo owner/repository \
  --environment production \
  --app-slug inventory
```

Removal requires:

```text
[PUBLIC INGRESS ROUTE REMOVE]
```

## Route safety

Before publishing a hostname, Deployment Kit verifies:

1. the selected shared Cloudflare ingress scope is ready;
2. the exact Project/environment `.local` route already exists and owns the requested origin hostname;
3. the public hostname is not owned by another managed Project route;
4. the Cloudflare tunnel configuration has the expected final fail-closed 404 rule;
5. no conflicting tunnel ingress rule exists;
6. no conflicting DNS record exists;
7. any existing DNS record exactly matches Project Forge's tunnel target and ownership marker.

The current partial adapter intentionally supports one first-level subdomain beneath the selected zone, such as `inventory.example.com`. Deeper names such as `api.inventory.example.com` require an explicit certificate/support review rather than being silently accepted.

## Domain is deliberately late-bound

A Builder does not need a domain to generate or develop a Project.

Bootstrap may record:

```text
exposure: public
ingress.provider: cloudflare-tunnel
ingress.bindingState: deferred
```

without a zone or public hostname. Once a domain is registered and active in Cloudflare, environment setup/readiness can bind the shared ingress scope and each Project can register its exact public hostname. Regeneration is not required merely to choose the domain later.

The shared Cloudflare zone is environment infrastructure and should not be copied into every Project as a credential-like default. The exact application hostname remains Project/environment state.

## Experimental authenticated public-origin mode

For an isolated test scope, `ingress cloudflare configure` supports `--authenticated-origin`. This explicit opt-in provisions a private Caddy Unix listener and mounts its socket directory only in the pinned cloudflared connector. Public hostname rules use `unix:/run/project-forge-origin/origin.sock` and the public hostname as Host; the LAN TCP listener and the existing default mode remain unchanged. The remote adapter derives each authenticated route's upstream from its still-owned LAN registry entry and strips/replaces forwarding headers before proxying.

**Not a supported Production setting yet:** origin mount possession is not end-user login. Real pinned cloudflared edge-to-app forwarding, canonical client-IP semantics, app proxy-peer trust, socket replacement, and rollback still need live proof. Do not grant the socket mount to unrelated containers or treat forwarded IP headers as an authorization credential.

An existing legacy scope can be migrated without replacing its tunnel, public routes, DNS/CNAME records, or unrelated tunnel rules. The operation has its own read-only plan, exact interactive authorization, and guarded apply:

```text
project-forge-deploy ingress cloudflare migrate-authenticated-origin <target> \
  --scope production \
  --zone example.com
```

Before planning, the operator must stop all Cloudflare dashboard/API tunnel-configuration writers for this scope. The CLI asks for an exact scope-bound freeze-active acknowledgment before making plan reads, and the programmatic planning API requires the corresponding `change_freeze_active_acknowledgement`, for example:

```text
[CLOUDFLARE EXTERNAL CHANGE FREEZE] ACTIVE scope=production
```

The freeze must remain in effect through apply, verification, and any rollback or recovery. It is an external operational prerequisite: the Deployment Kit cannot enforce it, identify all external writers, or prove that they are stopped. Cloudflare's full-configuration PUT has no compare-and-swap; pre-write snapshots and post-write checks do not prevent an external write from racing between a read and PUT. Do not start the operation unless this freeze can be maintained.

The plan requires every host-registered route to match one exact Project Forge legacy provider rule and one exact owned DNS record. Conflicting/unowned rules for managed hostnames, missing or duplicate routes, stale host/provider/DNS snapshots, or incomplete host migration evidence stop the operation. Other provider rules remain unchanged; no DNS write or tunnel creation occurs. Apply holds the existing per-scope host lock, prepares the connector-only socket and sanitized Caddy routes first, then changes only the exact managed Cloudflare rules. It rechecks ownership immediately before each phase and verifies the unchanged tunnel, route and DNS identities plus the socket/header contract afterward. These checks are defense in depth, not enforcement of the external freeze. There is no generic `--yes` bypass; the CLI first requires:

```text
[CLOUDFLARE AUTHENTICATED ORIGIN MIGRATION]
```

After showing the plan, the CLI separately requires the migration authorization and an exact freeze acknowledgment bound to the reviewed scope and snapshot context, for example:

```text
[CLOUDFLARE EXTERNAL CHANGE FREEZE] scope=production context=<plan-specific digest>
```

The programmatic apply API likewise requires `change_freeze_acknowledgement`; migration authorization alone is insufficient. The bound acknowledgment prevents accidental reuse for a different scope/plan, but is an operator assertion only—not a lock on Cloudflare. If the provider update is confirmed unchanged, a newly prepared host phase is rolled back from a protected host receipt. If provider state is uncertain or differs from both reviewed states, the host remains authenticated with its receipt retained; maintain the external freeze and do not hand-edit or rerun blindly. Re-plan/resume or roll back only after inspecting current state; keep the freeze until recovery is complete. This migration still does not establish an application identity/login flow or replace disposable application/database state.

Final migration output labels its evidence **structural-only**: it checks socket metadata, connector mount configuration, Caddy configuration, and the generated sanitized route files. It does not prove that the running pinned cloudflared connector can forward an HTTP request over that socket or that an application receives the intended headers. Live socket forwarding and end-to-end readiness remain unproven.

See `docs/EXPERIMENTAL_AUTHENTICATED_ORIGIN.md` and issue #78 for the detailed evidence boundary. For a new isolated scope, `configure --authenticated-origin` and the normal route gates remain unchanged.

## Current cloudflared runtime

The first partial implementation selects Cloudflare release `2026.10.4` and pins the actual Docker pull to the verified multi-platform image index digest:

```text
cloudflare/cloudflared:2026.10.4@sha256:c6c7ae1d5dfdcb094ad344ed68ccffc26635c9c6be80965664c33baf064b0515
```

`latest` is never used, and a mutable tag is not the final runtime identity. Promotion from `partial` to `supported` remains blocked until the package/release process and unrelated generated consumers prove this pinned artifact together with the live Cloudflare integration path.

## Required live proof before support promotion

At minimum:

1. create/adopt a real remotely managed Tunnel without manually logging into the Ubuntu host;
2. install cloudflared through verified Project Forge SSH and prove no inbound host/router port is required;
3. publish a real first-level hostname and verify external HTTPS reaches the expected Project container;
4. publish a second unrelated Project through the same shared scope and prove isolation/collision checks;
5. remove one Project route while preserving the other Project and the shared tunnel;
6. exercise DNS/provider failure rollback;
7. exercise changed host/provider state and prove stale plans fail closed;
8. prove separate logical Production/Staging scopes when both are configured;
9. prove generated/default-branch CI and human workspace acceptance.

Tunnel connector health alone is not sufficient application evidence. Final Production readiness must include an external HTTPS application probe.

## Deliberate V1 exclusions

- Cloudflare Access / Zero Trust identity policy;
- wildcard DNS publication for arbitrary applications;
- direct public router/firewall fallback;
- automatic domain purchase or registrar mutation;
- deeper-than-first-level public hostnames;
- implicit adoption of existing unmanaged Tunnel/DNS rules;
- deleting a shared Tunnel as part of normal Project tear-down.

These remain separate capabilities or future decisions.
