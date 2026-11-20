"""Read-only Auth DB restore boundary checks for Deployment Kit issue #115.

This deliberately cannot start a restore, trust a receipt, lock Auth epoch
state, clear holds, manipulate Docker, or claim application recovery readiness.
An Auth Kit-owned, versioned fence/receipt/reconcile contract is mandatory
before an operation that mutates a live Auth database can be implemented.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat

from .app_runtime import AUTH_EPOCH_ENV_KEY, AUTH_EPOCH_ROOT, AUTH_EPOCH_TARGET
from .auth_recovery_guard import verify_running_auth_container
from .errors import DeploymentKitError

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[0-9]+:[0-9]+$")
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_OWNER = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SET = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8,32}$")
_MAX_DB_SIZE = 8 * 1024**3


def _path(path: Path) -> Path:
    """Require an existing absolute canonical path with no symlink component."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise DeploymentKitError("Auth restore path must be absolute.")
    if path != Path(os.path.abspath(path)):
        raise DeploymentKitError("Auth restore path contains an unsafe traversal.")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise DeploymentKitError("Auth restore path contains a symlink.")
    return path


def _private_directory(path: Path) -> Path:
    path = _path(path)
    try:
        info = path.lstat()
    except OSError:
        raise DeploymentKitError("Auth restore directory is unavailable.") from None
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise DeploymentKitError("Auth restore directory is not owner-private.")
    return path


def _separate(a: Path, b: Path) -> bool:
    return a != b and a not in b.parents and b not in a.parents


def _private_backup_file(path: Path):
    path = _path(path)
    try:
        info = path.lstat()
    except OSError:
        raise DeploymentKitError("Selected Auth backup is unavailable.") from None
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            stat.S_IMODE(info.st_mode) & 0o077 or
            not 0 < info.st_size <= _MAX_DB_SIZE):
        raise DeploymentKitError("Selected Auth backup is not a private regular SQLite file.")
    return info


def _backup_sha256(path: Path, initial) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        after = _private_backup_file(path)
    except OSError:
        raise DeploymentKitError("Selected Auth backup could not be read.") from None
    if (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise DeploymentKitError("Selected Auth backup changed during preflight.")
    return digest.hexdigest()


def _verify_sqlite_read_only(path: Path) -> None:
    connection = None
    try:
        # The backup set must be checkpointed: never consult a mutable WAL.
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise DeploymentKitError("Selected Auth backup failed SQLite integrity.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DeploymentKitError("Selected Auth backup has foreign-key violations.")
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        raise DeploymentKitError("Selected Auth backup is not valid SQLite.") from None
    finally:
        if connection is not None:
            connection.close()


def _verify_epoch_runtime_mount(observed: dict, source: str) -> None:
    """Match the #112 external mount/environment, without reading epoch data."""
    if type(observed) is not dict or type(observed.get("Mounts")) is not list:
        raise DeploymentKitError("Auth runtime epoch mount evidence is unavailable.")
    mounts = observed["Mounts"]
    if any(type(m) is not dict or type(m.get("Destination")) is not str
           for m in mounts):
        raise DeploymentKitError("Malformed Auth runtime mount evidence.")
    matches = [m for m in mounts if m["Destination"] == AUTH_EPOCH_TARGET]
    if (len(matches) != 1 or matches[0].get("Type") != "bind" or
            matches[0].get("RW") is not True or matches[0].get("Source") != source):
        raise DeploymentKitError("Auth runtime epoch mount identity differs from reviewed target.")
    anchor = PurePosixPath(AUTH_EPOCH_TARGET)
    for mount in mounts:
        other = PurePosixPath(mount["Destination"])
        if other != anchor and (other in anchor.parents or anchor in other.parents):
            raise DeploymentKitError("Auth runtime contains an overlapping epoch mount.")
    config = observed.get("Config")
    if type(config) is not dict or type(config.get("Env")) is not list:
        raise DeploymentKitError("Auth runtime epoch setting evidence is unavailable.")
    setting = AUTH_EPOCH_ENV_KEY + "=" + AUTH_EPOCH_TARGET + "/state.sqlite"
    entries = [v for v in config["Env"] if type(v) is str and
               v.split("=", 1)[0] == AUTH_EPOCH_ENV_KEY]
    if entries != [setting]:
        raise DeploymentKitError("Auth runtime epoch path differs from reviewed target.")


def inspect_auth_restore_boundary(
    *, inventory: dict, observed_container: dict, reviewed_docker_binding: dict,
    owner_repo: str, app_slug: str, environment: str, reviewed_image: str,
    expected_epoch_identity: str, backup_root: Path, backup_database: Path,
    expected_backup_sha256: str,
) -> dict[str, object]:
    """Read-only evidence, NOT a plan permitting mutation or traffic release.

    The caller must get inventory, inspected Docker identity, the image digest
    mapping, expected epoch identity and backup digest from independently
    reviewed sources. All checks must be repeated under the eventual Kit host
    lock and Auth-owned epoch fence before a live DB restore.
    """
    if (type(owner_repo) is not str or not _OWNER.fullmatch(owner_repo) or
            type(app_slug) is not str or not _SLUG.fullmatch(app_slug) or
            type(environment) is not str or not _SLUG.fullmatch(environment) or
            type(reviewed_image) is not str or not reviewed_image or
            type(expected_epoch_identity) is not str or
            not _ID.fullmatch(expected_epoch_identity) or
            type(expected_backup_sha256) is not str or
            not _SHA.fullmatch(expected_backup_sha256)):
        raise DeploymentKitError("Reviewed Auth restore identity or backup digest is invalid.")
    if (type(inventory) is not dict or type(inventory.get("applications")) is not list or
            type(reviewed_docker_binding) is not dict):
        raise DeploymentKitError("Exact Auth restore runtime evidence is unavailable.")
    matches = [app for app in inventory["applications"] if type(app) is dict and
               app.get("appSlug") == app_slug and app.get("environment") == environment]
    if len(matches) != 1:
        raise DeploymentKitError("Auth restore Project/environment is absent or ambiguous.")
    current = matches[0]
    source = str(Path(AUTH_EPOCH_ROOT) / app_slug / environment)
    epoch = current.get("authenticationEpochStore")
    if (current.get("ownerRepo") != owner_repo or
            current.get("image") != reviewed_image or
            current.get("persistenceMode") != "directory" or
            current.get("containerRunning") is not True or
            current.get("containerPresent") is not True or
            current.get("imageMatchesRelease") is not True or
            current.get("authenticationEpochMountVerified") is not True or
            type(epoch) is not dict or epoch.get("hostPath") != source or
            epoch.get("containerPath") != AUTH_EPOCH_TARGET or
            epoch.get("sourceIdentity") != expected_epoch_identity):
        raise DeploymentKitError("Auth restore target or external epoch store has drifted.")
    if (reviewed_docker_binding.get("expected_owner") != owner_repo or
            reviewed_docker_binding.get("expected_environment") != environment or
            reviewed_docker_binding.get("container_name") != current.get("containerName")):
        raise DeploymentKitError("Auth restore Docker binding differs from Project identity.")
    proof = verify_running_auth_container(observed_container, **reviewed_docker_binding)
    _verify_epoch_runtime_mount(observed_container, source)

    root = _private_directory(backup_root)
    selected = _path(backup_database)
    if (selected.name != "auth.sqlite" or
            not _SET.fullmatch(selected.parent.name) or
            selected.parent.parent != root):
        raise DeploymentKitError("Auth restore backup selection is not an exact recovery set.")
    _private_directory(selected.parent)
    data = _path(Path(reviewed_docker_binding["expected_data_source"]))
    epoch_path = Path(source)
    if (not _separate(root, data) or not _separate(root, epoch_path) or
            not _separate(data, epoch_path)):
        raise DeploymentKitError("Auth restore backup, live data and epoch store overlap.")
    for extension in ("-wal", "-shm", "-journal"):
        sidecar = Path(str(selected) + extension)
        if sidecar.exists() or sidecar.is_symlink():
            raise DeploymentKitError("Selected Auth backup has uncheckpointed sidecars.")
    initial = _private_backup_file(selected)
    actual_sha = _backup_sha256(selected, initial)
    if actual_sha != expected_backup_sha256:
        raise DeploymentKitError("Selected Auth backup differs from reviewed artifact digest.")
    _verify_sqlite_read_only(selected)
    # Recheck after SQLite reads (never turn preflight into a trusted receipt).
    if _backup_sha256(selected, initial) != actual_sha:
        raise DeploymentKitError("Selected Auth backup changed during SQLite verification.")
    return {
        "runtimeId": proof["runtimeId"],
        "imageDigest": proof["imageDigest"],
        "epochSourceIdentity": expected_epoch_identity,
        "backupDatabaseSha256": actual_sha,
        "backupArtifactIntegrityVerified": True,
        "restoreReceiptTrusted": False,
        "authenticationPolicyVerified": False,
        "applicationRecoveryReady": False,
    }
