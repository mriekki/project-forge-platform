"""Durable workstation-local receipts for disposable environment proofs.

Receipts are diagnostic/readiness evidence, not deployment authorization or a workflow
database. They contain no credentials or mutable application data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .errors import DeploymentKitError
from .keys import key_fingerprint
from .profiles import load_profile


SCHEMA_VERSION = 1
PROOF_CONTRACT_VERSION = 1
_ENV_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _root() -> Path:
    configured = os.environ.get("PROJECT_FORGE_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".project-forge"


def _receipt_path(owner_repo: str, environment: str) -> Path:
    if _REPO_RE.fullmatch(owner_repo) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    if _ENV_RE.fullmatch(environment) is None:
        raise DeploymentKitError("environment must use lowercase letters, digits, and internal hyphens.")
    owner, repo = owner_repo.split("/", 1)
    return _root() / "evidence" / "environment-proofs" / owner / repo / f"{environment}.json"


def _sha256_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise DeploymentKitError(f"Cannot read target trust evidence {path}: {error}") from error
    return hashlib.sha256(data).hexdigest()


def current_target_signature(target_name: str) -> dict[str, Any]:
    """Return non-secret workstation/target identity used to invalidate stale proof."""

    profile = load_profile(target_name)
    identity = Path(profile["identityFile"])
    known_hosts = Path(profile["knownHostsFile"])
    signature = {
        "targetName": profile["targetName"],
        "targetOs": profile["targetOs"],
        "hostName": profile["hostName"],
        "sshAlias": profile["sshAlias"],
        "user": profile["user"],
        "port": profile["port"],
        "addressOverride": profile["addressOverride"],
        "identityFingerprint": key_fingerprint(identity),
        "trustSha256": _sha256_file(known_hosts),
    }
    canonical = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**signature, "signatureSha256": hashlib.sha256(canonical).hexdigest()}


def write_environment_proof_receipt(result: dict[str, Any]) -> dict[str, Any]:
    required = {
        "ownerRepo",
        "environment",
        "targetName",
        "production",
        "proof",
        "cleanupState",
        "finalMutationState",
    }
    missing = sorted(required.difference(result))
    if missing:
        raise DeploymentKitError("Environment proof result is missing receipt fields: " + ", ".join(missing))

    path = _receipt_path(result["ownerRepo"], result["environment"])
    target = current_target_signature(result["targetName"])
    receipt = {
        "schemaVersion": SCHEMA_VERSION,
        "proofContractVersion": PROOF_CONTRACT_VERSION,
        "deploymentKitVersion": __version__,
        "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ownerRepo": result["ownerRepo"],
        "environment": result["environment"],
        "targetName": result["targetName"],
        "production": bool(result["production"]),
        "proof": result["proof"],
        "cleanupState": result["cleanupState"],
        "finalMutationState": result["finalMutationState"],
        "registryDigest": result.get("registryDigest"),
        "localImageId": result.get("localImageId"),
        "remoteImageId": result.get("remoteImageId"),
        "targetSignature": target,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)
    return {"path": str(path), "recordedAt": receipt["recordedAt"], "state": "recorded"}


def load_environment_proof_receipt(
    target_name: str,
    *,
    owner_repo: str,
    environment: str,
    production: bool,
) -> dict[str, Any]:
    """Return whether a prior proof receipt is still applicable on this workstation."""

    path = _receipt_path(owner_repo, environment)
    if not path.is_file():
        return {"state": "missing", "path": str(path), "mutated": False}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "state": "invalid",
            "path": str(path),
            "reason": f"Cannot read proof receipt: {error}",
            "mutated": False,
        }

    expected = {
        "schemaVersion": SCHEMA_VERSION,
        "proofContractVersion": PROOF_CONTRACT_VERSION,
        "deploymentKitVersion": __version__,
        "ownerRepo": owner_repo,
        "environment": environment,
        "targetName": target_name,
        "production": bool(production),
    }
    mismatches = [key for key, value in expected.items() if receipt.get(key) != value]
    if mismatches:
        return {
            "state": "stale",
            "path": str(path),
            "reason": "Receipt context changed: " + ", ".join(mismatches),
            "mutated": False,
        }

    if receipt.get("proof") != "passed" or receipt.get("cleanupState") not in {"removed", "absent"}:
        return {
            "state": "not-proven",
            "path": str(path),
            "reason": "Latest receipt is not a clean passing proof.",
            "mutated": False,
        }

    try:
        current = current_target_signature(target_name)
    except DeploymentKitError as error:
        return {"state": "stale", "path": str(path), "reason": str(error), "mutated": False}
    previous = receipt.get("targetSignature") or {}
    if previous.get("signatureSha256") != current.get("signatureSha256"):
        return {
            "state": "stale",
            "path": str(path),
            "reason": "Target/workstation identity or trust changed after the recorded proof.",
            "mutated": False,
        }

    return {
        "state": "proven",
        "path": str(path),
        "recordedAt": receipt.get("recordedAt"),
        "targetName": target_name,
        "ownerRepo": owner_repo,
        "environment": environment,
        "production": bool(production),
        "finalMutationState": receipt.get("finalMutationState"),
        "mutated": False,
    }
