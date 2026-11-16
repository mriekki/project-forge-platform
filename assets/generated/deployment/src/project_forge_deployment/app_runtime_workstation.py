"""Remote application deployment using an exact image transferred from the workstation."""

from __future__ import annotations

import re
import subprocess
from typing import Any

from .app_runtime import (
    NETWORK_NAME,
    _find_app,
    _inventory_snapshot,
    _verify_material_evidence,
    app_inventory,
    build_remote_script,
)
from .box_platform import platform_status
from .errors import DeploymentKitError
from .image_transfer import transfer_image
from .profiles import load_profile
from .ssh import ssh_args, verify_access


_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _runtime_image_id(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_ID_RE.fullmatch(value) is None:
        raise DeploymentKitError("Preloaded runtime image ID must be sha256:<64 lowercase hex>.")
    return value


def _preloaded_script(
    spec: dict[str, Any], runtime_image_id: str, *, expected_materials: dict[str, str] | None = None,
) -> str:
    runtime_image = _runtime_image_id(runtime_image_id)
    script = build_remote_script(spec, expected_materials=expected_materials)
    registry_block = "    decode_desired\n    configure_registry_auth\n"
    if registry_block not in script:
        raise DeploymentKitError("Application runtime template no longer contains the expected registry-auth hook.")
    script = script.replace(registry_block, "    decode_desired\n", 1)

    pull = (
        '    docker pull "$D_IMAGE" >/dev/null\n'
        '    D_RUNTIME_IMAGE_ID="$(docker image inspect --format \'{{.Id}}\' "$D_IMAGE")" || {\n'
        '        echo "Pulled application image could not be inspected." >&2; exit 35;\n'
        '    }\n'
    )
    replacement = (
        f'    D_RUNTIME_IMAGE_ID="$(docker image inspect --format \'{{{{.Id}}}}\' "{runtime_image}")" || {{\n'
        '        echo "Exact application image ID was not preloaded by the workstation-mediated deployment path." >&2\n'
        "        exit 40;\n"
        "    }\n"
        f'    [[ "$D_RUNTIME_IMAGE_ID" == "{runtime_image}" ]] || {{\n'
        '        echo "Preloaded application image resolved to a different Docker config ID." >&2; exit 40;\n'
        "    }\n"
    )
    if pull not in script:
        raise DeploymentKitError("Application runtime template no longer contains the expected image-pull hook.")
    script = script.replace(pull, replacement, 1)

    runtime_hook = '    docker_args+=("$D_IMAGE")\n'
    if runtime_hook not in script:
        raise DeploymentKitError("Application runtime template no longer contains the expected runtime-image hook.")
    script = script.replace(runtime_hook, f'    docker_args+=("{runtime_image}")\n', 1)
    return script


def _validate_plan(plan: dict[str, Any]) -> None:
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
    if (not isinstance(plan, dict) or
            set(plan) != required | ({"readOnlyMaterialEvidence"} if plan.get("spec", {}).get("readOnlyMaterials") else set()) or
            plan["action"] != "deploy"):
        raise DeploymentKitError("Malformed application deployment plan.")


def _validate_transfer(plan: dict[str, Any], transfer: dict[str, Any]) -> str:
    required = {
        "targetName",
        "image",
        "registryDigest",
        "localImageId",
        "remoteImageId",
        "runtimeImage",
        "status",
        "mutated",
    }
    if not isinstance(transfer, dict) or set(transfer) != required:
        raise DeploymentKitError("Malformed workstation image-transfer evidence.")
    if transfer["targetName"] != plan["targetName"]:
        raise DeploymentKitError("Image-transfer target does not match the deployment plan.")
    if transfer["registryDigest"] != plan["image"] or transfer["image"] != plan["image"]:
        raise DeploymentKitError("Image-transfer registry digest does not match the deployment plan.")
    local_id = _runtime_image_id(transfer["localImageId"])
    remote_id = _runtime_image_id(transfer["remoteImageId"])
    runtime_id = _runtime_image_id(transfer["runtimeImage"])
    if not (local_id == remote_id == runtime_id):
        raise DeploymentKitError("Workstation and remote Docker image IDs do not match.")
    if transfer["status"] not in {"already-present", "transferred"} or not isinstance(transfer["mutated"], bool):
        raise DeploymentKitError("Image-transfer evidence has an invalid terminal state.")
    return runtime_id


def _run_preloaded_deploy(
    profile: dict[str, Any],
    address: str,
    spec: dict[str, Any],
    expected_spec_sha: str,
    runtime_image_id: str,
    expected_materials: dict[str, str] | None,
) -> None:
    command = ssh_args(
        profile,
        address,
        command="sudo -n bash -s -- deploy " + (expected_spec_sha or "NONE") + " " + profile["user"],
    )
    completed = subprocess.run(
        command,
        input=_preloaded_script(spec, runtime_image_id, expected_materials=expected_materials).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Workstation-mediated remote application deployment failed: {detail}")


def apply_app_deploy_with_preloaded_image(
    plan: dict[str, Any], transfer: dict[str, Any]
) -> dict[str, Any]:
    """Apply a reviewed deployment plan using already-verified transfer evidence."""

    _validate_plan(plan)
    runtime_image_id = _validate_transfer(plan, transfer)

    current = app_inventory(plan["targetName"])
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Application inventory changed while transferring the image; create and authorize a fresh plan."
        )
    platform = platform_status(plan["targetName"])
    if platform["state"] != "ready":
        raise DeploymentKitError("Shared host platform changed while transferring the image; deployment is blocked.")

    _verify_material_evidence(plan["targetName"], plan)
    profile = load_profile(plan["targetName"])
    evidence = verify_access(profile)
    _run_preloaded_deploy(
        profile,
        evidence["address"],
        plan["spec"],
        plan["expectedSpecSha256"] or "",
        runtime_image_id,
        plan.get("readOnlyMaterialEvidence"),
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
    final["imageSource"] = "workstation-transfer"
    final["imageTransfer"] = transfer
    final["attachesSharedNetwork"] = NETWORK_NAME
    return final


def apply_app_deploy_from_workstation(plan: dict[str, Any]) -> dict[str, Any]:
    _validate_plan(plan)

    current = app_inventory(plan["targetName"])
    if _inventory_snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError(
            "Application inventory changed after the plan was reviewed; create and authorize a fresh plan."
        )
    platform = platform_status(plan["targetName"])
    if platform["state"] != "ready":
        raise DeploymentKitError("Shared host platform is no longer ready; application deployment is blocked.")

    transfer = transfer_image(plan["targetName"], plan["image"])
    return apply_app_deploy_with_preloaded_image(plan, transfer)
