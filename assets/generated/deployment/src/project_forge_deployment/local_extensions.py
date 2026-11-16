"""Optional, loopback-only workstation bindings and scoped read-only material mounts.

No material is provisioned by the Kit. Source directories belong to the Project
and must already exist below its dedicated local-materials root.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .profiles import config_root

MATERIAL_TARGET_ROOT = "/run/project-forge/material"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
MAX_ADDITIONAL_PORTS = 8


def material_root(app_slug: str, environment: str) -> Path:
    return config_root() / "local-materials" / app_slug / environment


def bindings(spec: dict[str, Any]) -> list[dict[str, int]]:
    return [{"hostPort": spec["hostPort"], "runtimePort": spec["runtimePort"]}, *spec.get("additionalPortBindings", [])]


def normalize_bindings(primary_host: int, primary_runtime: int, values: object) -> list[dict[str, int]]:
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ADDITIONAL_PORTS:
        raise DeploymentKitError("additionalPortBindings must be a list of at most eight TCP mappings.")
    result = []
    host_ports = {primary_host}
    runtime_ports = {primary_runtime}
    for item in values:
        if not isinstance(item, dict) or set(item) != {"hostPort", "runtimePort"}:
            raise DeploymentKitError("Additional port mapping requires hostPort and runtimePort.")
        host, runtime = item["hostPort"], item["runtimePort"]
        if any(type(port) is not int or not 1 <= port <= 65535 for port in (host, runtime)):
            raise DeploymentKitError("Additional TCP ports must be integers from 1 through 65535.")
        if host in host_ports or runtime in runtime_ports:
            raise DeploymentKitError("All host ports and container runtime ports must be distinct.")
        host_ports.add(host)
        runtime_ports.add(runtime)
        result.append({"hostPort": host, "runtimePort": runtime})
    return sorted(result, key=lambda item: (item["hostPort"], item["runtimePort"]))


def _absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or any(ch in value for ch in ("\x00", "\n", "\r", ",")):
        raise DeploymentKitError(f"{field} must be a safe absolute path.")
    value = value.replace("\\", "/") if os.name == "nt" else value
    path = Path(value)
    if not path.is_absolute() or any(part in (".", "..") for part in value.replace("\\", "/").split("/")):
        raise DeploymentKitError(f"{field} must be an absolute path without traversal.")
    return path


def _no_symlink_components(path: Path) -> None:
    for entry in (path, *path.parents):
        if entry.is_symlink():
            raise DeploymentKitError("External material paths cannot contain symbolic links.")


def normalize_mounts(app_slug: str, environment: str, values: object, data_target: str | None) -> list[dict[str, str]]:
    if not isinstance(values, (list, tuple)):
        raise DeploymentKitError("readOnlyMounts must be a list.")
    root = material_root(app_slug, environment)
    result: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, dict) or set(item) != {"source", "target"}:
            raise DeploymentKitError("readOnlyMounts entries require source and target.")
        source = _absolute_path(item["source"], "material source")
        _no_symlink_components(source)
        try:
            relative = source.relative_to(root)
        except ValueError as error:
            raise DeploymentKitError("Material source must be beneath the Project-scoped local-materials root.") from error
        if not relative.parts or relative == Path("."):
            raise DeploymentKitError("Mount a named material directory, not the Project-scoped root.")
        target = item["target"]
        if not isinstance(target, str) or not target.startswith(MATERIAL_TARGET_ROOT + "/"):
            raise DeploymentKitError("Material targets must be under /run/project-forge/material/.")
        parts = target[len(MATERIAL_TARGET_ROOT) + 1:].split("/")
        if not all(_SAFE_NAME.fullmatch(part) and part not in {".", ".."} for part in parts):
            raise DeploymentKitError("Material target must use safe nonempty path segments.")
        target = MATERIAL_TARGET_ROOT + "/" + "/".join(parts)
        if data_target and (target == data_target or target.startswith(data_target.rstrip("/") + "/") or data_target.startswith(target + "/")):
            raise DeploymentKitError("Material target overlaps managed persistence.")
        result.append({"source": str(source), "target": target})
    for i, first in enumerate(result):
        for second in result[i+1:]:
            if any(a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")
                   for a, b in ((first["target"], second["target"]), (first["source"], second["source"]))):
                raise DeploymentKitError("Read-only material sources and targets cannot overlap.")
    return sorted(result, key=lambda item: (item["target"], item["source"]))


def snapshot_material(spec: dict[str, Any]) -> str | None:
    """Non-secret metadata snapshot; detects many, but not all, concurrent changes."""
    mounts = spec.get("readOnlyMounts", [])
    if not mounts:
        return None
    entries: list[object] = []
    for mount in mounts:
        source = Path(mount["source"])
        _no_symlink_components(source)
        if not source.is_dir():
            raise DeploymentKitError("External material source directory is missing.")
        for path in [source, *sorted(source.rglob("*"))]:
            _no_symlink_components(path)
            try:
                info = path.lstat()
            except OSError as error:
                raise DeploymentKitError("Cannot inspect external material source.") from error
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise DeploymentKitError("Material directories may contain only regular files and directories.")
            entries.append((mount["source"], str(path.relative_to(source)), info.st_dev, info.st_ino,
                            info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode("utf-8")).hexdigest()
