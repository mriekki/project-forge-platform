---
name: setup
description: "Guide and execute setup for this workstation/workspace instance, including verified local runtime convergence, optional remote-enabled capability, named deployment-environment onboarding, and disposable deployment-path proof."
argument-hint: "[status|update|repair|local|remote|<environment>]"
user-invocable: true
disable-model-invocation: true
---

# Setup

Purpose: give the developer one obvious entry point after cloning/opening a Project Forge workspace and whenever this workstation later needs local or remote environment preparation.

Normal first use is simply:

```text
/setup
```

Supported focused forms include:

```text
/setup status
/setup repair
/setup update
/setup local
/setup remote
/setup <environment>
```

`/setup` is the conversational/orchestration layer. Repository-local setup scripts and Deployment Kit commands remain the deterministic machine implementations. Do not duplicate installer, SSH, Docker, deployment, or profile mechanics in the skill when the repository already provides them.

The governing readiness invariant is:

```text
REQUESTED MODE != ready state
READY = verified operational evidence
```

A requested local/remote capability becomes ready only after its applicable readiness contract passes. Preserve the prior ready state when convergence fails.

## 1. Resolve this workspace instance

From the repository root inspect only what is needed:

- `DEV_ENVIRONMENT.json`;
- `DEPLOYMENT_TOPOLOGY.json` when present;
- `PROJECT_BOOTSTRAP.json` as generation/provenance and initial topology fallback;
- `SCAFFOLD_PLAN.json` when present;
- `.github/project-forge-workspace.json` and Project Forge/component baselines when present;
- `scripts/setup.ps1` on Windows or `scripts/setup.sh` on macOS/Linux; WSL2 is the supported generated Linux setup path;
- `tools/project-forge-vscode/work-item-status/install.py` and `docs/work-items` when present;
- current Git branch/status/upstream evidence so setup does not overwrite unrelated work;
- workstation-local setup/readiness evidence when present;
- actual workstation OS/platform and machine-local identity needed to describe this workspace instance.

If package-managed Project Forge files are drifted, route that problem to `/project-forge-update`; do not silently replace managed files during setup.

A **workspace instance** is one checkout of one Project Forge project on one developer workstation. Multiple workstations may work on the same project concurrently, and multiple workspace instances are normal.

When project provenance/configuration exists but this computer has no local readiness evidence for the checkout, treat the situation as:

```text
EXISTING PROJECT — NEW WORKSTATION
```

Do not require another workstation to be online and do not treat another computer as the project's primary machine.

Detect the current OS automatically. Do not ask the developer which setup launcher to use when the platform can be observed.

If the observed workstation OS is not declared in mutable `DEV_ENVIRONMENT.json`, surface that explicitly before claiming setup support:

```text
NEW WORKSTATION — PLATFORM NOT DECLARED
```

Do not silently reinterpret Bootstrap provenance or append a platform merely because tools happen to run. If current repository/catalog evidence supports the stack on the observed OS, offer one reviewed **consumer-owned** platform expansion to `DEV_ENVIRONMENT.json`; otherwise report the concrete unsupported/capability gap. Preserve original `PROJECT_BOOTSTRAP.json` provenance.

A workspace instance owns machine-local state such as local runtime/data, SSH private keys/trust, credential-manager entries, Docker state, and repository-scoped readiness evidence. Git/GitHub is the shared source-code coordination boundary. Never invent a central workstation registry merely to coordinate another computer.

## 2. `status` is read-only

`/setup status` performs no setup writes. Inspect current workstation evidence and live prerequisites, then report local workspace/runtime readiness plus any configured remote capabilities.

Prefer a compact result such as:

```text
SETUP STATUS

Workspace ........... READY / NOT CONFIGURED / BLOCKED
Local runtime ....... READY / STALE / NOT APPLICABLE
Build/tests ......... READY / STALE / BLOCKED
Local data .......... READY / NOT APPLICABLE / BLOCKED
Personal profile .... READY / DEFERRED / BLOCKED
Work-item Explorer .. READY / NOT INSTALLED / NOT APPLICABLE / ERROR
Remote capability ... READY / PARTIAL / NOT CONFIGURED

NEXT
/setup local | /setup remote | /setup <environment> | /next-step
```

Do not silently repair state during `status`.

## 2A. Periodic tool maintenance

`/setup update` previews catalog-backed workstation upgrades and stops at one approval gate. Read `docs/process/WORKSTATION_MAINTENANCE.md` and use `python tools/project-forge-setup/maintenance.py status` for read-only tool inventory when present. Run `update` without apply to get the reviewed command list and SHA-256; only then run `update --apply --plan-sha256 <reviewed-hash>` with the same selected tool IDs after explicit approval. A changed plan must be reviewed again. `/setup status` makes no writes; regular `/setup` may record a 30-day check in ignored workstation-local state. An update never implicitly alters Project-pinned runtimes, product dependencies, Project Forge package baselines, Docker/SSH trust, production environments or third-party guidance versions. Missing tool catalogs or unsupported managers are `MANUAL REVIEW`, not guesses.

## 3. Run generated workstation setup

Select the launcher for the actual workstation OS:

```text
Windows     -> .\scripts\setup.ps1
macOS       -> ./scripts/setup.sh
Linux/WSL2  -> ./scripts/setup.sh
```

For normal setup, run the launcher with repository restore enabled when supported:

```text
setup --restore
```

For a read-only generated setup check, use the script's check mode when supported:

```text
setup --check
```

A manually invoked `/setup` authorizes routine, bounded, non-destructive local setup that the generated script already owns: supported tool installation, VS Code extension installation, dependency restore, personal Project Forge profile initialization, and other declared workstation preparation.

Before a large workstation install run, surface all currently knowable prerequisites together when the generated tooling exposes them: missing tools, runtime/version pins, editor extensions, Docker operational state, interactive elevation/terminal requirements, and durable fresh-shell discovery. Group unavoidable sudo/administrator or secret-bearing prompts into clear terminal handoffs instead of discovering them one installer at a time.

A temporary process `PATH` adjustment may prove a diagnosis but does not by itself prove durable tool discovery. Re-check important runtime commands in the environment a fresh terminal/editor will use before reporting final readiness.

Stop before destructive replacement, unrelated machine mutation, secret disclosure, or repair outside the declared setup contract.

### Work-item Explorer decoration

When `tools/project-forge-vscode/work-item-status/install.py` exists, treat the Project Forge-owned VS Code work-item status extension as routine workstation setup when local `docs/work-items` folders are present.

For `/setup status`, remain read-only. If `docs/work-items` exists, run:

```text
python tools/project-forge-vscode/work-item-status/install.py status --json
```

Report the returned state as the `Work-item Explorer` setup dimension. If `docs/work-items` does not exist, report `NOT APPLICABLE` and do not create a local work-item hierarchy merely to enable badges.

For normal `/setup` and `/setup local`, when `docs/work-items` exists, run the bounded Project Forge installer:

```text
python tools/project-forge-vscode/work-item-status/install.py install --json
```

This installation is already authorized by `/setup` as routine workstation preparation; do not require a second `/work-item-status enable` confirmation. The installer may replace older versions of this same Project Forge extension only and must not install unrelated extensions, alter Project files, or change Git/GitHub state.
If the result has `reloadRequired: true`, tell the developer to reload VS Code once after setup. Do not repeatedly reinstall an already-ready version merely because the editor has not yet been reloaded.

If a Project has local `docs/work-items` but the package-managed installer is absent, report:

```text
PROJECT FORGE UPDATE NEEDED
```

Route to `/project-forge-update`; do not clone private Project Forge source repositories or download loose extension files as a workaround.

A decorator installation error does not erase otherwise valid runtime/build readiness. Report the `Work-item Explorer` dimension as `ACTION NEEDED` or `ERROR`, preserve the other independent setup dimensions, and give the smallest repair/update action.

## 3A. Optional Modern Web Guidance setup and verification

For browser-facing web/PWA Projects that include `.github/skills/web-guidance/SKILL.md`, `/setup` owns optional workstation-local guidance availability. Do not create another user-facing setup command. Non-web/backend Projects need no guidance installation. Keep this dimension independent from required runtime readiness and preserve existing third-party skills/configuration.

- `/setup status` is read-only: inspect the managed skill's presence, Node.js >=22, npm/npx availability, existing `.mwgrc`, and exact CLI cache when observable **without downloading or changing files**. Report `AVAILABLE`, `DEFERRED`, `NOT APPLICABLE` or `ACTION NEEDED` based on evidence. Skill-file existence alone is not successful retrieval.
- Normal `/setup` / `/setup local`: once repository-defined setup has provisioned Node, optionally prepare `modern-web-guidance@1.0.0` into the user's npm cache by a harmless search (`search "accessible form validation"`), and verify a relevant guide can be retrieved. For Linux/macOS/WSL prefix each command with `DISABLE_TELEMETRY=1`; for PowerShell set `$env:DISABLE_TELEMETRY = '1'` before `npx.cmd`.
- The first `npx` invocation may download and execute third-party code. Respect normal terminal/network approvals and project privacy policy. **Do not run Google's interactive `install` command**, globally install tooling, overwrite `.mwgrc`/agent files, or bypass permission failures. Project Forge distributes the skill itself.
- If Node 22+, exact package, permission or network is unavailable, report optional guidance `DEFERRED` rather than installing unrelated runtimes or blocking local setup. A newer arbitrary Google CLI is not proof of exact approved version.
- Check `/ux-review` discovery when included and `web-guidance` agent availability when frontend work applies. Existing independent Google skill installations must be preserved/reconciled, not overwritten.
- `/setup repair` may retry this bounded preparation. Report `Modern web guidance` as a distinct setup dimension; failure does not erase already-verified application/runtime readiness.

## 4. `/setup local` converges verified local development readiness

The first success target is:

```text
LOCAL WORKSPACE READY
```

Remote environments must not block local setup unless the approved project explicitly requires a remote dependency for local development.

If application scaffolding is intentionally deferred by `SCAFFOLD_PLAN.json` or approved work-item state, local workspace readiness may be valid without an application runtime. Do not invent source/runtime work merely to make local setup look complete.

When application source/runtime exists, converge only the repository-owned local development contract.

### A. Prerequisites and restore

Verify supported tools/versions using repository setup/doctor tooling when present. Run repository-defined dependency restore/setup commands when missing or stale. Preserve pinned versions and project conventions.

Treat **installation**, **version compatibility**, and **operational readiness** as separate evidence when tooling exposes those distinctions. A successful CLI/version probe does not prove that the backing service/runtime is operational for the required Project Forge action. For Docker-based setup, do not call the runtime ready merely because `docker --version` succeeds; require the repository/doctor operational probe before relying on Docker Engine capability.

### B. Local persistence

For SQLite local development, resolve the project-owned database path and migration/initialization contract from repository evidence. Prefer installed Deployment Kit local SQLite ensure/status primitives when available.

When the database is absent, creating the owned local SQLite file/directory and running normal forward initialization/migrations may be routine setup.

If an existing database is corrupt, incompatible, has unexpected ownership/schema state, or recovery would be destructive, stop. **Never delete, replace, reset, or migrate destructively** merely to make setup pass. Other persistence engines require their own explicit repository-owned setup contract.

Each workstation normally owns independent local development data; do not silently copy mutable local databases or runtime state from another computer.

### C. Build and tests

Run the repository's required local build and test commands. A missing/stale build is a normal convergence condition; rebuild it. If required build/tests fail, report:

```text
LOCAL MODE NOT READY
```

and do not record local runtime readiness.

### D. Local immutable runtime artifact

When local execution is Docker-based, build/acquire the application image through repository-owned commands and resolve an immutable identity. A repository-supported workstation adapter may accept an exact registry digest or a local Docker image ID (`sha256:<64 hex>`) for workstation-only execution. Never treat a mutable tag as final runtime identity.

### E. Local runtime and health

Converge the project-owned local application runtime through the repository-distributed workstation adapter when available. Current reusable workstation-container topology remains loopback-only:

```text
placement: workstation
isolation: container
exposure: loopback
```

Mount only project-owned local persistence as required. Verify the declared health endpoint/smoke check when the project defines one. Do not resolve SSH targets, publish images, create public routes, or deploy Staging/Production while preparing local development.

Only after applicable prerequisites, persistence, build/tests, runtime, and health checks pass should local readiness be recorded as ready.

### Optional passkey-ready Project setup (only when repository-selected and package-qualified)

For an Auth Kit Project with `generation.householdAuth.passkeys.signIn=passkey-first`
or a matching approved `HOUSEHOLD_AUTH_SETUP.json`, add an **independent**
readiness dimension, not an automatic authentication migration:

- Inspect the Project-owned configuration and the **exact pinned** managed
  Authentication Kit component, its `docs/PASSKEY_SUPPORT.json`, package
  verification and `AUTHENTICATION_BASELINE.json`. Only
  `supportState=qualified` in a provenance-verified published package is a
  selectable capability; a `candidate` marker or copied JS file is **not**
  support. A Google-only or non-Auth Project is `NOT APPLICABLE`.
- Check the declared HTTPS `applicationOrigin`, derive the RP ID from its
  **exact hostname**, and compare against the reviewed, Project-owned
  `ProjectForge:Authentication:Passkeys:RelyingPartyId`. Never use the
  Household Registry hostname or widen RP ID to a shared parent domain.
- Check that the existing approved Google OIDC enrollment/recovery remains
  functional, Auth Kit persistent SQLite and Data Protection keys have
  application-owned backup/restore coverage, and the strict Caddy/Cloudflare
  origin/physical-peer requirements remain in effect.
- Keep `ProjectForge:Authentication:Passkeys:Enabled` **false** by default.
  Neither `/setup` nor a managed-file update activates passkeys, creates a
  credential, resets accounts, changes providers or deploys Production.
- Local compile/unit/HTTP or a software-authenticator signature test may
  establish `BACKEND VERIFIED`; it does **not** establish Apple Face ID,
  iPhone Safari, installed-PWA, device recovery or Production readiness.
  Mark each untested dimension `NOT VERIFIED`, not `READY`.
- An actual live sign-in/recovery, security-policy, schema-compatible restore
  and named-environment activation require the normal reviewed deployment
  gates and appropriate operator/device participation. Failure of this
  optional dimension does not erase unrelated local runtime readiness.

This is part of the existing `/setup` flow, not a new command or a hidden
platform feature toggle. Use the canonical [passkey initiative](https://github.com/mriekki/project-forge-auth-kit/issues/26)
only when the repository actually selects or tests passkeys.

## 5. Establish/sync the personal Project Forge profile

When installed Deployment Kit exposes personal-profile operations, `/setup` should establish the authenticated developer's portable non-secret profile as routine setup state. This repo is per developer, not per Project or workstation.

If the expected private profile repository is missing, explain the intended creation before writing. It stores only non-secret target definitions/preferences. SSH private keys, passwords, PATs, known-host contents, mutable local databases, Docker credentials, and machine-local readiness remain local.

Use repository-provided deterministic profile operations when supported. If GitHub is unavailable, otherwise-ready local development remains valid; report profile portability as `DEFERRED`.

Never ask the developer to paste credentials into chat.

## 6. Present guided environment setup selection

After local readiness/profile state is understood, show the environments this workstation can be prepared to use.

This is an intentionally **multi-select** decision because preparing the workstation for several environments in one setup session is valid. When the host exposes structured choice UI, use native multi-select; in VS Code use a question surface such as `vscode_askQuestions`.

Conceptual choices are:
- `Local development`;
- each existing project-defined environment from current topology;
- `Other / define another environment`.

Recommend/select `Local development` by default only because Project Forge is local-first. Do not automatically recommend additional environments without project-specific evidence.

Rules:
- existing names come from `DEPLOYMENT_TOPOLOGY.json`, falling back to Bootstrap topology only for the initial topology;
- selecting an environment means **prepare this workstation for that environment**, not deploy the project application;
- do not force every environment to be configured in one session;
- the recorded setup scope comes from the developer's actual selections;
- later environment changes belong in mutable project topology, not casual rewrites of Bootstrap provenance.

### Builder-owned target namespace

Treat reusable remote target definitions as Builder-owned personal state. The Project owns logical environment roles and a logical `targetProfile` binding; it does not own another Builder's physical machine, SSH identity, trust, current address, or readiness.

The same logical target name may resolve to a different physical machine for another developer. For example, Project topology may bind `Production -> production`; each Builder may define their own personal `production` target with their own hostname, SSH account, identity, and trust. Do not treat another Builder's target profile, hostname, SSH identity/trust, address, or readiness as authoritative for this workstation.

When an already-bound remote environment references `<target>` but this Builder's personal/local profile has no such target, do not describe the Project as broken and do not ask the Builder to gain access to another person's box. Surface the condition explicitly:

```text
<ENVIRONMENT> TARGET NOT CONFIGURED FOR THIS BUILDER

This Project binds <environment> to logical target <target>, but this
Builder has not defined that target in their personal Project Forge profile.

CHOICES
Define my target `<target>` [RECOMMENDED]
Sync/import my personal target `<target>` if I already defined it elsewhere
Keep `<environment>` unavailable on this Builder
```

`Define my target` uses the supported personal target-profile flow and preserves the Project's existing logical `targetProfile` name. Do not silently substitute a differently named personal target merely because it is reachable; selecting a different logical target is a Project topology rebind and requires its separate explicit decision. Production-class configuration/access remains distinct from Production proof and application-deployment authorization.

### Define another environment

For `Other / define another environment`, collect only material durable facts, normally:

```text
Name ............ demo
Purpose ......... demo / staging / production / development
Placement ....... workstation / remote-target / managed-service / deferred
Target .......... <when placement requires one>
Isolation ....... <project/catalog-supported option>
Exposure ........ <project/catalog-supported option>
```

Use structured single-select controls for bounded mutually exclusive fields when available. Keep names/targets open-ended. Persist the approved logical environment definition before claiming it is configured.

Normal commands then use that exact name, for example:

```text
/setup demo
/deployment-readiness demo
/deploy demo
/tear-down demo
```

Do not create an environment whose required placement/adapter is unsupported; report the concrete `CATALOG GAP` or deferred state instead.

### Complete a deferred remote target binding before remote setup

When the selected existing environment already declares `placement: remote-target` and `adapter: remote-ssh` but has `bindingState: deferred`, treat target selection as a guided Project-configuration subflow rather than a terminal setup blocker.

1. Inspect/sync the developer's reusable non-secret target definitions through installed Deployment Kit personal-profile operations. Prefer `project-forge-deploy environment profile sync --apply --json` when available. Use the returned structured target/import evidence plus current local target profiles; do not invent a workstation registry.
2. Present compatible existing logical targets as a host-native **single-select** choice. Include `Other / define another target` and `Cancel / keep deferred`. Never silently choose a target, and never preselect or infer a Production target merely from an environment name.
3. If the developer chooses another target, use the supported Deployment Kit target-profile flow to define that non-secret logical target. Keep SSH identity/trust onboarding separate and never ask for private keys, passwords, or tokens in chat.
4. Before any Project write, preview the exact binding with the deterministic topology command when available:

```text
project-forge-deploy topology plan-binding <environment> --target-profile <target> --root . --json
```

Show the reviewed before/after environment record, selected target, Production classification, changed fields, and required authorization. The supported deferred-binding operation may change only `bindingState` and `targetProfile`; it must not rewrite placement, isolation, exposure, adapter, failure domain, purpose, or role.
5. Require the bounded Project-configuration authorization reported by the plan. Production-class configuration uses its distinct Production topology-write authorization, but that authorization is **not** a Production proof or application-deployment authorization.
6. After approval, apply the reviewed plan through the deterministic command (for example `project-forge-deploy topology bind ... --yes --json` when the orchestration layer has just collected the exact required approval). Do not hand-edit `DEPLOYMENT_TOPOLOGY.json` in the skill. If installed Project Forge tooling does not expose the deterministic binding capability, route to the applicable Project Forge update/capability path instead of inventing JSON mutation logic.
7. Re-read `DEPLOYMENT_TOPOLOGY.json` after the write. Continue normal `/setup <environment>` using the persisted logical target and, when available, use structured `environment setup check`/`plan` evidence for access/platform/proof readiness.

A configured environment that already points at a different target is a **rebind**, not deferred binding completion. Stop for a separate explicit topology-change decision; do not reuse this subflow to move an existing environment silently. Bootstrap remains provenance and must not be rewritten to record the later binding.

## 7. `/setup remote` and `/setup <environment>` prepare remote-enabled capability

Remote setup proves that this workstation can later work with the configured non-Production or Production-class environment under its normal safety contract. It does **not** publish an artifact or deploy the real application.

Verify as applicable:
- local developer prerequisites still needed to build/test;
- project topology contains the selected non-deferred environment;
- exact target/provider binding exists when required;
- workstation-to-target identity/trust/access is valid;
- target OS/runtime/platform prerequisites are valid;
- persistence/readiness prerequisites can be inspected safely;
- GitHub/registry access needed for a later release/publish step is available;
- repository deployment tooling/baselines are coherent.

For remote SSH preserve strict host identity. Unknown/changed host identity is a stop condition. Never copy SSH private keys/trust from another workstation and never fall back to another target/provider simply to make setup pass.

Remote readiness does not require configuring Production when the selected environment is non-Production. Production classification remains project topology/policy, not a literal-name check.

### One read-only remote preflight before recovery

Before asking the developer to repair one SSH prerequisite at a time, collect all currently knowable target-access facts through supported deterministic status/diagnosis surfaces. When installed Deployment Kit exposes the access diagnosis command, prefer:

```text
project-forge-deploy access diagnose <target> --json
```

If stable name resolution is unavailable and the developer supplies an exact address independently observed at the trusted target console, carry that address through read-only diagnosis without persisting it:

```text
project-forge-deploy access diagnose <target> --address <exact-ip> --json
```

The exact IP is address-path evidence, not a replacement SSH identity. Preserve the configured `HostKeyAlias`, target-specific trust, and configured identity. Do not store the address merely because it made diagnosis possible. Persist it only through the separately gated verified-address operation after strict SSH succeeds.

When diagnosis exposes route-source evidence, use the actual selected local source address/interface for any source-policy discussion. Never assume Wi-Fi, Ethernet, the first interface, or a subnet merely from workstation configuration.

If the Deployment Kit version does not expose the supported diagnosis surface, use its documented structured environment status/plan commands. Do not substitute ad hoc Python imports or unbounded raw `ssh -vvv` transcripts as normal orchestration.

### Guided remote failure recovery is part of `/setup`

A supported deterministic setup/readiness failure is not, by itself, the end of `/setup`. When installed Deployment Kit tooling returns structured diagnosis or a bounded next action, continue through that diagnosis automatically until one of these boundaries is reached:

- the failure is repaired through already-authorized routine setup work;
- a missing human fact is required;
- a separate write/Production/destructive authorization is required;
- a trusted-console or already-authorized administrative action is required;
- the capability is unsupported or remains blocked after bounded diagnosis.

Do **not** merely repeat an opaque subprocess exit code and tell the developer to fix access independently when deterministic diagnosis is available.

Preserve distinct categories such as:

```text
name resolution / address path
TCP reachability
host identity/trust
server-advertised authentication methods
configured identity fingerprint/offered key
local signing/passphrase/agent failure
remote public-key rejection
remote account/source-policy rejection
```

Keep credentials, private keys, raw secure-prompt content, and unbounded SSH transcripts out of conversational diagnostics and journals.

For workstation SSH-agent readiness, prefer the installed Deployment Kit's `target agent-session <target> -- <normal Deployment Kit command>` when supported; for repository-owned Python operations requiring SSH use `target agent-run <target> -- <exact local executable and arguments>` when available. This is a **local** convenience that works with the WSL/Linux private reused socket, the macOS agent or private fallback, and the native Windows OpenSSH agent service; the remote target OS is independent. Do not require the Builder to copy `SSH_AUTH_SOCK` paths across VS Code Chat terminal calls, switch to Copilot CLI, or type `[SSH AGENT WRITE]` as a second authorization merely to load the already-configured key. Keep the OpenSSH passphrase in the interactive terminal; never change the Windows agent service, host trust, or saved credentials without separate authority. After the key is ready, continue normal exact-target verification and the original write gates.

For fingerprint input, show the expected public form such as `SHA256:<fingerprint>` and validate that shape before progressing. Distinguish the **server host fingerprint**, the **client public-key fingerprint**, and passwords/passphrases. If input looks credential-like rather than fingerprint-shaped, do not repeat it into commands, reports, journals, or upstream issues.

If a local key/agent operation requires a passphrase or another terminal-owned secret prompt, follow the interactive-terminal handoff contract: collect any distinct bounded authorization once, then immediately provide the exact standalone copyable command, correct machine/working directory, expected local prompt, and the non-secret completion evidence to report. Do not ask for the passphrase through chat or ask a second ceremonial question merely to repeat the same authorized command.

**SSH signing proof matters:** a preliminary `Server accepts key` message
means the public key was eligible, **not** that local signing finished or the
remote account rejected an authenticated user. If the selected agent is absent
or signing is unproven (the fixed diagnostic code is `local-signing-unproven`),
try the already-supported exact-target
`target agent-session` in a trusted local terminal (only with the required
bounded local authority), then retry the unchanged read-only check once.
If client signature evidence exists but SSH is still rejected, report remote
authentication failure without claiming a particular account policy. Inspect
server account/source policy from a trusted console only when the evidence
actually justifies that branch. Do not repeatedly reinstall a key, weaken
trust, turn on password authentication or invent a server configuration fix.

Use recognized installed v1 `diagnosticSummary` fields and the bounded
continuation/no-progress policy in `core/process/INTERACTIVE_SESSION_GUIDE.md`
when available; older Kit output remains an explicitly limited capability.
Keep independent readiness evidence and do not reflect arbitrary exceptions
or secret-bearing stderr to Chat.

### One bounded trusted-console diagnostic bundle

When client evidence reaches the server but cannot establish why the account/session is rejected, request one compact server-side evidence bundle instead of a chain of one-fact-at-a-time questions. Limit the bundle to the facts needed for the selected account and actual route-selected source:

- intended SSH account;
- whether the expected **client public-key fingerprint** is present for that account, without dumping unrelated authorized keys;
- ownership/modes for the account's `.ssh` directory and `authorized_keys`;
- a narrowly scoped recent authentication reason for the attempted source/account;
- effective SSH allow/deny policy relevant to that account and source;
- the file/include/`Match` location that owns any relevant directive.

State exactly where to run each console command and what non-secret output to return. Never request full SSH configs/logs, passwords, private keys, tokens, or unrelated authorized-key material when the focused bundle is enough.

Client evidence may classify `remote-authentication-rejected` or `remote-account-policy-rejected`, but only trusted server-side evidence may establish a concrete cause such as `AllowUsers`.

### One exact server-policy repair after evidence

If the trusted-console evidence establishes that a server-side account/source policy change is required, prepare **one exact repair plan** before any write. The plan must show:

- exact affected file/directive and relevant before/after state;
- the actual durable source address/interface assumption being authorized;
- preservation of existing allow/deny entries unless the operator explicitly chooses otherwise;
- an exact backup of the affected file before editing;
- syntax/config validation before reload;
- preservation of the current trusted administrative session until new strict access is proven;
- reload/restart scope, rollback command, and explicit stop conditions.

Do not present configuration text as if it were a shell command. Give either one copyable bounded command or explicit editor instructions on the **target host**, with the file path stated. Do not assume that adding a new drop-in overrides or composes safely with existing includes/`Match` blocks. Never broaden a specific source restriction to a subnet merely for convenience.

A server-policy write remains a distinct operator/administrative authorization. Once the exact reviewed repair is authorized and the human reports it completed, do not ask the same authorization again: automatically re-run strict structured diagnosis/verification, then continue through separately gated address persistence, host-platform readiness, and proof as applicable.

If the human says stop, done, or pause at any point, stop modifying state. Read-only reporting may summarize what is already known, but newly observed prerequisite changes do not override the expressed pause.

### Gate password-assisted bootstrap on server capability

Before recommending a password-assisted/Home Lab bootstrap against a reachable server, use deterministic evidence of the server-advertised authentication methods when the installed Deployment Kit supports that probe.

- If password or keyboard-interactive authentication is not advertised, do not send the developer through a password bootstrap that cannot succeed.
- Route instead to strict key onboarding plus a trusted console/already-authorized session for any required server-side key/account-policy change.
- Never recommend enabling password SSH merely to make Project Forge onboarding work.

For Production-class environments, prefer the higher-assurance Strict onboarding path for new target trust/access unless the project/operator explicitly chooses a different supported security profile. Staging and other non-Production environments use the same target-access mechanics, with their own environment classification and authorization policy.

### Console-assisted recovery instructions

When a trusted-console action is required, optimize for reliable execution rather than dense shell snippets:

- one short command or one coherent semicolon-separated command per step;
- avoid unnecessary wildcards, escaping, and shell-specific quoting;
- say explicitly what the developer should run versus what output to return;
- state the expected evidence and the stop condition;
- use screenshot inspection when transcription is repeatedly failing.

Never silently edit `sshd`, widen account/source policy, disable host verification, or switch authentication policy merely to make setup pass.

### Treat target evidence and environment evidence separately

A verified workstation-to-target access relationship may be reused by multiple Projects/environments that bind to the same logical target. Environment proof remains specific to the Project + named environment + target + adapter/isolation contract.

When Staging and Production share one physical target, explicitly surface the shared failure domain and verify that their Project/environment-owned runtime identity, compose project, route/port allocation, persistence paths, and locking cannot collide. Staging evidence does not become Production evidence merely because the host is shared.
## 8. Prove supported remote mechanics with a disposable Project Forge probe

When the installed Deployment Kit exposes environment proof operations, a selected remote environment should normally be taken through an end-to-end **environment proof deployment** during setup.

The proof is not the Project application. It is a tiny disposable Project Forge-owned probe:

```text
acquire a stable probe image locally
→ resolve exact immutable digest
→ transfer using the real workstation-mediated path
→ deploy under reserved probe identity
→ verify runtime/HTTP health
→ remove probe
→ verify cleanup
```

Use the actual installed command/help contract. Never claim the Project application is deployed because the probe succeeds.

Preferred evidence:

```text
Environment ........... demo
Target/access ......... READY
Host platform ......... READY
Deployment path ....... PROVEN
Project application ... NOT YET DEPLOYED
```

For a Production-class environment, keep the proof explicitly labeled as a **PRODUCTION ENVIRONMENT PROOF** only when topology says the selected environment is Production-class. The disposable proof still does not authorize real Production deployment.

If cleanup fails, report `PROOF PASSED — CLEANUP ACTION NEEDED`; do not claim a clean setup.

When proof output distinguishes `transferState: transferred` from `transferState: already-present`, report that distinction. A proof that reused an exact cached image may still prove runtime/health/cleanup, but it must not be described as an observed fresh workstation-to-target image transfer. If fresh transport itself must be tested, plan that separately without deleting or pruning a shared image cache merely to manufacture evidence.

When installed Deployment Kit provides a durable local proof receipt or equivalent discoverable evidence, record/reuse it rather than relying on chat history. Reuse only while its target binding, host identity, workstation identity, adapter/provenance, logical environment, and cleanup result remain applicable. A new chat alone must not invalidate valid machine evidence.

## 9. `repair` is bounded and fail-closed

`/setup repair` may re-run safe deterministic setup/readiness operations after classifying the blocker. It may create missing local directories/caches, restore dependencies, rebuild outputs, create a new owned local database, run normal forward initialization, or recreate an owned disposable/local runtime when the repository contract permits those actions.

Stop for a separate explicit decision before:
- deleting/resetting an existing database;
- destructive migration or rollback;
- replacing unexplained persistent data;
- deleting unrelated containers/images/volumes;
- publishing an artifact remotely;
- rebinding a target;
- weakening host verification;
- changing public/LAN exposure;
- deploying Staging or Production.

## 10. Relationship to deployment readiness

`/setup` establishes workstation/workspace capability and may prove reusable environment mechanics.

`/deployment-readiness <environment>` remains the later pre-deployment check for one exact environment. It reuses fresh setup-time proof where valid, then verifies application-specific prerequisites for the real deployment.

`/setup` never implies `/deploy`. A successful setup/proof does not authorize a remote or Production application write.

## 11. Completion and handoff

After setup, report evidence rather than inferring human acceptance. Keep independent readiness dimensions independent instead of collapsing them into one `READY` label.

Prefer a compact final shape such as:

```text
SETUP RESULT

Local tools/runtime ......... VERIFIED / BLOCKED / NOT APPLICABLE
Fresh-shell discovery ....... VERIFIED / CAVEAT / BLOCKED
Build/tests ................. VERIFIED / BLOCKED / NOT RUN
Work-item Explorer .......... READY / ACTION NEEDED / NOT APPLICABLE
Remote target access ........ VERIFIED / BLOCKED / NOT CONFIGURED
Host platform ............... READY / BLOCKED / NOT APPLICABLE
Deployment path ............. PROVEN / NOT PROVEN / BLOCKED
Proof image transfer ........ TRANSFERRED / CACHE REUSED / NOT RUN
Proof cleanup ............... CLEAN / ACTION NEEDED / NOT RUN
Project application ......... NOT DEPLOYED / <actual evidence>
Repository CI ............... PASS / BLOCKED / NOT CHECKED
Human workspace acceptance .. CONFIRMED / PENDING
```

A generated setup/doctor/proof success is machine evidence. Human workspace acceptance remains distinct. A continuation/override for a documented Project Forge defect is not a CI waiver and is not human workspace acceptance; preserve its exact scope so resuming setup does not repeatedly ask the same decision.

Useful next actions include:
- `/next-step` — one sensible next action after current evidence is known;
- `/start-work <ID>` — implementation authorization after workspace acceptance;
- `/deployment-readiness <environment>` — final pre-deploy evidence for a prepared environment;
- `/deploy <environment>` — only after readiness and its own authorization contract;
- `/tear-down <scope>` — destructive cleanup under its separate gate.

Do not create a second top-level developer-environment-mode workflow. Local/remote workstation convergence belongs here.
