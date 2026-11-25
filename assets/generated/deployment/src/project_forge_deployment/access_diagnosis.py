"""Read-only strict target-access diagnosis with optional temporary address evidence."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
from typing import Any

from .errors import DeploymentKitError
from .profiles import load_profile
from .ssh import diagnose_access


def _temporary_address(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as error:
        raise DeploymentKitError("Temporary target address must be an exact IPv4 or IPv6 address.") from error
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
        raise DeploymentKitError("Temporary target address must not include an IPv6 scope identifier.")
    return str(parsed)


def _route_interface(address: str) -> str | None:
    if sys.platform == "darwin":
        route = shutil.which("route") or ("/sbin/route" if os.path.exists("/sbin/route") else None)
        if route:
            result = subprocess.run(
                [route, "-n", "get", address],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                match = re.search(r"^\s*interface:\s*(\S+)\s*$", result.stdout, re.MULTILINE)
                if match:
                    return match.group(1)
    elif os.name != "nt":
        ip = shutil.which("ip")
        if ip:
            result = subprocess.run(
                [ip, "route", "get", address],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                match = re.search(r"\bdev\s+(\S+)", result.stdout)
                if match:
                    return match.group(1)
    return None


def route_source_evidence(address: str, port: int) -> dict[str, Any]:
    """Return the local route-selected source for one exact target address without scanning."""
    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if isinstance(parsed, ipaddress.IPv6Address) else socket.AF_INET
    evidence: dict[str, Any] = {
        "targetAddress": str(parsed),
        "targetPort": int(port),
        "sourceAddress": None,
        "interface": _route_interface(str(parsed)),
    }
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as probe:
            probe.connect((str(parsed), int(port)))
            evidence["sourceAddress"] = probe.getsockname()[0]
    except OSError as error:
        evidence["sourceProbeError"] = str(error)
    return evidence


def diagnose_target_access(name: str, *, temporary_address: str | None = None) -> dict[str, Any]:
    """Diagnose strict SSH access without persisting a temporary address override."""
    profile = load_profile(name)
    address = _temporary_address(temporary_address)
    effective = dict(profile)
    if address is not None:
        effective["addressOverride"] = address

    diagnosis = diagnose_access(effective)
    used_address = diagnosis.get("address")
    if used_address is None and address is not None:
        used_address = address

    result: dict[str, Any] = {
        **diagnosis,
        "addressInput": (
            {
                "source": "temporary-operator-confirmed",
                "address": address,
                "persisted": False,
            }
            if address is not None
            else {
                "source": "profile",
                "address": profile.get("addressOverride"),
                "persisted": profile.get("addressOverride") is not None,
            }
        ),
        "mutated": False,
    }
    if used_address is not None:
        result["routeSource"] = route_source_evidence(used_address, int(profile["port"]))
    return result


# A separate, shareable view: never forward the raw diagnostic fields,
# addresses, identity fingerprints, stderr, profile paths or host logs.
_GUIDED_FAILURES = {
    "missing-identity": ("local-identity", "Check the existing target-specific identity in the configured workstation. Do not generate or replace keys automatically."),
    "missing-trust": ("host-trust", "Check the existing target trust file; independently verify host identity before any separate trust enrollment."),
    "local-security-or-trust-invalid": ("local-security-or-trust", "Check existing key and trust-file permissions and target identity. Do not weaken validation."),
    "name-resolution-failed": ("network", "Confirm the configured hostname or an independently observed exact target address; do not scan."),
    "transport-failed": ("network", "Check the selected target, port and network path. Do not change authentication policy to fix connectivity."),
    "host-identity-rejected": ("host-trust", "Stop and independently verify the target host fingerprint. Do not bypass strict host verification."),
    "local-signing-failed": ("local-signer", "Use the configured dedicated SSH agent in the supported local editor/terminal context. Never provide a passphrase in chat."),
    "local-signing-unproven": ("local-signer", "Verify the configured local signer and repeat the existing strict key-only diagnosis; a loaded agent or key offer alone does not establish completed signing."),
    "remote-authentication-rejected": ("remote-authentication", "Authentication was rejected. Inspect the server-side evidence using an independently authorized administrative session or local console."),
    "remote-account-policy-rejected": ("remote-authentication", "Client evidence does not establish a server policy denial. Inspect the server-side evidence through an independent authorized channel."),
    "authentication-rejected": ("remote-authentication", "Inspect the server authentication and account policy from an independently authorized channel; do not assume a particular cause."),
    "ssh-verification-failed": ("unresolved", "Review the private diagnostic evidence locally and repeat only the existing authorized access check."),
}
_CONSOLE_HANDOFF = {
    "requiredAuthority": "independently-authorized-server-admin-session-or-local-console",
    "automaticExecution": False,
    "instructions": [
        "Use an existing authorized Ubuntu administrator session or the physical console. A locked-out workstation cannot establish this authority itself.",
        "Correlate the failed attempt's time, account and server-observed source address in the SSH service journal. Keep raw logs private.",
        "An explicit matching server log stating the account was not allowed because it is not listed in AllowUsers is evidence of that denial; an unrelated, stale or ambiguous log is not.",
        "Check the actual service configuration and applicable Include/Match rules. Validate configuration syntax and review effective policy for that exact connection using the server-observed account, client address, client hostname and local address/port.",
        "Compare the server-observed source with previously approved entries; a workstation route-selected address may differ due to NAT or WSL networking. A change in source address does not by itself establish why access failed.",
        "Keep the independent administrative channel open. Stop before changing configuration, credentials, trust, or reloading SSH; obtain a separate reviewed recovery decision.",
    ],
    "ubuntuJournalCommand": "sudo journalctl -u ssh.service -u sshd.service --since '10 minutes ago' --no-pager -n 100",
    "syntaxCheckCommand": "sudo /usr/sbin/sshd -t",
    "effectivePolicyCommandTemplate": "sudo /usr/sbin/sshd -T -C 'user=ACCOUNT,addr=CLIENT_IP,host=CLIENT_HOST,laddr=SERVER_IP,lport=SERVER_PORT'",
    "commandNote": "Examples for an Ubuntu server using the standard sshd configuration. Confirm actual service/configuration and replace every uppercase placeholder locally; do not run the template literally or send raw output to chat. These commands are for read-only inspection, not an automated recovery.",
}


def guided_access_report(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """Return fixed, sanitized guidance, not an authenticated server report."""
    if not isinstance(diagnosis, dict) or diagnosis.get("mutated") is not False:
        raise DeploymentKitError("Invalid read-only access diagnostic.")
    state = diagnosis.get("state")
    if state not in ("verified", "failed"):
        raise DeploymentKitError("Invalid access diagnostic state.")
    category = diagnosis.get("failureCategory")
    if state == "verified":
        stage, action = ("strict-session", "Strict SSH access succeeded. No recovery or policy change is indicated by this check.")
    elif isinstance(category, str) and category in _GUIDED_FAILURES:
        stage, action = _GUIDED_FAILURES[category]
    else:
        stage, action = _GUIDED_FAILURES["ssh-verification-failed"]
    route = diagnosis.get("routeSource")
    route_observed = isinstance(route, dict) and isinstance(route.get("sourceAddress"), str) and bool(route["sourceAddress"])
    result = {
        "schemaVersion": 1,
        "kind": "guided-ssh-access-diagnosis",
        "state": state,
        "stage": stage,
        "evidenceAuthority": "local-client-diagnostic",
        "serverPolicyEvidence": "not-collected",
        "allowUsersDenial": "not-established",
        "serverObservedSourceAddress": "not-collected",
        "localRouteSource": "observed-not-server-source" if route_observed else "not-observed",
        "nextStep": action,
        "mutated": False,
        "authorizesMutation": False,
    }
    if stage == "remote-authentication":
        # Copy mutable values; callers cannot modify future reports.
        result["consoleHandoff"] = {
            **_CONSOLE_HANDOFF, "instructions": list(_CONSOLE_HANDOFF["instructions"])
        }
    return result
