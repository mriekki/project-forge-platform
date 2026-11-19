"""Generic immutable application-runtime deployment for Kit-managed hosts."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import subprocess
from typing import Any, Iterable

from .box_platform import platform_status
from .box_platform_assets import CADDY_CONTAINER, NETWORK_NAME
from .errors import DeploymentKitError
from .profiles import load_profile
from .ssh import ssh_args, verify_access
from .app_runtime_remote import REMOTE_SCRIPT

APP_ROOT = "/srv/project-forge-apps"
APP_SCHEMA_VERSION = 1
# Operator-provisioned remote sources: never workstation paths or auto-created directories.
REMOTE_MATERIAL_ROOT = "/srv/project-forge-material"
APP_DEPLOY_WRITE_PHRASE = "[APP DEPLOY WRITE]"
PRODUCTION_APP_DEPLOY_WRITE_PHRASE = "[PRODUCTION APP DEPLOY]"

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_IMAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$"
)
_RUN_AS_RE = re.compile(r"^[0-9]+(?::[0-9]+)?$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEALTH_PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/\-]*$")
_CONTAINER_PATH_RE = re.compile(r"^/[A-Za-z0-9._~+:/\-]*$")


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _container_name(value: str) -> str:
    if not isinstance(value, str) or _CONTAINER_RE.fullmatch(value) is None:
        raise DeploymentKitError("containerName contains unsupported characters.")
    return value


def _image(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_RE.fullmatch(value) is None:
        raise DeploymentKitError("image must be an immutable image reference ending in @sha256:<64 lowercase hex>.")
    return value


def _runtime_port(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise DeploymentKitError("runtimePort must be an integer from 1 through 65535.")
    return value


def _health_path(value: str) -> str:
    if not isinstance(value, str) or _HEALTH_PATH_RE.fullmatch(value) is None:
        raise DeploymentKitError("healthPath must be a safe absolute HTTP path.")
    return value


def _run_as(value: str) -> str:
    if not isinstance(value, str) or _RUN_AS_RE.fullmatch(value) is None:
        raise DeploymentKitError("runAs must be a numeric UID or UID:GID.")
    return value


def _container_path(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _CONTAINER_PATH_RE.fullmatch(value) is None or "/../" in f"{value}/":
        raise DeploymentKitError("dataContainerPath must be a safe absolute container path.")
    return value.rstrip("/") or "/"



def _normalize_read_only_materials(
    materials: Iterable[tuple[str, str]] | None,
    *,
    data_path: str | None,
) -> list[dict[str, str]]:
    if materials is None:
        return []
    result: list[dict[str, str]] = []
    names: set[str] = set()
    paths: list[str] = []
    for name, target in materials:
        if len(result) >= 8:
            raise DeploymentKitError("Remote read-only material mount count must not exceed eight.")
        name = _slug(name, "read-only material name")
        if name in names:
            raise DeploymentKitError(f"Duplicate read-only material name: {name}")
        if not isinstance(target, str) or _CONTAINER_PATH_RE.fullmatch(target) is None:
            raise DeploymentKitError("Read-only material target must be a safe absolute container directory.")
        parts = target.split("/")[1:]
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise DeploymentKitError("Read-only material target must be normalized and cannot be root.")
        if parts[0] in {"proc", "sys", "dev", "run"} or parts[:2] == ["var", "run"]:
            raise DeploymentKitError("Read-only material cannot mask a container system runtime directory.")
        for other in paths + ([data_path] if data_path else []):
            if target == other or target.startswith(other.rstrip("/") + "/") or other.startswith(target + "/"):
                raise DeploymentKitError("Read-only material target overlaps another mount.")
        names.add(name)
        paths.append(target)
        result.append({"name": name, "containerPath": target})
    return sorted(result, key=lambda item: item["name"])


def _material_evidence_for_spec(name: str, spec: dict[str, Any]) -> dict[str, str] | None:
    materials = spec.get("readOnlyMaterials")
    if not materials:
        return None
    profile = load_profile(name)
    evidence = verify_access(profile)
    output = _run_remote(profile, evidence["address"], "material-inspect", spec=spec)
    observed: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] != "MATERIAL":
            raise DeploymentKitError("Malformed remote material source evidence.")
        _, material_name, identity = parts
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", material_name) or not re.fullmatch(r"[0-9]+:[0-9]+", identity):
            raise DeploymentKitError("Malformed remote material source identity.")
        if material_name in observed:
            raise DeploymentKitError("Duplicate remote material source evidence.")
        observed[material_name] = identity
    if set(observed) != {item["name"] for item in materials}:
        raise DeploymentKitError("Remote material inspection omitted or added a source.")
    return dict(sorted(observed.items()))


def _verify_material_evidence(name: str, plan: dict[str, Any]) -> None:
    if plan["spec"].get("readOnlyMaterials"):
        if _material_evidence_for_spec(name, plan["spec"]) != plan["readOnlyMaterialEvidence"]:
            raise DeploymentKitError("Remote material directory identity changed after planning; review a new plan.")

def _normalize_environment_variables(items: dict[str, str] | Iterable[tuple[str, str]]) -> dict[str, str]:
    pairs = items.items() if isinstance(items, dict) else items
    result: dict[str, str] = {}
    for key, value in pairs:
        if not isinstance(key, str) or _ENV_KEY_RE.fullmatch(key) is None:
            raise DeploymentKitError(f"Invalid environment variable name: {key!r}")
        if key in result:
            raise DeploymentKitError(f"Duplicate environment variable: {key}")
        if not isinstance(value, str) or "\x00" in value or "\n" in value or "\r" in value:
            raise DeploymentKitError(f"Environment variable {key} contains unsupported control characters.")
        result[key] = value
    return dict(sorted(result.items()))


def normalize_app_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    container_name: str,
    image: str,
    runtime_port: int,
    health_path: str,
    run_as: str,
    persistence_mode: str,
    data_container_path: str | None,
    environment_variables: dict[str, str] | Iterable[tuple[str, str]],
    read_only_materials: Iterable[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if persistence_mode not in {"none", "directory"}:
        raise DeploymentKitError("persistenceMode must be 'none' or 'directory'.")
    data_path = _container_path(data_container_path)
    if persistence_mode == "directory" and data_path is None:
        raise DeploymentKitError("directory persistence requires dataContainerPath.")
    if persistence_mode == "none" and data_path is not None:
        raise DeploymentKitError("dataContainerPath must be omitted when persistenceMode is 'none'.")
    spec = {
        "schemaVersion": APP_SCHEMA_VERSION,
        "ownerRepo": _owner_repo(owner_repo),
        "environment": _slug(environment, "environment"),
        "appSlug": _slug(app_slug, "appSlug"),
        "containerName": _container_name(container_name),
        "image": _image(image),
        "runtimePort": _runtime_port(runtime_port),
        "healthPath": _health_path(health_path),
        "runAs": _run_as(run_as),
        "persistence": {
            "mode": persistence_mode,
            "dataContainerPath": data_path,
        },
        "environmentVariables": _normalize_environment_variables(environment_variables),
    }
    materials = _normalize_read_only_materials(read_only_materials, data_path=data_path)
    if materials:
        spec["readOnlyMaterials"] = materials
    spec["specSha256"] = _spec_sha(spec)
    return spec


def _spec_sha(spec: dict[str, Any]) -> str:
    value = {key: spec[key] for key in spec if key != "specSha256"}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def build_remote_script(
    spec: dict[str, Any] | None = None, *, expected_materials: dict[str, str] | None = None,
) -> str:
    env_keys: list[str] = []
    material_names: list[str] = []
    material_targets: list[str] = []
    material_expected: list[str] = []
    env_values: list[str] = []
    desired = {
        "ownerRepo": "",
        "environment": "",
        "appSlug": "",
        "containerName": "",
        "image": "",
        "runtimePort": "",
        "healthPath": "",
        "runAs": "",
        "persistenceMode": "",
        "dataContainerPath": "",
        "specSha256": "",
    }
    if spec is not None:
        desired.update(
            ownerRepo=spec["ownerRepo"],
            environment=spec["environment"],
            appSlug=spec["appSlug"],
            containerName=spec["containerName"],
            image=spec["image"],
            runtimePort=str(spec["runtimePort"]),
            healthPath=spec["healthPath"],
            runAs=spec["runAs"],
            persistenceMode=spec["persistence"]["mode"],
            dataContainerPath=spec["persistence"]["dataContainerPath"] or "",
            specSha256=spec["specSha256"],
        )
        for key, value in spec["environmentVariables"].items():
            env_keys.append(_b64(key))
            env_values.append(_b64(value))
        for item in spec.get("readOnlyMaterials", []):
            material_names.append(_b64(item["name"]))
            material_targets.append(_b64(item["containerPath"]))
            material_expected.append((expected_materials or {}).get(item["name"], ""))

    replacements = {
        "__APP_ROOT__": APP_ROOT,
        "__MATERIAL_ROOT__": REMOTE_MATERIAL_ROOT,
        "__APP_SCHEMA_VERSION__": str(APP_SCHEMA_VERSION),
        "__NETWORK_NAME__": NETWORK_NAME,
        "__CADDY_CONTAINER__": CADDY_CONTAINER,
        "__DESIRED_PRESENT__": "true" if spec is not None else "false",
        "__D_OWNER_B64__": _b64(desired["ownerRepo"]),
        "__D_ENV_B64__": _b64(desired["environment"]),
        "__D_APP_B64__": _b64(desired["appSlug"]),
        "__D_CONTAINER_B64__": _b64(desired["containerName"]),
        "__D_IMAGE_B64__": _b64(desired["image"]),
        "__D_PORT__": desired["runtimePort"],
        "__D_HEALTH_B64__": _b64(desired["healthPath"]),
        "__D_RUN_AS_B64__": _b64(desired["runAs"]),
        "__D_PERSISTENCE__": desired["persistenceMode"],
        "__D_DATA_TARGET_B64__": _b64(desired["dataContainerPath"]),
        "__D_SPEC_SHA__": desired["specSha256"],
        "__D_ENV_KEYS__": " ".join(f"'{item}'" for item in env_keys),
        "__D_ENV_VALUES__": " ".join(f"'{item}'" for item in env_values),
        "__D_MATERIAL_NAMES__": " ".join(shlex.quote(x) for x in material_names),
        "__D_MATERIAL_TARGETS__": " ".join(shlex.quote(x) for x in material_targets),
        "__D_MATERIAL_EXPECTED__": " ".join(shlex.quote(x) for x in material_expected),
    }
    script = REMOTE_SCRIPT
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    if "__" in script:
        raise DeploymentKitError("Internal application-runtime script contains an unresolved placeholder.")
    return script


def _parse_inventory(output: str) -> dict[str, Any]:
    apps: list[dict[str, Any]] = []
    summary: dict[str, str] = {}
    for raw in output.splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        if parts[0] == "SUMMARY":
            if len(parts) != 3 or parts[1] in summary:
                raise DeploymentKitError("Malformed or duplicate application inventory summary.")
            summary[parts[1]] = parts[2]
            continue
        if parts[0] != "APP" or len(parts) not in (15, 17, 19):
            raise DeploymentKitError("Malformed application inventory record.")
        try:
            port = int(parts[7])
        except ValueError as error:
            raise DeploymentKitError("Malformed application inventory runtime port.") from error
        if any(value not in {"true", "false"} for value in parts[12:15]):
            raise DeploymentKitError("Malformed application inventory boolean value.")
        owner = _owner_repo(parts[1])
        environment = _slug(parts[2], "environment")
        app_slug = _slug(parts[3], "appSlug")
        container = _container_name(parts[4])
        image = _image(parts[5])
        if re.fullmatch(r"[0-9a-f]{64}", parts[6]) is None:
            raise DeploymentKitError("Malformed application inventory spec fingerprint.")
        health_path = _health_path(parts[8])
        if parts[9] not in {"none", "directory"}:
            raise DeploymentKitError("Malformed application inventory persistence mode.")
        app = {
            "ownerRepo": owner,
            "environment": environment,
            "appSlug": app_slug,
            "containerName": container,
            "image": image,
            "specSha256": parts[6],
            "runtimePort": port,
            "healthPath": health_path,
            "persistenceMode": parts[9],
            "currentRelease": parts[10] or None,
            "previousRelease": parts[11] or None,
            "containerRunning": parts[12] == "true",
            "connectedToSharedNetwork": parts[13] == "true",
            "httpHealthy": parts[14] == "true",
        }
        has_materials = len(parts) == 19 or (len(parts) == 17 and parts[16] not in {"true", "false"})
        if has_materials:
            if parts[15] not in {"true", "false"} or not parts[16]:
                raise DeploymentKitError("Malformed remote material mount readiness.")
            materials: list[dict[str, str]] = []
            for encoded in parts[16].split(";"):
                pieces = encoded.split("@")
                if len(pieces) != 3 or re.fullmatch(r"[0-9]+:[0-9]+", pieces[2]) is None:
                    raise DeploymentKitError("Malformed remote material inventory identity.")
                materials.append({
                    "name": pieces[0],
                    "containerPath": pieces[1],
                    "sourceIdentity": pieces[2],
                })
            normalized = _normalize_read_only_materials(
                [(item["name"], item["containerPath"]) for item in materials],
                data_path=None,
            )
            if [(item["name"], item["containerPath"]) for item in normalized] != [
                (item["name"], item["containerPath"]) for item in materials
            ]:
                raise DeploymentKitError("Remote material inventory is unordered or conflicting.")
            app["readOnlyMaterials"] = materials
            app["materialMountsVerified"] = parts[15] == "true"
        image_flags = parts[17:19] if len(parts) == 19 else parts[15:17] if len(parts) == 17 and not has_materials else []
        if image_flags:
            if any(value not in {"true", "false"} for value in image_flags):
                raise DeploymentKitError("Malformed live container image evidence.")
            present, matches = (value == "true" for value in image_flags)
            if (not present and (matches or app["containerRunning"] or app["connectedToSharedNetwork"] or app["httpHealthy"])) or (
                not matches and app["httpHealthy"]
            ):
                raise DeploymentKitError("Inconsistent live container image evidence.")
            app["containerPresent"] = present
            app["imageMatchesRelease"] = matches
        apps.append(app)
    if set(summary) != {"appCount"}:
        raise DeploymentKitError("Application inventory omitted appCount.")
    try:
        count = int(summary["appCount"])
    except ValueError as error:
        raise DeploymentKitError("Malformed application inventory count.") from error
    if count != len(apps):
        raise DeploymentKitError("Application inventory count does not match records.")
    keys = [(item["appSlug"], item["environment"]) for item in apps]
    if len(keys) != len(set(keys)):
        raise DeploymentKitError("Duplicate application/environment ownership records were reported.")
    return {"applications": sorted(apps, key=lambda item: (item["appSlug"], item["environment"]))}


def _run_remote(
    profile: dict[str, Any],
    address: str,
    action: str,
    *,
    spec: dict[str, Any] | None = None,
    expected_spec_sha: str = "",
    expected_materials: dict[str, str] | None = None,
) -> str:
    if action not in {"inventory", "deploy", "material-inspect", "release-inspect"}:
        raise DeploymentKitError(f"Unsupported application-runtime action: {action}")
    args = [action]
    if action == "deploy":
        args.extend([expected_spec_sha or "NONE", profile["user"]])
    command = ssh_args(
        profile,
        address,
        command="sudo -n bash -s -- " + " ".join(args),
    )
    completed = subprocess.run(
        command,
        input=build_remote_script(spec, expected_materials=expected_materials).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote application-runtime {action} failed: {detail}")
    return stdout


def app_inventory(name: str) -> dict[str, Any]:
    profile = load_profile(name)
    evidence = verify_access(profile)
    inventory = _parse_inventory(
        _run_remote(profile, evidence["address"], "inventory")
    )
    inventory["targetName"] = name
    inventory["verifiedAddress"] = evidence["address"]
    inventory["mutated"] = False
    return inventory


def _parse_verified_release_observation(output: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Parse one privileged read-only host line, never arbitrary app JSON.

    Only the dedicated SSH + sudo host action may feed this function in a
    Production emitter. Structural parsing alone grants no release authority.
    """
    lines = output.splitlines()
    if len(lines) != 1:
        raise DeploymentKitError("Live release observer emitted no unique host record.")
    fields = lines[0].split("\t")
    if len(fields) != 12 or fields[0] != "RELEASE_OBSERVATION":
        raise DeploymentKitError("Live release observer record is malformed.")
    _, owner, app, environment, image, spec_sha, source, manifest, version, runtime_id, generation, operation = fields
    if (
        owner != spec["ownerRepo"] or app != spec["appSlug"]
        or environment != spec["environment"] or image != spec["image"]
        or spec_sha != spec["specSha256"]
        or re.fullmatch(r"[0-9a-f]{40}", source) is None
        or re.fullmatch(r"[0-9a-f]{64}", manifest) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", runtime_id) is None
        or re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?", version) is None
        or re.fullmatch(r"[1-9][0-9]{0,17}", generation) is None
        or re.fullmatch(r"pfrelease:[0-9a-f]{64}", operation) is None
    ):
        raise DeploymentKitError("Observed live release does not match the exact authorized runtime spec.")
    return {
        "ownerRepo": owner, "appSlug": app, "environment": environment,
        "registryImage": image, "specSha256": spec_sha,
        "sourceCommit": source, "manifestSha256": manifest,
        "releaseVersion": version, "runtimeImageId": runtime_id,
        "deploymentGeneration": int(generation),
        "postApplyOperationId": operation,
        "containerPresent": True, "imageMatchesRelease": True,
        "containerRunning": True, "connectedToSharedNetwork": True,
        "httpHealthy": True, "materialMountsVerified": True,
    }


def observe_verified_app_release(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Read the currently running exact release through the reviewed SSH peer.

    No CLI command, signing key, standalone Production publication or
    authentication is inferred from this function. It is a callable adapter
    for a separately authorized Deployment Kit post-apply signer.
    """
    if not isinstance(spec, dict) or not {
        "ownerRepo", "appSlug", "environment", "image", "specSha256"
    }.issubset(spec):
        raise DeploymentKitError("Exact authorized application spec missing.")
    if platform_status(name)["state"] != "ready":
        raise DeploymentKitError("Shared host platform is not ready for release inspection.")
    profile = load_profile(name)
    access = verify_access(profile)
    output = _run_remote(profile, access["address"], "release-inspect", spec=spec)
    return _parse_verified_release_observation(output, spec)


def _inventory_snapshot(inventory: dict[str, Any]) -> str:
    value = {"applications": inventory["applications"]}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _find_app(inventory: dict[str, Any], app_slug: str, environment: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in inventory["applications"]
            if item["appSlug"] == app_slug and item["environment"] == environment
        ),
        None,
    )


def plan_app_deploy(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    platform = platform_status(name)
    if platform["state"] != "ready":
        raise DeploymentKitError(
            f"Application deployment requires a ready shared platform; target '{name}' is '{platform['state']}'."
        )
    inventory = app_inventory(name)
    existing = _find_app(inventory, spec["appSlug"], spec["environment"])
    if existing is not None and existing["ownerRepo"] != spec["ownerRepo"]:
        raise DeploymentKitError("Application/environment ownership does not match the requested repository.")
    if existing is not None:
        if type(existing.get("containerPresent")) is not bool or type(existing.get("imageMatchesRelease")) is not bool:
            raise DeploymentKitError("Application inventory lacks live container image evidence; refresh it before deploying.")
        if existing["containerPresent"] and not existing["imageMatchesRelease"]:
            raise DeploymentKitError("Live container image differs from the managed release; reconcile ownership before deploying.")
    for item in inventory["applications"]:
        if (
            item["containerName"] == spec["containerName"]
            and (item["appSlug"], item["environment"])
            != (spec["appSlug"], spec["environment"])
        ):
            raise DeploymentKitError(
                f"Container name collision with managed app {item['appSlug']}--{item['environment']}."
            )
    if (
        existing is not None
        and existing["specSha256"] == spec["specSha256"]
        and existing["containerRunning"]
        and existing["connectedToSharedNetwork"]
        and existing["httpHealthy"]
        and existing.get("materialMountsVerified", True)
    ):
        raise DeploymentKitError("The exact application runtime spec is already deployed and healthy.")
    plan = {
        "targetName": name,
        "action": "deploy",
        "environment": spec["environment"],
        "appSlug": spec["appSlug"],
        "ownerRepo": spec["ownerRepo"],
        "containerName": spec["containerName"],
        "image": spec["image"],
        "runtimePort": spec["runtimePort"],
        "healthPath": spec["healthPath"],
        "persistenceMode": spec["persistence"]["mode"],
        "changeType": "update" if existing is not None else "create",
        "previousImage": existing["image"] if existing is not None else None,
        "previousRelease": existing["currentRelease"] if existing is not None else None,
        "retainsPreviousRelease": existing is not None,
        "publishesHostPort": False,
        "attachesSharedNetwork": NETWORK_NAME,
        "modifiesRoutes": False,
        "persistentDataDeletion": False,
        "inventorySnapshot": _inventory_snapshot(inventory),
        "expectedSpecSha256": existing["specSha256"] if existing is not None else None,
        "spec": spec,
    }
    if spec.get("readOnlyMaterials"):
        plan["readOnlyMaterialEvidence"] = _material_evidence_for_spec(name, spec)
    return plan


def deploy_write_phrase(plan: dict[str, Any]) -> str:
    return (
        PRODUCTION_APP_DEPLOY_WRITE_PHRASE
        if plan["environment"] == "production"
        else APP_DEPLOY_WRITE_PHRASE
    )


def render_locked_app_deploy_stage(
    plan: dict[str, Any], *, inherited_lock_fd: int, authorization: str, production: bool = False,
) -> dict[str, str]:
    """Render a Kit-validated deployment stage for an existing remote lock scope.

    The returned Bash stage is not an SSH command or authorization to run it.
    The caller must hold the exact app/environment lock in the same privileged
    remote shell and keep it through its application-specific checks and this
    stage. The remote script verifies the inherited descriptor before deploy.
    """
    required = {
        "targetName",
        "action",
        "environment",
        "appSlug",
        "ownerRepo",
        "containerName",
        "image",
        "runtimePort",
        "healthPath",
        "persistenceMode",
        "changeType",
        "previousImage",
        "previousRelease",
        "retainsPreviousRelease",
        "publishesHostPort",
        "attachesSharedNetwork",
        "modifiesRoutes",
        "persistentDataDeletion",
        "inventorySnapshot",
        "expectedSpecSha256",
        "spec",
    }
    if not isinstance(plan, dict) or set(plan) != required | ({"readOnlyMaterialEvidence"} if plan.get("spec", {}).get("readOnlyMaterials") else set()) or plan["action"] != "deploy":
        raise DeploymentKitError("Malformed application deployment plan.")
    if (plan["changeType"] != "update" or plan["retainsPreviousRelease"] is not True
            or not isinstance(plan["expectedSpecSha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", plan["expectedSpecSha256"]) is None):
        raise DeploymentKitError("Lock handoff is limited to an existing application deployment update.")
    if type(inherited_lock_fd) is not int or not 3 <= inherited_lock_fd <= 256:
        raise DeploymentKitError("Inherited remote lock descriptor must be an integer between 3 and 256.")
    if type(production) is not bool:
        raise DeploymentKitError("Production classification must be a boolean.")
    expected_authorization = (
        PRODUCTION_APP_DEPLOY_WRITE_PHRASE
        if production or plan["environment"] == "production"
        else APP_DEPLOY_WRITE_PHRASE
    )
    if authorization != expected_authorization:
        raise DeploymentKitError("Exact reviewed application deployment authorization phrase is required.")

    platform = platform_status(plan["targetName"])
    if platform["state"] != "ready":
        raise DeploymentKitError("Shared host platform is no longer ready; application deployment is blocked.")
    current = app_inventory(plan["targetName"])
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Application inventory changed after the plan was reviewed; create and authorize a fresh plan."
        )
    profile = load_profile(plan["targetName"])
    evidence = verify_access(profile)
    _verify_material_evidence(plan["targetName"], plan)
    script = build_remote_script(plan["spec"], expected_materials=plan.get("readOnlyMaterialEvidence"))
    delimiter = "PROJECT_FORGE_APP_DEPLOY_STAGE_" + hashlib.sha256(script.encode()).hexdigest()[:24]
    if delimiter in script:
        raise DeploymentKitError("Unsafe application deployment script delimiter collision.")
    command = "bash -s -- " + shlex.join([
        "deploy", plan["expectedSpecSha256"], profile["user"], str(inherited_lock_fd),
    ])
    return {
        "targetName": plan["targetName"],
        "verifiedAddress": evidence["address"],
        "action": "deploy",
        "script": f"{command} <<'{delimiter}'\n{script.rstrip()}\n{delimiter}\n",
    }


def apply_app_deploy(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "targetName",
        "action",
        "environment",
        "appSlug",
        "ownerRepo",
        "containerName",
        "image",
        "runtimePort",
        "healthPath",
        "persistenceMode",
        "changeType",
        "previousImage",
        "previousRelease",
        "retainsPreviousRelease",
        "publishesHostPort",
        "attachesSharedNetwork",
        "modifiesRoutes",
        "persistentDataDeletion",
        "inventorySnapshot",
        "expectedSpecSha256",
        "spec",
    }
    if not isinstance(plan, dict) or set(plan) != required | ({"readOnlyMaterialEvidence"} if plan.get("spec", {}).get("readOnlyMaterials") else set()) or plan["action"] != "deploy":
        raise DeploymentKitError("Malformed application deployment plan.")

    current = app_inventory(plan["targetName"])
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Application inventory changed after the plan was reviewed; create and authorize a fresh plan."
        )
    platform = platform_status(plan["targetName"])
    if platform["state"] != "ready":
        raise DeploymentKitError("Shared host platform is no longer ready; application deployment is blocked.")

    _verify_material_evidence(plan["targetName"], plan)
    profile = load_profile(plan["targetName"])
    evidence = verify_access(profile)
    _run_remote(
        profile,
        evidence["address"],
        "deploy",
        spec=plan["spec"],
        expected_spec_sha=plan["expectedSpecSha256"] or "",
        expected_materials=plan.get("readOnlyMaterialEvidence"),
    )
    final = app_inventory(plan["targetName"])
    deployed = _find_app(final, plan["appSlug"], plan["environment"])
    if deployed is None:
        raise DeploymentKitError("Application deployment returned without managed runtime state.")
    if deployed["specSha256"] != plan["spec"]["specSha256"]:
        raise DeploymentKitError("Application deployment returned with a different runtime spec.")
    if not (
        deployed.get("containerPresent") is True
        and deployed.get("imageMatchesRelease") is True
        and deployed["containerRunning"]
        and deployed["connectedToSharedNetwork"]
        and deployed["httpHealthy"]
        and deployed.get("materialMountsVerified", True)
    ):
        raise DeploymentKitError("Application deployment completed but runtime readiness is not healthy.")
    final["mutated"] = True
    return final
