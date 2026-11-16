---
name: pull-latest
description: Guided fast-forward-only Git update so a developer can safely get the latest remote branch state without remembering Git syntax.
argument-hint: "[optional branch name]"
user-invocable: true
disable-model-invocation: true
---

# Pull Latest

`/pull-latest` is a small convenience wrapper for routine Git updates. It removes the need to remember `fetch`, `switch`, `pull --ff-only`, or upstream-status syntax while preserving normal repository safety.

Existing repository conventions outrank Project Forge defaults.

Invocation starts read-only.

## 1. Inspect current state

Inspect:

```text
git status --short --branch
git branch --show-current
git remote -v
git branch -vv
```

Resolve:
- current branch,
- configured upstream for the current branch,
- configured default branch when observable,
- requested branch when one was supplied,
- whether the working tree is clean enough to switch/update safely.

Do not fetch, switch branches, pull, stash, merge, rebase, reset, clean, or delete anything during this first inspection.

## 2. Safety stop conditions

Stop before update when:
- tracked/staged/untracked work could be overwritten or makes branch switching unsafe,
- a merge/rebase/cherry-pick is in progress,
- the requested branch or remote is ambiguous,
- no usable upstream exists for the branch being updated,
- authentication/remote access fails,
- repository policy requires a different update method.

Never auto-stash user work.
Never use `reset --hard`, force-push, merge, or rebase as part of `/pull-latest`.

## 3. Choose the update target

When the user must choose an update action, use the host-native **single-select structured choice UI** when available; in VS Code use the native question surface such as `vscode_askQuestions`. Use a numbered text menu only when structured choice UI is unavailable.

If the human supplied a branch, use that branch as the requested target when it can be resolved safely.

If no branch was supplied and the current branch is the default branch, show:

```text
PULL LATEST READY

Current branch: <branch>
Working tree: CLEAN
```

Then offer:

- `Refresh remote state and pull latest <branch>` `[GIT WRITE]` — `RECOMMENDED`
- `Stop` `[NO ACTION]`

If no branch was supplied and the current branch is a non-default branch, show:

```text
PULL LATEST READY

Current branch: <branch>
Default branch: <default>
Working tree: CLEAN
```

Then offer:

- `Refresh and pull the current branch` `[GIT WRITE]`
- `Switch to the default branch and pull latest` `[GIT WRITE]` — `RECOMMENDED` when returning to baseline
- `Stop` `[NO ACTION]`

Only the selected choice authorizes fetch/switch/pull mechanics for the selected branch.

## 4. Refresh remote state

For the selected remote/branch, run the repository-normal equivalent of:

```text
git fetch <remote> --prune
```

Then re-evaluate local branch, upstream, and remote head before pulling.

Classify the branch as:
- `CURRENT` — local and upstream point to the same commit,
- `BEHIND` — local can be fast-forwarded to upstream,
- `AHEAD` — local has commits not on upstream,
- `DIVERGED` — both local and upstream contain unique commits,
- `UNKNOWN` — state cannot be established safely.

## 5. Apply only a fast-forward-safe update

### CURRENT

Do not create a no-op commit or other change. Report that the branch is already current.

### BEHIND

Use the repository-normal equivalent of:

```text
git pull --ff-only
```

If the user selected the default branch while currently on another branch, first switch to the existing local default branch only after confirming the working tree is safe, then perform the same fast-forward-only update.

### AHEAD

Do not pull, merge, rebase, reset, or push. Report `LOCAL AHEAD` and the observed commit counts when available.

### DIVERGED

Stop. Report `DIVERGED` and recommend explicit inspection. `/pull-latest` must not choose merge, rebase, reset, or force-push on the user's behalf.

### UNKNOWN

Stop and report the missing/ambiguous evidence.

## 6. Verification

After a successful update, inspect:

```text
git status --short --branch
git log -1 --oneline
```

When useful, also confirm the local branch head matches its upstream.

## 7. Completion report

Use:

```text
PULL LATEST COMPLETE

Branch: <branch>
Remote/upstream: <remote>/<branch>
Result: UPDATED | ALREADY CURRENT | LOCAL AHEAD | DIVERGED | BLOCKED
Head: <sha>
Working tree: <state>
```

Do not claim an update succeeded unless the resulting branch/upstream state was observed.

## 8. Boundaries

`/pull-latest` never:
- modifies application/source files directly,
- stashes work automatically,
- creates or deletes branches,
- commits or pushes,
- merges or rebases,
- resets or cleans the worktree,
- resolves conflicts automatically,
- changes remotes/upstreams unless a separate explicit action authorizes that configuration change.

It is intentionally just the safe convenience path for `refresh remote state → fast-forward if possible → verify`.
