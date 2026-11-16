"""Strict SSH verification and bounded diagnostics for logical targets."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .keys import agent_status, key_fingerprint
from .security import check_ssh_material_security, validate_target_trust_file


_AUTH_METHODS_RE = re.compile(r"Authentications that can continue:\s*(?P<methods>[^\r\n]+)")
_PERMISSION_DENIED_RE = re.compile(r"Permission denied \((?P<methods>[^)]+)\)")


def required_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DeploymentKitError(f"Required OpenSSH tool is unavailable: {name}")
    return path


def resolve_addresses(profile: dict[str, Any]) -> list[str]:
    override = profile["addressOverride"]
    if override:
        return [override]
    try:
        answers = socket.getaddrinfo(
            profile["hostName"],
            profile["port"],
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise DeploymentKitError(
            f"Cannot resolve target hostname {profile['hostName']}: {error}. "
            "Use only a separately verified address override; do not scan the network."
        ) from error
    addresses = sorted({answer[4][0] for answer in answers})
    if not addresses:
        raise DeploymentKitError(f"Target hostname {profile['hostName']} returned no addresses.")
    return addresses


def _strict_transport_args(profile: dict[str, Any], address: str) -> list[str]:
    return [
        required_tool("ssh"),
        "-F",
        "none",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UpdateHostKeys=no",
        "-o",
        "CheckHostIP=no",
        "-o",
        "VerifyHostKeyDNS=no",
        "-o",
        "GlobalKnownHostsFile=none",
        "-o",
        f"UserKnownHostsFile={profile['knownHostsFile']}",
        "-o",
        f"HostKeyAlias={profile['sshAlias']}",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ForwardX11=no",
        "-o",
        "ClearAllForwardings=yes",
        "-p",
        str(profile["port"]),
    ]


def ssh_args(
    profile: dict[str, Any],
    address: str,
    *,
    command: str = "true",
    verbose: bool = False,
) -> list[str]:
    args = _strict_transport_args(profile, address)
    if verbose:
        args.insert(1, "-vv")
    args.extend(
        [
            "-o",
            f"IdentityFile={profile['identityFile']}",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "PreferredAuthentications=publickey",
            f"{profile['user']}@{address}",
            command,
        ]
    )
    return args


def authentication_probe_args(profile: dict[str, Any], address: str) -> list[str]:
    """Build a read-only SSH handshake that discovers advertised auth methods.

    Host identity is still verified through the configured target-specific trust file.
    All actual client authentication mechanisms are disabled so the server's initial
    authentication-method advertisement can be observed without attempting credentials.
    """

    args = _strict_transport_args(profile, address)
    args.insert(1, "-vv")
    args.extend(
        [
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "GSSAPIAuthentication=no",
            "-o",
            "HostbasedAuthentication=no",
            f"{profile['user']}@{address}",
            "true",
        ]
    )
    return args


def _completed(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )


def _auth_methods(text: str) -> list[str]:
    methods: list[str] = []
    for match in _AUTH_METHODS_RE.finditer(text):
        for method in match.group("methods").split(","):
            value = method.strip()
            if value and value not in methods:
                methods.append(value)
    if not methods:
        denied = _PERMISSION_DENIED_RE.search(text)
        if denied:
            for method in denied.group("methods").split(","):
                value = method.strip()
                if value and value not in methods:
                    methods.append(value)
    return methods


def probe_authentication_methods(profile: dict[str, Any], address: str) -> dict[str, Any]:
    result = _completed(authentication_probe_args(profile, address))
    text = "\n".join(part for part in (result.stderr, result.stdout) if part)
    methods = _auth_methods(text)
    return {
        "address": address,
        "methods": methods,
        "passwordSupported": "password" in methods or "keyboard-interactive" in methods,
        "publicKeySupported": "publickey" in methods,
        "observed": bool(methods),
        "returnCode": result.returncode,
    }


def _tcp_probe(profile: dict[str, Any], address: str) -> dict[str, Any]:
    try:
        with socket.create_connection((address, int(profile["port"])), timeout=8):
            pass
        return {"state": "reachable", "address": address, "port": int(profile["port"])}
    except OSError as error:
        return {
            "state": "unreachable",
            "address": address,
            "port": int(profile["port"]),
            "reason": str(error),
        }


def _classify_failure(
    text: str,
    *,
    auth: dict[str, Any],
    offered: bool,
    accepted: bool,
    signer_loaded: bool | None = None,
) -> str:
    """Classify only what the SSH evidence proves.

    ``Server accepts key`` is a preliminary public-key handshake, not
    proof of client signing or of a completed authenticated session.
    """
    lower = text.lower()
    if "remote host identification has changed" in lower or "host key verification failed" in lower:
        return "host-identity-rejected"
    if any(
        marker in lower
        for marker in (
            "sign_and_send_pubkey: signing failed",
            "agent refused operation",
            "incorrect passphrase",
            "load key",
        )
    ):
        return "local-signing-failed"
    if "connection timed out" in lower or "connection refused" in lower or "no route to host" in lower:
        return "transport-failed"
    if "permission denied" in lower:
        if accepted:
            # No signer proof means neither a remote account-policy refusal
            # nor a verified credential rejection can be asserted.
            if "sign_and_send_pubkey: signing using" in lower:
                # A signer (agent or directly usable key) did sign, but
                # the remote side still refused authentication.
                return "remote-authentication-rejected"
            # Merely observing a loaded agent is not proof that this key signed.
            return "local-signing-unproven"
        if offered:
            # The server has enough evidence to refuse the offered key.
            return "remote-authentication-rejected"
        if auth.get("publicKeySupported") and signer_loaded is False:
            # A publickey-capable server does not establish that this
            # workstation could offer/sign the configured identity.
            return "local-signing-unproven"
        return "authentication-rejected"
    return "ssh-verification-failed"


def diagnose_access(profile: dict[str, Any]) -> dict[str, Any]:
    """Return safe structured SSH failure evidence without changing workstation or target state."""

    identity = Path(profile["identityFile"])
    known_hosts = Path(profile["knownHostsFile"])
    if not identity.is_file():
        return {
            "targetName": profile["targetName"],
            "state": "failed",
            "failureCategory": "missing-identity",
            "reason": f"Dedicated private key is missing: {identity}",
            "mutated": False,
        }
    if not known_hosts.is_file() or known_hosts.stat().st_size == 0:
        return {
            "targetName": profile["targetName"],
            "state": "failed",
            "failureCategory": "missing-trust",
            "reason": f"Target-specific trust file is missing or empty: {known_hosts}",
            "mutated": False,
        }

    try:
        check_ssh_material_security(identity, known_hosts)
        validate_target_trust_file(profile)
    except DeploymentKitError as error:
        return {
            "targetName": profile["targetName"],
            "state": "failed",
            "failureCategory": "local-security-or-trust-invalid",
            "reason": str(error),
            "mutated": False,
        }

    try:
        addresses = resolve_addresses(profile)
    except DeploymentKitError as error:
        return {
            "targetName": profile["targetName"],
            "state": "failed",
            "failureCategory": "name-resolution-failed",
            "reason": str(error),
            "mutated": False,
        }

    fingerprint = key_fingerprint(identity)
    local_signer: dict[str, Any] = {"state": "not-checked", "loaded": False}
    attempts: list[dict[str, Any]] = []
    for address in addresses:
        tcp = _tcp_probe(profile, address)
        if tcp["state"] != "reachable":
            attempts.append({"address": address, "tcp": tcp, "state": "transport-failed"})
            continue

        # Only examine the local agent when transport actually reached the
        # selected target. This remains a read-only observation: do not start
        # an agent, request a passphrase, or alter SSH trust during diagnosis.
        if local_signer["state"] == "not-checked":
            try:
                agent = agent_status(profile)
                local_signer = {
                    "state": agent["state"],
                    "loaded": agent["loaded"],
                }
            except (DeploymentKitError, OSError, KeyError):
                local_signer = {"state": "not-verified", "loaded": False}

        auth = probe_authentication_methods(profile, address)
        result = _completed(ssh_args(profile, address, verbose=True))
        text = "\n".join(part for part in (result.stderr, result.stdout) if part)
        offered = "offering public key" in text.lower()
        accepted = "server accepts key" in text.lower()
        if result.returncode == 0:
            return {
                "targetName": profile["targetName"],
                "state": "verified",
                "address": address,
                "identityFingerprint": fingerprint,
                "localSigner": local_signer,
                "authentication": auth,
                "offeredConfiguredIdentity": offered,
                "serverAcceptedConfiguredIdentity": accepted,
                "mutated": False,
            }

        attempts.append(
            {
                "address": address,
                "tcp": tcp,
                "authentication": auth,
                "identityFingerprint": fingerprint,
                "localSigner": local_signer,
                "offeredConfiguredIdentity": offered,
                "serverAcceptedConfiguredIdentity": accepted,
                "returnCode": result.returncode,
                "failureCategory": _classify_failure(
                    text,
                    auth=auth,
                    offered=offered,
                    accepted=accepted,
                    signer_loaded=local_signer["loaded"],
                ),
            }
        )

    category = "transport-failed"
    for candidate in (
        "host-identity-rejected",
        "local-signing-failed",
        "local-signing-unproven",
        "remote-account-policy-rejected",
        "remote-authentication-rejected",
        "authentication-rejected",
        "ssh-verification-failed",
    ):
        if any(item.get("failureCategory") == candidate for item in attempts):
            category = candidate
            break

    guidance = {
        "transport-failed": "Verify the configured address/port and network path; do not scan or silently switch targets.",
        "host-identity-rejected": "Re-verify host identity independently before any trust rotation.",
        "local-signing-failed": "Repair local key/passphrase/agent use; do not weaken remote authentication policy.",
        "local-signing-unproven": (
            "The server accepted a public key offer, but completed client signing "
            "was not established. Reuse the exact target's supported local SSH agent-session "
            "before investigating remote account policy. Do not weaken host trust."
        ),
        "remote-authentication-rejected": (
            "The configured public-key path reached the server but authentication was rejected. "
            "Verify authorized_keys and remote account/source access policy from a trusted console or already-authorized session."
        ),
        "remote-account-policy-rejected": (
            "The server accepted the configured key but the session was still rejected. "
            "Inspect remote account/source policy from a trusted console or already-authorized session."
        ),
        "authentication-rejected": "Inspect the server-advertised authentication policy and the configured account.",
        "ssh-verification-failed": "Inspect the structured attempt evidence before changing target or SSH policy.",
    }[category]

    return {
        "targetName": profile["targetName"],
        "state": "failed",
        "failureCategory": category,
        "identityFingerprint": fingerprint,
        "localSigner": local_signer,
        "attempts": attempts,
        "guidance": guidance,
        "mutated": False,
    }


def verify_access(profile: dict[str, Any]) -> dict[str, str]:
    identity = Path(profile["identityFile"])
    known_hosts = Path(profile["knownHostsFile"])
    if not identity.is_file():
        raise DeploymentKitError(f"Dedicated private key is missing: {identity}")
    if not known_hosts.is_file() or known_hosts.stat().st_size == 0:
        raise DeploymentKitError(
            f"Target-specific trust file is missing or empty: {known_hosts}. "
            "Enroll trust only after independently verifying the host fingerprint."
        )
    check_ssh_material_security(identity, known_hosts)
    validate_target_trust_file(profile)

    failures: list[str] = []
    for address in resolve_addresses(profile):
        result = _completed(ssh_args(profile, address))
        if result.returncode == 0:
            return {"targetName": profile["targetName"], "address": address, "status": "verified"}
        failures.append(f"{address}: exit {result.returncode}")

    raise DeploymentKitError(
        "Public-key SSH verification failed for all resolved addresses: " + "; ".join(failures)
    )
