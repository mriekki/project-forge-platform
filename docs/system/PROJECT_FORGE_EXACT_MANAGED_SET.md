# Project Forge Exact Managed Set

## Purpose

This document defines the operational interpretation of the package-managed update safety requirement in `PF-SYS-028` and the package-managed update boundary in `PF-SYS-027`. It does not create a second requirements authority; `PROJECT_FORGE_SYSTEM_REQUIREMENTS.md` remains normative.

## Invariant

After a successful Project Forge package/profile apply or update, the consumer MUST satisfy the **Exact Managed Set** invariant:

1. every path declared by the selected package/profile exists at the package-defined content;
2. every path recorded in the previous component baseline but absent from the new package/profile is no longer Project Forge-managed;
3. an unchanged retired managed file is removed automatically;
4. a retired managed file with consumer drift blocks the update unless the applicable ownership-transfer contract explicitly accepts that path;
5. when ownership is explicitly transferred, the file may remain in the consumer but MUST be omitted from the new Project Forge managed baseline;
6. unmanaged consumer files are outside this invariant and MUST NOT be deleted merely because they are absent from the Project Forge distribution;
7. the newly written component baseline contains exactly the managed paths declared by the selected package/profile.

The invariant applies to Project Forge-managed files, not to the consumer directory tree as a whole. Project Forge therefore converges its owned file set without destructive directory mirroring.

## State interpretation

The current update engine expresses the invariant through managed-path planning states:

- `ADD`, `CORE_UPDATE`, and `KIT_UPDATE` materialize current package-owned content;
- `SAME`, `UNTRACKED_MATCH`, and `BASELINE_STALE` are safe convergence states when ownership/content already agree;
- `REMOVE` deletes a previously managed path that the new distribution retired and whose current content still matches the previous baseline;
- `RETIRED_MISSING` is already converged because the retired managed path is absent;
- `LOCAL_DRIFT`, `CONFLICT`, `PATH_CONFLICT`, and `RETIRED_DRIFT` fail closed rather than overwrite/delete ambiguous consumer work;
- an explicitly accepted Core retirement transfers ownership out of Project Forge and therefore preserves the file while removing it from the new managed baseline.

## Success condition

A package update is not clean merely because all newly declared files were copied. It is clean only when:

- current managed destinations match the selected package/profile;
- no unhandled retired managed paths remain;
- component baseline metadata represents the current component revision/distribution;
- the baseline managed-path set exactly matches the selected distribution mappings.

## Non-goals

Exact Managed Set does **not** authorize Project Forge to:

- delete arbitrary untracked files;
- prune directories recursively because they are not package-owned;
- overwrite locally modified managed files without the normal drift-resolution contract;
- silently adopt consumer-owned files into Project Forge ownership;
- treat an ownership transfer as permission to modify the transferred file later.

## Regression expectation

Platform tests must cover at least one update where a previously managed path is retired, a replacement path is added, an unrelated unmanaged consumer file coexists in the same repository, and the resulting baseline contains exactly the new managed set. The retired unchanged file must be gone, the replacement must have package-defined content, and the unmanaged consumer file must remain untouched.
