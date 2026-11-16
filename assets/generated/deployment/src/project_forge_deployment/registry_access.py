"""Read-only exact-image registry capability verification by execution context."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import Any

from .errors import DeploymentKitError
from .profiles import load_profile
from .ssh import ssh_args, verify_access


_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$")
_REMOTE_DOES_NOT_PROVE = [
    "workstation-registry-access",
    "workstation-image-pull",
    "actions-registry-transport",
    "package-metadata-api-access",
]
_WORKSTATION_DOES_NOT_PROVE = [
    "remote-target-registry-access",
    "actions-registry-transport",
    "package-metadata-api-access",
]

_REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

unset DOCKER_CONFIG

IMAGE="$1"

[[ "$IMAGE" =~ ^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$ ]] || {
    echo "Image must be an immutable sha256 digest reference." >&2
    exit 41
}

command -v docker >/dev/null 2>&1 || {
    echo "Docker CLI is unavailable on the target." >&2
    exit 42
}

config_dir="$HOME/.docker"
config_file="$config_dir/config.json"
credential_state="absent"

if [[ -e "$config_file" ]]; then
    [[ -d "$config_dir" && ! -L "$config_dir" && -f "$config_file" && ! -L "$config_file" ]] || {
        echo "Docker credential path is not a regular protected directory/file." >&2
        exit 43
    }
    dir_mode="$(stat -c '%a' "$config_dir")"
    file_mode="$(stat -c '%a' "$config_file")"
    current_uid="$(id -u)"
    if (( (8#$dir_mode & 077) != 0 || (8#$file_mode & 077) != 0 )) ||
       [[ "$(stat -c '%u' "$config_dir")" != "$current_uid" || "$(stat -c '%u' "$config_file")" != "$current_uid" ]]; then
        echo "Docker credentials must be owned by the deployment account and deny group/other access." >&2
        exit 43
    fi
    export DOCKER_CONFIG="$config_dir"
    credential_state="protected"
fi

if ! docker manifest inspect "$IMAGE" </dev/null >/dev/null 2>&1; then
    echo "Registry manifest access failed for the exact image." >&2
    exit 44
fi

printf 'ACCESS\t%s\n' "$credential_state"
'''


class RegistryCapabilityError(DeploymentKitError):
    """Fail-closed registry capability error with safe structured evidence."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


def normalize_registry_image(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_RE.fullmatch(value) is None:
        raise DeploymentKitError(
            "image must be an immutable image reference ending in @sha256:<64 lowercase hex>."
        )
    return value


def build_remote_script() -> str:
    return _REMOTE_SCRIPT


def _parse_access(output: str) -> str:
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 1:
        raise DeploymentKitError("Malformed registry access verification output.")
    parts = lines[0].split("\t")
    if len(parts) != 2 or parts[0] != "ACCESS" or parts[1] not in {"absent", "protected"}:
        raise DeploymentKitError("Malformed registry access verification output.")
    return parts[1]


def _remote_failure_result(
    *,
    name: str,
    image: str,
    address: str,
    returncode: int,
) -> dict[str, Any]:
    failure_codes = {
        42: "docker-cli-unavailable",
        43: "credential-config-unsafe",
        44: "manifest-access-failed",
    }
    return {
        "status": "failed",
        "executionLocation": "remote-target",
        "targetName": name,
        "verifiedAddress": address,
        "capabilityAttempted": "registry-manifest-read",
        "image": image,
        "failureCode": failure_codes.get(returncode, "remote-command-failed"),
        "doesNotProve": list(_REMOTE_DOES_NOT_PROVE),
        "mutated": False,
    }


def _workstation_failure_result(*, image: str, failure_code: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "executionLocation": "workstation",
        "credentialContext": "workstation-docker-client",
        "dockerConfigSource": "explicit-environment" if os.environ.get("DOCKER_CONFIG") else "default",
        "capabilityAttempted": "registry-manifest-read",
        "image": image,
        "failureCode": failure_code,
        "doesNotProve": list(_WORKSTATION_DOES_NOT_PROVE),
        "mutated": False,
    }


def verify_registry_access(name: str, image: str) -> dict[str, Any]:
    """Verify exact-image manifest access from the named remote target."""

    exact_image = normalize_registry_image(image)
    profile = load_profile(name)
    access = verify_access(profile)
    address = access["address"]
    command = ssh_args(
        profile,
        address,
        command="bash -s -- " + shlex.quote(exact_image),
    )
    completed = subprocess.run(
        command,
        input=build_remote_script().encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        result = _remote_failure_result(
            name=name,
            image=exact_image,
            address=address,
            returncode=completed.returncode,
        )
        raise RegistryCapabilityError(
            f"Remote-target registry capability check failed ({result['failureCode']}).",
            result,
        )

    credential_state = _parse_access(stdout)
    return {
        "status": "verified",
        "executionLocation": "remote-target",
        "targetName": name,
        "verifiedAddress": address,
        "credentialContext": (
            "target-docker-config" if credential_state == "protected" else "target-anonymous"
        ),
        "capabilityProved": "registry-manifest-read",
        "image": exact_image,
        "manifestAccess": "verified",
        "credentialConfig": credential_state,
        "doesNotProve": list(_REMOTE_DOES_NOT_PROVE),
        "mutated": False,
    }


def verify_workstation_registry_access(image: str) -> dict[str, Any]:
    """Verify exact-image manifest access from this workstation without pulling."""

    exact_image = normalize_registry_image(image)
    command = ["docker", "manifest", "inspect", exact_image]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
        )
    except FileNotFoundError as error:
        result = _workstation_failure_result(
            image=exact_image,
            failure_code="docker-cli-unavailable",
        )
        raise RegistryCapabilityError(
            "Workstation registry capability check failed (docker-cli-unavailable).",
            result,
        ) from error

    if completed.returncode != 0:
        result = _workstation_failure_result(
            image=exact_image,
            failure_code="manifest-access-failed",
        )
        raise RegistryCapabilityError(
            "Workstation registry capability check failed (manifest-access-failed).",
            result,
        )

    return {
        "status": "verified",
        "executionLocation": "workstation",
        "credentialContext": "workstation-docker-client",
        "dockerConfigSource": "explicit-environment" if os.environ.get("DOCKER_CONFIG") else "default",
        "capabilityProved": "registry-manifest-read",
        "image": exact_image,
        "manifestAccess": "verified",
        "doesNotProve": list(_WORKSTATION_DOES_NOT_PROVE),
        "mutated": False,
    }


__all__ = [
    "RegistryCapabilityError",
    "build_remote_script",
    "normalize_registry_image",
    "verify_registry_access",
    "verify_workstation_registry_access",
]
