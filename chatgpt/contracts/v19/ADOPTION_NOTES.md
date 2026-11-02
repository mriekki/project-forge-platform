# Existing-Repository Adoption Notes

The stable `New Project` picker now includes **Adopt an existing repository** when the current descriptor advertises the `adoption` compatibility object.

Remote adoption remains distinct from greenfield generation. It uses `PROJECT_ADOPTION.json`, the exact analyzed target commit, an explicit `Apply adoption [WRITE]?` gate, a short-lived manifest-only seed branch, the distinct `[adopt-project]` Control Plane operation, deterministic exact-base apply, target PR/CI evidence, and human merge/finalize.

This note is explanatory only and is not part of the immutable seven-document ChatGPT snapshot declared by `chatgpt/current.json`.
