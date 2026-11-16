#!/usr/bin/env python3
"""Fail-closed Auth Kit recovery capture, isolated materialization and verification.

Low-level library only: never stops a service, replaces live Project data, or
claims application/session readiness. Deployment must independently verify
quiescence and perform dynamic protector/policy checks before live traffic.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

SHA = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
ALLOWED_POLICIES = {"preserve-authentication", "invalidate-authentication"}
MAX_KEYS = 128
MAX_KEY_BYTES = 1024 * 1024
MAX_DB_BYTES = 1024 * 1024 * 1024 * 8


class RecoveryError(ValueError):
    """A recovery qualification invariant has failed."""


def _object(value: object, fields: set[str], context: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise RecoveryError(f"{context}: unexpected or missing fields")
    return value


def _regular(path: Path, *, directory: bool = False) -> os.stat_result:
    """Never follow a symlink in an owned recovery-set path."""
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise RecoveryError("Recovery set contains a symlink")
    try:
        status = path.lstat()
    except OSError as exc:
        raise RecoveryError("Recovery set member is missing") from exc
    if (stat.S_ISDIR(status.st_mode) if directory else
            stat.S_ISREG(status.st_mode)) is not True:
        raise RecoveryError("Unexpected recovery-set filesystem member")
    return status


def validate_declaration(value: object) -> dict:
    """Validate non-secret Project-owned recovery intent, not runtime paths."""
    row = _object(value, {
        "schemaVersion", "projectId", "authenticationPolicy",
        "database", "keyRing", "protectorGeneration",
        "providerRecoveryDependencies"
    }, "declaration")
    if type(row["schemaVersion"]) is not int or row["schemaVersion"] != 1:
        raise RecoveryError("Unsupported recovery declaration version")
    if type(row["projectId"]) is not str or not ID.fullmatch(row["projectId"]):
        raise RecoveryError("Invalid Project identity")
    if type(row["authenticationPolicy"]) is not str or row["authenticationPolicy"] not in ALLOWED_POLICIES:
        raise RecoveryError("Explicit authentication recovery policy required")
    database = _object(row["database"], {"artifact", "format"}, "database")
    if database != {"artifact": "auth.sqlite", "format": "sqlite3"}:
        raise RecoveryError("Unsupported database artifact")
    ring = _object(row["keyRing"], {"directory", "required"}, "keyRing")
    if ring != {"directory": "keys", "required": True}:
        raise RecoveryError("Persistent DataProtection key ring is required")
    generation = row["protectorGeneration"]
    if type(generation) is not str or not re.fullmatch(r"[0-9a-f]{32}", generation):
        raise RecoveryError("Invalid protector generation fingerprint")
    dependencies = row["providerRecoveryDependencies"]
    if type(dependencies) is not list or len(dependencies) > 16:
        raise RecoveryError("Invalid external dependency declaration")
    if (any(type(x) is not str or not ID.fullmatch(x) for x in dependencies) or
            len(set(dependencies)) != len(dependencies)):
        raise RecoveryError("External dependencies must be unique non-secret IDs")
    return row


def _sha256(path: Path, limit: int) -> str:
    status = _regular(path)
    if status.st_size <= 0 or status.st_size > limit or status.st_nlink != 1:
        raise RecoveryError("Recovery artifact size/link count not accepted")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    if _regular(path).st_size != status.st_size:
        raise RecoveryError("Recovery artifact changed during validation")
    return digest.hexdigest()


def inspect_isolated_set(root: Path, declaration: dict, receipt: object) -> dict:
    """Check inert set integrity; NEVER report applicationRecoveryReady=true.

    root must be a private, isolated, disposable directory unrelated to the
    live Project data. The caller is responsible for verifying that placement.
    """
    validate_declaration(declaration)
    record = _object(receipt, {
        "schemaVersion", "projectId", "protectorGeneration", "policy",
        "databaseSha256", "keys"
    }, "receipt")
    if type(record["schemaVersion"]) is not int or record["schemaVersion"] != 1:
        raise RecoveryError("Unsupported recovery receipt")
    if (type(record["projectId"]) is not str or
            type(record["protectorGeneration"]) is not str or
            type(record["policy"]) is not str or
            record["projectId"] != declaration["projectId"] or
            record["protectorGeneration"] != declaration["protectorGeneration"] or
            record["policy"] != declaration["authenticationPolicy"]):
        raise RecoveryError("Recovery policy/identity/generation mismatch")
    root = Path(root)
    _regular(root, directory=True)
    db = root / "auth.sqlite"
    keys = root / "keys"
    _regular(keys, directory=True)
    if type(record["databaseSha256"]) is not str or not SHA.fullmatch(record["databaseSha256"]):
        raise RecoveryError("Invalid database hash")
    members = sorted(x.name for x in root.iterdir())
    if members not in (["auth.sqlite", "keys"], ["auth.sqlite", "keys", "receipt.json"]):
        raise RecoveryError("Unknown or partial recovery-set top-level files")
    if "receipt.json" in members:
        receipt_path = root / "receipt.json"
        if _regular(receipt_path).st_size > 32 * 1024:
            raise RecoveryError("Recovery receipt is oversized")
        try:
            stored = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise RecoveryError("Recovery receipt cannot be read") from exc
        if stored != receipt:
            raise RecoveryError("Private recovery receipt mismatch")
    if any((root / x).exists() or (root / x).is_symlink() for x in
           ("auth.sqlite-wal", "auth.sqlite-shm", "auth.sqlite-journal")):
        raise RecoveryError("Uncheckpointed database transaction artifacts")
    if _sha256(db, MAX_DB_BYTES) != record["databaseSha256"]:
        raise RecoveryError("Database artifact hash mismatch")
    entries = record["keys"]
    if type(entries) is not dict or not 1 <= len(entries) <= MAX_KEYS:
        raise RecoveryError("Missing or excessive key material")
    if any(type(name) is not str for name in entries):
        raise RecoveryError("Malformed key inventory names")
    observed = sorted(x.name for x in keys.iterdir())
    if observed != sorted(entries):
        raise RecoveryError("Unrecognized or missing key material")
    for name, digest in entries.items():
        if (type(name) is not str or not re.fullmatch(r"key-[A-Za-z0-9-]{1,120}\.xml", name)
                or type(digest) is not str or not SHA.fullmatch(digest)):
            raise RecoveryError("Malformed key inventory")
        if _sha256(keys / name, MAX_KEY_BYTES) != digest:
            raise RecoveryError("Key material hash mismatch")

    # SQLite URI read-only mode prevents a verifier from accidentally creating
    # a fresh database; mode=ro must not be construed as application validation.
    conn = None
    try:
        conn = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        fk = conn.execute("PRAGMA foreign_key_check").fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()
        tables = {
            item[0] for item in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected_columns = {
            "accounts": {
                "id", "email", "normalized_email", "email_verified",
                "is_admin", "disabled", "created_utc",
            },
            "external_identities": {"account_id", "issuer", "subject"},
            "invitations": {
                "id", "recipient_email", "recipient_normalized", "token_hash",
                "expires_utc", "consumed_utc", "created_by", "created_utc",
            },
            "sessions": {
                "token_hash", "account_id", "created_utc", "expires_utc",
                "revoked_utc",
            },
        }
        if (integrity != ("ok",) or fk is not None or version != (1,) or
                tables != set(expected_columns)):
            raise RecoveryError("Auth Kit schema or SQLite integrity invalid")
        for name, columns in expected_columns.items():
            found = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(" + name + ")").fetchall()
            }
            if found != columns:
                raise RecoveryError("Auth Kit schema column mismatch")
    except sqlite3.DatabaseError as exc:
        raise RecoveryError("SQLite recovery artifact is invalid") from exc
    finally:
        if conn is not None:
            conn.close()
    return {
        "backupArtifactIntegrityVerified": True,
        "isolatedArtifactInspectionComplete": True,
        "protectorViabilityVerified": False,
        "authenticationPolicyVerified": False,
        "applicationRecoveryReady": False,
        "scheduledBackupVerified": False,
        "alertInboxReceiptVerified": False,
        "unresolvedRequiredDependencies": [
            "dynamic-protector-proof", "authentication-policy-proof",
            *declaration["providerRecoveryDependencies"],
        ],
    }



def _exclusive_publish_directory(stage: Path, destination: Path) -> None:
    """Atomic directory publication with OS-level NO-REPLACE semantics.

    A preceding exists() check is insufficient: on POSIX, rename() can
    silently replace an existing *empty directory*. Unsupported filesystems
    fail closed; we do not fall back to an unsafe check-then-rename.
    """
    import ctypes
    import errno
    import sys

    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RecoveryError("Atomic no-replace directory rename unavailable")
        renameat2.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        status = renameat2(-100, source, -100, target, 1)  # RENAME_NOREPLACE
        if status != 0:
            failure = ctypes.get_errno()
            if failure in (errno.EEXIST, errno.ENOTEMPTY):
                raise RecoveryError("Recovery destination already exists")
            raise RecoveryError("Atomic recovery publication unavailable")
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex = getattr(libc, "renamex_np", None)
        if renamex is None:
            raise RecoveryError("Atomic no-replace directory rename unavailable")
        renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex.restype = ctypes.c_int
        if renamex(source, target, 0x00000004) != 0:  # RENAME_EXCL
            failure = ctypes.get_errno()
            if failure in (errno.EEXIST, errno.ENOTEMPTY):
                raise RecoveryError("Recovery destination already exists")
            raise RecoveryError("Atomic recovery publication unavailable")
    elif os.name == "nt":
        # Windows MoveFile-style os.rename refuses an existing destination.
        try:
            os.rename(stage, destination)
        except FileExistsError as exc:
            raise RecoveryError("Recovery destination already exists") from exc
        except OSError as exc:
            raise RecoveryError("Atomic recovery publication unavailable") from exc
    else:
        raise RecoveryError("Atomic no-replace directory rename unsupported")


def _disjoint(a: Path, b: Path) -> bool:
    """Compare normalized lexical paths; any symlink ancestor is rejected separately."""
    x = Path(os.path.abspath(a))
    y = Path(os.path.abspath(b))
    return x != y and x not in y.parents and y not in x.parents


def _copy_verified_file(source: Path, destination: Path, expected_hash: str,
                        limit: int) -> None:
    """Create an exclusive private file from a no-follow source descriptor."""
    import shutil

    if _sha256(source, limit) != expected_hash:
        raise RecoveryError("Recovery source changed before copy")
    before = _regular(source)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    handle = os.open(source, flags)
    try:
        opened = os.fstat(handle)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev, before.st_ino, before.st_size
        ):
            raise RecoveryError("Recovery artifact changed during open")
        with os.fdopen(os.dup(handle), "rb") as inp, destination.open("xb") as out:
            if os.name != "nt":
                os.chmod(destination, 0o600)
            shutil.copyfileobj(inp, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
    finally:
        os.close(handle)
    if _sha256(destination, limit) != expected_hash:
        raise RecoveryError("Recovery copy is incomplete or corrupted")
    if _sha256(source, limit) != expected_hash:
        raise RecoveryError("Recovery source changed during copy")


def materialize_disposable_restore(
    backup_set: Path, destination: Path, live_data_root: Path,
    declaration: dict, receipt: dict,
) -> dict:
    """Materialize a hash-verified private restore into a NEW disposable path.

    Does NOT run an app, rewrite live data, rotate keys, preserve sessions by
    itself or assert application recovery. The caller must supply the exact
    current live-data root and isolate the new destination from it and the
    backup set. No Production restore CLI is exposed.
    """
    import shutil
    import tempfile

    validate_declaration(declaration)
    backup_set = Path(os.path.abspath(backup_set))
    destination = Path(os.path.abspath(destination))
    live_data_root = Path(os.path.abspath(live_data_root))
    _regular(backup_set, directory=True)
    _regular(live_data_root, directory=True)
    parent = destination.parent
    _regular(parent, directory=True)
    if (not _disjoint(destination, live_data_root) or
            not _disjoint(destination, backup_set) or
            not _disjoint(parent, live_data_root) or
            not _disjoint(parent, backup_set) or
            not _disjoint(backup_set, live_data_root)):
        raise RecoveryError("Restore, backup and live data must be isolated")
    if os.name != "nt" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise RecoveryError("Disposable restore parent must be owner-private")
    if destination.exists() or destination.is_symlink():
        raise RecoveryError("Refusing to replace existing disposable data")
    if not (backup_set / "receipt.json").is_file():
        raise RecoveryError("Immutable recovery set requires a private receipt")
    inspect_isolated_set(backup_set, declaration, receipt)
    stage = Path(tempfile.mkdtemp(prefix=".auth-restore-", dir=parent))
    try:
        if os.name != "nt":
            os.chmod(stage, 0o700)
        (stage / "keys").mkdir(mode=0o700)
        _copy_verified_file(backup_set / "auth.sqlite", stage / "auth.sqlite",
                            receipt["databaseSha256"], MAX_DB_BYTES)
        for name, digest in receipt["keys"].items():
            _copy_verified_file(backup_set / "keys" / name, stage / "keys" / name,
                                digest, MAX_KEY_BYTES)
        _copy_verified_file(
            backup_set / "receipt.json", stage / "receipt.json",
            _sha256(backup_set / "receipt.json", 32 * 1024), 32 * 1024)
        inspect_isolated_set(stage, declaration, receipt)
        _exclusive_publish_directory(stage, destination)
        return {
            "isolatedRestoreMaterialized": True,
            "backupArtifactIntegrityVerified": True,
            "protectorViabilityVerified": False,
            "authenticationPolicyVerified": False,
            "applicationRecoveryReady": False,
            "normalTrafficAllowed": False,
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage)



RECOVERY_SET_NAME = re.compile(r"^(20[0-9]{6}T[0-9]{6}Z)-[0-9a-f]{8,32}$")
MAX_INVENTORY_SETS = 1000


def _valid_set_name(name: str) -> bool:
    from datetime import datetime

    if type(name) is not str:
        return False
    match = RECOVERY_SET_NAME.fullmatch(name)
    if match is None:
        return False
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError:
        return False
    return True


def plan_verified_retention(
    sets_root: Path, declaration: dict, *, keep_last: int = 7
) -> dict:
    """Read-only retention preview of fully verified immutable recovery sets.

    Fail closed if any set is corrupt, incomplete, symlinked, misidentified or
    ambiguously named; never delete a set, stage, or application directory.
    A retention plan is NOT a scheduled backup/restore/notification proof.
    """
    validate_declaration(declaration)
    if type(keep_last) is not int or not 2 <= keep_last <= 365:
        raise RecoveryError("Retention minimum must preserve at least two sets")
    sets_root = Path(sets_root)
    root_status = _regular(sets_root, directory=True)
    if os.name != "nt" and stat.S_IMODE(root_status.st_mode) & 0o077:
        raise RecoveryError("Recovery-set inventory must be owner-private")
    names = sorted(p.name for p in sets_root.iterdir())
    if len(names) > MAX_INVENTORY_SETS:
        raise RecoveryError("Recovery-set inventory count exceeds safe limit")
    if any(not _valid_set_name(name) for name in names):
        raise RecoveryError("Unknown, staging or malformed recovery-set name")
    verified = []
    for name in names:
        candidate = sets_root / name
        _regular(candidate, directory=True)
        receipt_path = candidate / "receipt.json"
        if _regular(receipt_path).st_size > 32 * 1024:
            raise RecoveryError("Recovery receipt exceeds size limit")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise RecoveryError("Recovery set receipt is not readable") from exc
        report = inspect_isolated_set(candidate, declaration, receipt)
        if report["backupArtifactIntegrityVerified"] is not True:
            raise RecoveryError("Unverified recovery set in retention inventory")
        verified.append(name)
    eligible = verified[:-keep_last] if len(verified) > keep_last else []
    return {
        "recoverySetCount": len(verified),
        "verifiedRecoverySetNames": verified,
        "retainedRecoverySetNames": verified[-keep_last:],
        "retentionCandidateNames": eligible,
        "retentionPlanOnly": True,
        "deletionPerformed": False,
        "scheduledBackupVerified": False,
        "alertInboxReceiptVerified": False,
        "applicationRecoveryReady": False,
    }



def apply_reviewed_disposable_retention(
    sets_root: Path, lock_directory: Path, declaration: dict,
    reviewed_plan: dict, *, keep_last: int = 7,
    environment: str, authorize_disposable_delete: bool = False,
    max_delete: int = 32,
) -> dict:
    """Prune only a reviewed subset of verified *disposable* backup sets.

    This is a low-level, opt-in Linux primitive, not a scheduled operation.
    The caller must independently prove the actual generated-Project owner,
    disposal-only environment, quiesced-capture success, separation from live
    data, and application-level recovery readiness. A complete, unchanged,
    read-only retention plan must have been reviewed before calling.
    A partial filesystem failure is fail-closed and requires manual inspection;
    this function cannot make multi-directory deletion atomic.
    """
    if (sys.platform != "linux" or environment != "disposable" or
            authorize_disposable_delete is not True):
        raise RecoveryError("Explicit disposable Linux retention authorization required")
    import fcntl

    if type(max_delete) is not int or not 1 <= max_delete <= 32:
        raise RecoveryError("Disposable retention deletion bound is invalid")
    sets_root = Path(sets_root)
    lock_directory = Path(lock_directory)
    if (not sets_root.is_absolute() or not lock_directory.is_absolute()
            or sets_root == lock_directory or sets_root in lock_directory.parents
            or lock_directory in sets_root.parents):
        raise RecoveryError("Reviewed backup inventory and lock must be isolated absolute paths")
    root_info = _regular(sets_root, directory=True)
    lock_info = _regular(lock_directory, directory=True)
    if (stat.S_IMODE(root_info.st_mode) & 0o077 or
            stat.S_IMODE(lock_info.st_mode) & 0o077 or
            root_info.st_uid != os.geteuid() or
            lock_info.st_uid != os.geteuid()):
        raise RecoveryError("Disposable retention directories must be owner-owned and private")
    lock_path = lock_directory / "auth-retention.lock"
    lock_fd = -1
    root_fd = -1
    deleted: list[str] = []
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)

    def checked_regular(directory_fd: int, name: str) -> None:
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RecoveryError("Unexpected retention set member; deletion blocked")

    try:
        lock_fd = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        lock_stat = os.fstat(lock_fd)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1 or
                stat.S_IMODE(lock_stat.st_mode) & 0o077):
            raise RecoveryError("Disposable retention lock is not owner-private")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryError("Another disposable retention operation is running") from None

        # No unlink, rename or rmdir occurs until every set has been checked,
        # and the inventory is identical to the caller's exact reviewed plan.
        plan = plan_verified_retention(sets_root, declaration, keep_last=keep_last)
        if type(reviewed_plan) is not dict or reviewed_plan != plan:
            raise RecoveryError("Disposable retention inventory differs from reviewed plan")
        selected = plan["retentionCandidateNames"][:max_delete]
        root_fd = os.open(sets_root, flags)
        opened = os.fstat(root_fd)
        if (opened.st_dev, opened.st_ino) != (root_info.st_dev, root_info.st_ino):
            raise RecoveryError("Disposable retention inventory changed during open")

        for name in selected:
            # Anchor all destructive operations to no-follow directory file
            # descriptors. Never call recursive deletion on a path.
            source_info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISDIR(source_info.st_mode):
                raise RecoveryError("Disposable retention candidate is not a directory")
            set_fd = os.open(name, flags, dir_fd=root_fd)
            try:
                opened_set = os.fstat(set_fd)
                if (opened_set.st_dev, opened_set.st_ino) != (
                        source_info.st_dev, source_info.st_ino):
                    raise RecoveryError("Disposable retention candidate changed during open")
                if sorted(os.listdir(set_fd)) != ["auth.sqlite", "keys", "receipt.json"]:
                    raise RecoveryError("Disposable retention candidate changed after verification")
                checked_regular(set_fd, "auth.sqlite")
                checked_regular(set_fd, "receipt.json")
                key_fd = os.open("keys", flags, dir_fd=set_fd)
                try:
                    key_names = sorted(os.listdir(key_fd))
                    if not 1 <= len(key_names) <= MAX_KEYS:
                        raise RecoveryError("Disposable retention key inventory changed")
                    for key_name in key_names:
                        if not re.fullmatch(r"key-[A-Za-z0-9-]{1,120}\.xml", key_name):
                            raise RecoveryError("Disposable retention key name changed")
                        checked_regular(key_fd, key_name)
                    # Verify all candidate names BEFORE the first unlink.
                    for key_name in key_names:
                        os.unlink(key_name, dir_fd=key_fd)
                    os.fsync(key_fd)
                finally:
                    os.close(key_fd)
                os.rmdir("keys", dir_fd=set_fd)
                os.unlink("receipt.json", dir_fd=set_fd)
                os.unlink("auth.sqlite", dir_fd=set_fd)
                os.fsync(set_fd)
            finally:
                os.close(set_fd)
            os.rmdir(name, dir_fd=root_fd)
            os.fsync(root_fd)
            deleted.append(name)

        # No assumption that deleting a valid old set proves application
        # restore, scheduler operation or delivered alerts.
        after = plan_verified_retention(sets_root, declaration, keep_last=keep_last)
        return {
            "deletedRecoverySetNames": deleted,
            "retainedRecoverySetNames": after["verifiedRecoverySetNames"],
            "deletionPerformed": bool(deleted),
            "retentionPlanOnly": False,
            "scheduledBackupVerified": False,
            "alertInboxReceiptVerified": False,
            "applicationRecoveryReady": False,
        }
    except OSError:
        raise RecoveryError(
            "Disposable retention filesystem operation failed; inspect the private inventory"
        ) from None
    finally:
        if root_fd != -1:
            os.close(root_fd)
        if lock_fd != -1:
            os.close(lock_fd)



def capture_quiesced_set(
    source: Path, destination: Path, declaration: dict, runtime_guard
) -> dict:
    """Stage a private, complete SQLite/key-ring set and atomically publish it.

    This is a low-level primitive, NOT a service-quiescence mechanism. The
    caller must supply a non-mutating guard backed by verified runtime
    introspection, rechecking the exact stopped service before and after
    capture. This function cannot establish that the guard itself is honest;
    it must not be used directly as an operator-ready restore/backup CLI.
    Never call on a Production host without a reviewed Deployment Kit driver.
    """
    import shutil
    import tempfile

    validate_declaration(declaration)
    if not callable(runtime_guard):
        raise RecoveryError("An independently verified runtime guard is required")
    source = Path(source)
    destination = Path(destination)
    if not _valid_set_name(destination.name):
        raise RecoveryError("Recovery set name must be a valid UTC timestamp and random suffix")
    _regular(source, directory=True)
    parent = destination.parent
    _regular(parent, directory=True)
    if destination.exists() or destination.is_symlink():
        raise RecoveryError("Refusing to overwrite an existing recovery set")
    # Backup sets must not live within or contain the live application's data.
    if source == destination or source in destination.parents or destination in source.parents:
        raise RecoveryError("Recovery set and source storage must be isolated")
    if os.name != "nt" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise RecoveryError("Recovery-set parent must be owner-private")
    if sorted(p.name for p in source.iterdir()) != ["auth.sqlite", "keys"]:
        raise RecoveryError("Unexpected source artifact or uncheckpointed WAL")
    db = source / "auth.sqlite"
    keys = source / "keys"
    db_status = _regular(db)
    _regular(keys, directory=True)
    if db_status.st_size <= 0 or db_status.st_size > MAX_DB_BYTES:
        raise RecoveryError("Invalid source database size")
    key_names = sorted(p.name for p in keys.iterdir())
    if not 1 <= len(key_names) <= MAX_KEYS:
        raise RecoveryError("Persistent key ring is missing or excessive")
    for name in key_names:
        if not re.fullmatch(r"key-[A-Za-z0-9-]{1,120}\.xml", name):
            raise RecoveryError("Unrecognized keyring file")
        st = _regular(keys / name)
        if st.st_nlink != 1 or not 0 < st.st_size <= MAX_KEY_BYTES:
            raise RecoveryError("Unsupported keyring file size or hard link")

    def guard() -> dict:
        observed = runtime_guard()
        if (type(observed) is not dict or
                set(observed) != {"stopped", "runtimeId", "imageDigest"} or
                observed["stopped"] is not True or
                type(observed["runtimeId"]) is not str or
                re.fullmatch(r"[0-9a-f]{64}", observed["runtimeId"]) is None or
                type(observed["imageDigest"]) is not str or
                re.fullmatch(r"sha256:[0-9a-f]{64}", observed["imageDigest"]) is None):
            raise RecoveryError("Runtime quiescence/identity was not proven")
        return observed

    before = guard()
    stage = Path(tempfile.mkdtemp(prefix=".auth-recovery-", dir=parent))
    try:
        os.chmod(stage, 0o700)
        (stage / "keys").mkdir(mode=0o700)
        # Read-only immutable source rejects accidental live SQLite creation.
        # SQLite backup produces a single consistent database without a WAL.
        conn = None
        dest_db = None
        try:
            conn = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
            dest_db = sqlite3.connect(stage / "auth.sqlite")
            conn.backup(dest_db)
            dest_db.commit()
        except sqlite3.DatabaseError as exc:
            raise RecoveryError("Quiesced SQLite capture failed") from exc
        finally:
            if dest_db is not None:
                dest_db.close()
            if conn is not None:
                conn.close()
        os.chmod(stage / "auth.sqlite", 0o600)
        receipt_keys: dict[str, str] = {}
        for name in key_names:
            source_file = keys / name
            expected = _regular(source_file)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            handle = os.open(source_file, flags)
            try:
                opened = os.fstat(handle)
                if ((opened.st_dev, opened.st_ino, opened.st_size) !=
                        (expected.st_dev, expected.st_ino, expected.st_size)):
                    raise RecoveryError("Keyring changed during capture")
                dest_file = stage / "keys" / name
                with os.fdopen(os.dup(handle), "rb") as inp, dest_file.open("xb") as out:
                    os.chmod(dest_file, 0o600)
                    shutil.copyfileobj(inp, out, 1024 * 1024)
                    out.flush()
                    os.fsync(out.fileno())
                receipt_keys[name] = _sha256(dest_file, MAX_KEY_BYTES)
            finally:
                os.close(handle)
        if guard() != before:
            raise RecoveryError("Stopped runtime identity changed during capture")
        receipt = {
            "schemaVersion": 1,
            "projectId": declaration["projectId"],
            "protectorGeneration": declaration["protectorGeneration"],
            "policy": declaration["authenticationPolicy"],
            "databaseSha256": _sha256(stage / "auth.sqlite", MAX_DB_BYTES),
            "keys": receipt_keys,
        }
        # Inspect the private set before publication. Runtime/key continuity
        # and application readiness still demand separate dynamic validation.
        # Keep the non-secret manifest inside the private recovery directory,
        # so a later isolated verifier does not depend on a transient return.
        receipt_path = stage / "receipt.json"
        with receipt_path.open("x", encoding="utf-8") as output:
            os.chmod(receipt_path, 0o600)
            json.dump(receipt, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        inspect_isolated_set(stage, declaration, receipt)
        if destination.exists() or destination.is_symlink():
            raise RecoveryError("Recovery destination appeared during staging")
        # Publish exclusively, even if another process races to create an
        # empty destination directory between preflight and publication.
        _exclusive_publish_directory(stage, destination)
        return {
            "setPath": str(destination),
            "receipt": receipt,
            "backupArtifactIntegrityVerified": True,
            "applicationRecoveryReady": False,
            "dynamicProtectorProofRequired": True,
            "quiescenceGuardRuntimeId": before["runtimeId"],
            "quiescenceGuardImageDigest": before["imageDigest"],
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage)
