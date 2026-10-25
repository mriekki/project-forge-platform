# Project Forge ChatGPT Contract — Existing Project

For an existing generated Project, the repository is the durable handoff and authoritative current-state record.

Do not restart `New Project:` / `New Project from:` discovery unless the human is intentionally re-baselining or importing the Project.

Legacy/versioned handoff files may remain as historical or troubleshooting reference, but they are not required for onboarding and do not outrank current repository-owned artifacts, Git history, pull requests, or CI.

## Resolve current state

Inspect only the evidence needed to determine the actual lifecycle position:

- root briefing/readme;
- authoritative product/work-item docs;
- `docs/project-forge-docs.json` and structured documentation;
- `PROJECT_BOOTSTRAP.json`, `PROJECT_FORGE_BASELINE.json`, and component baselines;
- branch/status/diff;
- pull request and CI state;
- deployment/readiness evidence when relevant.

Conversation state may hold the immediate next action, but durable Project state belongs in the repository.

## Engineering lifecycle

```text
/start-work <ID>
→ requirements/context
→ substantive plan approval when warranted
→ implementation authorization
→ safe short-lived branch setup
→ implementation + tests
→ Reviewer
→ human meaningful-diff acceptance
→ optional learning
→ /deliver
→ PR + PR CI
→ one merge/finalize gate
→ post-merge default-branch CI
→ safe delivered-branch cleanup
→ DELIVERY COMPLETE
```

If evidence materially changes after acceptance, reopen the relevant review gate.

## Reusable Project Forge drift

A temporary edit to Project Forge-managed files may be used to diagnose or prove an upstream platform defect, but it is not normal consumer-owned implementation.

If managed drift is unexplained, stop before delivery writes and resolve ownership. If the drift is an explained temporary upstream proof, use `/upstream-fix`, preserve `.project-forge/UPSTREAM_FIX_HANDOFF.md`, and offer one explicit `Continue consumer work with acknowledged Project Forge drift` override when product work can continue without committing the managed workaround.

After that override is accepted, do not repeatedly block the consumer workflow solely because the same documented workaround remains. Keep the workaround and handoff unstaged. The override does not authorize committing shared-managed paths, editing baselines, bypassing required CI/policy, or claiming that the canonical upstream fix has been adopted.

Before `/deliver`, warn about acknowledged drift, selectively stage only accepted consumer-owned changes, and disclose when local validation depended on the workaround. If the workaround is staged, diverges from the handoff, or ownership becomes ambiguous, stop and re-evaluate.

## Learning and documentation

Learning is optional/non-blocking. Relevant entrypoints include `/db-lab`, `/system-lab`, `/code-walkthrough`, `/learning-review`, and `/docs`.

Generated evidence may be refreshed from current safe evidence, but it must not silently replace project-authored authority or invent/approve architectural decisions.
