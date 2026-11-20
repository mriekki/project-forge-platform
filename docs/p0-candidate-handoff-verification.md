# Existing-release npm candidate verification (offline preview)

**Status:** Verification-only public Platform utility. This does not initiate a release, trust a private source, install a GitHub App, grant access, deploy a Project or replace npm trusted publishing.

The independent public CLI `scripts/verify-candidate-handoff.mjs` compares a candidate npm archive and its **untrusted** handoff metadata with the previously published, repository-owned `release/receipts/<version>.json` evidence.

For a downloaded or locally prepared `@mriekki/project-forge` candidate and the approved immutable public reference SHA:

```bash
node scripts/verify-candidate-handoff.mjs \
  --handoff ./UNTRUSTED_CANDIDATE_HANDOFF.json \
  --tarball ./mriekki-project-forge-4.35.0.tgz \
  --reference-commit 74b9462df28faab16bcde7599373f632e2b29626
```

The CLI reads the public receipt from the checked-out Platform repository, never from the untrusted candidate. It checks the exact archive SHA-256, byte count and npm filename, component revision/version set, selected immutable public reference, strict metadata fields, and the existing receipt's structural publication/CI claims. It returns `MATCHES_EXISTING_PUBLIC_RELEASE` only if all checks pass.

**Trust boundary:** Matching an already-published archive is not a proof of current GitHub source identity, independent Sigstore signature validation, review/CI authorization for a *new* version, or permission to publish. The CLI always returns `identityVerified=false`, `publicationAuthorized=false`, `productionAuthorized=false`. It does not call `npm publish`, GitHub APIs, registries, secrets, token endpoints, or modify any public release files.

A newly proposed version with **no existing durable public receipt intentionally fails closed**. Creating an actual source-to-publisher handoff requires a separately approved identity and access mechanism, independently qualified new-version release/consumer checks, the existing public signed-provenance and receipt pipeline, and explicit release authorization.

The utility is outside the `package.json` public npm `files` allowlist, so it does not change the published consumer payload or require a new npm version.
