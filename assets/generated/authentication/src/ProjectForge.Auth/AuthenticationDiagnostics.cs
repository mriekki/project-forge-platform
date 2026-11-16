using System;
using System.Collections.Generic;
using System.Linq;

namespace ProjectForge.Auth;

// Fixed internal diagnostics. These states must be populated only by trusted
// application middleware and must never include raw Google tokens, provider
// response bodies, account emails, usernames, session IDs or exception text.
public enum AuthenticationStage
{
    PublicOrigin,
    OidcAssertion,
    AccountAdmission,
    Session,
    ApplicationAuthorization,
    InvitationEmail
}

public enum AuthenticationStageState
{
    NotChecked,
    Passed,
    Failed,
    Blocked
}

public enum AuthenticationFailureCode
{
    None,
    PublicOriginRejected,
    OidcAssertionRejected,
    AccountNotAdmitted,
    SessionRejected,
    ApplicationAccessDenied,
    InvitationDeliveryUnavailable,
    Unclassified
}

public sealed record AuthenticationStageEvidence(
    AuthenticationStage Stage,
    AuthenticationStageState State,
    AuthenticationFailureCode FailureCode);

public sealed record AuthenticationDiagnosticSummary(
    int SchemaVersion,
    string Status,
    AuthenticationFailureCode ReasonCode,
    IReadOnlyList<AuthenticationStage> Proved,
    IReadOnlyList<AuthenticationStage> Failed,
    IReadOnlyList<AuthenticationStage> Blocked,
    IReadOnlyList<AuthenticationStage> NotChecked,
    DateTimeOffset ObservedAt,
    bool Mutated)
{
    // Public callers receive a uniform response, regardless of known,
    // uninvited, disabled or unlinked account state.
    public string PublicFailureMessage => "Unable to complete sign-in.";
}

/// <summary>
/// Deterministic, bounded, side-effect-free diagnostic projection.
/// This does not perform Google authentication, grant access or issue sessions.
/// </summary>
public static class AuthenticationDiagnostics
{
    private static readonly AuthenticationStage[] Stages =
    [
        AuthenticationStage.PublicOrigin,
        AuthenticationStage.OidcAssertion,
        AuthenticationStage.AccountAdmission,
        AuthenticationStage.Session,
        AuthenticationStage.ApplicationAuthorization,
        AuthenticationStage.InvitationEmail
    ];

    private static readonly IReadOnlyDictionary<AuthenticationStage, AuthenticationFailureCode> ExpectedFailures =
        new Dictionary<AuthenticationStage, AuthenticationFailureCode>
        {
            [AuthenticationStage.PublicOrigin] = AuthenticationFailureCode.PublicOriginRejected,
            [AuthenticationStage.OidcAssertion] = AuthenticationFailureCode.OidcAssertionRejected,
            [AuthenticationStage.AccountAdmission] = AuthenticationFailureCode.AccountNotAdmitted,
            [AuthenticationStage.Session] = AuthenticationFailureCode.SessionRejected,
            [AuthenticationStage.ApplicationAuthorization] = AuthenticationFailureCode.ApplicationAccessDenied,
            [AuthenticationStage.InvitationEmail] = AuthenticationFailureCode.InvitationDeliveryUnavailable
        };

    public static AuthenticationDiagnosticSummary Summarize(
        IEnumerable<AuthenticationStageEvidence> observations,
        DateTimeOffset observedAt)
    {
        ArgumentNullException.ThrowIfNull(observations);
        var byStage = new Dictionary<AuthenticationStage, AuthenticationStageEvidence>();
        foreach (var entry in observations)
        {
            if (entry is null || !ExpectedFailures.ContainsKey(entry.Stage) ||
                !Enum.IsDefined(entry.State) || !Enum.IsDefined(entry.FailureCode) ||
                !byStage.TryAdd(entry.Stage, entry))
            {
                throw new ArgumentException("Invalid or duplicate authentication stage observation.", nameof(observations));
            }

            if (entry.State == AuthenticationStageState.Failed &&
                entry.FailureCode != ExpectedFailures[entry.Stage] &&
                entry.FailureCode != AuthenticationFailureCode.Unclassified)
            {
                throw new ArgumentException("Failure code conflicts with stage.", nameof(observations));
            }

            if (entry.State != AuthenticationStageState.Failed &&
                entry.FailureCode != AuthenticationFailureCode.None)
            {
                throw new ArgumentException("A nonfailed stage cannot report a failure code.", nameof(observations));
            }
        }

        var proved = new List<AuthenticationStage>(6);
        var failed = new List<AuthenticationStage>(6);
        var blocked = new List<AuthenticationStage>(6);
        var notChecked = new List<AuthenticationStage>(6);
        var failure = AuthenticationFailureCode.None;
        foreach (var stage in Stages)
        {
            var state = byStage.TryGetValue(stage, out var evidence)
                ? evidence.State
                : AuthenticationStageState.NotChecked;
            switch (state)
            {
                case AuthenticationStageState.Passed:
                    proved.Add(stage);
                    break;
                case AuthenticationStageState.Failed:
                    failed.Add(stage);
                    if (failure == AuthenticationFailureCode.None)
                    {
                        failure = evidence!.FailureCode;
                    }
                    break;
                case AuthenticationStageState.Blocked:
                    blocked.Add(stage);
                    break;
                default:
                    notChecked.Add(stage);
                    break;
            }
        }

        // Email invitation delivery is not a prerequisite for an already
        // approved user's interactive sign-in.
        var required = Stages.Take(5).ToArray();
        var allRequiredProved = required.All(proved.Contains);
        var status = required.Any(failed.Contains) ? "failed"
            : required.Any(blocked.Contains) ? "blocked"
            : allRequiredProved ? "proved" : "incomplete";
        return new AuthenticationDiagnosticSummary(
            1, status, failure, proved, failed, blocked, notChecked,
            observedAt.ToUniversalTime(), Mutated: false);
    }
}
