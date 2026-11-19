# Project Forge Runtime Services & AI Software Factory — Phased Architecture Plan

**Status:** Proposed detailed plan for review, not implementation approval  
**Coordinating issue:** https://github.com/mriekki/project-forge-platform/issues/351  
**Date:** 2026-11-19  
**Source of truth:** This is a proposed initiative plan; normative cross-repo ownership remains with docs/system/PROJECT_FORGE_SYSTEM_REQUIREMENTS.md and the live owning repositories.

## 1. Vision and governing constraints

Project Forge is a **Builder-directed, AI-assisted Software Factory** with an optional set of independently managed runtime services. The engineering workflow continues to function without a hosted Project Forge installation. Shared runtime capabilities are explicit per-Project opt-ins with embedded alternatives where practical.

The first deployment is for this Builder's own Projects on an existing Ubuntu/Docker host. Architect for self-hosting and additional Builders later without treating the initial deployment as a public multitenant SaaS. Prefer free/self-hosted/open-source software; target **$0 incremental recurring license/hosting fees**; document existing CPU, RAM, disk, electricity, support and optional paid AI API costs. Production writes and paid services require separate approval.

### 12 accepted architectural decisions

| # | Accepted direction |
|---|---|
| 1 | Own Projects first; future multi-Builder/self-hosting |
| 2 | AI-assisted and Builder-directed; not autonomous engineering |
| 3 | Existing Ubuntu/Docker host; separate containers and lifecycle |
| 4 | Selective hybrid: embedded, shared, or both by Project-specific opt-in |
| 5 | Per-Project service identity and scoped authorization |
| 6 | Dedicated Project Forge Registry service/database |
| 7 | Grafana OSS, Prometheus, Loki, Alloy and OpenTelemetry from initial release |
| 8 | Protected host-managed secrets; future vault compatibility |
| 9 | Automated **local** backups first; off-host later (accepted exposure) |
| 10 | Comprehensive Project Forge Management Portal in Phase 1 |
| 11 | Portal controls run through existing authoritative systems and approval gates |
| 12 | First release is foundation **plus shared Feedback integration** with FMP disposable proof |

## 2. Current authority and intended owner map

- **Core** owns AI-assisted engineering workflows, HITL, brainstorm, work, review, delivery and reusable agent instructions.
- **Bootstrap** owns New Project modes, capability catalog/support evidence, deterministic project generation.
- **Control Plane** owns authorized Builder onboarding, GitHub App credentials and exact-target orchestration.
- **Platform** owns accepted package distribution, system documentation, cross-repository design and compatibility coordination; **not** a second canonical runtime implementation.
- **Deployment Kit** owns reusable host, container, routing, persistence, deployment evidence, rollback and recovery mechanics.
- **Auth Kit** owns reusable authentication and its existing Household Registry implementation. Household membership is not global consumer authorization.
- **Feedback Kit** owns canonical GitHub-first Feedback; the shared service expands existing https://github.com/mriekki/project-forge-feedback-kit/issues/24 while retaining embedded mode.
- **Release Notes Kit** remains local UI/manifest and verified deployment-evidence integration by default.
- **Consumer repositories (FMP)** own application data, permissions, specific deployment bindings and Production acceptance.
- **New Registry** will own runtime Project/service registration and grants only; it must not displace GitHub, Deployment Kit, Bootstrap or consumer authorities.
- **New Portal** will orchestrate approved operations by delegating to the existing authorities, never duplicate GitHub Issues or create its own deploy engine.

**Repository decision gate:** A new canonical source repo provisionally named project-forge-runtime-services is likely justified for the Registry + Portal and their shared contracts, but **do not create it until an ADR approves the ownership and service boundaries**. Feedback service source remains in Feedback Kit, and Deployment Kit retains deploy mechanics. Avoid one repo per container.

Existing planning view: https://github.com/mriekki/project-forge-platform/issues/294 (GitHub Projects Portfolio). A management portal is an operational interface, not another engineering Issue/PR database.

## 3. Logical topology and independence

Builder -> Project Forge Management Portal -> Registry grants, read-only GitHub/deployment/observability projections, and **constrained** operation adapters.

FMP / other consumer backend -> authenticated/scoped private service API -> shared Feedback service -> exact permitted GitHub repository/installation.

All application and service runtime telemetry -> Alloy/OpenTelemetry -> Prometheus and Loki -> Grafana.

Deployment Kit owns host/container orchestration, protected mounts, release evidence, Caddy/Cloudflare route configuration and scoped operations. Shared runtime services have **separate images, storage, secrets, network scopes, health checks, version receipts and rollback**, even though they share the same physical host. Host loss remains a single failure-domain risk.

Public-facing browsers never receive provider secrets, service-to-service credentials, Docker socket privileges, Registry administrative control, or arbitrary deployment authority.

## 4. Dedicated Registry contract

**Initial candidate stack:** .NET + SQLite + Docker to minimize new operations, subject to host-sizing and source ownership review.

Registry authoritative data:
- Project identity, owner/repository reference, logical environment references.
- ServiceDefinition (ID, service API version, mode, compatibility and provenance).
- ServiceInstance (runtime identity, environment, endpoint alias, declared version and status-evidence references).
- Project x environment x service **ServiceGrant** with exact allowed capabilities, tenant scope and revocation state.
- Credential references and key-rotation metadata **without secret bytes**.
- Non-secret operator/system audit events with actor, action, timestamp, decision and outcome.

Registry may display GitHub, host and deployment facts but **must query/reference their source authority rather than overwrite them**. A green health signal is not an authorization grant. Household Registry may be referenced, but its identities, data and lifecycle are not automatically merged.

**Open design gate:** whether service calls use online Registry validation or time-bounded locally verified grants; define revocation freshness, cache expiry, fail-closed semantics and blast radius. No silent grant broadening after Registry outage. Schema migrations need rollback/forward compatibility proof and an isolated backup/restore test.

## 5. Security and secrecy

- Unique least-privilege Project x environment x service identity; explicit grant, deactivate, rotate and revoke operations.
- Internal-network isolation with appropriate TLS at trust boundaries; private networking is **not authentication**.
- Choose exact short-lived signed assertion or mTLS-backed identity mechanism at P0 implementation ADR. Bind audience, tenant, environment, capability, expiry and replay protection; never trust a caller-selected GitHub repo URL.
- End-user sign-in, user roles, session/CSRF/origin checks remain consumer-owned. Delegated service context is bounded and verified independently by the service.
- Secret source: protected host storage, Deployment Kit-enforced ownership/mode/path checks, read-only minimal mounts when feasible. Vault-compatible secret provider interface without deploying OpenBao now.
- Portal operator authorization: reviewed roles, trusted session/identity, exact action plans, independent scope checks, immutable audit receipts and **existing HITL gates**. No arbitrary shell/Docker/GitHub APIs exposed in UI.
- Negative acceptance: wrong Project, wrong environment, forged principal, replay, stale/rotated key, path traversal, symlink, SSRF, bad GitHub grant, revoked permission, confused-deputy access, unauthorized portal operation.

## 6. Management Portal — comprehensive initial product

**Proposed React + .NET** presentation/API, not a mandate for all Projects. All eight functional areas appear in Phase 1 and supply useful real data/actions from available authoritative sources:

| Area | First-release minimum | Authority |
|---|---|---|
| Projects | Inventory, owner, Project/environment references and service opt-in | Registry + GitHub |
| Services | Service/instance catalog, grants, versions, register/revoke workflow | Registry |
| Environments | Exact deployment links and bounded deployment plan/dispatch | Deployment Kit |
| Engineering | GitHub Issues/PRs/CI status and links; no shadow database | GitHub |
| Operations | Grafana dashboards, health, error alerts, logs correlation | Grafana/Prometheus/Loki |
| Security | Scoped roles/grants, key metadata and audit history | Registry/owners |
| Recovery | Last backup, verified isolated restore, risk labels | Backup/Deployment evidence |
| Administration | Restricted policy, configured service actions, protected settings | Owning service |

Operations must be declared, exact-target, plan/preview-based, authorization checked on the backend and never treated as blanket approval to deploy Production. If an action lacks a supported safe backend, show **read-only/unsupported** rather than improvising it. Comprehensive portal means complete IA and operational core across all sections, not pretending P2 services already exist.

## 7. Initial observability stack and runtime constraints

**Selected**: Grafana OSS + Prometheus + Loki + Grafana Alloy/OpenTelemetry; self-hosted, no Grafana Cloud requirement. Pin tested images/digests and review licenses. Expose metrics/log endpoints only to trusted internal actors. Loki lacks its own auth by default; require protected ingress.

- Host CPU, RAM, disk, container restarts, health/readiness and disk/full-load alarms.
- Service latency, failure rate, dependency checks, deployed version, cross-request correlation IDs, redacted structured logs.
- Registry/FMP/Feedback health and private-provider failures shown separately; telemetry outage must not block Projects.
- Explicit label cardinality, CPU/memory quotas, metric/log retention, storage volume limits and privacy filtering.
- Alert proof for service failure, backup job failure, lack of telemetry and storage pressure. Grafana provides query/drill-down; Management Portal references it.
- Full distributed trace backend (for example Tempo) is **not** selected now; instrument correlation consistently and revisit on demonstrated need.

## 8. Backups / recovery

**Decision 9 knowingly chooses local-only automated backups initially**, not full disaster recovery. Evaluate Restic for encrypted local repositories, while reusing Deployment Kit's consistent snapshot, SQLite WAL, identity/keys and proof rules. Secrets and key custody require protected and independently declared recovery dependencies.

Require private immutable snapshot receipts, scheduling, retention, alarms, integrity checks and verified **disposable isolated restores** that never overwrite live Production. Make captured / integrity verified / restored / application recovered / alert inbox delivered separate statuses. Set proposed RPO/RTO in P0; do not claim untested guarantees.

Track existing https://github.com/mriekki/project-forge-deployment-kit/issues/106 and https://github.com/mriekki/project-forge-auth-kit/issues/9 rather than creating duplicate Auth recovery programs. Off-host encrypted copy (possibly TrueNAS), independent host recovery and resilience are **later** milestones.

## 9. Shared Feedback: first integrated runtime service

Preserve GitHub Issues as the only authoritative Feedback records. Extend the canonical Feedback Kit adapter in https://github.com/mriekki/project-forge-feedback-kit/issues/24 — do not resurrect retired SQL/worker architecture.

- Keep **embedded** Feedback available and default for existing consumers; **shared-service** is explicit per-Project/environment opt-in via Registry + compatible package/host adapter.
- Private service accepts **backend-only** delegated authenticated requests, validates exact tenant/environment/grant and issues scoped GitHub App credentials internally. No browser service credentials or caller-selected target repository.
- Preserve My Feedback reporter marker/HMAC continuity, feedback Issue IDs, labels and URLs, admin triage, and conservative unknown-create reconciliation. Do not blind-retry uncertain GitHub writes.
- Multiple synthetic isolated Project identities demonstrate no cross-tenant data or authorization leakage. Real-provider tests require an explicitly authorized disposable GitHub repository/installation.
- FMP disposable acceptance proves existing embedded mode, shared mode, My Feedback continuity, failure behavior, no duplicate Issues and an exact return path to embedded mode.
- Shared-service outages never block core FMP functionality. Validate timeouts, rate limits, restarts, version skew, idempotency and degradation.
- **No Production FMP switch in first-pass qualification.** A separate FMP reviewed plan, source gate, CI/release/deployment evidence and explicit Production authorization are mandatory.

**P1 release definition:** Foundation plus **disposable-proven** shared Feedback/FMP interoperability with secure operational evidence. This release claim does not mean shared Feedback is enabled on FMP Production.

## 10. Roadmap (priorities are not calendar dates)

### P0 — Architecture & feasibility (start now)

Deliver approved architecture ADR, owner map, revised cross-repo system requirements if needed, code repo decision, Registry protocol and availability model, service trust exchange, portal auth/roles/action schema, local-host inventory/capacity budget, recovery objectives, API compatibility and migration policy. The detailed plan and this GitHub backlog can be prepared in advance; **implementation/Production phase gates remain explicit**.

**Exit:** reviewed decisions, owners, resource envelope, unresolved blockers and a feasible implementation order.

### P1-F — Foundation + portal (first release prerequisite)

Deliver independently deployable Registry with migrations, exact grants, API and isolated restore; comprehensive portal with eight operational views and permitted operation adapters; Deployment Kit-owned private service runtime/secret mounting/isolation/rollback; Grafana/Prometheus/Loki/Alloy; protected local scheduled backups, alerts and recovery proof.

**Exit:** reproducible disposable stack, CI/security negative suite, rate/resource budget, alert drill, backup isolated restore, audit evidence, no privileged shortcuts.

### P1-I — Shared Feedback consumer integration (same first release)

Deliver Feedback Kit-owned shared service API + GitHub-first semantics; tenant isolation; exact Registry bindings; FMP disposable mode switch and rollback; version/restart/offline/provider-failure qualification.

**Exit:** reviewed, source-pinned CI/integration/provider acceptance where separately authorized; package publication only if an approved client distribution genuinely changes. FMP Production requires additional authorization.

### P2 — Expansions after initial success

Household Registry integration without globalizing consumer auth; bounded job scheduling and notifications when a real Project needs them; versioned feature/configuration control; richer Portal flows; supported Bootstrap per-Project opt-in/catalog after unrelated Project proof; off-host backup proof; Project portfolio dashboard integration via links/projections.

### P3 — Evaluated, not committed

Central SSO/user federation, AI model gateway/local inference, file/object storage, search/indexing, multi-host/HA, other Builders and separate self-hosted deployments. Advanced autonomous agent orchestration is **not** current user intent.

## 11. Ownership plan / backlog routing

Platform: overarching architecture/ADRs, owner decision, compatibility/release/public contract coordination.  
Deployment Kit: service runtime/secret isolation, telemetry stack deployment, backup/recovery/alert operations and bounded portal operation adapters.  
Feedback Kit: extend existing #24 and implement service/API under its canonical ownership after ADR review.  
FMP: disposable consumer proof, no Production mutation.  
Bootstrap: conditional supported opt-in once real proof exists, no default-enabled new capability before qualification.  
Auth Kit: later Household Registry interoperability and existing recovery work, not duplicate user authentication.  
Core/Control Plane: only if an approved plan truly changes HITL and authorization semantics.

Use one coordinating Platform issue with owner issues and reciprocal links; GitHub Projects Portfolio is a derived view. No code or Production write is authorized by an Issue alone.

## 12. Open implementation design gates and risk register

**Gates left to resolve before consequential runtime work:**
- Final source repository ownership and separate deployable units.
- Registry online-vs-lease grant validation, revocation freshness, resilience and data migration.
- Exact service-to-service authentication and key rotation.
- Operator sign-in, portal RBAC, action dispatch and independent Production approvals.
- Host memory/disk/capacity, ports, trusted network, identity and published route boundaries.
- Local-backup policy: schedule, retention, protected keys, RPO/RTO, alert delivery, proof.
- Consumer API version skew, client error behavior and rollback.
- FMP Production cutover remains outside automatic P1.

| Risk | Required mitigation |
|---|---|
| One host fails | Explicitly accepted shared failure domain; isolated local restores, off-host later |
| Registry outage/revoked grant | No fail-open; bounded cached grant policy and revocation proof |
| Secrets compromise | Per-Project scopes, strict mounts, audit, rotation/revoke tests |
| Portal bypasses gates | Backend-authorized exact operation plans, existing owner enforcement |
| GitHub Issue duplication | Stable reporter IDs, readback/unknown-outcome proof, conservative retries |
| Telemetry fills disk | Retention, cardinality limits, volume quotas and alarms |
| Overengineering / licensing | Stage gates, measured resource budget, free/open-source review |

## 13. Definition of Done and authorization boundary

P1 is **done** only after canonical owner/ADR acceptance; required tests and source-pinned CI; reproducible non-Production host deployment; Registry/Portal/Feedback API and cross-tenant security proof; Grafana dashboards/alert proof; local backup with isolated restore; FMP disposable embedded/shared and rollback proof; credible resources/costs; documentation; and clear release receipts/limitations.

A green Grafana dashboard, merged PR, npm version or issue closure **is not Production acceptance**. No new repository, GitHub App grant, provider credential, Production migration, package publication or host write is authorized by this plan without its distinct approved execution gate.

### Candidate free tools to validate during owner implementation

Grafana OSS, Prometheus, Loki, Alloy, OpenTelemetry and Restic, alongside existing Docker/Caddy and current GitHub-native tooling. Validate actual versions, licenses, security updates and measured overhead before selection is operationally accepted.

References: https://grafana.com/docs/grafana/latest/introduction/ ; https://grafana.com/docs/loki/latest/setup/install/ ; https://grafana.com/docs/alloy/latest/introduction/ ; https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html

---
**Proposal only.** Builder's twelve architecture choices are recorded; this document, its PR and linked Issues are preparation for an evidence-backed implementation plan and separate operational approvals.
