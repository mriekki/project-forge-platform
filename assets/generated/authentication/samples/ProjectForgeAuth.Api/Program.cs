using ProjectForge.Auth.Runtime;

var builder = WebApplication.CreateBuilder(args);

// The first administrator must be configured explicitly using the Google
// issuer/subject recorded through trusted administration. Nothing automatically
// promotes the first visitor or a member of the shared Household Registry.
if (args is ["admin-init"])
{
    var path = builder.Configuration["ProjectForge:Authentication:DbPath"]
        ?? throw new InvalidOperationException("App-owned authentication DB path required.");
    var subject = Environment.GetEnvironmentVariable("PF_INITIAL_APP_ADMIN_SUBJECT");
    var email = Environment.GetEnvironmentVariable("PF_INITIAL_APP_ADMIN_EMAIL");
    if (string.IsNullOrWhiteSpace(subject) || string.IsNullOrWhiteSpace(email))
        throw new InvalidOperationException("Preapproved administrator Google subject and email required.");
    var store = new ProjectAuthStore(path);
    store.Initialize();
    store.BootstrapAdministrator(
        "https://accounts.google.com", subject, email, DateTimeOffset.UtcNow);
    Console.WriteLine("Explicit per-Project administrator initialized; no public enrollment opened.");
    return;
}
if (args.Length != 0)
    throw new ArgumentException("Unknown command; supported host action: admin-init.");

builder.Services.AddProjectForgeProjectAuth(builder.Configuration);
var app = builder.Build();

// Before any static files, OIDC middleware or endpoints: verify the physical
// Caddy peer, exact host, HTTPS protocol and canonical forwarding evidence.
app.UseProjectForgeAuthPublicOrigin(app.Configuration);
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapProjectForgeAuth();
app.Run();

public partial class Program { }
