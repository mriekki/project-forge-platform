# Project Forge Platform GitHub Governance

This document records the intended GitHub administration policy for the public Project Forge Platform trust roots. Repository files can define and test the workflow side of these controls; repository rulesets and protected-environment reviewers remain GitHub Settings configuration and must be verified from live repository evidence.

## `main` protection

Configure one active repository ruleset targeting `main` with these minimum rules:

- block branch deletion;
- block non-fast-forward updates / force pushes;
- require changes to land through a pull request;
- require the stable `CI / required` check before merge;
- preserve the explicit human merge/finalize decision;
- use no bypass actor by default.

If a bypass later becomes necessary, document the exact actor and reason before enabling it. Do not grant blanket administrator or GitHub Actions bypass merely for convenience.

`Public ChatGPT Contract Alignment` is intentionally not a required pre-merge check while it remains a post-merge / post-publish workflow. If it is ever made required, first add a pull-request check that evaluates the proposed descriptor state rather than `main`.

## Workflow supply-chain and runtime coverage

External actions used by Platform workflows must be pinned to exact immutable commit SHAs. CI enforces this across `.github/workflows` so a floating action tag cannot be introduced silently.

The public package advertises Node `>=20`. Routine Platform CI therefore exercises Node 20, 22, and 24 on both Ubuntu and Windows, with the stable aggregate `required` job remaining the branch-ruleset gate.

## Stable Platform Health

`.github/workflows/stable-platform-health.yml` runs daily and can also be dispatched manually. It is a read-mostly live canary for the stable public surface and must not publish packages, generate Projects, update consumers, or perform application deployment.

The health audit verifies:

- repository tests and local public-contract/package alignment;
- the live canonical `chatgpt/current.json` matches checked-out `main`;
- every live immutable contract document still matches its SHA-256 pin;
- the public invitation policy remains reachable and valid;
- the exact stable npm package/version selected by the descriptor remains visible;
- that exact package executes successfully from a neutral directory.

If the audit fails, the workflow opens or updates one issue titled `[project-forge-health] Stable platform audit failing`. A later successful health run closes the managed incident automatically. The issue is an alert/recovery surface only; it does not authorize package publication, contract advancement, consumer updates, Project generation, or Production changes.

## npm publication environment

The `Publish npm Package` workflow binds its `publish` job to the GitHub Environment:

```text
npm-production
```

Configure that environment with at least one required human reviewer. For the current single-admin setup, the active Platform admin may be the reviewer; do not enable self-review prevention unless another trusted reviewer is configured, or publication would become inoperable.

Keep environment deployment scope limited to the Platform publication workflow. Approval of `npm-production` authorizes only the exact package publication run already bounded by its `version` and `source_commit` inputs. It does not authorize merge, Project generation, consumer updates, release/tag publication elsewhere, or Production application deployment.

Do not publish a package merely to test the environment gate. Validate the workflow reference in CI and verify the required-reviewer configuration in GitHub Settings/API.

## Acceptance evidence for issue #80

Before closing the hardening issue, retain evidence that:

1. the `main` ruleset is active and targets `main`;
2. force pushes and branch deletion are blocked;
3. pull requests are required and `CI / required` is enforced;
4. a normal direct human push to `main` is refused while an approved PR merge succeeds;
5. `npm-production` has a required human reviewer;
6. `.github/workflows/npm-publish.yml` references `npm-production`;
7. no npm package was published solely to prove the control.
