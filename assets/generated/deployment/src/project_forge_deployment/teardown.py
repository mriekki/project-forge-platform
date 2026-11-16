"""Scoped destructive tear-down for Kit-managed named environments and local Docker state."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from typing import Any, Iterable

from .app_runtime import app_inventory
from .box_platform import platform_status
from .cloudflare_ingress import (
    CLOUDFLARE_API_TOKEN_ENV,
    PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE,
    cloudflare_ingress_status,
    cloudflare_route_inventory,
    plan_public_route_removal,
)
from .errors import DeploymentKitError
from .profiles import load_profile
from .route_registry import apply_route_change, plan_route_removal, route_inventory
from .ssh import ssh_args, verify_access
from .teardown_remote import REMOTE_SCRIPT

TEAR_DOWN_WRITE_PHRASE = "[PROJECT TEAR DOWN]"
PRODUCTION_DATA_DELETE_PHRASE = "[PRODUCTION DATA DELETE]"
RESERVED_SCOPES = ("local", "all")

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PACKAGE_RE = re.compile(r"^ghcr\.io/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _package(value: str) -> str:
    if not isinstance(value, str) or _PACKAGE_RE.fullmatch(value) is None:
        raise DeploymentKitError("localPackage must use exact ghcr.io/owner/package form.")
    return value


def parse_environment_targets(items: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str) or "=" not in item:
            raise DeploymentKitError("environment target bindings must use environment=target form.")
        environment, target = item.split("=", 1)
        environment = _slug(environment, "environment")
        if environment in RESERVED_SCOPES:
            raise DeploymentKitError(f"{environment!r} is reserved and cannot be a remote environment name.")
        if not target or _TARGET_RE.fullmatch(target) is None:
            raise DeploymentKitError("target profile names contain unsupported characters.")
        if environment in result:
            raise DeploymentKitError(f"Duplicate environment target binding: {environment}")
        result[environment] = target
    return dict(sorted(result.items()))


def parse_environment_scopes(items: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str) or "=" not in item:
            raise DeploymentKitError("public-ingress scope bindings must use environment=scope form.")
        environment, scope = item.split("=", 1)
        environment = _slug(environment, "environment")
        if environment in RESERVED_SCOPES:
            raise DeploymentKitError(f"{environment!r} is reserved and cannot be a remote environment name.")
        scope = _slug(scope, "public ingress scope")
        if scope in RESERVED_SCOPES:
            raise DeploymentKitError(f"{scope!r} is reserved and cannot be a public ingress scope.")
        if environment in result:
            raise DeploymentKitError(f"Duplicate public-ingress scope binding: {environment}")
        result[environment] = scope
    return dict(sorted(result.items()))


def _normalize_production_environments(items: Iterable[str]) -> set[str]:
    result = {"production"}
    for item in items:
        environment = _slug(item, "productionEnvironment")
        if environment in RESERVED_SCOPES:
            raise DeploymentKitError("local/all cannot be classified as Production environments.")
        result.add(environment)
    return result


def normalize_teardown_spec(
    *,
    owner_repo: str,
    app_slug: str,
    scope: str,
    environment_targets: dict[str, str] | Iterable[tuple[str, str]],
    local_package: str | None,
    production_environments: Iterable[str] = (),
    public_ingress_scopes: dict[str, str] | Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    scope = _slug(scope, "scope")
    pairs = environment_targets.items() if isinstance(environment_targets, dict) else environment_targets
    normalized_targets: dict[str, str] = {}
    for environment, target in pairs:
        environment = _slug(environment, "environment")
        if environment in RESERVED_SCOPES:
            raise DeploymentKitError(f"{environment!r} is reserved and cannot be a remote environment name.")
        if not isinstance(target, str) or _TARGET_RE.fullmatch(target) is None:
            raise DeploymentKitError("target profile names contain unsupported characters.")
        if environment in normalized_targets:
            raise DeploymentKitError(f"Duplicate environment target binding: {environment}")
        normalized_targets[environment] = target

    ingress_pairs = (
        public_ingress_scopes.items()
        if isinstance(public_ingress_scopes, dict)
        else public_ingress_scopes
    )
    normalized_ingress: dict[str, str] = {}
    for environment, ingress_scope in ingress_pairs:
        environment = _slug(environment, "environment")
        ingress_scope = _slug(ingress_scope, "public ingress scope")
        if environment not in normalized_targets:
            raise DeploymentKitError(
                f"public ingress scope binding {environment!r} has no matching environment target binding."
            )
        if environment in normalized_ingress:
            raise DeploymentKitError(f"Duplicate public-ingress scope binding: {environment}")
        normalized_ingress[environment] = ingress_scope

    if scope == "local":
        selected_targets: dict[str, str] = {}
    elif scope == "all":
        selected_targets = dict(sorted(normalized_targets.items()))
    else:
        if scope not in normalized_targets:
            raise DeploymentKitError(f"scope {scope!r} requires an explicit {scope}=target binding.")
        selected_targets = {scope: normalized_targets[scope]}

    package = _package(local_package) if local_package is not None else None
    if scope == "local" and package is None:
        raise DeploymentKitError("scope 'local' requires --local-package for exact local Docker ownership.")

    production_set = _normalize_production_environments(production_environments)
    selected_production = sorted(set(selected_targets).intersection(production_set))
    selected_ingress = {
        environment: normalized_ingress[environment]
        for environment in selected_targets
        if environment in normalized_ingress
    }

    return {
        "schemaVersion": 3,
        "ownerRepo": _owner_repo(owner_repo),
        "appSlug": _slug(app_slug, "appSlug"),
        "scope": scope,
        "environmentTargets": selected_targets,
        "localPackage": package,
        "productionEnvironments": selected_production,
        "publicIngressScopes": selected_ingress,
    }


def _find_route(inventory: dict[str, Any], app_slug: str, environment: str) -> dict[str, Any] | None:
    route_id = f"{app_slug}--{environment}"
    return next((item for item in inventory["managedRoutes"] if item["routeId"] == route_id), None)


def _ensure_candidate(
    candidates: dict[str, dict[str, Any]],
    *,
    owner_repo: str,
    app_slug: str,
    environment: str,
    target_name: str,
) -> dict[str, Any]:
    route_id = f"{app_slug}--{environment}"
    candidate = candidates.get(route_id)
    if candidate is None:
        candidate = {
            "routeId": route_id,
            "ownerRepo": owner_repo,
            "appSlug": app_slug,
            "environment": environment,
            "targetName": target_name,
            "runtime": None,
            "trustedLanRoute": None,
            "publicIngress": [],
        }
        candidates[route_id] = candidate
        return candidate
    if candidate["ownerRepo"] != owner_repo:
        raise DeploymentKitError(
            f"Target inventory ownership mismatch for {route_id}: "
            f"{candidate['ownerRepo']} versus {owner_repo}."
        )
    return candidate


def target_inventory(name: str, *, ingress_scopes: Iterable[str] = ()) -> dict[str, Any]:
    """Read one target's shared platform and application-owned tear-down candidates."""
    platform = platform_status(name)
    apps_result = app_inventory(name)
    lan_result = route_inventory(name)

    candidates: dict[str, dict[str, Any]] = {}
    inferred_scopes: set[str] = set()

    for app in apps_result["applications"]:
        candidate = _ensure_candidate(
            candidates,
            owner_repo=app["ownerRepo"],
            app_slug=app["appSlug"],
            environment=app["environment"],
            target_name=name,
        )
        candidate["runtime"] = app
        inferred_scopes.add(app["environment"])

    for route in lan_result["managedRoutes"]:
        candidate = _ensure_candidate(
            candidates,
            owner_repo=route["ownerRepo"],
            app_slug=route["appSlug"],
            environment=route["environment"],
            target_name=name,
        )
        candidate["trustedLanRoute"] = route
        inferred_scopes.add(route["environment"])

    if isinstance(name, str) and _SLUG_RE.fullmatch(name):
        inferred_scopes.add(name)
    requested_scopes = {_slug(item, "public ingress scope") for item in ingress_scopes}
    scopes = sorted(inferred_scopes | requested_scopes)

    public_scopes: list[dict[str, Any]] = []
    for scope in scopes:
        status = cloudflare_ingress_status(name, scope)
        routes: list[dict[str, Any]] = []
        if status["markerPresent"]:
            routes = cloudflare_route_inventory(name, scope)["managedRoutes"]
            for route in routes:
                candidate = _ensure_candidate(
                    candidates,
                    owner_repo=route["ownerRepo"],
                    app_slug=route["appSlug"],
                    environment=route["environment"],
                    target_name=name,
                )
                candidate["publicIngress"].append({"scope": scope, **route})
        public_scopes.append(
            {
                "scope": scope,
                "state": status["state"],
                "markerPresent": status["markerPresent"],
                "managedRoutes": routes,
            }
        )

    applications: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates.values(),
        key=lambda item: (item["appSlug"], item["environment"], item["ownerRepo"]),
    ):
        public_bindings = sorted(
            {item["scope"] for item in candidate["publicIngress"]}
        )
        literal_production = candidate["environment"] == "production"
        candidate["tearDown"] = {
            "available": True,
            "scope": candidate["environment"],
            "environmentTarget": f"{candidate['environment']}={name}",
            "publicIngressScopes": [
                f"{candidate['environment']}={scope}" for scope in public_bindings
            ],
            "productionClassification": (
                "production" if literal_production else "requires-trusted-evidence"
            ),
            "productionClassificationSource": (
                "literal-environment-name" if literal_production else "not-encoded-in-target-inventory"
            ),
            "requiresProductionDataAuthorization": True if literal_production else None,
            "requiresPublicIngressAuthorization": bool(public_bindings),
        }
        applications.append(candidate)

    return {
        "schemaVersion": 1,
        "targetName": name,
        "verifiedAddress": apps_result.get("verifiedAddress") or lan_result.get("verifiedAddress"),
        "sharedPlatform": platform,
        "applications": applications,
        "publicIngressScopes": public_scopes,
        "mutated": False,
    }


def _tear_down_public_ingress(
    target: str,
    scope: str,
    owner_repo: str,
    app_slug: str,
    environment: str,
) -> dict[str, Any]:
    from .cloudflare_route_apply import apply_public_route_removal

    inventory = cloudflare_route_inventory(target, scope)
    route = _find_route(inventory, app_slug, environment)
    if route is None:
        return {"state": "absent", "mutated": False, "scope": scope}
    if (
        route["ownerRepo"] != owner_repo
        or route["appSlug"] != app_slug
        or route["environment"] != environment
    ):
        raise DeploymentKitError(
            f"Public route {app_slug}--{environment} ownership does not match the requested Project."
        )
    token = os.environ.get(CLOUDFLARE_API_TOKEN_ENV, "").strip()
    if not token:
        raise DeploymentKitError(
            f"Cloudflare API authorization is required to remove owned public ingress. "
            f"Set {CLOUDFLARE_API_TOKEN_ENV} in the current workstation process/secret boundary; "
            "never put the token in the Project repository or command line."
        )
    plan = plan_public_route_removal(
        target,
        scope=scope,
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        api_token=token,
    )
    result = apply_public_route_removal(plan, api_token=token)
    return {
        "state": "removed",
        "mutated": bool(result.get("mutated")),
        "scope": scope,
        "publicHostname": route["publicHostname"],
    }


def _tear_down_route(target: str, owner_repo: str, app_slug: str, environment: str) -> dict[str, Any]:
    inventory = route_inventory(target)
    route = _find_route(inventory, app_slug, environment)
    if route is None:
        return {"state": "absent", "mutated": False}
    if route["ownerRepo"] != owner_repo:
        raise DeploymentKitError(
            f"Route {app_slug}--{environment} is owned by {route['ownerRepo']}, not {owner_repo}."
        )
    plan = plan_route_removal(
        target,
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
    )
    apply_route_change(plan)
    return {"state": "removed", "mutated": True, "hostnames": route["hostnames"]}


def _tear_down_remote_environment(
    target: str,
    owner_repo: str,
    app_slug: str,
    environment: str,
) -> dict[str, Any]:
    profile = load_profile(target)
    evidence = verify_access(profile)
    command = ssh_args(
        profile,
        evidence["address"],
        command="sudo -n bash -s -- "
        + " ".join(shlex.quote(value) for value in (owner_repo, app_slug, environment)),
    )
    completed = subprocess.run(
        command,
        input=REMOTE_SCRIPT.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0:
        raise DeploymentKitError(
            "Remote Project tear-down failed: " + (stderr or stdout or f"exit {completed.returncode}")
        )
    parts = stdout.split("\t")
    if len(parts) not in {4, 5, 7} or parts[0] != "TEAR_DOWN" or parts[1] not in {"absent", "removed"}:
        raise DeploymentKitError("Remote Project tear-down returned malformed evidence.")
    if parts[2] != app_slug or parts[3] != environment:
        raise DeploymentKitError("Remote Project tear-down returned mismatched app/environment evidence.")
    result: dict[str, Any] = {"state": parts[1], "mutated": parts[1] == "removed"}
    if len(parts) >= 5:
        result["containerName"] = parts[4]
    if len(parts) == 7:
        if parts[6] not in {"true", "false"}:
            raise DeploymentKitError("Remote Project tear-down returned malformed image-removal evidence.")
        result["images"] = [item for item in parts[5].split(",") if item]
        result["allImagesRemoved"] = parts[6] == "true"
    return result


def _run_local(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _image_matches_package(image: str, package: str) -> bool:
    return image == package or image.startswith(package + ":") or image.startswith(package + "@")


def tear_down_workstation_package(package: str) -> dict[str, Any]:
    package = _package(package)
    docker = shutil.which("docker")
    if not docker:
        return {"state": "docker-unavailable", "mutated": False, "containers": [], "images": []}

    listed = _run_local([docker, "ps", "-a", "--format", "{{.ID}}"])
    if listed.returncode != 0:
        raise DeploymentKitError(
            "Local Docker container inventory failed: " + (listed.stderr or listed.stdout).strip()
        )

    containers: list[str] = []
    for container_id in [line.strip() for line in listed.stdout.splitlines() if line.strip()]:
        inspected = _run_local([docker, "inspect", "--format", "{{.Config.Image}}", container_id])
        if inspected.returncode != 0:
            raise DeploymentKitError(f"Local Docker inspect failed for container {container_id}.")
        if _image_matches_package(inspected.stdout.strip(), package):
            containers.append(container_id)

    if containers:
        removed = _run_local([docker, "rm", "-f", "-v", *containers])
        if removed.returncode != 0:
            raise DeploymentKitError(
                "Local Project container removal failed: " + (removed.stderr or removed.stdout).strip()
            )

    images_result = _run_local([docker, "images", "--format", "{{.Repository}}:{{.Tag}}"])
    if images_result.returncode != 0:
        raise DeploymentKitError(
            "Local Docker image inventory failed: " + (images_result.stderr or images_result.stdout).strip()
        )
    image_refs = sorted(
        {
            line.strip()
            for line in images_result.stdout.splitlines()
            if line.strip().startswith(package + ":") and not line.strip().endswith(":<none>")
        }
    )
    if image_refs:
        removed = _run_local([docker, "image", "rm", "-f", *image_refs])
        if removed.returncode != 0:
            raise DeploymentKitError(
                "Local Project image removal failed: " + (removed.stderr or removed.stdout).strip()
            )
    return {
        "state": "removed" if containers or image_refs else "absent",
        "mutated": bool(containers or image_refs),
        "containers": containers,
        "images": image_refs,
    }


def tear_down_project(spec: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_teardown_spec(
        owner_repo=spec.get("ownerRepo"),
        app_slug=spec.get("appSlug"),
        scope=spec.get("scope"),
        environment_targets=(spec.get("environmentTargets") or {}).items(),
        local_package=spec.get("localPackage"),
        production_environments=spec.get("productionEnvironments") or (),
        public_ingress_scopes=(spec.get("publicIngressScopes") or {}).items(),
    )

    environments: list[dict[str, Any]] = []
    mutated = False
    for environment, target in normalized["environmentTargets"].items():
        public_ingress: dict[str, Any] = {"state": "not-selected", "mutated": False}
        if environment in normalized["publicIngressScopes"]:
            public_ingress = _tear_down_public_ingress(
                target,
                normalized["publicIngressScopes"][environment],
                normalized["ownerRepo"],
                normalized["appSlug"],
                environment,
            )
        route = _tear_down_route(target, normalized["ownerRepo"], normalized["appSlug"], environment)
        runtime = _tear_down_remote_environment(
            target,
            normalized["ownerRepo"],
            normalized["appSlug"],
            environment,
        )
        mutated = (
            mutated
            or public_ingress["mutated"]
            or route["mutated"]
            or runtime["mutated"]
        )
        environments.append(
            {
                "environment": environment,
                "targetName": target,
                "publicIngress": public_ingress,
                "route": route,
                "runtimeAndPersistentData": runtime,
            }
        )

    workstation: dict[str, Any] = {"state": "not-selected", "mutated": False}
    if normalized["scope"] in {"local", "all"} and normalized["localPackage"] is not None:
        workstation = tear_down_workstation_package(normalized["localPackage"])
        mutated = mutated or workstation["mutated"]

    return {
        "schemaVersion": 3,
        "ownerRepo": normalized["ownerRepo"],
        "appSlug": normalized["appSlug"],
        "scope": normalized["scope"],
        "environments": environments,
        "workstation": workstation,
        "productionEnvironments": normalized["productionEnvironments"],
        "productionDataIncluded": bool(normalized["productionEnvironments"]),
        "publicIngressScopes": normalized["publicIngressScopes"],
        "publicIngressIncluded": bool(normalized["publicIngressScopes"]),
        "mutated": mutated,
    }


def render_teardown_summary(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
