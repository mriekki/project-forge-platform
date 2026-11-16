# Human Gates

Use explicit human gates where consequences warrant them.

Typical gates:
- workspace/setup acceptance before the first substantive work item,
- material requirements/scope approval when detailed requirements matter,
- substantive implementation-plan approval for STANDARD/ELEVATED work,
- meaningful local implementation/diff acceptance,
- merge/final-delivery decision after PR CI when the PR still matches the accepted implementation,
- unrelated/out-of-band branch deletion when not already covered by a bounded delivery/cleanup choice,
- external/remote/system writes not already covered by an explicitly invoked bounded workflow,
- first production deployment,
- destructive recovery/restore,
- publishing a release/tag.

Workspace/setup acceptance is distinct from generation or installation. Generated files, installed tools, operational dependencies, editor/agent discovery, and human usability are separate facts. A setup script or static diagnostic may provide evidence, but only the human accepts the checkout as ready for the next intended work item.

A human gate is meaningful only when the human understands what is being approved. If the explanation immediately before a gate did not land, re-explain it before asking for approval again. `/wait-what` is the standard read-only communication-repair path when available; invoking it never implies approval of the pending action.

## Human review surface contract

Before asking for any substantive human approval, identify the exact **review subject** and put the best available review surface in front of the human.

Classify review material when more than one artifact is relevant:

```text
PRIMARY — the artifact/diff/plan the human is deciding on
CONTEXT — supporting material that may help review
TRACEABILITY — provenance/reference material that is not itself being approved
```

When the current host supports opening or foregrounding the PRIMARY review surface, do so automatically immediately before the gate. Prefer the surface that best matches the decision:

- Markdown requirements, briefs, ADRs, and design documents → rendered Markdown preview when available;
- structured JSON approval artifacts → formatted source/editor preview plus a concise human-readable summary;
- implementation plans → the host's native plan surface, or a durable plan document when one exists;
- implementation acceptance → the meaningful local diff / Source Control review rather than a prose-only file list;
- final PR acceptance → the observed PR/diff at the exact reviewed head;
- other repository artifacts → the host's safest read-only preview/editor surface.

Do not open every supporting document and steal focus. Open the PRIMARY surface; name CONTEXT and TRACEABILITY material explicitly and make it easy to open when needed.

Every artifact-backed approval question must be self-contained. The gate itself must identify:

- the specific work item or approval scope;
- the exact approval purpose/subject;
- the exact PRIMARY artifact path or clickable link that is being approved;
- presentation status when an automatic open was attempted (`rendered Markdown opened`, `editor fallback opened`, `automatic opening unavailable/failed`, or equivalent truthful evidence);
- the consequence labels for each action.

Do not rely on an artifact link in earlier commentary, the active editor, a global plan, or another work item's document. The PRIMARY artifact named in the gate must be the same artifact that was requested/opened for presentation.

If the host cannot open the review surface automatically, provide the exact path/link inside the approval question and a deterministic manual fallback. For Markdown in VS Code on Windows, the fallback may say to open that exact file and press `Ctrl+Shift+V`. Never imply that a path reference alone is equivalent to review.

Opening, previewing, foregrounding, or navigating to a review surface is **read-only presentation**. It never communicates approval, authorization, or acceptance. Only the explicit gate choice does that.

If the PRIMARY artifact changes materially after approval, present and link the revised PRIMARY artifact before asking again. Navigation, preview, cancellation, or a `where is it?` question never preserves or creates approval for a materially changed subject.

Do not gate routine mechanics individually after a bounded action is already authorized.

Missing access to GitHub admin policy metadata is not itself a human gate. Use configured workflow/check results, PR mergeability, repository documentation, and any observable enforced policy as evidence. Do not ask the human to open GitHub Settings and transcribe branch-protection/ruleset check names merely to continue; ask only when unavailable policy information creates a material unresolved decision at merge, release, or another consequential action.

## Implementation-plan review gate

For STANDARD/ELEVATED work, invoking `/start-work` authorizes requirement/context inspection, risk assessment, and implementation planning. It does **not** authorize substantive implementation by itself.

The required boundary is:

```text
requirements/context ready
→ implementation plan produced
→ PRIMARY plan review surface opened/foregrounded when supported
→ HUMAN IMPLEMENTATION-PLAN APPROVAL
→ short-lived work branch setup
→ substantive implementation
```

Before the approval choice, state unambiguously that implementation has **not** started. The gate should identify the work item, risk level, exact review subject/artifact, presentation status, key plan coverage, and any unresolved material decisions.

Use an explicit action set equivalent to:

```text
IMPLEMENTATION PLAN REVIEW REQUIRED

Work item: <ID / key / concise change>
Approval subject: final proposed implementation plan
Primary artifact: <exact clickable plan link/path | native plan surface>
Presentation: <rendered Markdown opened | editor fallback opened | automatic opening unavailable/failed | native plan foregrounded>

Implementation has NOT started.

1. Approve plan and begin implementation [PLAN APPROVAL + CODE WRITE]
2. Request changes to the plan [PLAN ONLY]
3. Review assumptions / risks [READ ONLY]
4. Stop [NO ACTION]
```

When the host exposes structured choice UI, render these as a single-select decision instead of a numbered menu while preserving the consequence labels and the same work-item/artifact context in the question itself.

For ELEVATED work, Reviewer challenges the proposed plan before the human gate. Reconcile material Reviewer findings into the final proposed plan, then put that final plan in front of the human. Do not ask the human to approve an initial plan while separate Reviewer objections remain unresolved.

After approval, routine implementation details may evolve without ceremonial re-approval. Reopen the plan gate when evidence requires a **material** change to approved architecture, scope, schema/data handling, security model, externally visible behavior, major dependencies, or verification strategy. Show what changed, why it changed, and the revised plan before implementation continues. The renewed gate must link/present the revised PRIMARY artifact rather than relying on the stale approved plan.

## Implementation branch setup

Once implementation itself is authorized, creating/switching to the repository-appropriate short-lived work branch is routine setup, not a separate decision gate, when branch policy/naming and work-item scope are clear and the operation preserves the worktree without history rewriting.

For STANDARD/ELEVATED work, this branch setup follows plan approval. For LIGHT work, it is part of the human-selected implementation action.

Stop only when branch choice/state is ambiguous, unrelated work is present, or the operation would require stash/reset/rebase/force/history rewriting.

## Streamlined /deliver authorization

Because `/deliver` is manually invoked after implementation review and meaningful local acceptance, invoking it is one bounded authorization for routine delivery mechanics within that accepted scope:

```text
recover/create the short-lived branch when needed
→ selective stage
→ staged-diff verification
→ commit-message generation
→ commit
→ normal push
→ create/update PR
→ PR-body population
→ PR-CI inspection/rechecks
```

Do not separately ask `Create branch?`, `Commit?`, `Push?`, `Create PR?`, or `Check CI?` when those actions remain safe and within scope.

`/deliver` invocation does **not** authorize merge, production deployment, force push, code fixes after CI failure, unrelated branch deletion, scope expansion, or destructive/history-rewriting Git operations.

## Combined final acceptance + merge gate

When the PR head/diff still exactly represents the implementation the human already accepted locally, Reviewer is READY, configured PR CI is green, any additional observable repository-required checks are satisfied, and repository policy/mergeability are satisfactory, final PR acceptance and merge authorization may be combined into one meaningful choice:

```text
Merge and finalize delivery [HUMAN ACCEPTANCE + GITHUB/GIT WRITE]
```

That explicit choice covers only the observed PR and its normal short-lived delivered branch. It authorizes:
- final acceptance of the PR as observed,
- merge using the approved repository strategy,
- observation/recheck of applicable post-merge default-branch CI/policy,
- safe finalization of that delivered short-lived branch after that CI/policy evidence is satisfied.

It does not authorize deleting any other branch, bypassing changed evidence, or deploying to production.

If new commits, material diff changes, conflicts, or regressed checks appear after local acceptance, final PR review becomes a real gate again before merge.

If the repository/human explicitly requires branch retention, preserve the delivered branch. If safe cleanup cannot be proven, preserve it and report the exact reason rather than inserting another ceremonial prompt.

A later production deployment, unrelated branch cleanup, release publication, destructive recovery action, or newly changed implementation remains a separate explicit gate.

The principle is:

```text
conversation continues automatically
routine mechanics are grouped when safe
branch setup/finalization are automatic inside explicit bounded workflows
changed evidence re-opens the relevant review gate
consequential decisions remain human-controlled
```
