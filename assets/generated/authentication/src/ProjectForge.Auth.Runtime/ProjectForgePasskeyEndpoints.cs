using System;
using System.Linq;
using System.Threading.Tasks;
using Fido2NetLib;
using Fido2NetLib.Objects;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Routing;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;

namespace ProjectForge.Auth.Runtime;

/// <summary>Opt-in, same-origin WebAuthn endpoints using the Project-owned
/// account/session authority. Never map while Passkeys:Enabled is false.</summary>
internal static class ProjectForgePasskeyEndpoints
{
    private const string RegisterCookie = "__Host-pf-passkey-registration";
    private const string AuthenticateCookie = "__Host-pf-passkey-authentication";
    private const string CeremonyRatePolicy = "project-passkey-ceremonies";

    internal static IEndpointRouteBuilder MapProjectForgePasskeys(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/auth/passkeys/capabilities", (ProjectPasskeyWebAuthn verifier) =>
            Results.Ok(new
            {
                enabled = true,
                relyingPartyId = verifier.RelyingPartyId,
                userVerification = "required",
                enrollment = "approved-google-account"
            }));

        endpoints.MapGet("/api/auth/passkeys", (HttpContext http, ProjectAuthStore store) =>
        {
            var account = ProjectForgeAuthRuntimeExtensions.AuthenticatedAccount(http, store);
            if (account is null) return Results.Unauthorized();
            var credentials = store.ListPasskeys(account.Id)
                .Where(x => !x.Revoked)
                .Select(x => new
                {
                    id = Convert.ToHexString(x.CredentialId).ToLowerInvariant(),
                    x.Label,
                    x.CreatedAt,
                    x.LastUsedAt
                }).ToArray();
            return Results.Ok(credentials);
        });

        endpoints.MapPost("/api/auth/passkeys/registration/options", async Task<IResult> (
            HttpContext http, IAntiforgery csrf, ProjectAuthStore store,
            ProjectPasskeyWebAuthn verifier) =>
        {
            if (!await ProjectForgeAuthRuntimeExtensions.CsrfOk(http, csrf))
                return Results.BadRequest();
            var session = http.Request.Cookies[ProjectForgeAuthRuntimeExtensions.CookieName];
            var account = ProjectForgeAuthRuntimeExtensions.AuthenticatedAccount(http, store);
            var now = DateTimeOffset.UtcNow;
            if (account is null || session is null) return Results.Unauthorized();
            if (!store.HasRecentGoogleSignIn(account.Id, session, now))
                return Results.StatusCode(StatusCodes.Status403Forbidden);
            try
            {
                var handle = store.GetOrCreatePasskeyUserHandle(account.Id, session, now);
                // Exclude only *active* account credentials. A revoked
                // credential remains permanently non-reusable server-side,
                // but must not prevent the user from creating a replacement
                // credential on the same authenticator after Google recovery.
                var ids = store.ListPasskeys(account.Id)
                    .Where(x => !x.Revoked)
                    .Select(x => x.CredentialId).ToArray();
                var options = verifier.CreateRegistrationOptions(handle, ids);
                var token = store.BeginPasskeyCeremony(
                    "registration", options.ToJson(), account.Id, session, now);
                IssueCeremonyCookie(http, RegisterCookie, token);
                return Results.Content(options.ToJson(), "application/json");
            }
            catch (Exception e) when (e is ArgumentException or InvalidOperationException
                or SqliteException or UnauthorizedAccessException)
            {
                return Results.BadRequest();
            }
        }).RequireRateLimiting(CeremonyRatePolicy);

        endpoints.MapPost("/api/auth/passkeys/registration/complete", async Task<IResult> (
            AuthenticatorAttestationRawResponse response, HttpContext http,
            IAntiforgery csrf, ProjectAuthStore store, ProjectPasskeyWebAuthn verifier) =>
        {
            if (!await ProjectForgeAuthRuntimeExtensions.CsrfOk(http, csrf))
                return Results.BadRequest();
            var session = http.Request.Cookies[ProjectForgeAuthRuntimeExtensions.CookieName];
            var account = ProjectForgeAuthRuntimeExtensions.AuthenticatedAccount(http, store);
            var now = DateTimeOffset.UtcNow;
            var cookie = http.Request.Cookies[RegisterCookie];
            ClearCeremonyCookie(http, RegisterCookie);
            if (account is null || session is null) return Results.Unauthorized();
            if (!store.HasRecentGoogleSignIn(account.Id, session, now))
                return Results.StatusCode(StatusCodes.Status403Forbidden);
            var ceremony = store.ConsumePasskeyCeremony(
                "registration", cookie, account.Id, session, now);
            if (ceremony is null) return Results.BadRequest();
            try
            {
                var handle = store.GetOrCreatePasskeyUserHandle(account.Id, session, now);
                var verified = await verifier.VerifyRegistrationAsync(
                    response, ceremony.OptionsJson, handle,
                    store.AnyPasskeyCredentialId, http.RequestAborted);
                if (!store.HasRecentGoogleSignIn(account.Id, session, DateTimeOffset.UtcNow))
                    return Results.StatusCode(StatusCodes.Status403Forbidden);
                store.SaveVerifiedPasskey(account.Id, session, verified.Id, verified.User.Id,
                    verified.PublicKey, verified.SignCount, verified.IsBackupEligible,
                    verified.IsBackedUp, "Passkey", DateTimeOffset.UtcNow);
                return Results.NoContent();
            }
            catch (Exception e) when (e is Fido2NetLib.Fido2VerificationException
                or ArgumentException or InvalidOperationException or SqliteException
                or UnauthorizedAccessException)
            {
                return Results.BadRequest();
            }
        }).RequireRateLimiting(CeremonyRatePolicy);

        endpoints.MapPost("/api/auth/passkeys/authentication/options", async Task<IResult> (
            HttpContext http, IAntiforgery csrf, ProjectAuthStore store,
            ProjectPasskeyWebAuthn verifier) =>
        {
            if (!await ProjectForgeAuthRuntimeExtensions.CsrfOk(http, csrf))
                return Results.BadRequest();
            var options = verifier.CreateAuthenticationOptions();
            var token = store.BeginPasskeyCeremony(
                "authentication", options.ToJson(), null, null, DateTimeOffset.UtcNow);
            IssueCeremonyCookie(http, AuthenticateCookie, token);
            return Results.Content(options.ToJson(), "application/json");
        }).RequireRateLimiting(CeremonyRatePolicy);

        endpoints.MapPost("/api/auth/passkeys/authentication/complete", async Task<IResult> (
            AuthenticatorAssertionRawResponse response, HttpContext http,
            IAntiforgery csrf, ProjectAuthStore store, ProjectPasskeyWebAuthn verifier) =>
        {
            if (!await ProjectForgeAuthRuntimeExtensions.CsrfOk(http, csrf))
                return Results.BadRequest();
            var cookie = http.Request.Cookies[AuthenticateCookie];
            ClearCeremonyCookie(http, AuthenticateCookie);
            var ceremony = store.ConsumePasskeyCeremony(
                "authentication", cookie, null, null, DateTimeOffset.UtcNow);
            if (ceremony is null) return Results.Unauthorized();
            try
            {
                if (response is null) return Results.Unauthorized();
                var stored = store.FindActivePasskey(response.RawId ?? []);
                if (stored is null) return Results.Unauthorized();
                var verified = await verifier.VerifyAuthenticationAsync(
                    response, ceremony.OptionsJson, stored, http.RequestAborted);
                var result = store.FinishVerifiedPasskeyAssertion(stored.CredentialId,
                    stored.SignCount, verified.SignCount, verified.IsBackedUp,
                    DateTimeOffset.UtcNow);
                if (!result.Succeeded || result.Session is null || result.Account is null)
                    return Results.Unauthorized();
                http.Response.Cookies.Append(ProjectForgeAuthRuntimeExtensions.CookieName,
                    result.Session.Token, new CookieOptions
                    {
                        HttpOnly = true, Secure = true, SameSite = SameSiteMode.Lax,
                        Path = "/", Expires = result.Session.ExpiresAt
                    });
                return Results.Ok(new
                {
                    accountId = result.Account.Id,
                    isAdministrator = result.Account.IsAdministrator
                });
            }
            catch (Exception e) when (e is Fido2NetLib.Fido2VerificationException
                or ArgumentException or InvalidOperationException or SqliteException)
            {
                return Results.Unauthorized();
            }
        }).RequireRateLimiting(CeremonyRatePolicy);

        endpoints.MapPost("/api/auth/passkeys/revoke", async Task<IResult> (
            PasskeyRevokeRequest request, HttpContext http,
            IAntiforgery csrf, ProjectAuthStore store) =>
        {
            if (!await ProjectForgeAuthRuntimeExtensions.CsrfOk(http, csrf))
                return Results.BadRequest();
            var account = ProjectForgeAuthRuntimeExtensions.AuthenticatedAccount(http, store);
            var token = http.Request.Cookies[ProjectForgeAuthRuntimeExtensions.CookieName];
            if (account is null || token is null) return Results.Unauthorized();
            if (!store.HasRecentGoogleSignIn(account.Id, token, DateTimeOffset.UtcNow))
                return Results.StatusCode(StatusCodes.Status403Forbidden);
            try
            {
                var id = Convert.FromHexString(request.Id);
                return store.RevokeOwnPasskey(account.Id, token, id, DateTimeOffset.UtcNow)
                    ? Results.NoContent()
                    : Results.NotFound();
            }
            catch (Exception e) when (e is FormatException or ArgumentException)
            {
                return Results.BadRequest();
            }
        }).RequireRateLimiting(CeremonyRatePolicy);

        return endpoints;
    }

    private static void IssueCeremonyCookie(HttpContext http, string name, string token) =>
        http.Response.Cookies.Append(name, token, new CookieOptions
        {
            HttpOnly = true, Secure = true, SameSite = SameSiteMode.Strict,
            Path = "/", MaxAge = TimeSpan.FromMinutes(3)
        });

    private static void ClearCeremonyCookie(HttpContext http, string name) =>
        http.Response.Cookies.Delete(name, new CookieOptions
        {
            HttpOnly = true, Secure = true, SameSite = SameSiteMode.Strict, Path = "/"
        });

    internal sealed record PasskeyRevokeRequest(string Id);
}
