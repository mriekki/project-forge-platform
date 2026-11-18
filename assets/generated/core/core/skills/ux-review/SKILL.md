---
name: ux-review
description: Read-only review of user-facing features for usability, accessibility, responsiveness, modern browser behavior and performance.
argument-hint: "[feature, route, screen, or work-item ID]"
user-invocable: true
disable-model-invocation: true
---

# UX Review

`/ux-review` is a **read-only**, evidence-led experience review for new or existing Projects. Best for web/PWA Projects, but applicable to other user-facing software using that platform's conventions. Opt-in; never a mandatory release gate and not a replacement for independent implementation Reviewer.

## Scope

Resolve the requested feature, flow, work item or screen from current repository-owned requirements, architecture, screenshots, code, tests and design system. If broad, select and name representative journeys; never claim whole-app coverage from limited screens. For browser work consult the agent-invoked `web-guidance` skill when applicable and available. Non-browser UI should not be judged using browser APIs.

## Observe truthfully

Prefer actual observable screens across relevant viewport sizes, keyboard use, accessible names/landmarks, forms, error/empty/loading states, responsive layouts, touch targets, contrast, reduced motion, PWA offline/install/update states and existing performance evidence. Use safe existing tools only when they are already available and permitted.

Never claim a browser/device/assistive technology or audit was run unless actually observed. Mark static-only observations and unverified assumptions. Read-only **does not authorize** editing files, installing tools, starting infrastructure with side effects, authenticating as real users, submitting forms, mutating databases or deploying. Request separate authorization when needed or report a gap.

## Review dimensions

- Usability: task clarity, information hierarchy, navigation, feedback, error recovery and cognitive load.
- Accessibility: semantic structure, keyboard/focus behavior, labels, contrast, zoom, reduced motion and touch.
- Responsive and visual: mobile/tablet/desktop behavior, readability, affordances, consistency with approved design system.
- Browser/PWA: target-browser compatibility, progressive enhancement, offline/update behavior and permission flows.
- Performance and trust: perceived responsiveness, expensive interactions, privacy/safety signals, destructive-action clarity.

Do not force fads, extra libraries, unrequested redesigns, or newly invented product requirements.

## Passkey sign-in review (when the Project actually enables WebAuthn)

For a Project whose **repository configuration and verified runtime** explicitly select passkeys, also examine its passkey user journey. This is a conditional review dimension, **not a claim that Project Forge or the app currently ships passkeys**. Check:

- The person first establishes an approved Project account through its configured admission method (for the initial Auth Kit household model, verified Google OIDC plus invitation/admin approval). "Add a passkey" must not silently create or link an account using email.
- The primary sign-in action communicates **passkey** rather than promising Face ID specifically. Browsers/devices may offer Face ID, Touch ID, Windows Hello, Android biometrics, a security key or a device PIN.
- Google remains clearly available for fallback and lost-device recovery. Cancel, unsupported browser, unavailable authenticator, expired challenge, missing credential and transient network errors offer a safe retry or recovery path without revealing whether another account exists.
- A valid existing Project session should not produce unnecessary biometric prompts. **Passkey sign-in after session expiry** is distinct from **requiring an app unlock each time a PWA is opened**, and offline app unlock is not implied.
- Account security settings let an authorized user intentionally register, identify, manage and revoke the user's own credentials; important changes require the currently reviewed step-up/recovery policy. Never claim a synced passkey equals one physical device.
- Server and deployment evidence must establish HTTPS, the exact Project RP ID/origin and strict trusted-proxy behavior. UI review is not WebAuthn cryptographic validation. Expose missing account isolation, CSRF, single-use challenge, counter/backup/replay, recovery or restored-state proof to security review rather than passing UX solely on a successful screenshot.
- For the intended browser/device matrix, check Safari and installed iOS PWA separately where practical, plus accessible keyboard/focus and visible Google fallback. State **NOT VERIFIED** for devices that have not actually been tested. Fresh sign-in requires a network connection even if other PWA features work offline.

Follow the canonical [cross-repository passkey initiative](https://github.com/mriekki/project-forge-auth-kit/issues/26) only when relevant, and record any application-specific results in that Project's normal Issue/PR/review evidence. Do not create a separate passkey-specific UX command, replace `/start-work` or turn this optional review into an automatic release gate.

## Findings

State review scope, inspected evidence and not-verified surfaces. List actionable findings with location/flow, impact, supporting evidence, and smallest plausible remedy. Classify `HIGH` (essential-task/accessibility blocker), `MEDIUM` (significant friction), `LOW` (polish), and `EVIDENCE GAP` (not tested). Include strengths only when evidenced.

End with a concise recommendation and relevant verification plan. Findings are **proposals**, not approved requirements. Offer to convert selected findings into work items through Project Forge's normal requirements/`/start-work` gates. This skill never edits, stages, commits, pushes, opens PRs, merges, or deploys.
