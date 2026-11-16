"""Small, fixed-field, secret-free diagnostic summaries for exact-target setup.

This is an additive v1 projection. Full reviewed plans and evidence stay in
their canonical storage. Never reflect arbitrary stderr, provider responses,
host exception text, paths, URLs or untrusted string fields into this summary.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

DIAGNOSTIC_SCHEMA = 1
CAPABILITY = "remote-environment-setup"
CAPABILITY_VERSION = 1
SUMMARY_MAX_BYTES = 8192

_PHASES = (
    "workspace",
    "targetDefinition",
    "targetAccess",
    "hostPlatform",
    "deploymentPath",
    "application",
)
_ALLOWED_CODES = frozenset({
    "missing-identity",
    "missing-trust",
    "local-security-or-trust-invalid",
    "name-resolution-failed",
    "transport-failed",
    "host-identity-rejected",
    "local-signing-failed",
    "local-signing-unproven",
    "remote-authentication-rejected",
    "remote-account-policy-rejected",  # legacy consumers; not inferred from key offer
    "authentication-rejected",
    "ssh-verification-failed",
    "unclassified-failure",
})
_ALLOWED_ACTIONS = frozenset({
    "remote-environment-ready",
    "configure-target-profile",
    "create-or-select-key",
    "verify-and-enroll-host-trust",
    "set-verified-address",
    "repair-target-profile",
    "inspect-remote-account-access-policy",
    "repair-local-key-signing",
    "use-existing-target-agent-session",
    "reverify-host-identity",
    "repair-target-address-or-network-path",
    "diagnose-target-access",
    "install-host-platform",
    "upgrade-host-platform",
    "inspect-host-platform",
    "plan-deployment-path-proof",
    "review-deployment-path-proof",
    "resolve-environment-isolation-collision",
})
_ACTION_KIND = frozenset({
    "complete",
    "read-only",
    "local-prerequisite",
    "local-repair",
    "operator-action-required",
    "human-verification",
    "missing-facts",
    "blocked",
    "write-gated",
    "proof-context-required",
})


def _safe_target(value: object) -> str:
    # A selected local *logical name* only; never include hostnames, IPs,
    # filesystem paths, URLs or provider identifiers by default.
    if (not isinstance(value, str) or "." in value or
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is None):
        return "unknown-target"
    return value


def _dimension_state(value: str) -> str:
    if value in {"ready", "proven"}:
        return "proved"
    if value in {"not-proven", "not-part-of-setup"}:
        return "notChecked"
    if value.startswith("blocked") or value == "needs-profile":
        return "blocked"
    return "failed"


def project_setup_summary(
    result: dict[str, Any], *, observed_at: datetime | None = None
) -> dict[str, Any]:
    """Return an allowlisted, byte-bounded projection of remote setup evidence.

    Unknown states or reasons must not be reported as success. No arbitrary
    nested data, messages or paths are copied from the untrusted input.
    """
    stamp = observed_at if observed_at is not None else datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Observed time must include a timezone.")
    phases = result.get("phases")
    if not isinstance(phases, dict):
        phases = {}
    dimensions: dict[str, list[str]] = {
        "proved": [], "failed": [], "blocked": [], "notChecked": []
    }
    for key in _PHASES:
        phase = phases.get(key)
        state = phase.get("state") if isinstance(phase, dict) else None
        category = _dimension_state(state) if isinstance(state, str) else "notChecked"
        dimensions[category].append(key)

    next_action = result.get("next")
    if not isinstance(next_action, dict):
        next_action = {}
    action = next_action.get("action")
    action = action if isinstance(action, str) and action in _ALLOWED_ACTIONS else "unclassified-failure"
    kind = next_action.get("kind")
    kind = kind if isinstance(kind, str) and kind in _ACTION_KIND else "blocked"
    # A malformed/mixed producer cannot turn failed or missing prerequisite
    # observations into a success-shaped summary. Application is intentionally
    # not part of foundational environment proof.
    if action == "remote-environment-ready" and any(
        key not in dimensions["proved"] for key in _PHASES[:-1]
    ):
        action = "unclassified-failure"
        kind = "blocked"
    elif action == "unclassified-failure":
        kind = "blocked"
    target_access = phases.get("targetAccess", {})
    detail = target_access.get("detail") if isinstance(target_access, dict) else None
    failure_code = detail.get("failureCategory") if isinstance(detail, dict) else None
    reason_code = failure_code if isinstance(failure_code, str) and failure_code in _ALLOWED_CODES else action
    phase = result.get("currentPhase")
    phase = phase if isinstance(phase, str) and phase in _PHASES else "unknown"
    # Caller-reported mutation cannot be silently represented as read-only.
    # This shape is not an authorization token or operation receipt.
    mutated = result.get("mutated")
    mutation = "none" if mutated is False else "unknown" if mutated is None else "occurred"

    summary = {
        "schemaVersion": DIAGNOSTIC_SCHEMA,
        "capability": CAPABILITY,
        "capabilityVersion": CAPABILITY_VERSION,
        "target": _safe_target(result.get("targetName")),
        "observedAt": stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "reasonCode": reason_code,
        "dimensions": dimensions,
        "mutation": mutation,
        "nextAction": {
            "code": action,
            "kind": kind,
            "consequence": (
                "write-approval-required" if kind == "write-gated"
                else "human-verification-required" if kind in {"human-verification", "operator-action-required"}
                else "no-mutation"
            ),
        },
        "evidenceRef": None,
    }
    serialized = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(serialized) > SUMMARY_MAX_BYTES:
        # Never truncate failed/blocked dimensions to meet the bound.
        raise ValueError("Diagnostic summary exceeded the fixed v1 bound.")
    return summary
