"""Disposable-only Auth Kit backup lifecycle with exclusive host locking.

This is a low-level *explicitly authorized* local Linux driver, not a cron
job, Production command, generic application recovery proof or public CLI.
It never provisions providers or modifies Caddy/Cloudflare. The only Docker
mutations are stop/start of the exact pre-reviewed disposable container ID.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from .auth_recovery_capture import (
    _load_pinned_helper, capture_reviewed_stopped_auth_project,
)
from .auth_recovery_guard import verify_running_auth_container, verify_stopped_auth_container
from .errors import DeploymentKitError


def _real_private_directory(directory: Path) -> Path:
    path = Path(os.path.abspath(directory))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise DeploymentKitError("Auth recovery path contains a symlink.")
    try:
        mode = path.lstat()
    except OSError:
        raise DeploymentKitError("Auth recovery directory is unavailable.") from None
    if not stat.S_ISDIR(mode.st_mode) or stat.S_IMODE(mode.st_mode) & 0o077:
        raise DeploymentKitError("Auth recovery directory must be owner-private.")
    return path


def _separated(path: Path, other: Path) -> bool:
    a = Path(os.path.abspath(path))
    b = Path(os.path.abspath(other))
    return a != b and a not in b.parents and b not in a.parents


@contextmanager
def _exclusive_lifecycle_lock(lock_directory: Path):
    import fcntl  # Linux-only, deferred so other Project tools still import on Windows.

    directory = _real_private_directory(lock_directory)
    lock_path = directory / "auth-backup.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError:
        raise DeploymentKitError("Private Auth backup lock could not be opened.") from None
    try:
        status = os.fstat(fd)
        if (not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or
                stat.S_IMODE(status.st_mode) & 0o077):
            raise DeploymentKitError("Auth recovery lock is not a private regular file.")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentKitError("Another Auth recovery operation holds the lock.") from None
        yield
    finally:
        os.close(fd)


def _docker_inspect(docker: str, container_name: str) -> dict:
    try:
        result = subprocess.run(
            [docker, "inspect", "--format", "{{json .}}", container_name],
            text=True, capture_output=True, timeout=15, check=False,
            encoding="utf-8", errors="replace",
        )
        if (result.returncode != 0 or
                not 0 < len(result.stdout) <= 256 * 1024):
            raise DeploymentKitError("Exact disposable Docker inspection failed.")
        observed = json.loads(result.stdout)
        if type(observed) is not dict:
            raise DeploymentKitError("Malformed disposable Docker state.")
        return observed
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise DeploymentKitError("Exact disposable Docker inspection unavailable.") from None


def _docker_action(docker: str, action: str, runtime_id: str):
    if action not in {"stop", "start"}:
        raise DeploymentKitError("Unsupported Auth lifecycle action.")
    argv = ([docker, "stop", "--time", "20", runtime_id] if action == "stop"
            else [docker, "start", runtime_id])
    try:
        result = subprocess.run(
            argv, text=True, capture_output=True, timeout=40,
            check=False, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DeploymentKitError("Disposable Auth Docker lifecycle action failed.") from None
    if result.returncode != 0:
        # Docker stderr/stdout must never be logged (may expose host state).
        raise DeploymentKitError("Disposable Auth Docker lifecycle action was rejected.")


def _resume_exact_disposable(
    docker: str, binding: dict, initial: dict
) -> bool:
    """Attempt resumption only of the original reviewed container identity."""
    current = _docker_inspect(docker, binding["container_name"])
    try:
        running = verify_running_auth_container(current, **binding)
        if running["runtimeId"] == initial["runtimeId"]:
            return True  # Concurrently resumed: no duplicate start needed.
    except DeploymentKitError:
        pass
    # A changed/missing container or ownership drift MUST NOT be started.
    stopped = verify_stopped_auth_container(current, **binding)
    if stopped["runtimeId"] != initial["runtimeId"]:
        raise DeploymentKitError("Disposable Auth identity changed; manual recovery required.")
    _docker_action(docker, "start", initial["runtimeId"])
    resumed = verify_running_auth_container(
        _docker_inspect(docker, binding["container_name"]), **binding)
    if resumed["runtimeId"] != initial["runtimeId"]:
        raise DeploymentKitError("Disposable Auth identity drift after start.")
    return True


RESTART_JOURNAL = "auth-backup-restart.json"


def _binding_fingerprint(binding: dict) -> str:
    """Bind private restart intent to an independently reviewed Docker identity.

    Only a SHA-256 fingerprint is retained, never raw environment settings.
    """
    if type(binding) is not dict:
        raise DeploymentKitError("Reviewed Docker binding is unavailable.")
    allowed = {
        "container_name", "expected_owner", "expected_environment",
        "expected_image_digest", "expected_data_source",
        "expected_data_destination", "owner_label", "environment_label",
        "required_auth_environment",
    }
    if set(binding) != allowed or not isinstance(binding["expected_data_source"], Path):
        raise DeploymentKitError("Reviewed Docker binding is incomplete.")
    normalized = {
        **binding,
        "expected_data_source": str(Path(os.path.abspath(binding["expected_data_source"]))),
    }
    try:
        encoded = json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DeploymentKitError("Reviewed Docker binding is malformed.") from exc
    return hashlib.sha256(encoded).hexdigest()


def _journal_payload(binding: dict, initial: dict, backup_name: str) -> dict:
    import re
    if (type(initial) is not dict or
            type(initial.get("runtimeId")) is not str or
            re.fullmatch(r"[0-9a-f]{64}", initial["runtimeId"]) is None or
            type(initial.get("imageDigest")) is not str or
            re.fullmatch(r"sha256:[0-9a-f]{64}", initial["imageDigest"]) is None or
            initial["imageDigest"] != binding.get("expected_image_digest") or
            type(backup_name) is not str or not 1 <= len(backup_name) <= 128 or
            "/" in backup_name or "\\" in backup_name):
        raise DeploymentKitError("Unsafe original Docker identity for recovery journal.")
    return {
        "schemaVersion": 1,
        "purpose": "disposable-auth-resume",
        "runtimeId": initial["runtimeId"],
        "imageDigest": initial["imageDigest"],
        "bindingFingerprint": _binding_fingerprint(binding),
        "backupSetName": backup_name,
    }


def _sync_private_directory(directory: Path) -> None:
    if sys.platform != "linux":
        raise DeploymentKitError("Durable Auth journal requires Linux.")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(directory, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        raise DeploymentKitError("Durable Auth recovery journal synchronization failed.") from None


def _create_restart_journal(lock_directory: Path, binding: dict,
                            initial: dict, backup_name: str) -> None:
    """Durably publish *before* stopping Docker; never overwrite prior intent."""
    directory = _real_private_directory(lock_directory)
    payload = _journal_payload(binding, initial, backup_name)
    path = directory / RESTART_JOURNAL
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        raise DeploymentKitError("Existing or unsafe pending Auth restart journal.") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _sync_private_directory(directory)
    except Exception:
        # If persistence is uncertain, retain the journal and refuse stop.
        raise DeploymentKitError("Durable Auth restart journal could not be committed.") from None


def _read_restart_journal(lock_directory: Path, binding: dict) -> dict | None:
    directory = _real_private_directory(lock_directory)
    path = directory / RESTART_JOURNAL
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError:
        raise DeploymentKitError("Auth restart journal cannot be safely read.") from None
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or
                stat.S_IMODE(st.st_mode) & 0o077 or not 0 < st.st_size <= 4096):
            raise DeploymentKitError("Auth restart journal is not an owner-private regular file.")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            content = handle.read(4097)
        if len(content) > 4096:
            raise DeploymentKitError("Auth restart journal exceeds size limit.")
        def unique_pairs(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError("Duplicate journal key")
                out[key] = value
            return out
        value = json.loads(content, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, OSError) as exc:
        raise DeploymentKitError("Auth restart journal is malformed.") from None
    finally:
        if fd >= 0:
            os.close(fd)
    if (type(value) is not dict or
            set(value) != {
                "schemaVersion", "purpose", "runtimeId", "imageDigest",
                "bindingFingerprint", "backupSetName",
            } or type(value["schemaVersion"]) is not int or
            value["schemaVersion"] != 1 or
            value["purpose"] != "disposable-auth-resume" or
            value["bindingFingerprint"] != _binding_fingerprint(binding)):
        raise DeploymentKitError("Auth journal does not match reviewed Docker identity.")
    _journal_payload(binding, {
        "runtimeId": value["runtimeId"],
        "imageDigest": value["imageDigest"],
    }, value["backupSetName"])
    return value


def _clear_restart_journal(lock_directory: Path, binding: dict) -> None:
    current = _read_restart_journal(lock_directory, binding)
    if current is None:
        raise DeploymentKitError("Required Auth restart journal disappeared.")
    try:
        os.unlink(Path(lock_directory) / RESTART_JOURNAL)
    except OSError:
        raise DeploymentKitError("Auth restart journal could not be cleared.") from None
    _sync_private_directory(Path(lock_directory))


def recover_interrupted_disposable_auth(
    *, lock_directory: Path, reviewed_docker_binding: dict,
    authorize_disposable_resume: bool = False,
) -> dict:
    """Explicitly resume only the original journaled disposable Docker ID.

    A separately supervised service or human may invoke this when the
    capture process was interrupted. No installed timer, start unit or
    Production CLI is provided. Health and traffic readiness remain unknown.
    """
    if sys.platform != "linux" or authorize_disposable_resume is not True:
        raise DeploymentKitError("Explicit Linux disposable Auth recovery authorization required.")
    binding = reviewed_docker_binding
    if type(binding) is not dict or binding.get("expected_environment") != "disposable":
        raise DeploymentKitError("Only reviewed disposable Auth recovery is supported.")
    with _exclusive_lifecycle_lock(lock_directory):
        journal = _read_restart_journal(lock_directory, binding)
        if journal is None:
            return {
                "state": "no-pending-restart",
                "mutated": False,
                "runtimeResumedVerified": False,
                "healthVerified": False,
                "applicationRecoveryReady": False,
            }
        docker = shutil.which("docker")
        if docker is None:
            raise DeploymentKitError("Docker is unavailable for Auth restart recovery.")
        was_stopped = False
        current = _docker_inspect(docker, binding["container_name"])
        try:
            current_proof = verify_stopped_auth_container(current, **binding)
            was_stopped = True
        except DeploymentKitError:
            current_proof = verify_running_auth_container(current, **binding)
        if current_proof["runtimeId"] != journal["runtimeId"]:
            raise DeploymentKitError("Journaled original Docker ID changed; manual recovery required.")
        resumed = _resume_exact_disposable(
            docker, binding, {
                "runtimeId": journal["runtimeId"],
                "imageDigest": journal["imageDigest"],
            })
        if resumed is not True:
            raise DeploymentKitError("Journaled Auth resumption not proven.")
        _clear_restart_journal(lock_directory, binding)
        return {
            "state": "original-disposable-running",
            "mutated": was_stopped,
            "runtimeResumedVerified": True,
            "healthVerified": False,
            "applicationRecoveryReady": False,
            "scheduledBackupVerified": False,
            "alertInboxReceiptVerified": False,
            "normalTrafficReadinessProven": False,
        }


def capture_with_disposable_service_pause(
    *, project_root: Path, source_data_root: Path, destination: Path,
    lock_directory: Path, declaration: dict, reviewed_auth_revision: str,
    reviewed_recovery_sha256: str, reviewed_docker_binding: dict,
    authorize_disposable_stop: bool = False,
) -> dict:
    """Capture an exact disposable Auth Project, then prove Docker is running.

    The caller authorizes this single controlled disposable stop/start. This
    function cannot guarantee service health, normal traffic readiness,
    backup scheduling, secure host recovery from process death, or provider
    recovery. No Production execution and no CLI entrypoint are provided.
    """
    if sys.platform != "linux":
        raise DeploymentKitError("Disposable Auth lifecycle requires Linux Docker.")
    if authorize_disposable_stop is not True:
        raise DeploymentKitError("Explicit disposable Auth stop authorization required.")
    if type(reviewed_docker_binding) is not dict or set(reviewed_docker_binding) != {
        "container_name", "expected_owner", "expected_environment",
        "expected_image_digest", "expected_data_source",
        "expected_data_destination", "owner_label", "environment_label",
        "required_auth_environment",
    }:
        raise DeploymentKitError("Reviewed exact disposable Docker binding required.")
    binding = reviewed_docker_binding
    if binding.get("expected_environment") != "disposable":
        raise DeploymentKitError("Only disposable Auth containers may be controlled.")
    project = Path(os.path.abspath(project_root))
    source = Path(os.path.abspath(source_data_root))
    destination = Path(os.path.abspath(destination))
    lock = _real_private_directory(lock_directory)
    backup_parent = _real_private_directory(destination.parent)
    if (not _separated(source, project) or not _separated(destination, source)
            or not _separated(destination, project)
            or not _separated(backup_parent, source)
            or not _separated(backup_parent, project)
            or not _separated(lock, source) or not _separated(lock, project)
            or not _separated(lock, backup_parent)):
        raise DeploymentKitError("Disposable source, Project, backups and lock must be isolated.")
    if destination.exists() or destination.is_symlink():
        raise DeploymentKitError("Refusing existing Auth backup destination.")
    # Verify pinned managed helper and declaration BEFORE ever stopping a
    # service, to avoid downtime for an unsupported Auth version.
    helper = _load_pinned_helper(project, reviewed_auth_revision, reviewed_recovery_sha256)
    try:
        helper.validate_declaration(declaration)
        if not helper._valid_set_name(destination.name):
            raise ValueError("Invalid canonical set name")
    except Exception:
        raise DeploymentKitError("Auth recovery declaration or set name is invalid.") from None
    if (not isinstance(binding["expected_data_source"], Path)
            or Path(os.path.abspath(binding["expected_data_source"])) != source
            or type(binding["expected_data_destination"]) is not str
            or type(binding["required_auth_environment"]) is not dict):
        raise DeploymentKitError("Auth Docker source and environment bindings differ.")
    mount = binding["expected_data_destination"].rstrip("/")
    env = binding["required_auth_environment"]
    if (env.get("ProjectForge__Authentication__DbPath") != mount + "/auth.sqlite"
            or env.get("ProjectForge__Authentication__DataProtectionKeysPath")
            != mount + "/keys"):
        raise DeploymentKitError("Auth SQLite and key-ring bindings differ.")
    _real_private_directory(source)
    docker = shutil.which("docker")
    if not docker:
        raise DeploymentKitError("Linux Docker is unavailable.")

    with _exclusive_lifecycle_lock(lock):
        if destination.exists() or destination.is_symlink():
            raise DeploymentKitError("Recovery destination appeared while acquiring lock.")
        initial = verify_running_auth_container(
            _docker_inspect(docker, binding["container_name"]), **binding)
        _create_restart_journal(lock, binding, initial, destination.name)
        failure = False
        resumed = False
        capture = None
        stop_attempted = False
        try:
            stop_attempted = True
            _docker_action(docker, "stop", initial["runtimeId"])
            stopped = verify_stopped_auth_container(
                _docker_inspect(docker, binding["container_name"]), **binding)
            if stopped["runtimeId"] != initial["runtimeId"]:
                raise DeploymentKitError("Container identity changed while stopping.")
            capture = capture_reviewed_stopped_auth_project(
                project_root=project, source_data_root=source,
                destination=destination, declaration=declaration,
                reviewed_auth_revision=reviewed_auth_revision,
                reviewed_recovery_sha256=reviewed_recovery_sha256,
                reviewed_docker_binding=binding,
            )
        except Exception:
            failure = True
        finally:
            if stop_attempted:
                try:
                    resumed = _resume_exact_disposable(docker, binding, initial)
                except Exception:
                    # Journal deliberately remains for independent recovery.
                    raise DeploymentKitError(
                        "Disposable Auth resumption not proven; manual recovery required."
                    ) from None
                if resumed:
                    _clear_restart_journal(lock, binding)
        if failure or capture is None:
            raise DeploymentKitError(
                "Disposable Auth capture failed; original container is running."
            ) from None
        return {
            "backupArtifactIntegrityVerified": (
                capture.get("backupArtifactIntegrityVerified") is True
            ),
            "runtimeResumedVerified": resumed,
            "healthVerified": False,
            "applicationRecoveryReady": False,
            "scheduledBackupVerified": False,
            "alertInboxReceiptVerified": False,
            "normalTrafficReadinessProven": False,
            "quiescenceGuardRuntimeId": initial["runtimeId"],
            "quiescenceGuardImageDigest": initial["imageDigest"],
        }
