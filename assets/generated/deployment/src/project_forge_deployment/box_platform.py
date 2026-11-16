"""Shared Ubuntu box platform ownership and lifecycle operations."""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import subprocess
from typing import Any

from .box_platform_assets import (
    AVAHI_SERVICE,
    CADDYFILE,
    CADDY_CONTAINER,
    CADDY_IMAGE,
    COMPOSE_YAML,
    HOST_PLATFORM_WRITE_PHRASE,
    NETWORK_NAME,
    PLATFORM_DISTRIBUTION,
    PLATFORM_ROOT,
    PLATFORM_SCHEMA_VERSION,
    PLATFORM_VERSION,
    PUBLISH_ALIAS_SH,
)
from .box_platform_remote import REMOTE_SCRIPT
from .errors import DeploymentKitError
from .profiles import load_profile
from .ssh import ssh_args, verify_access

_BOOL_KEYS = {
    "markerPresent",
    "prerequisitesReady",
    "networkPresent",
    "caddyRunning",
    "avahiRunning",
    "port80InUse",
}
_EXPECTED_KEYS = {
    "state",
    "markerPresent",
    "markerSchemaVersion",
    "markerDistribution",
    "markerPlatformVersion",
    "expectedPlatformVersion",
    "prerequisitesReady",
    "networkPresent",
    "caddyRunning",
    "avahiRunning",
    "port80InUse",
    "platformRoot",
    "networkName",
    "caddyContainer",
}


def build_remote_script() -> str:
    replacements = {
        "__PLATFORM_ROOT__": PLATFORM_ROOT,
        "__NETWORK_NAME__": NETWORK_NAME,
        "__CADDY_CONTAINER__": CADDY_CONTAINER,
        "__CADDY_IMAGE__": CADDY_IMAGE,
        "__SCHEMA_VERSION__": str(PLATFORM_SCHEMA_VERSION),
        "__PLATFORM_VERSION__": PLATFORM_VERSION,
        "__DISTRIBUTION__": PLATFORM_DISTRIBUTION,
        "__COMPOSE_B64__": base64.b64encode(COMPOSE_YAML.encode()).decode("ascii"),
        "__CADDYFILE_B64__": base64.b64encode(CADDYFILE.encode()).decode("ascii"),
        "__PUBLISH_ALIAS_B64__": base64.b64encode(PUBLISH_ALIAS_SH.encode()).decode("ascii"),
        "__AVAHI_SERVICE_B64__": base64.b64encode(AVAHI_SERVICE.encode()).decode("ascii"),
    }
    script = REMOTE_SCRIPT
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    if "__" in script:
        raise DeploymentKitError("Internal host-platform script contains an unresolved placeholder.")
    return script


def _parse_status(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in output.splitlines():
        if not raw.strip():
            continue
        if "=" not in raw:
            raise DeploymentKitError(f"Malformed host-platform status line: {raw!r}")
        key, value = raw.split("=", 1)
        if key not in _EXPECTED_KEYS or key in result:
            raise DeploymentKitError(f"Unexpected or duplicate host-platform status key: {key!r}")
        if key in _BOOL_KEYS:
            if value not in {"true", "false"}:
                raise DeploymentKitError(f"Invalid boolean host-platform status value for {key}.")
            result[key] = value == "true"
        else:
            result[key] = value
    missing = _EXPECTED_KEYS - result.keys()
    if missing:
        raise DeploymentKitError(
            "Host-platform status omitted required keys: " + ", ".join(sorted(missing))
        )
    return result


def _run_remote(profile: dict[str, Any], address: str, action: str, *, sudo: bool) -> str:
    if action not in {"status", "install", "upgrade", "proxy-peer"}:
        raise DeploymentKitError(f"Unsupported host-platform action: {action}")
    remote_command = "bash -s -- " + shlex.quote(action)
    if sudo:
        remote_command = "sudo -n " + remote_command
    command = ssh_args(profile, address, command=remote_command)
    completed = subprocess.run(
        command,
        input=build_remote_script().encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote host-platform {action} failed: {detail}")
    return stdout


def platform_status(name: str) -> dict[str, Any]:
    profile = load_profile(name)
    evidence = verify_access(profile)
    status = _parse_status(_run_remote(profile, evidence["address"], "status", sudo=True))
    status["targetName"] = name
    status["verifiedAddress"] = evidence["address"]
    return status


def platform_proxy_peer(
    name: str,
    *,
    configured_peer: str | None = None,
    previous_container_id: str | None = None,
    previous_network_id: str | None = None,
) -> dict[str, Any]:
    """Read current Caddy peer and produce a no-write app convergence decision.

    This is NOT authority to update an application's trusted peer. That
    requires its own verified plan, meaningful review and runtime write gate.
    """
    from .proxy_peer import assess_configured_peer, parse_peer_observation

    profile = load_profile(name)
    evidence = verify_access(profile)
    observed = parse_peer_observation(
        _run_remote(profile, evidence["address"], "proxy-peer", sudo=True)
    )
    plan = assess_configured_peer(
        observed,
        configured_peer,
        previous_container_id=previous_container_id,
        previous_network_id=previous_network_id,
    )
    plan["targetName"] = name
    plan["mutated"] = False
    return plan


def platform_doctor(name: str) -> dict[str, Any]:
    status = platform_status(name)
    next_actions = {
        "installable": "platform-install",
        "upgrade-required": "platform-upgrade",
        "drifted": "inspect-platform-drift",
        "blocked": "prepare-host-prerequisites",
        "blocked-port-80": "identify-existing-port-80-owner",
        "incompatible": "manual-platform-recovery",
        "ready": "none",
    }
    status["nextAction"] = next_actions.get(status["state"], "manual-review")
    status["mutated"] = False
    return status


def _snapshot(status: dict[str, Any]) -> str:
    selected = {key: status[key] for key in sorted(_EXPECTED_KEYS)}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_platform_change(name: str, action: str) -> dict[str, Any]:
    if action not in {"install", "upgrade"}:
        raise DeploymentKitError("Platform change action must be install or upgrade.")
    status = platform_status(name)
    expected_state = "installable" if action == "install" else "upgrade-required"
    if status["state"] != expected_state:
        raise DeploymentKitError(
            f"Platform {action} requires state '{expected_state}', but target '{name}' is '{status['state']}'."
        )
    return {
        "targetName": name,
        "action": action,
        "fromState": status["state"],
        "toPlatformVersion": PLATFORM_VERSION,
        "distribution": PLATFORM_DISTRIBUTION,
        "platformRoot": PLATFORM_ROOT,
        "preserves": ["route-conf.d", "route-registry", "caddy-data", "caddy-config", "shared-network"],
        "doesNotOwn": ["application-containers", "application-data", "application-routes"],
        "statusSnapshot": _snapshot(status),
    }


def apply_platform_change(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "targetName",
        "action",
        "fromState",
        "toPlatformVersion",
        "distribution",
        "platformRoot",
        "preserves",
        "doesNotOwn",
        "statusSnapshot",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise DeploymentKitError("Malformed host-platform change plan.")
    name = plan["targetName"]
    action = plan["action"]
    if action not in {"install", "upgrade"}:
        raise DeploymentKitError("Malformed host-platform change action.")
    current = platform_status(name)
    if _snapshot(current) != plan["statusSnapshot"]:
        raise DeploymentKitError(
            "Host-platform state changed after the plan was reviewed; create and authorize a fresh plan."
        )
    profile = load_profile(name)
    evidence = verify_access(profile)
    _run_remote(profile, evidence["address"], action, sudo=True)
    final = platform_status(name)
    if final["state"] != "ready":
        raise DeploymentKitError(
            f"Host-platform {action} completed but readiness is '{final['state']}', not 'ready'."
        )
    final["mutated"] = True
    return final
