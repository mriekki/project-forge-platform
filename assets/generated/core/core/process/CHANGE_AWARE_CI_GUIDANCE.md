# Change-aware CI for Project Forge Projects (optional)

Reference implementation: FMP Project-owned change-aware CI workflow. Implementation work items and repository links remain in their owning repositories.

## Purpose
A Project can keep its existing always-running required CI workflow/job while skipping expensive application, browser, Docker and recovery steps when **the exact code change** is confined to reviewed package-managed Project Forge skills/docs plus baseline metadata. This is optional, Project-owned CI policy, **not** a platform promise that package upgrades are automatically safe.

## Classification invariant
- Require an exact authenticated Git SHA and reliably known base. On pull_request use the verified synthetic merge commit and exact event base/head parents; on push/main require the exact event before SHA and one parent (or conservatively run FULL). Manual dispatch: FULL.
- Parse the complete changed-file set, including additions/deletions/renames. Allow LIGHT only for a narrow known safe list of **package-managed** documentation/skill paths and package/baseline metadata; check every non-metadata path against the installed Core managedPaths manifest. Reject unfamiliar, missing, deleted, non-managed or CI/tooling paths with FULL.
- A managed code asset under tools/, scripts/, runtime or deployment is not automatically safe merely because it came from Project Forge. If baseline validators or classifier itself change, use FULL.
- Always execute the existing required check and package baseline hash verifier, source/provenance validators, exact published npm registry integrity and package check, even on LIGHT. No GitHub Actions workflow-level paths exclusion for required checks.
- Prefer keeping one stable required job name and step-level conditions. Every failed, ambiguous, or missing classifier result selects FULL and never counts as permission to skip a required security or Production gate.
- Record scope and exclusions in the job summary; LIGHT success means package integrity, **not** application readiness, runtime verification, release permission or Production deployment.
- Do not let this optimization bypass required GitHub security policy, branch gates or independent post-merge proof. Evaluate the actual required-check topology before generalizing it.
- Validate unit fixtures for PR synthetic merge, push/main squash, manual dispatch, mixed code changes, deleted/unmanaged assets, malformed Git output and CI config changes.
- Verify actual LIGHT PR + main outcomes on a later package-only update and FULL both ways for application changes; compare billed Actions minutes and runner durations against a measured baseline.

FMP's reference classifier is in tools/ci/classify_scope.py and scoped CI YAML in .github/workflows/ci.yml. Reuse the *principles*, not arbitrary copies of FMP's allowlist or Docker assumptions. Builder's Projects own their test scope. Do not enable this for all generated Projects until qualified in a real consumer.
