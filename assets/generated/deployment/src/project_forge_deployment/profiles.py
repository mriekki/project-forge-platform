"""User-scoped logical target profiles."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError


PROFILE_SCHEMA_VERSION = 1
TARGET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}$")
HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
SUPPORTED_TARGET_OS = {"ubuntu"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DeploymentKitError(f"Duplicate JSON property: {key}")
        value[key] = item
    return value


def config_root(home: Path | None = None) -> Path:
    override = os.environ.get("PROJECT_FORGE_HOME")
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            raise DeploymentKitError("PROJECT_FORGE_HOME must be an absolute path.")
        return candidate.resolve()
    return ((home or Path.home()).resolve() / ".project-forge").resolve()


def validate_target_name(name: str) -> str:
    if not isinstance(name, str) or TARGET_NAME_RE.fullmatch(name) is None:
        raise DeploymentKitError(
            "Target name must use lowercase letters, digits, and hyphens, and must start with a letter or digit."
        )
    return name


def target_profile_path(name: str, home: Path | None = None) -> Path:
    validate_target_name(name)
    return config_root(home) / "targets" / f"{name}.json"


def _validate_host_name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise DeploymentKitError("hostName must be a DNS/mDNS hostname.")
    if value.endswith("."):
        value = value[:-1]
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise DeploymentKitError(
            "hostName must be a stable DNS/mDNS name, not an IP address; use addressOverride for a verified temporary IP."
        )
    labels = value.split(".")
    if any(HOST_LABEL_RE.fullmatch(label) is None for label in labels):
        raise DeploymentKitError("hostName must be a valid DNS/mDNS hostname.")
    return value.lower()


def _ssh_path(value: Any, field: str, home: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentKitError(f"{field} must not be empty.")
    if value == "~":
        candidate = home
    elif value.startswith("~/") or value.startswith("~\\"):
        candidate = home / value[2:]
    else:
        candidate = Path(value)
    if not candidate.is_absolute():
        raise DeploymentKitError(f"{field} must be absolute or home-relative with '~'.")
    resolved = candidate.resolve()
    ssh_dir = (home / ".ssh").resolve()
    if resolved == ssh_dir or not resolved.is_relative_to(ssh_dir):
        raise DeploymentKitError(f"{field} must be a file inside the user's SSH directory: {ssh_dir}")
    return resolved


def validate_profile(
    value: dict[str, Any],
    *,
    expected_target_name: str | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    expected_fields = {
        "schemaVersion",
        "targetName",
        "targetOs",
        "hostName",
        "sshAlias",
        "user",
        "port",
        "identityFile",
        "knownHostsFile",
        "addressOverride",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise DeploymentKitError(
            "Target profile must contain exactly: " + ", ".join(sorted(expected_fields)) + "."
        )
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != PROFILE_SCHEMA_VERSION:
        raise DeploymentKitError("Unsupported target profile schemaVersion.")

    target_name = validate_target_name(value["targetName"])
    if expected_target_name is not None and target_name != expected_target_name:
        raise DeploymentKitError(
            f"Target profile mismatch: expected '{expected_target_name}', got '{target_name}'."
        )

    target_os = value["targetOs"]
    if target_os not in SUPPORTED_TARGET_OS:
        raise DeploymentKitError(
            f"Unsupported targetOs '{target_os}'. Initial support is limited to: {', '.join(sorted(SUPPORTED_TARGET_OS))}."
        )

    host_name = _validate_host_name(value["hostName"])
    alias = value["sshAlias"]
    if not isinstance(alias, str) or ALIAS_RE.fullmatch(alias) is None:
        raise DeploymentKitError("sshAlias contains unsupported characters.")

    username = value["user"]
    if not isinstance(username, str) or USER_RE.fullmatch(username) is None:
        raise DeploymentKitError("user contains unsupported characters.")

    port = value["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise DeploymentKitError("port must be an integer from 1 through 65535.")

    user_home = (home or Path.home()).resolve()
    identity_file = _ssh_path(value["identityFile"], "identityFile", user_home)
    known_hosts_file = _ssh_path(value["knownHostsFile"], "knownHostsFile", user_home)
    if identity_file == known_hosts_file:
        raise DeploymentKitError("identityFile and knownHostsFile must be different paths.")

    address_override = value["addressOverride"]
    if address_override is not None:
        if not isinstance(address_override, str):
            raise DeploymentKitError("addressOverride must be null or an IP address.")
        try:
            parsed = ipaddress.ip_address(address_override)
        except ValueError as error:
            raise DeploymentKitError("addressOverride must be a valid IPv4 or IPv6 address.") from error
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
            raise DeploymentKitError("addressOverride must not include an IPv6 scope identifier.")
        address_override = str(parsed)

    return {
        "schemaVersion": PROFILE_SCHEMA_VERSION,
        "targetName": target_name,
        "targetOs": target_os,
        "hostName": host_name,
        "sshAlias": alias,
        "user": username,
        "port": port,
        "identityFile": str(identity_file),
        "knownHostsFile": str(known_hosts_file),
        "addressOverride": address_override,
    }


def load_profile(name: str, *, home: Path | None = None) -> dict[str, Any]:
    path = target_profile_path(name, home)
    if path.is_symlink() or path.parent.is_symlink():
        raise DeploymentKitError("Target profile and its containing directory must not be symbolic links.")
    if not path.is_file():
        raise DeploymentKitError(f"Target profile is missing: {path}")
    try:
        with path.open(encoding="utf-8") as source:
            value = json.load(source, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read target profile {path}: {error}") from error
    return validate_profile(value, expected_target_name=name, home=home)


def save_profile(value: dict[str, Any], *, home: Path | None = None) -> Path:
    normalized = validate_profile(value, home=home)
    path = target_profile_path(normalized["targetName"], home)
    directory = path.parent
    if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
        raise DeploymentKitError(f"Target profile directory is not a real directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        directory.chmod(0o700)
    if path.exists() and path.is_symlink():
        raise DeploymentKitError(f"Refusing to replace symbolic-link target profile: {path}")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(0o600)
    temporary.replace(path)
    return path
