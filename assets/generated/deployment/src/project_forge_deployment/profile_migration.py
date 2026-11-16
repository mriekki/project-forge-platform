"""One-time migration of an existing workstation into the personal Project Forge profile model."""

from __future__ import annotations

from typing import Any

from .errors import DeploymentKitError
from .portable_profile import list_target_names
from .profile_repository import ensure_profile_repository, publish_profile, sync_profile
from .profiles import load_profile
from .ssh import verify_access


PERSONAL_PROFILE_MIGRATION_PHRASE = "[PERSONAL PROFILE MIGRATION]"


def migrate_current_workstation() -> dict[str, Any]:
    """Adopt existing portable target definitions without replacing machine identity/trust.

    Remote verification is evidence only: an offline/unreachable target does not roll back
    a successfully migrated personal profile/cache. Cleanup of legacy server credentials is
    intentionally outside this operation and requires a proven new deployment path first.
    """

    local_targets = list_target_names()
    ensured = ensure_profile_repository()
    published = publish_profile()
    synced = sync_profile(apply=True)
    if synced.get("blocked"):
        raise DeploymentKitError(str(synced["blocked"]))

    checks: list[dict[str, Any]] = []
    for name in local_targets:
        try:
            evidence = verify_access(load_profile(name))
            checks.append(
                {
                    "targetName": name,
                    "state": "ready",
                    "strictVerification": evidence,
                }
            )
        except DeploymentKitError as error:
            checks.append(
                {
                    "targetName": name,
                    "state": "not-verified",
                    "detail": str(error),
                }
            )

    return {
        "profileRepository": ensured["repository"],
        "localTargets": local_targets,
        "profileEnsure": ensured,
        "profilePublish": published,
        "profileSync": synced,
        "targetVerification": checks,
        "machineKeysAndTrust": "preserved",
        "legacyServerRegistryCredentials": "unchanged-until-new-deployment-path-is-proven",
        "mutated": bool(
            ensured.get("mutated")
            or published.get("mutated")
            or synced.get("mutated")
        ),
        "next": (
            "Use the normal workstation-mediated Staging deployment path when ready; "
            "remove legacy server-side registry credentials only after proving they are unused."
        ),
    }
