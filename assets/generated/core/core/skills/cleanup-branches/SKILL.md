---
name: cleanup-branches
description: Preview-first cleanup of completed short-lived Git branches locally and on the configured remote, using merged-PR evidence and explicit destructive authorization.
argument-hint: "[optional branch name/prefix]"
user-invocable: true
disable-model-invocation: true
---

# Cleanup Branches

`/cleanup-branches` removes completed short-lived branches without treating branch-name patterns or Git ancestry alone as proof that deletion is safe.

Existing repository conventions outrank Project Forge defaults. Preserve configured default/protected branches, release/integration branches, and any branch the repository intentionally keeps long-lived.

Invocation begins read-only.

## 1. Purpose

Use this skill for branch housekeeping outside the normal `/deliver` path, especially when historical feature/fix/chore branches have accumulated.

Normal delivery should clean its own short-lived branch after merge and successful required post-merge default-branch CI. This skill is for backlog cleanup, interrupted delivery, or explicit inspection.

## 2. Read-only discovery

Inspect current repository state and resolve the actual default branch and remotes. Typical evidence includes:

```text
git status --short --branch
git branch --show-current
git branch -vv
git branch -r
git remote -v
git fetch --all --prune --dry-run
```

When GitHub CLI is available, inspect repository/PR evidence rather than inferring from names alone:

```text
gh repo view
gh pr list --state merged
gh pr list --state open
```

For each candidate branch, record when observable:
- local head SHA,
- remote head SHA,
- merged PR number/state,
- PR head ref and head SHA,
- whether an open PR still references the branch,
- whether the branch is default/protected/long-lived by repository policy,
- whether local commits exist beyond the remote/merged PR head.

Do not modify anything during discovery.

## 3. Classification

Classify every observed non-default branch into one of these buckets.

### SAFE TO DELETE

A branch may be classified safe only when evidence shows it is completed and unchanged since completion. Strong evidence is:
- a merged PR exists for that exact head branch,
- the observed branch head still matches the PR head SHA (or the branch is already absent remotely),
- no open PR references the branch,
- no local-only commits were added after the approved/merged head,
- it is not the default, protected, release, integration, environment, or intentionally long-lived branch.

A branch fully merged by ancestry may also be safe when repository policy and commit history make that unambiguous.

### REVIEW REQUIRED

Use this when any material evidence is missing or ambiguous, including:
- no merged PR and ancestry is not conclusive,
- remote/local heads differ,
- branch moved after its PR merged,
- local-only commits exist,
- an open PR references it,
- branch purpose/lifecycle is unclear.

### PRESERVE

Always preserve by default:
- the configured default branch,
- protected branches,
- active/open-PR branches,
- release/integration/environment branches unless repository policy explicitly says otherwise,
- any branch the human marks to keep.

Never classify by prefix alone.

## 4. Preview

Present a concrete preview before deletion:

```text
BRANCH CLEANUP PREVIEW

Default branch: <name>
Working tree: <clean / details>

SAFE TO DELETE
  <branch>  local=<sha|absent>  remote=<sha|absent>  evidence=<merged PR / ancestry>

REVIEW REQUIRED
  <branch>  <reason>

PRESERVE
  <branch>  <reason>

NO CHANGES HAVE BEEN MADE
```

If no branch is safely deletable, stop after the preview.

## 5. Cleanup gate

For a non-empty verified-safe set, present one bounded destructive gate using the host-native **single-select structured choice UI** when available; in VS Code use the native question surface such as `vscode_askQuestions`. Offer:

- `Delete verified-safe local + remote branches` `[GIT + GITHUB WRITE]` — `RECOMMENDED`
- `Delete verified-safe remote branches only` `[GITHUB WRITE]`
- `Delete verified-safe local branches only` `[GIT WRITE]`
- `Stop` `[NO ACTION]`

Use a numbered text menu only when structured choice UI is unavailable. Only the selected choice authorizes the corresponding deletions. Do not include REVIEW REQUIRED branches in the bounded action.

## 6. Revalidate before deletion

Immediately before any deletion:
- fetch/prune remote state,
- re-resolve the default branch,
- confirm every candidate branch head still matches the previewed SHA/evidence,
- confirm no new/open PR now references it,
- confirm the working tree is safe to switch branches,
- confirm the current branch is not about to be deleted.

If anything materially changed, stop and return to preview. Do not silently widen the approved set.

## 7. Apply cleanup

Switch to the default branch before deleting the current feature branch and update it with the repository-approved non-rewriting method, normally `git pull --ff-only`.

For each approved remote branch, use the repository's normal remote-deletion mechanism, for example:

```text
git push origin --delete <branch>
```

If the remote branch is already absent, treat that as already-clean rather than an error.

For each approved local branch:
- prefer `git branch -d <branch>` when Git recognizes it as merged,
- squash/rebase merges may cause `-d` to reject even though the PR is merged,
- only when merged-PR evidence is exact and the local head has no commits beyond the approved PR head may `git branch -D <branch>` be used under the explicit cleanup authorization.

Never use `-D` merely to bypass uncertainty.

After deletion:

```text
git fetch origin --prune
```

## 8. Completion report

Report exactly what happened:

```text
BRANCH CLEANUP COMPLETE

Deleted remote:
  ...
Deleted local:
  ...
Already absent:
  ...
Preserved / review required:
  ...
Default branch: <name>
Working tree: <state>
```

Do not claim a branch was deleted unless the resulting local/remote state was observed.

## 9. Relationship to /deliver

`/deliver` owns branch finalization for the work it is actively delivering. `/cleanup-branches` is the standalone maintenance path for accumulated or previously retained branches.
