# Remote Existing-Repository Adoption — Iterative Testing Addendum

## Status

**Companion proposal for system review.**

This addendum defines the testing/reset boundary for the remote existing-repository adoption design. It exists because adoption will need repeated real-repository trials while the protocol is refined, and those trials must be fast to repeat without risking the consumer default branch.

## Goal

A Builder must be able to run an adoption trial, inspect the generated Project Forge changes, reject or refine the design, reset the trial, and start again from the exact same repository state with minimal manual Git work.

The normal trial path must preserve an immutable pre-adoption baseline and keep the consumer default branch untouched until the Builder intentionally accepts a real adoption.

## Trial branch model

For iterative testing, use three identities:

```text
consumer default branch
        |
        | exact source commit selected for the trial
        v
project-forge/adoption-test-baseline   (immutable trial baseline)
        |
        +--> project-forge/adoption-test   (disposable/resettable integration branch)
                    |
                    +--> per-run adoption working branch / PR as needed
```

The baseline branch is a named convenience reference to the exact pre-adoption commit. The commit SHA remains the ultimate authority.

The disposable integration branch is the only branch that may be reset as part of normal trial cleanup. The consumer default branch and baseline branch must not be rewritten by the trial reset operation.

## Baseline capture

Before the first mutating adoption trial, record at least:

- repository identity;
- default branch name;
- exact baseline commit SHA;
- baseline branch name;
- disposable trial branch name;
- upstream/fork relationship when applicable; and
- timestamp or trial identifier for human readability.

The baseline must be captured before Project Forge-managed files or adoption-generated Project documentation are introduced.

If the selected baseline source commit changes, that is a new test baseline rather than a silent update to the old one.

## Fast reset

Project Forge should eventually expose one explicit test-only reset operation. Conceptually:

```text
/reset-adoption-test
```

The operation should:

1. verify the exact repository identity;
2. verify the recorded baseline commit still exists;
3. verify the configured disposable branch is not the repository default branch;
4. verify the configured disposable branch is not the baseline branch;
5. inspect and surface open trial PRs or other state that would be invalidated;
6. close/abandon trial-only delivery state when explicitly within scope;
7. restore the disposable branch to the exact baseline commit, preferably by delete/recreate or another bounded deterministic ref operation;
8. remove only trial-owned temporary state when the implementation contract defines it; and
9. report the restored commit and readiness for another run.

A reset must never guess a baseline from ancestry, `HEAD~N`, dates, or remembered conversation state.

## History-rewrite exception

Normal Project Forge workflows prohibit force-push/history rewriting by default.

A narrowly scoped exception may be designed for the dedicated disposable adoption-test branch because resetting that branch is its explicit purpose. If implemented, the reset must use exact repository/ref verification and lease/current-head checks and must never apply to:

- the consumer default branch;
- the baseline branch;
- arbitrary feature branches;
- upstream/source repositories; or
- branches not explicitly marked as disposable adoption-test state.

Delete-and-recreate is preferred when it produces equivalent safety and simpler reasoning.

## Real adoption boundary

A successful trial does not itself adopt Project Forge into the consumer default branch.

When the Builder decides to adopt for real, Project Forge must create a fresh real-adoption proposal against the then-current approved default-branch commit, re-run the required stale-evidence/collision checks, and use the normal adoption human gates.

Trial evidence may inform that decision but must not bypass current-state verification.

## Fork-specific behavior

For a downstream tracking fork, the trial baseline belongs to the Builder-owned fork only. Project Forge must never create/reset baseline or trial refs in the upstream/source repository.

If the Builder intentionally refreshes the fork from upstream between test cycles, that produces a new candidate baseline commit. The previous baseline remains historical evidence; it is not silently retargeted.

## Proposed system requirements

### PF-SYS-120 — Adoption trial baseline

Before mutating iterative adoption testing, Project Forge MUST preserve an exact pre-adoption baseline commit and MUST provide a named, reviewable way to identify that baseline independently of conversation memory.

### PF-SYS-121 — Disposable adoption trial state

Iterative adoption testing SHOULD run on explicitly disposable target state rather than repeatedly mutating the consumer default branch.

### PF-SYS-122 — Bounded adoption-test reset

A Project Forge adoption-test reset MUST be restricted to explicitly identified disposable trial state and MUST NOT rewrite the consumer default branch, baseline reference, unrelated branches, or upstream repository.

### PF-SYS-123 — Trial is not adoption acceptance

Trial success MUST NOT imply approval to mutate or merge into the consumer default branch. Real adoption MUST revalidate against the current approved default-branch state and retain the normal human gates.

## Initial acceptance scenario

For a mature fork such as the intended Actual Budget trial:

1. capture the current fork default-branch commit as the exact baseline;
2. create an immutable convenience baseline branch at that commit;
3. create a disposable adoption-test branch from the same commit;
4. run adoption against disposable state;
5. inspect generated docs, AI reconciliation, operations profile, branch/PR behavior, and validation;
6. reset the disposable branch to the baseline;
7. repeat until the design is satisfactory; and
8. only then create a fresh real-adoption proposal against the current fork default branch.

This makes repeated refinement cheap while keeping rejection genuinely easy.
