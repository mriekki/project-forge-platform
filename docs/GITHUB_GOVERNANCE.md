# Project Forge Platform GitHub Governance

This document records the intended GitHub administration policy for the public Project Forge Platform trust roots. Repository files can define and test the workflow side of these controls; repository rulesets and protected settings remain GitHub Settings configuration and must be verified from live repository evidence.

## `main` protection

Configure one active repository ruleset targeting `main` with these minimum rules:

- block branch deletion;
- block non-fast-forward updates / force pushes;
- require changes to land through a pull request;
- require the stable `CI / required` check before merge;
- preserve explicit bounded release authorization for consequential release work;
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

## npm publication authorization

`Publish npm Package` is intentionally not protected by a second GitHub Environment reviewer. The meaningful human publication decision occurs before the cloud agent creates the exact publication request. Requiring another GitHub approval after that bounded authorization would duplicate the same decision without adding release evidence.

The preferred cloud publication path is an owner-authored issue titled exactly:

```text
[project-forge-publish] <version>
```

with a body containing only:

```json
{
  "version": "<exact-version>",
  "sourceCommit": "<exact-current-platform-main-sha>"
}
```

`.github/workflows/npm-publish.yml` ignores issue-triggered requests not authored by the repository owner and fails closed unless the request schema/title are exact, the authorized source is still current `main`, the package version matches, exact post-merge Platform CI is green, the target npm version is unused, protected component sources resolve, reproducible release preparation passes, and registry/provenance verification succeeds.

`workflow_dispatch` remains an administrative fallback using the same exact `version` and `source_commit` authorization tuple. Neither trigger authorizes unrelated merges, Project generation, consumer updates, release/tag publication elsewhere, or Production application deployment.

A single explicit end-to-end release authorization may cover the package-release merge, exact npm publication, and stable-alignment merge when those actions stay within the previously reviewed release scope and every fail-closed check remains green. If the release diff, source commit, version class, component revision, or verification evidence materially changes, the automation must stop for renewed review rather than stretching the original authorization.

The publication workflow records machine-readable verified publication evidence, including the exact Platform source, component pins, release-candidate SHA-256, registry shasum, publication timestamp, workflow run, signed-provenance transparency-log URL, and exact Platform CI run. For issue-triggered publication, that evidence is also persisted as a comment on the owner-authored request before the issue is closed.

## Acceptance evidence for issue #80

Retain the historical hardening evidence that:

1. the `main` ruleset is active and targets `main`;
2. force pushes and branch deletion are blocked;
3. pull requests are required and `CI / required` is enforced;
4. a normal direct human push to `main` is refused while an authorized PR merge succeeds;
5. npm Trusted Publishing is limited to `mriekki/project-forge-platform/.github/workflows/npm-publish.yml`;
6. publication is bounded to an exact version/source tuple and independently verifies current `main` plus post-merge CI;
7. no npm package is published merely to prove a governance control.
