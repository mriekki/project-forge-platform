"""Read-only workstation and target readiness checks."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .profiles import config_root, load_profile, target_profile_path
from .security import check_ssh_material_security, validate_target_trust_file
from .ssh import resolve_addresses


def workstation_doctor(*, home: Path | None = None) -> dict[str, Any]:
    root = config_root(home)
    targets_dir = root / "targets"
    profiles = []
    if targets_dir.is_dir() and not targets_dir.is_symlink():
        profiles = sorted(path.stem for path in targets_dir.glob("*.json") if path.is_file() and not path.is_symlink())

    tools = {name: shutil.which(name) for name in ("ssh", "ssh-keygen", "ssh-keyscan", "ssh-add")}
    missing_tools = [name for name, path in tools.items() if path is None]

    if not root.exists() and not profiles:
        state = "fresh-workstation"
    elif missing_tools:
        state = "blocked"
    elif profiles:
        state = "configured"
    else:
        state = "partially-configured"

    return {
        "state": state,
        "configRoot": str(root),
        "profiles": profiles,
        "tools": tools,
        "missingTools": missing_tools,
        "mutated": False,
    }


def target_doctor(name: str, *, home: Path | None = None) -> dict[str, Any]:
    path = target_profile_path(name, home)
    if not path.exists():
        return {
            "targetName": name,
            "state": "needs-profile",
            "profilePath": str(path),
            "nextAction": "configure-target-profile",
            "mutated": False,
        }

    try:
        profile = load_profile(name, home=home)
    except DeploymentKitError as error:
        return {
            "targetName": name,
            "state": "blocked",
            "profilePath": str(path),
            "reason": str(error),
            "mutated": False,
        }

    identity = Path(profile["identityFile"])
    known_hosts = Path(profile["knownHostsFile"])
    if not identity.is_file():
        return {
            "targetName": name,
            "state": "needs-key",
            "profilePath": str(path),
            "identityFile": str(identity),
            "nextAction": "create-or-select-dedicated-key",
            "mutated": False,
        }
    if not known_hosts.is_file() or known_hosts.stat().st_size == 0:
        return {
            "targetName": name,
            "state": "needs-trust",
            "profilePath": str(path),
            "knownHostsFile": str(known_hosts),
            "nextAction": "verify-console-fingerprint-before-trust-enrollment",
            "mutated": False,
        }

    try:
        check_ssh_material_security(identity, known_hosts)
        validate_target_trust_file(profile)
    except DeploymentKitError as error:
        return {
            "targetName": name,
            "state": "blocked",
            "profilePath": str(path),
            "reason": str(error),
            "nextAction": "repair-ssh-material-or-trust",
            "mutated": False,
        }

    try:
        addresses = resolve_addresses(profile)
    except DeploymentKitError as error:
        return {
            "targetName": name,
            "state": "needs-address",
            "profilePath": str(path),
            "hostName": profile["hostName"],
            "reason": str(error),
            "nextAction": "set-separately-verified-address-override",
            "mutated": False,
        }

    return {
        "targetName": name,
        "state": "ready-to-verify",
        "profilePath": str(path),
        "hostName": profile["hostName"],
        "addresses": addresses,
        "addressSource": "override" if profile["addressOverride"] else "dns-mdns",
        "mutated": False,
    }
