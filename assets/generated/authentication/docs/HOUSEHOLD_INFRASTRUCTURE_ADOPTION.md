# One-time Household Infrastructure Adoption — PWA Pilot

**Status (2026-11-14):** Household Registry and Project Auth runtime source PRs are merged. The PWA-specific Auth Kit cutover was independently accepted in [PWA issue #43](https://github.com/mriekki/family-meal-planner-mark-pwa/issues/43), using a *fresh app-owned Auth Kit account/session database and persistent keyring* because the PWA was an unused shell; its prior records and credentials were preserved separately for rollback. **This does not qualify shared household provider resources, general generated-Project recovery or a published Authentication-enabled Project Forge package.** Auth Kit [release issue #5](https://github.com/mriekki/project-forge-auth-kit/issues/5) is the current release gate, and [recovery issue #9](https://github.com/mriekki/project-forge-auth-kit/issues/9) tracks generated-Project readiness. No provider/Production changes are authorized by this document.

This is the agreed one-time path for reusing relevant Family Meal Planner PWA infrastructure to bootstrap shared Project Forge household defaults. Do not repeat Google, Cloudflare, and Resend setup from scratch merely because a reusable household profile is introduced.

The Authentication Kit owns this provider-resource assessment proposal. Existing-repository adoption, New Project discovery, deployment mechanics, and the PWA's own work-item approvals remain owned by their established Project Forge components.

## Separate infrastructure and application responsibilities

**A — Existing household infrastructure (first):** Inventory the existing PWA Google Cloud configuration, Cloudflare account/domain/Tunnel/Caddy network, Resend sending domain, and Ubuntu/Docker environment. Determine shared administrator-owned assets versus application-specific resources. Use independent **read-only provider verification** to establish current resource existence and ownership. Reuse appropriate shared assets, but allocate separate OAuth clients/redirects, narrowly scoped Resend keys, and exact app-owned ingress/routes for future Projects. PWA's credentials, hostnames, database, production route and runtime stay as-is.

**B — PWA-specific application adoption (accepted):** This migration has already occurred under PWA's separate review and Production approval. The accepted exception uses a newly seeded, isolated Auth Kit account/session database and persistent DataProtection keyring; historical PWA identities/passwords/sessions were *not* automatically translated because no active Product users or substantive Production user data needed migration. Historical PWA data and implementation were preserved for an explicit rollback. A future consumer with established users **must not inherit** this fresh-account exception: preserve or explicitly reconcile identities, sessions, passwords and app-owned authorization through that Project's own reviewed migration. Never auto-link by email or treat Household Registry membership as Project login.

## How to run the implemented assessment

From the private Authentication Kit checkout, run:

    python3 tools/household_adoption.py assess \
      --checkout /path/to/fmp \
      --expected-commit <exact-40-hex-pwa-head> \
      --output /private/existing/directory/pwa-household-assessment.json

The parent output directory must already exist outside the PWA checkout. On Windows, use paths and continuation syntax appropriate for PowerShell. The output is a new JSON report: an existing report is NEVER overwritten. POSIX writes use owner-only mode; Windows permissions depend on the destination directory.

The report is bound to the exact local Git HEAD commit, with hashes for a **fixed allowlist of committed source files**: Project Forge baseline, deployment topology, OIDC implementation, account schema/service/endpoints, Resend adapter, production provider boundaries, and exact origin transport. It never reads uncommitted files, database content, .env, provider credential material, private SSH data, local settings or live provider accounts. No provider API calls or Production actions occur.

The report includes **source-evidence-found** versus **needs-source-review** markers, and all provider candidates remain **provider-inventory-unverified**. Source evidence cannot establish whether live Google, Cloudflare or Resend resources are currently provisioned, reusable or owned by the household. It contains a deterministic assessment SHA-256 for future reviewed plans and no secrets or personal account records.

The source assessor implements **assess** only and never applies changes. Separate
draft Registry tools now implement the GET-only provider ID verifier and
name-based discovery, the digest-locked adoption-plan generator, and an
explicitly reviewed host-local Registry resource import/rollback.
See `HOUSEHOLD_REGISTRY.md` for the exact operator procedure.
These are not a live provider migration or automatic PWA identity cutover.

## Required review stages before any migration writes

1. Assess the **delivered** PWA commit using the read-only tool, not an older chat summary or uncommitted worktree.
2. Independently inventory non-secret Google Cloud, Cloudflare, and Resend resources using
   the trusted local read-only verification **commands**. Cloudflare allows read-scoped
   API tokens, whereas Resend may require a Full access key to perform its GET
   domain metadata reads; this verifier issues GET requests only. Never load or
   transmit such keys from ChatGPT or hosted CI. Confirm ownership, existing
   sharing, restrictions and per-Project scope.
3. Produce a reviewed household profile plan that classifies each asset as preserve, reuse existing shared resource, create separately scoped Project resource, or defer.
4. Separately approve any actual provider or host write with an idempotent, least-privileged executor, durable receipt and rollback/stop controls. No automatic PWA route or credential replacement.
5. Treat the accepted PWA Auth Kit cutover as a Project-specific completed event documented in PWA issue #43. For a different established Project, separately approve identity/session migration, disposable-data rehearsal, rollback, authorization and app-specific feature equivalence; do not assume the PWA fresh-account exception applies.
6. Only enable an opt-in household capability in Bootstrap's existing New Project lifecycle after full generated-Project integration proof.

## Current limitations and safety

Merged Auth Kit runtime includes .NET 10 Google OIDC code flow, per-Project SQLite account/invitation/session persistence, reference browser, exact proxy ingress checks, and a Bootstrap-managed optional generated API. Reusable, disposable Auth Kit recovery tests now cover real SQLite/DataProtection artifacts and isolated application HTTP startup; Deployment Kit includes exact Docker stopped-container capture, disposable stop/capture/resume and a durable interrupted-run journal. These are **not** real provider inventory, per-Project provider setup, durable Production scheduling/alert delivery, real full-application recovery readiness or npm release acceptance. The PWA-specific Production cutover is accepted separately; nothing here authorizes changing it.

Do not commit resulting reports to public repositories. They exclude credentials but still contain useful operational metadata. Secrets stay in protected local/provider input mechanisms, not Git, log output, shell argv, Chat, or plain JSON. PWA Production, FB-001/FB-002 requirements, provider resources and live data are all explicitly outside this change.
