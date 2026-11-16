"""Read-only, exact Docker quiescence evidence for future Auth Kit recovery.

No container stop/restart, backup, key read, provider operation or Production
mutation is performed. Do not expose this primitive as a supported backup
workflow until Deployment Kit owns a reviewed quiescence orchestration driver.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Callable

from .errors import DeploymentKitError

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _exact_dict(value: object, required: set[str], context: str) -> dict:
    if not isinstance(value, dict) or not required.issubset(value):
        raise DeploymentKitError(f"Invalid {context} runtime evidence.")
    return value


def _host_directory_is_real(path: Path) -> None:
    # Local host only. A symlink anywhere in the owned mount path is
    # forbidden even when its final resolution would be inside the root.
    if not path.is_absolute():
        raise DeploymentKitError("Auth recovery data mount must be absolute.")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise DeploymentKitError("Auth recovery mount may not use symlinks.")
    try:
        st = path.lstat()
    except OSError as error:
        raise DeploymentKitError("Auth recovery data directory is unavailable.") from error
    if not stat.S_ISDIR(st.st_mode):
        raise DeploymentKitError("Auth recovery data mount must be a directory.")


def verify_stopped_auth_container(
    observed: dict[str, Any],
    *,
    container_name: str,
    expected_owner: str,
    expected_environment: str,
    expected_image_digest: str,
    expected_data_source: Path,
    expected_data_destination: str,
    owner_label: str,
    environment_label: str,
    required_auth_environment: dict[str, str],
) -> dict[str, object]:
    """Return only non-secret proof for an exactly owned, stopped container.

    The caller must provide expected identity, image, labels, mount and auth
    settings from a reviewed Project deployment receipt. This does not stop
    the application or establish a viable restored application.
    """
    if not _CONTAINER.fullmatch(container_name):
        raise DeploymentKitError("Invalid inspected container name.")
    if not _HEX64.fullmatch(expected_image_digest.removeprefix("sha256:")) or (
        not expected_image_digest.startswith("sha256:")
    ):
        raise DeploymentKitError("An exact immutable Docker image digest is required.")
    if (not isinstance(expected_owner, str) or not expected_owner or
            not isinstance(expected_environment, str) or not expected_environment or
            not isinstance(owner_label, str) or not owner_label or
            not isinstance(environment_label, str) or not environment_label or
            type(required_auth_environment) is not dict or
            not required_auth_environment or
            any(not isinstance(k, str) or not k or not isinstance(v, str)
                for k, v in required_auth_environment.items())):
        raise DeploymentKitError("Exact Auth recovery ownership declaration required.")
    mount_root = Path(expected_data_source)
    _host_directory_is_real(mount_root)
    if (not isinstance(expected_data_destination, str) or
            not expected_data_destination.startswith("/") or
            ".." in expected_data_destination.split("/")):
        raise DeploymentKitError("Invalid reviewed container data destination.")

    info = _exact_dict(observed, {
        "Id", "Name", "Image", "State", "Config", "HostConfig", "Mounts"
    }, "container")
    runtime_id = info["Id"]
    if (not isinstance(runtime_id, str) or not _HEX64.fullmatch(runtime_id) or
            info["Name"] != "/" + container_name or
            info["Image"] != expected_image_digest):
        raise DeploymentKitError("Auth container identity or image drift detected.")
    state = _exact_dict(info["State"], {"Running", "Restarting", "Status"}, "state")
    policy = _exact_dict(info["HostConfig"], {"RestartPolicy"}, "host configuration")
    restart = _exact_dict(policy["RestartPolicy"], {"Name"}, "restart policy")
    if (state["Running"] is not False or state["Restarting"] is not False or
            state["Status"] != "exited" or restart["Name"] != "no"):
        raise DeploymentKitError(
            "Auth recovery requires a stopped, restart-disabled exact container."
        )

    config = _exact_dict(info["Config"], {"Labels", "Env"}, "configuration")
    labels = _exact_dict(config["Labels"], {owner_label, environment_label}, "labels")
    if (labels[owner_label] != expected_owner or
            labels[environment_label] != expected_environment):
        raise DeploymentKitError("Auth runtime ownership labels do not match.")
    raw_env = config["Env"]
    if not isinstance(raw_env, list):
        raise DeploymentKitError("Malformed Auth runtime environment.")
    env: dict[str, str] = {}
    for item in raw_env:
        if not isinstance(item, str) or "=" not in item:
            raise DeploymentKitError("Malformed Auth runtime environment.")
        name, value = item.split("=", 1)
        if name in env or not name:
            raise DeploymentKitError("Duplicate Auth runtime environment key.")
        env[name] = value
    for key, value in required_auth_environment.items():
        if env.get(key) != value:
            raise DeploymentKitError("Auth runtime binding differs from approved receipt.")

    mounts = info["Mounts"]
    if not isinstance(mounts, list):
        raise DeploymentKitError("Malformed Auth container mount inventory.")
    data = [m for m in mounts if isinstance(m, dict)
            and m.get("Destination") == expected_data_destination]
    if (len(data) != 1 or data[0].get("Type") != "bind" or
            data[0].get("RW") is not True or
            data[0].get("Source") != str(mount_root)):
        raise DeploymentKitError("Auth owned data bind is not the reviewed mount.")
    if any(not isinstance(m, dict) for m in mounts):
        raise DeploymentKitError("Malformed Auth container mount inventory.")

    return {
        "stopped": True,
        "runtimeId": runtime_id,
        "imageDigest": expected_image_digest,
    }



def verify_running_auth_container(
    observed: dict[str, Any], **binding: Any
) -> dict[str, object]:
    """Verify the *same* strict Auth owner/image/mount, but in running state.

    Reuse the stopped proof's complete configuration inspection after
    independently checking the actual running state. The normalized copy
    below is verification-only and never sent to Docker.
    """
    if type(observed) is not dict:
        raise DeploymentKitError("Malformed running Auth Docker inspection.")
    state = observed.get("State")
    if (type(state) is not dict or state.get("Running") is not True
            or state.get("Restarting") is not False
            or state.get("Status") != "running"):
        raise DeploymentKitError("Exact Auth container is not running.")
    projection = {
        **observed,
        "State": {**state, "Running": False, "Status": "exited"},
    }
    proof = verify_stopped_auth_container(projection, **binding)
    return {
        "running": True,
        "runtimeId": proof["runtimeId"],
        "imageDigest": proof["imageDigest"],
    }


def docker_auth_quiescence_guard(
    *,
    container_name: str,
    expected_owner: str,
    expected_environment: str,
    expected_image_digest: str,
    expected_data_source: Path,
    expected_data_destination: str,
    owner_label: str,
    environment_label: str,
    required_auth_environment: dict[str, str],
) -> Callable[[], dict[str, object]]:
    """Build a read-only local Linux Docker inspect guard, to call twice.

    Raw Docker inspect includes sensitive environment material. Never log the
    response, return it, or include stderr in user-facing failure messages.
    """
    if sys.platform != "linux":
        raise DeploymentKitError(
            "Auth recovery Docker quiescence requires a reviewed Linux host driver."
        )
    if not _CONTAINER.fullmatch(container_name):
        raise DeploymentKitError("Invalid container identity.")
    docker = shutil.which("docker")
    if docker is None:
        raise DeploymentKitError("Docker runtime is unavailable.")

    def inspect() -> dict[str, object]:
        try:
            cmd = subprocess.run(
                [docker, "inspect", "--format", "{{json .}}", container_name],
                capture_output=True, text=True, check=False,
                timeout=15, encoding="utf-8", errors="replace",
            )
            if cmd.returncode != 0 or len(cmd.stdout) > 256 * 1024:
                raise DeploymentKitError("Auth runtime inspect failed closed.")
            observed = json.loads(cmd.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            raise DeploymentKitError(
                "Auth runtime evidence is unavailable or invalid."
            ) from error
        return verify_stopped_auth_container(
            observed, container_name=container_name,
            expected_owner=expected_owner,
            expected_environment=expected_environment,
            expected_image_digest=expected_image_digest,
            expected_data_source=expected_data_source,
            expected_data_destination=expected_data_destination,
            owner_label=owner_label,
            environment_label=environment_label,
            required_auth_environment=required_auth_environment,
        )
    return inspect
