---
applyTo: "**"
---

# Project Forge Agentic Workflow

Read `.github/project-forge-workspace.json` when present before assuming how requirements/work items are organized.

Existing team conventions outrank Project Forge defaults.

For browser-facing implementation or review, use the repository-managed `web-guidance` skill to consult exact-version Modern Web Guidance when available. Do not apply it to backend-only work or bypass browser support/privacy/tool permissions. `/ux-review` is the optional, read-only Builder-facing UX review; it never replaces Reviewer or authorizes fixes.

Possible sources include Product Briefs, Feature Briefs, Engineering Enablers, Jira Epics/Stories, GitHub Issues, local requirements, ADRs, or small session context.

Use proportional rigor: `LIGHT`, `STANDARD`, `ELEVATED`.

For ongoing tool maintenance use `/setup update` with the catalog-driven preview/approval/check contract. Do not turn normal `/setup` into a blanket package upgrade or change project-pinned runtimes and managed assets through a workstation update.

Keep explicit human gates for material requirements, substantive plans, meaningful implementation acceptance, the final merge/delivery decision, and production deployment.

Before any substantive approval gate, identify the exact PRIMARY review subject for the current work item/scope and put the best available review surface in front of the human when the host supports it. Treat supporting documents as CONTEXT or TRACEABILITY instead of opening everything. For Markdown prefer rendered preview, for structured approval artifacts prefer formatted source plus a concise summary, for implementation acceptance prefer the meaningful diff/Source Control surface, and for plans prefer the native plan surface or durable plan document. Opening or foregrounding a review surface is read-only presentation and never implies approval.

Every artifact-backed approval question must carry its own work-item/scope identity, approval purpose, exact PRIMARY artifact link/path, truthful presentation status, and consequence labels. Do not rely on links in earlier commentary, editor focus, a global plan, or another work item's artifact. The artifact named in the gate must be the same artifact requested/opened for review. If automatic opening is unavailable or fails, say so inside the gate and provide the exact link/path plus a deterministic manual fallback rather than fabricating success.

In VS Code, when the Project Forge companion extension is installed, use the exact-path `projectForge.openReviewArtifact` command or Project Forge language-model review tool when the current host can invoke it. The helper is read-only, workspace-confined, must fail on ambiguous multi-root matches instead of guessing from editor focus, and should report actual presentation mode when available. Use a stronger native host review/diff surface when available.

For STANDARD/ELEVATED work, invoking `/start-work` authorizes context resolution, risk assessment, and planning only. It does **not** authorize substantive implementation or implementation branch setup by itself. Produce the final proposed plan, resolve the exact work-item-specific PRIMARY artifact when one exists, foreground that exact review surface, state that implementation has not started, include the same exact artifact link/path and presentation status inside the approval question, and require an explicit `Approve plan and begin implementation [PLAN APPROVAL + CODE WRITE]` action before code writes or routine implementation branch setup. For ELEVATED work, Reviewer challenges the plan and material findings are reconciled before the human reviews the final proposed plan.

If implementation later requires a material change to the approved architecture, scope, schema/data handling, security model, externally visible behavior, major dependencies, or verification strategy, reopen the implementation-plan gate with the revised PRIMARY plan presented and linked before continuing. Stale approval does not authorize a materially changed plan.

Once a bounded action is authorized, routine mechanics inside that scope should proceed without repeated ceremonial confirmation.

For implementation, establish the repository-appropriate short-lived work branch as routine setup once implementation itself is authorized; do not add a separate branch-creation gate when branch policy/naming and scope are clear.

Continuous modes such as `/grill-me`, `/refine-requirements`, `/coach`, `/learning-review`, and `/deployment-readiness` continue until stopped or naturally complete.

During interactive questioning, prefer concise choice-first options for genuinely bounded human decisions, including `Other / specify` and `Not sure — recommend one` when appropriate. When the host exposes native structured question controls, use them instead of a plain numbered chat list. In VS Code, use the host's structured question surface such as `vscode_askQuestions` when available: single-select for mutually exclusive decisions/actions and multi-select only when several simultaneous selections are valid. A textual numbered or lettered menu is only the fallback when structured choice UI is unavailable.

When an authorized action requires a developer-owned interactive terminal prompt, follow the interactive-terminal handoff in `INTERACTIVE_SESSION_GUIDE.md`: collect any distinct bounded authorization first through the host-native structured control, then immediately provide the exact command in a standalone fenced code block, state the working directory when relevant, explain the local prompt briefly, keep passphrases/passwords/tokens/private keys local to the terminal, and say what result to report back for deterministic verification. Do not make the inability to inject terminal keystrokes the main response when a copyable command is sufficient. If the host can insert terminal text, insert only the non-secret command for human review/execution rather than silently executing the interactive step.

Make a recommendation only when current evidence, repository policy, or a clear engineering tradeoff supports one. Mark exactly one supported choice with the host's `recommended` indicator when available and give a brief rationale. When the host does not expose recommendation metadata, append `[RECOMMENDED]` to exactly one option label and keep the rationale visible. A default/preselected option may match the recommendation, but a default alone must never communicate advice or human approval. If no option is clearly better, do not mark any option recommended and do not use a default that implies preference. A recommendation is advice, not approval: record only the human's selected/confirmed answer. If the human asks for no recommendation on one decision, honor that for that decision only; later questions may still include evidence-backed recommendations.

Keep factual/environment-specific values and questions intended to elicit the human's own framing, reasoning, debugging approach, design rationale, or understanding open-ended unless options are later useful as scaffolding.

`/grill-me` is the single adversarial-questioning entry point. It begins read-only and may, after one explicit session-level choice, reconcile resolved decisions into permitted local authorities or proposed external updates. Do not create a second documentation-aware grilling command.

`/setup` is the single workstation/environment preparation entry point. It owns status, repair, verified local runtime convergence, remote-enabled capability preparation, and named-environment setup/proof. Do not create a second developer-environment-mode command. `/deployment-readiness <environment>` remains the later exact-environment pre-deploy verification step.

For `/setup`, apply the interactive-terminal handoff whenever deterministic Project Forge tooling reaches a local prompt that must remain under developer control. For example, after the exact target key-creation action is authorized, provide the returned `project-forge-deploy target key-create <target>` command immediately in a standalone copyable block, tell the developer to enter `[LOCAL KEY WRITE]` and the private-key passphrase only in the terminal, and state the non-secret result/evidence to report back so setup can verify and continue. Do not ask the developer to paste the passphrase or private key into chat and do not turn terminal ownership into a dead-end explanation.

For deployment readiness, inspect existing non-secret configuration before asking setup questions. Show already-known simple machine facts such as hostname/address, deployment user, port, and target OS for confirmation. Ask only for missing or conflicting facts. Keep deployment-tool implementation identifiers such as logical target names, `targetName`, SSH aliases, profile paths, and trust-file paths internal unless troubleshooting or genuine ambiguity requires them.

Shared managed code keeps its canonical owner. When a consumer contains `CORE_BASELINE.json` or `DEPLOYMENT_BASELINE.json`, treat those baselines as ownership evidence. A temporary edit to a shared-managed consumer file may be used to diagnose or prove a reusable defect, but it is not the canonical deliverable.

When reusable Project Forge drift is detected, distinguish unexplained drift from an explained temporary upstream proof. Unexplained managed drift remains fail-closed before delivery writes. For explained drift, route through `/upstream-fix`, preserve `.project-forge/UPSTREAM_FIX_HANDOFF.md`, and offer one explicit `Continue consumer work with acknowledged Project Forge drift` override when the current work can proceed without committing the managed workaround. That override is session/work-item continuation authority only; it does not authorize committing shared-managed paths, editing baselines, bypassing required CI/policy, or claiming that the canonical fix has been adopted.

After an accepted continuation override, do not repeatedly halt normal consumer implementation solely because the same documented managed workaround remains present. Keep the handoff and workaround unstaged. Before consumer `/deliver`, warn about the acknowledged drift, selectively stage only accepted consumer-owned changes, and disclose when local validation depended on the workaround. Required CI/policy remains authoritative. If the workaround is staged, appears in the proposed consumer commit/PR, no longer matches the handoff, or ownership becomes ambiguous, stop and re-evaluate.

Package-managed generated Projects use `/project-forge-update`. Direct `/core-sync` remains only for component-only Core consumers without `PROJECT_FORGE_BASELINE.json` and is not part of the normal greenfield Project command surface.

Do not manually preserve a private consumer fork of shared managed code merely because the consumer exposed the bug. Consumer-owned product/application files remain normal consumer implementation scope.

After implementation review and local human acceptance, manually invoking `/deliver` authorizes routine short-lived-branch recovery/setup as needed, selective stage/commit/push, PR creation/update, and PR-CI inspection. `/deliver` then stops once for the explicit `Merge and finalize delivery` decision. When the PR still exactly matches the accepted implementation, that one choice combines final PR acceptance, merge authorization, post-merge CI observation, and safe delivered-branch finalization.

Changed PR evidence re-opens the relevant review gate. Merge never implies production-deployment authorization.

## Post-delivery documentation and learning handoff

After engineering delivery is complete, documentation impact and learning are **non-blocking follow-ups**, not new delivery states or gates.

Use the accepted work-item/PR diff conservatively to classify likely documentation impact. Examples:

- public API/contract changes may affect architecture/runtime/API narrative;
- services, dependencies, messaging, caches, auth, observability, deployment topology, or failure handling may affect System evidence;
- entities, migrations, schema/DDL, ORM, queries, constraints, or indexes may affect DB evidence;
- environment/deployment changes may affect operations docs;
- durable developer/test workflow changes may affect engineering docs;
- a consequential architectural tradeoff may deserve an ADR recommendation.

A changed file proves relevant evidence was touched; it does not by itself prove a runtime or physical-schema change.

When the relevant tools exist and prerequisites are safe, `/deliver` may best-effort prepare **disposable** evidence/site projections under:

```text
.project-forge/docs-cache/system/
.project-forge/docs-cache/database/
.project-forge/docs-site/
```

System evidence may be reconstructed from the current repository. Database evidence may be generated automatically only when a safe local development/test database path is already explicit; never guess a path merely to populate docs.

If `tools/project-forge-docs/docs-site.py` exists, a build of the local documentation projection may follow safe lab preparation. Failure to build docs or a lab projection does not change `DELIVERY COMPLETE`.

Do not silently rewrite project-owned narrative or approve/create an ADR solely because implementation evidence changed. Instead surface a compact `DOCUMENTATION IMPACT` handoff, for example:

```text
DOCUMENTATION IMPACT

✓ Project brief: no material change detected
★ System evidence: changed; current projection prepared
★ Database evidence: changed; /db-lab recommended
○ ADR consideration: new synchronous external dependency introduced

/docs — explore the current project documentation
```

Use only claims supported by observed evidence. Keep `/docs`, `/db-lab`, `/system-lab`, `/code-walkthrough`, and `/learning-review` visible when useful, but never require them solely to complete engineering delivery.

Do not pin or automatically escalate models.
