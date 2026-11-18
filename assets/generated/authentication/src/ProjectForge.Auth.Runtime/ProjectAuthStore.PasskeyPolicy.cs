using System;
using System.Globalization;
using Microsoft.Data.Sqlite;

namespace ProjectForge.Auth.Runtime;

public sealed partial class ProjectAuthStore
{
    /// <summary>
    /// Separate, additive versioned Google step-up evidence. No existing session
    /// record changes, and the feature-off Google-only reader remains compatible.
    /// The recent record is created ONLY after a server-verified Google OIDC sign-in.
    /// </summary>
    public void InitializePasskeyStepUpSchema()
    {
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using var cmd = Sql(db, tx, """
            CREATE TABLE IF NOT EXISTS passkey_recent_google (
                token_hash TEXT PRIMARY KEY NOT NULL REFERENCES sessions(token_hash),
                account_id TEXT NOT NULL REFERENCES accounts(id),
                verified_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_passkey_recent_google_time
                ON passkey_recent_google(verified_utc);
            """);
        cmd.ExecuteNonQuery();
        tx.Commit();
    }

    /// <summary>Called by the trusted OIDC success callback only, never from a
    /// public API. Does not accept email, account ID or a client-supplied claim.</summary>
    internal void RecordRecentGoogleSignIn(string sessionToken, DateTimeOffset now)
    {
        var account = GetSession(sessionToken, now)
            ?? throw new UnauthorizedAccessException("Verified, approved session required.");
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using (var cleanup = Sql(db, tx,
            "DELETE FROM passkey_recent_google WHERE verified_utc<$limit",
            ("$limit", Utc(now.AddDays(-1)))))
            cleanup.ExecuteNonQuery();
        using (var cmd = Sql(db, tx, """
            INSERT OR REPLACE INTO passkey_recent_google(token_hash,account_id,verified_utc)
            VALUES($token,$account,$now)
            """, ("$token", Hash(sessionToken)), ("$account", account.Id),
            ("$now", Utc(now))))
            cmd.ExecuteNonQuery();
        tx.Commit();
    }

    /// <summary>For sensitive enrollment/revocation: a valid Project session
    /// created by successful Google OIDC within the last five minutes.</summary>
    internal bool HasRecentGoogleSignIn(string accountId, string? sessionToken, DateTimeOffset now)
    {
        using var db = Open();
        return HasRecentGoogleSignInInTransaction(db, null, accountId, sessionToken, now);
    }

    // Security-sensitive writes must check this proof under their own SQLite
    // write transaction, not rely on an HTTP preflight checked before WebAuthn
    // cryptography. A proof expired/revoked during verification grants nothing.
    private static bool HasRecentGoogleSignInInTransaction(
        SqliteConnection db, SqliteTransaction? tx,
        string accountId, string? sessionToken, DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(accountId) ||
            sessionToken is null || !TokenPattern.IsMatch(sessionToken)) return false;
        using var query = Sql(db, tx, """
            SELECT COUNT(*) FROM passkey_recent_google proof
            JOIN sessions s ON s.token_hash=proof.token_hash
            JOIN accounts a ON a.id=s.account_id
            WHERE proof.token_hash=$token AND proof.account_id=$account
              AND s.account_id=$account AND s.revoked_utc IS NULL
              AND s.expires_utc>$now AND a.disabled=0 AND a.email_verified=1
              AND proof.verified_utc>$cutoff AND proof.verified_utc<=$now
            """, ("$token", Hash(sessionToken)), ("$account", accountId),
            ("$now", Utc(now)), ("$cutoff", Utc(now.AddMinutes(-5))));
        return Convert.ToInt32(query.ExecuteScalar(), CultureInfo.InvariantCulture) == 1;
    }

    /// <summary>Check uniqueness over every credential, including revoked
    /// records; credential IDs can never be reassigned across accounts.</summary>
    internal bool AnyPasskeyCredentialId(byte[] credentialId)
    {
        if (credentialId is null || credentialId.Length is < 16 or > 1024) return true;
        using var db = Open();
        using var query = Sql(db, null,
            "SELECT COUNT(*) FROM passkey_credentials WHERE credential_id=$id",
            ("$id", credentialId));
        return Convert.ToInt32(query.ExecuteScalar(), CultureInfo.InvariantCulture) != 0;
    }

    internal bool RevokeOwnPasskey(string accountId, string sessionToken, byte[] credentialId,
        DateTimeOffset now)
    {
        if (credentialId is null || credentialId.Length is < 16 or > 1024)
            return false;
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        if (!HasRecentGoogleSignInInTransaction(db, tx, accountId, sessionToken, now))
            return false;
        using (var cmd = Sql(db, tx, """
            UPDATE passkey_credentials SET revoked_utc=$now
            WHERE account_id=$account AND credential_id=$id AND revoked_utc IS NULL
            """, ("$now", Utc(now)), ("$account", accountId), ("$id", credentialId)))
        {
            if (cmd.ExecuteNonQuery() != 1) return false;
        }
        // A revoked passkey must not leave unrelated sessions alive for the
        // affected account. Keep only the current fresh Google session.
        using (var revoke = Sql(db, tx, """
            UPDATE sessions SET revoked_utc=$now
            WHERE account_id=$account AND token_hash<>$current
              AND revoked_utc IS NULL
            """, ("$now", Utc(now)), ("$account", accountId),
            ("$current", Hash(sessionToken))))
            revoke.ExecuteNonQuery();
        tx.Commit();
        return true;
    }
}
