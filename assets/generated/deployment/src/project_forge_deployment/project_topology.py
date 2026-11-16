"""Deterministic mutation of project-owned deployment topology bindings."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .profiles import load_profile


TOPOLOGY_FILE = "DEPLOYMENT_TOPOLOGY.json"
TOPOLOGY_SCHEMA_VERSION = 1
PROJECT_TOPOLOGY_WRITE_PHRASE = "[PROJECT TOPOLOGY WRITE]"
PROJECT_PRODUCTION_TOPOLOGY_WRITE_PHRASE = "[PROJECT PRODUCTION TOPOLOGY WRITE]"


def _topology_path(root: str | Path) -> Path:
    project_root = Path(root).expanduser().resolve()
    path = project_root / TOPOLOGY_FILE
    if path.is_symlink() or not path.is_file():
        raise DeploymentKitError(f"Project deployment topology is missing or unsafe: {path}")
    return path


def _read_topology(root: str | Path) -> tuple[Path, str, dict[str, Any]]:
    path = _topology_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read project deployment topology {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != TOPOLOGY_SCHEMA_VERSION:
        raise DeploymentKitError("Unsupported or malformed project deployment topology schema.")
    environments = value.get("environments")
    if not isinstance(environments, list):
        raise DeploymentKitError("Project deployment topology environments must be an array.")
    names: list[str] = []
    for item in environments:
        if not isinstance(item, dict):
            raise DeploymentKitError("Project deployment topology contains a non-object environment.")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise DeploymentKitError("Project deployment topology contains an environment without a valid name.")
        names.append(name)
    if len(names) != len(set(names)):
        raise DeploymentKitError("Project deployment topology contains duplicate environment names.")
    return path, raw, value


def _environment(value: dict[str, Any], name: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(value["environments"]):
        if item.get("name") == name:
            return index, item
    raise DeploymentKitError(f"Project deployment topology does not define environment: {name}")


def _topology_sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_environment_binding(
    root: str | Path,
    environment: str,
    target_profile: str,
) -> dict[str, Any]:
    """Preview completion of one deferred remote-target binding without writing project state."""

    path, raw, topology = _read_topology(root)
    _, current = _environment(topology, environment)

    role = current.get("role")
    if role not in {"non-production", "production"}:
        raise DeploymentKitError(f"Environment {environment} has an unsupported role: {role}")
    if current.get("placement") != "remote-target" or current.get("adapter") != "remote-ssh":
        raise DeploymentKitError(
            f"Environment {environment} is not an existing remote-target/remote-ssh binding; "
            "this command will not rewrite placement or adapter intent."
        )

    profile = load_profile(target_profile)
    target_os = profile.get("targetOs")
    required_os = current.get("targetOs")
    if required_os not in {None, "other"} and target_os != required_os:
        raise DeploymentKitError(
            f"Target profile {target_profile} uses targetOs={target_os}; environment {environment} requires {required_os}."
        )

    state = current.get("bindingState")
    existing_target = current.get("targetProfile")
    production = role == "production"
    authorization = (
        PROJECT_PRODUCTION_TOPOLOGY_WRITE_PHRASE
        if production
        else PROJECT_TOPOLOGY_WRITE_PHRASE
    )

    before = deepcopy(current)
    if state == "configured":
        if existing_target != target_profile:
            raise DeploymentKitError(
                f"Environment {environment} is already configured for target {existing_target}; "
                "rebinding requires a separate explicit topology-change contract."
            )
        return {
            "status": "already-bound",
            "projectRoot": str(path.parent),
            "path": str(path),
            "environment": environment,
            "production": production,
            "targetProfile": target_profile,
            "targetOs": target_os,
            "before": before,
            "after": deepcopy(current),
            "changedFields": [],
            "requiredAuthorization": None,
            "expectedTopologySha256": _topology_sha(raw),
            "mutated": False,
        }
    if state != "deferred":
        raise DeploymentKitError(
            f"Environment {environment} has unsupported bindingState={state}; expected deferred or configured."
        )
    if existing_target is not None:
        raise DeploymentKitError(
            f"Deferred environment {environment} unexpectedly already contains targetProfile={existing_target}."
        )

    after = deepcopy(current)
    after["bindingState"] = "configured"
    after["targetProfile"] = target_profile

    return {
        "status": "bind",
        "projectRoot": str(path.parent),
        "path": str(path),
        "environment": environment,
        "production": production,
        "targetProfile": target_profile,
        "targetOs": target_os,
        "targetSummary": {
            "targetName": profile.get("targetName"),
            "targetOs": target_os,
            "hostName": profile.get("hostName"),
            "sshAlias": profile.get("sshAlias"),
        },
        "before": before,
        "after": after,
        "changedFields": ["bindingState", "targetProfile"],
        "requiredAuthorization": authorization,
        "expectedTopologySha256": _topology_sha(raw),
        "mutated": False,
    }


def apply_environment_binding(plan: dict[str, Any]) -> dict[str, Any]:
    """Apply exactly one previously previewed deferred binding, refusing stale topology state."""

    if plan.get("status") == "already-bound":
        return {
            "status": "already-bound",
            "environment": plan.get("environment"),
            "targetProfile": plan.get("targetProfile"),
            "production": bool(plan.get("production")),
            "path": plan.get("path"),
            "mutated": False,
        }
    required = {
        "projectRoot",
        "environment",
        "targetProfile",
        "before",
        "after",
        "expectedTopologySha256",
        "requiredAuthorization",
    }
    if plan.get("status") != "bind" or any(key not in plan for key in required):
        raise DeploymentKitError("Project topology binding plan is malformed.")

    path, raw, topology = _read_topology(plan["projectRoot"])
    if _topology_sha(raw) != plan["expectedTopologySha256"]:
        raise DeploymentKitError(
            "Project deployment topology changed after preview; re-run the binding plan before writing."
        )
    index, current = _environment(topology, plan["environment"])
    if current != plan["before"]:
        raise DeploymentKitError(
            "Selected environment changed after preview; re-run the binding plan before writing."
        )

    updated = deepcopy(topology)
    updated["environments"][index] = deepcopy(plan["after"])
    temp = path.with_name(path.name + ".tmp")
    if temp.is_symlink():
        raise DeploymentKitError(f"Refusing to write project topology through a symbolic link: {temp}")
    try:
        temp.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    except (OSError, UnicodeError) as error:
        raise DeploymentKitError(f"Cannot persist project deployment topology {path}: {error}") from error

    _, _, reread = _read_topology(plan["projectRoot"])
    _, bound = _environment(reread, plan["environment"])
    if bound != plan["after"]:
        raise DeploymentKitError("Project deployment topology write did not persist the reviewed environment binding.")

    return {
        "status": "bound",
        "environment": plan["environment"],
        "targetProfile": plan["targetProfile"],
        "production": bool(plan.get("production")),
        "bindingState": "configured",
        "path": str(path),
        "mutated": True,
    }
