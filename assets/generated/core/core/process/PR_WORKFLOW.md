# Pull Request / Merge Workflow

After:

```text
implementation complete
→ relevant local checks satisfactory
→ Reviewer READY
→ human meaningful local-diff approval
```

run `/deliver`.

Normal delivery is intentionally streamlined:

```text
/deliver
→ establish/recover short-lived work branch if needed
→ selective stage
→ verify staged diff
→ commit
→ push
→ create/update PR
→ PR CI
→ one MERGE + FINALIZE decision
→ merge
→ post-merge default-branch CI when configured, plus any observable enforced checks
→ safe delivered-branch cleanup
→ delivery complete
```

Invoking `/deliver` is the bounded authorization for the routine mechanics through PR creation/update and PR-CI inspection.

In a live capable host, **one bounded check watch** (for example, `gh pr checks <PR> --watch --interval 20`, subject to real host timeout/cancellation) should continue straight to the existing single Merge and finalize gate as soon as checks succeed. There is no need to invoke /deliver a second time when the same interactive session and exact evidence remain available. Never auto-merge or wait invisibly in the background. When a watch cannot complete, preserve the exact PR/head SHA/run ID and offer an accurate resume checkpoint; resume /deliver without redoing commits, PRs, approval or CI dispatches. After authorized merge, observe post-merge CI similarly, and distinguish the separate PR and main CI **events** from /deliver invocations.

Cost guidance: optionally use Project-owned strict change-aware CI for package-managed-only changes; see CHANGE_AWARE_CI_GUIDANCE.md. The baseline/integrity gate always runs and unknown, mixed app/deployment/auth and manually dispatched changes run full validation. Do not path-filter an entire required CI workflow. Do not add separate branch/commit/push/PR/CI permission prompts when the work remains inside the already-reviewed delivery scope.

Key rules:
- existing repository branch/PR/CI/merge policy outranks Project Forge defaults,
- `required CI` means the configured workflows/checks that apply to the exact commit plus any additional enforced repository policy observable through available tooling,
- inability to read branch-protection/ruleset admin settings alone is not a human gate and must not be converted into a Settings-page questionnaire; ask only when missing policy data creates a concrete block to merge/release,
- `/start-work` should establish the short-lived work branch when implementation begins; `/deliver` may recover safely if reviewed work is still on the default branch,
- PR templates are internal scaffolding and do not require a separate validation ceremony,
- because implementation was already meaningfully accepted locally, a final PR acceptance prompt does not need to be separate from merge when the PR head/diff still exactly matches that accepted scope,
- green PR CI is necessary evidence but never merge authorization by itself,
- the explicit `Merge and finalize delivery` choice is both final acceptance of the observed PR and merge authorization,
- if new commits/material diff changes/conflicts/regressed checks appear, final PR review is required before merge,
- merge authorization is not production-deployment authorization,
- for a normal short-lived delivered branch, `Merge and finalize delivery` also authorizes safe local/remote cleanup after applicable post-merge default-branch CI/policy evidence is satisfied,
- no second branch-deletion prompt is needed for that delivered branch when the cleanup evidence remains exact and safe,
- unrelated, accumulated, protected/default, release/integration/environment, policy-retained, changed, or ambiguous branches are preserved,
- squash/rebase merges require merged-PR/head-SHA evidence before any local force deletion is considered safe,
- do not claim checks passed or branches were deleted unless the remote/local state was actually observed,
- do not silently modify code after CI failure; inspect/diagnose and return through review as warranted,
- rerunning `/deliver` after interruption resumes from the furthest observed safe delivery state instead of repeating completed actions or re-asking routine authorization.

If PR CI or post-merge CI remains pending beyond the practical interaction/tool window, preserve state and report that rerunning `/deliver` will resume observation/finalization.

Use `/cleanup-branches` for preview-first maintenance of accumulated, previously retained, unrelated, or otherwise out-of-band branches outside the active `/deliver` flow.
