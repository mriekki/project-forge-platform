# Project Forge Release Receipts

This directory contains durable, privacy-safe publication evidence for released `@mriekki/project-forge` package versions.

A receipt is named `<exact-semver>.json` and is added only after that exact package has been published and verified. It records the exact Platform source, logical component revisions, release-candidate hash, npm registry shasum, signed-provenance reference, and the release-gate verification facts that were true at publication time.

Receipts are repository history, not mutable current-state pointers. Current package/component selection remains owned by `package.json`, `assets/components.json`, and `chatgpt/current.json`. A receipt must not contain private source-repository names, credentials, secrets, consumer data, or deployment state.

Actions workflow/run IDs in a receipt are historical references only. The receipt remains valid evidence when those runs have expired under GitHub Actions retention. Release logic must prefer a valid receipt for the current published package and use historical Actions runs only as a legacy fallback for package versions that predate receipts.

Normal release flow adds the receipt in the post-publication public-contract alignment PR. Existing receipts are append-only in normal operation and must not be silently rewritten.
