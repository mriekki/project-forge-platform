---
name: web-guidance
description: Consult modern browser-compatible web platform patterns for relevant UI, CSS, client JavaScript, PWA, accessibility, and performance work.
user-invocable: false
---

# Modern Web Guidance

Automatically use this skill for browser-facing HTML/CSS, UI/client-side JavaScript, responsive design, accessibility, performance and PWA implementation or review. For mixed backend/frontend work, scope lookup to the browser-facing portion. Do not invoke for backend-only TypeScript, SQL, API routes, Docker, CI, dependency tooling, or unrelated non-web work.

This Project Forge skill is a **thin adapter** to Google's externally maintained [Modern Web Guidance](https://github.com/GoogleChrome/modern-web-guidance). Do not copy Google's skill pack or guide library into Project Forge. Approved Project requirements, existing engineering conventions, browser support, security constraints and Human-in-the-Loop gates outrank external recommendations.

## Task workflow

1. Identify one relevant browser capability. Inspect any existing `.mwgrc`, browser-support policy and installed third-party skills read-only; do not replace them.
2. Search with a short action phrase, e.g., `"accessible modal dialog"`, not product-specific names. Use **exact CLI version `modern-web-guidance@1.0.0`**, never floating `@latest`.
3. Inspect search matches, retrieve only relevant guide IDs and applicable discipline guidance; rephrase once when no good result appears. No matching guide means proceed with repository standards; never fabricate a result.
4. Apply progressive enhancement, appropriate compatibility fallbacks and Project target-browser policy. Do not opt in to volatile APIs or Origin Trials without Builder approval. Do not introduce unrelated dependencies or redesigns.
5. Cross-check with code/tests. Briefly attribute materially used guidance IDs in implementation/review reports without copying whole guides.

### Exact-version invocation

Linux, macOS, WSL:

```sh
DISABLE_TELEMETRY=1 npx --yes modern-web-guidance@1.0.0 search "accessible modal dialog"
DISABLE_TELEMETRY=1 npx --yes modern-web-guidance@1.0.0 retrieve "<returned-guide-id>"
```

For PowerShell, set `$env:DISABLE_TELEMETRY = '1'` before the same `npx.cmd --yes modern-web-guidance@1.0.0` command. Requires Node.js **22+**. Disable telemetry on each invocation; never change global shell configuration, share secrets, or upload source/user prompts. The initial package fetch requires normal network/terminal permissions; do not bypass denied permissions or grant blanket npx access. Cached CLI can search locally.

The Project Forge-managed skill is the entrypoint. **Do not run Google's interactive `install` wizard** during Project Forge setup: it would write a second, unmanaged agent skill. Respect already installed third-party guidance without overwriting it.

If exact CLI, compatible Node, permission or network access is unavailable, report guidance `DEFERRED` without blocking otherwise valid local development. No silent runtime upgrade solely for optional guidance.

## Modernization

Run `legacy-scan` only if the Builder explicitly requests broad web modernization/legacy-pattern review. Validate findings manually, preserve intentional compatibility fallbacks, report false positives and never auto-edit during read-only review.

## Credits

Google Chrome/collaborators maintain the guidance. Guide content is CC BY 4.0; upstream code is Apache 2.0. Attribute copied/adapted documentation, do not vendor the corpus.
