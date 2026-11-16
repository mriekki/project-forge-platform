using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;

namespace ProjectForge.Feedback.GitHub;

/// <summary>
/// Project-owned authentication result. This package never authenticates the
/// browser, looks up Auth Kit user tables, or inherits household roles.
/// </summary>
public sealed record GitHubFeedbackPrincipal(
    string AccountId, bool CanSubmit, bool CanAdminister);

public interface IGitHubFeedbackPrincipalResolver
{
    ValueTask<GitHubFeedbackPrincipal?> ResolveAsync(
        HttpContext http, CancellationToken cancellationToken);
}

/// <summary>Host-owned current CSRF and exact-origin validation, fail-closed.</summary>
public interface IGitHubFeedbackMutationGuard
{
    ValueTask<bool> ValidateAsync(HttpContext http, CancellationToken cancellationToken);
}

public static class GitHubFeedbackEndpoints
{
    private const int MaxSubmitBytes = 12 * 1024;

    /// <summary>
    /// Only these four same-origin paths are mapped; no generic upstream proxy.
    /// Register this route group only when its server-owned GitHub App config
    /// and authenticated identity/antiforgery adapters are fully configured.
    /// </summary>
    public static IEndpointRouteBuilder MapProjectForgeGitHubFeedback(
        this IEndpointRouteBuilder endpoints, string prefix = "/feedback-api")
    {
        if (prefix != "/feedback-api")
            throw new ArgumentException("Reviewed feedback route prefix cannot be changed");
        endpoints.MapGet(prefix + "/v1/feedback/mine", Mine).RequireRateLimiting("project-forge-feedback");
        endpoints.MapPost(prefix + "/v1/feedback", Submit).RequireRateLimiting("project-forge-feedback");
        endpoints.MapGet(prefix + "/v1/admin/feedback", AdminInbox).RequireRateLimiting("project-forge-feedback");
        endpoints.MapPost(prefix + "/v1/admin/feedback/{issueNumber:int}/triage", Triage).RequireRateLimiting("project-forge-feedback");
        return endpoints;
    }

    private static async Task<IResult> Mine(
        HttpContext http, IGitHubFeedbackPrincipalResolver resolver,
        GitHubFeedbackClient feedback, CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "private, no-store";
        var user = await resolver.ResolveAsync(http, ct);
        if (user is not { CanSubmit: true })
            return Results.Unauthorized();
        try { return Results.Json(await feedback.ListMineAsync(user.AccountId, ct)); }
        catch (FeedbackProviderException ex) { return Error(ex); }
    }

    private static async Task<IResult> Submit(
        HttpContext http, IGitHubFeedbackPrincipalResolver resolver,
        IGitHubFeedbackMutationGuard guard, GitHubFeedbackClient feedback,
        CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "private, no-store";
        var user = await resolver.ResolveAsync(http, ct);
        if (user is not { CanSubmit: true })
            return Results.Unauthorized();
        if (!await guard.ValidateAsync(http, ct))
            return Results.StatusCode(StatusCodes.Status403Forbidden);
        if (http.Request.ContentLength > MaxSubmitBytes ||
            http.Request.ContentType?.StartsWith("application/json",
                StringComparison.OrdinalIgnoreCase) != true)
            return Results.BadRequest(new { error = "invalid_feedback_request" });
        var key = http.Request.Headers["Idempotency-Key"].ToString();
        try
        {
            using var memory = new MemoryStream();
            var buffer = new byte[2048];
            int count;
            while ((count = await http.Request.Body.ReadAsync(buffer, ct)) > 0)
            {
                if (memory.Length + count > MaxSubmitBytes)
                    return Results.StatusCode(StatusCodes.Status413PayloadTooLarge);
                memory.Write(buffer, 0, count);
            }
            var value = JsonSerializer.Deserialize<FeedbackInput>(memory.ToArray(),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            if (value is null)
                return Results.BadRequest(new { error = "invalid_feedback_request" });
            var created = await feedback.CreateAsync(user.AccountId,
                new FeedbackDraft(value.Category ?? "", value.Title ?? "",
                    value.Description ?? "", key), ct);
            // The browser can display Issue number/status even if the private
            // GitHub URL is inaccessible to the reporter's GitHub account.
            return Results.Json(created, statusCode: StatusCodes.Status201Created);
        }
        catch (JsonException) { return Results.BadRequest(new { error = "invalid_feedback_request" }); }
        catch (FeedbackProviderException ex) { return Error(ex); }
    }

    private static async Task<IResult> AdminInbox(
        HttpContext http, IGitHubFeedbackPrincipalResolver resolver,
        GitHubFeedbackClient feedback, CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "private, no-store";
        var user = await resolver.ResolveAsync(http, ct);
        if (user is not { CanSubmit: true, CanAdminister: true })
            return Results.StatusCode(StatusCodes.Status403Forbidden);
        try { return Results.Json(await feedback.ListAdminAsync(ct)); }
        catch (FeedbackProviderException ex) { return Error(ex); }
    }

    private static async Task<IResult> Triage(
        int issueNumber, HttpContext http, IGitHubFeedbackPrincipalResolver resolver,
        IGitHubFeedbackMutationGuard guard, GitHubFeedbackClient feedback,
        CancellationToken ct)
    {
        http.Response.Headers.CacheControl = "private, no-store";
        var user = await resolver.ResolveAsync(http, ct);
        if (user is not { CanSubmit: true, CanAdminister: true })
            return Results.StatusCode(StatusCodes.Status403Forbidden);
        if (!await guard.ValidateAsync(http, ct))
            return Results.StatusCode(StatusCodes.Status403Forbidden);
        if (http.Request.ContentLength > 2048 ||
            http.Request.ContentType?.StartsWith("application/json",
                StringComparison.OrdinalIgnoreCase) != true)
            return Results.BadRequest(new { error = "invalid_triage_request" });
        try
        {
            using var memory = new MemoryStream();
            var buffer = new byte[512];
            int count;
            while ((count = await http.Request.Body.ReadAsync(buffer, ct)) > 0)
            {
                if (memory.Length + count > 2048)
                    return Results.StatusCode(StatusCodes.Status413PayloadTooLarge);
                memory.Write(buffer, 0, count);
            }
            var request = JsonSerializer.Deserialize<TriageInput>(memory.ToArray(),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
            var updated = await feedback.SetTriageStatusAsync(
                issueNumber, request?.Status ?? "", ct);
            return Results.Json(updated);
        }
        catch (JsonException) { return Results.BadRequest(new { error = "invalid_triage_request" }); }
        catch (FeedbackProviderException ex) { return Error(ex); }
    }

    private static IResult Error(FeedbackProviderException ex)
    {
        var code = ex.Kind switch
        {
            FeedbackErrorKind.InvalidInput => StatusCodes.Status400BadRequest,
            FeedbackErrorKind.Conflict => StatusCodes.Status409Conflict,
            FeedbackErrorKind.InvalidProviderResponse => StatusCodes.Status502BadGateway,
            _ => StatusCodes.Status503ServiceUnavailable
        };
        var id = ex.Kind switch
        {
            FeedbackErrorKind.OutcomeUnknown => "submission_outcome_unknown",
            FeedbackErrorKind.IncompleteRead => "feedback_read_incomplete",
            FeedbackErrorKind.Conflict => "submission_key_conflict",
            FeedbackErrorKind.InvalidInput => "invalid_feedback_request",
            _ => "github_feedback_unavailable"
        };
        // Deliberately do not expose provider bodies, account IDs, tokens or
        // trace details in the browser response.
        return Results.Json(new { error = id }, statusCode: code);
    }

    private sealed record FeedbackInput(string? Category, string? Title, string? Description);
    private sealed record TriageInput(string? Status);
}
