using System;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Configuration;

namespace ProjectForge.Auth.Runtime;

/// <summary>
/// Opt-in, fail-closed runtime admission precursor for the reviewed hold-only
/// recovery v1. NO operator command, restore, traffic release or passkey
/// activation is implemented here. Even a valid state remains CLOSED until B
/// independently qualifies stop/drain/restart prevention and traffic release.
/// </summary>
public sealed class ProjectAuthRecoveryAdmission
{
    public const string Mode = "hold-only-v1";
    public const string Prefix = "ProjectForge:Authentication:Recovery:";
    private const int O_RDONLY = 0;
    private const int O_NOFOLLOW = 0x20000;
    private const int O_CLOEXEC = 0x80000;
    private const int LOCK_EX = 2;
    private const int LOCK_NB = 4;
    private const int LOCK_UN = 8;
    private const int AT_FDCWD = -100;
    private const int AT_EMPTY_PATH = 0x1000;
    private const int AT_SYMLINK_NOFOLLOW = 0x100;
    private const uint STATX_BASIC_STATS = 0x7ff;
    private static readonly Regex ScopePattern = new(
        @"^[a-z0-9-]{1,64}/[a-z0-9-]{1,64}/[a-z0-9-]{1,64}$",
        RegexOptions.CultureInvariant);
    private readonly string _lock;
    private readonly string _owner;
    private readonly string _epoch;
    private readonly string _authDb;
    private readonly string _scope;
    private readonly uint _ownerUid;
    private readonly ulong _expectedLockInode;
    private readonly uint _expectedDeviceMajor;
    private readonly uint _expectedDeviceMinor;

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int OpenNative([MarshalAs(UnmanagedType.LPUTF8Str)] string path, int flags);
    [DllImport("libc", EntryPoint = "flock", SetLastError = true)]
    private static extern int Flock(int fd, int operation);
    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int CloseNative(int fd);
    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint EffectiveUid();
    [DllImport("libc", EntryPoint = "statx", SetLastError = true)]
    private static extern int Statx(int fd, [MarshalAs(UnmanagedType.LPUTF8Str)] string path,
        int flags, uint mask, IntPtr data);

    private readonly record struct Inode(ulong Number, uint DeviceMajor, uint DeviceMinor,
        uint Uid, ushort Mode, uint Nlink);

    private static Inode ReadIdentity(int fd, string path, int flags)
    {
        var buffer = Marshal.AllocHGlobal(256);
        try
        {
            for (var i = 0; i < 256; i += 8)
                Marshal.WriteInt64(buffer, i, 0);
            if (Statx(fd, path, flags, STATX_BASIC_STATS, buffer) != 0)
                throw new IOException("Recovery lock identity cannot be verified.");
            var mask = unchecked((uint)Marshal.ReadInt32(buffer));
            if ((mask & STATX_BASIC_STATS) != STATX_BASIC_STATS)
                throw new IOException("Recovery lock identity is incomplete.");
            return new Inode(
                unchecked((ulong)Marshal.ReadInt64(buffer, 32)),
                unchecked((uint)Marshal.ReadInt32(buffer, 136)),
                unchecked((uint)Marshal.ReadInt32(buffer, 140)),
                unchecked((uint)Marshal.ReadInt32(buffer, 20)),
                unchecked((ushort)Marshal.ReadInt16(buffer, 28)),
                unchecked((uint)Marshal.ReadInt32(buffer, 16)));
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    private static void RequireOwner(Inode stat, uint uid)
    {
        // S_IFREG=0100000, S_IFDIR=0040000; deny group/other write.
        if (stat.Uid != uid || stat.Nlink == 0 || (stat.Mode & 0x12) != 0)
            throw new IOException("Recovery owner metadata is not protected.");
    }

    public static bool LegacyDatabaseHasRecoveryMarker(string dbPath)
    {
        if (string.IsNullOrWhiteSpace(dbPath) || !File.Exists(dbPath))
            return false;
        using var db = ReadOnly(dbPath);
        using var cmd = db.CreateCommand();
        cmd.CommandText = """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='auth_recovery_mirror';
            """;
        return Convert.ToInt32(cmd.ExecuteScalar(), CultureInfo.InvariantCulture) != 0;
    }

    public static ProjectAuthRecoveryAdmission? FromConfiguration(
        IConfiguration config, string authDbPath)
    {
        var mode = config[Prefix + "Mode"];
        if (string.IsNullOrEmpty(mode))
        {
            // Partial loss of recovery configuration must not silently
            // downgrade even when the Auth DB has disappeared or been
            // replaced with a pre-enrollment snapshot. B additionally owns
            // the protected host policy and forbids old-image restarts.
            foreach (var suffix in new[] {
                "OwnerRoot", "EpochDbPath", "Scope", "OwnerUid",
                "LockInode", "LockDeviceMajor", "LockDeviceMinor" })
                if (config[Prefix + suffix] is not null)
                    throw new InvalidOperationException(
                        "Partial Auth recovery config cannot select legacy mode.");
            if (LegacyDatabaseHasRecoveryMarker(authDbPath))
                throw new InvalidOperationException("Auth recovery enrollment forbids legacy rollback.");
            return null;
        }
        if (!string.Equals(mode, Mode, StringComparison.Ordinal))
            throw new InvalidOperationException("Unreviewed Auth recovery mode.");
        if (!OperatingSystem.IsLinux())
            throw new PlatformNotSupportedException("Protected Auth recovery requires Linux.");
        var root = config[Prefix + "OwnerRoot"];
        var epoch = config[Prefix + "EpochDbPath"];
        var scope = config[Prefix + "Scope"];
        if (string.IsNullOrWhiteSpace(root) || !Path.IsPathFullyQualified(root) ||
            string.IsNullOrWhiteSpace(epoch) || !Path.IsPathFullyQualified(epoch) ||
            (string.IsNullOrWhiteSpace(scope) || !ScopePattern.IsMatch(scope)) ||
            !uint.TryParse(config[Prefix + "OwnerUid"], NumberStyles.None,
                CultureInfo.InvariantCulture, out var ownerUid) ||
            ownerUid == 0 || ownerUid == EffectiveUid() ||
            !ulong.TryParse(config[Prefix + "LockInode"], NumberStyles.None,
                CultureInfo.InvariantCulture, out var inode) || inode == 0 ||
            !uint.TryParse(config[Prefix + "LockDeviceMajor"], NumberStyles.None,
                CultureInfo.InvariantCulture, out var major) ||
            !uint.TryParse(config[Prefix + "LockDeviceMinor"], NumberStyles.None,
                CultureInfo.InvariantCulture, out var minor))
            throw new InvalidOperationException("Exact protected operator and lock identity required.");
        return new ProjectAuthRecoveryAdmission(
            root, epoch, authDbPath, scope, ownerUid, inode, major, minor);
    }

    public ProjectAuthRecoveryAdmission(string root, string epochDb, string authDb,
        string scope, uint ownerUid, ulong lockInode,
        uint lockDeviceMajor, uint lockDeviceMinor)
    {
        if (!OperatingSystem.IsLinux())
            throw new PlatformNotSupportedException();
        if (!Path.IsPathFullyQualified(root) || !Path.IsPathFullyQualified(epochDb) ||
            !Path.IsPathFullyQualified(authDb) || (string.IsNullOrWhiteSpace(scope) || !ScopePattern.IsMatch(scope)) ||
            ownerUid == 0 || ownerUid == EffectiveUid() || lockInode == 0)
            throw new ArgumentException("Separate absolute operator-owned recovery scope required.");
        var canonicalRoot = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var canonicalEpoch = Path.GetFullPath(epochDb);
        var canonicalAuth = Path.GetFullPath(authDb);
        if (canonicalEpoch == canonicalAuth ||
            canonicalEpoch.StartsWith(canonicalRoot + Path.DirectorySeparatorChar,
                StringComparison.Ordinal) ||
            canonicalAuth.StartsWith(canonicalRoot + Path.DirectorySeparatorChar,
                StringComparison.Ordinal))
            throw new ArgumentException("Recovery owner, Auth and epoch stores require distinct roots.");
        _lock = Path.Combine(canonicalRoot, "auth-recovery.lock");
        _owner = Path.Combine(canonicalRoot, "auth-recovery-control.sqlite");
        _epoch = canonicalEpoch;
        _authDb = canonicalAuth;
        _scope = scope;
        _ownerUid = ownerUid;
        _expectedLockInode = lockInode;
        _expectedDeviceMajor = lockDeviceMajor;
        _expectedDeviceMinor = lockDeviceMinor;
    }

    private static SqliteConnection ReadOnly(string path)
    {
        if (!File.Exists(path) || new FileInfo(path).LinkTarget is not null)
            throw new IOException("Required recovery store is unavailable.");
        var db = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = path, Mode = SqliteOpenMode.ReadOnly, Pooling = false
        }.ToString());
        db.Open();
        return db;
    }

    /// <summary>
    /// Observes the same protected lock and durable external hold/mirror/epoch
    /// under one kernel fence. Returns FALSE on any missing/uncertain state.
    /// TRUE only confirms a coherent HOLD; it NEVER authorizes a request.
    /// </summary>
    public bool HasConsistentHold()
    {
        try
        {
            using var hold = AcquireProtectedLock();
            // An owner-only HOLD cannot be stored on a runtime-owned or
            // hard-linked SQLite file, even if its content currently matches.
            var ownerFile = ReadIdentity(AT_FDCWD, _owner, AT_SYMLINK_NOFOLLOW);
            RequireOwner(ownerFile, _ownerUid);
            if ((ownerFile.Mode & 0xF000) != 0x8000 || ownerFile.Nlink != 1)
                throw new IOException("Operator control store identity is unsafe.");
            using var owner = ReadOnly(_owner);
            using var mirror = ReadOnly(_authDb);
            using var epoch = ReadOnly(_epoch);
            static string? Value(SqliteConnection db, string sql)
            {
                using var cmd = db.CreateCommand();
                cmd.CommandText = sql;
                return cmd.ExecuteScalar() as string;
            }
            var external = Value(owner, """
                SELECT operation_id || ':' || scope_id FROM auth_recovery_control
                WHERE singleton=1 AND schema_version=1 AND phase='HELD';
                """);
            var local = Value(mirror, """
                SELECT operation_id || ':' || scope_id FROM auth_recovery_mirror
                WHERE singleton=1 AND schema_version=1 AND phase='HELD';
                """);
            var scopedEpoch = Value(epoch, """
                SELECT scope_id FROM auth_recovery_epoch
                WHERE singleton=1 AND schema_version=1;
                """);
            return !string.IsNullOrWhiteSpace(external) &&
                string.Equals(external, local, StringComparison.Ordinal) &&
                string.Equals(scopedEpoch, _scope, StringComparison.Ordinal) &&
                external.EndsWith(":" + _scope, StringComparison.Ordinal);
        }
        catch (Exception ex) when (ex is IOException or SqliteException
            or InvalidOperationException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private IDisposable AcquireProtectedLock()
    {
        var parent = Path.GetDirectoryName(_lock)!;
        var directory = ReadIdentity(AT_FDCWD, parent, AT_SYMLINK_NOFOLLOW);
        RequireOwner(directory, _ownerUid);
        if ((directory.Mode & 0xF000) != 0x4000)
            throw new IOException("Recovery parent must be a real directory.");
        int fd = OpenNative(_lock, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0)
            throw new IOException("Recovery lock unavailable.");
        try
        {
            var opened = ReadIdentity(fd, "", AT_EMPTY_PATH);
            var named = ReadIdentity(AT_FDCWD, _lock, AT_SYMLINK_NOFOLLOW);
            RequireOwner(opened, _ownerUid);
            // A same-name replacement must not become the new fence authority,
            // even when the owning UID and mode are otherwise unchanged.
            // B must pin these exact values in its owner-reviewed placement.
            if (opened.Number != _expectedLockInode ||
                opened.DeviceMajor != _expectedDeviceMajor ||
                opened.DeviceMinor != _expectedDeviceMinor)
                throw new IOException("Recovery lock identity differs from reviewed placement.");
            if ((opened.Mode & 0xF000) != 0x8000 || opened.Nlink != 1 || opened != named ||
                Flock(fd, LOCK_EX | LOCK_NB) != 0)
                throw new IOException("Recovery fence unavailable or substituted.");
            // After taking the fence, inspect again against same opened inode;
            // a rename cannot silently turn a new pathname into authority.
            if (opened != ReadIdentity(AT_FDCWD, _lock, AT_SYMLINK_NOFOLLOW))
                throw new IOException("Recovery fence identity changed.");
            return new NativeLock(fd);
        }
        catch
        {
            CloseNative(fd);
            throw;
        }
    }

    private sealed class NativeLock(int fd) : IDisposable
    {
        private int _fd = fd;
        public void Dispose()
        {
            if (_fd < 0) return;
            Flock(_fd, LOCK_UN);
            CloseNative(_fd);
            _fd = -1;
        }
    }
}
