"""Filesystem integrity checks for SSH identity and host-trust material."""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError


WINDOWS_SID_RE = __import__("re").compile(r"^S-1-(?:[0-9]+-){1,15}[0-9]+$")
HOST_KEY_TYPES = {"ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa"}


def _valid_windows_sid(value: Any) -> bool:
    if not isinstance(value, str) or WINDOWS_SID_RE.fullmatch(value) is None:
        return False
    components = value.split("-")
    subauthorities = components[3:]
    if not 1 <= len(subauthorities) <= 15:
        return False

    def within_bound(component: str, maximum: int) -> bool:
        if component != "0" and component.startswith("0"):
            return False
        limit = str(maximum)
        return len(component) < len(limit) or (len(component) == len(limit) and component <= limit)

    return within_bound(components[2], 0xFFFFFFFFFFFF) and all(
        within_bound(component, 0xFFFFFFFF) for component in subauthorities
    )


def validate_windows_acl_report(report: Any) -> None:
    try:
        if not isinstance(report, dict) or set(report) != {"currentUserSid", "entries"}:
            raise ValueError("unexpected ACL report shape")
        current_user = report["currentUserSid"]
        entries = report["entries"]
        if not _valid_windows_sid(current_user):
            raise ValueError("invalid current-user SID")
        if not isinstance(entries, list) or not entries:
            raise ValueError("missing ACL entries")

        trusted_sids = {current_user, "S-1-5-18", "S-1-5-32-544"}
        write_rights = 2 | 4 | 16 | 64 | 256 | 65536 | 262144 | 524288
        known_rights = (
            1 | 2 | 4 | 8 | 16 | 32 | 64 | 128 | 256 |
            65536 | 131072 | 262144 | 524288 | 1048576
        )

        for entry in entries:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"path", "ownerSid", "reparsePoint", "rules"}
                or not isinstance(entry["path"], str)
                or not entry["path"]
                or not _valid_windows_sid(entry["ownerSid"])
                or type(entry["reparsePoint"]) is not bool
                or not isinstance(entry["rules"], list)
            ):
                raise ValueError("malformed ACL entry")
            if entry["reparsePoint"] or entry["ownerSid"] not in trusted_sids:
                raise DeploymentKitError(
                    f"Windows SSH material has an untrusted owner or reparse point: {entry['path']}"
                )
            for rule in entry["rules"]:
                if (
                    not isinstance(rule, dict)
                    or set(rule) != {"sid", "rights", "type"}
                    or not _valid_windows_sid(rule["sid"])
                    or rule["type"] not in {"Allow", "Deny"}
                    or type(rule["rights"]) is not int
                    or rule["rights"] < 0
                    or rule["rights"] & ~known_rights
                ):
                    raise ValueError("malformed ACL rule")
                if (
                    rule["type"] == "Allow"
                    and rule["sid"] not in trusted_sids
                    and rule["rights"] & write_rights
                ):
                    raise DeploymentKitError(
                        f"Windows SSH material grants write access to an untrusted principal: {entry['path']}"
                    )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DeploymentKitError(
            "Windows SSH-material ACL report was malformed; verification is blocked."
        ) from error


def _ssh_directory_for(path: Path) -> Path:
    candidates = (path, *path.parents)
    ssh_directory = next((candidate for candidate in candidates if candidate.name.lower() == ".ssh"), None)
    if ssh_directory is None:
        raise DeploymentKitError("SSH material is not inside the user's .ssh directory.")
    return ssh_directory


def _check_windows_acl(path: Path) -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        raise DeploymentKitError(
            "Cannot verify Windows SSH-material ACLs because PowerShell is unavailable."
        )
    ssh_directory = _ssh_directory_for(path)

    checked_paths = [path]
    directory = path.parent
    while True:
        checked_paths.append(directory)
        if directory == ssh_directory.parent:
            break
        if directory != ssh_directory and ssh_directory not in directory.parents:
            raise DeploymentKitError("SSH-material path escaped the user's .ssh directory.")
        directory = directory.parent

    serialized_paths = json.dumps([str(candidate) for candidate in dict.fromkeys(checked_paths)])
    serialized_paths = serialized_paths.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$paths = @(ConvertFrom-Json -InputObject '{serialized_paths}')
$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$entries = foreach ($candidate in $paths) {{
    $item = Get-Item -LiteralPath $candidate -Force
    $acl = Get-Acl -LiteralPath $candidate
    $rules = foreach ($rule in $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {{
        [ordered]@{{
            sid = $rule.IdentityReference.Value
            rights = [int]$rule.FileSystemRights
            type = $rule.AccessControlType.ToString()
        }}
    }}
    [ordered]@{{
        path = $candidate
        ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
        reparsePoint = (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
        rules = @($rules)
    }}
}}
[ordered]@{{ currentUserSid = $userSid; entries = @($entries) }} | ConvertTo-Json -Depth 6 -Compress
"""
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DeploymentKitError(
            "Cannot verify Windows SSH-material ACLs; access verification is blocked."
        )
    try:
        validate_windows_acl_report(json.loads(result.stdout))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise DeploymentKitError(
            "Windows SSH-material ACL report was malformed; verification is blocked."
        ) from error


def _posix_directory_chain(path: Path) -> list[Path]:
    ssh_directory = _ssh_directory_for(path)
    directories: list[Path] = []
    current = path.parent
    while True:
        directories.append(current)
        if current == ssh_directory:
            return directories
        if current == current.parent:
            raise DeploymentKitError("SSH-material path escaped the user's .ssh directory.")
        current = current.parent


def _posix_directory_issues(path: Path) -> list[str]:
    issues: list[str] = []
    current_uid = os.getuid()
    for directory in _posix_directory_chain(path):
        if directory.is_symlink():
            issues.append(f"symbolic link: {directory}")
            continue
        if not directory.exists():
            continue
        if not directory.is_dir():
            issues.append(f"not a directory: {directory}")
            continue
        details = directory.stat()
        if details.st_uid != current_uid:
            issues.append(f"not owned by the current user: {directory}")
        if details.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            issues.append(f"permissions are too broad: {directory}")
    return issues


def _check_posix_directories(path: Path) -> None:
    issues = _posix_directory_issues(path)
    if issues:
        raise DeploymentKitError("SSH directory chain is unsafe: " + "; ".join(issues))


def prepare_ssh_directory(path: Path) -> None:
    """Create missing owned SSH directories safely without silently repairing existing unsafe state."""
    _ssh_directory_for(path)
    if os.name == "nt":
        if path.exists():
            if path.is_symlink() or not path.is_dir():
                raise DeploymentKitError(f"SSH material directory is not a real directory: {path}")
        else:
            path.mkdir(parents=True, mode=0o700)
        _check_windows_acl(path)
        return

    probe = path / "placeholder"
    issues = _posix_directory_issues(probe)
    if issues:
        raise DeploymentKitError("SSH directory chain is unsafe: " + "; ".join(issues))

    for directory in reversed(_posix_directory_chain(probe)):
        if directory.exists():
            continue
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)

    _check_posix_directories(probe)


def check_identity_security(identity: Path) -> None:
    if not identity.is_file():
        raise DeploymentKitError(f"Required SSH identity is missing: {identity}")
    if identity.is_symlink():
        raise DeploymentKitError(f"SSH material must not use symbolic links: {identity}")
    if os.name == "nt":
        _check_windows_acl(identity)
    else:
        _check_posix_directories(identity)
        if identity.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise DeploymentKitError(f"Private key permissions are too broad: {identity}")


def check_known_hosts_security(known_hosts: Path) -> None:
    if not known_hosts.is_file():
        raise DeploymentKitError(f"Required SSH trust file is missing: {known_hosts}")
    if known_hosts.is_symlink():
        raise DeploymentKitError(f"SSH material must not use symbolic links: {known_hosts}")
    if os.name == "nt":
        _check_windows_acl(known_hosts)
    else:
        _check_posix_directories(known_hosts)
        if known_hosts.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise DeploymentKitError(f"Target trust file is writable by another principal: {known_hosts}")


def check_ssh_material_security(identity: Path, known_hosts: Path) -> None:
    check_identity_security(identity)
    check_known_hosts_security(known_hosts)


def known_hosts_token(profile: dict[str, Any]) -> str:
    alias = profile["sshAlias"]
    port = profile["port"]
    return alias if port == 22 else f"[{alias}]:{port}"


def validate_target_trust_file(
    profile: dict[str, Any],
    *,
    allow_missing_or_empty: bool = False,
) -> list[tuple[str, str]]:
    """Validate that a target trust file contains only one exact stable-alias host key."""
    path = Path(profile["knownHostsFile"])
    if not path.exists():
        if allow_missing_or_empty:
            return []
        raise DeploymentKitError(f"Target-specific trust file is missing: {path}")
    if path.is_symlink() or not path.is_file():
        raise DeploymentKitError(f"Target-specific trust file is not a real file: {path}")
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise DeploymentKitError(f"Cannot read target-specific trust file {path}: {error}") from error

    lines = [line.strip() for line in raw_lines if line.strip()]
    if not lines:
        if allow_missing_or_empty:
            return []
        raise DeploymentKitError(f"Target-specific trust file is empty: {path}")
    if len(lines) != 1:
        raise DeploymentKitError(
            "Target-specific trust file must contain exactly one literal stable-alias host key."
        )

    fields = lines[0].split()
    if len(fields) != 3:
        raise DeploymentKitError("Target-specific trust entry must contain exactly host, key type, and key data.")
    host_token, key_type, key_data = fields
    expected = known_hosts_token(profile)
    if host_token != expected:
        raise DeploymentKitError(
            f"Target-specific trust entry must use only the stable alias token '{expected}'."
        )
    if any(marker in host_token for marker in ("*", "?", ",", "|")) or host_token.startswith("@"):
        raise DeploymentKitError("Wildcard, hashed, marked, or multi-host trust entries are not allowed.")
    if key_type not in HOST_KEY_TYPES:
        raise DeploymentKitError(f"Unsupported target host-key type in trust file: {key_type}")
    try:
        decoded = base64.b64decode(key_data.encode("ascii"), validate=True)
    except (ValueError, UnicodeError) as error:
        raise DeploymentKitError("Target-specific trust entry contains invalid key data.") from error
    if not decoded:
        raise DeploymentKitError("Target-specific trust entry contains empty key data.")
    return [(key_type, key_data)]
