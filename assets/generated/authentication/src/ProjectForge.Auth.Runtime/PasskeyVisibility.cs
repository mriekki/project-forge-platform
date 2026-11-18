using System.Runtime.CompilerServices;

// The direct storage primitives must not be reachable from untrusted web
// consumers. Only the Auth Kit verification component (same assembly) and
// synthetic contract tests may call them.
[assembly: InternalsVisibleTo("ProjectForge.Auth.Runtime.ContractTests")]
