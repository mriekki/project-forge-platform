"""Console-verified target host-trust enrollment and rotation."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .security import (
    HOST_KEY_TYPES,
    check_identity_security,
    check_known_hosts_security,
    known_hosts_token,
    prepare_ssh_directory,
    validate_target_trust_file,
)


FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
KEYSCAN_TYPES = "ed25519,ecdsa,rsa"


def required_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DeploymentKitError(f"Required OpenSSH tool is unavailable: {name}")
    return path


def _validate_console_address(address: str) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise DeploymentKitError(
            "Console-provided trust address must be an exact IPv4 or IPv6 address, never a hostname."
        ) from error
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
        raise DeploymentKitError("Console-provided trust address must not include an IPv6 scope identifier.")
    return str(parsed)


def _scan_addresses(profile: dict[str, Any], console_address: str | None) -> list[str]:
    if console_address is not None:
        return [_validate_console_address(console_address)]
    if profile["addressOverride"]:
        return [profile["addressOverride"]]
    try:
        answers = socket.getaddrinfo(
            profile["hostName"],
            profile["port"],
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise DeploymentKitError(
            f"Cannot resolve target hostname {profile['hostName']} for trust candidate discovery: {error}. "
            "Obtain the exact current IP from the trusted target console and supply --address; do not scan the network."
        ) from error
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses:
        raise DeploymentKitError(
            "Target hostname returned no addresses. Supply only an exact address independently observed at the trusted console."
        )
    return addresses


def _fingerprint_public_key(key_type: str, key_data: str) -> str:
    result = subprocess.run(
        [required_tool("ssh-keygen"), "-lf", "-"],
        input=f"{key_type} {key_data}\n",
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DeploymentKitError("ssh-keygen could not fingerprint a scanned host-key candidate.")
    fingerprint = next(
        (token for token in result.stdout.split() if FINGERPRINT_RE.fullmatch(token)),
        None,
    )
    if fingerprint is None:
        raise DeploymentKitError("ssh-keygen returned no valid SHA256 fingerprint for a scanned host key.")
    return fingerprint


def scan_host_keys(
    profile: dict[str, Any],
    *,
    console_address: str | None = None,
) -> list[dict[str, str]]:
    candidates: dict[tuple[str, str], dict[str, str]] = {}
    failures: list[str] = []
    for address in _scan_addresses(profile, console_address):
        result = subprocess.run(
            [
                required_tool("ssh-keyscan"),
                "-T",
                "5",
                "-p",
                str(profile["port"]),
                "-t",
                KEYSCAN_TYPES,
                address,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        found = False
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 3:
                raise DeploymentKitError("ssh-keyscan returned a malformed host-key candidate.")
            key_type, key_data = fields[1], fields[2]
            if key_type not in HOST_KEY_TYPES:
                continue
            found = True
            fingerprint = _fingerprint_public_key(key_type, key_data)
            candidates[(key_type, key_data)] = {
                "address": address,
                "keyType": key_type,
                "keyData": key_data,
                "fingerprint": fingerprint,
            }
        if not found:
            failures.append(f"{address}: exit {result.returncode}")
    if not candidates:
        raise DeploymentKitError(
            "No supported host-key candidates were returned for the selected target address(es): "
            + "; ".join(failures)
        )
    return sorted(candidates.values(), key=lambda item: (item["fingerprint"], item["keyType"], item["address"]))


def candidate_view(candidate: dict[str, str]) -> dict[str, str]:
    return {
        "address": candidate["address"],
        "keyType": candidate["keyType"],
        "fingerprint": candidate["fingerprint"],
        "trustState": "candidate-only-not-trusted",
    }


def _write_exact_trust(profile: dict[str, Any], key_type: str, key_data: str) -> None:
    path = Path(profile["knownHostsFile"])
    prepare_ssh_directory(path.parent)
    if path.exists() and path.is_symlink():
        raise DeploymentKitError(f"Refusing to replace symbolic-link trust file: {path}")

    token = known_hosts_token(profile)
    line = f"{token} {key_type} {key_data}\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(line)
        if os.name != "nt":
            temp.chmod(0o600)
        check_known_hosts_security(temp)
        temp.replace(path)
        check_known_hosts_security(path)
        validate_target_trust_file(profile)
    except Exception:
        try:
            if temp.exists():
                temp.unlink()
        finally:
            raise


def plan_console_verified_trust(
    profile: dict[str, Any],
    *,
    fingerprint: str,
    rotate: bool,
    console_address: str | None = None,
) -> dict[str, Any]:
    if FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise DeploymentKitError(
            "Supply the SHA256 fingerprint independently observed at the trusted target console."
        )

    identity = Path(profile["identityFile"])
    trust_path = Path(profile["knownHostsFile"])
    check_identity_security(identity)
    existing = validate_target_trust_file(profile, allow_missing_or_empty=True)
    if rotate:
        if not existing:
            raise DeploymentKitError("Trust rotation requires an existing valid target-specific trust entry.")
        check_known_hosts_security(trust_path)
    elif existing:
        raise DeploymentKitError("Target trust is already enrolled; use explicit trust rotation instead.")

    candidates = scan_host_keys(profile, console_address=console_address)
    matches = [candidate for candidate in candidates if candidate["fingerprint"] == fingerprint]
    if not matches:
        raise DeploymentKitError(
            "The console-observed fingerprint did not match any candidate returned by the configured target/address. "
            "No trust was written."
        )
    identities = {(item["keyType"], item["keyData"]) for item in matches}
    if len(identities) != 1:
        raise DeploymentKitError("Fingerprint matched inconsistent host-key candidates; no trust was written.")

    selected = matches[0]
    return {
        "targetName": profile["targetName"],
        "action": "rotate" if rotate else "enroll",
        "fingerprint": fingerprint,
        "keyType": selected["keyType"],
        "keyData": selected["keyData"],
        "address": selected["address"],
        "knownHostsFile": str(trust_path),
        "priorTrust": existing,
    }


def trust_plan_view(plan: dict[str, Any]) -> dict[str, str]:
    return {
        "targetName": plan["targetName"],
        "action": plan["action"],
        "address": plan["address"],
        "keyType": plan["keyType"],
        "fingerprint": plan["fingerprint"],
        "knownHostsFile": plan["knownHostsFile"],
    }


def apply_trust_plan(profile: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    if plan["targetName"] != profile["targetName"]:
        raise DeploymentKitError("Trust plan target does not match the selected profile.")
    current = validate_target_trust_file(profile, allow_missing_or_empty=True)
    if current != plan["priorTrust"]:
        raise DeploymentKitError(
            "Target trust state changed after the plan was reviewed; no trust was written. Re-plan and re-authorize."
        )
    if current:
        check_known_hosts_security(Path(profile["knownHostsFile"]))
    check_identity_security(Path(profile["identityFile"]))
    _write_exact_trust(profile, plan["keyType"], plan["keyData"])
    return {
        "targetName": profile["targetName"],
        "status": "rotated" if plan["action"] == "rotate" else "enrolled",
        "fingerprint": plan["fingerprint"],
        "keyType": plan["keyType"],
        "address": plan["address"],
        "knownHostsFile": plan["knownHostsFile"],
        "mutated": True,
    }


def apply_console_verified_trust(
    profile: dict[str, Any],
    *,
    fingerprint: str,
    rotate: bool,
    console_address: str | None = None,
) -> dict[str, Any]:
    plan = plan_console_verified_trust(
        profile,
        fingerprint=fingerprint,
        rotate=rotate,
        console_address=console_address,
    )
    return apply_trust_plan(profile, plan)
