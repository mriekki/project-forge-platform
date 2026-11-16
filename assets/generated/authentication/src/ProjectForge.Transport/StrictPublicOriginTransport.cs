using System;
using System.Linq;
using System.Net;
using Microsoft.AspNetCore.Http;

namespace ProjectForge.Transport;

/// <summary>
/// Exact Caddy-to-application ingress boundary, modeled on the proven PWA
/// ProductionOriginTransport contract. Do not use alongside generic forwarded
/// header processing: the raw physical peer and single forwarded headers
/// must be checked BEFORE any middleware rewrites them.
/// </summary>
public static class StrictPublicOriginTransport
{
    public static bool TryApply(HttpContext context, IPAddress reviewedCaddy, Uri origin)
    {
        var request = context.Request;
        var physicalPeer = Normalize(context.Connection.RemoteIpAddress);
        if (physicalPeer is null || !physicalPeer.Equals(Normalize(reviewedCaddy)) ||
            origin.Scheme != Uri.UriSchemeHttps ||
            request.Host.Value != origin.Authority ||
            !ExactHeader(request, "X-Forwarded-Host", origin.Authority) ||
            !ExactHeader(request, "X-Forwarded-Proto", "https") ||
            !ReadIp(request, "X-Forwarded-For", out var client) ||
            !ReadIp(request, "X-Real-IP", out var real) ||
            !client.Equals(real) ||
            request.Headers.Keys.Any(k => IsForwardingHeader(k) && !IsCanonicalHeader(k)))
            return false;

        request.Scheme = Uri.UriSchemeHttps;
        request.Host = origin.IsDefaultPort
            ? new HostString(origin.Host)
            : new HostString(origin.Host, origin.Port);
        context.Connection.RemoteIpAddress = client;
        StripForwardingHeaders(request);
        return true;
    }

    /// <summary>Diagnostic endpoints must be GET, loopback-only, and free of proxy claims.</summary>
    public static bool AllowLocalDiagnostic(HttpContext context)
    {
        if (!HttpMethods.IsGet(context.Request.Method) ||
            context.Connection.RemoteIpAddress is not IPAddress address ||
            !IPAddress.IsLoopback(address))
            return false;
        StripForwardingHeaders(context.Request);
        return true;
    }

    private static bool ExactHeader(HttpRequest request, string name, string expected)
    {
        var value = request.Headers[name];
        return value.Count == 1 &&
               string.Equals(value[0], expected, StringComparison.Ordinal);
    }

    private static bool ReadIp(HttpRequest request, string header, out IPAddress ip)
    {
        ip = IPAddress.None;
        var value = request.Headers[header];
        if (value.Count != 1 || string.IsNullOrEmpty(value[0]))
            return false;
        var raw = value[0]!;
        if (raw.Any(char.IsWhiteSpace) || raw.Contains(',') ||
            !IPAddress.TryParse(raw, out var parsed) ||
            parsed.Equals(IPAddress.Any) || parsed.Equals(IPAddress.IPv6Any))
            return false;
        ip = Normalize(parsed)!;
        return true;
    }

    private static IPAddress? Normalize(IPAddress? ip) =>
        ip?.IsIPv4MappedToIPv6 == true ? ip.MapToIPv4() : ip;

    private static bool IsCanonicalHeader(string name) =>
        name.Equals("X-Forwarded-For", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("X-Forwarded-Host", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("X-Forwarded-Proto", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("X-Real-IP", StringComparison.OrdinalIgnoreCase);

    private static bool IsForwardingHeader(string name) =>
        name.StartsWith("X-Forwarded-", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("X-Real-IP", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("Forwarded", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("True-Client-IP", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("CF-Connecting-IP", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("CF-Visitor", StringComparison.OrdinalIgnoreCase);

    private static void StripForwardingHeaders(HttpRequest request)
    {
        foreach (var header in request.Headers.Keys.Where(IsForwardingHeader).ToArray())
            request.Headers.Remove(header);
    }
}
