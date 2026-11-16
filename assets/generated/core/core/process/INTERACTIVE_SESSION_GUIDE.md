# Continuous Interactive Sessions

The following modes are continuous after the human explicitly enters them:

```text
/grill-me
/refine-requirements
/coach
/learning-review
/deployment-readiness
```

Default cadence:

```text
question
→ human answer
→ critique / teach / reconcile / update as permitted
→ next material question
```

## Question presentation

Choose the question shape based on what the interaction is trying to learn or decide.

When a material question has a reasonable bounded answer space and the human is choosing or confirming a decision, prefer a concise choice-first presentation:

- offer a small set of plausible choices, normally 3-6;
- include `Other / specify` when the choices are not exhaustive;
- include `Not sure — recommend one` when the human can reasonably delegate the choice;
- accept a choice label/text or a free-form answer;
- treat choices as interaction aids, not additional requirements.

### Host-native structured choice UI

When the current host exposes a structured question/choice UI, use it for bounded choices instead of rendering a plain numbered chat menu. In VS Code, use the native question surface exposed by the host, such as `vscode_askQuestions` when available.

Presentation rules:

- use **single-select** when the choices are mutually exclusive or one action is being authorized;
- use **multi-select** only when selecting several choices at the same time is semantically valid;
- preserve one-material-question-at-a-time cadence whenever practical even if the host can batch questions;
- keep consequence/action labels such as `[READ ONLY]`, `[REQUIREMENTS GATE]`, `[PLAN APPROVAL + CODE WRITE]`, or `[GIT + GITHUB WRITE]` visible when they matter to authorization;
- include `Other / specify` or host-supported free-text input when the option set may be incomplete; after `Other / specify`, collect the missing value without forcing another invented menu;
- accept equivalent free-text answers even when a structured selector is shown, unless the host UI itself requires a selection;
- map the returned structured value to the same semantic choice the workflow would have accepted by label/text.

### Human review surface presentation

Before a substantive approval gate, follow the review-surface contract in `HUMAN_GATES.md`.

1. Identify the exact PRIMARY review subject for the current work item/gate.
2. Separate supporting CONTEXT and TRACEABILITY material when useful.
3. Put the best available PRIMARY review surface in front of the human before asking for approval.
4. Capture the actual presentation result when the host reports one.
5. Render the explicit approval/action choice with the same exact work-item/artifact identity inside the question itself.

Use the host's native surface when it is stronger than prose:

- Markdown artifact → rendered Markdown preview when supported;
- JSON approval artifact → formatted editor/preview plus a concise summary;
- implementation plan → native plan surface or durable plan document;
- implementation acceptance → Source Control / meaningful diff review;
- PR acceptance → exact PR/diff surface at the observed head.

In VS Code, when the Project Forge companion extension is installed and the host can invoke VS Code commands, `projectForge.openReviewArtifact` is the preferred Project Forge-owned action for repository artifacts. Pass the exact workspace-relative artifact path. The command is presentation-only and must reject targets outside the open workspace and ambiguous multi-root matches rather than guessing from editor focus.

On hosts that expose the Project Forge language-model review tool, use it only with the exact already-resolved PRIMARY artifact path. Its result is presentation evidence, not approval. The result should distinguish resolved artifact URI, requested presentation mode, actual opened mode, cancellation, and failure/unavailable state. For Markdown, distinguish rendered Markdown from ordinary editor-preview fallback.

If the host exposes its own safe resource-opening or diff-opening capability, it may use that directly instead. Do not require the Project Forge command/tool when the host already provides a stronger native review surface.

Do not automatically open every supporting document. Foreground only the PRIMARY review subject and list supporting context explicitly.

For every artifact-backed gate, put the exact artifact path/link inside the approval question itself. Do not make the human hunt through earlier commentary for the link. The question should also identify the work item, approval purpose, and truthful presentation status.

If automatic opening is unavailable or fails, say so briefly in the gate and provide a deterministic fallback. For Markdown in VS Code on Windows, tell the human to open the exact linked file and press `Ctrl+Shift+V`. Do not block planning merely because automatic opening is unavailable, and never fabricate a successful open.

Opening a review surface is never approval. A preview event, editor focus, file read, diff display, navigation action, cancellation, or `where is it?` question is read-only presentation and must not advance a gate.

For an implementation-plan gate, explicitly state that implementation has **not** started before offering approval. The approval action must be distinct from plan revision/read-only review actions.

When the approval subject changes materially, present and link the revised PRIMARY artifact before asking again. Do not reuse stale presentation evidence or stale approval for the revised subject.

### Recommendations inside choices

A recommendation is optional advice, not a required field and not an accepted decision.

- mark **exactly one** choice as `RECOMMENDED` only when current evidence, repository policy, or a clear engineering tradeoff supports it;
- use the host's `recommended` indicator/metadata when available and add a brief rationale in the choice description or surrounding prompt;
- when the host does not expose recommendation metadata, append `[RECOMMENDED]` to exactly one option label and keep the concise rationale visible in the prompt or option description;
- a default/preselected value may match the recommended option, but a default alone must never communicate that an option is recommended or human-approved;
- do not mark multiple choices recommended;
- do not invent a preference merely to populate recommendation metadata;
- when no option is clearly better, present the choices with **no recommendation** and do not use a default that implies a preference;
- if the human asks for no recommendation on a specific decision, omit the recommendation for that question only; later questions may still include evidence-backed recommendations;
- the human may select a different option or answer free-form;
- record only the human's selected/confirmed answer as the requirement, action, or decision. Never record the recommendation itself as accepted state.

A structured selector is presentation, not extra authorization. Selecting a choice authorizes only the action/session that the workflow says that choice authorizes.

When the host has no structured question UI, use a concise textual fallback. A numbered or lettered list is acceptable **only as this fallback**; keep the same labels/recommendation/consequence tags, including `[RECOMMENDED]` when one option is evidence-backed, and accept the number/letter, label, or a free-form answer. Do not use a plain numbered list as the normal VS Code interaction when native structured choice UI is available.

### Interactive terminal handoff

When an authorized action must run in the developer's own terminal because it requires an interactive prompt, secure local input, or another terminal-owned interaction, treat the command handoff as continuation of the workflow rather than as a generic blocker.

- If the action has its own bounded authorization, collect that authorization first through the host-native structured question control when available. Once the exact action is authorized, do not ask for the same permission again merely because execution moves to the terminal. When the installed deterministic CLI exposes a scoped `--yes` option, prefer it **only after** the matching exact plan/stage has been approved through the native Chat gate, avoiding duplicate typed confirmation phrases. Do not use `--yes` as a standing default, bypass a changed plan, or suppress independent destructive/trust/credential authorizations. SSH passphrase entry remains interactive and never belongs in Chat.
- Immediately after authorization, provide the exact command in a **standalone fenced code block**. State the working directory when it is not already unambiguous. Do not bury the command inside explanatory prose.
- Briefly describe the local prompt the developer should expect and which sensitive values must be entered **only in the terminal**. Never ask for a passphrase, password, token, private key, or other secret through chat, and never place such a secret in the command arguments merely to avoid an interactive prompt.
- State what observable result or concise evidence the developer should report back so the workflow can verify the action and continue. Prefer deterministic verification after the local step instead of asking for secret-bearing terminal transcripts.
- Do not lead with or dwell on the assistant's inability to send keystrokes when a copyable command is an adequate path forward. Capability limitations may be stated briefly only when they materially affect the next action.
- If the host exposes terminal-send support, it may insert the exact non-secret command for **human review/execution** rather than silently executing an interactive command. Keep interactive secret input local and never inject it through the host automation channel.

Keep questions open-ended when predefined choices would weaken the purpose of the interaction. This includes:

- user-authored problem/outcome/workflow framing where the human's own wording matters;
- factual values such as a hostname, IP address, path, account, observed error, or environment-specific fact;
- learning/understanding assessment where the human should explain or reason in their own words;
- debugging, design, or grilling questions whose purpose is to expose the human's reasoning before options or hints are introduced.

If an open-ended reasoning question stalls, options/hints may be introduced as scaffolding after the initial attempt. Do not manufacture bounded choices merely to make every question look structured.

For deployment readiness, discover existing local/repository configuration before asking factual questions. Show known simple environment/machine facts for confirmation and ask only for missing or conflicting facts. Do not lead with deployment-tool implementation identifiers such as `targetName`, SSH aliases, profile paths, or trust-file paths when the workflow can discover, reuse, or derive them.

Do not repeatedly ask `Do you want to continue?`.

Stop when:
- the human says stop/done/pause,
- the objective naturally completes,
- no material questions remain,
- a genuine approval/scope/action gate appears,
- the human switches workflows.

Continuous conversation never implies permission for unrelated file, Git, external-system, remote, or production writes.

For modifying sessions such as `/grill-me` decision reconciliation, requirement refinement, or deployment-readiness documentation, one explicit session-level authorization may cover focused updates within the defined scope; do not re-ask after every answer.

Compound action skills may also define their own bounded authorization. In particular, manually invoking `/deliver` after its prerequisites are satisfied authorizes routine branch/stage/commit/push/PR/CI mechanics within the accepted delivery scope. Do not interrupt that compound action with repeated ceremonial permission prompts. `/deliver` still stops for changed evidence, ambiguity/risk, and the explicit merge/finalize decision.

If a tool/channel interruption leaves a compound workflow partially complete, a later invocation should inspect current state and resume from the furthest safe point rather than assuming nothing happened or requiring the same routine authorization again.

`/wait-what` is different. It is a one-turn, read-only communication repair for the immediately preceding explanation. It re-establishes context and clarity, then returns control to the current workflow without silently continuing a pending action or approval gate.

## Operational continuity and bounded retries (PF-03/PF-04)

Use these rules within existing Project Forge skills and repository-defined
operations. This is **not** a new approval store, model selection policy, or
background execution system.

### Scope a working authorization before a consequential action

Before a multi-stage or unattended continuation, state a short **reviewed-stage
envelope** in the already-existing work item/review context:

- Exact Project, named logical environment/target, host identity where relevant,
  and intended operation(s).
- Immutable artifact, plan identity and reviewed evidence, including freshness
  and expiry when the installed capability exposes them.
- Allowed mechanical continuation and **separate** Production runtime, public
  route, trust/credential, destructive data, merge, and release boundaries.
- Remaining secret-input or human decision points and the precise stop conditions.

One currently approved, unchanged reviewed stage authorizes its supported
routine mechanics; never request a second identical shell phrase or chat
permission when the installed deterministic command supports scoped execution.
However, authorization is **not** a standing token: changed target, plan, peer,
data/backup risk, credential, identity, exposure, trust or other consequence
reopens the relevant gate. Never infer indefinite authority from elapsed time
or a prior session. Explain any interactive passphrase/provider action **before**
the developer leaves an unattended workflow; do not promise unattended
completion if required local input or a human approval remains.

### Read safe results without losing the failed phase

When the installed Deployment Kit supplies an additive safe
`diagnosticSummary`, use it only if the **observed installed** schema and
capability version match the documented contract (currently schema 1,
`remote-environment-setup` capability 1). Preserve phase, fixed reasonCode,
proved/failed/blocked/notChecked dimensions, observedAt, mutation, consequence
and any safe evidence reference. An unknown capability, reason, malformed
summary or mixed stderr becomes **unclassified**, never green/success.
Report unsupported or older installed tooling honestly; do not reconstruct the
same field by parsing private exceptions or create a new runtime prerequisite
during Bootstrap. A concise summary is not a complete reviewed mutation plan.

### Avoid no-information attempts and context inflation

If the **same** fixed reason code and non-secret exact target/phase/context have
failed twice with unchanged inputs **and no new evidence**, change the method
(e.g. inspect a different bounded proof) or stop with the precise missing fact.
Do not perform a third identical attempt, rerun an unchanged reviewer objective,
replay a failed login, or repeatedly ask for the same fact. A newly loaded SSH
agent, changed plan, confirmed host identity, updated installed helper or other
material new evidence resets the same-phase retry comparison.

Start a continuation with the smallest authoritative repository/state
checkpoint: current work-item state, exact commit/PR/CI, package/component
provenance, observed capability and proof freshness, unresolved decision, and
next safe action. Follow links to deeper current evidence only as needed.
Do not reload a whole incident transcript, broad skill catalog or all historical
retries just because context is available. Favor one bounded wait/read of a
known CI run ID over repeated short polling and large tool output. Use only
relevant skill and artifact slices; keep full evidence available separately.

Measure improvements with one matched, bounded replay holding the same fault,
safety obligations and environmental assumptions. Record model/tool rounds,
operator prompts, elapsed/waiting time and cache-adjusted token volume:
input tokens minus cache reads plus output tokens, respecting each counter's
semantics. Candidate >=50% reductions are **targets**, not guaranteed savings.
Never hide failed checks, truncate material mutation evidence, skip security
gates, or change model tier automatically to make metrics look better.
