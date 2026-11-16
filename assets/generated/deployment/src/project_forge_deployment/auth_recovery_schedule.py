"""Owner-private, disposable-only Auth backup operation orchestration.

A reviewed operator may invoke this from a separately installed systemd
oneshot/timer. Nothing in this module installs, enables, or dispatches units.
No Production backup, provider interaction, or Health/restore-ready claim.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

from .auth_recovery_lifecycle import (
    _binding_fingerprint,
    _read_restart_journal,
    _real_private_directory,
    _separated,
    _sync_private_directory,
    capture_with_disposable_service_pause,
    recover_interrupted_disposable_auth,
)
from .errors import DeploymentKitError


_STATUS = "auth-backup-status.json"
_ATTEMPTS = "attempts"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED = {
    "schemaVersion", "environment", "projectRoot", "sourceDataRoot",
    "backupsRoot", "lockDirectory", "statusDirectory",
    "authRevision", "recoverySha256", "declaration", "dockerBinding",
}
_BINDING = {
    "container_name", "expected_owner", "expected_environment",
    "expected_image_digest", "expected_data_source",
    "expected_data_destination", "owner_label", "environment_label",
    "required_auth_environment",
}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(now: datetime) -> str:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise DeploymentKitError("UTC Auth backup clock required.")
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _regular_private_file(path: Path, *, missing_ok: bool = False) -> bool:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise DeploymentKitError("Auth operation path contains a symlink.")
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise DeploymentKitError("Private Auth operation file is unavailable.") from None
    except OSError:
        raise DeploymentKitError("Private Auth operation file cannot be inspected.") from None
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            stat.S_IMODE(info.st_mode) & 0o077 or not 0 < info.st_size <= 64 * 1024):
        raise DeploymentKitError("Private Auth operation file has unsafe size, mode or identity.")
    return True


def _read_json(path: Path) -> dict:
    _regular_private_file(path)
    expected = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            observed = os.fstat(handle.fileno())
            if ((observed.st_dev, observed.st_ino, observed.st_nlink) !=
                    (expected.st_dev, expected.st_ino, expected.st_nlink) or
                    not stat.S_ISREG(observed.st_mode) or
                    stat.S_IMODE(observed.st_mode) & 0o077 or
                    observed.st_size > 65536):
                raise ValueError("private file changed during open")
            text = handle.read(65537)
        if len(text) > 65536:
            raise ValueError("oversize")
        def unique_pairs(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate field")
                value[key] = item
            return value
        value = json.loads(text, object_pairs_hook=unique_pairs)
    except (OSError, ValueError, UnicodeError):
        raise DeploymentKitError("Private Auth operation JSON is invalid.") from None
    if type(value) is not dict:
        raise DeploymentKitError("Private Auth operation JSON must be an object.")
    return value


def _project_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise DeploymentKitError("Reviewed Auth Project root must be absolute.")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise DeploymentKitError("Reviewed Auth Project root cannot contain symlinks.")
    if not path.is_dir():
        raise DeploymentKitError("Reviewed Auth Project root is unavailable.")
    return path


def load_disposable_operation_config(path: Path) -> dict:
    """Parse a strict, protected, non-secret operator-reviewed config.

    The actual Docker owner/image/mount, source revision and Auth declaration
    must come from a separately reviewed generated-Project acceptance record.
    The config is not that review or permission to touch Production.
    """
    if sys.platform != "linux":
        raise DeploymentKitError("Disposable Auth scheduled operations require Linux.")
    path = Path(os.path.abspath(path))
    _real_private_directory(path.parent)
    raw = _read_json(path)
    if set(raw) != _ALLOWED or type(raw.get("schemaVersion")) is not int or (
            raw["schemaVersion"] != 1 or raw["environment"] != "disposable"):
        raise DeploymentKitError("Only exact disposable Auth operation configuration is supported.")
    fields = ("projectRoot", "sourceDataRoot", "backupsRoot", "lockDirectory", "statusDirectory")
    if any(type(raw.get(key)) is not str or not Path(raw[key]).is_absolute()
           for key in fields):
        raise DeploymentKitError("Auth operation paths must be absolute.")
    project = _project_directory(Path(raw["projectRoot"]))
    source = _real_private_directory(Path(raw["sourceDataRoot"]))
    backups = _real_private_directory(Path(raw["backupsRoot"]))
    lock = _real_private_directory(Path(raw["lockDirectory"]))
    status = _real_private_directory(Path(raw["statusDirectory"]))
    _real_private_directory(status / _ATTEMPTS)  # Preflight before any Docker stop.
    paths = (project, source, backups, lock, status)
    if any(not _separated(one, two) for i, one in enumerate(paths)
           for two in paths[i + 1:]):
        raise DeploymentKitError("Auth operation directories must be separate.")
    if (not isinstance(raw.get("authRevision"), str) or
            _HEX40.fullmatch(raw["authRevision"]) is None or
            not isinstance(raw.get("recoverySha256"), str) or
            _HEX64.fullmatch(raw["recoverySha256"]) is None or
            type(raw.get("declaration")) is not dict):
        raise DeploymentKitError("Auth recovery source or declaration is not exact.")
    binding = raw.get("dockerBinding")
    if type(binding) is not dict or set(binding) != _BINDING:
        raise DeploymentKitError("Exact reviewed disposable Docker binding is required.")
    if (binding.get("expected_environment") != "disposable" or
            type(binding.get("expected_data_source")) is not str or
            Path(binding["expected_data_source"]) != source):
        raise DeploymentKitError("Auth operation container/data owner does not match.")
    binding = {**binding, "expected_data_source": source}
    if (type(binding["required_auth_environment"]) is not dict or
            set(binding["required_auth_environment"]) != {
                "ProjectForge__Authentication__DbPath",
                "ProjectForge__Authentication__DataProtectionKeysPath",
            }):
        raise DeploymentKitError("Auth operation may only pin canonical DB and key-ring mounts.")
    _binding_fingerprint(binding)
    return {
        "project": project, "source": source, "backups": backups, "lock": lock,
        "status": status, "revision": raw["authRevision"],
        "helperSha": raw["recoverySha256"],
        "declaration": raw["declaration"], "binding": binding,
    }


@contextmanager
def _operation_lock(directory: Path):
    import fcntl

    directory = _real_private_directory(directory)
    file = directory / "auth-operation.lock"
    try:
        fd = os.open(file, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        raise DeploymentKitError("Auth operation lock cannot be safely opened.") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                stat.S_IMODE(info.st_mode) & 0o077):
            raise DeploymentKitError("Auth operation lock is not private.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentKitError("Another Auth backup operation is running.") from None
        yield
    finally:
        os.close(fd)


def _write_private_json(path: Path, value: dict, *, replace: bool) -> None:
    directory = _real_private_directory(path.parent)
    if replace:
        _regular_private_file(path, missing_ok=True)
    elif path.exists() or path.is_symlink():
        raise DeploymentKitError("Refusing existing immutable Auth attempt receipt.")
    blob = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(blob) > 16 * 1024:
        raise DeploymentKitError("Auth operation receipt exceeds safe size.")
    temp = directory / ("." + secrets.token_hex(16) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temp, path)
        else:
            # Atomic no-overwrite publication; source temp remains private.
            os.link(temp, path, follow_symlinks=False)
        _sync_private_directory(directory)
    except OSError:
        raise DeploymentKitError("Private Auth operation receipt could not be committed.") from None
    finally:
        if temp.exists():
            temp.unlink()
            _sync_private_directory(directory)


def _valid_utc_timestamp(value: object) -> bool:
    if type(value) is not str or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)


def _validate_status(value: dict) -> None:
    if (set(value) != {"schemaVersion", "lastAttempt", "lastSuccess", "lastResumption"}
            or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1):
        raise DeploymentKitError("Auth operation status schema is invalid.")
    attempt = value["lastAttempt"]
    if attempt is not None:
        if (type(attempt) is not dict or set(attempt) != {
                "id", "setName", "startedAt", "completedAt", "outcome",
                "backupArtifactIntegrityVerified", "runtimeResumedVerified",
                "applicationRecoveryReady", "healthVerified",
                "alertInboxReceiptVerified",
            } or type(attempt["id"]) is not str or
                re.fullmatch(r"[0-9a-f]{32}", attempt["id"]) is None or
                type(attempt["setName"]) is not str or
                re.fullmatch(r"20[0-9]{6}T[0-9]{6}Z-[0-9a-f]{32}",
                             attempt["setName"]) is None or
                not _valid_utc_timestamp(attempt["startedAt"]) or
                type(attempt["outcome"]) is not str or
                attempt["outcome"] not in {"in-progress", "success", "failed"} or
                any(type(attempt[key]) is not bool for key in (
                    "backupArtifactIntegrityVerified", "runtimeResumedVerified",
                    "applicationRecoveryReady", "healthVerified",
                    "alertInboxReceiptVerified")) or
                attempt["applicationRecoveryReady"] is not False or
                attempt["healthVerified"] is not False or
                attempt["alertInboxReceiptVerified"] is not False or
                (attempt["completedAt"] is None) !=
                    (attempt["outcome"] == "in-progress") or
                (attempt["completedAt"] is not None and
                 not _valid_utc_timestamp(attempt["completedAt"]))):
            raise DeploymentKitError("Auth attempt receipt is malformed.")
    success = value["lastSuccess"]
    if success is not None:
        if (type(success) is not dict or
                set(success) != {"setName", "completedAt"} or
                type(success["setName"]) is not str or
                re.fullmatch(r"20[0-9]{6}T[0-9]{6}Z-[0-9a-f]{32}",
                             success["setName"]) is None or
                not _valid_utc_timestamp(success["completedAt"])):
            raise DeploymentKitError("Auth last-success evidence is malformed.")
    resumption = value["lastResumption"]
    if resumption is not None:
        if (type(resumption) is not dict or
                set(resumption) != {"checkedAt", "state", "runtimeResumedVerified"} or
                not _valid_utc_timestamp(resumption["checkedAt"]) or
                type(resumption["state"]) is not str or
                resumption["state"] not in {
                    "failed", "no-pending-restart", "original-disposable-running",
                } or type(resumption["runtimeResumedVerified"]) is not bool):
            raise DeploymentKitError("Auth last-resumption evidence is malformed.")


def _previous_status(directory: Path) -> dict:
    path = directory / _STATUS
    if not _regular_private_file(path, missing_ok=True):
        return {"schemaVersion": 1, "lastAttempt": None, "lastSuccess": None,
                "lastResumption": None}
    value = _read_json(path)
    _validate_status(value)
    return value


def _commit_status(config: dict, value: dict) -> None:
    _write_private_json(config["status"] / _STATUS, value, replace=True)


def _receipt(config: dict, attempt: dict) -> None:
    root = config["status"] / _ATTEMPTS
    _real_private_directory(root)
    _write_private_json(root / (attempt["id"] + ".json"), attempt, replace=False)


def run_reviewed_disposable_backup(
    config: dict, *, authorize_disposable_stop: bool = False,
    now: datetime | None = None,
) -> dict:
    """One explicitly authorized operation, suitable for a reviewed one-shot.

    A systemd timer is never installed or enabled by calling this. Success
    means capture integrity + original Docker ID resumed, not application
    health, full recovery, provider or alert inbox proof.
    """
    if sys.platform != "linux" or authorize_disposable_stop is not True:
        raise DeploymentKitError("Explicit disposable Auth backup authorization required.")
    with _operation_lock(config["status"]):
        status = _previous_status(config["status"])
        started = _clock() if now is None else now
        attempt_id = secrets.token_hex(16)
        name = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + attempt_id
        attempt = {"id": attempt_id, "setName": name, "startedAt": _stamp(started),
                   "completedAt": None, "outcome": "in-progress",
                   "backupArtifactIntegrityVerified": False,
                   "runtimeResumedVerified": False,
                   "applicationRecoveryReady": False,
                   "healthVerified": False, "alertInboxReceiptVerified": False}
        status["lastAttempt"] = attempt
        _commit_status(config, status)  # Durable BEFORE stopping the container.
        try:
            capture = capture_with_disposable_service_pause(
                project_root=config["project"], source_data_root=config["source"],
                destination=config["backups"] / name, lock_directory=config["lock"],
                declaration=config["declaration"],
                reviewed_auth_revision=config["revision"],
                reviewed_recovery_sha256=config["helperSha"],
                reviewed_docker_binding=config["binding"],
                authorize_disposable_stop=True,
            )
            if (capture.get("backupArtifactIntegrityVerified") is not True or
                    capture.get("runtimeResumedVerified") is not True):
                raise DeploymentKitError("Auth backup integrity or Docker resumption not proven.")
            attempt["backupArtifactIntegrityVerified"] = True
            attempt["runtimeResumedVerified"] = True
            attempt["outcome"] = "success"
        except Exception:
            # Do not write raw Docker/Auth messages (or credentials) to status.
            attempt["outcome"] = "failed"
        attempt["completedAt"] = _stamp(_clock() if now is None else now)
        _receipt(config, attempt)
        status["lastAttempt"] = attempt
        if attempt["outcome"] == "success":
            status["lastSuccess"] = {
                "setName": name, "completedAt": attempt["completedAt"]}
            # A later fully verified capture proves the exact original
            # container resumed. Clear an older unverified/failed recovery
            # signal only on this independent, journal-protected evidence.
            status["lastResumption"] = {
                "checkedAt": attempt["completedAt"],
                "state": "original-disposable-running",
                "runtimeResumedVerified": True,
            }
        _commit_status(config, status)
        if attempt["outcome"] != "success":
            raise DeploymentKitError(
                "Disposable Auth backup failed; check the private restart journal and recover."
            ) from None
        return attempt


def run_reviewed_disposable_recovery(
    config: dict, *, authorize_disposable_resume: bool = False,
) -> dict:
    """Independent rescue entrypoint after the capture worker exits/dies."""
    if sys.platform != "linux" or authorize_disposable_resume is not True:
        raise DeploymentKitError("Explicit disposable Auth recovery authorization required.")
    with _operation_lock(config["status"]):
        status = _previous_status(config["status"])
        try:
            result = recover_interrupted_disposable_auth(
                lock_directory=config["lock"],
                reviewed_docker_binding=config["binding"],
                authorize_disposable_resume=True)
        except Exception:
            status["lastResumption"] = {
                "checkedAt": _stamp(_clock()), "state": "failed",
                "runtimeResumedVerified": False}
            _commit_status(config, status)
            raise DeploymentKitError(
                "Exact original Auth Docker recovery could not be proven."
            ) from None
        status["lastResumption"] = {
            "checkedAt": _stamp(_clock()),
            "state": result["state"],
            "runtimeResumedVerified": result["runtimeResumedVerified"] is True}
        _commit_status(config, status)
        return result


def inspect_disposable_backup_status(config: dict, *, now: datetime | None = None,
                                     max_age_hours: int = 48) -> dict:
    """Read-only alert candidate summary; does NOT send an alert."""
    if type(max_age_hours) is not int or not 1 <= max_age_hours <= 720:
        raise DeploymentKitError("Auth backup maximum age is unsupported.")
    status = _previous_status(config["status"])
    journal = _read_restart_journal(config["lock"], config["binding"])
    current = _clock() if now is None else now
    previous = status["lastAttempt"]
    success = status["lastSuccess"]
    if journal is not None:
        state = "recovery-required"
    elif (status["lastResumption"] is not None and
          status["lastResumption"]["state"] == "failed"):
        # Even if the last backup was valid, an unresolved exact-Docker
        # resumption failure is a host operation failure, never fresh.
        state = "recovery-failed"
    elif (status["lastResumption"] is not None and
          status["lastResumption"]["runtimeResumedVerified"] is not True):
        # "No pending restart" does NOT inspect/prove a running container.
        # It must not silently clear an earlier failed recovery.
        state = "recovery-unverified"
    elif previous is not None and previous.get("outcome") == "failed":
        state = "backup-failed"
    elif previous is not None and previous.get("outcome") == "in-progress":
        state = "interrupted-or-running"
    elif success is None:
        state = "no-backup"
    else:
        try:
            at = datetime.fromisoformat(success["completedAt"].replace("Z", "+00:00"))
            state = ("fresh" if at <= current <= at + timedelta(hours=max_age_hours)
                     else "overdue")
        except (TypeError, KeyError, ValueError):
            raise DeploymentKitError("Private Auth success timestamp is invalid.") from None
    return {
        "state": state, "lastAttempt": previous,
        "lastSuccess": success, "lastResumption": status["lastResumption"],
        "scheduledBackupVerified": False,
        "healthVerified": False,
        "alertInboxReceiptVerified": False,
        "applicationRecoveryReady": False,
        "mutated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Disposable Auth Kit backup runner (not Production)")
    parser.add_argument("action", choices=["backup", "recover", "status"])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--authorize-disposable-stop", action="store_true")
    parser.add_argument("--authorize-disposable-resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_disposable_operation_config(args.config)
        if args.action == "backup":
            result = run_reviewed_disposable_backup(
                config, authorize_disposable_stop=args.authorize_disposable_stop)
            print("Disposable Auth backup: verified artifact; original Docker running.")
            print("Set: " + result["setName"])
        elif args.action == "recover":
            result = run_reviewed_disposable_recovery(
                config, authorize_disposable_resume=args.authorize_disposable_resume)
            print("Disposable Auth original Docker recovery state: " + result["state"])
        else:
            state = inspect_disposable_backup_status(config)["state"]
            print("Disposable Auth operation: " + state)
            # A scheduler/monitor must not mistake stale/failed backups or
            # pending exact-Docker recovery for an operational success.
            # No alert is sent; nonzero status is an observable host signal.
            if state != "fresh":
                return 2
        return 0
    except DeploymentKitError:
        print("BLOCKED: Disposable Auth backup operation cannot be verified.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
