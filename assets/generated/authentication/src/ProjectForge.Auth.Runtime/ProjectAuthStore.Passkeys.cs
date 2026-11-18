using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using Microsoft.Data.Sqlite;

namespace ProjectForge.Auth.Runtime;

/// <summary>Project-local WebAuthn public credential. The private key and biometric
/// information remain exclusively with the authenticator/passkey provider.</summary>
public sealed record ProjectPasskeyCredential(
    byte[] CredentialId, string AccountId, byte[] UserHandle, byte[] PublicKey,
    uint SignCount, bool BackupEligible, bool BackedUp, bool Revoked,
    string Label, DateTimeOffset CreatedAt, DateTimeOffset? LastUsedAt);

/// <summary>Single-use server ceremony state, bound to purpose and, for registration,
/// the preexisting authenticated Project session. No raw challenge cookie is stored.</summary>
public sealed record ProjectPasskeyCeremony(string OptionsJson, string? AccountId);

public sealed partial class ProjectAuthStore
{
    private const int MaximumPasskeysPerAccount = 10;
    private const int MaximumOptionBytes = 32768;

    /// <summary>
    /// Explicit opt-in migration. This deliberately keeps the original Project
    /// auth PRAGMA user_version=1: a reviewed feature-off rollback to an older
    /// Google-only runtime continues to read its existing account/session tables.
    /// No Production process calls this until feature activation is authorized.
    /// </summary>
    public void InitializePasskeySchema()
    {
        using var db = Open();
        using (var version = Sql(db, null, "PRAGMA user_version;"))
        {
            if (Convert.ToInt32(version.ExecuteScalar(), CultureInfo.InvariantCulture) != 1)
                throw new InvalidOperationException("An initialized Project Auth v1 store is required.");
        }
        using var tx = db.BeginTransaction(deferred: false);
        using (var cmd = Sql(db, tx, """
            CREATE TABLE IF NOT EXISTS passkey_schema (
                singleton INTEGER PRIMARY KEY CHECK (singleton=1),
                version INTEGER NOT NULL CHECK (version=1)
            );
            CREATE TABLE IF NOT EXISTS passkey_users (
                account_id TEXT PRIMARY KEY NOT NULL REFERENCES accounts(id),
                user_handle BLOB NOT NULL UNIQUE CHECK(length(user_handle)=32)
            );
            CREATE TABLE IF NOT EXISTS passkey_credentials (
                credential_id BLOB PRIMARY KEY NOT NULL,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                user_handle BLOB NOT NULL,
                public_key BLOB NOT NULL,
                sign_count INTEGER NOT NULL CHECK(sign_count>=0),
                backup_eligible INTEGER NOT NULL CHECK(backup_eligible IN (0,1)),
                backed_up INTEGER NOT NULL CHECK(backed_up IN (0,1)),
                label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 64),
                created_utc TEXT NOT NULL,
                last_used_utc TEXT,
                revoked_utc TEXT,
                FOREIGN KEY(account_id) REFERENCES passkey_users(account_id)
            );
            CREATE INDEX IF NOT EXISTS ix_passkey_credentials_account
                ON passkey_credentials(account_id,revoked_utc);
            CREATE TABLE IF NOT EXISTS passkey_ceremonies (
                token_hash TEXT PRIMARY KEY NOT NULL,
                purpose TEXT NOT NULL CHECK (purpose IN ('registration','authentication')),
                options_json TEXT NOT NULL,
                account_id TEXT REFERENCES accounts(id),
                session_hash TEXT,
                expires_utc TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                CHECK ((purpose='registration' AND account_id IS NOT NULL AND session_hash IS NOT NULL)
                    OR (purpose='authentication' AND account_id IS NULL AND session_hash IS NULL))
            );
            CREATE INDEX IF NOT EXISTS ix_passkey_ceremonies_expiry
                ON passkey_ceremonies(expires_utc);
            INSERT OR IGNORE INTO passkey_schema(singleton,version) VALUES(1,1);
            """)) cmd.ExecuteNonQuery();
        using (var version = Sql(db, tx, "SELECT version FROM passkey_schema WHERE singleton=1"))
        {
            if (Convert.ToInt32(version.ExecuteScalar(), CultureInfo.InvariantCulture) != 1)
                throw new InvalidOperationException("Unsupported passkey schema version.");
        }
        tx.Commit();
    }

    private static bool SessionMatches(SqliteConnection db, SqliteTransaction tx,
        string accountId, string sessionToken, DateTimeOffset now)
    {
        if (sessionToken is null || !TokenPattern.IsMatch(sessionToken)) return false;
        using var cmd = Sql(db, tx, """
            SELECT COUNT(*) FROM sessions s JOIN accounts a ON a.id=s.account_id
            WHERE s.token_hash=$hash AND s.account_id=$account
              AND s.revoked_utc IS NULL AND s.expires_utc>$now
              AND a.disabled=0 AND a.email_verified=1
            """, ("$hash", Hash(sessionToken)), ("$account", accountId),
            ("$now", Utc(now)));
        return Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture) == 1;
    }

    public byte[] GetOrCreatePasskeyUserHandle(string accountId, string sessionToken, DateTimeOffset now)
    {
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        if (!SessionMatches(db, tx, accountId, sessionToken, now))
            throw new UnauthorizedAccessException("Approved session required.");
        var handle = RandomNumberGenerator.GetBytes(32);
        using (var insert = Sql(db, tx, """
            INSERT OR IGNORE INTO passkey_users (account_id,user_handle) VALUES ($id,$handle)
            """, ("$id", accountId), ("$handle", handle))) insert.ExecuteNonQuery();
        using var query = Sql(db, tx, "SELECT user_handle FROM passkey_users WHERE account_id=$id",
            ("$id", accountId));
        var persisted = (byte[]?)query.ExecuteScalar() ?? throw new InvalidOperationException("User handle missing.");
        tx.Commit();
        return persisted;
    }

    /// <summary>Returns a cookie-only 256-bit bearer binding, not WebAuthn options.
    /// The caller sets a Secure, HttpOnly, same-origin, short-lived cookie.</summary>
    public string BeginPasskeyCeremony(string purpose, string optionsJson,
        string? accountId, string? sessionToken, DateTimeOffset now)
    {
        if (purpose is not ("registration" or "authentication") ||
            string.IsNullOrWhiteSpace(optionsJson) ||
            System.Text.Encoding.UTF8.GetByteCount(optionsJson) > MaximumOptionBytes ||
            (purpose == "registration" && (string.IsNullOrWhiteSpace(accountId) || sessionToken is null)) ||
            (purpose == "authentication" && (accountId is not null || sessionToken is not null)))
            throw new ArgumentException("Invalid passkey ceremony.");
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        if (purpose == "registration" && !SessionMatches(db, tx, accountId!, sessionToken!, now))
            throw new UnauthorizedAccessException("Approved session required.");
        var token = NewToken();
        using (var trim = Sql(db, tx,
            "DELETE FROM passkey_ceremonies WHERE expires_utc<=$now", ("$now", Utc(now))))
            trim.ExecuteNonQuery();
        using (var insert = Sql(db, tx, """
            INSERT INTO passkey_ceremonies(token_hash,purpose,options_json,account_id,
                                          session_hash,created_utc,expires_utc)
            VALUES($token,$purpose,$options,$account,$session,$created,$expires)
            """, ("$token", Hash(token)), ("$purpose", purpose),
            ("$options", optionsJson), ("$account", accountId),
            ("$session", sessionToken is null ? null : Hash(sessionToken)),
            ("$created", Utc(now)), ("$expires", Utc(now.AddMinutes(3)))))
            insert.ExecuteNonQuery();
        tx.Commit();
        return token;
    }

    /// <summary>Atomically consumes a challenge before cryptographic verification.
    /// Even a malformed or failed assertion cannot replay the same ceremony.</summary>
    public ProjectPasskeyCeremony? ConsumePasskeyCeremony(string purpose, string? cookieToken,
        string? accountId, string? sessionToken, DateTimeOffset now)
    {
        if (cookieToken is null || !TokenPattern.IsMatch(cookieToken) ||
            purpose is not ("registration" or "authentication")) return null;
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using var query = Sql(db, tx, """
            SELECT options_json,account_id,session_hash,expires_utc
            FROM passkey_ceremonies WHERE token_hash=$hash AND purpose=$purpose
            """, ("$hash", Hash(cookieToken)), ("$purpose", purpose));
        string options;
        string? boundAccount;
        string? boundSession;
        string expiry;
        using (var reader = query.ExecuteReader())
        {
            if (!reader.Read()) return null;
            options = reader.GetString(0);
            boundAccount = reader.IsDBNull(1) ? null : reader.GetString(1);
            boundSession = reader.IsDBNull(2) ? null : reader.GetString(2);
            expiry = reader.GetString(3);
        }
        // Delete first, irrespective of the verification outcome, under the write lock.
        using (var consume = Sql(db, tx,
            "DELETE FROM passkey_ceremonies WHERE token_hash=$hash",
            ("$hash", Hash(cookieToken))))
        {
            if (consume.ExecuteNonQuery() != 1) return null;
        }
        var valid = now < ReadUtc(expiry) && (purpose == "authentication"
            ? boundAccount is null && boundSession is null && accountId is null && sessionToken is null
            : boundAccount == accountId && sessionToken is not null &&
              TokenPattern.IsMatch(sessionToken) && boundSession == Hash(sessionToken) &&
              SessionMatches(db, tx, accountId!, sessionToken, now));
        tx.Commit();
        return valid ? new ProjectPasskeyCeremony(options, boundAccount) : null;
    }

    public IReadOnlyList<ProjectPasskeyCredential> ListPasskeys(string accountId)
    {
        using var db = Open();
        using var cmd = Sql(db, null, """
            SELECT credential_id,account_id,user_handle,public_key,sign_count,
                   backup_eligible,backed_up,revoked_utc,label,created_utc,last_used_utc
            FROM passkey_credentials WHERE account_id=$id ORDER BY created_utc
            """, ("$id", accountId));
        var credentials = new List<ProjectPasskeyCredential>();
        using var reader = cmd.ExecuteReader();
        while (reader.Read()) credentials.Add(ReadPasskey(reader));
        return credentials;
    }

    private static ProjectPasskeyCredential ReadPasskey(SqliteDataReader r) => new(
        r.GetFieldValue<byte[]>(0), r.GetString(1), r.GetFieldValue<byte[]>(2),
        r.GetFieldValue<byte[]>(3), checked((uint)r.GetInt64(4)),
        r.GetInt32(5) != 0, r.GetInt32(6) != 0, !r.IsDBNull(7),
        r.GetString(8), ReadUtc(r.GetString(9)),
        r.IsDBNull(10) ? null : ReadUtc(r.GetString(10)));

    public ProjectPasskeyCredential? FindActivePasskey(byte[] credentialId)
    {
        if (credentialId is null || credentialId.Length is < 16 or > 1024) return null;
        using var db = Open();
        using var cmd = Sql(db, null, """
            SELECT c.credential_id,c.account_id,c.user_handle,c.public_key,
                   c.sign_count,c.backup_eligible,c.backed_up,c.revoked_utc,
                   c.label,c.created_utc,c.last_used_utc
            FROM passkey_credentials c JOIN accounts a ON a.id=c.account_id
            WHERE c.credential_id=$id AND c.revoked_utc IS NULL
                  AND a.disabled=0 AND a.email_verified=1
            """, ("$id", credentialId));
        using var r = cmd.ExecuteReader();
        return r.Read() ? ReadPasskey(r) : null;
    }

    /// <summary>Persist ONLY the successfully verified output of the WebAuthn library.
    /// Never call with unverified browser credential fields.</summary>
    internal void SaveVerifiedPasskey(string accountId, string sessionToken, byte[] credentialId,
        byte[] userHandle, byte[] publicKey, uint signCount, bool backupEligible,
        bool backedUp, string label, DateTimeOffset now)
    {
        if (credentialId is null || credentialId.Length is < 16 or > 1024 ||
            userHandle is null || userHandle.Length != 32 ||
            publicKey is null || publicKey.Length is < 16 or > 8192 ||
            string.IsNullOrWhiteSpace(label) || label.Length > 64 ||
            (backedUp && !backupEligible))
            throw new ArgumentException("Invalid verified passkey credential.");
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        // A verified WebAuthn response is not sufficient to enroll a key:
        // the *same* session must still carry recent verified Google proof
        // at the moment the credential is committed. This check shares the
        // SQLite write transaction with credential insertion.
        if (!HasRecentGoogleSignInInTransaction(db, tx, accountId, sessionToken, now))
            throw new UnauthorizedAccessException("Fresh Google identity required.");
        using (var count = Sql(db, tx,
            "SELECT COUNT(*) FROM passkey_credentials WHERE account_id=$id AND revoked_utc IS NULL",
            ("$id", accountId)))
        {
            if (Convert.ToInt32(count.ExecuteScalar(), CultureInfo.InvariantCulture) >= MaximumPasskeysPerAccount)
                throw new InvalidOperationException("Passkey limit reached.");
        }
        using (var handle = Sql(db, tx,
            "SELECT user_handle FROM passkey_users WHERE account_id=$id",
            ("$id", accountId)))
        {
            if (handle.ExecuteScalar() is not byte[] savedHandle ||
                !CryptographicOperations.FixedTimeEquals(savedHandle, userHandle))
                throw new UnauthorizedAccessException("Passkey user handle mismatch.");
        }
        using (var insert = Sql(db, tx, """
            INSERT INTO passkey_credentials(credential_id,account_id,user_handle,public_key,
                     sign_count,backup_eligible,backed_up,label,created_utc)
            VALUES($id,$account,$handle,$key,$counter,$eligible,$backed,$label,$time)
            """, ("$id", credentialId), ("$account", accountId),
            ("$handle", userHandle), ("$key", publicKey), ("$counter", (long)signCount),
            ("$eligible", backupEligible ? 1 : 0), ("$backed", backedUp ? 1 : 0),
            ("$label", label.Trim()), ("$time", Utc(now)))) insert.ExecuteNonQuery();
        tx.Commit();
    }

    /// <summary>After Fido2 has verified a WebAuthn assertion against the exact
    /// retrieved stored key/counter, perform a compare-and-swap update and issue
    /// the normal seven-day Project session. Not an authentication verifier.</summary>
    internal ProjectAuthResult FinishVerifiedPasskeyAssertion(byte[] credentialId,
        uint originalCounter, uint verifiedCounter, bool backedUp, DateTimeOffset now)
    {
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using var find = Sql(db, tx, """
            SELECT c.account_id,c.sign_count,c.backup_eligible,c.backed_up
            FROM passkey_credentials c JOIN accounts a ON a.id=c.account_id
            WHERE c.credential_id=$id AND c.revoked_utc IS NULL
                  AND a.disabled=0 AND a.email_verified=1
            """, ("$id", credentialId));
        string accountId;
        bool eligible;
        using (var r = find.ExecuteReader())
        {
            if (!r.Read() || checked((uint)r.GetInt64(1)) != originalCounter)
                return new(false, "passkey-not-approved", null, null);
            accountId = r.GetString(0);
            eligible = r.GetInt32(2) != 0;
        }
        if ((backedUp && !eligible) ||
            (originalCounter != 0 && verifiedCounter <= originalCounter))
            return new(false, "passkey-not-approved", null, null);
        using (var update = Sql(db, tx, """
            UPDATE passkey_credentials SET sign_count=$counter, backed_up=$backed,
                   last_used_utc=$time WHERE credential_id=$id AND sign_count=$old
            """, ("$counter", (long)verifiedCounter), ("$backed", backedUp ? 1 : 0),
            ("$time", Utc(now)), ("$id", credentialId), ("$old", (long)originalCounter)))
        {
            if (update.ExecuteNonQuery() != 1)
                return new(false, "passkey-not-approved", null, null);
        }
        var account = AccountById(db, tx, accountId);
        if (account is not { Disabled: false, EmailVerified: true })
            return new(false, "passkey-not-approved", null, null);
        var session = IssueWithin(db, tx, accountId, now);
        tx.Commit();
        return new(true, "approved-passkey", session, account);
    }
}
