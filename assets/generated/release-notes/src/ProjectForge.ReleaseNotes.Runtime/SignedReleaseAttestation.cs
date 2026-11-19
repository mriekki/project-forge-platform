using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ProjectForge.ReleaseNotes.Runtime;

/// <summary>
/// Current release facts obtained from an independent, trusted host-owned
/// observation. These values MUST NOT be copied from a signed envelope,
/// browser parameters, request headers or application-writable files.
/// </summary>
public sealed record VerifiedHostReleaseFacts(
    string OwnerRepo, string AppSlug, string Environment,
    string SourceCommit, string RegistryImage, string RuntimeImageId,
    string SpecSha256, string ReleaseVersion,
    long DeploymentGeneration, string ManifestSha256);

/// <summary>
/// Verifies the Deployment Kit's canonical ECDSA P-256 SHA-256 release envelope.
/// This is a consumer-side signature check, NOT the current-host observer or
/// Production deployment verifier. Both are required to activate What's New.
/// </summary>
public static class SignedReleaseAttestation
{
    private static readonly HashSet<string> EnvelopeFields = [
        "schemaVersion", "algorithm", "keyId", "release", "signature"
    ];
    private static readonly HashSet<string> ReleaseFields = [
        "schemaVersion", "kind", "idempotencyKey", "ownerRepo", "appSlug",
        "environment", "deploymentState", "sourceCommit", "registryImage",
        "runtimeImageId", "specSha256", "verifiedAtUtc", "evidenceDigest",
        "manifestSha256", "releaseVersion", "deploymentGeneration"
    ];
    private static readonly Regex Hash = new("^[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex SourceCommit = new("^[0-9a-f]{40}$", RegexOptions.CultureInvariant);
    private static readonly Regex Image = new("^sha256:[0-9a-f]{64}$", RegexOptions.CultureInvariant);
    private static readonly Regex Version = new(@"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$", RegexOptions.CultureInvariant);

    public static bool TryVerify(
        ReadOnlySpan<byte> envelopeBytes, string pinnedPublicKeyPem,
        string pinnedKeyId, VerifiedHostReleaseFacts observed,
        DateTimeOffset nowUtc, out DateTimeOffset verifiedAtUtc)
    {
        verifiedAtUtc = default;
        if (envelopeBytes.IsEmpty || envelopeBytes.Length > 16_384 ||
            string.IsNullOrWhiteSpace(pinnedPublicKeyPem) || pinnedPublicKeyPem.Length > 4096 ||
            string.IsNullOrWhiteSpace(pinnedKeyId) || pinnedKeyId.Length > 128 ||
            observed is null || nowUtc.Offset != TimeSpan.Zero)
            return false;

        try
        {
            using var doc = JsonDocument.Parse(envelopeBytes.ToArray(),
                new JsonDocumentOptions {
                    MaxDepth = 10,
                    CommentHandling = JsonCommentHandling.Disallow,
                    AllowTrailingCommas = false
                });
            var envelope = doc.RootElement;
            if (!ExactObject(envelope, EnvelopeFields) ||
                Number(envelope, "schemaVersion") != 1 ||
                Text(envelope, "algorithm") != "ecdsa-p256-sha256-der" ||
                Text(envelope, "keyId") != pinnedKeyId)
                return false;

            var body = envelope.GetProperty("release");
            if (!ExactObject(body, ReleaseFields) ||
                Number(body, "schemaVersion") != 1 ||
                Text(body, "kind") != "verified-application-release" ||
                Text(body, "deploymentState") != "verified-deployed")
                return false;

            string source = Text(body, "sourceCommit");
            string image = Text(body, "runtimeImageId");
            string digest = Text(body, "manifestSha256");
            string version = Text(body, "releaseVersion");
            string specSha = Text(body, "specSha256");
            string registryImage = Text(body, "registryImage");
            string evidence = Text(body, "evidenceDigest");
            if (!SourceCommit.IsMatch(source) || !Image.IsMatch(image) ||
                !Hash.IsMatch(digest) || !Hash.IsMatch(specSha) ||
                !Image.IsMatch(evidence) || !Version.IsMatch(version) ||
                !registryImage.Contains("@sha256:", StringComparison.Ordinal) ||
                !Hash.IsMatch(registryImage.Split("@sha256:")[^1]))
                return false;

            long generation = Long(body, "deploymentGeneration");
            if (generation < 1 ||
                Text(body, "ownerRepo") != observed.OwnerRepo ||
                Text(body, "appSlug") != observed.AppSlug ||
                Text(body, "environment") != "production" ||
                observed.Environment != "production" ||
                source != observed.SourceCommit ||
                registryImage != observed.RegistryImage ||
                image != observed.RuntimeImageId ||
                specSha != observed.SpecSha256 ||
                version != observed.ReleaseVersion ||
                generation != observed.DeploymentGeneration ||
                digest != observed.ManifestSha256)
                return false;

            string date = Text(body, "verifiedAtUtc");
            if (!DateTimeOffset.TryParseExact(date, "yyyy-MM-dd'T'HH:mm:ss'Z'",
                CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal,
                out var verified) || verified.Offset != TimeSpan.Zero ||
                verified > nowUtc)
                return false;

            string signatureText = Text(envelope, "signature");
            if (signatureText.Length is < 1 or > 256 ||
                signatureText.Any(c => !char.IsAsciiLetterOrDigit(c) && c is not '-' and not '_') ||
                signatureText.Length % 4 == 1)
                return false;
            byte[] signature = Convert.FromBase64String(
                signatureText.Replace('-', '+').Replace('_', '/') +
                new string('=', (4 - signatureText.Length % 4) % 4));

            using var signingKey = ECDsa.Create();
            signingKey.ImportFromPem(pinnedPublicKeyPem);
            if (signingKey.ExportParameters(false).Curve.Oid.Value !=
                "1.2.840.10045.3.1.7")
                return false;
            var canonical = CanonicalJson(body);
            if (!signingKey.VerifyData(canonical, signature,
                HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence))
                return false;

            verifiedAtUtc = verified;
            return true;
        }
        catch (Exception error) when (
            error is JsonException or InvalidOperationException or
            FormatException or CryptographicException or ArgumentException or
            OverflowException)
        {
            return false;
        }
    }

    private static byte[] CanonicalJson(JsonElement root)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        }))
        {
            WriteCanonical(root, writer);
            writer.Flush();
        }
        return stream.ToArray();
    }

    private static void WriteCanonical(JsonElement element, Utf8JsonWriter writer)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (var p in element.EnumerateObject().OrderBy(
                    p => p.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(p.Name);
                    WriteCanonical(p.Value, writer);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (var value in element.EnumerateArray())
                    WriteCanonical(value, writer);
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText());
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new JsonException("Unsupported signed release JSON type.");
        }
    }

    private static bool ExactObject(JsonElement element, HashSet<string> fields)
    {
        if (element.ValueKind != JsonValueKind.Object)
            return false;
        var names = element.EnumerateObject().Select(p => p.Name).ToArray();
        return names.Length == fields.Count &&
            names.Distinct(StringComparer.Ordinal).Count() == fields.Count &&
            names.All(fields.Contains);
    }

    private static string Text(JsonElement e, string name)
    {
        var value = e.GetProperty(name);
        if (value.ValueKind != JsonValueKind.String)
            throw new JsonException("Unexpected signed release text.");
        return value.GetString() ?? throw new JsonException("Missing release text.");
    }

    private static int Number(JsonElement e, string name)
    {
        var value = e.GetProperty(name);
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out int x))
            throw new JsonException("Unexpected signed release schema.");
        return x;
    }

    private static long Long(JsonElement e, string name)
    {
        var value = e.GetProperty(name);
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out long x))
            throw new JsonException("Unexpected signed release generation.");
        return x;
    }
}
