"""Manually reviewed disposable Auth retention operations; no scheduler/Production wiring.

A plan is private and non-secret, bound to the exact generated-Project helper,
Docker owner binding, most recently verified backup and inventory. Applying
requires the human-reviewed SHA-256 of that private plan, plus explicit
disposable deletion authorization. This is not host or inbox acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

from .auth_recovery_capture import _load_pinned_helper
from .auth_recovery_lifecycle import _binding_fingerprint
from .auth_recovery_schedule import (
    _operation_lock, _read_json, _write_private_json,
    inspect_disposable_backup_status, load_disposable_operation_config,
)
from .errors import DeploymentKitError

_PLAN = "auth-retention-reviewed-plan.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _verified_backup(config: dict) -> dict:
    report = inspect_disposable_backup_status(config)
    attempt = report["lastAttempt"]
    latest = report["lastSuccess"]
    if (report["state"] != "fresh" or type(attempt) is not dict or
            type(latest) is not dict or attempt["outcome"] != "success" or
            attempt["backupArtifactIntegrityVerified"] is not True or
            attempt["runtimeResumedVerified"] is not True or
            attempt["setName"] != latest["setName"] or
            attempt["completedAt"] != latest["completedAt"]):
        raise DeploymentKitError(
            "A current verified disposable Auth backup and exact Docker resumption are required."
        )
    return latest


def _verified_helper(config: dict):
    helper = _load_pinned_helper(
        config["project"], config["revision"], config["helperSha"])
    if (not callable(getattr(helper, "plan_verified_retention", None)) or
            not callable(getattr(helper, "apply_reviewed_disposable_retention", None))):
        raise DeploymentKitError(
            "Reviewed generated Auth helper does not support disposable retention."
        )
    try:
        helper.validate_declaration(config["declaration"])
    except Exception:
        raise DeploymentKitError("Reviewed Auth recovery declaration is invalid.") from None
    return helper


def _binding_record(config: dict, last: dict, keep_last: int) -> dict:
    return {
        "schemaVersion": 1,
        "environment": "disposable",
        "projectId": config["declaration"]["projectId"],
        "authRevision": config["revision"],
        "recoverySha256": config["helperSha"],
        "dockerBindingSha256": _binding_fingerprint(config["binding"]),
        "backupsRoot": str(config["backups"]),
        "latestSuccessfulSetName": last["setName"],
        "latestSuccessfulAt": last["completedAt"],
        "keepLast": keep_last,
    }


def create_reviewed_disposable_retention_plan(
    config: dict, *, keep_last: int = 7,
) -> dict:
    """Write only a private review artifact, no backup deletion."""
    if type(keep_last) is not int or not 2 <= keep_last <= 365:
        raise DeploymentKitError("Auth retention must preserve at least two recovery sets.")
    with _operation_lock(config["status"]):
        last = _verified_backup(config)
        helper = _verified_helper(config)
        try:
            preview = helper.plan_verified_retention(
                config["backups"], config["declaration"], keep_last=keep_last)
        except Exception:
            raise DeploymentKitError("Auth retention inventory could not be verified.") from None
        if (type(preview) is not dict or preview.get("retentionPlanOnly") is not True or
                preview.get("deletionPerformed") is not False or
                last["setName"] not in preview.get("retainedRecoverySetNames", [])):
            raise DeploymentKitError("Current verified backup must remain in the retained inventory.")
        envelope = {**_binding_record(config, last, keep_last), "reviewedPlan": preview}
        digest = hashlib.sha256(_canonical_json(envelope)).hexdigest()
        _write_private_json(config["status"] / _PLAN, envelope, replace=True)
        return {
            "planSha256": digest,
            "candidateCount": len(preview["retentionCandidateNames"]),
            "deletionPerformed": False,
            "reviewRequiredBeforeApply": True,
        }


def apply_reviewed_disposable_retention(
    config: dict, *, expected_plan_sha256: str,
    authorize_disposable_delete: bool = False,
) -> dict:
    """Apply only an exact operator-reviewed private plan, never automatically."""
    if (authorize_disposable_delete is not True or
            type(expected_plan_sha256) is not str or
            _SHA256.fullmatch(expected_plan_sha256) is None):
        raise DeploymentKitError("Explicit disposable retention approval and reviewed SHA-256 required.")
    with _operation_lock(config["status"]):
        last = _verified_backup(config)
        helper = _verified_helper(config)
        envelope = _read_json(config["status"] / _PLAN)
        if hashlib.sha256(_canonical_json(envelope)).hexdigest() != expected_plan_sha256:
            raise DeploymentKitError("Disposable retention reviewed-plan hash differs.")
        if (set(envelope) != set(_binding_record(config, last, 7)) | {"reviewedPlan"} or
                type(envelope.get("keepLast")) is not int or
                not 2 <= envelope["keepLast"] <= 365):
            raise DeploymentKitError("Disposable retention plan schema is invalid.")
        if (envelope != {**_binding_record(config, last, envelope["keepLast"]),
                        "reviewedPlan": envelope["reviewedPlan"]}):
            raise DeploymentKitError("Reviewed retention plan does not match generated Project.")
        preview = envelope["reviewedPlan"]
        try:
            current = helper.plan_verified_retention(
                config["backups"], config["declaration"], keep_last=envelope["keepLast"])
        except Exception:
            raise DeploymentKitError("Current retention inventory could not be verified.") from None
        if (current != preview or
                last["setName"] not in current["retainedRecoverySetNames"]):
            raise DeploymentKitError("Retention inventory changed after operator review.")

        # An immutable start receipt survives interruption, and the immutable
        # finish receipt records the actual outcome. No partial failure can be
        # reported as completion or silently retried.
        operation_id = secrets.token_hex(16)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        base = {
            "schemaVersion": 1, "operationId": operation_id,
            "startedAt": stamp, "reviewedPlanSha256": expected_plan_sha256,
            "projectId": config["declaration"]["projectId"],
            "plannedCandidateNames": current["retentionCandidateNames"][:32],
        }
        prefix = config["status"] / ("auth-retention-" + operation_id)
        _write_private_json(Path(str(prefix) + "-started.json"), base, replace=False)
        try:
            result = helper.apply_reviewed_disposable_retention(
                config["backups"], config["lock"], config["declaration"], preview,
                keep_last=envelope["keepLast"], environment="disposable",
                authorize_disposable_delete=True, max_delete=32)
            if (type(result) is not dict or
                    result.get("deletedRecoverySetNames") != base["plannedCandidateNames"] or
                    result.get("deletionPerformed") is not bool(base["plannedCandidateNames"])):
                raise DeploymentKitError("Disposable retention deletion proof differs.")
        except Exception:
            _write_private_json(
                Path(str(prefix) + "-failed.json"),
                {**base, "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                 "outcome": "failed-or-unverified"}, replace=False)
            raise DeploymentKitError(
                "Disposable retention incomplete; inspect private receipts and inventory."
            ) from None

        _write_private_json(
            Path(str(prefix) + "-completed.json"),
            {**base, "completedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
             "outcome": "success", "deletedRecoverySetNames": result["deletedRecoverySetNames"]},
            replace=False)
        return {
            "deletedRecoverySetNames": result["deletedRecoverySetNames"],
            "deletionPerformed": result["deletionPerformed"] is True,
            "applicationRecoveryReady": False,
            "scheduledBackupVerified": False,
            "alertInboxReceiptVerified": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual disposable-only Auth retention; never a Production or timer command")
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--keep-last", type=int, default=7)
    parser.add_argument("--reviewed-plan-sha256")
    parser.add_argument("--authorize-disposable-delete", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_disposable_operation_config(args.config)
        if args.action == "plan":
            if args.reviewed_plan_sha256 or args.authorize_disposable_delete:
                raise DeploymentKitError("Read-only retention planning refuses deletion approval flags.")
            result = create_reviewed_disposable_retention_plan(
                config, keep_last=args.keep_last)
            print("Disposable Auth retention candidate count: " + str(result["candidateCount"]))
            print("Review private plan before apply; SHA-256: " + result["planSha256"])
        else:
            if args.keep_last != 7:
                raise DeploymentKitError("Retention apply uses the keep-last value pinned in reviewed plan.")
            result = apply_reviewed_disposable_retention(
                config, expected_plan_sha256=args.reviewed_plan_sha256,
                authorize_disposable_delete=args.authorize_disposable_delete)
            print("Disposable Auth verified retention deleted sets: " +
                  str(len(result["deletedRecoverySetNames"])))
        return 0
    except DeploymentKitError:
        print("BLOCKED: Disposable Auth retention could not be proven safe.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
