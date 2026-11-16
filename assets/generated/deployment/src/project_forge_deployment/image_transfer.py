"""Transfer an exact local Docker image to a verified remote target without remote registry credentials."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from typing import Any

from .errors import DeploymentKitError
from .profiles import load_profile
from .registry_access import normalize_registry_image
from .ssh import ssh_args, verify_access


_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        raise DeploymentKitError("Docker CLI is unavailable on the workstation.")
    return path


def _image_id(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_ID_RE.fullmatch(value) is None:
        raise DeploymentKitError("Docker image ID must be sha256:<64 lowercase hex>.")
    return value


def verify_local_image(image: str) -> dict[str, str]:
    """Verify the declared immutable registry digest and resolve its local config/image ID.

    Registry RepoDigests are release identity. Docker's image ID is the config digest and is
    the content identity preserved by ``docker save``/``docker load`` even when RepoTags are
    absent from the archive.
    """

    exact = normalize_registry_image(image)
    result = subprocess.run(
        [_docker(), "image", "inspect", "--format", "{{.Id}}", exact],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DeploymentKitError(
            f"Exact image is not present in the workstation Docker engine: {exact}. "
            "Pull/build it locally before transfer."
        )
    image_id = _image_id(result.stdout.strip())
    return {
        "image": exact,
        "registryDigest": exact,
        "localImageId": image_id,
    }


def _remote_has_image(profile: dict[str, Any], address: str, image_id: str) -> bool:
    exact_id = _image_id(image_id)
    command = "sudo -n docker image inspect " + shlex.quote(exact_id) + " >/dev/null 2>&1"
    result = subprocess.run(
        ssh_args(profile, address, command=command),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def remote_image_present(name: str, image_id: str) -> bool:
    """Read-only check for one exact Docker config/image ID on a verified target."""

    exact_id = _image_id(image_id)
    profile = load_profile(name)
    access = verify_access(profile)
    return _remote_has_image(profile, access["address"], exact_id)


def transfer_image(name: str, image: str) -> dict[str, Any]:
    local = verify_local_image(image)
    exact = local["registryDigest"]
    image_id = local["localImageId"]
    profile = load_profile(name)
    access = verify_access(profile)
    address = access["address"]

    if _remote_has_image(profile, address, image_id):
        return {
            "targetName": name,
            "image": exact,
            "registryDigest": exact,
            "localImageId": image_id,
            "remoteImageId": image_id,
            "runtimeImage": image_id,
            "status": "already-present",
            "mutated": False,
        }

    save = subprocess.Popen(
        [_docker(), "save", exact],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert save.stdout is not None
    load = subprocess.Popen(
        ssh_args(profile, address, command="sudo -n docker load >/dev/null"),
        stdin=save.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    save.stdout.close()
    load_stdout, load_stderr = load.communicate()
    save_stderr = save.stderr.read() if save.stderr is not None else b""
    save_code = save.wait()

    if save_code != 0:
        detail = save_stderr.decode("utf-8", errors="replace").strip() or f"exit {save_code}"
        raise DeploymentKitError(f"Docker image export failed: {detail}")
    if load.returncode != 0:
        detail = (
            load_stderr.decode("utf-8", errors="replace").strip()
            or load_stdout.decode("utf-8", errors="replace").strip()
            or f"exit {load.returncode}"
        )
        raise DeploymentKitError(f"Remote Docker image load failed: {detail}")

    if not _remote_has_image(profile, address, image_id):
        raise DeploymentKitError(
            "Remote docker load completed but the exact Docker config/image ID is not inspectable on the target."
        )
    return {
        "targetName": name,
        "image": exact,
        "registryDigest": exact,
        "localImageId": image_id,
        "remoteImageId": image_id,
        "runtimeImage": image_id,
        "status": "transferred",
        "mutated": True,
    }
