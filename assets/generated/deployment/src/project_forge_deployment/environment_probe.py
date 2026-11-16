"""Disposable end-to-end proof for one named remote deployment environment."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from typing import Any

from .app_runtime import normalize_app_spec, plan_app_deploy
from .app_runtime_workstation import apply_app_deploy_with_preloaded_image
from .box_platform import platform_status
from .environment_isolation import environment_isolation_preflight
from .errors import DeploymentKitError
from .image_transfer import remote_image_present, transfer_image, verify_local_image
from .proof_receipt import write_environment_proof_receipt
from .registry_access import normalize_registry_image
from .teardown import tear_down_project

ENVIRONMENT_PROOF_WRITE_PHRASE = "[ENVIRONMENT PROOF WRITE]"
PRODUCTION_ENVIRONMENT_PROOF_WRITE_PHRASE = "[PRODUCTION ENVIRONMENT PROOF]"
DEFAULT_PROBE_IMAGE = "nginx:alpine"

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        raise DeploymentKitError("Docker CLI is unavailable on the workstation.")
    return path


def _probe_slug(owner_repo: str) -> str:
    digest = hashlib.sha256(owner_repo.encode("utf-8")).hexdigest()[:10]
    return f"project-forge-env-probe-{digest}"


def _resolve_probe_image(image_tag: str) -> str:
    if not isinstance(image_tag, str) or not image_tag.strip() or "@sha256:" in image_tag:
        raise DeploymentKitError("probeImage must be a non-empty mutable image tag; Project Forge resolves it to an exact digest.")
    docker = _docker()
    pulled = subprocess.run(
        [docker, "pull", image_tag],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if pulled.returncode != 0:
        raise DeploymentKitError(
            "Environment proof image pull failed: " + (pulled.stderr or pulled.stdout).strip()
        )
    inspected = subprocess.run(
        [docker, "image", "inspect", "--format", "{{json .RepoDigests}}", image_tag],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if inspected.returncode != 0:
        raise DeploymentKitError(
            "Environment proof image digest inspection failed: " + (inspected.stderr or inspected.stdout).strip()
        )
    try:
        digests = json.loads(inspected.stdout.strip())
    except json.JSONDecodeError as error:
        raise DeploymentKitError("Environment proof image inspection returned malformed RepoDigests JSON.") from error
    if not isinstance(digests, list):
        raise DeploymentKitError("Environment proof image inspection did not return a RepoDigests list.")
    for item in digests:
        try:
            return normalize_registry_image(item)
        except DeploymentKitError:
            continue
    raise DeploymentKitError("Environment proof image has no usable immutable sha256 RepoDigest.")


def _proof_isolation_preflight(
    target_name: str,
    *,
    owner_repo: str,
    environment: str,
    production: bool,
    probe_app_slug: str,
) -> dict[str, Any]:
    return environment_isolation_preflight(
        target_name,
        owner_repo=owner_repo,
        environment=environment,
        production=production,
        app_slug=probe_app_slug,
        container_name=f"{probe_app_slug}--{environment}",
        runtime_port=80,
        persistence_mode="none",
        require_vacant_app_identity=True,
    )


def plan_environment_proof(
    target_name: str,
    *,
    owner_repo: str,
    environment: str,
    production: bool = False,
    probe_image: str = DEFAULT_PROBE_IMAGE,
) -> dict[str, Any]:
    owner = _owner_repo(owner_repo)
    env = _slug(environment, "environment")
    if not isinstance(production, bool):
        raise DeploymentKitError("production must be true or false.")
    if not isinstance(probe_image, str) or not probe_image.strip():
        raise DeploymentKitError("probeImage must be a non-empty image tag.")
    platform = platform_status(target_name)
    if platform.get("state") != "ready":
        raise DeploymentKitError(
            f"Environment proof requires a ready shared platform; target '{target_name}' is '{platform.get('state', 'unknown')}'."
        )
    probe_app_slug = _probe_slug(owner)
    isolation = _proof_isolation_preflight(
        target_name,
        owner_repo=owner,
        environment=env,
        production=production,
        probe_app_slug=probe_app_slug,
    )
    return {
        "targetName": target_name,
        "ownerRepo": owner,
        "environment": env,
        "production": production,
        "probeAppSlug": probe_app_slug,
        "probeImageTag": probe_image,
        "artifactDelivery": "workstation-transfer",
        "persistence": "none",
        "healthPath": "/",
        "cleanup": "automatic",
        "isolationPreflight": isolation,
        "runnable": isolation["state"] == "clear",
        "requiredAuthorization": (
            PRODUCTION_ENVIRONMENT_PROOF_WRITE_PHRASE if production else ENVIRONMENT_PROOF_WRITE_PHRASE
        ),
    }


def _proof_result(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "targetName": plan["targetName"],
        "ownerRepo": plan["ownerRepo"],
        "environment": plan["environment"],
        "production": plan["production"],
        "probeAppSlug": plan["probeAppSlug"],
        "probeImageTag": plan["probeImageTag"],
        "preflight": {
            "targetAccess": "verified-by-platform-doctor",
            "hostPlatform": "ready",
            "environmentIsolation": plan["isolationPreflight"]["state"],
            "isolationEvidenceSha256": plan["isolationPreflight"]["evidenceSha256"],
        },
        "registryDigest": None,
        "localImageId": None,
        "transferState": "not-started",
        "remoteImageId": None,
        "runtimeState": "not-started",
        "httpHealth": "not-run",
        "cleanupState": "not-run",
        "imageCacheState": "unknown",
        "proof": "failed",
        "mutated": False,
        "finalMutationState": "none",
        "error": None,
        "cleanupError": None,
        "receipt": None,
        "receiptError": None,
    }


def _cleanup_state(cleanup: dict[str, Any] | None, environment: str) -> str:
    if not isinstance(cleanup, dict):
        return "unknown"
    entry = next(
        (item for item in cleanup.get("environments", []) if item.get("environment") == environment),
        None,
    )
    if not isinstance(entry, dict):
        return "unknown"
    state = entry.get("runtimeAndPersistentData", {}).get("state")
    return state if isinstance(state, str) and state else "unknown"


def _final_mutation_state(result: dict[str, Any]) -> str:
    cleanup = result["cleanupState"]
    cache = result["imageCacheState"]
    if cleanup not in {"removed", "absent", "not-run"}:
        return "cleanup-incomplete"
    if cache == "present":
        return "runtime-clean-image-cached"
    if result["mutated"] and cache == "absent":
        return "clean"
    if result["mutated"]:
        return "runtime-clean-cache-unknown"
    if result["transferState"] == "attempting" and cache == "unknown":
        return "mutation-unknown-after-transfer-attempt"
    return "none"


def run_environment_proof(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "targetName",
        "ownerRepo",
        "environment",
        "production",
        "probeAppSlug",
        "probeImageTag",
        "artifactDelivery",
        "persistence",
        "healthPath",
        "cleanup",
        "isolationPreflight",
        "runnable",
        "requiredAuthorization",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise DeploymentKitError("Malformed environment proof plan.")
    if plan["isolationPreflight"].get("state") != "clear" or not plan["runnable"]:
        raise DeploymentKitError(
            "Environment proof is blocked by the reviewed isolation/collision preflight; resolve the reported conflicts and create a fresh plan."
        )

    current_isolation = _proof_isolation_preflight(
        plan["targetName"],
        owner_repo=plan["ownerRepo"],
        environment=plan["environment"],
        production=plan["production"],
        probe_app_slug=plan["probeAppSlug"],
    )
    if current_isolation["state"] != "clear":
        raise DeploymentKitError(
            "Environment isolation became blocked after the proof plan was reviewed; no proof mutation was attempted."
        )
    if current_isolation["evidenceSha256"] != plan["isolationPreflight"].get("evidenceSha256"):
        raise DeploymentKitError(
            "Environment isolation evidence changed after the proof plan was reviewed; create and authorize a fresh plan."
        )

    result = _proof_result(plan)
    deploy_plan: dict[str, Any] | None = None
    transfer: dict[str, Any] | None = None
    deployment: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None
    operation_error: Exception | None = None

    try:
        exact_image = _resolve_probe_image(plan["probeImageTag"])
        result["registryDigest"] = exact_image
        local = verify_local_image(exact_image)
        result["localImageId"] = local["localImageId"]

        spec = normalize_app_spec(
            owner_repo=plan["ownerRepo"],
            environment=plan["environment"],
            app_slug=plan["probeAppSlug"],
            container_name=f"{plan['probeAppSlug']}--{plan['environment']}",
            image=exact_image,
            runtime_port=80,
            health_path=plan["healthPath"],
            run_as="0",
            persistence_mode="none",
            data_container_path=None,
            environment_variables={},
        )
        deploy_plan = plan_app_deploy(plan["targetName"], spec)

        result["transferState"] = "attempting"
        transfer = transfer_image(plan["targetName"], exact_image)
        result["transferState"] = transfer["status"]
        result["remoteImageId"] = transfer["remoteImageId"]
        result["mutated"] = bool(transfer["mutated"])

        result["runtimeState"] = "applying"
        deployment = apply_app_deploy_with_preloaded_image(deploy_plan, transfer)
        result["runtimeState"] = "healthy"
        result["httpHealth"] = "passed"
        result["mutated"] = True
    except Exception as error:  # terminal proof evidence must survive operational failure
        operation_error = error
        result["error"] = str(error)
        if result["runtimeState"] == "applying":
            result["runtimeState"] = "failed-or-partial"
            result["httpHealth"] = "failed-or-not-reached"
    finally:
        if deploy_plan is not None:
            try:
                cleanup = tear_down_project(
                    {
                        "ownerRepo": plan["ownerRepo"],
                        "appSlug": plan["probeAppSlug"],
                        "scope": plan["environment"],
                        "environmentTargets": {plan["environment"]: plan["targetName"]},
                        "localPackage": None,
                        "productionEnvironments": [plan["environment"]] if plan["production"] else [],
                    }
                )
                result["cleanupState"] = _cleanup_state(cleanup, plan["environment"])
                if result["cleanupState"] == "removed":
                    result["mutated"] = True
            except Exception as error:
                result["cleanupState"] = "failed"
                result["cleanupError"] = str(error)

        image_id = result.get("localImageId")
        if isinstance(image_id, str):
            try:
                cached = remote_image_present(plan["targetName"], image_id)
                result["imageCacheState"] = "present" if cached else "absent"
                if cached:
                    result["remoteImageId"] = image_id
                    if result["transferState"] == "attempting":
                        result["mutated"] = True
            except Exception:
                result["imageCacheState"] = "unknown"

    cleanup_terminal = result["cleanupState"] in {"removed", "absent"}
    if operation_error is None and result["cleanupError"] is None and cleanup_terminal:
        assert deployment is not None
        matched = next(
            (
                item
                for item in deployment.get("applications", [])
                if item.get("appSlug") == plan["probeAppSlug"]
                and item.get("environment") == plan["environment"]
            ),
            None,
        )
        if matched and matched.get("containerRunning") and matched.get("httpHealthy"):
            result["proof"] = "passed"
        else:
            result["error"] = "Environment proof returned without healthy disposable runtime evidence."
    elif operation_error is None and result["cleanupError"] is None and not cleanup_terminal:
        result["error"] = "Environment proof cleanup did not return terminal runtime cleanup evidence."

    result["finalMutationState"] = _final_mutation_state(result)
    try:
        result["receipt"] = write_environment_proof_receipt(result)
    except Exception as error:  # proof result stays truthful even if local evidence persistence fails
        result["receiptError"] = str(error)
    return result
