using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace ProjectForge.Auth.Runtime;

public sealed record ProjectAccount(
    string Id, string Email, string NormalizedEmail, bool EmailVerified,
    bool IsAdministrator, bool Disabled, long CreatedAt);
public sealed record ProjectAuthSession(
    string Token, string AccountId, DateTimeOffset ExpiresAt);
public sealed record VerifiedGoogleIdentity(
    string Issuer, string Subject, string Email, bool EmailVerified);
public sealed record ProjectInvitation(string Token, DateTimeOffset ExpiresAt);
public sealed record ProjectAuthResult(
    bool Succeeded, string ReasonCode, ProjectAuthSession? Session, ProjectAccount? Account);

/// <summary>
/// Application-local, durable SQLite identity and opaque-session store.
/// Does not read Household Registry during login or copy application users.
/// No email-only account linking, no implicit admin bootstrap, no tokens in DB.
/// </summary>
public sealed class ProjectAuthStore
{
    private readonly string _connString;
    private const string GoogleIssuer = "https://accounts.google.com";
    private static readonly Regex Email = new(
        @"^[^@\s]{1,100}@[^@\s]{1,180}$", RegexOptions.CultureInvariant);
    private static readonly Regex TokenPattern = new(
        @"^[0-9a-f]{64}$", RegexOptions.CultureInvariant);

    public ProjectAuthStore(string databasePath)
    {
        if (string.IsNullOrWhiteSpace(databasePath))
            throw new ArgumentException("App-owned SQLite database path is required.");
        _connString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false
        }.ToString();
    }

    private SqliteConnection Open()
    {
        var db = new SqliteConnection(_connString);
        db.Open();
        using var pragma = db.CreateCommand();
        pragma.CommandText = "PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;";
        pragma.ExecuteNonQuery();
        return db;
    }

    private static SqliteCommand Sql(SqliteConnection db, SqliteTransaction? tx, string sql,
        params (string, object?)[] bindings)
    {
        var cmd = db.CreateCommand();
        cmd.CommandText = sql;
        cmd.Transaction = tx;
        foreach (var (name, value) in bindings)
            cmd.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return cmd;
    }
    private static string Id() => Guid.NewGuid().ToString("N");
    private static string Utc(DateTimeOffset now) => now.UtcDateTime.ToString("O", CultureInfo.InvariantCulture);
    private static DateTimeOffset ReadUtc(string value) =>
        DateTimeOffset.Parse(value, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);
    private static string NormalizeEmail(string email)
    {
        if (email is null) throw new ArgumentException("Email is required.");
        var normalized = email.Trim();
        if (!Email.IsMatch(normalized) || normalized.Length > 254)
            throw new ArgumentException("Valid verified email is required.");
        return normalized.ToUpperInvariant();
    }
    private static bool ValidIdentity(VerifiedGoogleIdentity principal) =>
        principal is not null &&
        principal.Issuer == GoogleIssuer &&
        !string.IsNullOrWhiteSpace(principal.Subject) &&
        principal.Subject.Length <= 512 &&
        principal.EmailVerified &&
        Email.IsMatch(principal.Email ?? "");

    private static string Hash(string token) =>
        Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(token)));
    private static string NewToken() => Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();

    /// <summary>
    /// Read-only application liveness probe for a *currently running* Project.
    /// A missing/corrupt/stale identity database is unhealthy; a health result
    /// does not prove recovered sessions, DataProtection continuity, external
    /// Google/Resend access, backup freshness, or normal traffic acceptance.
    /// Unlike Initialize(), this must NEVER create the missing SQLite file.
    /// </summary>
    public bool IsReadableAndCurrent()
    {
        try
        {
            var options = new SqliteConnectionStringBuilder(_connString)
            {
                Mode = SqliteOpenMode.ReadOnly,
                Pooling = false
            };
            using var db = new SqliteConnection(options.ToString());
            db.Open();
            using var schema = db.CreateCommand();
            schema.CommandText = "PRAGMA user_version;";
            if (Convert.ToInt32(schema.ExecuteScalar(), CultureInfo.InvariantCulture) != 1)
                return false;
            schema.CommandText = """
                SELECT COUNT(*) FROM sqlite_master
                WHERE type = 'table' AND name IN ('accounts', 'sessions');
                """;
            return Convert.ToInt32(schema.ExecuteScalar(), CultureInfo.InvariantCulture) == 2;
        }
        catch (SqliteException)
        {
            // Only a coarse status may reach the caller. Never reveal a
            // physical DB path or SQLite diagnostic over HTTP.
            return false;
        }
    }

    public void Initialize()
    {
        using var db = Open();
        using var cmd = Sql(db, null, "PRAGMA user_version;");
        var version = Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture);
        if (version > 1) throw new InvalidOperationException("Application auth store schema is newer than this Kit.");
        if (version == 1) return;
        using var tx = db.BeginTransaction(deferred: false);
        using var schema = Sql(db, tx, """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY NOT NULL,
                email TEXT NOT NULL,
                normalized_email TEXT NOT NULL UNIQUE,
                email_verified INTEGER NOT NULL CHECK (email_verified IN (0,1)),
                is_admin INTEGER NOT NULL CHECK (is_admin IN (0,1)),
                disabled INTEGER NOT NULL CHECK (disabled IN (0,1)) DEFAULT 0,
                created_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS external_identities (
                account_id TEXT NOT NULL REFERENCES accounts(id),
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                PRIMARY KEY (issuer,subject),
                UNIQUE (account_id,issuer,subject)
            );
            CREATE TABLE IF NOT EXISTS invitations (
                id TEXT PRIMARY KEY NOT NULL,
                recipient_email TEXT NOT NULL,
                recipient_normalized TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_utc TEXT NOT NULL,
                consumed_utc TEXT,
                created_by TEXT NOT NULL REFERENCES accounts(id),
                created_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_invites_created_by ON invitations(created_by,created_utc);
            CREATE INDEX IF NOT EXISTS ix_invites_recipient ON invitations(recipient_normalized,created_utc);
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY NOT NULL,
                account_id TEXT NOT NULL REFERENCES accounts(id),
                created_utc TEXT NOT NULL,
                expires_utc TEXT NOT NULL,
                revoked_utc TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_sessions_account ON sessions(account_id);
            PRAGMA user_version=1;
            """);
        schema.ExecuteNonQuery();
        tx.Commit();
    }

    /// <summary>
    /// First administrator is provisioned only through trusted local host
    /// configuration, with a preapproved immutable Google subject.
    /// Email remains unverified until actual Google OIDC assertion.
    /// </summary>
    public string BootstrapAdministrator(
        string issuer, string subject, string email, DateTimeOffset now)
    {
        if (issuer != GoogleIssuer || string.IsNullOrWhiteSpace(subject) ||
            subject.Length > 512)
            throw new ArgumentException("Preapproved exact Google issuer and subject required.");
        var normalized = NormalizeEmail(email);
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using (var count = Sql(db, tx, "SELECT COUNT(*) FROM accounts"))
        {
            if (Convert.ToInt32(count.ExecuteScalar(), CultureInfo.InvariantCulture) != 0)
                throw new InvalidOperationException("First administrator is already provisioned.");
        }
        var id = Id();
        using (var cmd = Sql(db, tx, """
            INSERT INTO accounts (id,email,normalized_email,email_verified,is_admin,disabled,created_utc)
            VALUES ($id,$email,$norm,0,1,0,$time)
            """, ("$id", id), ("$email", email.Trim()), ("$norm", normalized),
            ("$time", Utc(now))))
            cmd.ExecuteNonQuery();
        using (var link = Sql(db, tx, """
            INSERT INTO external_identities (account_id,issuer,subject)
            VALUES ($id,$issuer,$subject)
            """, ("$id", id), ("$issuer", issuer), ("$subject", subject)))
            link.ExecuteNonQuery();
        tx.Commit();
        return id;
    }

    private static ProjectAccount ReadAccount(SqliteDataReader r) =>
        new(r.GetString(0), r.GetString(1), r.GetString(2),
            r.GetInt32(3) != 0, r.GetInt32(4) != 0,
            r.GetInt32(5) != 0, 0);

    private static ProjectAccount? AccountById(
        SqliteConnection db, SqliteTransaction? tx, string id)
    {
        using var cmd = Sql(db, tx, """
            SELECT id,email,normalized_email,email_verified,is_admin,disabled
            FROM accounts WHERE id=$id
            """, ("$id", id));
        using var reader = cmd.ExecuteReader();
        return reader.Read() ? ReadAccount(reader) : null;
    }

    public ProjectAccount? FindGoogleAccount(VerifiedGoogleIdentity principal)
    {
        if (!ValidIdentity(principal)) return null;
        using var db = Open();
        using var cmd = Sql(db, null, """
            SELECT a.id,a.email,a.normalized_email,a.email_verified,a.is_admin,a.disabled
            FROM accounts a JOIN external_identities i ON i.account_id=a.id
            WHERE i.issuer=$iss AND i.subject=$sub
            """, ("$iss", principal.Issuer), ("$sub", principal.Subject));
        using var r = cmd.ExecuteReader();
        return r.Read() ? ReadAccount(r) : null;
    }

    private static ProjectAuthSession IssueWithin(
        SqliteConnection db, SqliteTransaction tx, string accountId, DateTimeOffset now)
    {
        var token = NewToken();
        var expiry = now.AddDays(7);
        using var cmd = Sql(db, tx, """
            INSERT INTO sessions(token_hash,account_id,created_utc,expires_utc)
            VALUES($t,$a,$c,$e)
            """, ("$t", Hash(token)), ("$a", accountId), ("$c", Utc(now)),
                ("$e", Utc(expiry)));
        cmd.ExecuteNonQuery();
        return new ProjectAuthSession(token, accountId, expiry);
    }

    public ProjectAuthResult SignIn(VerifiedGoogleIdentity principal, DateTimeOffset now)
    {
        if (!ValidIdentity(principal))
            return new(false, "google-identity-not-verified", null, null);
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        string? accountId;
        using (var find = Sql(db, tx, """
            SELECT account_id FROM external_identities
            WHERE issuer=$iss AND subject=$sub
            """, ("$iss", principal.Issuer), ("$sub", principal.Subject)))
            accountId = find.ExecuteScalar() as string;
        if (accountId is null)
            return new(false, "account-not-approved", null, null);
        var account = AccountById(db, tx, accountId);
        if (account is null || account.Disabled)
            return new(false, "account-not-approved", null, null);
        // The bound issuer+subject is identity authority, not the current
        // email claim. A changed email never auto-links to another account.
        if (!account.EmailVerified)
        {
            using var promote = Sql(db, tx,
                "UPDATE accounts SET email_verified=1 WHERE id=$id",
                ("$id", accountId));
            promote.ExecuteNonQuery();
            account = account with { EmailVerified = true };
        }
        var session = IssueWithin(db, tx, accountId, now);
        tx.Commit();
        return new(true, "approved-google-account", session, account);
    }

    public ProjectInvitation CreateInvitation(string actorId, string email, DateTimeOffset now)
    {
        var normalized = NormalizeEmail(email);
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        var admin = AccountById(db, tx, actorId);
        if (admin is not { IsAdministrator: true, Disabled: false })
            throw new UnauthorizedAccessException("Approved administrator required.");
        // Persistent, transactional abuse controls: at most five invitations
        // per administrator per hour and three per address per 24 hours.
        // These constraints hold across process restarts and parallel requests.
        using (var adminCount = Sql(db, tx, """
            SELECT COUNT(*) FROM invitations
            WHERE created_by=$admin AND created_utc>$since
            """, ("$admin", actorId), ("$since", Utc(now.AddHours(-1)))))
        {
            if (Convert.ToInt32(adminCount.ExecuteScalar(), CultureInfo.InvariantCulture) >= 5)
                throw new InvalidOperationException("Invitation rate limit reached.");
        }
        using (var recipientCount = Sql(db, tx, """
            SELECT COUNT(*) FROM invitations
            WHERE recipient_normalized=$recipient AND created_utc>$since
            """, ("$recipient", normalized), ("$since", Utc(now.AddDays(-1)))))
        {
            if (Convert.ToInt32(recipientCount.ExecuteScalar(), CultureInfo.InvariantCulture) >= 3)
                throw new InvalidOperationException("Recipient invitation rate limit reached.");
        }
        var token = NewToken();
        var expiry = now.AddHours(48);
        using var cmd = Sql(db, tx, """
            INSERT INTO invitations(id,recipient_email,recipient_normalized,
                                    token_hash,expires_utc,created_by,created_utc)
            VALUES($id,$email,$norm,$hash,$expires,$actor,$created)
            """, ("$id", Id()), ("$email", email.Trim()), ("$norm", normalized),
                ("$hash", Hash(token)), ("$expires", Utc(expiry)),
                ("$actor", actorId), ("$created", Utc(now)));
        cmd.ExecuteNonQuery();
        tx.Commit();
        return new ProjectInvitation(token, expiry);
    }

    public ProjectAuthResult RedeemInvitation(
        VerifiedGoogleIdentity principal, string token, DateTimeOffset now)
    {
        if (!ValidIdentity(principal) || token is null || !TokenPattern.IsMatch(token))
            return new(false, "invitation-unavailable", null, null);
        var normalized = NormalizeEmail(principal.Email);
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        string inviteId, recipient, expiry;
        using (var cmd = Sql(db, tx, """
            SELECT id,recipient_normalized,expires_utc
            FROM invitations WHERE token_hash=$hash AND consumed_utc IS NULL
            """, ("$hash", Hash(token)))
        )
        using (var r = cmd.ExecuteReader())
        {
            if (!r.Read()) return new(false, "invitation-unavailable", null, null);
            inviteId = r.GetString(0);
            recipient = r.GetString(1);
            expiry = r.GetString(2);
        }
        if (recipient != normalized || now >= ReadUtc(expiry))
            return new(false, "invitation-unavailable", null, null);
        var accountId = Id();
        try
        {
            using (var cmd = Sql(db, tx, """
                INSERT INTO accounts (id,email,normalized_email,email_verified,is_admin,disabled,created_utc)
                VALUES($id,$email,$norm,1,0,0,$created)
                """, ("$id", accountId), ("$email", principal.Email.Trim()),
                    ("$norm", normalized), ("$created", Utc(now))))
                cmd.ExecuteNonQuery();
            using (var identity = Sql(db, tx, """
                INSERT INTO external_identities(account_id,issuer,subject)
                VALUES($id,$iss,$sub)
                """, ("$id", accountId), ("$iss", principal.Issuer),
                    ("$sub", principal.Subject)))
                identity.ExecuteNonQuery();
            using (var consume = Sql(db, tx, """
                UPDATE invitations SET consumed_utc=$time
                WHERE id=$id AND consumed_utc IS NULL
                """, ("$time", Utc(now)), ("$id", inviteId)))
            {
                if (consume.ExecuteNonQuery() != 1)
                    return new(false, "invitation-unavailable", null, null);
            }
            var session = IssueWithin(db, tx, accountId, now);
            var account = AccountById(db, tx, accountId);
            tx.Commit();
            return new(true, "invited-account-created", session, account);
        }
        catch (SqliteException ex) when (ex.SqliteErrorCode == 19)
        {
            return new(false, "invitation-unavailable", null, null);
        }
    }

    public ProjectAccount? GetSession(string token, DateTimeOffset now)
    {
        if (token is null || !TokenPattern.IsMatch(token)) return null;
        using var db = Open();
        using var cmd = Sql(db, null, """
            SELECT a.id,a.email,a.normalized_email,a.email_verified,a.is_admin,a.disabled,
                   s.expires_utc,s.revoked_utc
            FROM sessions s JOIN accounts a ON a.id=s.account_id
            WHERE s.token_hash=$token
            """, ("$token", Hash(token)));
        using var reader = cmd.ExecuteReader();
        if (!reader.Read() || reader.GetInt32(5) != 0 ||
            !reader.IsDBNull(7) || now >= ReadUtc(reader.GetString(6)))
            return null;
        return ReadAccount(reader);
    }

    public bool RevokeSession(string token, DateTimeOffset now)
    {
        if (token is null || !TokenPattern.IsMatch(token)) return false;
        using var db = Open();
        using var cmd = Sql(db, null, """
            UPDATE sessions SET revoked_utc=$time
            WHERE token_hash=$token AND revoked_utc IS NULL
            """, ("$time", Utc(now)), ("$token", Hash(token)));
        return cmd.ExecuteNonQuery() == 1;
    }

    public bool DisableAccount(string adminSession, string accountId, DateTimeOffset now)
    {
        var admin = GetSession(adminSession, now);
        if (admin is not { IsAdministrator: true, Disabled: false })
            throw new UnauthorizedAccessException("Administrator required.");
        if (admin.Id == accountId) return false;
        using var db = Open();
        using var tx = db.BeginTransaction(deferred: false);
        using var cmd = Sql(db, tx,
            "UPDATE accounts SET disabled=1 WHERE id=$id AND disabled=0 AND is_admin=0",
            ("$id", accountId));
        var changed = cmd.ExecuteNonQuery() == 1;
        tx.Commit();
        return changed;
    }

    public void Backup(string destination)
    {
        if (string.IsNullOrWhiteSpace(destination) ||
            !Directory.Exists(Path.GetDirectoryName(Path.GetFullPath(destination))))
            throw new ArgumentException("A new protected backup destination is required.");

        // CreateNew is atomic: it refuses existing paths, including dangling
        // symlinks. A separate File.Exists + File.Create pair has a race that
        // could overwrite another backup between the existence check and open.
        try
        {
            using var reserved = new FileStream(
                destination, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        }
        catch (IOException error)
        {
            throw new ArgumentException(
                "A new protected backup destination is required.", nameof(destination), error);
        }
        try
        {
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(destination, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            using var origin = Open();
            using var target = new SqliteConnection(new SqliteConnectionStringBuilder
            {
                DataSource = destination, Mode = SqliteOpenMode.ReadWrite, Pooling = false
            }.ToString());
            target.Open();
            origin.BackupDatabase(target);
            using var check = Sql(target, null, "PRAGMA integrity_check;");
            if (check.ExecuteScalar() is not string status || status != "ok")
                throw new InvalidOperationException("SQLite backup integrity failed.");
        }
        catch
        {
            try { File.Delete(destination); } catch (IOException) { }
            throw;
        }
    }
}
