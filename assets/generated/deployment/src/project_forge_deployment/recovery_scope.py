"""Reusable recovery-scope declarations and non-secret readiness evidence."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .errors import DeploymentKitError

RECOVERY_SCHEMA_VERSION = 1
AUTHENTICATION_POLICIES = {"preserve-authentication", "invalidate-authentication"}
_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$")
_ALLOWED_TOP = {"schemaVersion", "authenticationPolicy", "dependencies"}
_ALLOWED_DEPENDENCY = {"id", "type", "required"}


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, dots, underscores, and internal hyphens.")
    return value


def normalize_recovery_scope(value: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a strict, non-secret recovery declaration.

    The declaration deliberately has no free-form values, paths, credentials, or
    provider configuration. It describes recovery dependencies without storing
    their contents or teaching generic persistence tooling how to archive them.
    """
    if value is None:
        return {
            "schemaVersion": RECOVERY_SCHEMA_VERSION,
            "declared": False,
            "authenticationPolicy": None,
            "dependencies": [],
            "manifestSha256": None,
        }
    if not isinstance(value, dict) or set(value) != _ALLOWED_TOP:
        raise DeploymentKitError(
            "Recovery manifest must contain exactly schemaVersion, authenticationPolicy, and dependencies."
        )
    if value["schemaVersion"] != RECOVERY_SCHEMA_VERSION:
        raise DeploymentKitError(f"Recovery manifest schemaVersion must be {RECOVERY_SCHEMA_VERSION}.")
    policy = value["authenticationPolicy"]
    if policy is not None and policy not in AUTHENTICATION_POLICIES:
        raise DeploymentKitError(
            "authenticationPolicy must be preserve-authentication, invalidate-authentication, or null."
        )
    dependencies = value["dependencies"]
    if not isinstance(dependencies, list):
        raise DeploymentKitError("Recovery manifest dependencies must be an array.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict) or set(dependency) != _ALLOWED_DEPENDENCY:
            raise DeploymentKitError("Each recovery dependency must contain exactly id, type, and required.")
        dependency_id = _identifier(dependency["id"], "Recovery dependency id")
        dependency_type = _identifier(dependency["type"], "Recovery dependency type")
        required = dependency["required"]
        if not isinstance(required, bool):
            raise DeploymentKitError("Recovery dependency required must be a boolean.")
        if dependency_id in seen:
            raise DeploymentKitError(f"Duplicate recovery dependency id: {dependency_id}")
        seen.add(dependency_id)
        normalized.append({"id": dependency_id, "type": dependency_type, "required": required})
    normalized.sort(key=lambda item: item["id"])
    canonical = {
        "schemaVersion": RECOVERY_SCHEMA_VERSION,
        "authenticationPolicy": policy,
        "dependencies": normalized,
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        **canonical,
        "declared": True,
        "manifestSha256": fingerprint,
    }


def public_recovery_scope(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": scope["schemaVersion"],
        "declared": scope["declared"],
        "authenticationPolicy": scope["authenticationPolicy"],
        "dependencies": [dict(item) for item in scope["dependencies"]],
        "manifestSha256": scope["manifestSha256"],
    }


def recovery_readiness(scope: dict[str, Any], *, database_backup_verified: bool) -> dict[str, Any]:
    unresolved = [item["id"] for item in scope["dependencies"] if item["required"]]
    return {
        "schemaVersion": RECOVERY_SCHEMA_VERSION,
        "databaseBackupVerified": bool(database_backup_verified),
        "verifiedBackupScope": "database" if database_backup_verified else None,
        "recoveryScopeDeclared": scope["declared"],
        "authenticationPolicy": scope["authenticationPolicy"],
        "authenticationPolicyVerified": False if scope["authenticationPolicy"] is not None else None,
        "unresolvedRequiredDependencies": unresolved,
        "manifestSha256": scope["manifestSha256"],
        "applicationRecoveryReady": False,
        "readinessReason": "restore-policy-not-verified" if scope["declared"] else "recovery-scope-not-declared",
    }


def recovery_evidence(scope: dict[str, Any], *, database_backup_verified: bool) -> dict[str, Any]:
    """Return the privacy-safe evidence payload persisted with a SQLite operation."""
    readiness = recovery_readiness(scope, database_backup_verified=database_backup_verified)
    return {
        **readiness,
        "dependencies": [dict(item) for item in scope["dependencies"]],
    }
