# GitHub Issues Feedback integration

This .NET 10 backend adapter is optional. GitHub Issues in the Project's
server-configured repository are the authoritative feedback records. The
adapter does not provision an App, configure authentication, or deploy itself.

An application that enables it must:

- Supply an exact owner and repository, GitHub App and installation identifiers,
  a protected App private key, and a separate stable HMAC key of at least
  32 bytes. Keep all secrets and installation tokens on the backend.
- Configure the App installation for that repository with the required Issues
  permissions and required Feedback labels.
- Resolve the authenticated Project account and explicit submit/admin grants
  through `IGitHubFeedbackPrincipalResolver`; do not accept a browser-supplied
  account ID or infer permissions from household roles.
- Implement `IGitHubFeedbackMutationGuard` with the application's CSRF and
  exact-origin checks. Configure the `project-forge-feedback` rate-limit policy
  and register the endpoint group only after all dependencies are configured.
- Register a single `GitHubFeedbackClient` per application process. Do not
  horizontally scale writers without separate durable coordination.
- Keep Feedback disabled by default. In a supported .NET 10 host, call
  `AddProjectForgeGitHubFeedback` with the reviewed Project repository and exact
  public HTTPS origin; the adapter rejects repository mismatches, missing or
  unsafe secret files, and non-HTTPS origins. Register the Project-owned
  `IGitHubFeedbackPrincipalResolver` before mapping the routes. Add the package
  project reference from `tools/project-forge-feedback-kit/ProjectForge.Feedback.GitHub/ProjectForge.Feedback.GitHub.csproj`.
- Call `app.UseRateLimiter()` before `MapProjectForgeGitHubFeedback()`. Keep the
  forwarded client address trustworthy at the host boundary; do not accept
  browser-provided repository names, account IDs, or grants.
- Store `ProjectForge:Feedback:GitHub:PrivateKeyFile` and
  `ProjectForge:Feedback:GitHub:ReporterHmacKeyFile` as separate absolute
  protected files. On Unix, each file must be readable by the service owner
  only; the reporter key is at least 32 bytes encoded as hexadecimal. The App
  key must be a valid RSA PEM private key. Never place either secret in
  `PROJECT_BOOTSTRAP.json`, generated source, or browser configuration.
- Configure ASP.NET antiforgery and make a valid request token available to
  the application's authenticated UI. Mutation requests must carry both that
  token and the exact `Origin`; missing or invalid values fail closed.

The adapter exposes text-only submission, the reporter's own Issues, and an
explicitly authorized admin inbox and triage. It does not provide exactly-once
creation across processes or restarts; an uncertain provider result fails closed.
Enabling the package profile only installs and manages adapter assets; it does
not register routes, grant application access, create a GitHub App, or activate
the feature.
Unsupported stacks must not enable this adapter or silently substitute a stub.
