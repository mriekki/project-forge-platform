using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Fido2NetLib;
using Fido2NetLib.Objects;

namespace ProjectForge.Auth.Runtime;

/// <summary>
/// Project-scoped WebAuthn cryptographic boundary. Auth Kit must persist the exact
/// options for a single-use, expiring, account/session-bound ceremony before
/// accepting a response. This service is not an endpoint or an authentication
/// session issuer, and must never accept browser-selected RP origins.
/// </summary>
public sealed class ProjectPasskeyWebAuthn
{
    private readonly IFido2 _fido2;
    public string RelyingPartyId { get; }
    public string ExactOrigin { get; }

    public ProjectPasskeyWebAuthn(string exactHttpsOrigin, string displayName)
    {
        if (!Uri.TryCreate(exactHttpsOrigin, UriKind.Absolute, out var uri) ||
            uri.Scheme != Uri.UriSchemeHttps ||
            uri.AbsolutePath != "/" ||
            !string.IsNullOrEmpty(uri.Query) ||
            !string.IsNullOrEmpty(uri.Fragment) ||
            !string.IsNullOrEmpty(uri.UserInfo) ||
            string.IsNullOrWhiteSpace(displayName) ||
            displayName.Length > 100)
            throw new ArgumentException("Exact configured HTTPS Project origin and display name required.");
        if (!string.Equals(exactHttpsOrigin.TrimEnd('/'), uri.GetLeftPart(UriPartial.Authority),
                StringComparison.Ordinal))
            throw new ArgumentException("Project origin must be canonical and include no path.");
        RelyingPartyId = uri.IdnHost;
        ExactOrigin = uri.GetLeftPart(UriPartial.Authority);
        _fido2 = new Fido2(new Fido2Configuration
        {
            RPID = RelyingPartyId,
            RPName = displayName,
            Origins = new HashSet<string>(StringComparer.Ordinal) { ExactOrigin },
            ChallengeSize = 32,
            Timeout = 180000
        });
    }

    /// <summary>The caller MUST bind and persist these options to the current
    /// approved, recently Google-authenticated Project account session.</summary>
    public CredentialCreateOptions CreateRegistrationOptions(byte[] opaqueUserHandle,
        IReadOnlyList<byte[]> existingCredentialIds)
    {
        if (opaqueUserHandle is null || opaqueUserHandle.Length != 32)
            throw new ArgumentException("Expected a stable, opaque 32-byte Project user handle.");
        return _fido2.RequestNewCredential(new RequestNewCredentialParams
        {
            User = new Fido2User
            {
                Id = opaqueUserHandle,
                Name = "Project account",
                DisplayName = "Project account"
            },
            ExcludeCredentials = existingCredentialIds.Select(x =>
                new PublicKeyCredentialDescriptor(x)).ToArray(),
            AuthenticatorSelection = new AuthenticatorSelection
            {
                ResidentKey = ResidentKeyRequirement.Required,
                UserVerification = UserVerificationRequirement.Required
            },
            AttestationPreference = AttestationConveyancePreference.None
        });
    }

    /// <summary>All claims in the returned credential are verified by Fido2.
    /// The caller must still atomically persist it to the session's account.</summary>
    public async Task<RegisteredPublicKeyCredential> VerifyRegistrationAsync(
        AuthenticatorAttestationRawResponse response,
        string originalOptionsJson,
        byte[] expectedUserHandle,
        Func<byte[], bool> credentialIdExists,
        CancellationToken cancellationToken = default)
    {
        if (response is null || string.IsNullOrWhiteSpace(originalOptionsJson) ||
            expectedUserHandle is null || expectedUserHandle.Length != 32)
            throw new ArgumentException("Valid registration ceremony required.");
        var options = CredentialCreateOptions.FromJson(originalOptionsJson);
        if (options?.User?.Id is null ||
            !CryptographicOperations.FixedTimeEquals(options.User.Id, expectedUserHandle) ||
            !string.Equals(options.Rp?.Id, RelyingPartyId, StringComparison.Ordinal) ||
            options.AuthenticatorSelection?.UserVerification != UserVerificationRequirement.Required)
            throw new InvalidOperationException("Registration ceremony does not match Project policy.");

        var verified = await _fido2.MakeNewCredentialAsync(new MakeNewCredentialParams
        {
            AttestationResponse = response,
            OriginalOptions = options,
            IsCredentialIdUniqueToUserCallback = (args, _) =>
                Task.FromResult(!credentialIdExists(args.CredentialId))
        }, cancellationToken);
        // Stable Fido2 4.3.3 validates the requested origin/RP ID and UV
        // policy inside MakeNewCredentialAsync; it does not expose the
        // development-branch RpId/UvInitialized credential properties.
        if (verified.User is null || verified.User.Id is null ||
            !CryptographicOperations.FixedTimeEquals(verified.User.Id, expectedUserHandle))
            throw new InvalidOperationException("Verified passkey does not meet Project policy.");
        return verified;
    }

    /// <summary>Username-free discoverable passkey flow. Never include a
    /// global credential list or leak account existence in options.</summary>
    public AssertionOptions CreateAuthenticationOptions() =>
        _fido2.GetAssertionOptions(new GetAssertionOptionsParams
        {
            AllowedCredentials = [],
            UserVerification = UserVerificationRequirement.Required
        });

    /// <summary>Cryptographically verify assertion, challenge, origin, RP ID,
    /// user verification and public-key signature before any Project session.</summary>
    public async Task<VerifyAssertionResult> VerifyAuthenticationAsync(
        AuthenticatorAssertionRawResponse response,
        string originalOptionsJson,
        ProjectPasskeyCredential stored,
        CancellationToken cancellationToken = default)
    {
        if (response?.RawId is null || stored is null ||
            !response.RawId.AsSpan().SequenceEqual(stored.CredentialId) ||
            string.IsNullOrWhiteSpace(originalOptionsJson))
            throw new ArgumentException("Passkey assertion unavailable.");
        var options = AssertionOptions.FromJson(originalOptionsJson);
        if (options is null ||
            options.UserVerification != UserVerificationRequirement.Required ||
            options.RpId != RelyingPartyId ||
            options.AllowCredentials.Count != 0)
            throw new InvalidOperationException("Authentication ceremony does not match Project policy.");
        var verified = await _fido2.MakeAssertionAsync(new MakeAssertionParams
        {
            AssertionResponse = response,
            OriginalOptions = options,
            StoredPublicKey = stored.PublicKey,
            StoredSignatureCounter = stored.SignCount,
            IsUserHandleOwnerOfCredentialIdCallback = (args, _) =>
                Task.FromResult(args.CredentialId.AsSpan().SequenceEqual(stored.CredentialId) &&
                    args.UserHandle is not null &&
                    args.UserHandle.AsSpan().SequenceEqual(stored.UserHandle))
        }, cancellationToken);
        // Stable Fido2 4.3.3 enforces UV from the persisted Required options.
        // Its result type does not yet expose the newer IsUserVerified property.
        if (!verified.CredentialId.AsSpan().SequenceEqual(stored.CredentialId))
            throw new InvalidOperationException("Verified assertion does not meet Project user-verification policy.");

        // The immutable BE flag is part of signed authenticatorData. Fido2
        // 4.3.3 checks BS-without-BE but lacks the newer
        // StoredBackupEligible input needed to compare this credential's
        // registration-time BE. Compare only AFTER its challenge, origin,
        // RP ID, UV and signature verification has succeeded. BS may evolve
        // for a synced passkey; BE must never change.
        var signedAuthenticatorData = response.Response?.AuthenticatorData;
        if (signedAuthenticatorData is null || signedAuthenticatorData.Length < 37)
            throw new InvalidOperationException("Verified passkey authenticator data missing.");
        const byte backupEligibleBit = 0x08;
        const byte backedUpBit = 0x10;
        bool eligibleNow = (signedAuthenticatorData[32] & backupEligibleBit) != 0;
        bool backedUpNow = (signedAuthenticatorData[32] & backedUpBit) != 0;
        if (eligibleNow != stored.BackupEligible ||
            (!eligibleNow && backedUpNow) ||
            backedUpNow != verified.IsBackedUp)
            throw new InvalidOperationException("Verified passkey backup eligibility mismatch.");

        return verified;
    }
}
