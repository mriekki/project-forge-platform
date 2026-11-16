"""Portable non-secret target-definition export/import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .profiles import config_root, load_profile, save_profile, validate_target_name


BUNDLE_SCHEMA_VERSION = 1
BUNDLE_KIND = "project-forge-environment-bundle"


def _portable_target(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "targetName": profile["targetName"],
        "targetOs": profile["targetOs"],
        "hostName": profile["hostName"],
        "sshAlias": profile["sshAlias"],
        "user": profile["user"],
        "port": profile["port"],
    }


def list_target_names() -> list[str]:
    directory = config_root() / "targets"
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise DeploymentKitError(f"Target profile directory is not a real directory: {directory}")
    names: list[str] = []
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise DeploymentKitError(f"Target profile entry is not a real file: {path}")
        names.append(validate_target_name(path.stem))
    return names


def export_bundle(names: list[str] | None = None) -> dict[str, Any]:
    selected = list_target_names() if names is None else names
    normalized = sorted(dict.fromkeys(validate_target_name(name) for name in selected))
    return {
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "targets": [_portable_target(load_profile(name)) for name in normalized],
    }


def write_bundle(bundle: dict[str, Any], path: Path) -> Path:
    normalized = validate_bundle(bundle)
    candidate = path.expanduser().resolve()
    if candidate.exists():
        raise DeploymentKitError(f"Refusing to overwrite existing bundle: {candidate}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    return candidate


def validate_bundle(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "kind", "targets"}:
        raise DeploymentKitError("Portable environment bundle has an unexpected shape.")
    if value["schemaVersion"] != BUNDLE_SCHEMA_VERSION or value["kind"] != BUNDLE_KIND:
        raise DeploymentKitError("Unsupported portable environment bundle schema/kind.")
    targets = value["targets"]
    if not isinstance(targets, list):
        raise DeploymentKitError("Portable environment bundle targets must be an array.")

    expected = {"targetName", "targetOs", "hostName", "sshAlias", "user", "port"}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for item in targets:
        if not isinstance(item, dict) or set(item) != expected:
            raise DeploymentKitError("Portable target definition has an unexpected shape.")
        name = validate_target_name(item["targetName"])
        if name in seen:
            raise DeploymentKitError(f"Duplicate portable target definition: {name}")
        seen.add(name)
        machine = _machine_profile(item)
        normalized_profile = _validate_machine_profile(machine)
        normalized.append(_portable_target(normalized_profile))
    return {"schemaVersion": BUNDLE_SCHEMA_VERSION, "kind": BUNDLE_KIND, "targets": normalized}


def load_bundle(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if candidate.is_symlink() or not candidate.is_file():
        raise DeploymentKitError(f"Portable environment bundle is missing or unsafe: {candidate}")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read portable environment bundle {candidate}: {error}") from error
    return validate_bundle(value)


def _machine_paths(name: str) -> tuple[str, str]:
    base = Path.home().resolve() / ".ssh" / "project-forge" / validate_target_name(name)
    return str(base / "id_ed25519"), str(base / "known_hosts")


def _machine_profile(item: dict[str, Any]) -> dict[str, Any]:
    identity, known_hosts = _machine_paths(item["targetName"])
    return {
        "schemaVersion": 1,
        **item,
        "identityFile": identity,
        "knownHostsFile": known_hosts,
        "addressOverride": None,
    }


def _validate_machine_profile(value: dict[str, Any]) -> dict[str, Any]:
    from .profiles import validate_profile

    return validate_profile(value, expected_target_name=value["targetName"])


def plan_import(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_bundle(bundle)
    items: list[dict[str, Any]] = []
    for portable in normalized["targets"]:
        desired = _validate_machine_profile(_machine_profile(portable))
        path = config_root() / "targets" / f"{desired['targetName']}.json"
        if path.exists():
            current = load_profile(desired["targetName"])
            current_portable = _portable_target(current)
            if current_portable == portable:
                state = "already-present"
            else:
                state = "conflict"
        else:
            state = "create"
        items.append(
            {
                "targetName": desired["targetName"],
                "state": state,
                "portable": portable,
                "identityFile": desired["identityFile"],
                "knownHostsFile": desired["knownHostsFile"],
            }
        )
    return {
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "kind": BUNDLE_KIND,
        "targets": items,
        "hasConflicts": any(item["state"] == "conflict" for item in items),
        "mutated": False,
    }


def apply_import(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("kind") != BUNDLE_KIND or not isinstance(plan.get("targets"), list):
        raise DeploymentKitError("Portable environment import plan is malformed.")
    if plan.get("hasConflicts"):
        raise DeploymentKitError("Portable environment import has conflicts; existing target definitions are never overwritten.")

    created: list[str] = []
    existing: list[str] = []
    for item in plan["targets"]:
        state = item.get("state")
        if state == "already-present":
            existing.append(item["targetName"])
            continue
        if state != "create":
            raise DeploymentKitError("Portable environment import plan contains an unsupported state.")
        desired = _validate_machine_profile(_machine_profile(item["portable"]))
        path = config_root() / "targets" / f"{desired['targetName']}.json"
        if path.exists():
            raise DeploymentKitError(
                f"Target profile appeared after preview; re-run preview before importing: {desired['targetName']}"
            )
        save_profile(desired)
        created.append(desired["targetName"])
    return {
        "created": created,
        "alreadyPresent": existing,
        "mutated": bool(created),
        "next": "Imported definitions still need this workstation's SSH identity/trust before remote readiness.",
    }
