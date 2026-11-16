using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ProjectForge.Feedback.GitHub;

/// <summary>
/// Creates a short-lived GitHub App installation token for precisely one
/// server-configured repository with Issues read/write permissions.
/// The caller must register an HTTP client with redirects and cookies disabled.
/// </summary>
public sealed class GitHubAppInstallationTokens : IGitHubIssueTokenSource
{
    private readonly GitHubFeedbackConfig _config;
    private readonly HttpClient _client;
    private readonly string _privateKeyPem;

    public GitHubAppInstallationTokens(
        GitHubFeedbackConfig config, HttpClient client, string privateKeyPem)
    {
        config.Validate();
        if (string.IsNullOrWhiteSpace(privateKeyPem))
            throw new ArgumentException("GitHub App private key is required");
        _config = config;
        _client = client;
        _privateKeyPem = privateKeyPem;
    }

    public async Task<string> GetInstallationTokenAsync(bool write, CancellationToken cancellationToken)
    {
        string jwt;
        try
        {
            using var key = RSA.Create();
            key.ImportFromPem(_privateKeyPem);
            var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string header = Encode(JsonSerializer.SerializeToUtf8Bytes(new
            {
                alg = "RS256", typ = "JWT"
            }));
            string claims = Encode(JsonSerializer.SerializeToUtf8Bytes(new
            {
                iat = now - 30, exp = now + 540, iss = long.Parse(_config.AppId)
            }));
            string signingInput = header + "." + claims;
            jwt = signingInput + "." + Encode(key.SignData(
                Encoding.ASCII.GetBytes(signingInput),
                HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1));
        }
        catch (Exception ex) when (ex is CryptographicException or ArgumentException)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                "GitHub App signing credential is invalid");
        }

        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            new Uri($"https://api.github.com/app/installations/{_config.InstallationId}/access_tokens"))
        {
            Content = new StringContent(
                JsonSerializer.Serialize(new
                {
                    repositories = new[] { _config.Repository },
                    permissions = new { issues = write ? "write" : "read" }
                }), Encoding.UTF8, "application/json")
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", jwt);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        request.Headers.UserAgent.ParseAdd("ProjectForgeFeedback/1.0");
        request.Headers.TryAddWithoutValidation("X-GitHub-Api-Version", "2022-11-28");

        try
        {
            using var response = await _client.SendAsync(
                request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (response.StatusCode != HttpStatusCode.Created)
                throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                    "GitHub installation token request failed");

            await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
            using var buffer = new MemoryStream();
            byte[] chunk = new byte[4096];
            int n;
            while ((n = await stream.ReadAsync(chunk, cancellationToken)) != 0)
            {
                if (buffer.Length + n > 16 * 1024)
                    throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                        "GitHub installation token response too large");
                buffer.Write(chunk, 0, n);
            }

            using var doc = JsonDocument.Parse(buffer.ToArray());
            if (!doc.RootElement.TryGetProperty("token", out var value) ||
                value.ValueKind != JsonValueKind.String ||
                value.GetString() is not { Length: >= 20 and <= 4096 } token)
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub returned an invalid installation token");
            // Check the provider's actual grant rather than assuming the
            // token endpoint honored the requested restriction.
            var root = doc.RootElement;
            if (!root.TryGetProperty("permissions", out var permissions) ||
                permissions.ValueKind != JsonValueKind.Object ||
                !permissions.TryGetProperty("issues", out var issueGrant) ||
                issueGrant.ValueKind != JsonValueKind.String ||
                issueGrant.GetString() != (write ? "write" : "read") ||
                permissions.EnumerateObject().Any(p =>
                    p.Name is not ("issues" or "metadata") ||
                    (p.Name == "metadata" &&
                     (p.Value.ValueKind != JsonValueKind.String ||
                      p.Value.GetString() != "read"))))
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub installation token permissions do not match the request");

            if (!root.TryGetProperty("repository_selection", out var selection) ||
                selection.ValueKind != JsonValueKind.String ||
                selection.GetString() != "selected" ||
                !root.TryGetProperty("repositories", out var repositories) ||
                repositories.ValueKind != JsonValueKind.Array ||
                repositories.GetArrayLength() != 1 ||
                repositories[0].ValueKind != JsonValueKind.Object ||
                !repositories[0].TryGetProperty("full_name", out var fullName) ||
                fullName.ValueKind != JsonValueKind.String ||
                !string.Equals(fullName.GetString(),
                    _config.Owner + "/" + _config.Repository,
                    StringComparison.OrdinalIgnoreCase))
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub installation token repository scope is invalid");

            if (!root.TryGetProperty("expires_at", out var expires) ||
                expires.ValueKind != JsonValueKind.String ||
                !DateTimeOffset.TryParse(expires.GetString(), out var expiration) ||
                expiration <= DateTimeOffset.UtcNow)
                throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                    "GitHub installation token expiration is invalid");
            return token;
        }
        catch (HttpRequestException)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                "GitHub installation token service is unavailable");
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.ProviderUnavailable,
                "GitHub installation token request timed out");
        }
        catch (JsonException)
        {
            throw new FeedbackProviderException(FeedbackErrorKind.InvalidProviderResponse,
                "GitHub installation token response is invalid");
        }
    }

    private static string Encode(byte[] bytes) =>
        Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}
