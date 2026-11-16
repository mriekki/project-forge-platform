"""Read-only colocated-environment isolation and collision preflight."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable

from .app_runtime import APP_ROOT, app_inventory
from .errors import DeploymentKitError
from .route_registry import route_inventory
from .sqlite_adapter import sqlite_inventory

ISOLATION_SCHEMA_VERSION = 1
_LOCK_ROOT = "/run/lock"
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DB_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _container(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _CONTAINER_RE.fullmatch(value) is None:
        raise DeploymentKitError("containerName contains unsupported characters.")
    return value


def _port(value: int | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= 65535:
        raise DeploymentKitError("runtimePort must be an integer from 1 through 65535.")
    return value


def _database_file(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _DB_FILE_RE.fullmatch(value) is None or value in {".", ".."}:
        raise DeploymentKitError("databaseFile must be a safe file name without path separators.")
    return value


def _hostnames(values: Iterable[str] | None) -> list[str]:
    result: set[str] = set()
    for value in values or ():
        if not isinstance(value, str) or not value.strip():
            raise DeploymentKitError("routeHostnames must contain non-empty strings.")
        result.add(value.lower().rstrip("."))
    return sorted(result)


def _snapshot(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _resource_state(conflicts: list[dict[str, Any]], resources: set[str]) -> str:
    return "blocked" if any(item["resource"] in resources for item in conflicts) else "clear"


def _identity(item: dict[str, Any]) -> tuple[str, str, str]:
    return (item["ownerRepo"], item["appSlug"], item["environment"])


def _conflict(
    code: str,
    resource: str,
    message: str,
    **detail: Any,
) -> dict[str, Any]:
    return {"code": code, "resource": resource, "message": message, **detail}


def environment_isolation_preflight(
    target_name: str,
    *,
    owner_repo: str,
    environment: str,
    production: bool = False,
    app_slug: str | None = None,
    container_name: str | None = None,
    runtime_port: int | None = None,
    persistence_mode: str | None = None,
    database_file: str | None = None,
    route_hostnames: Iterable[str] | None = None,
    require_vacant_app_identity: bool = False,
) -> dict[str, Any]:
    """Inspect managed shared-host state without mutating it.

    Same-target colocation is allowed. The preflight blocks only ambiguous ownership,
    duplicate managed identities, route/runtime drift, or a requested footprint that
    would take over a sibling Project/environment resource.
    """

    owner = _owner_repo(owner_repo)
    env = _slug(environment, "environment")
    app = _slug(app_slug, "appSlug") if app_slug is not None else None
    container = _container(container_name)
    port = _port(runtime_port)
    database = _database_file(database_file)
    hosts = _hostnames(route_hostnames)
    if not isinstance(production, bool):
        raise DeploymentKitError("production must be true or false.")
    if not isinstance(require_vacant_app_identity, bool):
        raise DeploymentKitError("requireVacantAppIdentity must be true or false.")
    if persistence_mode not in {None, "none", "directory"}:
        raise DeploymentKitError("persistenceMode must be omitted, 'none', or 'directory'.")
    if app is None and any(value is not None for value in (container, port, persistence_mode, database)):
        raise DeploymentKitError("appSlug is required when an application footprint is supplied.")
    if app is None and hosts:
        raise DeploymentKitError("appSlug is required when routeHostnames are supplied.")
    if persistence_mode == "none" and database is not None:
        raise DeploymentKitError("databaseFile cannot be supplied when persistenceMode is 'none'.")

    app_state = app_inventory(target_name)
    route_state = route_inventory(target_name)
    sqlite_state = sqlite_inventory(target_name)
    applications = list(app_state.get("applications", []))
    routes = list(route_state.get("managedRoutes", []))
    sqlite = list(sqlite_state.get("sqlite", []))

    conflicts: list[dict[str, Any]] = []

    containers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in applications:
        containers[item["containerName"]].append(item)
    for name, items in containers.items():
        identities = {_identity(item) for item in items}
        if len(identities) > 1:
            conflicts.append(
                _conflict(
                    "duplicate-managed-container",
                    "runtime",
                    f"Managed container name {name!r} is claimed by multiple Project/environment identities.",
                    containerName=name,
                    identities=[list(value) for value in sorted(identities)],
                )
            )

    route_hosts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        for hostname in route["hostnames"]:
            route_hosts[hostname].append(route)
    for hostname, items in route_hosts.items():
        route_ids = sorted({item["routeId"] for item in items})
        if len(route_ids) > 1:
            conflicts.append(
                _conflict(
                    "duplicate-managed-hostname",
                    "route",
                    f"Managed hostname {hostname!r} is claimed by multiple routes.",
                    hostname=hostname,
                    routeIds=route_ids,
                )
            )

    sqlite_keys: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in sqlite:
        sqlite_keys[(item["appSlug"], item["environment"])].append(item)
    for key, items in sqlite_keys.items():
        owners = sorted({item["ownerRepo"] for item in items})
        if len(items) > 1:
            conflicts.append(
                _conflict(
                    "duplicate-sqlite-reservation",
                    "persistence",
                    f"SQLite identity {key[0]}--{key[1]} has multiple managed reservations.",
                    appSlug=key[0],
                    environment=key[1],
                    owners=owners,
                )
            )

    apps_by_key = {(item["appSlug"], item["environment"]): item for item in applications}
    for route in routes:
        runtime = apps_by_key.get((route["appSlug"], route["environment"]))
        if runtime is None:
            conflicts.append(
                _conflict(
                    "route-without-managed-runtime",
                    "route",
                    f"Route {route['routeId']} has no matching managed application runtime.",
                    routeId=route["routeId"],
                )
            )
            continue
        if runtime["ownerRepo"] != route["ownerRepo"]:
            conflicts.append(
                _conflict(
                    "route-runtime-owner-mismatch",
                    "ownership",
                    f"Route {route['routeId']} and its managed runtime have different repository owners.",
                    routeOwnerRepo=route["ownerRepo"],
                    runtimeOwnerRepo=runtime["ownerRepo"],
                )
            )
        if runtime["containerName"] != route["upstreamContainer"]:
            conflicts.append(
                _conflict(
                    "route-upstream-container-mismatch",
                    "route",
                    f"Route {route['routeId']} points at a different container than its managed runtime.",
                    upstreamContainer=route["upstreamContainer"],
                    runtimeContainer=runtime["containerName"],
                )
            )
        if runtime["runtimePort"] != route["upstreamPort"]:
            conflicts.append(
                _conflict(
                    "route-upstream-port-mismatch",
                    "route",
                    f"Route {route['routeId']} port does not match its managed runtime port.",
                    upstreamPort=route["upstreamPort"],
                    runtimePort=runtime["runtimePort"],
                )
            )

    sibling_environments: set[str] = set()
    for collection in (applications, routes, sqlite):
        for item in collection:
            if item["ownerRepo"] == owner and item["environment"] != env:
                sibling_environments.add(item["environment"])

    desired_identity = (owner, app, env) if app is not None else None
    matching_apps = [
        item for item in applications if app is not None and item["appSlug"] == app and item["environment"] == env
    ]
    matching_routes = [
        item for item in routes if app is not None and item["appSlug"] == app and item["environment"] == env
    ]
    matching_sqlite = [
        item for item in sqlite if app is not None and item["appSlug"] == app and item["environment"] == env
    ]

    for item in matching_apps:
        if item["ownerRepo"] != owner:
            conflicts.append(
                _conflict(
                    "application-identity-owned-by-other-project",
                    "ownership",
                    f"Application identity {app}--{env} is already owned by another repository.",
                    existingOwnerRepo=item["ownerRepo"],
                )
            )
    for item in matching_routes:
        if item["ownerRepo"] != owner:
            conflicts.append(
                _conflict(
                    "route-identity-owned-by-other-project",
                    "ownership",
                    f"Route identity {app}--{env} is already owned by another repository.",
                    existingOwnerRepo=item["ownerRepo"],
                )
            )
    for item in matching_sqlite:
        if item["ownerRepo"] != owner:
            conflicts.append(
                _conflict(
                    "sqlite-identity-owned-by-other-project",
                    "ownership",
                    f"SQLite identity {app}--{env} is already owned by another repository.",
                    existingOwnerRepo=item["ownerRepo"],
                )
            )

    if app is not None and require_vacant_app_identity:
        if matching_apps:
            conflicts.append(
                _conflict(
                    "reserved-application-identity-not-vacant",
                    "runtime",
                    f"Reserved application identity {app}--{env} already has managed runtime state.",
                )
            )
        if matching_routes:
            conflicts.append(
                _conflict(
                    "reserved-route-identity-not-vacant",
                    "route",
                    f"Reserved application identity {app}--{env} already has managed route state.",
                )
            )
        if matching_sqlite:
            conflicts.append(
                _conflict(
                    "reserved-persistence-identity-not-vacant",
                    "persistence",
                    f"Reserved application identity {app}--{env} already has managed SQLite state.",
                )
            )

    if container is not None and desired_identity is not None:
        for item in applications:
            if item["containerName"] == container and _identity(item) != desired_identity:
                conflicts.append(
                    _conflict(
                        "requested-container-name-collision",
                        "runtime",
                        f"Requested container name {container!r} belongs to another managed Project/environment.",
                        existingIdentity=list(_identity(item)),
                    )
                )

    requested_hosts = set(hosts)
    if requested_hosts:
        desired_route_id = f"{app}--{env}"
        for route in routes:
            if route["routeId"] == desired_route_id and route["ownerRepo"] == owner:
                continue
            collision = requested_hosts.intersection(route["hostnames"])
            if collision:
                conflicts.append(
                    _conflict(
                        "requested-hostname-collision",
                        "route",
                        "Requested hostname is already owned by another managed route.",
                        routeId=route["routeId"],
                        hostnames=sorted(collision),
                    )
                )

    if persistence_mode == "none" and matching_sqlite:
        conflicts.append(
            _conflict(
                "requested-no-persistence-conflicts-with-sqlite",
                "persistence",
                f"Application identity {app}--{env} requests no persistence but has managed SQLite state.",
            )
        )

    conflicts.sort(
        key=lambda item: (
            item["resource"],
            item["code"],
            json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    )

    app_root = f"{APP_ROOT}/{app}/{env}" if app is not None else None
    lock_identity = f"{_LOCK_ROOT}/project-forge-app-{app}--{env}.lock" if app is not None else None
    database_path = f"{app_root}/data/{database}" if app_root is not None and database is not None else None

    desired = {
        "appSlug": app,
        "containerName": container,
        "runtimePort": port,
        "routeHostnames": hosts,
        "persistenceMode": persistence_mode,
        "databaseFile": database,
        "requireVacantAppIdentity": require_vacant_app_identity,
    }
    evidence_value = {
        "schemaVersion": ISOLATION_SCHEMA_VERSION,
        "targetName": target_name,
        "ownerRepo": owner,
        "environment": env,
        "production": production,
        "desired": desired,
        "applications": applications,
        "routes": routes,
        "sqlite": sqlite,
    }
    evidence_sha = _snapshot(evidence_value)

    return {
        "schemaVersion": ISOLATION_SCHEMA_VERSION,
        "targetName": target_name,
        "ownerRepo": owner,
        "environment": env,
        "production": production,
        "state": "blocked" if conflicts else "clear",
        "sharedFailureDomain": bool(sibling_environments),
        "siblingEnvironments": sorted(sibling_environments),
        "desired": desired,
        "checks": {
            "managedOwnership": {
                "state": _resource_state(conflicts, {"ownership"}),
                "applicationRecords": len(applications),
                "routeRecords": len(routes),
                "sqliteRecords": len(sqlite),
            },
            "runtimeIdentity": {
                "state": _resource_state(conflicts, {"runtime", "ownership"}),
                "appRoot": app_root,
                "containerName": container,
                "composeProject": {
                    "state": "not-applicable",
                    "reason": "The remote managed runtime uses direct Docker container ownership, not Docker Compose project identity.",
                },
                "hostPortPublishing": {
                    "state": "not-applicable",
                    "reason": "Managed remote application containers do not publish host ports; sibling containers may safely reuse the same internal runtime port.",
                },
            },
            "routes": {
                "state": _resource_state(conflicts, {"route", "ownership"}),
                "requestedHostnames": hosts,
                "runtimePort": port,
                "portIsolation": "container-scoped",
            },
            "persistence": {
                "state": _resource_state(conflicts, {"persistence", "ownership"}),
                "appRoot": app_root,
                "databasePath": database_path,
            },
            "deploymentLock": {
                "state": _resource_state(conflicts, {"runtime", "ownership"}),
                "lockIdentity": lock_identity,
                "scope": "app/environment",
            },
        },
        "conflicts": conflicts,
        "inventorySnapshots": {
            "applications": _snapshot(applications),
            "routes": _snapshot(routes),
            "sqlite": _snapshot(sqlite),
        },
        "evidenceSha256": evidence_sha,
        "mutated": False,
    }
