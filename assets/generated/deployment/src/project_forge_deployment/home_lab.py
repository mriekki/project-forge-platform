"""Password-assisted Home Lab target onboarding with local-only credential prompting."""

from __future__ import annotations

import base64
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .keys import key_fingerprint, public_key_info, required_tool as required_ssh_tool
from .portable_profile import _machine_paths
from .profiles import load_profile, save_profile, target_profile_path, validate_profile, validate_target_name
from .security import check_identity_security, prepare_ssh_directory, validate_target_trust_file
from .ssh import probe_authentication_methods, resolve_addresses, verify_access


HOME_LAB_BOOTSTRAP_PHRASE = "[HOME LAB ACCESS BOOTSTRAP]"


def _create_unencrypted_key(profile: dict[str, Any]) -> dict[str, Any]:
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
            required_ssh_tool("ssh-keygen"),
            "-q",
            "-t",
            "ed25519",
            "-a",
            "64",
            "-N",
            "",
            "-f",
            str(identity),
            "-C",
            comment,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentKitError(
            "ssh-keygen did not complete successfully. Any partial key material is left for explicit inspection."
        )
    if not identity.is_file() or identity.is_symlink() or not public.is_file() or public.is_symlink():
        raise DeploymentKitError("ssh-keygen completed without the expected private/public key pair.")
    if os.name != "nt":
        identity.chmod(0o600)
        public.chmod(0o644)
    check_identity_security(identity)
    return {
        "identityFile": str(identity),
        "publicKeyFile": str(public),
        "identityFingerprint": key_fingerprint(identity),
        "passphrase": "none",
        "mutated": True,
    }


def _desired_profile(
    name: str,
    *,
    host_name: str,
    user: str,
    port: int,
    ssh_alias: str | None,
    address: str | None,
) -> dict[str, Any]:
    identity, known_hosts = _machine_paths(validate_target_name(name))
    return validate_profile(
        {
            "schemaVersion": 1,
            "targetName": name,
            "targetOs": "ubuntu",
            "hostName": host_name,
            "sshAlias": ssh_alias or name,
            "user": user,
            "port": port,
            "identityFile": identity,
            "knownHostsFile": known_hosts,
            "addressOverride": address,
        },
        expected_target_name=name,
    )


def _same_target_definition(left: dict[str, Any], right: dict[str, Any]) -> bool:
    fields = ("targetName", "targetOs", "hostName", "sshAlias", "user", "port", "addressOverride")
    return all(left[field] == right[field] for field in fields)


def plan_home_lab_bootstrap(
    name: str,
    *,
    host_name: str,
    user: str,
    port: int = 22,
    ssh_alias: str | None = None,
    address: str | None = None,
    protect_key_with_passphrase: bool = False,
) -> dict[str, Any]:
    desired = _desired_profile(
        name,
        host_name=host_name,
        user=user,
        port=port,
        ssh_alias=ssh_alias,
        address=address,
    )
    path = target_profile_path(name)
    profile_state = "create"
    if path.exists():
        current = load_profile(name)
        if not _same_target_definition(current, desired):
            raise DeploymentKitError(
                "Existing target profile differs from the requested Home Lab definition. "
                "Refusing to overwrite it; inspect/repair the profile explicitly."
            )
        desired = current
        profile_state = "reuse"

    identity = Path(desired["identityFile"])
    public = Path(f"{identity}.pub")
    if identity.exists() != public.exists():
        raise DeploymentKitError("Existing SSH key pair is incomplete; repair it explicitly before onboarding.")
    key_state = "reuse" if identity.exists() else "create"

    known_hosts = Path(desired["knownHostsFile"])
    trust_state = "reuse" if known_hosts.is_file() and known_hosts.stat().st_size > 0 else "accept-first-use"
    if trust_state == "reuse":
        validate_target_trust_file(desired)

    return {
        "targetName": name,
        "securityProfile": "home-lab",
        "profileState": profile_state,
        "keyState": key_state,
        "keyPassphraseMode": "interactive" if protect_key_with_passphrase else "none",
        "trustState": trust_state,
        "hostName": desired["hostName"],
        "addressOverride": desired["addressOverride"],
        "sshAlias": desired["sshAlias"],
        "user": desired["user"],
        "port": desired["port"],
        "identityFile": desired["identityFile"],
        "knownHostsFile": desired["knownHostsFile"],
        "passwordHandling": "OpenSSH local terminal prompt only; never stored or passed as an argument",
        "mutated": False,
    }


def _create_key(profile: dict[str, Any], *, protect_key_with_passphrase: bool) -> dict[str, Any]:
    if protect_key_with_passphrase:
        # Existing helper intentionally lets ssh-keygen own the interactive passphrase prompt.
        from .keys import create_dedicated_key

        result = create_dedicated_key(profile)
        return {**result, "passphrase": "interactive"}
    return _create_unencrypted_key(profile)


def _password_bootstrap_args(profile: dict[str, Any], *, first_use: bool, command: str) -> list[str]:
    target = profile["addressOverride"] or profile["hostName"]
    return [
        required_ssh_tool("ssh"),
        "-F",
        "none",
        "-o",
        "BatchMode=no",
        "-o",
        "ConnectTimeout=8",
        "-o",
        f"StrictHostKeyChecking={'accept-new' if first_use else 'yes'}",
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
        "PubkeyAuthentication=no",
        "-o",
        "PasswordAuthentication=yes",
        "-o",
        "KbdInteractiveAuthentication=yes",
        "-o",
        "PreferredAuthentications=keyboard-interactive,password",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ForwardX11=no",
        "-o",
        "ClearAllForwardings=yes",
        "-p",
        str(profile["port"]),
        f"{profile['user']}@{target}",
        command,
    ]


def _require_password_bootstrap_capability(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Fail before password onboarding when a trusted server advertises key-only auth."""

    evidence = [probe_authentication_methods(profile, address) for address in resolve_addresses(profile)]
    observed = [item for item in evidence if item["observed"]]
    if observed and not any(item["passwordSupported"] for item in observed):
        advertised = sorted({method for item in observed for method in item["methods"]})
        shown = ", ".join(advertised) if advertised else "none observed"
        raise DeploymentKitError(
            "Password-assisted Home Lab bootstrap is unavailable for this trusted target: "
            f"the SSH server advertises {shown}, not password/keyboard-interactive authentication. "
            "Use the Strict key-onboarding path and a trusted console or already-authorized session "
            "for any required server-side key/account-policy change. Do not enable password SSH merely for bootstrap."
        )
    return evidence


def _install_public_key_with_password(profile: dict[str, Any], *, first_use: bool) -> None:
    info = public_key_info(profile)
    encoded = base64.b64encode(info["publicKey"].encode("utf-8")).decode("ascii")
    script = (
        "set -eu; umask 077; mkdir -p \"$HOME/.ssh\"; chmod 700 \"$HOME/.ssh\"; "
        "auth=\"$HOME/.ssh/authorized_keys\"; touch \"$auth\"; chmod 600 \"$auth\"; "
        f"key=$(printf '%s' {shlex.quote(encoded)} | base64 --decode); "
        "grep -Fxq -- \"$key\" \"$auth\" || printf '%s\\n' \"$key\" >> \"$auth\""
    )
    known_hosts = Path(profile["knownHostsFile"])
    prepare_ssh_directory(known_hosts.parent)
    print(
        f"OpenSSH will prompt locally for the password of {profile['user']}@{profile['hostName']}. "
        "The password is not read or stored by Project Forge."
    )
    result = subprocess.run(
        _password_bootstrap_args(
            profile,
            first_use=first_use,
            command="bash -c " + shlex.quote(script),
        ),
        check=False,
    )
    if result.returncode != 0:
        raise DeploymentKitError(
            "Password-assisted SSH bootstrap did not complete successfully. "
            "No password was retained; inspect target access and retry."
        )


def apply_home_lab_bootstrap(
    plan: dict[str, Any],
    *,
    protect_key_with_passphrase: bool = False,
) -> dict[str, Any]:
    required = {
        "targetName",
        "securityProfile",
        "profileState",
        "keyState",
        "keyPassphraseMode",
        "trustState",
        "hostName",
        "addressOverride",
        "sshAlias",
        "user",
        "port",
        "identityFile",
        "knownHostsFile",
        "passwordHandling",
        "mutated",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan["securityProfile"] != "home-lab":
        raise DeploymentKitError("Malformed Home Lab bootstrap plan.")

    desired = _desired_profile(
        plan["targetName"],
        host_name=plan["hostName"],
        user=plan["user"],
        port=plan["port"],
        ssh_alias=plan["sshAlias"],
        address=plan["addressOverride"],
    )
    path = target_profile_path(plan["targetName"])
    mutated = False
    if plan["profileState"] == "create":
        if path.exists():
            raise DeploymentKitError("Target profile appeared after planning; create a fresh onboarding plan.")
        save_profile(desired)
        mutated = True
    else:
        current = load_profile(plan["targetName"])
        if not _same_target_definition(current, desired):
            raise DeploymentKitError("Target profile changed after planning; create a fresh onboarding plan.")
        desired = current

    identity = Path(desired["identityFile"])
    public = Path(f"{identity}.pub")
    if plan["keyState"] == "create":
        if identity.exists() or public.exists():
            raise DeploymentKitError("SSH key material appeared after planning; create a fresh onboarding plan.")
        _create_key(desired, protect_key_with_passphrase=protect_key_with_passphrase)
        mutated = True
    elif not identity.is_file() or not public.is_file():
        raise DeploymentKitError("Expected existing SSH key pair is no longer present.")

    known_hosts = Path(desired["knownHostsFile"])
    first_use = plan["trustState"] == "accept-first-use"
    if not first_use:
        validate_target_trust_file(desired)

    # If the complete strict path is already healthy, do not ask for a password again.
    if not first_use:
        try:
            evidence = verify_access(desired)
            return {
                "targetName": desired["targetName"],
                "status": "already-ready",
                "strictVerification": evidence,
                "mutated": mutated,
            }
        except DeploymentKitError:
            pass

        # Existing trust lets us discover the server's advertised auth methods safely.
        # Avoid a guaranteed-to-fail password prompt against public-key-only servers.
        _require_password_bootstrap_capability(desired)

    _install_public_key_with_password(desired, first_use=first_use)
    validate_target_trust_file(desired)
    evidence = verify_access(desired)
    return {
        "targetName": desired["targetName"],
        "status": "ready",
        "strictVerification": evidence,
        "passwordRetained": False,
        "mutated": True,
    }
