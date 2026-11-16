---
applyTo: "**"
---

# Project Forge Local Development Contract

Keep Core stack-neutral and Projects operationally deterministic. Follow `docs/process/LOCAL_DEVELOPMENT_COMMANDS.md` when it exists.

When an Engineering Enabler or equivalent foundational work item first establishes executable application topology, establish unambiguous repository-owned build and run commands for the normal developer path. Do not require a particular wrapper language or invent placeholder commands before executable topology exists.

For Feature Brief and Engineering Enabler implementation/validation, default application execution and persistence operations to the established Project-owned local developer runtime and its associated persistence unless the developer explicitly selects a supported alternative. When the Project defines a local container/database pair as that topology, do not silently substitute a native process or separate checkout database.

If the established default runtime/persistence is absent, stopped, stale, or blocked by initialization/schema prerequisites, route through `/setup local` or the repository-owned repair workflow. Do not bypass it by selecting another runtime/database. Preserve `/run`'s no-implicit-setup/no-automatic-migration boundary.

When a work item materially changes executable topology, assess and maintain the affected Project-owned engineering interfaces in the same accepted change:

```text
BUILD CONTRACT IMPACT
RUN CONTRACT IMPACT
SETUP CONTRACT IMPACT
CI CONTRACT IMPACT
```

Examples include build-system changes, native/container changes, component composition, persistence ownership/location, launch profiles/ports, transport/authentication requirements, readiness checks, and stop/cleanup mechanics.

Prefer the same underlying repository-owned build entry point in CI where practical. Preserve repository-required isolated/disposable test runtimes and databases; never redirect automated tests into mutable developer data merely to reuse the normal developer runtime.

A failing or stale established build/run command is a Project contract problem. Do not silently bypass it with ecosystem-native inference. Framework-native discovery remains a fallback only while no Project-owned command contract exists yet or when the developer explicitly selects a supported alternative.
