"""Workstation-only application spec normalization."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

from .app_runtime import normalize_app_spec
from .errors import DeploymentKitError
from .local_extensions import normalize_bindings, normalize_mounts


_LOCAL_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _host_port(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise DeploymentKitError("hostPort must be an integer from 1 through 65535.")
    return value


def _base_image(image: str) -> tuple[str, bool]:
    if isinstance(image, str) and _LOCAL_IMAGE_ID_RE.fullmatch(image):
        return f"local-workstation/immutable@{image}", True
    return image, False


def normalize_workstation_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    container_name: str,
    image: str,
    runtime_port: int,
    host_port: int,
    health_path: str,
    run_as: str,
    persistence_mode: str,
    data_container_path: str | None,
    environment_variables: dict[str, str] | Iterable[tuple[str, str]],
    additional_port_bindings: list[dict[str, int]] | None = None,
    read_only_mounts: list[dict[str, str]] | None = None,
    allow_file_mounts: bool = False,
) -> dict[str, Any]:
    """Normalize a loopback-only workstation spec.

    Remote deployment keeps the registry-digest-only contract. Workstation execution
    additionally accepts an immutable local Docker image ID (sha256:<64 hex>) so a
    developer can build/test/run without publishing to a registry first.
    """

    normalized_image, local_image_id = _base_image(image)
    base = normalize_app_spec(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        container_name=container_name,
        image=normalized_image,
        runtime_port=runtime_port,
        health_path=health_path,
        run_as=run_as,
        persistence_mode=persistence_mode,
        data_container_path=data_container_path,
        environment_variables=environment_variables,
    )
    base.pop("specSha256", None)
    if local_image_id:
        base["image"] = image
    base.update(
        {
            "schemaVersion": 1,
            "placement": "workstation",
            "isolation": "container",
            "exposure": "loopback",
            "hostAddress": "127.0.0.1",
            "hostPort": _host_port(host_port),
            "imageSource": "local-image-id" if local_image_id else "registry-digest",
        }
    )
    extra_bindings = normalize_bindings(base["hostPort"], base["runtimePort"], additional_port_bindings or [])
    extra_mounts = normalize_mounts(
        base["appSlug"],
        base["environment"],
        read_only_mounts or [],
        base["persistence"]["dataContainerPath"],
        allow_file_mounts=allow_file_mounts,
    )
    if extra_bindings:
        base["additionalPortBindings"] = extra_bindings
    if extra_mounts:
        base["readOnlyMounts"] = extra_mounts
    base["specSha256"] = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return base
