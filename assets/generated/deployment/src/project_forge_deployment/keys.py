"""Dedicated SSH-key and agent onboarding helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .security import check_identity_security, prepare_ssh_directory


FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def required_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DeploymentKitError(f"Required OpenSSH tool is unavailable: {name}")
    return path


def key_fingerprint(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise DeploymentKitError(f"SSH key file is missing or unsafe: {path}")
    result = subprocess.run(
        [required_tool("ssh-keygen"), "-lf", str(path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot read SSH key fingerprint for {path}.")
    fingerprint = next(
        (token for token in result.stdout.split() if FINGERPRINT_RE.fullmatch(token)),
        None,
    )
    if fingerprint is None:
        raise DeploymentKitError(f"ssh-keygen returned no valid SHA256 fingerprint for {path}.")
    return fingerprint


def create_dedicated_key(profile: dict[str, Any]) -> dict[str, Any]:
    identity = Path(profile["identityFile"])
    public = Path(f"{identity}.pub")
    if identity.exists() or public.exists():
        raise DeploymentKitError(
            f"Refusing to overwrite existing SSH key material: {identity} / {public}"
        )

    prepare_ssh_directory(identity.parent)
    comment = f"project-forge:{profile['targetName']}:{profile['sshAlias']}"
    result = subprocess.run(
        [
            required_tool("ssh-keygen"),
            "-q",
            "-t",
            "ed25519",
            "-a",
            "64",
            "-f",
            str(identity),
            "-C",
            comment,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentKitError(
            "ssh-keygen did not complete successfully. Any partial key material is left in place for explicit inspection."
        )
    if not identity.is_file() or identity.is_symlink() or not public.is_file() or public.is_symlink():
        raise DeploymentKitError("ssh-keygen completed without the expected private/public key pair.")

    if os.name != "nt":
        identity.chmod(0o600)
        public.chmod(0o644)
    check_identity_security(identity)
    return {
        "targetName": profile["targetName"],
        "identityFile": str(identity),
        "publicKeyFile": str(public),
        "identityFingerprint": key_fingerprint(identity),
        "status": "created",
        "mutated": True,
    }


def public_key_info(profile: dict[str, Any]) -> dict[str, str]:
    identity = Path(profile["identityFile"])
    public = Path(f"{identity}.pub")
    check_identity_security(identity)
    if not public.is_file() or public.is_symlink():
        raise DeploymentKitError(f"Dedicated public key is missing or unsafe: {public}")
    try:
        lines = [line.strip() for line in public.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError) as error:
        raise DeploymentKitError(f"Cannot read dedicated public key {public}: {error}") from error
    if len(lines) != 1 or not lines[0].startswith("ssh-ed25519 "):
        raise DeploymentKitError("Dedicated public-key file must contain exactly one ssh-ed25519 key.")
    return {
        "targetName": profile["targetName"],
        "publicKeyFile": str(public),
        "identityFingerprint": key_fingerprint(identity),
        "publicKey": lines[0],
    }


def agent_status(profile: dict[str, Any]) -> dict[str, Any]:
    identity = Path(profile["identityFile"])
    check_identity_security(identity)
    fingerprint = key_fingerprint(identity)
    result = subprocess.run(
        [required_tool("ssh-add"), "-l"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 2:
        return {
            "targetName": profile["targetName"],
            "state": "agent-unavailable",
            "identityFingerprint": fingerprint,
            "loaded": False,
            "mutated": False,
        }
    if result.returncode == 1:
        return {
            "targetName": profile["targetName"],
            "state": "not-loaded",
            "identityFingerprint": fingerprint,
            "loaded": False,
            "mutated": False,
        }
    if result.returncode != 0:
        raise DeploymentKitError(f"ssh-add could not inspect the running SSH agent (exit {result.returncode}).")
    loaded = fingerprint in result.stdout.split()
    return {
        "targetName": profile["targetName"],
        "state": "loaded" if loaded else "not-loaded",
        "identityFingerprint": fingerprint,
        "loaded": loaded,
        "mutated": False,
    }


def add_key_to_agent(profile: dict[str, Any]) -> dict[str, Any]:
    before = agent_status(profile)
    if before["state"] == "agent-unavailable":
        raise DeploymentKitError(
            "The SSH agent is unavailable. Start/enable it as a separate workstation action; "
            "the Deployment Kit will not change agent service configuration implicitly."
        )
    if before["loaded"]:
        return {**before, "status": "already-loaded"}

    identity = Path(profile["identityFile"])
    result = subprocess.run([required_tool("ssh-add"), str(identity)], check=False)
    if result.returncode != 0:
        raise DeploymentKitError("ssh-add did not load the dedicated identity.")
    after = agent_status(profile)
    if not after["loaded"]:
        raise DeploymentKitError("ssh-add reported success but the dedicated identity is not visible in the agent.")
    return {**after, "status": "loaded", "mutated": True}
