# Project Forge Household Registry

Status: **tested Registry and adoption engine under review, not deployed or published as a supported capability**.

This is a .NET 10 / SQLite service that persists shared household membership,
registered Projects and non-secret infrastructure references. It can be
accessed from a browser on Windows, WSL/Linux or macOS by a family Developer
such as Kyle using his own Google identity.

## Ownership and authority

The Registry stores household identity, approved Google issuer+subject
membership, admin/developer/member roles, one-time invitations, registered
Projects, shared resource references, explicit Project-resource bindings
and audit entries. It does **not** store provider tokens, Project passwords,
application user accounts, PWA sessions, Google OAuth client secrets,
Resend keys, SSH credentials or application data.

A household Developer is not automatically an administrator or user of PWA
or any other Project. Independent applications continue to operate if the
Registry is temporarily offline.

## First-time setup (trusted host; not a public endpoint)

Provision a private SQLite data directory owned by the non-root service UID.
For deployment, provide these settings from protected local configuration:

    PF_HOUSEHOLD_DB=/data/household.sqlite
    PF_HOUSEHOLD_ID=my-household
    PF_HOUSEHOLD_NAME=My Household
    PF_INITIAL_GOOGLE_SUBJECT=<exact-preverified-google-subject>

In a trusted host administration session execute exactly once:

    dotnet ProjectForge.HouseholdRegistry.dll admin-init

The exact initial subject must be independently verified; email matches or
first-visitor behavior never grant administration. The operation refuses an
already-initialized registry.

The runtime requires:

    PF_HOUSEHOLD_DB=/data/household.sqlite
    PF_GOOGLE_CLIENT_ID=<per-registry-oauth-client-id>
    PF_GOOGLE_CLIENT_SECRET_FILE=/run/secrets/google_oidc_client_secret
    PF_REGISTRY_KEY_DIR=/data/keys
    PF_REGISTRY_PUBLIC_ORIGIN=https://registry.example.com
    PF_TRUSTED_CADDY_IP=<exact-reviewed-managed-caddy-ip>

Google callback: https://registry.example.com/signin-google

Do not put credentials in a tracked compose file, Git, Chat, CLI arguments,
shell history, or a public household profile. The service Dockerfile runs
as non-root on internal port 8080. The Deployment Kit must own Caddy/Tunnel
routing, exact public origin, allowed header forwarding and peer convergence;
do not publish the container directly to LAN/public TCP or trust Docker
network subnets. Use the Kit's read-only platform peer inspection before
reviewing the exact Caddy transport setting. The application rejects a
non-HTTPS or unexpected public host.

The `deploy/household-registry.compose.yml` reference is an isolated
no-host-port, non-root service with a separately mounted Google OAuth secret
file, durable SQLite volume and persistent private DataProtection key ring.
Set `PF_CADDY_NETWORK`, `PF_REVIEWED_CADDY_IP`,
`PF_HOUSEHOLD_DATA_DIR`, `PF_REGISTRY_GOOGLE_CLIENT_ID`,
`PF_GOOGLE_CLIENT_SECRET_FILE`, and `PF_REGISTRY_PUBLIC_ORIGIN`
through trusted host setup. The exact Caddy network/IP values must come
from the existing Deployment Kit 4.26.1 read-only proxy-peer observation.
Do not enable or rewrite the shared Caddy route from this Compose template,
and do not put OAuth secrets into provider inventory JSON.

On POSIX the key ring directory is restricted to owner access. Protect the
mounted persistent volume, backups and host secret file. A Production
deployment must validate process UID/GID and backup/restore before cutover.

The .NET runtime uses a Google OIDC code flow with PKCE and server cookie;
the browser sends an antiforgery header on all mutations. Every Registry API
call rereads member status so disabling a Developer immediately blocks future
Registry API access. Provider references always start unverified unless
installed through a separately approved adoption plan.

## One-time existing household adoption from PWA

First create the exact-commit read-only PWA source assessment, as documented
in HOUSEHOLD_INFRASTRUCTURE_ADOPTION.md:

    python3 tools/household_adoption.py assess --checkout /path/to/fmp \
      --expected-commit <exact-40-hex-pwa-commit> \
      --output /private/evidence/pwa.json

Verify existing shared provider resources with read-only scoped credentials,
in a trusted local terminal. The Cloudflare and Resend credentials are read
from PF_CF_READ_TOKEN and PF_RESEND_READ_TOKEN environment variables; Google
Cloud access uses the current trusted gcloud auth identity.

    python3 tools/household_provider_verify.py verify \
      --google-project <google-project-id> \
      --cf-account <account-id> --cf-zone <zone-id> \
      --cf-tunnel <tunnel-id> --resend-domain <domain-id> \
      --output /private/evidence/providers.json

**Preferred when existing provider names are known but IDs are not:** locate
the exact existing Cloudflare zone/tunnel and Resend sender domain automatically
through their read-only listing endpoints, then independently verify all
discovered IDs using the original detailed provider API checks:

    python3 tools/household_provider_discover.py discover \
      --google-project <existing-google-cloud-project-id> \
      --cf-zone-name <exact-cloudflare-zone-domain> \
      --cf-tunnel-name <exact-production-tunnel-name> \
      --resend-domain-name <exact-verified-sender-domain> \
      --pwa-hostname <exact-existing-pwa-public-hostname> \
      --pwa-origin-service <exact-existing-pwa-unix-origin-service> \
      --output /private/evidence/providers.json

The name-discovery command uses the same protected environment variables and
`gcloud auth` context as the ID-based `verify` command. It fails closed if a
list is incomplete or paginated, resource names are ambiguous or missing, or
any detail response disagrees with the expected resource. Its only persistent
output is the same private, exclusive-created, non-secret provider observation
JSON. When both optional `--pwa-hostname` and `--pwa-origin-service`
are provided, it also performs a **GET** for the remotely managed tunnel's
ingress configuration, requires exactly one matching existing PWA hostname
without a path restriction, checks the exact reviewed Unix socket service and
the owning Cloudflare account, and records only that matched route. A
missing/changed/ambiguous route fails closed. A locally managed tunnel or a
Cloudflare account without read permission for the configuration endpoint
cannot satisfy this optional proof and requires a separately reviewed
on-host ingress check; do not silently treat a tunnel record as routing
evidence. The verifier never rewrites the existing PWA route.

The route proof does not check the Caddy virtual-host table, Google OAuth
client redirects, or live application availability; those still have
independent acceptance requirements. It does not change tunnel routing or
attest Google OAuth client callbacks.

**Optional no-API-key-in-the-shell Resend path:** the official Resend CLI
supports an interactive, locally approved browser OAuth login. After separately
installing the official `resend` CLI, the operator may authorize an isolated
local profile (do **not** run this in CI):

    resend --profile household-review login --web

Then append `--resend-cli --resend-profile household-review` to the
`household_provider_discover.py discover` command above. In that mode, the
script runs only `resend domains list` and `resend domains get <id>` with
JSON output, captures/sanitizes CLI output, and does not require
`PF_RESEND_READ_TOKEN`, pass a token argument or read the CLI credential file.
The CLI's locally stored OAuth permission may still be broad; only the
invoked commands are read-only. Resend's browser authorization callback must
reach the same local machine as the CLI (check WSL/Windows localhost routing
if needed). No OAuth login is launched or granted by the verification script.
Cloudflare still needs its separately scoped Zone/Tunnel Read token. For Cloudflare, use a token scoped to **Zone Read** and
**Cloudflare Tunnel/Connectors Read** on the intended account. **Resend
currently offers Full access or Sending access keys, not a read-only API-key
permission**; `GET /domains` requires an authorized key that can retrieve
domain metadata. The variable name `PF_RESEND_READ_TOKEN` describes the
**read-only behavior of this verifier**, not the Resend key's privileges.
If the operator chooses to provide a Full access key, use it **only in the
trusted local terminal**, never in hosted CI or a tracked file, and remove
its environment variable after the read. An existing send-only key cannot
be used for this domain inventory. No new key should be created without
explicit operator review. **Never paste tokens, key files or Google
authorization codes into a chat or commit them into Git.**

These commands make only HTTPS GET requests; no provider resource or
credential is modified. The output contains independently confirmed non-secret
references, status and observation time. Evidence must be less than 24 hours
old to create a new plan. Dashboard screenshots are useful inventory clues
but are **not** equivalent to this API-backed evidence.

Create the exact reviewed import plan:

    python3 tools/household_adoption_plan.py plan \
      --assessment /private/evidence/pwa.json \
      --provider-evidence /private/evidence/providers.json \
      --household-id my-household \
      --registry-origin https://registry.example.com \
      --pwa-hostname <exact-existing-pwa-public-hostname> \
      --pwa-origin-service <exact-existing-pwa-unix-origin-service> \
      --output /private/evidence/adoption-plan.json

Supplying the exact PWA hostname and Unix origin to the plan command
requires the upstream provider evidence to contain a matching, independently
read Cloudflare tunnel route. A missing or changed route cannot be used to
approve the household resource-reference import. This binds the preexisting
PWA ingress preservation review into the exact provider-evidence digest;
it does not test the downstream Caddy virtual-host mapping. The two route
parameters must be supplied together. If the tunnel is locally managed and
the configuration-read API is unavailable, stop and obtain a separately
reviewed local ingress proof rather than claiming the remote tunnel
configuration was verified.

Review the full plan and its printed file SHA-256. After administrator
approval, copy the reviewed plan securely to the Registry host, ensure
PF_INITIAL_GOOGLE_SUBJECT identifies the approved household admin, and
set PF_APPROVED_ADOPTION_SHA to that exact reviewed file checksum and
PF_HOUSEHOLD_ADOPTION_PLAN to the local private file. Then run, from the
trusted host context only:

    dotnet ProjectForge.HouseholdRegistry.dll admin-import

This is the **actual one-time household resource reference migration**.
It creates five reviewed Google/Cloudflare/Resend reference records in one
SQLite transaction with an audit receipt, preserves existing matching
resources, and treats an identical exact plan replay as no-op. It does not
create new OAuth clients, Resend keys or DNS routes and does not modify PWA
or its Production data. A different plan must receive a fresh reviewed
checksum. An operator-reviewed resource reference is not a cryptographic
attestation of continuing provider availability.

## Invite another Developer

The initial administrator signs in to the Registry browser with Google,
creates a one-time 48-hour invitation for the Developer's verified Google
email and shares the resulting token privately (not in a URL, Git issue or
terminal logs). Kyle signs into the same Registry origin using his Google
account and redeems that token. He can then register Projects and view
approved household references. He still needs separately approved provider
credentials and Project-specific application authorization.

The Registry address itself is a non-secret **explicit locator** shared with
the Developer. New Project Forge setup must verify that exact HTTPS origin
and perform authorized discovery; it must never scan household networks or
copy the Registry database.

## Backups and safe recovery

Use a trusted SQLite consistent backup or stop the Registry before copying
its protected volume. Protect the directory and backups with owner-only
permissions; perform an integrity check and disposable restore rehearsal
before Production adoption. A schema version newer than the service
understands fails closed. Backup and restoration must not overwrite PWA's
independent SQLite database or application-managed migration journals.

## What is still required for production and next kit

Registry deployment into the actual household, real provider credentials and
resource verification, controlled PWA authentication adapter/migration,
existing-account and password compatibility proof, full Google callback and
hostile Caddy/Tunnel tests, cross-platform New Project setup integration and
package distribution/installed consumer qualification.

These are real release blockers, not solved by the Registry's passing domain
tests. A successful Registry deployment is also not permission to rewrite
PWA Production, reset user sessions or install a new provider adapter.
