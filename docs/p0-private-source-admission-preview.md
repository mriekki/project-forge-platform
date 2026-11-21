# P0 private-source admission preview (default OFF)

**Status:** Safe implementation preview only. No change to the existing `.github/workflows/npm-publish.yml`, npm trusted publisher identity, package, signed provenance, stable ChatGPT descriptor, public release receipts or consumer deployment.

The `.github/workflows/p0-monorepo-source-preview.yml` workflow supports manual `workflow_dispatch` and the validated owner-authored Issue request (opened event). Its job is **disabled by default** unless the repository variable `PF_MONOREPO_SOURCE_PREVIEW_ENABLED` is explicitly set to the string `true`. Ordinary PRs and pushes cannot trigger it; an owner-Issue request is separately validated. Without that variable, a manual dispatch or Issue request records a skipped job, **not** accepted evidence.

## Protected configuration (not configured by this change)

The public Platform repository's authorized administrator must separately review, grant and configure:

- `PF_MONOREPO_SOURCE_REPOSITORY` (repository secret): exact private `owner/repo` identifier. **Never put its value in source code, a public issue, CI logs or an npm artifact.**
- `PF_MONOREPO_SOURCE_REPOSITORY_ID` (repository secret): immutable numeric GitHub repository ID from trusted owner verification, protecting against rename/recreation.
- `PF_MONOREPO_SOURCE_READ_TOKEN` (new preview-only protected secret): must have **Contents: read** and **Actions: read** on that exact private repository. Keep the legacy `PROJECT_FORGE_SOURCE_TOKEN` **untouched**: it remains necessary for the existing multi-repository publisher and its permissions are not part of this preview. Create a dedicated fine-grained token or a GitHub App installation credential with only `Contents: read` and `Actions: read` on the new private source repository. Do not assume ChatGPT's GitHub connection grants permission to the public Actions workflow.
- `PF_MONOREPO_SOURCE_PREVIEW_ENABLED` (repository variable): leave unset or `false` until explicit access review and a verified private source qualification run.

The historical parity preview needs two inputs: the **exact 40-character private merged `main` commit SHA** and its **completed successful full release qualification run ID** from `.github/workflows/p0-main-release-qualification.yml`. A green PR run or identity-only `p0-main-source-preflight.yml` run does **not** qualify.

## What the workflow validates

1. Authenticated GitHub REST reads the protected exact source repository, latest `main` ref and the selected full qualification run. All three are compared against the protected repository name and ID, requested SHA, supported event, complete successful conclusion, exact source workflow path, branch and run identity. For owner-Issue qualifications, independently obtain the exact attempt's jobs and reviewed code identities from GitHub REST; require the repository owner's immutable actor and rerun actor ID, pinned qualification workflow and identity-verifier Git blobs, and a complete successful qualification job with every required step executed. This compatibility change is limited to read-only preview admission. Manual qualification retains the existing contract.
2. Checks out only that exact accepted private commit with `persist-credentials: false`. The source credential is not exposed to package build steps or stored in the checkout.
3. Rebuilds the **previously published 4.35.0 historical candidate only** using the native source assembler; checks generated assets, candidate handoff and independent public Platform `release/receipts/4.35.0.json` hash and component identities.
4. Rechecks authenticated private `main` at the end to reject source drift.
5. Emits a preview-only result. There is **no** npm publish, tag, release, credential mutation, extra signing root, new public contract or Production deployment.

The verification library (`scripts/private-source-admission-preview.mjs`) rejects spoofed repository IDs, moving main refs, failures or incomplete source CI, PR/identity-only workflow evidence, altered revisions and unpublished versions. The live GitHub REST transport itself is authenticated in the manual workflow; local JSON fixture tests cannot establish that trust independently.

## What remains before any new npm version

The current private `tools/npm/build_candidate.py` and public proof are **intentionally locked to 4.35.0** as a compatibility fixture. A later, separately reviewed new-version native assembler must preserve and migrate the public per-component revision semantics, qualify the new package and recovery behavior, and integrate accepted release inputs into the existing public OIDC publisher. The publisher must independently confirm a fresh exact-source full-release qualification and keep the original public signed provenance and durable receipt rules. Explicit separate approval is needed for any source-ownership cutover, secret grant, npm publication or Production deployment.

This preview adds **no automatic GitHub Actions runs** beyond existing PR tests; when explicitly activated it runs one bounded Linux job with no artifact uploads or paid private-repo attestations.

Tracked with [private source issue #32](https://github.com/mriekki/project-forge-source/issues/32), [public Platform issue #357](https://github.com/mriekki/project-forge-platform/issues/357), and [read-only existing-receipt verifier](p0-candidate-handoff-verification.md).

## Owner-Issue qualification compatibility (preview only)

The independent verifier accepts an authenticated issue-triggered full qualification only when the immutable repository owner started (and if rerun, reran) it, exact source main/run identity matches, the source qualification workflow and entry identity verifier match reviewed Git blob pins at the selected commit, and the attempt-specific sole full qualification job and all mandatory steps completed successfully in order. Missing, skipped, failed, duplicated, changed, or wrong-attempt evidence refuses. Authentication is performed by the existing protected REST transport; tests are synthetic and do not themselves authenticate a run. The Git blob pins are reviewed code identities, not credentials or publication authority. An intentional change to the source qualification contract requires a new review; do not automatically accept a different blob. No new credential, package, publisher or receipt format is introduced. Source main must be rechecked after preview as before. A live preview against a fresh exact main run remains necessary after review.
