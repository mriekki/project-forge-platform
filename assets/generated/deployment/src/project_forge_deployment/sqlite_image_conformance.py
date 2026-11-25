"""Opt-in pre-publication SQLite maintenance check on an exact local image.

Only for trusted, reviewed images on a disposable Linux CI worker. This
creates temporary local containers/data, never contacts a deployment target
or registry, and does not authorize publishing or prove recovery readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid

from .errors import DeploymentKitError

IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
DB_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
MAX_FILE_BYTES = 8 * 1024 * 1024
DOCKER_HOST = "unix:///var/run/docker.sock"
LABEL = "com.mriekki.project-forge.sqlite-conformance"


def validate_inputs(image_id, run_as, database_file, database_env, timeout):
    if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
        raise DeploymentKitError("Exact local Docker image ID required.")
    if (sys.platform != "linux" or not hasattr(os, "geteuid") or os.geteuid() == 0
            or run_as != f"{os.geteuid()}:{os.getegid()}" or os.getegid() == 0):
        raise DeploymentKitError("Use a non-root Linux worker matching the reviewed numeric UID:GID.")
    if not isinstance(database_file, str) or not DB_NAME.fullmatch(database_file):
        raise DeploymentKitError("A safe database filename is required.")
    if database_env is not None and (not isinstance(database_env, str)
                                     or not ENV_NAME.fullmatch(database_env)):
        raise DeploymentKitError("Invalid database-path environment variable name.")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        raise DeploymentKitError("Maintenance timeout must be 1 through 120 seconds.")


def snapshot(directory: Path, database_file: str) -> dict[str, str]:
    """Bounded hashes of only the disposable DB and its SQLite sidecars."""
    allowed = {database_file, *(database_file + suffix for suffix in ("-wal", "-shm", "-journal"))}
    result = {}
    for path in directory.iterdir():
        info = path.lstat()
        if (path.name not in allowed or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1 or info.st_uid != os.geteuid()
                or info.st_gid != os.getegid() or info.st_size > MAX_FILE_BYTES):
            raise DeploymentKitError("Unexpected disposable SQLite storage entry.")
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
        if len(data) != info.st_size or len(data) > MAX_FILE_BYTES:
            raise DeploymentKitError("Disposable SQLite storage changed during inspection.")
        result[path.name] = hashlib.sha256(data).hexdigest()
    return result


def validate_database(directory: Path, database_file: str) -> None:
    before = snapshot(directory, database_file)
    if database_file not in before:
        raise DeploymentKitError("First-install did not create the expected database.")
    with (directory / database_file).open("rb") as handle:
        if handle.read(16) != b"SQLite format 3\x00":
            raise DeploymentKitError("First-install did not create a SQLite file header.")
    # An immutable read cannot observe outstanding WAL changes. Require a
    # checkpointed, quiescent fixture instead of silently ignoring a WAL.
    for suffix in ("-wal", "-journal"):
        sidecar = directory / (database_file + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise DeploymentKitError("First-install left uncheckpointed disposable storage.")
    try:
        with sqlite3.connect((directory / database_file).as_uri() + "?mode=ro&immutable=1",
                             uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise DeploymentKitError("Disposable SQLite quick_check failed.")
    except sqlite3.DatabaseError:
        raise DeploymentKitError("First-install did not create a valid SQLite database.") from None
    if snapshot(directory, database_file) != before:
        raise DeploymentKitError("Database integrity inspection changed disposable storage.")


class LocalDocker:
    """Use only the local Unix socket, with an empty temporary client config."""
    def __init__(self, config: Path):
        self.config = config

    def run(self, args, *, timeout=30, check=True):
        env = dict(os.environ)
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
                    "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_API_VERSION"):
            env.pop(key, None)
        try:
            result = subprocess.run(
                ["docker", "--host", DOCKER_HOST, "--config", str(self.config), *args],
                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                timeout=timeout, check=False, env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise DeploymentKitError("Local disposable Docker command failed or timed out.") from None
        if check and result.returncode:
            raise DeploymentKitError("Local disposable Docker command failed.")
        return result

    def inspect(self, kind, identity):
        try:
            records = json.loads(self.run([kind, "inspect", identity]).stdout)
            if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
                raise ValueError()
            return records[0]
        except (ValueError, TypeError):
            raise DeploymentKitError("Invalid disposable Docker inspection response.") from None


class CleanupUnverified(DeploymentKitError):
    """The disposable worker may still contain a container we could not identify/remove."""


def owned_container(info, cid, token, name):
    config = info.get("Config") if isinstance(info, dict) else None
    labels = config.get("Labels") if isinstance(config, dict) else None
    return (isinstance(info, dict) and info.get("Id") == cid
            and info.get("Name") == "/" + name
            and isinstance(labels, dict) and labels.get(LABEL) == token)


def cleanup_container(docker, *, cid, candidate, token, name):
    """Recover only an exact, uniquely identified disposable container.

    A create failure can be ambiguous (the daemon may have accepted it).
    Never remove by a name, partial ID, label filter alone, or contradictory
    evidence. If ownership cannot be reestablished, report uncertainty.
    """
    try:
        if cid is None:
            listed = docker.run(["ps", "-aq", "--no-trunc", "--filter",
                                 f"label={LABEL}={token}"]).stdout.splitlines()
            if len(listed) != 1 or not CONTAINER_ID.fullmatch(listed[0]):
                raise ValueError("unique disposable identity not recovered")
            recovered = listed[0]
            if candidate is not None and candidate != recovered:
                raise ValueError("creation identity conflicts with recovery")
            if not owned_container(docker.inspect("container", recovered), recovered, token, name):
                raise ValueError("disposable ownership not established")
            cid = recovered
        docker.run(["rm", "--force", cid])
    except (DeploymentKitError, OSError, ValueError, TypeError, KeyError, AttributeError):
        # The generated UUID is safe to disclose; no daemon response, host
        # details, credentials or arbitrary labels are included.
        raise CleanupUnverified(
            f"Disposable container cleanup unverified; inspect the isolated worker for "
            f"{LABEL}={token}. Do not publish or prune shared resources."
        ) from None


def maintenance(docker, image_id, run_as, directory, database_file, database_env,
                arguments, *, succeeds, timeout):
    token = uuid.uuid4().hex
    name = f"pf-sqlite-check-{token}"
    args = ["create", "--pull", "never", "--name", name, "--label", f"{LABEL}={token}",
            "--network", "none", "--user", run_as, "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--read-only", "--no-healthcheck",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--mount", f"type=bind,src={directory},dst=/data"]
    if database_env:
        args.extend(("--env", f"{database_env}=/data/{database_file}"))
    args.extend((image_id, *arguments))
    cid = candidate = None
    try:
        output = docker.run(args).stdout.strip()
        if not CONTAINER_ID.fullmatch(output):
            raise DeploymentKitError("Disposable container identity unavailable.")
        candidate = output
        info = docker.inspect("container", candidate)
        if not owned_container(info, candidate, token, name):
            raise DeploymentKitError("Disposable container identity mismatch.")
        cid = candidate
        if info.get("Image") != image_id:
            raise DeploymentKitError("Disposable container image mismatch.")
        config = info.get("Config", {})
        host = info.get("HostConfig", {})
        mounts = info.get("Mounts", [])
        if not isinstance(mounts, list) or any(not isinstance(m, dict) for m in mounts):
            raise DeploymentKitError("Invalid disposable mount inventory.")
        binds = [m for m in mounts if m.get("Type") == "bind"]
        extras = [m for m in mounts if m.get("Type") != "bind"]
        if (config.get("User") != run_as or host.get("NetworkMode") != "none"
                or host.get("Privileged") is not False or host.get("ReadonlyRootfs") is not True
                or host.get("PortBindings") not in (None, {})
                or len(binds) != 1 or len(extras) > 1
                or any(m.get("Type") != "tmpfs" or m.get("Destination") != "/tmp" for m in extras)
                or binds[0].get("Source") != str(directory)
                or binds[0].get("Destination") != "/data"
                or binds[0].get("RW") is not True):
            raise DeploymentKitError("Disposable container execution boundary mismatch.")
        run = docker.run(["start", "--attach", cid], timeout=timeout, check=False)
        state = docker.inspect("container", cid).get("State", {})
        exit_code = state.get("ExitCode")
        if (state.get("Status") != "exited" or state.get("OOMKilled") is not False
                or state.get("Error") != "" or type(exit_code) is not int
                or not 0 <= exit_code < 125 or run.returncode not in (0, exit_code)):
            raise DeploymentKitError("Maintenance did not exit normally within the disposable contract.")
        if (exit_code == 0) != succeeds:
            raise DeploymentKitError("Unexpected SQLite maintenance exit result.")
    finally:
        cleanup_container(docker, cid=cid, candidate=candidate, token=token, name=name)


def run_conformance(image_id: str, run_as: str, database_file: str, *,
                    database_env: str | None = None, timeout: int = 30) -> dict:
    validate_inputs(image_id, run_as, database_file, database_env, timeout)
    checks = []
    with tempfile.TemporaryDirectory(prefix="pf-sqlite-conformance-", dir="/tmp") as raw:
        root = Path(raw).resolve()
        config, data, corrupt, invalid = (root / p for p in ("config", "data", "corrupt", "invalid"))
        for directory in (config, data, corrupt, invalid):
            directory.mkdir(mode=0o700)
        docker = LocalDocker(config)
        image = docker.inspect("image", image_id)
        if image.get("Id") != image_id:
            raise DeploymentKitError("Local image does not match the exact built ID.")
        volumes = image.get("Config", {}).get("Volumes") or {}
        if not isinstance(volumes, dict) or set(volumes) - {"/data"}:
            raise DeploymentKitError("Image declares additional volume mounts; disposable contract unsupported.")

        def invoke(directory, arguments, succeeds):
            maintenance(docker, image_id, run_as, directory, database_file, database_env,
                        arguments, succeeds=succeeds, timeout=timeout)

        invoke(data, ["--migrate", "--first-install"], True)
        validate_database(data, database_file)
        checks.append("first-install-valid-database")
        before = snapshot(data, database_file)
        invoke(data, ["--check-rollback-compatibility"], True)
        if snapshot(data, database_file) != before:
            raise DeploymentKitError("Compatibility command modified disposable SQLite storage.")
        checks.append("compatible-check-preserves-storage")
        invoke(data, ["--migrate", "--first-install"], False)
        if snapshot(data, database_file) != before:
            raise DeploymentKitError("Refused repeated first-install modified storage.")
        checks.append("repeat-first-install-refused-without-change")
        (corrupt / database_file).write_bytes(b"disposable-invalid-sqlite")
        before = snapshot(corrupt, database_file)
        invoke(corrupt, ["--check-rollback-compatibility"], False)
        if snapshot(corrupt, database_file) != before:
            raise DeploymentKitError("Refused damaged database check modified storage.")
        checks.append("damaged-database-refused-without-change")
        for arguments in (["--pf-unsupported-maintenance"],
                          ["--migrate", "--first-install", "--pf-unsupported-maintenance"]):
            invoke(invalid, arguments, False)
            if snapshot(invalid, database_file):
                raise DeploymentKitError("Invalid command modified disposable storage.")
        checks.append("unsupported-arguments-refused")
    return {"schemaVersion": 1, "kind": "disposable-sqlite-image-conformance",
            "imageId": image_id, "runAs": run_as, "checks": checks,
            "network": "none", "dataScope": "disposable-only", "authorizesMutation": False,
            "publicationAuthorized": False, "recoveryReady": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--run-as", required=True)
    parser.add_argument("--database-file", required=True)
    parser.add_argument("--database-env")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    try:
        result = run_conformance(args.image_id, args.run_as, args.database_file,
                                 database_env=args.database_env, timeout=args.timeout)
    except CleanupUnverified as error:
        parser.exit(2, str(error) + "\n")
    except (DeploymentKitError, OSError, ValueError, TypeError, KeyError):
        parser.exit(2, "Disposable SQLite image conformance failed; do not publish. Check disposable worker cleanup.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
