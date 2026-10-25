# npm Release Process

`@mriekki/project-forge` is the public npm distribution assembled from exact accepted revisions of private canonical Project Forge component sources.

Release preparation and npm publication are automated, but publication remains an explicit decision for one exact package/version/source tuple. Public package metadata records logical component IDs and opaque exact revisions; private source repository locations remain protected configuration.

## Normal operator workflow

Use the repository-local VS Code skill:

```text
/release-project-forge
```

The normal flow is:

```text
accepted component revisions
→ choose package version
→ deterministic package metadata + descriptor update
→ tests / asset verification
→ release PR + PR CI
→ ONE PACKAGE PR MERGE GATE
→ post-merge main CI
→ ONE EXACT NPM PUBLISH GATE
→ GitHub OIDC direct publish
→ registry + neutral npx verification
→ public ChatGPT contract alignment
```

Publishing the package does not update consumers. Existing package-managed Projects adopt it separately through `/project-forge-update`.

## Release invariants

Before npm publication:

- Project Forge Platform publication source is an exact clean `main` commit;
- `assets/components.json` uses schema v2 and pins exact opaque component revisions;
- local canonical component checkouts are clean exact accepted `origin/main` states when a release PR is prepared locally;
- packaged distribution descriptors exactly match the pinned source descriptors;
- all package tests pass;
- generated assets verify against the assembly ledger;
- two independent `npm pack` runs produce the same SHA-256;
- a clean temporary install can run `project-forge version`, `project-forge install`, and `project-forge check` successfully;
- the npm version does not already exist;
- the exact Platform source commit and package version are revalidated by the publication workflow.

`scripts/prepare-release.mjs` enforces release-candidate checks and writes ignored release artifacts under `dist/release/` and ignored generated package assets under `assets/generated/`.

## Privacy-safe component provenance

`assets/components.json` schema v2 contains only:

- logical component IDs such as `core` and `deployment`;
- exact opaque `revision` values;
- public compatibility/version and distribution metadata;
- packaged descriptor/source-root paths.

It must not publish private source repository identities. New consumer baselines use schema v2 with the same logical-ID + opaque-revision model. Package runtime remains backward-compatible with schema v1 baselines so an existing Project can upgrade in place; the next successful apply rewrites its package provenance as schema v2 without changing clean managed files solely for the migration.

## Deterministic package-update preparation

The release skill runs `scripts/prepare-package-update.mjs` with local Core and Deployment source roots. The script refuses Platform `main`, requires clean exact component `origin/main` checkouts, validates canonical descriptors, and updates only:

- `package.json` version;
- `package-lock.json` version metadata;
- `assets/components.json` package version and exact component revisions/versions;
- packaged component distribution descriptors copied from those exact source checkouts.

Private source repository names are not encoded in package metadata or required as public command arguments. After preparation, run package tests, asset assembly/verification, `git diff --check`, and meaningful diff review before PR delivery.

## Package version policy

For `1.0.0` and later, use conventional semantic versioning:

- patch — backward-compatible corrections;
- minor — backward-compatible consumer-visible features;
- major — breaking consumer contracts.

The baseline provenance v2 migration is backward-compatible because schema v1 remains readable, so it is a minor release.

## Protected source-repository mappings

The publication workflow resolves private source locations only from protected Actions secrets on Project Forge Platform:

```text
CORE_SOURCE_REPOSITORY
DEPLOYMENT_SOURCE_REPOSITORY
```

Values are exact `owner/repository` mappings. Do not print them, commit them, or place them in public package metadata. The workflow validates their shape, masks resolved values in logs, and uses `PROJECT_FORGE_SOURCE_TOKEN` only for read access to the exact private sources needed by the release.

## Trusted Publishing

Normal releases use npm Trusted Publishing (OIDC) from:

```text
GitHub owner: mriekki
Repository: project-forge-platform
Workflow: npm-publish.yml
Allowed action: npm publish
```

Routine releases do not require local npm login. Inspect or change npm trust only during initial setup, migration, repository/workflow identity changes, or a reported trust error.

For one-time trust administration, use npmjs.com or, when needed:

```powershell
npm login --auth-type=web --registry=https://registry.npmjs.org/
npm trust list @mriekki/project-forge --json
```

If npm returns `EOTP`, complete the browser authorization locally. Never paste or store its one-time URL or OTP in chat, repository files, or CI.

## Exact release gates

A green release PR stops at one package merge gate. Merging does not authorize publication.

After the merged exact Platform `main` commit passes post-merge CI and the target npm version is confirmed unused, stop at one exact npm publication gate naming:

- package/version;
- Platform main SHA;
- exact logical component revisions (and Core version where applicable);
- green post-merge CI;
- GitHub OIDC / `npm-publish.yml` publisher.

If approved, trigger:

```powershell
gh workflow run npm-publish.yml --ref main `
  -f version=<version> `
  -f source_commit=<exact-main-sha>
```

The workflow refuses stale or changed evidence.

## Publication workflow behavior

`.github/workflows/npm-publish.yml`:

1. checks out exact Project Forge Platform source;
2. verifies the authorized Platform SHA and package version;
3. refuses an already-published version;
4. resolves exact component revisions from schema-v2 `assets/components.json`;
5. resolves private component source locations from protected source-repository mappings and masks them;
6. checks out each exact component revision with read-only source credentials;
7. runs `scripts/prepare-release.mjs` and verifies the release manifest;
8. publishes the exact tarball with OIDC;
9. verifies registry version/integrity/shasum with bounded retry;
10. runs a neutral-directory `npx` smoke check.

If a pre-publication step fails, npm is not published. If publication succeeds but post-publish verification fails, report the published state accurately and never republish the same version.

## Public ChatGPT contract alignment

After registry verification, compare live `chatgpt/current.json` with the exact published package. Never point stable to an unpublished version. If only the mutable package/revision pointer is stale and the immutable operating contract is unchanged, prepare the smallest follow-up PR; otherwise create a new immutable snapshot as required by the live contract rules.

## What release does not imply

Publishing `@mriekki/project-forge` does not regenerate existing Projects, update consumers, deploy an application, publish component GitHub releases/tags, or perform Production changes. Those remain separately authorized actions.
