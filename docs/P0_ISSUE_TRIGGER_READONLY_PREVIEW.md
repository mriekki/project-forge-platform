# Owner-created GitHub Issue trigger for read-only source qualification previews

The existing [P0 Private Source Admission Preview](https://github.com/mriekki/project-forge-platform/actions/workflows/p0-monorepo-source-preview.yml) now supports **two equivalent request surfaces**, with identical private GitHub REST, PAT, exact-main CI, archive verification and post-run main checks:

- Normal GitHub Actions manual `workflow_dispatch`.
- An **owner-created GitHub Issue**, allowing ChatGPT's existing GitHub connector (which can create Issues but cannot initiate a new `workflow_dispatch`) to start the same *nonpublishing* workflow.

There is no new token, credential scope, workflow job, repository secret, Actions dispatcher PAT, or independent release workflow. The existing `PF_MONOREPO_SOURCE_PREVIEW_ENABLED=true` gate and the current least-privilege private-source PAT remain required. The public npm OIDC publisher is unchanged.

## Exactly accepted Issue request

**Repository:** `mriekki/project-forge-platform`

**Title:** `[project-forge-source-preview]`

**Body:** strict JSON containing **only** these three fields:

```json
{
  "sourceSha": "0000000000000000000000000000000000000000",
  "sourceRunId": 12345,
  "candidateMode": "changed-feedback-4.36-preview"
}
```

Use the real exact qualified private source `main` SHA and that commit's successful manual or owner-issue-triggered full qualification Actions run ID. Supported modes are `historical-4.35` and `changed-feedback-4.36-preview`. Never put a PAT, secret, internal repository URL, or other confidential material into a public Issue.

The workflow starts only for an `opened` Issue with the **exact title**, authored and sent by the repository owner. Requests from others are skipped before acquiring a runner. The separate resolver checks the issue's owner, action, state, exact JSON keys, 40-character SHA, positive safe run ID, and allowlisted nonpublishing mode. It converts the request into the same workflow outputs as manual dispatch; no untrusted issue-body string is evaluated as shell code. Authenticated private-main and successful exact SHA/run checks remain required and are rechecked after the historical/new-source preview.

The public repository is used because the current public Platform workflow and token are already the approved owners. We do not introduce a public/private source repository mapping into issue bodies.

## ChatGPT workflow

ChatGPT can create the exact Issue, read the resulting Actions run, inspect logs, and close the request after success. Failure leaves an auditable Issue/run for diagnosis. It may rerun a failed job only when safe and already within the approved scope; changed input or source SHA requires a new Issue. Creating an Issue is **not** a substitute for the separate human approval of npm publication, source ownership migration, or Production deployment.

## Cost and operational boundaries

GitHub may register a skipped workflow run for unrelated new issues, but only the exact owner-authored preview title launches a runner. This reuses the existing 15-minute job, no additional matrix. Do not create redundant preview requests for the same exact evidence.

Tracking: [source issue #39](https://github.com/mriekki/project-forge-source/issues/39), [public migration #357](https://github.com/mriekki/project-forge-platform/issues/357).
