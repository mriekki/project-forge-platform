# Project Forge CI execution policy — Linux-first

## Default execution target

Use **Ubuntu/Linux** for routine pull-request and default-branch CI across Project Forge Platform, component Kits, and newly generated Projects. Docker-based application and integration runtimes target Linux containers, regardless of whether a Developer uses Windows/WSL2, macOS, or Linux locally.

For standard Projects, generated CI defaults to `runs-on: ubuntu-latest`. Preserve stack-specific tests, application security gates, Docker/Compose proofs, exact-baseline checks, and stable branch-protection status checks. Test all supported language versions when compatibility warrants it, but do not multiply them by desktop OS without an explicit native-host requirement.

An existing adopted Project keeps its repository-owned CI unless the Builder expressly elects to change it. Adoption is not permission to replace a team's CI or operating-system coverage.

## Native-host exceptions

Windows and macOS should **not** be normal runtime CI matrix axes. They may be exercised separately only when testing host-specific behavior that a Linux container cannot faithfully verify, such as:

- Windows PowerShell 5.1, native command shims, path/quoting behavior, and generated Windows setup or doctor wrappers.
- macOS Homebrew discovery, system utilities, and native setup/doctor wrappers.
- A Project explicitly targeting native Windows/macOS binaries or deployment environments.

Prefer manually dispatched or path-scoped native compatibility workflows. For a change affecting a supported native-host entrypoint, run and review its native checks before approving that change for release; an optional check is not a substitute for required release evidence.

## Cost and concurrency

Private-repository macOS and Windows hosted minutes are substantially more expensive than Linux hosted minutes. For normal PR checks, prefer concurrency cancellation of superseded commits. Do not cancel stateful generation, invitation, release, or publication jobs.

Public repositories may already receive standard hosted-runner compute without charges. Optimize them for latency and signal quality, not assumed cash savings.

## Governance

- Platform owns this policy; Bootstrap owns Linux-first generated CI and should test the generated default.
- Kits own their CI implementation and justified host-specific exceptions.
- Preserve stable required check names and branch protection, including `CI / required` on Platform.
- Do not weaken Auth/Feedback isolation, Docker/Compose, cross-service integration, or release verification in the name of cost reduction.
- Future Windows/macOS matrices require an explicit runtime need, an owner, and a documented exception.
