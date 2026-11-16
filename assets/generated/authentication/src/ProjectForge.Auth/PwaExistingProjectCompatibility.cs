using System;

namespace ProjectForge.Auth;

/// <summary>
/// Compatibility boundary for existing Family Meal Planner FB-001 accounts.
/// This adapts the already-linked Google identity to the reusable approval
/// policy WITHOUT changing its on-disk 32-hex string GUID, password hash,
/// email-recovery flow, session credentials, data or membership.
////
//// PWA still owns password sign-in, session issuance, OIDC code flow and
//// initial enrollment behavior until a separately approved runtime cutover.
/// The adapter must be called only after the PWA's trusted Google middleware
/// validated the OIDC assertion, issuer and subject. An unverified email
/// remains unverified under the PWA-compatible mode; it never links by email.
/// </summary>
public sealed record ExistingPwaGoogleAccount(
    string AccountIdN,
    string LinkedIssuer,
    string LinkedSubject,
    string Email,
    bool EmailVerifiedByGoogle);

public sealed record ExistingPwaCompatibilityResult(
    SignInDecision Decision,
    string? PreservedAccountId,
    string ReasonCode,
    bool PreserveUnverifiedEmailState);

public sealed class PwaExistingProjectCompatibility
{
    // Existing PWA FB-001 deliberately allows a verified OIDC assertion with
    // email_verified=false to create a non-email-verified account/session.
    // Its service tests document that behavior. New Projects default to the
    // stricter invite-only policy; migration must not silently tighten PWA.
    public ExistingPwaCompatibilityResult EvaluateExistingGoogleLink(
        ExistingPwaGoogleAccount? account,
        string authenticatedIssuer,
        string authenticatedSubject)
    {
        if (account is null ||
            !Guid.TryParseExact(account.AccountIdN, "N", out var id) ||
            id == Guid.Empty ||
            account.AccountIdN != id.ToString("N") ||
            authenticatedIssuer != "https://accounts.google.com" ||
            account.LinkedIssuer != authenticatedIssuer ||
            string.IsNullOrWhiteSpace(account.LinkedSubject) ||
            account.LinkedSubject != authenticatedSubject ||
            string.IsNullOrWhiteSpace(account.Email))
        {
            return new ExistingPwaCompatibilityResult(
                SignInDecision.Denied, null, "existing-link-not-proven", false);
        }

        // OIDC token validation and application-session issuance remain PWA
        // responsibilities. This adapter is a non-destructive exact-link
        // check, not a household membership or email verification grant.
        return new ExistingPwaCompatibilityResult(
            SignInDecision.Allowed,
            account.AccountIdN,
            "existing-link-verified-pwa-compatibility",
            !account.EmailVerifiedByGoogle);
    }
}
