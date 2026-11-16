# Project Forge Application Versioning

Every Project Forge application must implement a real runtime version identity. A static label that never changes across builds is not sufficient.

## Contract

Application versioning has two layers:

1. **release version** — a deliberate Semantic Version such as `0.1.0` or `1.0.0`;
2. **build identity** — automatically derived evidence that identifies the exact built artifact.

The normal human-readable form is intentionally simple:

```text
v1.0.0 (build 142)
```

The machine/informational form may carry richer provenance:

```text
1.0.0+build.142.sha.a1b2c3d
```

A build record should expose equivalent fields when available:

```text
releaseVersion: 1.0.0
buildNumber: 142
commit: a1b2c3d
builtAtUtc: 2026-10-21T20:15:00Z
informationalVersion: 1.0.0+build.142.sha.a1b2c3d
displayVersion: v1.0.0 (build 142)
```

## Release version

Use Semantic Versioning (`MAJOR.MINOR.PATCH`) for the application release version.

Recommended default for a new project under active development:

```text
0.1.0
```

Promote deliberately. The first accepted V1 release may become `1.0.0`; later major/minor/patch changes follow the project's release policy.

The release version is expected to remain stable across multiple development builds. It must not be bumped merely to create a unique build identity.

Use one stack-native authoritative source for the release version. Do not maintain unrelated duplicated constants or decorative `VERSION.md` values that can drift from the built application.

## Build identity

A releasable CI-built artifact must receive an automatically derived build identity.

Preferred evidence:

- monotonically increasing CI/build sequence number;
- exact source commit, with a short commit acceptable for display and the full commit retained in machine evidence when practical;
- UTC build timestamp as supplemental evidence.

The canonical informational form is conceptually:

```text
<releaseVersion>+build.<buildNumber>.sha.<shortCommit>
```

A timestamp may be appended as metadata, but a date alone should not replace a sequencing value when the build system can provide a monotonic run/build number.

For local developer builds where no CI build number exists, use an explicitly non-release identity such as:

```text
0.1.0+local.20261021T201500Z.sha.a1b2c3d
```

Do not invent a CI/release build number for a local build.

## Runtime exposure

The running application must make its effective version identity observable.

For applications with a user interface, expose a concise human-readable value in an appropriate low-noise surface such as About, Settings, diagnostics, or a footer:

```text
v1.0.0 (build 142)
```

Also provide machine-readable or diagnostic evidence when the stack/application shape supports it, for example:

- a version/info endpoint;
- CLI `--version` output;
- startup diagnostic metadata;
- an application metadata object consumed by the UI.

The display must be derived from the same build identity as the machine evidence rather than maintained as a separate hard-coded string.

## Stack-specific implementation

The contract is stack-independent; the implementation is not.

Examples of appropriate stack-native sources include:

- .NET/Blazor/ASP.NET: project/package version plus assembly/informational version metadata;
- Node/React/Angular: package/project version plus build-time injected CI/commit metadata;
- Java/Spring: Maven/Gradle project version plus generated build metadata/resources.

These examples are implementation guidance, not a fixed technology requirement. Prefer the repository's native build/package mechanism.

## Build and run helpers

`/build` should report the effective release/build identity when the selected build produces or exposes it.

`/run` should report the effective runtime version when the started application exposes it.

Neither helper should invent version information or mutate release version state merely to make version evidence appear.

## Delivery and deployment

A deployable artifact should be traceable to one version identity and one source commit. Deployment evidence may record the version/build identity, but deployment must not silently rewrite it.

A release tag, GitHub release, package version, container tag, or deployment label does not substitute for runtime application version evidence unless the built application actually consumes that same authoritative version metadata.

## Replatforming

Application versioning is a reusable engineering requirement, not a portable product requirement.

`PROJECT_REQUIREMENTS.json` therefore does not need to encode stack-specific version mechanics. A replatformed project must receive the current Project Forge application-versioning contract and implement it using the target stack's native facilities.

## Acceptance

Application foundation is not complete until:

- one authoritative release version source exists;
- a build can derive a unique build identity without manually editing display text;
- the source commit is traceable from build evidence;
- a running application exposes the effective version in an appropriate human-readable form;
- release/CI builds use a real sequencing value when the CI system provides one;
- local builds are clearly distinguishable from release/CI builds.
