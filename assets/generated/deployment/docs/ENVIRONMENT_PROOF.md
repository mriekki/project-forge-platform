# Environment Proof Deployment

A Project Forge environment proof verifies that one developer workstation can exercise the real remote deployment path for one exact named logical environment before the Project application exists or before its first real deployment.

It is intentionally **not** the project application.

## What it proves

For a supported remote-target environment, the proof uses the same reusable mechanics as a normal workstation-mediated application deployment:

```text
this workstation
→ verified target/profile access
→ ready shared host platform
→ pull small stable probe image locally
→ resolve exact immutable registry RepoDigest
→ resolve local Docker config/image ID
→ transfer image over verified SSH
→ verify the same config/image ID after remote docker load
→ deploy with the managed application runtime using that verified loaded image ID
→ verify HTTP health
→ tear down the reserved probe runtime
→ verify cleanup and image-cache evidence
```

The current default probe image tag is `nginx:alpine`. The mutable tag is never treated as deployed identity.

Project Forge deliberately records two exact identities because Docker `save`/`load` does not guarantee that a registry RepoDigest remains inspectable under the same repository reference after load:

- **registry digest** — immutable reviewed artifact/release identity (`repository@sha256:...`);
- **Docker config/image ID** — content identity used to verify the workstation-to-target transfer and to run the preloaded image (`sha256:...`).

The registry digest remains in the deployment spec and release/proof evidence. The loaded runtime is verified and launched by the matching Docker config/image ID. A target that already has that exact image ID can reuse it without retransferring the image.

The probe uses:

- no project database;
- no project persistent data;
- no project application secrets;
- a reserved per-repository probe app slug;
- the exact selected logical environment name;
- the existing per-app/per-environment deployment lock;
- automatic cleanup through the existing scoped tear-down machinery.

## Setup orchestration

Before running proof commands directly, the read-only remote setup orchestrator can show whether target access and the host platform are actually ready:

```text
project-forge-deploy environment setup status <target> --json
project-forge-deploy environment setup plan <target> \
  --owner-repo <owner/repo> \
  --environment <name> \
  --json
```

These commands never perform the proof or authorize a write. They make `TARGET ACCESS READY`, `HOST PLATFORM READY`, and `DEPLOYMENT PATH PROVEN` separate states.

When owner/repository and logical environment context are supplied, setup planning also checks the current workstation for a still-applicable prior proof receipt before recommending another proof run.

## Commands

Read-only plan:

```text
project-forge-deploy environment proof plan <target> \
  --owner-repo <owner/repo> \
  --environment <name>
```

Run the proof after authorization:

```text
project-forge-deploy environment proof run <target> \
  --owner-repo <owner/repo> \
  --environment <name>
```

For a named environment whose project purpose is Production, preserve that classification even when its name is custom:

```text
project-forge-deploy environment proof run <target> \
  --owner-repo <owner/repo> \
  --environment prod-east \
  --production
```

Use the exact installed CLI/help rather than copying examples blindly.

## Authorization

Normal non-Production proof:

```text
[ENVIRONMENT PROOF WRITE]
```

Production-class proof:

```text
[PRODUCTION ENVIRONMENT PROOF]
```

A successful proof never authorizes the later real application deployment. Production proof never authorizes a Production application deployment.

## Terminal evidence

A proof run returns a terminal result even when the operational path fails after the run begins. The result distinguishes planning from observed execution and includes, when available:

```text
preflight
registryDigest
localImageId
transferState
remoteImageId
runtimeState
httpHealth
cleanupState
imageCacheState
proof
mutated
finalMutationState
error
cleanupError
receipt
receiptError
```

A read-only plan does not claim `mutated: false` as though it were the eventual run result. The run reports whether transfer/runtime mutation actually occurred and whether cleanup completed.

A failed proof exits nonzero even when structured terminal evidence was produced successfully.

## Cleanup

The proof attempts cleanup even when deployment raises after mutation begins.

Successful completion requires terminal cleanup evidence (`removed` or already `absent`) for the reserved probe runtime. If deployment succeeds but cleanup cannot be verified, the command fails rather than reporting a clean proof.

A loaded Docker image may remain cached after runtime cleanup. That state is reported explicitly (for example `runtime-clean-image-cached`) rather than being presented as an unmodified host. Cached image content is not application runtime or persistent application data.

The probe must not delete another Project, another application, another logical environment, or shared host platform state.

## Workstation-local proof receipt

Every terminal proof run attempts to write a compact workstation-local proof receipt under the user's Project Forge evidence directory. The receipt is diagnostic/readiness evidence only; it is not deployment authorization and is not repository content.

The receipt records only non-secret evidence needed to decide whether the prior proof is still applicable, including:

- Project owner/repository;
- exact logical environment;
- logical target name and Production classification;
- Deployment Kit/proof contract version;
- proof/cleanup/final mutation state;
- immutable probe artifact identities when available;
- a hash-based signature of the current target profile, configured workstation identity fingerprint, and target trust file.

It never stores private keys, passwords, tokens, known-host contents, or application secrets.

`environment setup plan` treats the receipt as `PROVEN` only when the latest receipt passed with terminal cleanup and still matches the current Project/environment/target context and current workstation target identity/trust. A target/profile/trust change, Production-classification change, proof-contract change, or Deployment Kit version change makes the evidence stale and causes a new proof to be planned.

A **new chat or new assistant session alone does not invalidate proof**. Evidence validity is based on machine/project/environment facts, not conversation history.

A failed proof may also leave a receipt, but that receipt is explicitly `not-proven` and is never promoted to readiness.

## Relationship to `/setup` and `/deploy`

`/setup remote` or `/setup <environment>` may use deterministic setup status/plan first, then run this proof after the developer selects the named remote environment and the relevant write authorization is granted.

A later first real `/deploy <environment>` can reuse fresh proof evidence for target access/platform/transport mechanics and ask only unresolved application-specific questions such as persistence, health, route/exposure, and immutable application artifact policy.

Project-defined environment names are not limited to Staging and Production. `demo`, `qa`, `prod-east`, or another safe configured slug use the same mechanics, while Production purpose/classification keeps the stronger authorization path.
