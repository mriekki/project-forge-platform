using System.Security.Cryptography;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace ProjectForge.Feedback.GitHub;

/// <summary>Optional hosting setup; the Project supplies its own authenticated principal resolver.</summary>
public static class GitHubFeedbackHosting
{
    private const string Prefix = "ProjectForge:Feedback:GitHub:";

    public static bool IsEnabled(IConfiguration configuration)
    {
        var value = configuration[Prefix + "Enabled"];
        if (string.IsNullOrEmpty(value))
            return false;
        if (!bool.TryParse(value, out var enabled))
            throw new InvalidOperationException("Feedback enabled setting must be true or false.");
        return enabled;
    }

    public static void AddProjectForgeGitHubFeedback(
        this IServiceCollection services, IConfiguration configuration,
        string expectedOwner, string expectedRepository, string? projectPublicOrigin)
    {
        if (!IsEnabled(configuration))
            return;
        if (services.Any(item => item.ServiceType == typeof(GitHubFeedbackClient)))
            throw new InvalidOperationException("Only one Feedback writer may be registered per process.");

        var owner = configuration[Prefix + "Owner"];
        var repository = configuration[Prefix + "Repository"];
        if (owner is null || repository is null ||
            !string.Equals(owner, expectedOwner, StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(repository, expectedRepository, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Feedback repository differs from the reviewed Project repository.");
        if (!long.TryParse(configuration[Prefix + "InstallationId"], out var installation) ||
            installation <= 0)
            throw new InvalidOperationException("Feedback GitHub App installation ID is required.");
        var appId = configuration[Prefix + "AppId"]
            ?? throw new InvalidOperationException("Feedback GitHub App ID is required.");
        var origin = ExactOrigin(projectPublicOrigin);
        var privateKeyPath = configuration[Prefix + "PrivateKeyFile"];
        var hmacPath = configuration[Prefix + "ReporterHmacKeyFile"];
        if (string.Equals(privateKeyPath, hmacPath, StringComparison.Ordinal))
            throw new InvalidOperationException("Feedback requires separate App and reporter keys.");

        byte[] reporterKey;
        try { reporterKey = Convert.FromHexString(ReadProtectedFile(hmacPath)); }
        catch (FormatException)
        {
            throw new InvalidOperationException("Feedback reporter HMAC key must be hexadecimal.");
        }
        var privateKey = ReadProtectedFile(privateKeyPath);
        try
        {
            using var rsa = RSA.Create();
            rsa.ImportFromPem(privateKey);
            _ = rsa.ExportParameters(true);
        }
        catch (Exception error) when (error is CryptographicException or ArgumentException)
        {
            throw new InvalidOperationException("Feedback GitHub App private key is invalid.", error);
        }
        var binding = new GitHubFeedbackConfig(owner, repository, installation, appId, reporterKey);
        binding.Validate();
        services.AddSingleton(binding);
        services.AddSingleton(new FeedbackOrigin(origin));
        services.AddHttpClient("ProjectForgeGitHubFeedback", client =>
            client.Timeout = TimeSpan.FromSeconds(15))
            .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            {
                AllowAutoRedirect = false,
                UseCookies = false,
                UseDefaultCredentials = false
            });
        services.AddSingleton<IGitHubIssueTokenSource>(provider =>
            new GitHubAppInstallationTokens(binding,
                provider.GetRequiredService<IHttpClientFactory>().CreateClient("ProjectForgeGitHubFeedback"),
                privateKey));
        services.AddSingleton(provider =>
            new GitHubFeedbackClient(binding,
                provider.GetRequiredService<IHttpClientFactory>().CreateClient("ProjectForgeGitHubFeedback"),
                provider.GetRequiredService<IGitHubIssueTokenSource>()));
        services.AddScoped<IGitHubFeedbackMutationGuard, FeedbackAntiforgeryGuard>();
        services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            options.AddPolicy("project-forge-feedback", http =>
                RateLimitPartition.GetFixedWindowLimiter(
                    http.Connection.RemoteIpAddress?.ToString() ?? "unknown",
                    _ => new FixedWindowRateLimiterOptions
                    {
                        PermitLimit = 30,
                        Window = TimeSpan.FromMinutes(5),
                        QueueLimit = 0,
                        AutoReplenishment = true
                    }));
        });
    }

    private static string ExactOrigin(string? value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) ||
            uri.Scheme != Uri.UriSchemeHttps || !uri.IsDefaultPort ||
            uri.UserInfo.Length != 0 || uri.AbsolutePath != "/" ||
            uri.Query.Length != 0 || uri.Fragment.Length != 0)
            throw new InvalidOperationException("Feedback requires the reviewed exact HTTPS Project origin.");
        return uri.GetLeftPart(UriPartial.Authority);
    }

    private static string ReadProtectedFile(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
            throw new InvalidOperationException("Feedback secrets require protected absolute file paths.");
        var file = new FileInfo(path);
        if (!file.Exists || file.LinkTarget is not null || file.Length is < 1 or > 32768)
            throw new InvalidOperationException("Feedback secret file is missing, linked, or outside size limits.");
        for (var directory = file.Directory; directory is not null; directory = directory.Parent)
        {
            if (directory.LinkTarget is not null)
                throw new InvalidOperationException("Feedback secret path contains a symbolic link.");
        }
        if (OperatingSystem.IsWindows())
            throw new InvalidOperationException("Feedback secret-file hosting requires a supported Unix deployment.");
        var forbidden = UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute |
            UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute;
        var mode = File.GetUnixFileMode(path);
        if ((mode & forbidden) != 0 || (mode & UnixFileMode.UserRead) == 0)
            throw new InvalidOperationException("Feedback secret file permissions are unsafe.");
        var value = File.ReadAllText(path).TrimEnd('\r', '\n');
        if (string.IsNullOrWhiteSpace(value))
            throw new InvalidOperationException("Feedback secret file is empty.");
        return value;
    }

    private sealed record FeedbackOrigin(string Value);

    private sealed class FeedbackAntiforgeryGuard(
        FeedbackOrigin expected, IAntiforgery antiforgery) : IGitHubFeedbackMutationGuard
    {
        public async ValueTask<bool> ValidateAsync(HttpContext http, CancellationToken cancellationToken)
        {
            var header = http.Request.Headers.Origin;
            if (header.Count != 1 ||
                !string.Equals(header.ToString(), expected.Value, StringComparison.OrdinalIgnoreCase))
                return false;
            try
            {
                await antiforgery.ValidateRequestAsync(http);
                return true;
            }
            catch (AntiforgeryValidationException) { return false; }
        }
    }
}
