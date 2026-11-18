using System;
using System.Net;
using System.Security.Claims;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Tokens;
using ProjectForge.Transport;

namespace ProjectForge.Auth.Runtime;

/// <summary>
/// A separate per-Project account/session implementation. Does NOT query the
/// Household Registry in interactive sign-in; Registry membership is not an
/// automatic Project account grant.
/// </summary>
public static class ProjectForgeAuthRuntimeExtensions
{
    public const string GoogleScheme = "PF-Google";
    public const string ExternalScheme = "PF-External";
    public const string CookieName = "__Host-pf-project-session";
    private const string InviteStateKey = "pf-invite-token";
    public const string CallbackPath = "/signin-pf-google";

    // A Docker secret may be mounted as a file rather than placed in an
    // environment variable (which would be visible in container inspection).
    // Never silently choose between two credentials for the same setting.
    private static string? ReadProtectedSecret(IConfiguration configuration, string key)
    {
        var inline = configuration[key];
        var secretPath = configuration[key + "File"];
        if (!string.IsNullOrWhiteSpace(inline) && !string.IsNullOrWhiteSpace(secretPath))
            throw new InvalidOperationException(
                "A provider credential cannot be configured both inline and through a secret file.");
        if (string.IsNullOrWhiteSpace(secretPath))
            return inline;
        if (!Path.IsPathFullyQualified(secretPath))
            throw new InvalidOperationException(
                "Provider secret file must have an absolute protected path.");
        var file = new FileInfo(secretPath);
        if (!file.Exists || file.LinkTarget is not null || file.Length < 12 || file.Length > 8192)
            throw new InvalidOperationException(
                "Provider secret file is missing, linked, or outside supported size bounds.");
        var value = File.ReadAllText(file.FullName).TrimEnd('\r', '\n');
        if (value.Length < 12 || value.Length > 8192 ||
            value.Contains('\r') || value.Contains('\n'))
            throw new InvalidOperationException(
                "Provider secret file must contain exactly one non-empty credential.");
        return value;
    }

    public static IServiceCollection AddProjectForgeProjectAuth(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        var path = configuration["ProjectForge:Authentication:DbPath"];
        var clientId = configuration["ProjectForge:Authentication:Google:ClientId"];
        var clientSecret = ReadProtectedSecret(configuration, "ProjectForge:Authentication:Google:ClientSecret");
        var originText = configuration["ProjectForge:Authentication:PublicOrigin"];
        var proxyText = configuration["ProjectForge:Authentication:TrustedProxyIp"];
        if (string.IsNullOrWhiteSpace(path) ||
            string.IsNullOrWhiteSpace(clientId) ||
            string.IsNullOrWhiteSpace(clientSecret) ||
            !Uri.TryCreate(originText, UriKind.Absolute, out var origin) ||
            origin.Scheme != Uri.UriSchemeHttps ||
            origin.AbsolutePath != "/" ||
            !string.IsNullOrEmpty(origin.Query) ||
            !string.IsNullOrEmpty(origin.Fragment) ||
            !string.IsNullOrEmpty(origin.UserInfo) ||
            !IPAddress.TryParse(proxyText, out var peer) ||
            IPAddress.IsLoopback(peer) || peer.Equals(IPAddress.Any) ||
            peer.Equals(IPAddress.IPv6Any))
            throw new InvalidOperationException(
                "Exact Project-owned SQLite path, OIDC credentials and reviewed public origin/proxy are required.");
        var store = new ProjectAuthStore(path);
        store.Initialize();
        services.AddSingleton(store);

        var keysPath = configuration["ProjectForge:Authentication:DataProtectionKeysPath"];
        if (string.IsNullOrWhiteSpace(keysPath) || !Path.IsPathFullyQualified(keysPath))
            throw new InvalidOperationException(
                "A persistent private per-Project OIDC key directory is required.");
        // A configured key directory must never silently redirect the OIDC
        // correlation/state key ring through a symlink. In particular,
        // chmod on a symlink target can change an unrelated directory.
        var keysDirectory = new DirectoryInfo(keysPath);
        if (keysDirectory.LinkTarget is not null)
            throw new InvalidOperationException(
                "The per-Project OIDC key directory cannot be a symbolic link.");
        Directory.CreateDirectory(keysPath);
        keysDirectory.Refresh();
        if (keysDirectory.LinkTarget is not null)
            throw new InvalidOperationException(
                "The per-Project OIDC key directory cannot be a symbolic link.");
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(keysPath,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        services.AddDataProtection()
            .PersistKeysToFileSystem(new DirectoryInfo(keysPath))
            .SetApplicationName("ProjectForge.Auth." +
                Convert.ToHexString(
                    System.Security.Cryptography.SHA256.HashData(
                        System.Text.Encoding.UTF8.GetBytes(
                            origin.GetLeftPart(UriPartial.Authority)))));

        // Resend is explicitly Project-scoped. Household infrastructure may
        // provide a verified sending domain, but never a shared API secret.
        var resendKey = ReadProtectedSecret(configuration, "ProjectForge:Authentication:Resend:ApiKey");
        var resendFrom = configuration["ProjectForge:Authentication:Resend:From"];
        if (string.IsNullOrWhiteSpace(resendKey) != string.IsNullOrWhiteSpace(resendFrom))
            throw new InvalidOperationException(
                "Per-Project Resend credential and verified sender address must be configured together.");
        if (!string.IsNullOrWhiteSpace(resendKey))
        {
            services.AddSingleton<IProjectInvitationDelivery>(
                new ResendProjectInvitationDelivery(
                    new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }),
                    resendKey, resendFrom!, origin.GetLeftPart(UriPartial.Authority)));
        }

        services.AddAntiforgery(options =>
        {
            options.HeaderName = "X-PF-CSRF";
            options.Cookie.Name = "__Host-pf-project-csrf";
            options.Cookie.Path = "/";
            options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
            options.Cookie.SameSite = SameSiteMode.Strict;
            options.Cookie.HttpOnly = true;
        });
        services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            options.AddPolicy("project-passkey-ceremonies", http =>
                RateLimitPartition.GetFixedWindowLimiter(
                    http.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                    _ => new FixedWindowRateLimiterOptions
                    {
                        PermitLimit = 12,
                        Window = TimeSpan.FromMinutes(5),
                        AutoReplenishment = true,
                        QueueLimit = 0
                    }));
            options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(
                http => RateLimitPartition.GetFixedWindowLimiter(
                    http.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                    _ => new FixedWindowRateLimiterOptions
                    {
                        PermitLimit = 60,
                        Window = TimeSpan.FromMinutes(1),
                        AutoReplenishment = true,
                        QueueLimit = 0
                    }));
        });

        // Do not replace a consuming Project's default authentication scheme.
        // The short-lived external cookie scheme is never used for persistent
        // Project authorization; OIDC ticket handling creates an opaque
        // server-authoritative session cookie and calls HandleResponse().
        services.AddAuthentication()
            .AddCookie(ExternalScheme, options =>
            {
                options.Cookie.Name = "__Host-pf-external";
                options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
                options.Cookie.HttpOnly = true;
                options.Cookie.SameSite = SameSiteMode.Lax;
                options.ExpireTimeSpan = TimeSpan.FromMinutes(10);
                options.SlidingExpiration = false;
            })
            .AddOpenIdConnect(GoogleScheme, options =>
            {
                options.SignInScheme = ExternalScheme;
                options.Authority = "https://accounts.google.com";
                options.ClientId = clientId;
                options.ClientSecret = clientSecret;
                options.ResponseType = "code";
                options.UsePkce = true;
                options.SaveTokens = false;
                options.MapInboundClaims = false;
                options.GetClaimsFromUserInfoEndpoint = false;
                options.CallbackPath = CallbackPath;
                options.Scope.Clear();
                options.Scope.Add("openid");
                options.Scope.Add("email");
                options.TokenValidationParameters = new TokenValidationParameters
                {
                    ValidateIssuer = true,
                    ValidIssuer = "https://accounts.google.com",
                    ValidateAudience = true,
                    ValidAudience = clientId,
                    ValidateIssuerSigningKey = true,
                    NameClaimType = "email"
                };
                options.Events = new OpenIdConnectEvents
                {
                    OnMessageReceived = context =>
                    {
                        if (!TrustedOrigin(context.HttpContext, origin))
                            context.Fail("Public origin is not trusted.");
                        return Task.CompletedTask;
                    },
                    OnTokenValidated = context =>
                    {
                        var issuer = context.SecurityToken?.Issuer;
                        var subject = ExactlyOne(context.Principal, "sub");
                        var email = ExactlyOne(context.Principal, "email");
                        var verified = ExactlyOne(context.Principal, "email_verified");
                        if (issuer != "https://accounts.google.com" ||
                            string.IsNullOrWhiteSpace(subject) ||
                            subject.Length > 512 ||
                            string.IsNullOrWhiteSpace(email) ||
                            !string.Equals(verified, "true", StringComparison.OrdinalIgnoreCase) ||
                            context.Principal?.Identity is not ClaimsIdentity identity)
                        {
                            context.Fail("Verified Google claims required.");
                            return Task.CompletedTask;
                        }
                        identity.AddClaim(new Claim("pf_verified_google_issuer", issuer));
                        return Task.CompletedTask;
                    },
                    OnTicketReceived = context =>
                    {
                        var store = context.HttpContext.RequestServices
                            .GetRequiredService<ProjectAuthStore>();
                        var claims = context.Principal;
                        var issuer = ExactlyOne(claims, "pf_verified_google_issuer");
                        var subject = ExactlyOne(claims, "sub");
                        var email = ExactlyOne(claims, "email");
                        var verified = ExactlyOne(claims, "email_verified");
                        if (!TrustedOrigin(context.HttpContext, origin) ||
                            issuer != "https://accounts.google.com" ||
                            string.IsNullOrWhiteSpace(subject) ||
                            string.IsNullOrWhiteSpace(email) ||
                            !string.Equals(verified, "true", StringComparison.OrdinalIgnoreCase))
                        {
                            context.HandleResponse();
                            context.Response.Redirect("/?auth=unavailable");
                            return Task.CompletedTask;
                        }
                        var google = new VerifiedGoogleIdentity(
                            issuer, subject, email, EmailVerified: true);
                        var time = DateTimeOffset.UtcNow;
                        string? invitation = null;
                        context.Properties?.Items.TryGetValue(InviteStateKey, out invitation);
                        var result = string.IsNullOrWhiteSpace(invitation)
                            ? store.SignIn(google, time)
                            : store.RedeemInvitation(google, invitation, time);

                        // Same generic response for no account, bad invitation,
                        // disabled account and other unapproved principals.
                        if (!result.Succeeded || result.Session is null)
                        {
                            context.HandleResponse();
                            context.Response.Redirect("/?auth=unavailable");
                            return Task.CompletedTask;
                        }
                        // Only the verified Google OIDC callback can create
                        // recent-Google evidence for passkey enrollment/revocation.
                        // Passkey sign-in never creates this step-up authorization.
                        if (context.HttpContext.RequestServices
                            .GetService<ProjectPasskeyWebAuthn>() is not null)
                            store.RecordRecentGoogleSignIn(result.Session.Token, time);
                        context.Response.Cookies.Append(
                            CookieName, result.Session.Token,
                            new CookieOptions
                            {
                                HttpOnly = true, Secure = true,
                                SameSite = SameSiteMode.Lax,
                                Path = "/", Expires = result.Session.ExpiresAt
                            });
                        context.HandleResponse();
                        context.Response.Redirect("/");
                        return Task.CompletedTask;
                    },
                    OnRemoteFailure = context =>
                    {
                        context.HandleResponse();
                        context.Response.Redirect("/?auth=unavailable");
                        return Task.CompletedTask;
                    },
                    OnRedirectToIdentityProvider = context =>
                    {
                        if (!TrustedOrigin(context.HttpContext, origin))
                        {
                            context.HandleResponse();
                            context.Response.StatusCode = StatusCodes.Status400BadRequest;
                        }
                        return Task.CompletedTask;
                    }
                };
            });

        // Passkeys are a separate, explicit capability. Neither Google-only
        // Projects nor existing Production deployments auto-enable this path.
        if (configuration.GetValue<bool>("ProjectForge:Authentication:Passkeys:Enabled"))
        {
            var configuredRpId = configuration["ProjectForge:Authentication:Passkeys:RelyingPartyId"];
            if (!string.Equals(configuredRpId, origin.IdnHost, StringComparison.Ordinal))
                throw new InvalidOperationException("Passkeys require the exact Project HTTPS host as RP ID.");
            var name = configuration["ProjectForge:Authentication:Passkeys:DisplayName"];
            var verifier = new ProjectPasskeyWebAuthn(
                origin.GetLeftPart(UriPartial.Authority),
                string.IsNullOrWhiteSpace(name) ? "Project Forge application" : name);
            store.InitializePasskeySchema();
            store.InitializePasskeyStepUpSchema();
            services.AddSingleton(verifier);
        }
        services.AddAuthorization();
        return services;
    }

    public static IApplicationBuilder UseProjectForgeAuthPublicOrigin(
        this IApplicationBuilder app, IConfiguration configuration)
    {
        var expectedText = configuration["ProjectForge:Authentication:PublicOrigin"];
        if (!Uri.TryCreate(expectedText, UriKind.Absolute, out var expected) ||
            expected.Scheme != Uri.UriSchemeHttps)
            throw new InvalidOperationException("Exact configured HTTPS public origin required.");
        var reviewedPeerText = configuration["ProjectForge:Authentication:TrustedProxyIp"];
        if (!IPAddress.TryParse(reviewedPeerText, out var reviewedPeer) ||
            IPAddress.IsLoopback(reviewedPeer) ||
            reviewedPeer.Equals(IPAddress.Any) || reviewedPeer.Equals(IPAddress.IPv6Any))
            throw new InvalidOperationException("An exact reviewed transport peer is required.");
        // Validate raw Caddy transport and forwarded headers before any
        // auth processing. Never pre-run generic ForwardedHeaders here.
        app.Use(async (context, next) =>
        {
            if (!StrictPublicOriginTransport.TryApply(context, reviewedPeer, expected))
            {
                context.Response.StatusCode = StatusCodes.Status403Forbidden;
                return;
            }
            // WebAuthn JSON envelopes contain bounded keys and authenticator
            // data, never file uploads. Kestrel's general 30 MiB body limit
            // would allow expensive malformed credential payloads to reach
            // model binding. Restrict *only* passkey POSTs, before reading
            // request bodies; keep other Project API limits unchanged.
            const long passkeyMaxRequestBody = 64 * 1024;
            if (HttpMethods.IsPost(context.Request.Method) &&
                context.Request.Path.StartsWithSegments("/api/auth/passkeys",
                    StringComparison.Ordinal))
            {
                if (context.Request.ContentLength > passkeyMaxRequestBody)
                {
                    context.Response.StatusCode = StatusCodes.Status413PayloadTooLarge;
                    return;
                }
                var sizeFeature = context.Features.Get<IHttpMaxRequestBodySizeFeature>();
                if (sizeFeature is { IsReadOnly: false })
                    sizeFeature.MaxRequestBodySize = passkeyMaxRequestBody;
            }
            context.Response.Headers.CacheControl = "no-store";
            context.Response.Headers["X-Content-Type-Options"] = "nosniff";
            context.Response.Headers["Referrer-Policy"] = "no-referrer";
            context.Response.Headers["Strict-Transport-Security"] = "max-age=31536000";
            await next();
        });
        return app;
    }

    public static IEndpointRouteBuilder MapProjectForgeAuth(
        this IEndpointRouteBuilder endpoints)
    {
        // Liveness only. The application's strict origin/physical-peer guard
        // runs BEFORE endpoint routing, so even health cannot be reached by
        // a direct/forged host request. Do not use this as restore readiness.
        endpoints.MapGet("/health", (ProjectAuthStore db) =>
            db.IsReadableAndCurrent()
                ? Results.Ok(new { status = "healthy" })
                : Results.StatusCode(StatusCodes.Status503ServiceUnavailable));

        endpoints.MapGet("/api/auth/google", (HttpContext http) =>
        {
            if (!http.Request.IsHttps) return Results.BadRequest();
            return Results.Challenge(new AuthenticationProperties
            {
                RedirectUri = "/"
            }, [GoogleScheme]);
        });

        endpoints.MapGet("/api/auth/csrf", (HttpContext http, IAntiforgery antiforgery) =>
        {
            var tokens = antiforgery.GetAndStoreTokens(http);
            return Results.Ok(new { requestToken = tokens.RequestToken });
        });

        // Form POST is an actual browser navigation; invitation token lives
        // inside DataProtection-protected OIDC state rather than a query URL.
        endpoints.MapPost("/api/auth/google/invite", async Task<IResult> (
            HttpContext http, IAntiforgery antiforgery) =>
        {
            if (!await CsrfOk(http, antiforgery) ||
                !http.Request.HasFormContentType)
                return Results.BadRequest();
            var values = await http.Request.ReadFormAsync();
            var token = values["invitationToken"].ToString();
            if (token.Length != 64 ||
                !System.Text.RegularExpressions.Regex.IsMatch(
                    token, "^[0-9a-f]{64}$"))
                return Results.BadRequest();
            var props = new AuthenticationProperties { RedirectUri = "/" };
            props.Items[InviteStateKey] = token;
            return Results.Challenge(props, [GoogleScheme]);
        });

        endpoints.MapGet("/api/auth/me", (HttpContext http, ProjectAuthStore db) =>
        {
            var account = AuthenticatedAccount(http, db);
            return account is null
                ? Results.Unauthorized()
                : Results.Ok(new { accountId = account.Id, isAdministrator = account.IsAdministrator });
        });

        endpoints.MapPost("/api/auth/logout", async Task<IResult> (
            HttpContext http, IAntiforgery antiforgery, ProjectAuthStore db) =>
        {
            if (!await CsrfOk(http, antiforgery)) return Results.BadRequest();
            var token = http.Request.Cookies[CookieName];
            if (token is not null) db.RevokeSession(token, DateTimeOffset.UtcNow);
            http.Response.Cookies.Delete(CookieName, new CookieOptions
            {
                Path = "/", Secure = true, HttpOnly = true, SameSite = SameSiteMode.Lax
            });
            return Results.NoContent();
        });

        endpoints.MapPost("/api/auth/invitations", async Task<IResult> (
            InvitationRequest input, HttpContext http, IAntiforgery antiforgery,
            ProjectAuthStore db) =>
        {
            if (!await CsrfOk(http, antiforgery)) return Results.BadRequest();
            var account = AuthenticatedAccount(http, db);
            if (account is not { IsAdministrator: true }) return Results.StatusCode(StatusCodes.Status403Forbidden);
            try
            {
                var invite = db.CreateInvitation(
                    account.Id, input.RecipientEmail, DateTimeOffset.UtcNow);
                var delivery = http.RequestServices.GetService<IProjectInvitationDelivery>();
                if (delivery is not null)
                {
                    var delivered = await delivery.SendAsync(
                        input.RecipientEmail, invite.Token, invite.ExpiresAt,
                        http.RequestAborted);
                    // Never send the invitation token back to the browser
                    // when configured for secure Project-owned email delivery.
                    return delivered ? Results.NoContent() : Results.StatusCode(
                        StatusCodes.Status502BadGateway);
                }
                // Manual operator delivery remains available without a
                // Resend credential; the token is shown only once to admin.
                return Results.Ok(new { token = invite.Token, expiresAt = invite.ExpiresAt });
            }
            catch (ArgumentException) { return Results.BadRequest(); }
            catch (InvalidOperationException)
            {
                return Results.StatusCode(StatusCodes.Status429TooManyRequests);
            }
        });

        endpoints.MapPost("/api/auth/accounts/{accountId}/disable",
            async Task<IResult> (string accountId, HttpContext http,
                IAntiforgery antiforgery, ProjectAuthStore db) =>
            {
                if (!await CsrfOk(http, antiforgery)) return Results.BadRequest();
                var token = http.Request.Cookies[CookieName];
                if (token is null) return Results.Unauthorized();
                try
                {
                    return db.DisableAccount(token, accountId, DateTimeOffset.UtcNow)
                        ? Results.NoContent() : Results.NotFound();
                }
                // The Project Auth API deliberately has no default ASP.NET
                // authentication scheme: application sessions are validated
                // against SQLite rather than forwarded to cookie auth.
                // Results.Forbid() would throw when no DefaultForbidScheme
                // exists, turning a denied member into an HTTP 500.
                catch (UnauthorizedAccessException)
                {
                    return Results.StatusCode(StatusCodes.Status403Forbidden);
                }
            });
        if (endpoints.ServiceProvider.GetService<ProjectPasskeyWebAuthn>() is not null)
            endpoints.MapProjectForgePasskeys();
        return endpoints;
    }

    public static bool IsReviewedTransportPeer(IPAddress? observed, IPAddress reviewed) =>
        observed is not null && observed.Equals(reviewed);

    private static string? ExactlyOne(ClaimsPrincipal? principal, string name)
    {
        var claims = principal?.FindAll(name).Take(2).ToArray();
        return claims?.Length == 1 ? claims[0].Value : null;
    }
    private static bool TrustedOrigin(HttpContext http, Uri origin) =>
        http.Request.IsHttps &&
        string.Equals(http.Request.Host.Host, origin.Host, StringComparison.OrdinalIgnoreCase) &&
        http.Request.Host.Port == (origin.IsDefaultPort ? null : origin.Port);

    internal static ProjectAccount? AuthenticatedAccount(HttpContext http, ProjectAuthStore db)
    {
        var token = http.Request.Cookies[CookieName];
        return token is null ? null : db.GetSession(token, DateTimeOffset.UtcNow);
    }
    internal static async Task<bool> CsrfOk(HttpContext http, IAntiforgery antiforgery)
    {
        try
        {
            await antiforgery.ValidateRequestAsync(http);
            return true;
        }
        catch (AntiforgeryValidationException) { return false; }
    }
    public sealed record InvitationRequest(string RecipientEmail);
}
