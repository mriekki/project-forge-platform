# Project Forge Release Receipts

This directory contains durable, privacy-safe publication evidence for released `@mriekki/project-forge` package versions.

A receipt is named `<exact-semver>.json` and is added only after that exact package has been published and verified. It records the exact Platform source, logical component revisions, release-candidate hash, npm registry shasum, signed-provenance reference, and the release-gate verification facts that were true at publication time.

Receipts are repository history, not mutable current-state pointers. Current package/component selection remains owned by `package.json`, `assets/components.json`, and `chatgpt/current.json`. A receipt must not contain private source-repository names, credentials, secrets, consumer data, or deployment state.

Actions workflow/run IDs in a receipt are historical references only. The receipt remains valid evidence when those runs have expired under GitHub Actions retention. Release logic must prefer a valid receipt for the current published package and use historical Actions runs only as a legacy fallback for package versions that predate receipts.

Normal release flow adds the receipt in the post-publication public-contract alignment PR. Existing receipts are append-only in normal operation and must not be silently rewritten.


## On-demand native package provenance observation

The **Native Package Provenance Status (READ ONLY)** Actions workflow accepts
one exact, already-published native package version on main. It reuses the
existing native receipt validator and signed publication verifier, downloads
the exact npm archive without running package scripts, checks the pinned npm
verifier integrity and registry signature, and independently checks the signed
subject, certificate and original publication run. It does not change the
receipt, stable selection, publisher trust, registry or any deployment.

A successful run retains the nonsecret `native-package-provenance-observation`
artifact for 30 days. The artifact binds the exact receipt bytes, archive hash,
version, original publication run and verification run/attempt/commit/time.
The artifact is a projection of the existing verifier's result, **not** a new
signature or authorization. Independently check its origin, successful job and
artifact digest, reviewed workflow commit, and receipt identity before relying
on it. PR runs exercise the path against the stable receipt as a preview only;
do not use a PR artifact as authoritative main-branch proof. A missing,
expired or unavailable original run/attestation or failed verification leaves
fresh verification unavailable; it does not rewrite or invalidate the
historical receipt. No production or publication gate is satisfied by this
diagnostic.
