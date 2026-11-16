using System;
using System.Collections.Generic;

namespace ProjectForge.Auth;

/// <summary>
/// Immutable OIDC identity key. Provider token validation is the responsibility
/// of a trusted adapter: never construct one from unsigned browser parameters.
/// Comparison is deliberately ordinal; provider subjects are not email aliases.
/// </summary>
public sealed record ExternalIdentityKey
{
    public string Issuer { get; }
    public string Subject { get; }

    public ExternalIdentityKey(string issuer, string subject)
    {
        if (string.IsNullOrWhiteSpace(issuer) ||
            !Uri.TryCreate(issuer, UriKind.Absolute, out var address) ||
            address.Scheme != Uri.UriSchemeHttps ||
            !string.IsNullOrEmpty(address.UserInfo) ||
            !string.IsNullOrEmpty(address.Query) ||
            !string.IsNullOrEmpty(address.Fragment))
        {
            throw new ArgumentException("An absolute HTTPS issuer is required.", nameof(issuer));
        }

        if (string.IsNullOrWhiteSpace(subject) || subject != subject.Trim())
        {
            throw new ArgumentException("A stable, nonblank subject is required.", nameof(subject));
        }

        Issuer = issuer;
        Subject = subject;
    }
}

/// <summary>
/// An assertion already authenticated by the host's OIDC middleware.
/// This type does not verify tokens, issuer allowlists, nonce, audience or PKCE.
/// </summary>
public sealed record VerifiedExternalPrincipal(
    ExternalIdentityKey Identity,
    string? Email,
    bool EmailVerified);

public enum ApplicationAccountState
{
    PendingApproval,
    Approved,
    Disabled
}

/// <summary>
/// Snapshot read from the owning application's trusted account store.
/// Public-facing responses must not distinguish unknown, disabled or unlinked users.
/// </summary>
public sealed record AccountSnapshot(
    Guid AccountId,
    ApplicationAccountState State,
    IReadOnlySet<ExternalIdentityKey> LinkedIdentities);

public enum SignInDecision
{
    Denied,
    Allowed
}

/// <summary>
/// An application-store-validated invitation proof. The caller must validate
/// a one-time token hash and redeem it transactionally with the account write.
/// A matching email alone never constitutes an invitation.
/// </summary>
public sealed record ValidatedInvitation(
    Guid InvitationId,
    string IntendedEmail,
    ExternalIdentityKey? BoundIdentity,
    DateTimeOffset ExpiresAt,
    bool TokenProofVerified,
    bool Consumed,
    bool Revoked);

/// <summary>
/// Explicitly reviewed, time-bounded, stable identity for initial administrator
/// creation. No "first user to sign in becomes admin" behavior.
/// </summary>
public sealed record PreapprovedAdministratorSeed(
    ExternalIdentityKey Identity,
    DateTimeOffset ExpiresAt,
    bool Enabled);

/// <summary>
/// Fail-closed, side-effect-free policy primitives for the initial Google OIDC
/// household preset. These do not create users, issue sessions, send email,
/// mutate storage, or replace proper OIDC validation or transaction boundaries.
/// </summary>
public sealed class InviteOnlyAdmissionPolicy
{
    public SignInDecision EvaluateSignIn(
        VerifiedExternalPrincipal principal,
        AccountSnapshot? account)
    {
        ArgumentNullException.ThrowIfNull(principal);

        if (!HasVerifiedEmail(principal) ||
            account is null ||
            account.AccountId == Guid.Empty ||
            account.State != ApplicationAccountState.Approved ||
            account.LinkedIdentities is null ||
            !account.LinkedIdentities.Contains(principal.Identity))
        {
            return SignInDecision.Denied;
        }

        return SignInDecision.Allowed;
    }

    public bool MayAcceptInvitation(
        VerifiedExternalPrincipal principal,
        ValidatedInvitation? invitation,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(principal);

        if (!HasVerifiedEmail(principal) ||
            invitation is null ||
            invitation.InvitationId == Guid.Empty ||
            !invitation.TokenProofVerified ||
            invitation.Consumed ||
            invitation.Revoked ||
            now >= invitation.ExpiresAt ||
            !SameNormalizedEmail(principal.Email!, invitation.IntendedEmail))
        {
            return false;
        }

        return invitation.BoundIdentity is null ||
               invitation.BoundIdentity == principal.Identity;
    }

    public bool MayInitializeFirstAdministrator(
        VerifiedExternalPrincipal principal,
        PreapprovedAdministratorSeed? seed,
        int existingAdministratorCount,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(principal);

        return HasVerifiedEmail(principal) &&
               existingAdministratorCount == 0 &&
               seed is { Enabled: true } &&
               now < seed.ExpiresAt &&
               seed.Identity == principal.Identity;
    }

    private static bool HasVerifiedEmail(VerifiedExternalPrincipal principal) =>
        principal.Identity is not null &&
        principal.EmailVerified &&
        !string.IsNullOrWhiteSpace(principal.Email);

    private static bool SameNormalizedEmail(string asserted, string intended) =>
        !string.IsNullOrWhiteSpace(intended) &&
        string.Equals(
            asserted.Trim(),
            intended.Trim(),
            StringComparison.OrdinalIgnoreCase);
}
