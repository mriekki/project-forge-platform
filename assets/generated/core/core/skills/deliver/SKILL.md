---
name: deliver
description: "Streamlined delivery after implementation review/approval: short-lived branch recovery/setup, selective commit/push/PR/CI mechanics, one explicit merge/finalize gate, post-merge CI, safe delivered-branch cleanup, and optional non-blocking learning handoff."
argument-hint: "[optional work-item ID or external key]"
user-invocable: true
disable-model-invocation: true
---

# Deliver

Native Codex invocation is `$deliver` from `.agents/skills/deliver/SKILL.md`; Copilot uses `/deliver`. This is the same Core contract, not a new permission source. Verify real local `git` / `gh` capabilities and require human meaningful-diff acceptance and the single merge/finalize gate regardless of editor/agent. Use a textual fallback when a Copilot-only UI/agent tool is missing; do not claim it ran. See `docs/project-forge/CODEX_EXECUTION_SURFACE.md`.

`/deliver` is the clear handoff after:

```text
implementation complete
→ relevant local checks satisfactory
→ Reviewer READY
→ human meaningful-diff approval
```

Existing repository conventions outrank Project Forge defaults. Preserve branch rules, PR template, CI, merge strategy, required reviews, long-lived branch policy, and other repository policy.

## 1. Authorization model

Because `/deliver` is manually invoked, invoking it is one bounded authorization for the routine delivery mechanics of the already-reviewed/accepted work item. Keep a delivery started in VS Code Copilot Chat in that interface when host tools can run the deterministic repository commands; a separate Copilot CLI session is not required for automation:

```text
establish/recover the short-lived work branch when needed
→ selective stage
→ verify staged diff
→ generate repository-appropriate commit message
→ commit
→ normal push
→ create/update PR
→ populate PR body from observed evidence
→ inspect/recheck PR CI
```

Do **not** ask separate `Create branch?`, `Stage?`, `Commit?`, `Push?`, `Create PR?`, `Mark ready?`, or `Check CI?` questions when those actions are safe, deterministic, and within the current delivery scope.

Invocation does **not** authorize merge, production deployment, force push, unrelated branch deletion, scope expansion, code fixes, or destructive/history-rewriting Git operations.

### Linked GitHub Issue and local-document traceability

When the configured source is `github-issues`, resolve the **exact canonical Issue** first and include its verified URL in the PR/work-item traceability. A prior stable `FB-...`/`EN-...` ID is not a GitHub Issue number; use only verified Issue/document mapping. Preserve any existing version-controlled approved `docs/work-items/` requirements and plan links. Do not paste a duplicate Issue body into local Markdown, reset approved requirements, silently change acceptance scope, or close a work item solely because code merged. Distinguish engineering delivery from verified Production release. Missing Issue access or conflicting mappings block Issue-state updates and must be reported without altering the human review and merge gates.

## 2. Phases

```text
A. RESUME / PREFLIGHT
B. ROUTINE PR PREPARATION — automatic within /deliver authorization
C. PR CI — automatic read/recheck within practical limits
D. MERGE + FINALIZE DECISION — one human gate
E. POST-MERGE DEFAULT-BRANCH CI — automatic observation
F. DELIVERED-BRANCH FINALIZATION — automatic when authorized and safe
G. DELIVERY COMPLETE
H. OPTIONAL LEARNING HANDOFF — visible, read-only/non-blocking
```

Phase H never changes whether engineering delivery is complete.

## 3. Resume-aware initial inspection

Inspect only what is needed to determine the furthest safe delivery state, such as:

```text
git branch --show-current
git status --short --branch
git diff --stat
git diff
git diff --cached --stat
git log -1 --oneline
git remote -v
```

When available:

```text
gh auth status
gh pr status
```

Resolve current work-item/review evidence and detect already-completed delivery steps.

If implementation, required local checks, Reviewer, or human meaningful-diff approval are not ready, route back to the missing gate. Do not perform delivery writes merely because `/deliver` was invoked too early.

If `/deliver` is rerun after interruption/tool unavailability, continue from the observed safe state. Do not repeat already-completed branch/commit/push/PR operations and do not ask the human to re-authorize the same routine mechanics.

Examples:
- branch exists + changes uncommitted → continue with selective staging/commit/push/PR;
- commit exists + branch not pushed → push and continue;
- branch pushed + no PR → create PR and continue;
- PR exists + CI pending → inspect/recheck CI;
- PR merged + post-merge CI pending → resume observation/finalization rather than starting over.

## 4. Short-lived branch handling

Normal implementation should already be on a short-lived work branch because `/start-work` establishes it when implementation begins.

If reviewed, scoped, uncommitted work is still on the default/integration branch, `/deliver` may recover automatically by creating/switching to the repository-appropriate short-lived work branch while preserving the current worktree.

Branch naming order:
1. repository/team convention when defined,
2. an already-existing branch clearly tied to the work item,
3. Project Forge fallback: `<lowercase-work-item-id>-<concise-slug>` for ID-backed work, or `work/<concise-slug>` for an ad hoc change.

Before creating/switching, capture enough worktree evidence to confirm the scoped diff. After switching, verify the same files/content remain changed and no work was lost or broadened.

Do not ask a separate branch-creation question when the branch operation is safe and deterministic under this rule.

Stop instead when:
- branch policy/naming is materially ambiguous,
- an intended branch already exists with divergent/unrelated work,
- unrelated/unexpected files are present,
- switching would require stash/reset/rebase/force/history rewriting,
- repository policy forbids the planned branch operation.

## 5. Routine PR preparation

Proceed automatically within `/deliver` authorization:

1. Selectively stage only the accepted delivery scope. Do not use blind `git add .` when unrelated changes exist.
2. Inspect staged diff/stat and verify it still matches the human-accepted implementation scope.
3. Generate a concise repository-appropriate commit message; do not create a separate commit-message approval ceremony unless ambiguity is material.
4. Commit.
5. Push normally without force.
6. Create a normal PR when none exists, or update/use the existing branch PR when appropriate.
7. Use Draft PR only when repository policy/convention requires it or meaningful work is still intentionally incomplete. Because `/deliver` begins after implementation/review acceptance, a normal ready PR is the default Project Forge behavior.
8. Populate the PR body from actual evidence only.
9. Inspect PR CI.

The repository PR template is internal scaffolding. Do not ask the human to validate the template itself.

PR evidence may include:
- work item,
- change summary,
- approved requirements/acceptance criteria,
- local checks actually observed,
- Reviewer verdict,
- known limitations/follow-up,
- CI status when observed.

Do not claim evidence that was not observed.

For work with a stable work-item ID, keep one hidden Project Forge navigation marker in the PR body using the exact resolved ID:

```html
<!-- project-forge-work-item: <ID> -->
```

The marker is navigation metadata only. It does not prove requirement approval, implementation acceptance, review, CI, merge readiness, delivery completion, deployment, or any other lifecycle state. Never use the marker alone to satisfy a gate.

When `/deliver` resumes an existing PR that clearly corresponds to the same ID-backed work item and the marker is absent, adding the marker is routine PR-body maintenance within the existing `/deliver` authorization. Preserve the rest of the existing PR body and do not add or rewrite the marker when the work-item identity is ambiguous. For ad hoc work without a stable work-item ID, omit the marker rather than inventing one.

## 6. Stop conditions during routine delivery

Stop before/during routine writes for:
- unrelated/unexpected files,
- possible secrets,
- unclear work-item boundary,
- known failing required local checks,
- Reviewer `CHANGES REQUIRED`,
- conflicts,
- Git/GitHub authentication/permission failure,
- unexpected generated/tracked files,
- repository policy that blocks the planned action,
- a branch/remote state that requires rebase/reset/force or other history rewriting.

Never force-push unless separately and explicitly authorized.

## 7. PR CI and policy evidence

Throughout this skill, CI/policy satisfaction means:
- the repository-configured workflows/checks that apply to the exact PR or default-branch commit have completed successfully; and
- any additional repository-enforced policy that is observable through available repository/GitHub tooling is also satisfied.

Do not interpret `required` as a mandate to read branch-protection or ruleset admin settings. When those settings are unavailable, use observable workflow/check results, PR mergeability, repository documentation, and any other visible policy evidence.

Do not ask the human to open GitHub Settings and transcribe required-check names merely to continue delivery. Stop only when unavailable policy data creates a concrete ambiguity that actually blocks merge, release, or another consequential action.

Inspect the configured/observable PR CI and checks without asking permission for each recheck.

### Pending

When the host provides a live, cancelable terminal or GitHub watch facility, prefer **one bounded CI watch** after creating/updating the PR over asking the Builder to invoke /deliver again. The watch is an observation, not a GitHub Actions re-run or workflow_dispatch:

- Capture the exact PR URL/number, head SHA, required check names and current statuses. Use a supported command such as `gh pr checks <PR> --watch --interval 20` in the correct repository, with an actual host-enforced timeout/cancellation (recommended upper bound **8 minutes**) and user-visible progress. For Codex, VS Code Copilot or ChatGPT, use only real available tool capabilities; never promise a background follow-up.
- If the watch turns green while the **same interactive session** is active, re-fetch the PR head SHA, diff/mergeability and observed policy evidence and immediately show the **single** section 8 Merge and finalize delivery gate. Do **not** ask the Builder to rerun /deliver first.
- If the observed PR head changes, a check fails, a check disappears or branch rules are unclear, stop with a precise explanation and no merge. Do not auto-fix code, auto-merge, rerun expensive CI, or reset the approval gate.
- If the host cannot safely wait, the session is interrupted, a watch times out, or no CI status is accessible, stop with an exact **DELIVERY RESUME** checkpoint: PR URL/number, head SHA, current CI run/check URL and state, last accepted implementation/diff identity, and the next gate. The next /deliver invocation must revalidate live evidence and continue from there without duplicate commits/PRs or approval requests.
- If CI is already green on the first check, skip watching entirely and advance to section 8. Use a single watch per unchanged CI phase; do not spam GitHub API or restart failed workflows.

Use bounded read-only polling/rechecks when practical. If CI is still running beyond the practical interaction/tool window, report:

```text
PR CI: RUNNING
Delivery state preserved. Re-run /deliver to resume.
```

Do not insert a new write-authorization prompt merely because CI is pending.
Use the exact known workflow/run ID and one bounded wait/recheck when possible
rather than repeated short polling, reloading the same CI output, or relaunching
a Reviewer on an unchanged objective. Treat two unchanged, no-information
attempts at one phase as a stop/change-method condition. Preserve the PR/commit
and CI status as a concise authoritative resumption checkpoint. See
`core/process/INTERACTIVE_SESSION_GUIDE.md` for freshness and context rules.

### Failed

Inspect failing evidence when available. Report the failure and offer inspect/diagnose/targeted-fix/stop. Do not automatically change code because CI failed.

Any code fix returns through the review/meaningful-diff gate as warranted before delivery resumes.

### Green

Before the merge gate, verify:
- PR head branch/head SHA are the expected delivered branch/commit,
- no unexpected commits appeared,
- PR diff still represents the locally reviewed/accepted implementation,
- Reviewer/policy/check state is still satisfactory,
- PR is mergeable under observed repository rules.

If the final PR differs materially from the accepted local implementation, require final diff review before merge. Do not silently treat changed evidence as accepted.

If a Draft PR was required earlier and all readiness conditions are now satisfied, mark it ready as routine delivery mechanics unless repository policy requires a different human/reviewer action.

## 8. Single merge + finalize gate

When PR evidence still matches the accepted implementation and CI/policy are satisfactory, combine final PR acceptance and merge authorization into one meaningful gate. First show:

```text
MERGE READY

PR CI: GREEN
Reviewer: READY
PR diff: matches accepted delivery scope
Mergeable/policy: <observed state>
```

Then render the mutually exclusive gate through the host-native **single-select structured choice UI** when available. In VS Code use the native question surface such as `vscode_askQuestions`. Offer:

- `Merge and finalize delivery` `[HUMAN ACCEPTANCE + GITHUB/GIT WRITE]` — `RECOMMENDED`
- `Review final PR diff first` `[READ ONLY]`
- `Leave PR open` `[NO ACTION]`

Use a numbered text list only when structured choice UI is unavailable.

Selecting `Merge and finalize delivery` means:
- the human accepts the final PR as observed,
- merge is authorized using the repository-approved strategy,
- applicable post-merge default-branch CI/policy may be observed/rechecked automatically,
- after that CI/policy evidence is satisfied, the delivered normal short-lived branch may be finalized automatically locally/remotely under the safety rules below.

Do not present a second `Accept PR?` prompt immediately followed by `Merge?` when the evidence has not changed.

If the human chooses to review the final PR diff, return to this same merge gate after the review if no new issues appear.

If merge strategy is materially ambiguous and repository convention does not resolve it, stop and ask rather than inventing one.

Before merge, record the PR head branch and head SHA so finalization can distinguish the approved delivered state from later work.

Stop before merge if checks regress, new commits appear, conflicts arise, or policy changes the state.

## 9. Post-merge default-branch CI

After authorized merge, inspect the actual configured default branch/workflows and any observable enforced checks automatically.

When the same session remains active and a bounded observable post-merge CI watch is available, continue to completion without a second /deliver invocation. Post-merge CI is **another GitHub Actions event** from PR CI; it does not indicate a second /deliver invocation, and /deliver must not dispatch a duplicate run. Recheck exact merged/default-branch SHA and CI. If the host cannot continue, emit an exact MERGED — DEFAULT-BRANCH CI PENDING resumption checkpoint (merge SHA, run URL, next safe cleanup step) and stop; never claim successful post-merge checks before they complete.

If configured post-merge default-branch CI is pending, use bounded read-only rechecks when practical. If still pending beyond the practical interaction/tool window, report:

```text
MERGED — DEFAULT-BRANCH CI PENDING
Delivery state preserved. Re-run /deliver to resume finalization.
```

Do not ask the human to authorize observation again.

If post-merge CI fails, report it clearly and inspect/diagnose; do not silently revert, modify production, or delete the delivered branch.

Only after configured post-merge default-branch CI and any additional observable repository-required checks are satisfied may delivered-branch finalization proceed. If the repository has no post-merge CI workflow/policy, state that explicitly and proceed using the observed merged/default-branch state.

## 10. Delivered-branch finalization

For a normal short-lived delivered branch, the `Merge and finalize delivery` gate choice already authorizes finalization. Do not ask a separate `Delete branch?` question.

Preserve by default:
- the configured default branch,
- protected branches,
- release/integration/environment branches intended to be long-lived,
- branches repository policy says to retain,
- a branch the human explicitly asked to retain before/during the merge gate,
- any branch whose state changed or became ambiguous after merge.

Before deletion, revalidate:
- the PR is still merged,
- the recorded PR head branch/head SHA are unchanged as delivery evidence,
- the remote branch, when present, still points to the recorded PR head SHA,
- no open PR now depends on the branch,
- the local branch has no commits beyond the recorded approved PR head,
- the working tree is safe to switch to the default branch.

Then:
1. switch to the default branch,
2. update it using the repository's normal non-rewriting method, usually `git pull --ff-only`,
3. delete the remote delivered branch when it still exists and policy allows,
4. delete the local delivered branch,
5. prune stale remote-tracking refs,
6. confirm final default-branch/working-tree state.

For the local branch:
- prefer `git branch -d <branch>` when Git recognizes it as merged,
- squash/rebase merges may make `-d` reject even when the PR is merged,
- only when merged-PR evidence is exact and the local head has no commits beyond the recorded PR head may `git branch -D <branch>` be used under the merge-and-finalize authorization.

An already-auto-deleted remote branch is `already clean`, not a failure.

Never use force deletion merely to bypass uncertainty.

If any safety condition fails, preserve the branch and report `BRANCH CLEANUP PENDING` with the exact reason instead of asking repetitive yes/no questions.

## 11. Delivery completion and optional learning handoff

First report the observed engineering outcome:

```text
DELIVERY COMPLETE

PR: MERGED
Default branch: UPDATED
Post-merge CI: GREEN / NOT CONFIGURED
Branch finalization: DELETED / RETAINED BY POLICY OR CHOICE / ALREADY CLEAN
```

If merge/default-branch delivery is complete but requested/authorized cleanup could not be performed safely, report:

```text
DELIVERY COMPLETE — BRANCH CLEANUP PENDING
```

and preserve the branch.

After engineering delivery is complete, use the accepted PR/work-item diff to classify optional learning relevance. This classification is read-only and does not create another delivery state.

Database relevance can include observed changes to entities/models, migrations, DDL/schema, SQL/query/repository/persistence code, indexes/constraints, ORM mappings, or transaction/concurrency behavior.

System-design relevance can include observed changes to APIs/contracts, service/module boundaries, cross-component dependencies, external integrations, messaging/events, caches, security/auth boundaries, observability, deployment/runtime topology, infrastructure, scaling/performance behavior, or failure handling.

A changed file proves that evidence was touched; it does not by itself prove a physical-schema or runtime-behavior change. Use `changed`/`affected` wording conservatively and verify deeper claims through the corresponding lab.

### Best-effort disposable workbench preparation

After merge, satisfactory post-merge/default-branch evidence, and update to the delivered default-branch checkout, `/deliver` may prepare current disposable learning artifacts automatically when all prerequisites are already safe and unambiguous.

System Lab:
- when system-design relevance is present and `tools/project-forge-system-lab/system-workbench.py` exists, it may run the exporter against the current repository;
- use a stable per-repository temp/cache output directory so an older disposable `workbench.json` can be compared before replacement;
- pass the accepted changed-file list via `--changed-file` when practical;
- never write generated workbench output into tracked project paths by default.

Database Lab:
- when database relevance is present, `tools/project-forge-db-lab/sqlite-workbench.py` exists, and a safe local development/test SQLite database path is already known from project setup/configuration/evidence, it may generate the current DB workbench;
- do not guess a database path;
- do not create a database, apply migrations, mutate data, inspect Production, or change code merely to prepare a learning artifact.

For either lab:
- artifact generation is read-only/best-effort;
- failure/unavailability is reported briefly and never changes `DELIVERY COMPLETE`;
- generation does not mean the human performed the learning activity or demonstrated understanding;
- do not open browser/UI automatically unless normal repository/local-workflow conventions make that expected and non-disruptive.

### Visible optional learning reminder

Keep learning visible while the change is fresh. Prefer this order:

```text
OPTIONAL LEARNING — recommended while this change is fresh

★ /db-lab changes <work-item>
  This work changed database structure or behavior.
  Explore affected relationships, queries, indexes, constraints, and ORM behavior.

★ /system-lab changes <work-item>
  This work changed system structure or runtime behavior.
  Explore affected components, flows, dependencies, tradeoffs, and failure modes.

○ /code-walkthrough <work-item>
  Walk through the implementation and changed-file flow.

○ /learning-review <work-item>
  Test your understanding.

Learning is optional and does not affect delivery state.
```

Only use `★` for a lab supported by the accepted change evidence. If a lab is not especially relevant, keep it visible as an available option when useful, for example:

```text
○ /db-lab
  Explore the current database schema, relationships, queries, indexes, and ORM behavior.

○ /system-lab
  Explore the current architecture, runtime flows, dependencies, scaling, and failure behavior.
```

Do not tell the human to "rebuild", "refresh", or maintain a generated diagram. Invoking a lab means inspect current evidence and generate/show the current view.

Do not turn these reminders into approval prompts. The human may invoke one, continue to deployment work, start another work item, or do nothing.

## 12. Deployment handoff

If the delivered work item owns release/deployment engineering, successful engineering delivery may hand off to the selected environment's state-driven readiness workflow:

```text
/deployment-readiness <environment>
```

Readiness re-discovers current state and continues from the furthest safe point; do not ask the human to choose `discovery`, `enable`, or `resume` merely because engineering delivery just completed.

The readiness workflow is environment-generic. Production remains an environment role with stronger policy; merge approval never implies remote or production-deployment authorization.

The optional learning handoff does not block or replace deployment readiness when deployment is the sensible next engineering action.

## 13. Relationship to /start-work, /next-step, and /cleanup-branches

`/start-work` establishes the short-lived work branch as routine implementation setup once implementation is actually authorized.

`/next-step` answers `Where am I?` and may surface optional learning choices without creating learning-only workflow states.

`/deliver` takes reviewed/accepted work through routine branch/commit/push/PR/CI mechanics automatically, then stops once for the merge-and-finalize decision. After successful engineering completion it may prepare disposable learning workbenches and shows an optional learning handoff without creating another gate.

`/cleanup-branches` is the standalone preview-first path for accumulated, previously retained, unrelated, or otherwise out-of-band branch housekeeping.
