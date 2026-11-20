# Project Forge 2.0 — P0 Re-architecture and Private Source Monorepo Plan

**Status:** Proposal for architecture review and incremental migration; source consolidation objective approved, actual cutover not yet approved.  
**Approved direction:** Decision 14-C (private monorepo as P0 objective) plus Builder-approved substantial internal refactoring/reimplementation.  
**Primary value:** Faster, clearer and safer development of the Builder's **own Projects**. Supporting other Builders is optional future growth, not the main justification.  
**Owner issue:** https://github.com/mriekki/project-forge-platform/issues/357  
**Cross-Project initiative:** https://github.com/mriekki/project-forge-platform/issues/351  
**Services roadmap:** https://github.com/mriekki/project-forge-platform/pull/352

## 1. Optimize the product, not just repository count

Project Forge's near-term objective is to help one Builder move efficiently through discovery, implementation, review, delivery, release and operation across several Projects. It should be reliable, understandable, low-maintenance, free-first and self-hostable.

This is **not** a proposal to merely place eight Git repositories under one directory and preserve every old synchronization workflow. Those old workflows were built around source-repository boundaries that would no longer exist. The new design should eliminate them when doing so retains tested external contracts.

Key measurable outcomes:
1. A change involving Core + Bootstrap + a Kit can be implemented, reviewed and integration-tested **in one source PR**.
2. Routine delivery normally has **one reviewed merge/finalize decision**, with no second deliver required merely to pick up component/release synchronization.
3. A component can build and release independently; a Registry or Feedback service update does not rebuild unrelated services/consumer Projects.
4. A release or generated Project has immutable **source commit + artifact digest + tested component manifest** provenance without manual chains of accepted source SHAs.
5. Projects such as FMP can safely adopt a new version when explicitly approved, without cloned private platform repositories, undetected managed drift or a forced Production cutover.
6. A Builder can understand current support, dependency and release state through one consistent inventory, not conflicting READMEs or several overlapping data ledgers.

## 2. Recommended structural boundaries

### Single source monorepo — private initially

**Decision 15 (approved):** The existing private `mriekki/project-forge-runtime-services` repository will be **renamed to `mriekki/project-forge-source`**, then used as the permanent private monorepo destination. The Builder approved this precise name; **the GitHub rename has not yet been executed or independently verified**. Keep using the existing owner/repo name for live GitHub operations until the rename is confirmed. Do not create a second destination repository or archive source repositories as part of this naming step.

Suggested logical layout:

    packages/
      core/                  # workflow source and reusable agent skills
      bootstrap/             # discovery and deterministic generation
      adoption/              # existing Project adoption and update
      deployment/            # exact-target deployment logic
      project-forge-cli/     # package transport, apply/update, release UX
    kits/
      authentication/
      feedback/
      release-notes/
    services/
      registry/
      feedback/              # built from the Feedback Kit's canonical source
    apps/
      management-portal/
    shared/
      contracts/
      security/
      observability/
    build/
      dependency-graph/
      test/
      publish/
      migrations/
    tests/
      cross-component/
      disposable-consumers/
      threat-model/
      release-compatibility/
    docs/
      architecture/
      decisions/
      runbooks/

The layout is a design proposal, **not** a requirement to force one implementation language or a generic shared library for everything. Only extract shared code when two real implementations benefit and it avoids coupling their runtime release schedules.

### Keep separate

- **Public Platform**: current stable ChatGPT bootstrap descriptor, immutable published contracts, normative system references, public documentation and the approved npm distribution/publication boundary. Its role could narrow to a public *publication projection* of the monorepo without duplicating implementation.
- **Public Control Plane**: Builder authorization, GitHub App installation/request verification, private-target access orchestration. Review whether some trusted non-public source belongs in monorepo, but preserve the public security boundary.
- **Consumer Projects** (especially FMP): source, GitHub Issues, requirements, application data, account authorization, CI acceptance and Production deployment proof. Never co-locate consumer app data or Prod credentials in the source monorepo.

A monorepo is **not** a monolith: the Registry, Management Portal, Feedback Service, optional Household Registry and generated Projects remain independently versioned and independently deployed.

## 3. The refactoring program

### Stream A — One coherent delivery pipeline (P0/P1)

Refactor the current cross-repo component acceptance, source copying, package ledger and repeated GitHub Actions release choreography into:
- One source commit and dependency-aware impacted-component graph.
- Path-scoped checks plus required cross-component and public-contract tests.
- Reproducible build artifacts and signed/checksummed release manifests for each package/service, based on exact source commit and dependency lock state.
- A **release decision** distinct from a source PR merge, but without redundant source handoffs or repeated end-user deliver operations.
- One consumer update contract that identifies owned paths, verifies integrity and drift, and leaves consumer-managed files untouched.
- Explicit status stages: source merged; tests passed; package published; consumer updated; deployed; Production accepted. None imply the next.

A simplification must not relax immutable npm publication, per-consumer opt-in, exact source verification or normal single human merge/finalize gates.

### Stream B — Consolidate duplicate capabilities and support state (P1)

Use one canonical workflow implementation for Copilot, Codex and ChatGPT-distributed assets, with adapters for surface differences. Review duplicated Core/Adoption/Platform asset copies; generate derived artifacts from source rather than hand-syncing implementation. Keep Bootstrap catalog as the discoverable support authority while making capability proof machine-readable and consistency-checked.

Revisit shared security/audit/telemetry/config interfaces for Registry, Portal and Feedback rather than letting each Kit independently invent them. Preserve account/household/runtime service identity boundaries and proper authorization domains.

### Stream C — Runtime Services (P1, following core contracts)

Registry and Management Portal source move into selected monorepo canonical modules. Feedback shared service reuses its existing GitHub Issues adapter and remains optional for consumers. Full Grafana/Prometheus/Loki/Alloy, host-managed secrets, local-only automated backups and isolated restore proof remain first-release requirements. Consumer FMP must prove disposable shared/embedded Feedback switch and rollback before any Production consideration.

Do not begin significant Registry/Portal feature implementation using a provisional single-repo ownership map that would immediately be reversed by monorepo cutover; complete P0 source and security ADR first.

## 4. Real current constraints to reconcile

The public Project Forge System Requirements currently require specific *repository* ownership and exact cross-repo component assembly (including PF-SYS-002 through -006, -020 through -028, -090 and -091). The proposed monorepo intentionally changes those physical ownership rules. Write an explicit **before/after authority and provenance table** and make reviewed normative amendments; do not treat repository drift as silently accepted policy.

The existing public descriptor points to immutable v19 contract snapshots. Its verification and exact-source generation behavior remain supported throughout. The npm package remains a consumer transport; this plan does not republish prior versions or directly mutate FMP.

Existing GitHub Issues/PRs remain in their original repositories unless separately migrated with faithful references; Project Forge Portfolio remains a derived view. Old repositories may become archived/read-only only **after** every live integration, release receipt and ownership link has a verified replacement.

## 5. P0 migration decision sequence and gates

### P0.1 — Current-state inventory (read only)
Document each repo's deployable/source assets, inter-repo copied paths, workflow and action dependencies, tags/releases, package/Docker images, CI permissions, published contracts, consumers and live provider integrations. Inspect secret **names and locations only**, never retrieve values. Identify all public/private and legal/licensing boundaries.

### P0.2 — Monorepo destination and visibility
**Name selection complete:** Rename the existing private `project-forge-runtime-services` repository to **`project-forge-source`**, preserving its GitHub repository identity, history, Issues, PRs, default branch and permissions. The rename is a separate GitHub Settings action and must be verified before changing live clone URLs, workflows or source authority. No new repository is required.

**Visibility decision (approved): keep the monorepo PRIVATE.** Public source may bring external review, contributor patches, transparency, educational/portfolio value and easier external scrutiny; none inherently fixes development workflows or is needed for the Builder's own Projects. Public visibility also exposes complete source/history/metadata and requires licensing/credentials/security/copyright audits and ongoing issue/contributor expectations. Other Builders are not currently the deciding factor. No obligation to publish code, no need to split source solely to open-source it, and no visibility change without a later explicit Builder decision.

### P0.3 — Target build graph and release ADR
Choose Node/JS/TS and .NET workspace integration without imposing one language. Establish package/service boundaries, dependency rules, CODEOWNERS, CI checks, artifacts, release manifest, stable consumer package path and rollback. Target one PR and one meaningful delivery gate per change; preserve publishing authorization as a separate explicit release decision.

### P0.4 — Migration dry run
In a disposable workspace/branch, import or selectively reimplement representative Core, Bootstrap and Kit source. Verify reproducible package build and an unchanged generated Project contract. Compare test coverage, output hashes where compatibility is required, and independent service release capability. Preserve historical Git references and mapping; no force push/default-branch overwrite.

### P0.5 — Incremental canonical cutover
Move selected sources in dependency order and freeze/relabel former canonical owners only when CI/provenance/consumer qualification is proven. Favor short, bounded migration batches:
1. Workflow / Core + package transport and test infrastructure.
2. Bootstrap / Adoption and generated-project compatibility.
3. Deployment Kit contract and test harness.
4. Auth / Feedback / Release Notes Kit sources.
5. Registry, Portal, shared Feedback and observability integration.

This is a suggested ordering, not mandatory if dependency analysis supports a safer alternative.

### P0.6 — Operational validation
Prove existing FMP remains unchanged and supports an explicit future update; no Production data or image changes. Verify public descriptor, Control Plane GitHub App path, package publishing preflight, cross-repo links and first new source release receipts. Define rollback to original repository sources until acceptance.

## P0 cost envelope (approved design constraint)

The Builder explicitly requires **GitHub Actions cost awareness and broader low-cost/self-hosted operation**. Plan to target **$0 incremental recurring cash costs** without mischaracterizing electricity, hardware wear, existing network/domain spending, maintenance or optional AI APIs as free.

- First source-monorepo pilot: https://github.com/mriekki/project-forge-source/pull/6. Experimental Core + Bootstrap + Feedback samples, one source checkout and deterministic offline contract bundle; a single path-filtered Linux job capped at five minutes, no Docker, browser, artifact upload or publication.
- Detailed bounded policy: https://github.com/mriekki/project-forge-source/blob/p0/atomic-source-pilot/docs/P0_COST_GUARDRAILS.md (draft). It covers current GitHub Free usage allowances, Actions runner types, storage/cache, CI duplication, local host CPU/RAM/electricity, Prometheus/Loki retention, backup growth, Cloudflare limits, paid AI API guards and maintenance.
- **Right-sized CI:** fast checks per PR; affected-component checks by source/dependency graph; expensive Docker/browser/recovery/security checks when a changed component or release gate actually requires them. Do not save compute by skipping relevant auth, passkey, deployment, secrets or restore safety evidence.
- CI billable minutes and GitHub Plans are mutable; review **actual GitHub Billing and Usage** rather than guessing spend from workflow count or wall clock. The current inventory identifies at least 28 existing workflows, but that count does **not** imply billable usage.
- Host/runtime provisioning must start with a measured capacity and storage budget. Grafana/Loki retention can exhaust disks even with free software; enforce quotas and alert before full disk. Off-host DR, additional disks, domain renewals and services may eventually require explicit spend approval.
- Keep the monorepo private (approved); GitHub Free private-branch enforcement limitations should not trigger a paid plan upgrade unless a separately reviewed security/business case warrants it.

### P0 cost acceptance

- [ ] Collect monthly GitHub Actions billed usage and project future CI cost before adding OS matrices.
- [ ] Establish an upper-cost budget and fail-closed or notification policy for paid APIs/vendors.
- [ ] Verify a reproducible source-pinned CI build in one checkout without irrelevant jobs/duplicate source handoffs.
- [ ] Establish host utilization/storage estimates with monitoring retention and backup growth.
- [ ] Document unavoidable paid requirements separately; none silently introduced.

## 6. Success criteria and hazards

- [ ] One source-repo decision and private/public rationale recorded.
- [ ] Complete owner/path/package/API compatibility matrix and one source of truth.
- [ ] Tested monorepo tooling with representative CI, artifact, generated-consumer and service independence proofs.
- [ ] Cross-repo duplication and second-deliver causes identified with before/after tests.
- [ ] Revised public PF-SYS requirements and System Design reviewed before declaring new source authority.
- [ ] Old Git refs, existing Issues, release receipts, public bootstrap/Control Plane and consumer data remain valid.
- [ ] First-release Runtime Services roadmap rebaselined to monorepo source without losing the approved foundation + shared Feedback deliverable.
- [ ] No Production deployment, forced consumer migration, irreversible repo action, paid license, or public-repository conversion without a distinct approved change.

**Risk register:** source-history provenance loss; broken public npm/descriptor contract; CI job explosion; packages accidentally forced to common release cadence; duplicate source authority during cutover; misplaced GitHub App/secrets rights; accidental consumer file overwrite; Grafana resource overhead on one host. Address each in testable phase gates.

**Conclusion:** The value of the monorepo is not the number of repositories removed. It is the opportunity to make Project Forge a coherent, reliable, faster-moving engineering platform for the Builder while keeping its external promises intact.
