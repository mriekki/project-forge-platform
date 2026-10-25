# Project Forge ChatGPT Contract — Onboarding

Project Forge onboarding separates identity/authorization from operating rules and Project state.

Canonical public surfaces:

```text
GitHub App: Project Forge Builder
Control Plane: mriekki/project-forge-control-plane
Public contract: https://raw.githubusercontent.com/mriekki/project-forge-platform/main/chatgpt/current.json
```

## Invitation

A Project Forge Control Plane invitation issue is the onboarding portal. It grants no access merely by being opened or forwarded.

Control Plane invitation issues are public. Do not paste source code, Project requirements, credentials, tokens, private keys, or other private information into them.

Happy path:

```text
PENDING
→ open invitation issue
→ install/approve Project Forge Builder
→ invited GitHub user comments /accept-project-forge
→ identity + App installation verified
→ ACTIVE
→ public Project Forge contract verified automatically
→ READY FOR PROJECT FORGE
→ configure ChatGPT Project once
```

The Control Plane validates that the invited target exists as a GitHub user account before publishing a real invitation.

The invited user may comment `/decline-project-forge` while the invitation is still pending. Unclaimed pending invitations expire under the public invitation policy. An ACTIVE Builder cannot later decline or expire the completed invitation; revocation is the separate administrator path.

Expected user/input failures remain fail-closed and should post actionable recovery guidance on the onboarding issue.

## Automatic readiness and doctor retry

Successful `/accept-project-forge` activation performs normal readiness verification automatically. The check verifies ACTIVE authorization, Project Forge Builder availability, and the public `project-forge-platform/chatgpt/current.json` descriptor plus its complete SHA-256-pinned immutable document set.

If readiness later needs retrying, use:

```text
/project-forge-doctor
```

For an already-ACTIVE developer without an invitation issue, open:

```text
[project-forge-doctor] <github-user>
```

A successful readiness retry closes its recovery issue.

Doctor/readiness is onboarding evidence, not a mandatory prerequisite for every `New Project:` or `New Project from:` request. Generation separately revalidates exact target access.

## Admin self-test

An ACTIVE admin may rehearse onboarding with `[test-invite-forge]`. Test mode is self-only and non-authorizing: no registry mutation, role/capability change, Project generation, deployment, or tear-down.

## ChatGPT setup

Once READY FOR PROJECT FORGE, configure one normal ChatGPT coding Project.

Every Builder uses the same canonical Project Forge Project instruction: the fenced instruction text in `PROJECT_INSTRUCTIONS.md` under the immutable snapshot named by `chatgpt/current.json`. Do not create per-person forks of that canonical instruction.

In the same ChatGPT Project instructions field, immediately after the canonical instruction, append one clearly delimited personal Developer Profile block conforming to `USER_PROFILE.schema.json`.

The Developer Profile is the only Builder-specific part of the normal Project Forge Project instructions. Only `schemaVersion` and `githubOwner` are required. Optional OS/shell/editor/workspace-root/learning fields should be omitted when unknown rather than guessed.

The profile may contain identity, local environment, and working/learning preferences. It must not contain passwords, tokens, private keys, Production credentials, product requirements, work-item state, commit SHAs, or other durable Project state.

Verify the one-time setup by starting a chat in that Project and saying:

```text
Verify my Project Forge setup.
```

A successful verification resolves the current public descriptor and immutable snapshot, confirms the canonical instruction is present, validates the Developer Profile shape, and confirms that consequential Project Forge work can proceed without relying on remembered platform state.

Do not copy legacy handoff documents, component commit SHAs, product requirements, or current Project state into ChatGPT Project instructions.

After generation, the generated Project repository owns its current product state, work items, architecture, baselines, deployment facts, Git history, pull requests, and CI evidence. Foundational Project Forge capabilities own reusable platform behavior. Legacy handoff files may remain historical/reference material, but they are not an onboarding dependency or current-state authority.

Normal entrypoints:

```text
New Project: <idea>
New Project from: <PROJECT_INPUT.json or existing product source>
```

Both enter the same Bootstrap-owned discovery protocol; the second begins from approved/importable product evidence.

## Generated workspace welcome

Current Bootstrap generation configures the generated `.code-workspace` to use the Project `README.md` as the VS Code startup page when there is no restored editor state. The README is the single human-facing welcome/how-to-get-started front door; supporting Markdown remains available as reference.

## Revocation

Revocation removes future Control Plane authorization. It must not delete, transfer, disable, or mutate repositories the developer already owns.
