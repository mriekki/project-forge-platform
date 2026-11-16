"""Owned application-route registry for the shared Ubuntu box platform."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shlex
import subprocess
from typing import Any, Iterable

from .box_platform import platform_status
from .box_platform_assets import (
    CADDY_CONTAINER,
    CADDY_IMAGE,
    NETWORK_NAME,
    PLATFORM_DISTRIBUTION,
    PLATFORM_ROOT,
    PLATFORM_SCHEMA_VERSION,
    PLATFORM_VERSION,
)
from .errors import DeploymentKitError
from .profiles import load_profile
from .route_registry_remote import REMOTE_SCRIPT
from .ssh import ssh_args, verify_access

ROUTE_WRITE_PHRASE = "[ROUTE WRITE]"
ROUTE_REMOVE_PHRASE = "[ROUTE REMOVE]"
ROUTE_SCHEMA_VERSION = 1

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def _validate_slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _validate_owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _validate_container(value: str) -> str:
    if not isinstance(value, str) or _CONTAINER_RE.fullmatch(value) is None:
        raise DeploymentKitError("upstreamContainer contains unsupported characters.")
    return value


def _validate_hostname(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise DeploymentKitError("Route hostnames must be non-empty DNS/mDNS names.")
    value = value.lower().rstrip(".")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise DeploymentKitError("Raw IP routes are not allowed; each application route must use an owned hostname.")
    labels = value.split(".")
    if any(_HOST_LABEL_RE.fullmatch(label) is None for label in labels):
        raise DeploymentKitError(f"Invalid route hostname: {value}")
    if not value.endswith(".local"):
        raise DeploymentKitError("The trusted-LAN distribution currently supports only .local application hostnames.")
    return value


def normalize_route_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    upstream_container: str,
    upstream_port: int,
    hostnames: Iterable[str],
) -> dict[str, Any]:
    owner_repo = _validate_owner_repo(owner_repo)
    environment = _validate_slug(environment, "environment")
    app_slug = _validate_slug(app_slug, "appSlug")
    upstream_container = _validate_container(upstream_container)
    if type(upstream_port) is not int or not 1 <= upstream_port <= 65535:
        raise DeploymentKitError("upstreamPort must be an integer from 1 through 65535.")
    normalized_hosts = sorted({_validate_hostname(item) for item in hostnames})
    if not normalized_hosts:
        raise DeploymentKitError("At least one route hostname is required.")
    return {
        "schemaVersion": ROUTE_SCHEMA_VERSION,
        "ownerRepo": owner_repo,
        "environment": environment,
        "appSlug": app_slug,
        "routeId": f"{app_slug}--{environment}",
        "upstreamContainer": upstream_container,
        "upstreamPort": upstream_port,
        "hostnames": normalized_hosts,
    }


def _encode_spec(spec: dict[str, Any]) -> str:
    return "\t".join(
        [
            str(spec["schemaVersion"]),
            spec["ownerRepo"],
            spec["environment"],
            spec["appSlug"],
            spec["routeId"],
            spec["upstreamContainer"],
            str(spec["upstreamPort"]),
            ",".join(spec["hostnames"]),
        ]
    )


def _parse_inventory(output: str) -> dict[str, Any]:
    summary: dict[str, str] = {}
    routes: list[dict[str, Any]] = []
    for raw in output.splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        kind = parts[0]
        if kind == "SUMMARY":
            if len(parts) != 3 or parts[1] in summary:
                raise DeploymentKitError("Malformed or duplicate route-inventory summary field.")
            summary[parts[1]] = parts[2]
        elif kind == "ROUTE":
            if len(parts) != 9:
                raise DeploymentKitError("Malformed managed route inventory record.")
            try:
                schema = int(parts[1])
                port = int(parts[7])
            except ValueError as error:
                raise DeploymentKitError("Malformed numeric route inventory value.") from error
            spec = normalize_route_spec(
                owner_repo=parts[2],
                environment=parts[3],
                app_slug=parts[4],
                upstream_container=parts[6],
                upstream_port=port,
                hostnames=parts[8].split(",") if parts[8] else [],
            )
            if schema != ROUTE_SCHEMA_VERSION or parts[5] != spec["routeId"]:
                raise DeploymentKitError("Managed route metadata has an unsupported schema or route ID mismatch.")
            routes.append(spec)
        else:
            raise DeploymentKitError(f"Unexpected route inventory record type: {kind!r}")

    expected_summary = {"platformState", "managedRouteCount"}
    if set(summary) != expected_summary:
        raise DeploymentKitError("Route inventory omitted required summary fields.")
    try:
        count = int(summary["managedRouteCount"])
    except ValueError as error:
        raise DeploymentKitError("Malformed managed route count.") from error
    if count != len(routes):
        raise DeploymentKitError("Managed route count does not match inventory records.")
    route_ids = [item["routeId"] for item in routes]
    if len(route_ids) != len(set(route_ids)):
        raise DeploymentKitError("Duplicate managed route IDs were reported by the target.")
    return {
        "platformState": summary["platformState"],
        "managedRoutes": sorted(routes, key=lambda item: item["routeId"]),
    }


def _inventory_snapshot(inventory: dict[str, Any]) -> str:
    value = {
        "platformState": inventory["platformState"],
        "managedRoutes": inventory["managedRoutes"],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_remote_script() -> str:
    replacements = {
        "__PLATFORM_ROOT__": PLATFORM_ROOT,
        "__NETWORK_NAME__": NETWORK_NAME,
        "__CADDY_CONTAINER__": CADDY_CONTAINER,
        "__CADDY_IMAGE__": CADDY_IMAGE,
        "__PLATFORM_SCHEMA_VERSION__": str(PLATFORM_SCHEMA_VERSION),
        "__PLATFORM_VERSION__": PLATFORM_VERSION,
        "__PLATFORM_DISTRIBUTION__": PLATFORM_DISTRIBUTION,
        "__ROUTE_SCHEMA_VERSION__": str(ROUTE_SCHEMA_VERSION),
    }
    script = REMOTE_SCRIPT
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    if "__" in script:
        raise DeploymentKitError("Internal route-registry script contains an unresolved placeholder.")
    return script


def _run_remote(
    profile: dict[str, Any],
    address: str,
    action: str,
    *,
    sudo: bool,
    spec: dict[str, Any] | None = None,
    previous_spec: dict[str, Any] | None = None,
) -> str:
    if action not in {"inventory", "register", "remove"}:
        raise DeploymentKitError(f"Unsupported route-registry action: {action}")
    args = [action]
    if spec is not None:
        args.append(_encode_spec(spec))
    if action == "register":
        args.append(_encode_spec(previous_spec) if previous_spec is not None else "NONE")
    remote_command = "bash -s -- " + " ".join(shlex.quote(item) for item in args)
    if sudo:
        remote_command = "sudo -n " + remote_command
    completed = subprocess.run(
        ssh_args(profile, address, command=remote_command),
        input=build_remote_script().encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote route-registry {action} failed: {detail}")
    return stdout


def route_inventory(name: str) -> dict[str, Any]:
    profile = load_profile(name)
    evidence = verify_access(profile)
    inventory = _parse_inventory(_run_remote(profile, evidence["address"], "inventory", sudo=True))
    inventory["targetName"] = name
    inventory["verifiedAddress"] = evidence["address"]
    inventory["mutated"] = False
    return inventory


def _find_route(inventory: dict[str, Any], route_id: str) -> dict[str, Any] | None:
    return next((item for item in inventory["managedRoutes"] if item["routeId"] == route_id), None)


def plan_route_registration(
    name: str,
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    upstream_container: str,
    upstream_port: int,
    hostnames: Iterable[str],
) -> dict[str, Any]:
    spec = normalize_route_spec(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        upstream_container=upstream_container,
        upstream_port=upstream_port,
        hostnames=hostnames,
    )
    inventory = route_inventory(name)
    if inventory["platformState"] != "ready":
        raise DeploymentKitError(
            f"Route registration requires a ready Kit-owned platform; target '{name}' is '{inventory['platformState']}'."
        )
    existing = _find_route(inventory, spec["routeId"])
    if existing is not None:
        owner_fields = ("ownerRepo", "environment", "appSlug")
        if any(existing[field] != spec[field] for field in owner_fields):
            raise DeploymentKitError(
                f"Route ID {spec['routeId']} is already owned by another Project/environment; refusing takeover."
            )
    requested = set(spec["hostnames"])
    for route in inventory["managedRoutes"]:
        if route["routeId"] == spec["routeId"]:
            continue
        collision = requested.intersection(route["hostnames"])
        if collision:
            raise DeploymentKitError(
                "Hostname collision with route " + route["routeId"] + ": " + ", ".join(sorted(collision))
            )
    return {
        "targetName": name,
        "action": "register",
        "route": spec,
        "changeType": "update" if existing else "create",
        "previousRoute": existing,
        "inventorySnapshot": _inventory_snapshot(inventory),
        "sharedPlatformAssetsModified": False,
        "rawHostIpRoute": False,
        "requiresUpstreamOnSharedNetwork": True,
    }


def plan_route_removal(
    name: str,
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
) -> dict[str, Any]:
    route_id = f"{_validate_slug(app_slug, 'appSlug')}--{_validate_slug(environment, 'environment')}"
    owner_repo = _validate_owner_repo(owner_repo)
    inventory = route_inventory(name)
    if inventory["platformState"] != "ready":
        raise DeploymentKitError(
            f"Route removal requires a ready Kit-owned platform; target '{name}' is '{inventory['platformState']}'."
        )
    existing = _find_route(inventory, route_id)
    if existing is None:
        raise DeploymentKitError(f"Managed route does not exist: {route_id}")
    if existing["ownerRepo"] != owner_repo or existing["environment"] != environment or existing["appSlug"] != app_slug:
        raise DeploymentKitError("Route removal ownership does not match the registered Project/environment.")
    return {
        "targetName": name,
        "action": "remove",
        "route": existing,
        "inventorySnapshot": _inventory_snapshot(inventory),
        "removes": ["caddy-route", "mdns-aliases", "route-ownership-metadata"],
        "preserves": ["shared-platform", "shared-network", "application-container", "application-data"],
    }


def apply_route_change(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("action") not in {"register", "remove"}:
        raise DeploymentKitError("Malformed route-registry change plan.")
    required_register = {
        "targetName", "action", "route", "changeType", "previousRoute", "inventorySnapshot",
        "sharedPlatformAssetsModified", "rawHostIpRoute", "requiresUpstreamOnSharedNetwork",
    }
    required_remove = {"targetName", "action", "route", "inventorySnapshot", "removes", "preserves"}
    expected = required_register if plan["action"] == "register" else required_remove
    if set(plan) != expected:
        raise DeploymentKitError("Malformed route-registry change plan.")

    name = plan["targetName"]
    current = route_inventory(name)
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Route inventory changed after the plan was reviewed; create and authorize a fresh plan."
        )
    platform = platform_status(name)
    if platform["state"] != "ready":
        raise DeploymentKitError("Shared host platform is no longer ready; route change is blocked.")

    profile = load_profile(name)
    evidence = verify_access(profile)
    _run_remote(
        profile,
        evidence["address"],
        plan["action"],
        sudo=True,
        spec=plan["route"],
        previous_spec=plan.get("previousRoute"),
    )
    final = route_inventory(name)
    route_id = plan["route"]["routeId"]
    registered = _find_route(final, route_id)
    if plan["action"] == "register":
        if registered != plan["route"]:
            raise DeploymentKitError("Route registration returned without the exact requested ownership metadata.")
    elif registered is not None:
        raise DeploymentKitError("Route removal returned but the route remains registered.")
    final["mutated"] = True
    return final
