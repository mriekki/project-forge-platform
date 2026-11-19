"""Bounded post-apply signed release orchestration for an authorized Kit host.

This callable performs NO deployment or persistence and is deliberately not
exposed as an app endpoint, GitHub Action, or generic CLI command. Its real
Production caller must already have independently authorized and completed
the Deployment Kit apply, verified the private release source, and have
exclusive access to the host's protected signing key. Ordinary CI exercises
synthetic observers only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any

from . import app_runtime
from .release_attestation import ReleaseAttestationError
from .release_attestation_signer import sign_postapply_release

_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?\Z")
_EXPECTED_KEYS = (
    "ownerRepo", "appSlug", "environment", "sourceCommit", "registryImage",
    "runtimeImageId", "specSha256", "releaseVersion", "manifestSha256",
    "deploymentGeneration", "postApplyOperationId",
)


def sign_after_verified_deploy(
    *,
    exact_authorized_plan: dict[str, Any],
    successful_apply_result: dict[str, Any],
    approved_source_commit: str,
    approved_release_version: str,
    approved_manifest_bytes: bytes,
    privileged_signer_key_path: Path,
    pinned_signer_key_id: str,
    verified_at_utc: datetime,
) -> bytes:
    """Double-check live immutable image and approved bytes before signing.

    A test can inject an app_runtime observer, but that does not manufacture
    production authority. Real invocation must be inside the authorized
    Deployment Kit post-apply stage and use app_runtime's verified SSH path.
    """
    plan = exact_authorized_plan
    if (
        type(plan) is not dict or plan.get("action") != "deploy"
        or plan.get("environment") != "production"
        or type(plan.get("spec")) is not dict
    ):
        raise ReleaseAttestationError("only an authorized Production deploy can request evidence")
    spec = plan["spec"]
    if (
        plan.get("ownerRepo") != spec.get("ownerRepo")
        or plan.get("appSlug") != spec.get("appSlug")
        or plan.get("environment") != spec.get("environment")
        or plan.get("image") != spec.get("image")
        or type(spec.get("specSha256")) is not str
        or type(plan.get("targetName")) is not str
        or not plan["targetName"]
        or type(approved_source_commit) is not str
        or not _SHA1.fullmatch(approved_source_commit)
        or type(approved_release_version) is not str
        or not _VERSION.fullmatch(approved_release_version)
        or type(approved_manifest_bytes) is not bytes
        or not 1 <= len(approved_manifest_bytes) <= 131072
    ):
        raise ReleaseAttestationError("incomplete reviewed exact image/build/manifest release selection")
    if type(successful_apply_result) is not dict or successful_apply_result.get("mutated") is not True:
        raise ReleaseAttestationError("no successful managed application apply")
    items = successful_apply_result.get("applications")
    if type(items) is not list:
        raise ReleaseAttestationError("no final verified host application inventory")
    matches = [
        item for item in items if type(item) is dict
        and item.get("ownerRepo") == spec["ownerRepo"]
        and item.get("appSlug") == spec["appSlug"]
        and item.get("environment") == "production"
    ]
    if len(matches) != 1:
        raise ReleaseAttestationError("no unique verified final runtime")
    deployed = matches[0]
    if (
        deployed.get("specSha256") != spec["specSha256"]
        or deployed.get("image") != spec["image"]
        or any(deployed.get(field) is not True for field in (
            "containerPresent", "imageMatchesRelease", "containerRunning",
            "connectedToSharedNetwork", "httpHealthy",
        ))
        or deployed.get("materialMountsVerified", True) is not True
    ):
        raise ReleaseAttestationError("final managed runtime is not verified healthy")
    clock = verified_at_utc
    now = datetime.now(timezone.utc)
    if (
        not isinstance(clock, datetime) or clock.tzinfo is None
        or clock.utcoffset() is None or clock.utcoffset().total_seconds() != 0
        or (now - clock).total_seconds() < 0
        or (now - clock).total_seconds() > 120
    ):
        raise ReleaseAttestationError("post-apply verification time is not fresh UTC")

    digest = hashlib.sha256(approved_manifest_bytes).hexdigest()
    target = plan["targetName"]
    first = app_runtime.observe_verified_app_release(target, spec)
    if (
        first["sourceCommit"] != approved_source_commit
        or first["releaseVersion"] != approved_release_version
        or first["manifestSha256"] != digest
        or first["registryImage"] != spec["image"]
        or first["ownerRepo"] != spec["ownerRepo"]
        or first["appSlug"] != spec["appSlug"]
        or first["environment"] != "production"
        or first["specSha256"] != spec["specSha256"]
    ):
        raise ReleaseAttestationError("actual live source/manifest differs from the approved build")
    # The signer itself re-reads via SSH: same generation, container-image ID
    # and operation proof are required during this second observation.
    expected = {key: first[key] for key in _EXPECTED_KEYS}
    return sign_postapply_release(
        observe_privileged_host=lambda: app_runtime.observe_verified_app_release(target, spec),
        authorized_expected=expected,
        signer_key_path=privileged_signer_key_path,
        pinned_key_id=pinned_signer_key_id,
        verified_at_utc=clock,
    )
