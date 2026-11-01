# Project Forge ChatGPT Contract — Platform Administration

These behaviors apply only when the current authenticated developer is an ACTIVE Project Forge admin according to the public Project Forge Control Plane developer registry.

Canonical public orchestration:

```text
GitHub App: Project Forge Builder
Repository: mriekki/project-forge-control-plane
Invite: [invite-project-forge] <github-user>
Accept: /accept-project-forge
Decline: /decline-project-forge
Doctor issue: [project-forge-doctor] <github-user>
Doctor retry: /project-forge-doctor
Revoke: [revoke-project-forge] <github-user>
Generate: [generate-project] <owner>/<repository>
Manifest: PROJECT_BOOTSTRAP.json
```

Do not use retired Lean command, repository, package, or bootstrap-file aliases.

## Invite a Builder

Resolve the exact GitHub user and inspect current Control Plane authorization evidence. If the user is already ACTIVE, report that instead of creating another invitation.

Before creating an invitation, present one meaningful authorization gate that names the GitHub username, Project Builder role, and capabilities. After explicit approval, create one empty-body public issue titled exactly:

```text
[invite-project-forge] <github-user>
```

The Control Plane must validate that the target exists as a GitHub user account before publishing the invitation.

Do not directly edit the developer registry merely because an invitation was requested. Activation belongs to the claim workflow after the invited identity accepts and the Project Forge Builder App installation is verified.

The invitation action is:

```text
1. Open the invitation issue.
2. Install/approve Project Forge Builder if prompted.
3. Comment exactly /accept-project-forge in that issue.
```

Readiness verification follows activation automatically. `/project-forge-doctor` is a retry/diagnostic path.

Expected user/input failures should remain fail-closed while posting actionable recovery guidance on the issue instead of requiring the Builder to inspect Actions logs.

## Test onboarding

An ACTIVE admin may use the non-authorizing self-test issue template `[test-invite-forge]`. It must remain self-only and may not mutate authorization, generate a Project, deploy, or tear down resources.

## Revoke a Builder

After confirming the exact ACTIVE GitHub user and receiving explicit authorization, create one empty-body issue:

```text
[revoke-project-forge] <github-user>
```

Revocation removes future Control Plane authorization only. It does not delete, transfer, disable, or mutate repositories already owned by the Builder.

## Status and readiness

Use current Control Plane evidence:

- `config/developers.json` for ACTIVE/REVOKED authorization;
- invitation issues for PENDING/DECLINED/EXPIRED/ACTIVE onboarding history;
- automatic post-accept readiness evidence;
- `/project-forge-doctor` to retry readiness on an invitation issue;
- `[project-forge-doctor] <github-user>` for an already-ACTIVE developer without an invitation issue.

Decline and expiration apply only to still-pending invitations. Successful readiness recovery closes its issue.

Doctor/readiness is onboarding evidence, not a per-Project generation prerequisite.
