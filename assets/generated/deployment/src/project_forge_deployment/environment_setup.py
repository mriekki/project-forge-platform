"""Read-only orchestration for one remote Project Forge setup target.

This module intentionally composes existing deterministic primitives without applying
mutations. It gives conversational front ends one state machine to render instead of
reconstructing profile, SSH, host-platform, and proof readiness themselves.
"""

from __future__ import annotations

from typing import Any

from .box_platform import platform_doctor
from .doctor import target_doctor, workstation_doctor
from .environment_probe import plan_environment_proof
from .errors import DeploymentKitError
from .profiles import load_profile
from .proof_receipt import load_environment_proof_receipt
from .safe_diagnostics import project_setup_summary
from .ssh import diagnose_access


READINESS_ORDER = (
    "workspace",
    "targetDefinition",
    "targetAccess",
    "hostPlatform",
    "deploymentPath",
    "application",
)


def _phase(label: str, state: str, *, detail: Any = None) -> dict[str, Any]:
    value: dict[str, Any] = {"label": label, "state": state}
    if detail is not None:
        value["detail"] = detail
    return value


def _current_phase(phases: dict[str, dict[str, Any]]) -> str:
    return next(
        (key for key in READINESS_ORDER if phases[key]["state"] not in {"ready", "proven", "not-part-of-setup"}),
        "application",
    )


def remote_setup_status(name: str) -> dict[str, Any]:
    """Return one read-only, terminal status model for remote environment setup."""

    workstation = workstation_doctor()
    target = target_doctor(name)

    phases: dict[str, dict[str, Any]] = {
        "workspace": _phase(
            "WORKSPACE READY",
            "ready" if workstation["state"] in {"configured", "partially-configured"} else workstation["state"],
            detail=workstation,
        ),
        "targetDefinition": _phase(
            "TARGET DEFINITION READY",
            "ready" if target["state"] != "needs-profile" else "needs-profile",
            detail=target,
        ),
        "targetAccess": _phase("TARGET ACCESS READY", "blocked"),
        "hostPlatform": _phase("HOST PLATFORM READY", "blocked"),
        "deploymentPath": _phase("DEPLOYMENT PATH PROVEN", "not-proven"),
        "application": _phase("APPLICATION DEPLOYED", "not-part-of-setup"),
    }

    host_platform: dict[str, Any] | None = None

    if target["state"] == "ready-to-verify":
        target_access = diagnose_access(load_profile(name))
        phases["targetAccess"] = _phase(
            "TARGET ACCESS READY",
            "ready" if target_access["state"] == "verified" else "diagnosis-required",
            detail=target_access,
        )
    elif target["state"] == "needs-profile":
        phases["targetAccess"] = _phase("TARGET ACCESS READY", "blocked-by-target-definition")
    else:
        phases["targetAccess"] = _phase(
            "TARGET ACCESS READY",
            f"blocked-by-{target['state']}",
            detail={"nextAction": target.get("nextAction")},
        )

    if phases["targetAccess"]["state"] == "ready":
        try:
            host_platform = platform_doctor(name)
            phases["hostPlatform"] = _phase(
                "HOST PLATFORM READY",
                "ready" if host_platform["state"] == "ready" else host_platform["state"],
                detail=host_platform,
            )
        except DeploymentKitError as error:
            phases["hostPlatform"] = _phase(
                "HOST PLATFORM READY",
                "inspection-failed",
                detail={"reason": str(error)},
            )
    else:
        phases["hostPlatform"] = _phase("HOST PLATFORM READY", "blocked-by-target-access")

    return {
        "targetName": name,
        "state": "host-platform-ready" if phases["hostPlatform"]["state"] == "ready" else "needs-setup",
        "currentPhase": _current_phase(phases),
        "phases": phases,
        "mutated": False,
    }


def _access_recovery(status: dict[str, Any]) -> dict[str, Any]:
    detail = status["phases"]["targetAccess"].get("detail") or {}
    category = detail.get("failureCategory")
    target = status["targetName"]
    command = f"project-forge-deploy environment setup status {target} --json"

    if category in {"remote-authentication-rejected", "remote-account-policy-rejected"}:
        return {
            "kind": "operator-action-required",
            "action": "inspect-remote-account-access-policy",
            "command": command,
            "reason": detail.get("guidance"),
            "safety": (
                "Use a trusted target console or already-authorized administrative session. "
                "Do not reinstall keys repeatedly, enable password SSH, widen AllowUsers, or weaken host verification implicitly."
            ),
        }
    if category == "local-signing-unproven":
        return {
            "kind": "local-prerequisite",
            "action": "use-existing-target-agent-session",
            "command": (
                f"project-forge-deploy target agent-session {target} "
                f"-- environment setup status {target} --json"
            ),
            "reason": detail.get("guidance"),
            "safety": (
                "Prepare the configured local signer using the existing supported "
                "agent-session helper in a trusted interactive terminal. "
                "No remote SSH policy change, new key or trust alteration is authorized."
            ),
        }
    if category == "local-signing-failed":
        return {
            "kind": "local-repair",
            "action": "repair-local-key-signing",
            "command": command,
            "reason": detail.get("guidance"),
        }
    if category == "host-identity-rejected":
        return {
            "kind": "human-verification",
            "action": "reverify-host-identity",
            "command": f"project-forge-deploy target trust-candidates {target}",
            "reason": detail.get("guidance"),
        }
    if category in {"transport-failed", "name-resolution-failed"}:
        return {
            "kind": "missing-facts",
            "action": "repair-target-address-or-network-path",
            "command": command,
            "reason": detail.get("guidance") or detail.get("reason"),
        }
    if category == "missing-identity":
        return {
            "kind": "write-gated",
            "action": "create-or-select-key",
            "command": f"project-forge-deploy target key-create {target}",
            "authorization": "[LOCAL KEY WRITE]",
            "reason": detail.get("reason"),
        }
    if category == "missing-trust":
        return {
            "kind": "human-verification",
            "action": "verify-and-enroll-host-trust",
            "command": f"project-forge-deploy target trust-candidates {target}",
            "reason": detail.get("reason"),
        }
    return {
        "kind": "read-only",
        "action": "diagnose-target-access",
        "command": command,
        "reason": detail.get("guidance") or detail.get("reason"),
    }


def _next_action(status: dict[str, Any]) -> dict[str, Any]:
    phases = status["phases"]
    target = phases["targetDefinition"].get("detail") or {}

    if phases["targetDefinition"]["state"] == "needs-profile":
        return {
            "kind": "missing-facts",
            "action": "configure-target-profile",
            "command": f"project-forge-deploy target configure {status['targetName']} <target facts>",
            "reason": "A target profile does not exist yet; host/user/SSH facts must come from the developer or portable profile.",
        }

    target_state = target.get("state")
    if target_state == "needs-key":
        return {
            "kind": "write-gated",
            "action": "create-or-select-key",
            "command": f"project-forge-deploy target key-create {status['targetName']}",
            "authorization": "[LOCAL KEY WRITE]",
        }
    if target_state == "needs-trust":
        return {
            "kind": "human-verification",
            "action": "verify-and-enroll-host-trust",
            "command": f"project-forge-deploy target trust-candidates {status['targetName']}",
            "reason": "Host-key trust requires an independently observed target-console fingerprint before enrollment.",
        }
    if target_state == "needs-address":
        return {
            "kind": "missing-facts",
            "action": "set-verified-address",
            "command": f"project-forge-deploy target address-set {status['targetName']} --address <verified-address>",
            "reason": "Stable host identity exists but no usable address resolved; use only a separately verified current address.",
        }
    if target_state == "blocked":
        return {
            "kind": "blocked",
            "action": target.get("nextAction", "repair-target-profile"),
            "reason": target.get("reason", "Target definition is blocked."),
        }

    if phases["targetAccess"]["state"] != "ready":
        return _access_recovery(status)

    platform = phases["hostPlatform"].get("detail") or {}
    platform_state = phases["hostPlatform"]["state"]
    if platform_state == "installable":
        return {
            "kind": "write-gated",
            "action": "install-host-platform",
            "command": f"project-forge-deploy platform install {status['targetName']}",
            "authorization": "[HOST PLATFORM WRITE]",
        }
    if platform_state == "upgrade-required":
        return {
            "kind": "write-gated",
            "action": "upgrade-host-platform",
            "command": f"project-forge-deploy platform upgrade {status['targetName']}",
            "authorization": "[HOST PLATFORM WRITE]",
        }
    if platform_state in {"blocked-port-80", "drifted", "blocked", "incompatible", "inspection-failed"}:
        return {
            "kind": "blocked",
            "action": platform.get("nextAction", "inspect-host-platform"),
            "reason": platform.get("reason", f"Host platform state is {platform_state}."),
            "safety": "Inspect exact ownership/state first; do not broadly prune or take over unrelated host resources.",
        }
    if platform_state != "ready":
        return {
            "kind": "blocked",
            "action": "inspect-host-platform",
            "reason": f"Host platform state is {platform_state}.",
        }

    if phases["deploymentPath"]["state"] == "proven":
        return {
            "kind": "complete",
            "action": "remote-environment-ready",
            "reason": "Fresh workstation-local proof evidence matches this Project/environment/target context and current isolation remains clear.",
            "proofReceipt": phases["deploymentPath"].get("detail"),
        }

    return {
        "kind": "proof-context-required",
        "action": "plan-deployment-path-proof",
        "reason": "Target access and host platform are ready. Owner/repository and logical environment are needed to plan the disposable proof.",
    }


def _proof_command(name: str, proof: dict[str, Any], *, production: bool) -> str:
    command = (
        f"project-forge-deploy environment proof plan {name} "
        f"--owner-repo {proof['ownerRepo']} --environment {proof['environment']}"
    )
    if production:
        command += " --production"
    return command


def _blocked_isolation_action(
    name: str,
    proof: dict[str, Any],
    *,
    production: bool,
) -> dict[str, Any]:
    return {
        "kind": "blocked",
        "action": "resolve-environment-isolation-collision",
        "command": _proof_command(name, proof, production=production),
        "reason": (
            "The read-only colocated-environment preflight found a managed ownership or footprint collision. "
            "Do not redirect this environment to a sibling target identity or take over existing runtime, route, persistence, or lock state."
        ),
        "proofPlan": proof,
        "isolationPreflight": proof.get("isolationPreflight"),
        "safety": "Inspect the reported managed ownership records and resolve the collision explicitly before creating a fresh proof plan.",
    }


def remote_setup_plan(
    name: str,
    *,
    owner_repo: str | None = None,
    environment: str | None = None,
    production: bool = False,
) -> dict[str, Any]:
    """Return the exact next deterministic setup action without mutating state."""

    if (owner_repo is None) != (environment is None):
        raise DeploymentKitError("ownerRepo and environment must be supplied together for setup proof planning.")

    status = remote_setup_status(name)
    proof: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    if (
        owner_repo is not None
        and environment is not None
        and status["phases"]["hostPlatform"]["state"] == "ready"
    ):
        # Current machine isolation must be checked even when a prior proof receipt is
        # otherwise reusable. A sibling environment can be added after the receipt was
        # recorded without changing workstation/target identity or trust evidence.
        proof = plan_environment_proof(
            name,
            owner_repo=owner_repo,
            environment=environment,
            production=production,
        )
        receipt = load_environment_proof_receipt(
            name,
            owner_repo=owner_repo,
            environment=environment,
            production=production,
        )
        isolation_clear = proof.get("runnable", True)
        if isolation_clear:
            status["phases"]["deploymentPath"] = _phase(
                "DEPLOYMENT PATH PROVEN",
                "proven" if receipt["state"] == "proven" else "not-proven",
                detail=receipt,
            )
            if receipt["state"] == "proven":
                status["state"] = "environment-ready"
        else:
            status["phases"]["deploymentPath"] = _phase(
                "DEPLOYMENT PATH PROVEN",
                "blocked",
                detail={
                    "proofReceipt": receipt,
                    "isolationPreflight": proof.get("isolationPreflight"),
                },
            )
            status["state"] = "needs-setup"
        status["currentPhase"] = _current_phase(status["phases"])

    next_action = _next_action(status)

    if proof is not None and not proof.get("runnable", True):
        next_action = _blocked_isolation_action(name, proof, production=production)
    elif (
        next_action["action"] == "plan-deployment-path-proof"
        and proof is not None
    ):
        next_action = {
            "kind": "read-only",
            "action": "review-deployment-path-proof",
            "command": _proof_command(name, proof, production=production),
            "proofPlan": proof,
            "runAuthorization": proof["requiredAuthorization"],
            "previousProof": receipt,
        }

    result = {
        **status,
        "next": next_action,
        "mutated": False,
    }
    # Additive safe, bounded, versioned projection. Retain the full evidence
    # in its existing owner; never echo arbitrary remote stderr to summaries.
    result["diagnosticSummary"] = project_setup_summary(result)
    return result
