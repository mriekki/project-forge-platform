# Generated Project Auth API and Google/Resend setup

**Status:** reference consumer code, not a Production-qualified release.
The Authentication Kit is a separately managed component. An approved
`householdAuth` Bootstrap selection copies the tested
`samples/ProjectForgeAuth.Api` starter into a new Project's
`src/ProjectForgeAuth.Api` and leaves its pinned, reusable domain/runtime/
transport source under `tools/project-forge-auth-kit/`.

Normal Projects use the standard package profile and do not receive this
capability. Household-enabled Projects use the explicit internal package
profile `greenfield-household-project`. This is **not** a different
user-facing New Project start mode.

## Separate application ownership

The host is a working ASP.NET Core 10 reference API using per-Project
SQLite, invite-only account admission, Google OIDC code + PKCE,
issuer/audience/state/nonce validation through ASP.NET middleware,
cryptographically random hashed invitation and opaque session tokens,
authenticated per-Project APIs, antiforgery checks, and strict exact
Caddy-to-application transport validation.

The application owns its account IDs, SQLite database, private
DataProtection key ring, sessions, initial admin, Google OAuth client,
and Resend sending key. The Household Registry serves only authorized
shared infrastructure references and Developer/household membership.
The Registry is not contacted during application login and does not
grant automatic access.

## Required protected Project configuration

Use a protected configuration mechanism already supported by the Project.
Never commit these values to Git, `HOUSEHOLD_AUTH_SETUP.json`, chat, logs,
or GitHub Actions:

- `ProjectForge:Authentication:DbPath` — private, per-Project SQLite path
- `ProjectForge:Authentication:DataProtectionKeysPath` — persistent
  owner-only directory for OIDC state/correlation and external cookies
- `ProjectForge:Authentication:Google:ClientId` — unique OAuth client ID
- `ProjectForge:Authentication:Google:ClientSecret` — private client secret, **or** `:ClientSecretFile` — absolute path to a protected secret file (never both)
- `ProjectForge:Authentication:PublicOrigin` — exact public HTTPS origin
- `ProjectForge:Authentication:TrustedProxyIp` — exact reviewed Caddy peer
- Optional `ProjectForge:Authentication:Resend:ApiKey` (or
  `:ApiKeyFile`, an absolute protected secret-file path) and `:From`
  — **both required together** for automatic invitation delivery with a
  separately scoped Project email key and a verified sender address.
  The inline and file forms must never be configured together.

The Google OAuth callback is
`https://<approved-public-origin>/signin-pf-google`.
The app's TLS, Caddy network, Cloudflare Tunnel and exact trusted-peer
reconciliation remain Deployment Kit operations. Do not trust a Docker
subnet, direct LAN requests, forged X-Forwarded headers or an
unreviewed proxy address.

### Optional workstation HTTPS

Deployment Kit can provide opt-in `https://localhost` ingress for one local
Auth application on WSL2 Ubuntu with Docker Desktop. This does not change
Authentication's exact-origin or exact physical-peer middleware: the app
still accepts forwarded request authority only from the inspected Caddy
container peer on its private Docker bridge. The app has no published host
port; Caddy alone binds `127.0.0.1:443`.

The Project owner must configure its own Google client with the exact
`https://localhost/signin-pf-google` callback and keep the client secret in a
protected file mounted read-only beneath
`/run/secrets/pf-google-client-secret`. Deployment Kit does not create or alter OAuth
clients. Installing the Caddy public root into Windows CurrentUser Root is an
independent, exact-thumbprint operation requiring its own authorization; plan,
apply, and status do not change operating-system trust. See the Deployment
Kit [workstation HTTPS contract](../../../packages/deployment/docs/LOCAL_WORKSTATION_EXTENSIONS.md#opt-in-local-auth-https-wsl2)
for supported commands, lifecycle and limits.

Bootstrap writes a non-secret `HOUSEHOLD_AUTH_SETUP.json` with
`requires-reviewed-provider-bindings`. The application refuses startup
without a complete reviewed configuration. The reference backend is
built locally/CI with:

```sh
dotnet restore src/ProjectForgeAuth.Api/ProjectForgeAuth.Api.csproj
dotnet build src/ProjectForgeAuth.Api/ProjectForgeAuth.Api.csproj --no-restore
```

## One-time administrator setup

Only from a protected, reviewed local host session, preconfigure
`PF_INITIAL_APP_ADMIN_SUBJECT` with the exact intended Google subject
and `PF_INITIAL_APP_ADMIN_EMAIL` with that verified identity's address,
then execute the host's `admin-init` command with the correct protected
per-Project database path. No public endpoint may create the first admin.
Repeated bootstrap is rejected; never infer administrator status from
Household Registry Developer membership.

## Invitation flow

With a verified administrator session, the reference UI can create a
48-hour one-time Project invitation for a Google email address.

With Project-specific Resend configuration, the API sends the token to
the invited address using the fixed HTTPS Resend API and a deterministic
hashed idempotency key. No invitation token is returned to the browser,
stored in the Registry, or placed in a URL. Provider failures return
generic failure; use separate reviewed retry/recovery processes.

Without a configured Resend sender, the administrator may receive the
one-time token through the secured authenticated API and share it
privately. The invited user enters the token in the browser form.
Google issuer, immutable subject and email verification are checked
before admitting the Project account. Email-only matching never grants
access. Sign-in creates an opaque seven-day Project session, not a
Registry session.

## Disposable container deployment (review-only templates)

The Auth Kit now includes
`samples/ProjectForgeAuth.Api/Dockerfile` and
`deploy/disposable-project-auth.compose.yml`. They package the actual
reference API and attach it to an **already reviewed exact Caddy network**
without publishing any host port or changing DNS, Caddy, Cloudflare,
Google or Resend. The API uses its own SQLite database and key ring;
the image's fixed non-root application user must be able to write its **disposable only**
`/data` directory. Do **not** point it at the PWA or Registry volume.
The existing PWA Unix-socket origin and production tunnel ingress must
remain untouched.

The operator must first obtain an authorized, **separate** disposable
HTTPS hostname, dedicated Google web OAuth client with callback
`https://<approved-disposable-hostname>/signin-pf-google`, reviewed
physical Caddy peer and exact network, a private data directory, and a
protected local Google client-secret file. No new credential, public
hostname, DNS route or provider write is authorized by this template.
Never fabricate the peer IP or silently route through the existing PWA
hostname.

Set these reviewed non-secret deployment inputs in a trusted private
host session: `PF_AUTH_DISPOSABLE_DATA_DIR`, `PF_AUTH_GOOGLE_CLIENT_ID`,
`PF_AUTH_PUBLIC_ORIGIN`, `PF_REVIEWED_CADDY_IP`, and
`PF_CADDY_NETWORK`. Set
`PF_AUTH_GOOGLE_CLIENT_SECRET_FILE` to a separately protected local
file outside Git. Keep the `PF_AUTH_DISPOSABLE_DATA_DIR` and any
local evidence paths private. The base Compose file has **no Resend
sender** and is safe to inspect without sending email.

From the Auth Kit checkout, use the *non-mutating* composition check
after all required values have been independently reviewed:

```sh
docker compose -f deploy/disposable-project-auth.compose.yml config --quiet
```

After an explicit deployment authorization, the same Compose file may
be used to start a disposable instance. First qualify the exact
physical peer/Caddy route, public origin, real Google callback,
administrator identity and negative spoofing paths. The template
does **not** deploy a Caddy route or prove Google login by itself.

Only for a separately approved test-email acceptance, add
`deploy/disposable-project-auth.resend.compose.yml` **after** setting
`PF_AUTH_RESEND_FROM` and `PF_AUTH_RESEND_KEY_FILE` to the approved
disposable Project's verified sender and protected Project-scoped
sending key. Its overlay adds a `/run/secrets/resend_project_key`
mount and turns on Resend invitation delivery. Run `config --quiet`
with both `-f` files to validate the combined settings before any
authorized send. Do not reuse the PWA or Registry's keys, and never
put secrets on the CLI or into GitHub reports.

Rollback is isolation-first: stop the disposable app, remove any
separately approved test DNS/Caddy ingress through Deployment Kit's
reviewed rollback, revoke the disposable credentials and retire
disposable state only after preserving required acceptance receipts.
PWA authentication, its hostname, and its data must remain unchanged.

## Exact reviewed shared-host route binding (disposable)

The existing host has a Kit-owned Caddy container `project-forge-caddy`
attached to the external Docker network `caddy-net`. The reviewed
physical peer was `172.19.0.2`; that IP is **observed, not permanent**.
Before each actual change, inspect the current exact container/network
identity and rerun the normal Deployment Kit plan. Do not pin an old peer
after Docker/network reconciliation.

The disposable Compose service has the stable container name
`project-forge-auth-test--disposable`. The proposed **separate** route
ownership is:

| Layer | Reviewed proposed value |
| --- | --- |
| Host target | `production` (shared Ubuntu host; not PWA Production state) |
| Owner repository | `mriekki/project-forge-auth-kit` |
| Environment | `disposable` |
| Application slug | `project-forge-auth-test` |
| Route ID | `project-forge-auth-test--disposable` |
| Caddy upstream | `project-forge-auth-test--disposable:8080` |
| Trusted-LAN route | `project-forge-auth-test-disposable.local` |
| Public hostname | `auth-test.nalasuniverse.com` |
| Existing Cloudflare scope | `production` (must first reverify current authenticated-origin state) |
| Google callback | `https://auth-test.nalasuniverse.com/signin-pf-google` |

These are **proposed bindings**, not completed registrations. The route
IDs are unique and must be checked against the fresh host inventory before
registration. The existing PWA route and `mealplanner.nalasuniverse.com`
remain under their original owner.

**Read-only host/secret staging preflight:** after the PWA's Deployment
Kit SSH-agent session is working, use Auth Kit's pinned branch tooling from
the trusted local WSL2 workstation (the example assumes the current directory
is the Auth Kit checkout and the PWA checkout is at the existing WSL2 path):

```sh
cd "$HOME/Developer/Projects/fmp"
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$HOME/Developer/Projects/project-forge-auth-kit/tools/disposable_project_auth_host_preflight.py" \\
    --pwa-checkout "$PWD" --expected-caddy-peer 172.19.0.2
```

Adjust the **Auth Kit checkout path** to the actual trusted clone; never
assume it exists. The reviewed peer value is an example from the
2026-11-13 observation, not a permanent default. This command uses the
existing strict target identity, verifies current managed Caddy/network
and the PWA-owned LAN route, tests remote Docker/Compose availability,
checks that the disposable container and namespace are absent, and
checks only the **local** secret file owner/mode/size. It does not read
the secret contents, transfer credentials, configure OAuth, create
host files or query Cloudflare DNS. It fails closed on stale identities
or collisions. Successful preflight is **not** deployment permission.
Any new host-stage command must separately protect remote data/secret
permissions (non-root app user, private data directory, root-owned
Project-only secret) and preserve every existing PWA service.

**First explicit host-stage write (not application deployment):** when the
read-only preflight has completed with every positive gate true and
`mutated=false`, run the Kit's separately authorized staging program.
It rechecks the exact Caddy identity and exclusively creates a new,
**disposable-only** host namespace. The OAuth client secret travels from the
protected WSL2 file over the verified Deployment Kit SSH channel's stdin.
The secret is neither included in remote command arguments nor copied to Git.
The resulting file is root-owned, group-readable only by the ASP.NET
application UID/GID 1654 (`0640`); its parent directory is root-only.
The app's dedicated data directory is owned by 1654, private (`0700`).
All paths are new and fail closed on collision or symbolic links.

The command below assumes `AUTH_KIT_CHECKOUT` is the current, inspected
Auth Kit checkout. Set it to your actual clone directory (not a made-up
relative path). It uses a previously reviewed exact Caddy container/network
baseline; **refresh those identifiers if the host changes**.

```sh
cd "$HOME/Developer/Projects/fmp"
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$AUTH_KIT_CHECKOUT/tools/disposable_project_auth_host_stage.py" \\
    --pwa-checkout "$PWD" \\
    --expected-caddy-container-id b1f1916698ee9b76b8e1cceeec38beaa495369ce49a5ee741a2971519b67aaaf \\
    --expected-caddy-network-id 96dbe39067aa21441cd796cb8363d45b07c324f22e8ca42cda8ef67ed6beac2f \\
    --expected-caddy-peer 172.19.0.2 \\
    --apply
```

**Review before running:** `--apply` is the explicit authorization for a
new directory and a credential file on the shared Ubuntu host. Without it,
the command prints only a non-mutating plan. The local Google secret must
already be stored as
`~/.local/share/project-forge/disposable-auth/secrets/google-client-secret`.
The program never prints the credential or includes it in an SSH command.
It will not create routes, containers, DNS, Google clients, Registry
members or PWA records. A stage failure may leave a partial protected
disposable namespace; **do not rerun blindly**. Inspect exact stage-owned
paths and reconcile under a separate reviewed recovery action.

A successful receipt `state=staged` establishes only host data directory
and secret placement. The reference API source/build context, container
image, Compose installation, live Caddy route and public hostname are
**not** staged or deployed by this operation. Those remain separately
reviewed phases; never treat a successful credential stage as a passed
live Google login or a supported authentication release.

**Source-pinned disposable image build and launch (separate write phase):**
After a successful `state=staged` host receipt, the Auth Kit's
`tools/disposable_project_auth_launch.py` can build a dedicated image from
only four committed Auth Kit source directories and launch it. It uses the
**same exact existing Deployment Kit SSH target**, checks the reviewed full
Caddy container and network IDs, checks the independent host-stage receipt
and secret/data metadata, and requires a specific reviewed Git commit.
Source travels as a `git archive` streamed to remote `docker build`
standard input, not as a persistent host checkout; no secret is included
in the archive or Docker build. The image gets its own deterministic
disposable tag; build may access approved public .NET dependencies.

The container starts non-root (`1654:1654`) on external `caddy-net`
with `--read-only`, `--cap-drop ALL`, no-new-privileges, a private
`/tmp` tmpfs, and a separate durable `/data` bind. The Google
credential is mounted as a read-only protected **file** and is never
added to Docker argv, image layers or environment variables. The launch
spec declares port 8080 internally but **publishes no host ports**.
There is no Resend sender, no first-admin bootstrap, and no Google
callback from this launch alone.

Run this from the current trusted PWA checkout using a newly cloned Auth
Kit feature branch. Use the **exact Git commit just independently reviewed
for that branch**, not a blind local HEAD:

```sh
cd "$HOME/Developer/Projects/fmp"
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$AUTH_KIT_CHECKOUT/tools/disposable_project_auth_launch.py" \\
    --pwa-checkout "$PWD" \\
    --auth-kit-checkout "$AUTH_KIT_CHECKOUT" \\
    --expected-auth-commit "$REVIEWED_AUTH_KIT_COMMIT" \\
    --expected-caddy-container-id b1f1916698ee9b76b8e1cceeec38beaa495369ce49a5ee741a2971519b67aaaf \\
    --expected-caddy-network-id 96dbe39067aa21441cd796cb8363d45b07c324f22e8ca42cda8ef67ed6beac2f \\
    --expected-caddy-peer 172.19.0.2 \\
    --apply
```

`--apply` is the explicit authorization for **Docker image creation
and disposable container launch only**. Omit it to review the exact
readiness plan without writing. It will not mutate Caddy, Cloudflare,
the PWA, the Household Registry, or any application route. The complete
image SHA256 and container ID in its non-secret receipt must be retained
as release acceptance evidence. If build/launch fails or the container
exits, **do not blindly rerun**: a tagged image or stopped container may
remain and requires scoped inspection/reconciliation first.

An image and container running after the startup grace period is
**not proof of HTTP readiness, live Google identity or inbox
delivery**. Subsequent owned LAN route, authenticated Cloudflare
public route, Google callback and invitation tests retain their own
release gates. Reinspect the exact physical proxy IP immediately
before route registration; do not broaden proxy trust.

**Running container verification and isolated LAN route:** After the
image/container receipt confirms exact source revision and no published ports,
run the **read-only** `tools/disposable_project_auth_runtime_probe.py`
from a trusted current Auth Kit checkout, via the PWA's verified Deployment
Kit SSH-agent session. It verifies the launched container's exact image,
revision and network identity, then connects to its private bridge IP from
the Ubuntu host. Both a direct request without forwarding and a direct
request with forged forwarding headers must return **403**; requests from
the unreviewed host physical peer must not bypass the Caddy-only trust
boundary. Expected successful state:
`ready-for-isolated-lan-route`, `mutated=false`.

The read-only probe uses the **specific, already verified disposable
container** receipt of 2026-11-13: Docker container
`b01e6838104d2fe0f7de61712452b4551ed08c1abbb29c9464efadc31a76f0f9`
and image
`sha256:aef68c599763576938c4241d77f5ad466fe530e2c32799c6fc1e9b107efeca3c`,
built from commit `838efecd406b83b01664f3c9e99749dd9dc0be91`.
If that instance is replaced or restarted with a different image/container,
do not reinterpret a failure as success; update reviewed receipt evidence
under a separately approved action. A 403 proves origin peer rejection
only—not health through Caddy or live Google sign-in.

Only after this probe passes and shared platform/route inventory remains
unchanged should the Deployment Kit register the **separate internal
application route**. Its existing plan-and-confirmation write gate applies:

```sh
cd "$HOME/Developer/Projects/fmp"
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-session production -- \\
  route register production \\
    --owner-repo mriekki/project-forge-auth-kit \\
    --environment disposable \\
    --app-slug project-forge-auth-test \\
    --upstream-container project-forge-auth-test--disposable \\
    --upstream-port 8080 \\
    --hostname project-forge-auth-test-disposable.local
```

Review the printed change plan; approve only the new
`project-forge-auth-test--disposable` route, not an update to the
PWA route. The command requires the Deployment Kit's explicit
`[ROUTE WRITE]` confirmation. Do not add the public Cloudflare
hostname through the LAN command. The LAN route is an owned
Caddy upstream prerequisite only; in authenticated-origin mode,
the **public** route's Caddy handler must still pass the strict
Host and forwarding contract. Verify that independently before
claiming successful authentication.

**Cloudflare API credentials for this route:** A token that can read the
existing tunnel configuration but receives HTTP 403 when listing DNS
records is **insufficient**, even for read-only planning. Do not
attempt `--apply` with it. The existing WSL2
`PROJECT_FORGE_CLOUDFLARE_API_TOKEN`, if set, is preferred for plan-only
reads over the narrower `PF_CF_READ_TOKEN`; selecting it does **not**
authorize a write. To inspect configuration without printing secrets:

```sh
if [[ -n "${PROJECT_FORGE_CLOUDFLARE_API_TOKEN:-}" ]]; then
  echo "Reusable route token already set (value not shown)."
else
  echo "No existing route token set in this shell."
fi
```

A provider-supported single appropriately scoped route token needs
**Zone: Zone Read** for listing the exact zone, **Zone: DNS Edit** for
listing/creating the exact test CNAME, and **Account: Cloudflare Tunnel
Edit** (or corresponding current Cloudflare One connector write grant)
for reading/updating the existing remotely managed tunnel. Limit to
the known `nalasuniverse.com` zone and reviewed Cloudflare account;
prefer the shortest suitable lifetime. An existing token with equivalent
permissions can be reused; do not create another solely to obtain a new
secret. Never paste API tokens into chats, issue comments, shell
arguments or tracked files. Set the token in the current private shell
using `read -rs` and `export` when a new credential is actually
necessary. Re-run read-only planning before any explicit write gate.

**Separate public Cloudflare route — read-only review first:** After
the owned LAN route inventory lists `project-forge-auth-test--disposable`,
use `tools/disposable_project_auth_public_route.py` from the current Auth
Kit feature branch. It delegates to the **existing PWA Deployment Kit's**
`cloudflare_ingress.plan_public_route` and
`cloudflare_route_apply.apply_public_route`; no independent/unmanaged
Cloudflare mutation code is used.

The review accepts only the verified `project-forge-production`
authenticated-origin tunnel, zone `nalasuniverse.com`, exact Auth Kit
owner/environment/route, current PWA Unix-socket ingress, unowned test
DNS name, unchanged non-ingress configuration, unchanged existing ingress
rules, and the final 404. Existing provider configuration may include
unrelated rules; they must be preserved, not replaced. Its summary hides
raw provider configuration, API credentials and existing DNS records.

In the **same trusted WSL2 SSH-agent session**, with a locally available
read-only Cloudflare token in `PF_CF_READ_TOKEN`:

```sh
cd "$HOME/Developer/Projects/fmp"
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$AUTH_KIT_CHECKOUT/tools/disposable_project_auth_public_route.py" \\
    --pwa-checkout "$PWD"
```

If this read-only plan returns `state=blocked`, it now reports the
specific `stage` and sanitized `category`, not the raw Cloudflare
error. A `dns-read` / `cloudflare-permission-denied` result means
the **read token cannot read DNS records** at this zone; a read-only
tunnel-config success does not imply DNS list access. A
`strict-plan-review` / `strict-contract-mismatch` result means the
reviewed route or existing PWA ingress does not match the expected
exact state and must be investigated, **not bypassed**. The
`managed-lan-route`, `managed-public-routes`,
`tunnel-config-read`, and `kit-plan` stages distinguish the other
bounded preflight dependencies. These checks never grant write
permissions or activate a public hostname; they only classify which
reviewed dependency failed. If blocked, do not try `--apply` or
change an existing PWA route.

This prints `ready-for-explicit-public-route-registration` if the
reviewed change would append **only** the Auth Kit's
`auth-test.nalasuniverse.com` authenticated Unix-socket ingress to the
shared tunnel, alongside an owned DNS CNAME. **It makes no provider or host
writes.** A read token with insufficient DNS read access may block the
plan; do not assume an unverified hostname is available.

Only after inspecting the exact printed plan should the operator
consider running the *same* command with `--apply`. That mode requires
a **separate** locally configured `PROJECT_FORGE_CLOUDFLARE_API_TOKEN`
with the necessary reviewed DNS and tunnel edit authority and an
interactive terminal. The operator must enter the exact Kit
`[PUBLIC INGRESS ROUTE WRITE]` confirmation. Provider changes are made
only by the Deployment Kit's existing transaction-locked, verified,
post-write-recovery path. The edit token remains in the trusted WSL2
process environment, never Git, chat, Docker or printed plans.

A successful public-route receipt **does not** prove public HTTPS,
the app's strict forwarded-header contract, Google OAuth redirect,
initial administrator bootstrap, or email delivery. These are separate
live checks. A failed or ambiguous apply must be inspected before retry;
do not edit or remove shared `project-forge-production` tunnel rules or
the existing PWA entry manually.

**Order of operations (independent explicit approvals at write boundaries):**

1. Revalidate exact Caddy peer, current shared network, and both route
   inventories. Confirm the proposed hostname is not already used by
   managed or unmanaged DNS/ingress; DNS non-resolution alone is not proof
   of ownership. Review the existing Cloudflare `production` scope's
   authenticated-origin mode. The accepted PWA configuration uses
   `unix:/run/project-forge-origin/origin.sock`; do not replace it.
2. Stage the **separate** app-only private directory and Google secret
   on the reviewed Ubuntu host. A WSL2-only secret file is not magically
   available in remote-host Docker Compose. Transfer any approved secret
   through an established protected host workflow, never Git or a public
   PR. Verify the image user can write only the disposable data directory.
3. Build/launch only the disposable service with **no host-published
   port**, then verify its exact container/network peer, restart and health.
   Do not start it using the PWA-owned Production release/deploy scripts.
4. Use the **existing Deployment Kit** route-registry planning and write
   gate for a new, owned `.local` Caddy route with the exact spec above.
   Do not route public DNS to an unverified application.
5. After the LAN route is registered and the authenticated Cloudflare
   origin is reverified, use the Deployment Kit's **separate** public-route
   plan/authorization for the proposed hostname and origin. That plan
   must preserve every existing ingress rule (including the PWA Unix
   route), the final 404 rule, and other DNS records. Do **not** hand-edit
   Caddyfiles or tunnel configuration. The previously created Cloudflare
   Zone/Tunnel **Read** token cannot authorize DNS or Tunnel writes; any
   write credential and action require separate explicit review.
6. Only then perform real Google OIDC callback acceptance. Initial
   Project administrator provisioning requires a separately verified
   exact Google subject; no first-visitor privilege and no email-only
   binding. Keep the Resend sending overlay disabled until a distinct
   approved email test.

**Rollback:** Remove only the owned disposable public route via the
Deployment Kit's exact route-removal procedure, then the owned LAN route;
stop the disposable application; retain a private evidence/rollback
receipt. Do not tear down shared Caddy, cloudflared, their network,
existing tunnel, the PWA route, or the PWA app/data.

## Exact disposable recovery after host restart — separate write gate

The operator's 2026-11-13 read-only receipt establishes that the
**original disposable Auth Kit container is exited** and has Docker
restart policy `no`. The existing managed Caddy **container ID** and
Docker **network ID** are unchanged, but the Caddy bridge IP moved from
`172.19.0.2` to `172.19.0.4`. The shared cloudflared connector
and Caddy are running. This explains the Auth Kit public 502 and
requires both restarting the isolated backend **and** replacing its
immutable `TrustedProxyIp` setting: a blind `docker start` would
retain the obsolete trusted physical peer. The earlier PWA public
`403` is not an authorized reason to change the PWA.

`tools/disposable_project_auth_recover.py` is an exact **one-off**
reviewed recovery helper for this initial disposable instance. By
default it only prints a plan. Before any mutation it verifies the
Deployment Kit's current Caddy image/network/peer, shared connector,
existing managed PWA/Auth Kit LAN and public-route inventory, original
stopped container full ID/source/image/owner, original isolated Docker
configuration, protected data/secret mounts and stage receipt, and an
available backup name. It uses the original image and the same private
SQLite, keyring and Google client secret files; neither image build nor
credential replacement is needed.

From the already trusted workstation and Deployment Kit SSH-agent:

```sh
cd "$HOME/Developer/Projects/fmp" || exit
git -C "$AUTH_ROUTE_DIR/auth-kit" pull --ff-only || exit

python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$AUTH_ROUTE_DIR/auth-kit/tools/disposable_project_auth_recover.py" \\
    --pwa-checkout "$PWD"
```

Only after the operator reviews an exact
`state=ready-for-exact-disposable-recovery` plan, the same command may
be invoked with `--apply` and the explicit interactive phrase
`[DISPOSABLE AUTH RECOVERY WRITE]`. The approved narrow operation
renames the original **stopped** container to a reserved backup name,
starts a replacement using the same reviewed original image and data,
sets the exact newly validated physical Caddy peer to
`172.19.0.4`, and applies `--restart unless-stopped`. It rechecks
all original host guards immediately before its Docker writes. The
private authenticated-origin Unix socket must then answer `401` for
an anonymous Caddy-routed request. The resulting receipt sets
`livePublicHttpsVerified=false` until separately tested from the
workstation. The previous stopped container is preserved for rollback;
its data directory and secret remain Project-owned and are not copied
or written by the helper.

The `unless-stopped` policy improves survival of Docker daemon
restarts (<https://docs.docker.com/engine/containers/start-containers-automatically/>),
but does **not** make the authenticated physical Caddy IP stable.
A future Caddy IP change still requires reviewed exact-peer convergence.
That durable identity/lifecycle improvement belongs to the canonical
Project Forge Deployment Kit, not a permanent untracked edit inside
this consumer.

If the plan is blocked, the image is unavailable, host identity changes,
or the replacement fails after the old container is renamed, **stop**;
inspect the retained original backup and the exact Docker name before
another attempt. Do not automatically remove either container, reuse
PWA private resources, change shared Caddy, or loosen transport trust.

## Caddy identity rollover: status-only recovery check

After the operator observed public Auth Kit HTTP 502, the original
`disposable_project_auth_socket_probe.py` safely refused to continue
because managed Caddy's container identity changed from the previously
reviewed exact baseline. In the same operator run, the existing PWA
hostname returned public HTTP 403; this alone does **not** establish
that the PWA is down (it may enforce request admission rules).

The current probe now calls the Deployment Kit's **read-only** verified
`platform_proxy_peer` against the previous full Caddy container/network
IDs and configured peer IP. When Caddy has been recreated, it reports
`reviewedCaddyIdentityChanged`, validated
`currentCaddyIdentity`, and the disposable app's explicit
`appContainerStatus`, restart policy, Caddy/cloudflared states.
The embedded private-socket probe retains the old pinned identity
check and does **not** attempt private-socket traffic against a new
unreviewed Caddy container. No trust configuration or application
route is automatically rewritten.

Rerun this revised read-only probe (as documented below) before deciding
whether the disposable container alone should be restarted or a
separate reviewed Caddy peer convergence is needed. Do not re-use
the old peer IP as proof of the new Caddy's physical identity, and do
not treat public 403 or 502 as proof that Google login is broken.

## Next-day public 502 versus Python-style 403 — availability triage

On 2026-11-13 the operator repeated public HTTPS tests twice: normal
`curl` returned `502` from **all three** Auth Kit API endpoints,
while a `Python-urllib` User-Agent request returned `403`.
Previously a plain public `curl /api/auth/me` returned the correct
`401`, and the protected Caddy Unix-socket diagnostic returned
`401` for the canonical request, `403` for the missing-client-IP
request, and `404` for an unrelated host.

**Do not infer a Google callback failure from a 502.** These are
different symptoms: a 502 means the public request cannot be completed
through the origin/upstream path; a 403 for a particular client can be
a separate edge filtering or strict-transport rejection. The initial
disposable container was explicitly created with Docker
`--restart no`, so a subsequent daemon or host reboot could leave
the exact disposable container stopped without affecting existing
public DNS/route ownership. This is a hypothesis to verify; there is
not yet an operator receipt showing a stopped container.

Re-run `disposable_project_auth_socket_probe.py` unchanged through
the verified PWA Deployment Kit `target agent-run production` wrapper.
Its revised read-only output includes `appContainerStatus`,
`appRestartPolicy`, `caddyRunning`, `cloudflaredRunning`, and
`cloudflaredAttachedToCaddyNetwork`, along with existing exact
Caddy/app identity, authenticated Unix-socket and public HTTPS checks.

- If assessment is `disposable-auth-container-not-running` and
  `appRestartPolicy=no`, inspect the **same exact** container ID/image,
  read-only volumes, network and origin route before requesting one
  separately authorized, narrowly scoped container start.
- If the disposable container is running but Caddy or cloudflared is
  not, investigate the unavailable shared service without blindly
  restarting or modifying shared infrastructure.
- If Caddy's canonical request is 401 but public requests remain 502,
  investigate tunnel connector/origin routing and Cloudflare edge
  independently. Confirm that the existing PWA hostname is still
  responding without assuming its status code.
- Do not troubleshoot Google login or reissue OAuth/Cloudflare tokens
  until the public `/api/auth/me` request consistently returns 401.

No DNS rewrite, route re-registration, secret replacement, Caddy
transport relaxation or PWA production deployment is authorized by
this diagnostic.

## Public 403 routing diagnosis — read-only, no Caddy changes

After the 2026-11-13 live public HTTPS probe returned **403 for all
three** `/api/auth/me`, `/api/auth/csrf`, and `/api/auth/google`
endpoints, do not reconfigure Google or weaken the strict origin
middleware. A 403 from Auth Kit's early transport middleware is
indistinguishable by status alone from a separate Cloudflare edge
challenge or policy rejection.

`tools/disposable_project_auth_socket_probe.py` is a **read-only**
diagnostic that uses the PWA Deployment Kit's exact SSH target and
rechecks managed Caddy and disposable app container identities and
Cloudflare public route ownership. Through the authenticated-origin
Unix socket, it makes three bounded GET `/api/auth/me` requests:

- Correct test hostname plus **synthetic** `CF-Connecting-IP:
  198.51.100.42` (reserved documentation address) — expect **401**
  when the Caddy -> application forwarding contract is working.
- Correct test hostname without `CF-Connecting-IP` — expect **403**
  from the application transport guard.
- Unrelated hostname with synthetic client IP — expect **404** from
  Caddy's fail-closed public listener.

It separately makes one TLS-validated public HTTPS GET to the exact test
`/api/auth/me` endpoint, reporting only the numeric status and
boolean Cloudflare challenge/header fingerprints. It never outputs
headers, cookies, raw bodies, source IP addresses, tokens or OAuth
state, makes no database writes or login challenges, and changes
neither Caddy nor PWA/provider routes. It requires the already observed
test container/image/Caddy identities and refuses to silently probe a
replacement container.

```sh
cd "$HOME/Developer/Projects/fmp" || exit
git -C "$AUTH_ROUTE_DIR/auth-kit" pull --ff-only || exit
python3 tools/project-forge-deployment/project-forge-deploy.py \\
  target agent-run production -- \\
  python3 "$AUTH_ROUTE_DIR/auth-kit/tools/disposable_project_auth_socket_probe.py" \\
    --pwa-checkout "$PWD"
```

If the synthetic canonical request also returns 403, investigate the
exact Caddy/ASP.NET forwarding contract. If canonical reaches 401 but
public still gets 403, investigate Cloudflare-edge policy/header
delivery without changing the trusted Caddy peer. Caddy's
`reverse_proxy header_up -CF-Connecting-IP` strips that header from
the **upstream** request; it is not itself proof that the original
`http.request.header.CF-Connecting-IP` placeholder was lost. Any
confirmed reusable Caddy/forwarding bug must be fixed in the canonical
Deployment Kit owner with tests and separately reviewed host rollout.
No shared Production PWA proxy changes are justified by 403 alone.

## Recovered public HTTPS — 401 / 200 / 302 and client-specific 403

Following exact recovery of the isolated container (new Docker ID
`fbcd0420d33dd3bae594294c49e96ee8cce4bbdc4cd93abdbf483ef0b5992c58`,
reviewed Caddy peer `172.19.0.4`, original data and keys retained),
the operator's public `curl` matrix returned the expected:

- `GET /api/auth/me` → HTTP **401** (anonymous request rejected)
- `GET /api/auth/csrf` → HTTP **200**
- `GET /api/auth/google` → HTTP **302** (Google challenge initiated)

With a `Python-urllib/3.12` User-Agent the `/api/auth/me`
request separately returned HTTP **403**. That is client-dependent
behavior, potentially provider/edge enforcement, not evidence that
normal browser or curl requests are unavailable; source layer is not
yet proven. Avoid changing Caddy, Cloudflare security policies or the
ASP.NET origin checks solely to force the Python client through.

`tools/disposable_project_auth_curl_probe.py` uses the actual
working **curl** HTTPS client rather than `urllib`, invokes only those
three fixed public GET endpoints, **does not follow redirects**, and
validates the CSRF token shape, auth security headers and the redirect
to `accounts.google.com` with the **separately reviewed test client**,
exact callback `https://auth-test.nalasuniverse.com/signin-pf-google`,
authorization code/PKCE S256, state and nonce. It prints only status
integers and boolean checks, never Google authorization URLs, raw
headers, Set-Cookie, CSRF tokens or OAuth state/nonce. It writes
nothing to the Project, provider, PWA or host.

```sh
cd "$HOME/Developer/Projects/fmp" || exit
git -C "$AUTH_ROUTE_DIR/auth-kit" pull --ff-only || exit
python3 "$AUTH_ROUTE_DIR/auth-kit/tools/disposable_project_auth_curl_probe.py" \\
  --check-google-challenge
```

A successful result `state=ready-for-live-google-login` means only
that the public **challenge redirect** is correct. It does not
demonstrate Google consent, callback validation, session creation, or
administrator admission.

**Do not assume the first Google visitor becomes an administrator.**
The app requires an independently verified immutable Google `sub`
claim for the approved initial administrator, paired with a verified
email in a **protected host-only** `admin-init` action. Until this is
provisioned, a successful but unapproved Google callback is expected
to redirect generically to `/?auth=unavailable`. Never paste OAuth
codes, ID tokens, subject values, session cookies, Google client
secrets, invitation tokens or callback URLs with state/code into
GitHub issues or ChatGPT. The current disposable image is the
reference code built from commit `838efecd406b` and is independent
of the evolving Auth Kit draft PR's test tooling.

## Post-registration public HTTPS smoke proof

When the Deployment Kit returns `state=public-route-registered`, the
hostname, DNS record and tunnel ingress have been written, but
`liveHttpsVerified=false` is still authoritative: a successful provider
write does **not** prove end-to-end HTTP, TLS, strict proxy handling or
Google authorization. From a workstation with real public DNS/network
access, run the bounded Auth Kit probe:

```sh
cd "$HOME/Developer/Projects/fmp"
git -C "$AUTH_ROUTE_DIR/auth-kit" pull --ff-only
python3 "$AUTH_ROUTE_DIR/auth-kit/tools/disposable_project_auth_public_probe.py" \\
  --check-google-challenge
```

This performs only public HTTPS GETs over a normal TLS-validated
connection, **never** SSH or Cloudflare writes. It requires unauthenticated
`/api/auth/me` to return `401`, `/api/auth/csrf` to return `200`
with an opaque token, and expected cache/HSTS/security headers. With
`--check-google-challenge` it also requests
`/api/auth/google` and expects an **unfollowed** `302` to
`accounts.google.com` with the separately reviewed test Google client,
exact `https://auth-test.nalasuniverse.com/signin-pf-google` callback,
authorization-code flow, PKCE S256, opaque state, and nonce. It does
not complete Google login, persist its own cookies, return credentials,
print OAuth state or raw response headers, send emails, or access
the PWA's APIs/database. The server may generate ordinary OIDC
correlation/DataProtection state as part of handling the challenge.

If the public smoke check reports `state=blocked` with all boolean
checks false, do **not** assume an OAuth configuration fault. As of the
2026-11-13 test, the initial version did not include raw HTTP statuses.
The revised probe includes only `observedHttpStatuses` for the three
fixed endpoints (e.g. 403, 404, 502), without dumping response bodies,
cookies, OAuth redirects or Cloudflare identifiers. This lets us
distinguish strict origin/forwarding rejection from route or upstream
failure before touching Caddy or Google configuration.

**Potential shared Deployment Kit forwarding defect to verify against
actual status evidence:** the authenticated-origin Caddy template
`cloudflare_ingress_remote.py` currently contains
`request_header -CF-Connecting-IP` before
`header_up X-Forwarded-For {http.request.header.Cf-Connecting-Ip}`
and the same `X-Real-IP` substitution. If Caddy removes the source
header before those upstream placeholders are evaluated, the exact
`StrictPublicOriginTransport` contract will reject all requests
because forwarded client/real IP are absent. This is **not** yet
confirmed on the live test route; any reusable fix must be made in
the canonical Deployment Kit owner with regression/security proofs,
not as an untracked hand edit to the running PWA proxy. Preserve the
live PWA route, its existing working session and current public
Cloudflare route during diagnosis.

Expected result: `state=ready-for-live-google-login` with all
reported checks `true` and `googleLoginCompleted=false`. A failure
may mean DNS propagation, TLS, proxy transport, application startup, or
OIDC configuration has not been proven; do not compensate by disabling
strict proxy validation, reusing the PWA OAuth client, or relaxing TLS.
If the runner cannot resolve the hostname due to its own network
environment, that is not sufficient to prove a universal public outage.

A passed challenge is not permission to enroll the first arbitrary
visitor. Before an actual approved administrator signs in, use the
separate per-Project `admin-init` procedure with a independently
verified exact Google `issuer+subject` and intended email. Never
bootstrap from a guessed subject, email alone, the household Registry,
or an unauthenticated first visitor.

## Live-provider acceptance sequence (isolated Project only)

**Prerequisite:** The existing household provider inventory is a *read-only*
proof of resource identity, not an authorization to deploy or send emails.
A healthy PWA tunnel route must remain unchanged throughout this sequence.
The reference API has offline fake-Google, fake-Resend, and disposable
transport contract tests; none substitutes for these live steps.

1. **Prepare a new, separately reviewed application origin.** Obtain the
   Deployment Kit's exact Caddy network, physical peer address and independent
   hostname routing plan. Do not repurpose the existing PWA hostname,
   OAuth client, socket, API key, session cookies, SQLite file or
   DataProtection key ring. Start with a disposable instance that has no public
   Caddy/Cloudflare route and no host-published TCP port.
2. **Qualify Google first.** Create or select a *separate* authorized Google
   Web OAuth client for this exact disposable application origin; register
   only its exact `https://<approved-app-host>/signin-pf-google` callback.
   Store its client secret via local protected configuration. Run one real
   approved-admin Google code flow end to end and confirm the expected
   issuer+subject, opaque cookie, /me result, logout and denied-uninvited-user
   path. Reject wrong audience, host, state, nonce, forwarded headers and
   unreviewed physical peers. Do not infer Google callback readiness from the
   existing PWA's working OAuth client.
3. **Qualify invitations separately.** The successful **read-only Resend
   sender-domain verification** confirms the shared sender domain is
   provisioned but grants no application sending authority. Configure a
   separately approved Project-scoped sending credential and a
   `From` address at the verified domain using protected local configuration.
   Send a single controlled invitation to an explicitly approved test mailbox
   only after the operator authorizes that real email. Confirm receipt,
   exact recipient, 48-hour expiry, single redemption after verified Google
   sign-in and replay rejection. Exercise provider rejection and unavailable
   network paths without emailing real users. The application must not
   return invitation tokens to the browser when Resend is configured.
4. **Restart and restore.** Prove the durable Project-owned account/session DB
   and private OIDC key directory survive restart. Rehearse a stopped disposable
   database backup and restore, session revocation, one-time administrator
   bootstrap rejection on repeat, and no cross-Project identity leakage.
5. **Only then review rollout.** Capture sanitized results, exact source
   revisions, successful CI runs, reviewed DNS/Caddy changes, rollback
   procedure and explicit authorization for any provider or host write.
   The PWA migration is a separate compatibility/rehearsal gate. Never use
   the household Registry's Developer membership as application admission.

**Evidence hygiene:** Keep API keys, OAuth client secrets, Google subjects,
invitation tokens, user email addresses, local SQLite DBs and raw provider
responses out of GitHub comments, public artifacts, and this checklist.
Record success/failure, code revision, time and non-secret resource references
in the release acceptance issue. A missing credential or public route is
**blocked**, not passed, and must not be bypassed by swapping in synthetic
provider results.

## Deployment and migration boundaries

The optional new Project starter is not PWA's existing FB-001
authentication engine. PWA's current Google/password/email recovery,
session and FB-002 membership code remains working and its opt-in adapter
is separately reviewed. Do not replace PWA databases or use the new
Project SQLite store as a destination for silent user copy.

To qualify release: run the generated consumer on disposable current
Docker/Caddy/Cloudflare topology with real Google callbacks and negative
spoofing, invitation expiry/replay/rate tests, email delivery and
provider failure, durable backup/restore, cookie key persistence across
restart, per-Project isolation, host bootstrap, and old PWA parity.

Neither package assembly nor unit tests are authorization to publish
the next kit or deploy Production.
