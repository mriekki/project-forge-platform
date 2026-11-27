# Optional workstation loopback endpoints and runtime material

The local Deployment Kit supports **opt-in** additional IPv4 loopback TCP mappings and
external read-only runtime-material directories. This is workstation-container
functionality, not a remote/Production ingress feature.

## Deploy interface

The existing primary `--host-port` / `--runtime-port` mapping and HTTP diagnostic
health check are unchanged. An application may add at most eight additional
mappings with repeated `--additional-port HOST_PORT:RUNTIME_PORT`. Every host port
and every container port must be unique, and every host address is fixed to
`127.0.0.1`. The option never accepts a public address or UDP.

Use repeated `--read-only-mount SOURCE::TARGET` for external directories.
For example, for app slug `example` in environment `demo`:

```text
SOURCE: <config_root>/local-materials/example/demo/tls
TARGET: /run/project-forge/material/tls
```

`config_root` is the existing Deployment Kit workstation configuration root.
The Project's setup owns creating and granting the source directory; the Kit
will not create it. Its files must remain outside repositories, build contexts,
application persistence and backup sets. The Kit refuses symlinks anywhere in
the source path or recursively inside the source. It rejects unsafe target
paths, duplicate/overlapping mount sources or targets, and overlapping managed
persistence targets. Directories must contain only ordinary files/directories.

Material is mounted read-only and validated using an isolated disposable
container with the application's numeric `--run-as` identity. The optional
mount feature currently requires an immutable runtime image with `/bin/sh` for
the non-mutating permission probe. If that is unavailable, deployment fails
before replacing an existing container; there is no weaker host-only fallback.
The probe uses `--network none` and `--read-only`, never executes the
application or modifies material, and does not read certificate contents into
Deployment Kit state.

## Review, compatibility and readiness

Absent optional settings do not add spec fields and preserve existing SHA-256
specification hashes and version-one state. Extended configurations use
version-two persisted state. Inventory reads both formats and never rewrites
them. Extended plans contain non-secret source metadata snapshots; detectable
changes between plan and apply require fresh review. Metadata cannot guarantee
detection of all in-place content changes or prevent all filesystem races.

Actual Docker TCP publishing and mounts must match the saved configuration;
unexpected public bindings, missing bindings, changed mount sources, or
unexpected mounts are configuration drift. Preflight checks precede container
replacement. Docker bind races and other late failures are explicit; the Kit
does **not** automatically roll back. Managed SQLite and external material
are never deleted as a result of those failures.

`httpHealthy` remains the existing **HTTP diagnostic** check on the primary
port. It does not prove TLS readiness, certificate identity, authenticated
gateway authority, or application login functionality. Projects opting into
TLS must verify their own authenticated transport and functional readiness.

The additional endpoints are loopback-only. They do not provide phone/device
LAN connectivity or authorize changes to Production ingress. The Kit does not
generate certificates, install trust roots, rotate keys, manage gateway
processes, or migrate application data.

## Opt-in local Auth HTTPS ingress (WSL2)

The Deployment Kit has one narrow exception to the boundary above: an
opt-in local HTTPS runtime for one Auth Kit application on WSL2 Ubuntu using
the Docker Desktop `default` context. It reserves `127.0.0.1:443` and the
exact public origin `https://localhost`; it does not change the Auth Kit's
exact-origin or exact physical Caddy-peer checks. Native Linux/macOS trust
automation, multiple simultaneous Auth apps on this origin, alternate ports,
shared Caddy, LAN access and Production ingress are unsupported.

Use the materialized Deployment CLI and the exact Project-owned immutable
application image:

```sh
python tools/project-forge-deployment/project-forge-deploy.py local https status \
  --owner-repo <owner/repository> --environment <environment> --app-slug <slug>

python tools/project-forge-deployment/project-forge-deploy.py local https plan \
  --owner-repo <owner/repository> --environment <environment> --app-slug <slug> \
  --image sha256:<64-hex-image-id> \
  --env ProjectForge__Authentication__Google__ClientId=<project-client-id> \
  --env ProjectForge__Authentication__Google__ClientSecretFile=/run/secrets/pf-google-client-secret \
  --read-only-mount <protected-host-file>::/run/secrets/pf-google-client-secret
```

`plan` is read-only. `apply` accepts the same application arguments, displays
the current plan, and requires the separate `[LOCAL HTTPS AUTH DEPLOY]`
confirmation. The runtime starts Caddy on a dedicated ingress bridge before
joining its private app bridge, adds the Auth app to that private bridge and
an app-only egress bridge, publishes only loopback 443, and never publishes
the app port. Docker identities, exact memberships, inspected Caddy peer,
mounted config/CA volumes and the exported public CA identity are verified
before reporting readiness. The app runs as UID/GID `1654:1654`; `/api/auth/me`
must respond over TLS with the exported CA. No OS trust change is part of
plan or apply.

The Google secret stays in a Project-owned protected file outside the
repository and is mounted as exactly `/run/secrets/pf-google-client-secret`
with read-only Docker file bind. Do not pass secret bytes through `--env`,
shell history, logs, chat or GitHub. The Project owner remains responsible
for its Google client and exact `https://localhost/signin-pf-google` callback;
the Kit never creates or edits provider configuration.

On WSL2, an owner-only file is not readable by the non-root container. After
creating the secret privately under
`~/.project-forge/local-materials/<slug>/<environment>/` (or the same path
under `PROJECT_FORGE_HOME`), grant the app UID read access without making the
file world-readable:

```sh
chmod 600 <protected-host-file>
setfacl -m g::---,u:1654:r--,m::r-- <protected-host-file>
```

Keep the parent directories private. The runtime checks access before applying
the plan; if `setfacl` is unavailable, install the workstation's ACL tooling
before retrying rather than broadening file permissions.

Trust operations are deliberately separate:

```sh
python tools/project-forge-deployment/project-forge-deploy.py local https trust-status \
  --owner-repo <owner/repository> --environment <environment> --app-slug <slug>
python tools/project-forge-deployment/project-forge-deploy.py local https trust-install \
  --owner-repo <owner/repository> --environment <environment> --app-slug <slug>
```

Trust install requires the exact recorded public root and the distinct
`[LOCAL HTTPS AUTH TRUST WRITE]` confirmation. It writes only the exact
thumbprint to Windows CurrentUser Root. Removal likewise requires the
`[LOCAL HTTPS AUTH TRUST REMOVE]` confirmation and the exact recorded
thumbprint; it never removes other roots. Runtime removal is a third
confirmation-gated action. It removes only the owned Caddy containers,
networks, and Caddy CA/config volumes, preserving the app data volume. Remove
the Windows trust root separately before runtime removal.

Port conflicts, unsupported hosts, missing/changed material, stale CA
identity, or Docker drift are blockers. Do not select HTTP, a different port,
another Docker context, or another trust store as a fallback. Resolve the
reported condition and obtain a fresh plan.

After an interrupted apply, use the confirmation-gated `local https recover`
command before planning again. Recovery removes only verified partial
resources, preserves an exact recorded app-data volume if one exists, and
requires the recorded CA root to be absent from Windows trust before removing
its Caddy volume. Ambiguous identities or a changed Docker engine block recovery.

## Verification

Unit coverage: `PYTHONPATH=src python -m unittest tests.test_local_extensions
tests.test_local_spec tests.test_local_runtime tests.test_local_cli -v`.
Canonical CI uses Python 3.11, compileall, and full unittest discovery.
On an explicitly selected WSL2 workstation with Docker Desktop and .NET 10,
the real Deployment Kit HTTPS lifecycle test can be run with:

```sh
PF_LOCAL_HTTPS_AUTH_DOCKER_CI=1 PYTHONPATH=src \
  python -m unittest discover -s tests -p 'test_disposable_local_https_auth.py' -v
```

It builds a disposable fake Auth endpoint with a fake secret file, exercises
failure/recovery, plan/apply/status, resume and removal, verifies that trust remains uninstalled,
then removes only its UUID-scoped test resources. It does not configure or
contact an OAuth provider. The separate Authentication candidate integration
test exercises the actual Auth Kit middleware behind Docker/Caddy.
Integration acceptance additionally requires disposable Docker fixture proof
of actual bound addresses, read-only denial, non-root readability, source
drift and failed-preflight retention, as well as consumer-owned authenticated
TLS tests. Do not use developer SQLite or real credentials for these tests.
