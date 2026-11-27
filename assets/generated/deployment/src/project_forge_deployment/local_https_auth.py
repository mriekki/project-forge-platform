"""Opt-in WSL2 loopback HTTPS ingress for one local Auth Kit application."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
import shutil
import ssl
import stat
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .box_platform_assets import CADDY_IMAGE
from .errors import DeploymentKitError
from .local_extensions import snapshot_material
from .local_runtime import _preflight_material
from .local_spec import normalize_workstation_spec
from .profiles import config_root

LOCAL_HTTPS_AUTH_SCHEMA_VERSION = 1
LOCAL_HTTPS_AUTH_DEPLOY_WRITE_PHRASE = "[LOCAL HTTPS AUTH DEPLOY]"
LOCAL_HTTPS_AUTH_TRUST_WRITE_PHRASE = "[LOCAL HTTPS AUTH TRUST WRITE]"
LOCAL_HTTPS_AUTH_TRUST_REMOVE_PHRASE = "[LOCAL HTTPS AUTH TRUST REMOVE]"
LOCAL_HTTPS_AUTH_REMOVE_PHRASE = "[LOCAL HTTPS AUTH REMOVE]"
LOCAL_HTTPS_AUTH_RECOVER_PHRASE = "[LOCAL HTTPS AUTH RECOVER]"
LOCAL_HTTPS_AUTH_PORT = 443
LOCAL_HTTPS_AUTH_ORIGIN = "https://localhost"
LOCAL_HTTPS_AUTH_SECRET_FILE = "/run/secrets/pf-google-client-secret"
_AUTH_LABEL_PREFIX = "com.mriekki.project-forge.local-https-auth"
_AUTH_UID_GID = "1654:1654"
_AUTH_HEALTH_PATH = "/api/auth/me"
_AUTH_DB_PATH = "/data/project.sqlite"
_AUTH_KEYS_PATH = "/data/keys"
_AUTH_SECRET_ROOT = "/run/secrets/"
_FORBIDDEN_ENVIRONMENT_KEYS = {
    "ProjectForge__Authentication__DbPath",
    "ProjectForge__Authentication__DataProtectionKeysPath",
    "ProjectForge__Authentication__PublicOrigin",
    "ProjectForge__Authentication__TrustedProxyIp",
}
_INLINE_SECRET_ENVIRONMENT_SUFFIXES = {
    "accesstoken",
    "apikey",
    "clientsecret",
    "credential",
    "credentials",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
    "token",
}


class _LifecycleLockContention(DeploymentKitError):
    pass


def _docker() -> str:
    executable = shutil.which("docker")
    if not executable:
        raise DeploymentKitError("Local HTTPS Auth requires an available Docker CLI and engine.")
    context = subprocess.run(
        [executable, "context", "show"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if context.returncode != 0 or context.stdout.strip() != "default":
        raise DeploymentKitError("Local HTTPS Auth requires the reviewed Docker Desktop 'default' context.")
    completed = subprocess.run(
        [executable, "info", "--format", "{{.OperatingSystem}}"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or "docker desktop" not in completed.stdout.lower():
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError(
            "Local HTTPS Auth requires the reviewed Docker Desktop engine"
            + (f": {detail}" if detail else ".")
        )
    return executable


def _workspace_identity() -> str:
    completed = subprocess.run(
        ["git", "-C", str(Path.cwd()), "rev-parse", "--show-toplevel", "HEAD"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if len(lines) >= 1:
            return hashlib.sha256(lines[0].encode("utf-8")).hexdigest()
    return hashlib.sha256(str(Path.cwd().resolve()).encode("utf-8")).hexdigest()


def _docker_engine_identity(docker: str) -> str:
    completed = _run(docker, ["info", "--format", "{{.ID}}"])
    engine_id = completed.stdout.strip()
    if not engine_id:
        raise DeploymentKitError("Docker did not report the engine identity.")
    return engine_id


def _run(docker: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [docker, *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Local HTTPS Auth Docker command failed: {detail}")
    return completed


def _inspect(docker: str, resource_type: str, name: str) -> dict[str, Any] | None:
    completed = _run(docker, [resource_type, "inspect", name], check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).lower()
        if "no such" in detail or "not found" in detail:
            return None
        raise DeploymentKitError(
            f"Unable to inspect local {resource_type} resource {name}: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DeploymentKitError(f"Docker returned malformed {resource_type} inspection evidence.") from error
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise DeploymentKitError(f"Docker returned unexpected {resource_type} inspection evidence.")
    return value[0]


def _identity(spec: dict[str, Any]) -> str:
    value = (
        f"{spec['ownerRepo']}|{spec['appSlug']}|{spec['environment']}|"
        f"{spec.get('workspaceIdentity', _workspace_identity())}"
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _resource_names(spec: dict[str, Any]) -> dict[str, str]:
    suffix = _identity(spec)
    return {
        "appContainer": f"pf-local-auth-{suffix}-app",
        "caddyContainer": f"pf-local-auth-{suffix}-caddy",
        "appNetwork": f"pf-local-auth-{suffix}-app",
        "egressNetwork": f"pf-local-auth-{suffix}-egress",
        "ingressNetwork": f"pf-local-auth-{suffix}-ingress",
        "appDataVolume": f"pf-local-auth-{suffix}-data",
        "caddyDataVolume": f"pf-local-auth-{suffix}-caddy-data",
        "caddyConfigVolume": f"pf-local-auth-{suffix}-caddy-config",
    }


def _state_root(spec: dict[str, Any]) -> Path:
    return config_root() / "local-https-auth" / _identity(spec)


def _state_file(spec: dict[str, Any]) -> Path:
    return _state_root(spec) / "deployment.json"


def _root_certificate_file(spec: dict[str, Any]) -> Path:
    return _state_root(spec) / "caddy-root.crt"


def _caddyfile(spec: dict[str, Any]) -> Path:
    return _state_root(spec) / "Caddyfile"


def _load_state(spec: dict[str, Any]) -> dict[str, Any] | None:
    path = _state_file(spec)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read local HTTPS Auth state {path}: {error}") from error
    if (
        not isinstance(value, dict)
        or value.get("schemaVersion") != LOCAL_HTTPS_AUTH_SCHEMA_VERSION
        or value.get("ownerRepo") != spec["ownerRepo"]
        or value.get("appSlug") != spec["appSlug"]
        or value.get("environment") != spec["environment"]
    ):
        raise DeploymentKitError(f"Unsupported or mismatched local HTTPS Auth state: {path}")
    return value


def _safe_state_write(spec: dict[str, Any], state: dict[str, Any]) -> None:
    root = _state_root(spec)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _state_file(spec)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


@contextmanager
def _lifecycle_lock(spec: dict[str, Any], timeout_seconds: float = 10.0):
    root = _state_root(spec)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    host_descriptor = None
    host_path = Path("/run/lock/project-forge-local-https-auth.lock")
    host_flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        host_flags |= os.O_NOFOLLOW
    host_descriptor = os.open(host_path, host_flags, 0o600)
    os.chmod(host_path, 0o600)
    path = root / "lifecycle.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.chmod(path, 0o600)
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(host_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise _LifecycleLockContention(
                        "Another local HTTPS Auth lifecycle operation holds the workspace lock."
                    )
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
            if host_descriptor is not None:
                try:
                    fcntl.flock(host_descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(host_descriptor)


def _owner_labels(spec: dict[str, Any], component: str) -> dict[str, str]:
    return {
        f"{_AUTH_LABEL_PREFIX}.owner-repo": spec["ownerRepo"],
        f"{_AUTH_LABEL_PREFIX}.app-slug": spec["appSlug"],
        f"{_AUTH_LABEL_PREFIX}.environment": spec["environment"],
        f"{_AUTH_LABEL_PREFIX}.component": component,
        f"{_AUTH_LABEL_PREFIX}.placement": "workstation",
    }


def _labels_match(actual: object, expected: dict[str, str]) -> bool:
    return isinstance(actual, dict) and all(actual.get(key) == value for key, value in expected.items())


def _parse_environment(items: dict[str, str] | Iterable[tuple[str, str]]) -> dict[str, str]:
    pairs = items.items() if isinstance(items, dict) else items
    result: dict[str, str] = {}
    for key, value in pairs:
        if not isinstance(key, str) or not key or "=" in key or "\x00" in key:
            raise DeploymentKitError(f"Invalid environment variable name: {key!r}")
        if key in result:
            raise DeploymentKitError(f"Duplicate environment variable: {key}")
        if not isinstance(value, str) or any(character in value for character in ("\x00", "\n", "\r")):
            raise DeploymentKitError(f"Environment variable {key} contains unsupported control characters.")
        result[key] = value
    return result


def _is_inline_secret_environment_key(key: str) -> bool:
    if key == "ProjectForge__Authentication__Google__ClientSecretFile":
        return False
    compact = key.casefold().replace("_", "").replace("-", "")
    suffix = key.rsplit("__", 1)[-1].casefold()
    if suffix in {"clientsecretfile", "googleclientsecretfile"}:
        return False
    if suffix in _INLINE_SECRET_ENVIRONMENT_SUFFIXES:
        return True
    return any(token in compact for token in (
        "accesstoken",
        "apikey",
        "clientsecret",
        "credential",
        "signingkey",
        "encryptionkey",
        "password",
        "privatekey",
        "refreshtoken",
        "secret",
        "token",
    ))


def normalize_local_https_auth_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    image: str,
    runtime_port: int,
    health_path: str,
    run_as: str,
    environment_variables: dict[str, str] | Iterable[tuple[str, str]],
    read_only_mounts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if run_as != _AUTH_UID_GID:
        raise DeploymentKitError("Local Auth Kit containers must run as the reviewed non-root UID/GID 1654:1654.")
    if health_path != _AUTH_HEALTH_PATH:
        raise DeploymentKitError(f"Local Auth readiness must probe the authenticated route {_AUTH_HEALTH_PATH}.")
    supplied = _parse_environment(environment_variables)
    forbidden = _FORBIDDEN_ENVIRONMENT_KEYS.intersection(supplied)
    if forbidden:
        raise DeploymentKitError(
            "Local HTTPS Auth owns these runtime bindings: " + ", ".join(sorted(forbidden)) + "."
        )
    for key in supplied:
        if _is_inline_secret_environment_key(key):
            raise DeploymentKitError(
                f"{key} must not be passed inline; use a Project-owned protected read-only material file."
            )
    client_id = supplied.get("ProjectForge__Authentication__Google__ClientId")
    secret_file = supplied.get("ProjectForge__Authentication__Google__ClientSecretFile")
    if not client_id or not secret_file:
        raise DeploymentKitError(
            "Google ClientId and a protected Google ClientSecretFile path are required for local Auth."
        )
    if secret_file != LOCAL_HTTPS_AUTH_SECRET_FILE or ".." in Path(secret_file).parts:
        raise DeploymentKitError(
            "Google ClientSecretFile must be the exact protected mount /run/secrets/pf-google-client-secret."
        )
    mounts = read_only_mounts or []
    exact_secret_mounts = [
        mount
        for mount in mounts
        if isinstance(mount, dict)
        and mount.get("target") == secret_file
    ]
    if len(exact_secret_mounts) != 1:
        raise DeploymentKitError(
            "Google ClientSecretFile requires one exact read-only file mount at the container path."
        )
    secret_source = Path(exact_secret_mounts[0]["source"])
    if not secret_source.is_file() or secret_source.is_symlink():
        raise DeploymentKitError("Google ClientSecretFile must resolve to a protected regular file.")
    try:
        secret_stat = secret_source.stat()
    except OSError as error:
        raise DeploymentKitError("Cannot inspect the protected Google ClientSecretFile.") from error
    if not stat.S_ISREG(secret_stat.st_mode):
        raise DeploymentKitError("Google ClientSecretFile must be a regular file.")
    if (stat.S_IMODE(secret_stat.st_mode) not in {0o600, 0o640}):
        raise DeploymentKitError("Google ClientSecretFile is broader than owner-only or owner/group 0640 access.")
    if secret_stat.st_uid != os.geteuid() and secret_stat.st_gid != 1654:
        raise DeploymentKitError("Google ClientSecretFile must be owned by the current developer or group 1654.")
    if secret_source.name not in secret_file:
        raise DeploymentKitError("Google ClientSecretFile name must match its exact container mount path.")

    identity = f"{owner_repo}|{app_slug}|{environment}"
    candidate_subnets = _candidate_subnets(identity)
    peer_ip = str(candidate_subnets["app"].network_address + 2)
    supplied.update(
        {
            "ASPNETCORE_URLS": f"http://0.0.0.0:{runtime_port}",
            "ProjectForge__Authentication__DbPath": _AUTH_DB_PATH,
            "ProjectForge__Authentication__DataProtectionKeysPath": _AUTH_KEYS_PATH,
            "ProjectForge__Authentication__PublicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
            "ProjectForge__Authentication__TrustedProxyIp": peer_ip,
        }
    )
    normalized = normalize_workstation_spec(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        container_name=_resource_names(
            {"ownerRepo": owner_repo, "appSlug": app_slug, "environment": environment}
        )["appContainer"],
        image=image,
        runtime_port=runtime_port,
        host_port=LOCAL_HTTPS_AUTH_PORT,
        health_path=health_path,
        run_as=run_as,
        persistence_mode="directory",
        data_container_path="/data",
        environment_variables=supplied,
        read_only_mounts=read_only_mounts or [],
        allow_file_mounts=True,
    )
    if not any(secret_file == mount["target"] for mount in normalized.get("readOnlyMounts", [])):
        raise DeploymentKitError(
            "Google ClientSecretFile must be inside one of the declared read-only material mounts."
        )
    normalized.pop("hostAddress")
    normalized.pop("hostPort")
    normalized["exposure"] = "localhost-https"
    normalized["publicOrigin"] = LOCAL_HTTPS_AUTH_ORIGIN
    normalized["caddyImage"] = CADDY_IMAGE
    normalized["networkSubnets"] = {name: str(value) for name, value in candidate_subnets.items()}
    normalized["caddyPeerIp"] = peer_ip
    normalized["workspaceIdentity"] = _workspace_identity()
    normalized["dockerContext"] = "default"
    normalized["specSha256"] = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return normalized


def _candidate_subnets(identity: str) -> dict[str, ipaddress.IPv4Network]:
    seed = int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8], 16)
    pools = (ipaddress.ip_network("10.240.0.0/12"), ipaddress.ip_network("172.16.0.0/12"))
    for pool in pools:
        count = 1 << (28 - pool.prefixlen)
        first = seed % count
        for offset in range(count):
            index = (first + offset) % count
            start = int(pool.network_address) + (index * 3 * 16)
            candidates = {
                "ingress": ipaddress.ip_network((start, 28)),
                "app": ipaddress.ip_network((start + 16, 28)),
                "egress": ipaddress.ip_network((start + 32, 28)),
            }
            if all(candidate.subnet_of(pool) for candidate in candidates.values()):
                return candidates
    raise DeploymentKitError("Unable to allocate deterministic local HTTPS Auth Docker networks.")


def _available_subnets(docker: str, identity: str) -> dict[str, str]:
    seed = int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8], 16)
    occupied = [*_existing_networks(docker), *_route_networks()]
    for pool in (ipaddress.ip_network("10.240.0.0/12"), ipaddress.ip_network("172.16.0.0/12")):
        if any(route.supernet_of(pool) for route in occupied):
            continue
        count = 1 << (28 - pool.prefixlen)
        first = seed % count
        for offset in range(count):
            index = (first + offset) % count
            start = int(pool.network_address) + (index * 3 * 16)
            candidates = {
                "ingress": ipaddress.ip_network((start, 28)),
                "app": ipaddress.ip_network((start + 16, 28)),
                "egress": ipaddress.ip_network((start + 32, 28)),
            }
            if not all(candidate.subnet_of(pool) for candidate in candidates.values()):
                continue
            if not any(candidate.overlaps(route) for candidate in candidates.values() for route in occupied):
                return {name: str(network) for name, network in candidates.items()}
    raise DeploymentKitError(
        "No non-overlapping private Docker subnets are available for local HTTPS Auth."
    )


def _bind_networks(spec: dict[str, Any], subnets: dict[str, str]) -> None:
    peer_ip = str(ipaddress.ip_network(subnets["app"]).network_address + 2)
    spec["networkSubnets"] = subnets
    spec["caddyPeerIp"] = peer_ip
    spec["environmentVariables"]["ProjectForge__Authentication__TrustedProxyIp"] = peer_ip
    unsigned = {key: value for key, value in spec.items() if key != "specSha256"}
    spec["specSha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _network_names(spec: dict[str, Any]) -> dict[str, str]:
    names = _resource_names(spec)
    return {
        "ingress": names["ingressNetwork"],
        "app": names["appNetwork"],
        "egress": names["egressNetwork"],
    }


def _route_networks() -> list[ipaddress.IPv4Network]:
    executable = shutil.which("ip")
    if not executable:
        raise DeploymentKitError("Cannot verify Docker subnet conflicts: the iproute2 'ip' command is unavailable.")
    completed = subprocess.run(
        [executable, "-j", "route", "show"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError("Cannot inspect workstation network routes" + (f": {detail}" if detail else "."))
    try:
        routes = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DeploymentKitError("Workstation returned malformed IP route evidence.") from error
    result: list[ipaddress.IPv4Network] = []
    for route in routes:
        destination = route.get("dst") if isinstance(route, dict) else None
        if not destination or destination == "default":
            continue
        try:
            network = ipaddress.ip_network(destination, strict=False)
        except ValueError:
            continue
        if isinstance(network, ipaddress.IPv4Network):
            result.append(network)
    return result


def _existing_networks(docker: str) -> list[ipaddress.IPv4Network]:
    listed = _run(docker, ["network", "ls", "--format", "{{.Name}}"])
    result: list[ipaddress.IPv4Network] = []
    for name in (line.strip() for line in listed.stdout.splitlines() if line.strip()):
        network = _inspect(docker, "network", name)
        if network is None:
            continue
        ipam = network.get("IPAM", {}).get("Config", [])
        if ipam is None:
            continue
        if not isinstance(ipam, list):
            raise DeploymentKitError(f"Docker returned malformed IPAM evidence for network {name}.")
        for config in ipam:
            if not isinstance(config, dict) or not config.get("Subnet"):
                continue
            try:
                subnet = ipaddress.ip_network(config["Subnet"], strict=False)
            except ValueError as error:
                raise DeploymentKitError(f"Docker returned invalid subnet evidence for network {name}.") from error
            if isinstance(subnet, ipaddress.IPv4Network):
                result.append(subnet)
    return result


def _assert_subnets_available(
    docker: str, spec: dict[str, Any], subnets: dict[str, str]
) -> None:
    candidates = [ipaddress.ip_network(value) for value in subnets.values()]
    existing = [*_existing_networks(docker), *_route_networks()]
    if any(candidate.overlaps(item) for candidate in candidates for item in existing):
        raise DeploymentKitError(
            "The reviewed local HTTPS Auth Docker subnets overlap an existing Docker network or workstation route; "
            "no alternate origin or network was selected."
        )


def _resource_snapshot(docker: str, spec: dict[str, Any]) -> dict[str, Any]:
    names = _resource_names(spec)
    return {
        "containers": {
            key: _inspect(docker, "container", names[key])
            for key in ("appContainer", "caddyContainer")
        },
        "networks": {
            key: _inspect(docker, "network", names[key])
            for key in ("appNetwork", "egressNetwork", "ingressNetwork")
        },
        "volumes": {
            key: _inspect(docker, "volume", names[key])
            for key in ("appDataVolume", "caddyDataVolume", "caddyConfigVolume")
        },
    }


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    normalized = {
        kind: {
            name: (
                None
                if resource is None
                else {
                    "Id": resource.get("Id"),
                    "Name": resource.get("Name"),
                    "CreatedAt": resource.get("CreatedAt"),
                    "Labels": resource.get("Config", {}).get("Labels")
                    if kind == "containers"
                    else resource.get("Labels"),
                }
            )
            for name, resource in sorted(resources.items())
        }
        for kind, resources in sorted(snapshot.items())
    }
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _port_443_available() -> None:
    executable = shutil.which("ss")
    if not executable:
        raise DeploymentKitError("Local HTTPS Auth requires 'ss' to inspect loopback port availability.")
    listeners = subprocess.run(
        [executable, "-H", "-ltn", f"sport = :{LOCAL_HTTPS_AUTH_PORT}"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if listeners.returncode != 0:
        detail = (listeners.stderr or listeners.stdout).strip()
        raise DeploymentKitError(
            "Unable to inspect local loopback port 443"
            + (f": {detail}" if detail else f" (exit {listeners.returncode}).")
        )
    if listeners.stdout.strip():
        raise DeploymentKitError(
            "A WSL listener already owns port 443; local HTTPS Auth requires the exact localhost:443 origin."
        )
    windows = _powershell(
        "if (Get-NetTCPConnection -State Listen -LocalPort 443 -ErrorAction SilentlyContinue) "
        "{ 'IN_USE' } else { 'FREE' }"
    )
    if windows != "FREE":
        raise DeploymentKitError(
            "Windows already has a listener on port 443; local HTTPS Auth requires the exact localhost:443 origin."
        )


def _require_supported_host() -> None:
    try:
        kernel = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
        os_release = Path("/etc/os-release").read_text(encoding="utf-8").lower()
    except OSError as error:
        raise DeploymentKitError("Local HTTPS Auth currently supports WSL2 Ubuntu only.") from error
    if "microsoft" not in kernel or "wsl2" not in kernel or 'id=ubuntu' not in os_release:
        raise DeploymentKitError("Local HTTPS Auth currently supports WSL2 Ubuntu only.")


def _resource_conflicts(
    snapshot: dict[str, Any], *, allow_data_volume: bool, spec: dict[str, Any], allow_partial: bool = False
) -> None:
    if not allow_partial:
        for kind in ("containers", "networks"):
            existing = [(name, item) for name, item in snapshot[kind].items() if item is not None]
            if existing:
                names = ", ".join(name for name, _ in existing)
                raise DeploymentKitError(
                    f"Local HTTPS Auth resources already exist without a clean active state ({names}); "
                    "inspect local HTTPS Auth status and do not replace them automatically."
                )
    for key, purpose in (
        ("caddyDataVolume", "CA data"),
        ("caddyConfigVolume", "Caddy configuration"),
    ):
        volume = snapshot["volumes"][key]
        if volume is None:
            continue
        if not allow_partial:
            raise DeploymentKitError(
                f"The app-scoped Caddy {purpose} volume already exists without an active state; "
                "inspect local HTTPS Auth status and do not replace it automatically."
            )
    data_volume = snapshot["volumes"]["appDataVolume"]
    if data_volume is not None:
        labels = data_volume.get("Labels")
        if not allow_data_volume or not _labels_match(labels, _owner_labels(spec, "app-data")):
            raise DeploymentKitError(
                "The local HTTPS Auth data volume exists but is not an explicitly retained, owned volume."
            )
        state = _load_state(spec)
        if state and _volume_id(data_volume) != state.get("resourceIds", {}).get("appDataVolume"):
            raise DeploymentKitError(
                "The retained local HTTPS Auth data volume identity changed; refusing to reuse or replace it."
            )
    elif allow_data_volume:
        raise DeploymentKitError(
            "The retained local HTTPS Auth data volume is missing; refusing to create an empty replacement."
        )


def plan_local_https_auth(spec: dict[str, Any]) -> dict[str, Any]:
    _require_supported_host()
    docker = _docker()
    if spec.get("dockerContext") != "default":
        raise DeploymentKitError("The local HTTPS Auth plan is bound to an unsupported Docker context.")
    if spec.get("dockerEngineId") and _docker_engine_identity(docker) != spec["dockerEngineId"]:
        raise DeploymentKitError("The Docker engine changed after planning; create a fresh plan.")
    spec["workspaceIdentity"] = _workspace_identity()
    spec["dockerContext"] = "default"
    spec["dockerEngineId"] = _docker_engine_identity(docker)
    state = _load_state(spec)
    allow_resume = False
    if state and state.get("lifecycle") in {"partial", "blocked"}:
        raise DeploymentKitError(
            "A partial or blocked lifecycle exists; run `local https recover` under its lifecycle lock before planning."
        )
    if state and state.get("lifecycle") == "active":
        _bind_networks(spec, state["appNetworkSubnets"])
        if state.get("specSha256") != spec["specSha256"]:
            raise DeploymentKitError("The active local HTTPS Auth specification changed; refusing resume.")
        status = local_https_auth_status(spec)
        if status["state"] == "ready" and state.get("specSha256") == spec["specSha256"]:
            raise DeploymentKitError("The exact local HTTPS Auth runtime is already ready.")
        allowed_resume_drift = {"caddy-container-not-running", "app-container-not-running"}
        if not set(status.get("drift", [])).issubset(allowed_resume_drift):
            raise DeploymentKitError(
                "An active local HTTPS Auth runtime has drift or a changed specification; "
                "review status and use the exact scoped recovery action."
            )
        allow_resume = True
    if state and state.get("lifecycle") not in {"removed", "partial-clean"} and not allow_resume:
        raise DeploymentKitError(
            "A partial local HTTPS Auth setup exists; inspect status and reconcile it before creating a new plan."
        )
    if allow_resume:
        subnets = state["appNetworkSubnets"]
        _bind_networks(spec, subnets)
    else:
        identity = f"{spec['ownerRepo']}|{spec['appSlug']}|{spec['environment']}"
        subnets = _available_subnets(docker, identity)
        _bind_networks(spec, subnets)
        _port_443_available()
        _assert_subnets_available(docker, spec, subnets)
    snapshot = _resource_snapshot(docker, spec)
    _resource_conflicts(
        snapshot,
        allow_data_volume=bool(
            state and (
                state.get("lifecycle") == "removed"
                or state.get("resourceIds", {}).get("appDataVolume")
            )
        ),
        spec=spec,
        allow_partial=bool(
            allow_resume
            or (state and state.get("lifecycle") in {"partial", "blocked"})
        ),
    )
    material_snapshot = snapshot_material(spec)
    return {
        "schemaVersion": LOCAL_HTTPS_AUTH_SCHEMA_VERSION,
        "action": "deploy-local-https-auth",
        "ownerRepo": spec["ownerRepo"],
        "appSlug": spec["appSlug"],
        "environment": spec["environment"],
        "appContainerName": _resource_names(spec)["appContainer"],
        "caddyContainerName": _resource_names(spec)["caddyContainer"],
        "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
        "hostAddress": "127.0.0.1",
        "hostPort": LOCAL_HTTPS_AUTH_PORT,
        "caddyImage": CADDY_IMAGE,
        "appImage": spec["image"],
        "appNetworkSubnets": subnets,
        "caddyPeerIp": spec["caddyPeerIp"],
        "appRuntimePort": spec["runtimePort"],
        "healthPath": spec["healthPath"],
        "environmentVariableNames": sorted(spec["environmentVariables"]),
        "specSha256": spec["specSha256"],
        "inventorySnapshot": _snapshot_hash(snapshot),
        "materialSnapshot": material_snapshot,
        "spec": spec,
    }


def _base_state(plan: dict[str, Any]) -> dict[str, Any]:
    spec = plan["spec"]
    names = _resource_names(spec)
    return {
        "schemaVersion": LOCAL_HTTPS_AUTH_SCHEMA_VERSION,
        "lifecycle": "provisioning",
        "operationId": uuid.uuid4().hex,
        "operationIntent": "deploy-local-https-auth",
        "journal": [],
        "ownerRepo": spec["ownerRepo"],
        "appSlug": spec["appSlug"],
        "environment": spec["environment"],
        "specSha256": spec["specSha256"],
        "appImage": spec["image"],
        "caddyImage": CADDY_IMAGE,
        "appContainerName": names["appContainer"],
        "caddyContainerName": names["caddyContainer"],
        "appNetworkName": names["appNetwork"],
        "egressNetworkName": names["egressNetwork"],
        "ingressNetworkName": names["ingressNetwork"],
        "appDataVolumeName": names["appDataVolume"],
        "caddyDataVolumeName": names["caddyDataVolume"],
        "caddyConfigVolumeName": names["caddyConfigVolume"],
        "appNetworkSubnets": spec["networkSubnets"],
        "caddyPeerIp": spec["caddyPeerIp"],
        "workspaceIdentity": spec.get("workspaceIdentity"),
        "dockerContext": spec.get("dockerContext"),
        "dockerEngineId": spec.get("dockerEngineId"),
        "materialSnapshot": plan.get("materialSnapshot"),
        "trustOwnership": "uninstalled",
        "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
        "hostAddress": "127.0.0.1",
        "hostPort": LOCAL_HTTPS_AUTH_PORT,
        "runtimePort": spec["runtimePort"],
        "healthPath": spec["healthPath"],
        "environmentVariableNames": sorted(spec["environmentVariables"]),
        "secretFileContainerPath": spec["environmentVariables"][
            "ProjectForge__Authentication__Google__ClientSecretFile"
        ],
        "readOnlyMounts": spec.get("readOnlyMounts", []),
        "dockerReadOnlyMountSources": {},
        "rootCertificatePath": str(_root_certificate_file(spec)),
        "caThumbprint": None,
        "caSha256": None,
        "resourceIds": {},
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def _journal(state: dict[str, Any], stage: str) -> None:
    state.setdefault("journal", []).append(
        {
            "operationId": state.get("operationId"),
            "stage": stage,
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


def _expected_caddyfile_content(spec: dict[str, Any]) -> str:
    app_name = _resource_names(spec)["appContainer"]
    return (
        "localhost {\n"
        "  tls internal\n"
        f"  reverse_proxy {app_name}:{spec['runtimePort']} {{\n"
        "    header_up Host localhost\n"
        "    header_up X-Forwarded-Host localhost\n"
        "    header_up X-Forwarded-Proto https\n"
        "    header_up X-Forwarded-For {remote_host}\n"
        "    header_up X-Real-IP {remote_host}\n"
        "  }\n"
        "}\n"
    )


def _write_caddyfile(spec: dict[str, Any]) -> str:
    path = _caddyfile(spec)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = _expected_caddyfile_content(spec)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise DeploymentKitError("The app-scoped Caddyfile differs from the reviewed local HTTPS Auth plan.")
    else:
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o600)
    return content


def _write_caddyfile_to_volume(docker: str, volume: str, content: str) -> None:
    executable = [docker, "run", "--rm", "-i", "--network", "none",
                  "--mount", f"type=volume,source={volume},target=/etc/caddy",
                  "--entrypoint", "/bin/sh", CADDY_IMAGE,
                  "-c", "cat > /etc/caddy/Caddyfile"]
    completed = subprocess.run(
        executable,
        input=content,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError(
            "Unable to initialize the app-scoped Caddy config volume"
            + (f": {detail}" if detail else ".")
        )


def _docker_labels(labels: dict[str, str]) -> list[str]:
    args: list[str] = []
    for key, value in sorted(labels.items()):
        args.extend(["--label", f"{key}={value}"])
    return args


def _network_labels(spec: dict[str, Any], component: str) -> dict[str, str]:
    return {**_owner_labels(spec, f"network-{component}")}


def _create_network(
    docker: str,
    spec: dict[str, Any],
    *,
    component: str,
    name: str,
    subnet: str,
    internal: bool,
) -> dict[str, Any]:
    gateway = str(ipaddress.ip_network(subnet).network_address + 1)
    args = ["network", "create", "--driver", "bridge", "--subnet", subnet, "--gateway", gateway]
    if internal:
        args.append("--internal")
    args.extend(_docker_labels(_network_labels(spec, component)))
    args.append(name)
    _run(docker, args)
    network = _inspect(docker, "network", name)
    if network is None:
        raise DeploymentKitError(f"Docker did not create the expected local HTTPS Auth network {name}.")
    configs = network.get("IPAM", {}).get("Config", [])
    if (
        len(configs) != 1
        or configs[0].get("Subnet") != subnet
        or configs[0].get("Gateway") != gateway
        or bool(network.get("Internal")) != internal
        or not _labels_match(network.get("Labels"), _network_labels(spec, component))
    ):
        raise DeploymentKitError(f"Docker created local HTTPS Auth network {name} with unexpected IPAM or ownership.")
    return network


def _create_volume(docker: str, spec: dict[str, Any], name: str, component: str) -> dict[str, Any]:
    labels = _owner_labels(spec, component)
    _run(docker, ["volume", "create", *_docker_labels(labels), name])
    volume = _inspect(docker, "volume", name)
    if volume is None or not _labels_match(volume.get("Labels"), labels):
        raise DeploymentKitError(f"Docker did not create the owned local HTTPS Auth volume {name}.")
    return volume


def _volume_id(volume: dict[str, Any]) -> str:
    return str(volume.get("CreatedAt") or volume.get("Mountpoint") or volume.get("Name"))


def _mount_signature(mount: dict[str, Any]) -> tuple[object, ...]:
    mount_type = mount.get("Type")
    return (
        mount_type,
        mount.get("Name") if mount_type == "volume" else None,
        mount.get("Source") if mount_type == "bind" else None,
        mount.get("Destination"),
        mount.get("RW"),
    )


def _docker_read_only_mount_sources(
    app: dict[str, Any], spec: dict[str, Any]
) -> dict[str, str]:
    expected = {mount["target"] for mount in spec.get("readOnlyMounts", [])}
    observed: dict[str, str] = {}
    mounts = app.get("Mounts", [])
    if not isinstance(mounts, list):
        raise DeploymentKitError("Docker returned malformed Auth material mount evidence.")
    for mount in mounts:
        if not isinstance(mount, dict):
            raise DeploymentKitError("Docker returned malformed Auth material mount evidence.")
        target = mount.get("Destination")
        if target not in expected:
            continue
        source = mount.get("Source")
        if (
            mount.get("Type") != "bind"
            or mount.get("RW") is not False
            or not isinstance(source, str)
            or not source
        ):
            raise DeploymentKitError(
                f"Docker did not create the expected read-only material mount at {target}."
            )
        if target in observed:
            raise DeploymentKitError(f"Docker returned duplicate Auth material mounts at {target}.")
        observed[target] = source
    if set(observed) != expected:
        raise DeploymentKitError("Docker omitted one or more reviewed read-only Auth material mounts.")
    return observed


def _container(docker: str, name: str) -> dict[str, Any]:
    value = _inspect(docker, "container", name)
    if value is None:
        raise DeploymentKitError(f"Docker did not create the expected local HTTPS Auth container {name}.")
    return value


def _verify_caddy_peer(docker: str, spec: dict[str, Any], state: dict[str, Any]) -> None:
    names = _resource_names(spec)
    caddy = _container(docker, names["caddyContainer"])
    networks = caddy.get("NetworkSettings", {}).get("Networks", {})
    app_network = networks.get(names["appNetwork"])
    if (
        not isinstance(app_network, dict)
        or app_network.get("IPAddress") != spec["caddyPeerIp"]
        or app_network.get("NetworkID") != state["resourceIds"].get("appNetwork")
    ):
        raise DeploymentKitError("Caddy's exact app-network peer identity changed before app start.")


def _auth_environment(spec: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key, value in sorted(spec["environmentVariables"].items()):
        result.extend(["--env", f"{key}={value}"])
    return result


def _initialize_data_volume(docker: str, spec: dict[str, Any], volume_name: str) -> None:
    uid, gid = spec["runAs"].split(":", 1) if ":" in spec["runAs"] else (spec["runAs"], spec["runAs"])
    command = (
        f"mkdir -p {_AUTH_KEYS_PATH} && "
        f"chown -R {uid}:{gid} /data && chmod 700 /data && "
        f"chown {uid}:{gid} {_AUTH_KEYS_PATH} && chmod 700 {_AUTH_KEYS_PATH}"
    )
    _run(
        docker,
        [
            "run", "--rm", "--network", "none", "--user", "0:0",
            "--mount", f"type=volume,source={volume_name},target=/data",
            "--entrypoint", "/bin/sh", spec["image"], "-c", command,
        ],
    )


def _export_ca_root(docker: str, spec: dict[str, Any], state: dict[str, Any]) -> tuple[str, str]:
    destination = _root_certificate_file(spec)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="pf-local-auth-root-", dir=destination.parent) as temp:
        temporary = Path(temp) / "root.crt"
        _run(
            docker,
            [
                "cp",
                f"{state['caddyContainerName']}:/data/caddy/pki/authorities/local/root.crt",
                str(temporary),
            ],
        )
        try:
            certificate = temporary.read_text(encoding="ascii")
            if certificate.count("-----BEGIN CERTIFICATE-----") != 1 or "PRIVATE KEY" in certificate:
                raise DeploymentKitError("Caddy did not export exactly one public CA root certificate.")
            der = ssl.PEM_cert_to_DER_cert(certificate)
        except (OSError, UnicodeError, ValueError) as error:
            raise DeploymentKitError("Caddy's public CA root certificate is missing or malformed.") from error
        sha256 = hashlib.sha256(der).hexdigest()
        thumbprint = hashlib.sha1(der).hexdigest().upper()
        if destination.exists():
            old_der = ssl.PEM_cert_to_DER_cert(destination.read_text(encoding="ascii"))
            if hashlib.sha256(old_der).hexdigest() != sha256:
                raise DeploymentKitError(
                    "The Caddy CA root changed; trust is stale and requires exact-thumbprint reconciliation."
                )
        else:
            temporary.replace(destination)
            os.chmod(destination, 0o644)
        state["caThumbprint"] = thumbprint
        state["caSha256"] = sha256
        return thumbprint, sha256


def _https_status(spec: dict[str, Any], *, timeout: float = 3.0) -> int | None:
    root = _root_certificate_file(spec)
    try:
        context = ssl.create_default_context(cafile=str(root))
        connection = http.client.HTTPSConnection("localhost", LOCAL_HTTPS_AUTH_PORT, timeout=timeout, context=context)
        try:
            connection.request("GET", spec["healthPath"])
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()
    except (OSError, ssl.SSLError, http.client.HTTPException):
        return None


def _wait_for_https(spec: dict[str, Any], *, timeout_seconds: float = 120.0) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None
    while time.monotonic() < deadline:
        last_status = _https_status(spec)
        if last_status in {200, 401}:
            return last_status
        time.sleep(1)
    raise DeploymentKitError(
        f"Local HTTPS Auth did not become ready through {LOCAL_HTTPS_AUTH_ORIGIN}{spec['healthPath']}; "
        f"last HTTP status was {last_status!r}."
    )


def _resume_active_runtime(docker: str, spec: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    names = _resource_names(spec)
    for key, name_key, component in (
        ("caddyContainer", "caddyContainerName", "caddy"),
        ("appContainer", "appContainerName", "auth-app"),
    ):
        name = state.get(name_key)
        container = _inspect(docker, "container", name) if name else None
        if (
            container is None
            or container.get("Id") != state.get("resourceIds", {}).get(key)
            or not _labels_match(container.get("Config", {}).get("Labels"), _owner_labels(spec, component))
        ):
            raise DeploymentKitError("Refusing resume of an ambiguous or replaced local HTTPS Auth container.")
    caddy_id = state["resourceIds"]["caddyContainer"]
    app_id = state["resourceIds"]["appContainer"]
    caddy = _container(docker, caddy_id)
    if not caddy.get("State", {}).get("Running"):
        _run(docker, ["start", caddy_id])
        caddy = _container(docker, caddy_id)
    caddy_networks = caddy.get("NetworkSettings", {}).get("Networks", {})
    if names["appNetwork"] not in caddy_networks:
        app_network_id = state["resourceIds"].get("appNetwork")
        if not app_network_id:
            raise DeploymentKitError("Refusing resume without the recorded local HTTPS Auth network identity.")
        _run(
            docker,
            ["network", "connect", "--ip", spec["caddyPeerIp"], app_network_id, caddy_id],
        )
    _verify_caddy_peer(docker, spec, state)
    drift, _ = _inspect_status(spec, state)
    if not set(drift).issubset({"app-container-not-running"}):
        raise DeploymentKitError("Local HTTPS Auth identity changed during resume; refusing to start the app.")
    app = _container(docker, app_id)
    if not app.get("State", {}).get("Running"):
        _run(docker, ["start", app_id])
    health_status = _wait_for_https(spec)
    drift, _ = _inspect_status(spec, state)
    if drift:
        raise DeploymentKitError("Local HTTPS Auth identity changed during resume; inspect status before retrying.")
    state["lifecycle"] = "active"
    state["healthStatus"] = health_status
    state["readyAt"] = datetime.now(timezone.utc).isoformat()
    _journal(state, "resumed")
    _safe_state_write(spec, state)
    return {
        "state": "ready",
        "mutated": True,
        "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
        "caddyPeerIp": spec["caddyPeerIp"],
        "caddyImage": CADDY_IMAGE,
        "appContainerId": state["resourceIds"].get("appContainer"),
        "caddyContainerId": state["resourceIds"].get("caddyContainer"),
        "healthStatus": health_status,
        "trustStoreChanged": False,
    }


def _apply_local_https_auth_unlocked(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schemaVersion", "action", "ownerRepo", "appSlug", "environment",
        "appContainerName", "caddyContainerName", "publicOrigin", "hostAddress",
        "hostPort", "caddyImage", "appImage", "appNetworkSubnets", "caddyPeerIp",
        "appRuntimePort", "healthPath", "environmentVariableNames", "specSha256",
        "inventorySnapshot", "materialSnapshot", "spec",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan.get("action") != "deploy-local-https-auth":
        raise DeploymentKitError("Malformed local HTTPS Auth deployment plan.")
    spec = plan["spec"]
    if (
        plan["ownerRepo"] != spec.get("ownerRepo")
        or plan["appSlug"] != spec.get("appSlug")
        or plan["environment"] != spec.get("environment")
        or plan["specSha256"] != spec.get("specSha256")
        or plan["appImage"] != spec.get("image")
        or plan["caddyPeerIp"] != spec.get("caddyPeerIp")
        or plan["caddyImage"] != CADDY_IMAGE
        or plan["publicOrigin"] != LOCAL_HTTPS_AUTH_ORIGIN
        or plan["hostAddress"] != "127.0.0.1"
        or plan["hostPort"] != LOCAL_HTTPS_AUTH_PORT
        or plan["appNetworkSubnets"] != spec.get("networkSubnets")
        or plan["appRuntimePort"] != spec.get("runtimePort")
        or plan["healthPath"] != spec.get("healthPath")
        or plan["environmentVariableNames"] != sorted(spec.get("environmentVariables", {}))
    ):
        raise DeploymentKitError("Local HTTPS Auth plan identity differs from its normalized specification.")
    _require_supported_host()
    docker = _docker()
    if spec.get("dockerContext") != "default":
        raise DeploymentKitError("The local HTTPS Auth plan is bound to an unsupported Docker context.")
    if spec.get("dockerEngineId") and _docker_engine_identity(docker) != spec["dockerEngineId"]:
        raise DeploymentKitError("The Docker engine changed after planning; create a fresh plan.")
    state = _load_state(spec)
    if isinstance(state, dict) and state.get("lifecycle") in {"partial", "blocked"}:
        raise DeploymentKitError(
            "Explicit local HTTPS Auth recovery is required; apply must not clean partial resources implicitly."
        )
    snapshot = _resource_snapshot(docker, spec)
    if _snapshot_hash(snapshot) != plan["inventorySnapshot"]:
        raise DeploymentKitError("Local HTTPS Auth inventory changed after planning; create a fresh plan.")
    state = _load_state(spec)
    if isinstance(state, dict) and state.get("lifecycle") == "active":
        if state.get("specSha256") != spec["specSha256"]:
            raise DeploymentKitError("The active local HTTPS Auth specification changed; refusing resume.")
        drift, _ = _inspect_status(spec, state)
        allowed_resume_drift = {"caddy-container-not-running", "app-container-not-running"}
        if drift and set(drift).issubset(allowed_resume_drift):
            if plan["materialSnapshot"] != snapshot_material(spec):
                raise DeploymentKitError("Local Auth protected material changed after planning; create a fresh plan.")
            return _resume_active_runtime(docker, spec, state)
    previous_lifecycle = state.get("lifecycle") if isinstance(state, dict) else None
    _resource_conflicts(
        snapshot,
        allow_data_volume=bool(
            state and (
                previous_lifecycle == "removed"
                or (
                    previous_lifecycle == "partial-clean"
                    and state.get("resourceIds", {}).get("appDataVolume")
                )
            )
        ),
        spec=spec,
        allow_partial=bool(previous_lifecycle in {"partial", "blocked"}),
    )
    _port_443_available()
    _assert_subnets_available(docker, spec, plan["appNetworkSubnets"])
    if plan["materialSnapshot"] != snapshot_material(spec):
        raise DeploymentKitError("Local Auth read-only material changed after planning; create a fresh plan.")
    _preflight_material(docker, spec)

    previous_state = _load_state(spec)
    if previous_state and previous_state.get("lifecycle") == "removed":
        trust = local_https_auth_trust_status(spec)
        if trust["state"] != "not-installed":
            raise DeploymentKitError(
                "The previous exact CurrentUser CA thumbprint must be removed before recreating local HTTPS Auth."
            )
        old_root = _root_certificate_file(spec)
        if old_root.exists():
            old_thumbprint, old_sha256 = _certificate_thumbprint(old_root)
            if (
                old_thumbprint != previous_state.get("caThumbprint")
                or old_sha256 != previous_state.get("caSha256")
            ):
                raise DeploymentKitError(
                    "The retained public CA file differs from its recorded identity; refusing to replace it."
                )
            old_root.unlink()
    state = _base_state(plan)
    _journal(state, "provisioning-start")
    _safe_state_write(spec, state)
    caddyfile_content = _write_caddyfile(spec)
    names = _resource_names(spec)
    subnets = plan["appNetworkSubnets"]
    ingress = _create_network(
        docker, spec, component="ingress", name=names["ingressNetwork"],
        subnet=subnets["ingress"], internal=False,
    )
    state["resourceIds"]["ingressNetwork"] = ingress["Id"]
    _journal(state, "ingress-network-created")
    _safe_state_write(spec, state)
    private = _create_network(
        docker, spec, component="app", name=names["appNetwork"],
        subnet=subnets["app"], internal=True,
    )
    state["resourceIds"]["appNetwork"] = private["Id"]
    _journal(state, "app-network-created")
    _safe_state_write(spec, state)
    egress = _create_network(
        docker, spec, component="egress", name=names["egressNetwork"],
        subnet=subnets["egress"], internal=False,
    )
    state["resourceIds"]["egressNetwork"] = egress["Id"]
    _journal(state, "egress-network-created")
    _safe_state_write(spec, state)
    app_data = _create_volume(docker, spec, names["appDataVolume"], "app-data")
    state["resourceIds"]["appDataVolume"] = _volume_id(app_data)
    _journal(state, "app-data-volume-created")
    _safe_state_write(spec, state)
    ca_volume = _create_volume(docker, spec, names["caddyDataVolume"], "caddy-data")
    state["resourceIds"]["caddyDataVolume"] = _volume_id(ca_volume)
    _journal(state, "caddy-data-volume-created")
    _safe_state_write(spec, state)
    config_volume = _create_volume(docker, spec, names["caddyConfigVolume"], "caddy-config")
    state["resourceIds"]["caddyConfigVolume"] = _volume_id(config_volume)
    _journal(state, "caddy-config-volume-created")
    _safe_state_write(spec, state)
    _write_caddyfile_to_volume(docker, names["caddyConfigVolume"], caddyfile_content)
    if snapshot["volumes"]["appDataVolume"] is None:
        _initialize_data_volume(docker, spec, names["appDataVolume"])

    caddy_args = [
        "run", "-d", "--name", names["caddyContainer"], "--restart", "no",
        "--network", names["ingressNetwork"],
        "-p", f"127.0.0.1:{LOCAL_HTTPS_AUTH_PORT}:443",
        "--mount", f"type=volume,source={names['caddyDataVolume']},target=/data",
        "--mount", f"type=volume,source={names['caddyConfigVolume']},target=/etc/caddy,readonly",
        *_docker_labels({**_owner_labels(spec, "caddy"), f"{_AUTH_LABEL_PREFIX}.spec-sha256": spec["specSha256"]}),
        CADDY_IMAGE,
    ]
    _run(docker, caddy_args)
    caddy = _container(docker, names["caddyContainer"])
    state["resourceIds"]["caddyContainer"] = caddy["Id"]
    _journal(state, "caddy-container-started")
    _safe_state_write(spec, state)
    _run(
        docker,
        [
            "network", "connect", "--ip", spec["caddyPeerIp"],
            names["appNetwork"], names["caddyContainer"],
        ],
    )
    _verify_caddy_peer(docker, spec, state)

    _run(
        docker,
        [
            "run", "-d", "--name", names["appContainer"], "--restart", "no",
            "--user", spec["runAs"], "--network", names["egressNetwork"],
            "--mount", f"type=volume,source={names['appDataVolume']},target=/data",
            *[
                value
                for mount in spec.get("readOnlyMounts", [])
                for value in (
                    "--mount",
                    f"type=bind,source={mount['source']},target={mount['target']},readonly",
                )
            ],
            *_docker_labels({**_owner_labels(spec, "auth-app"), f"{_AUTH_LABEL_PREFIX}.spec-sha256": spec["specSha256"]}),
            *_auth_environment(spec),
            spec["image"],
        ],
    )
    app = _container(docker, names["appContainer"])
    state["resourceIds"]["appContainer"] = app["Id"]
    state["dockerReadOnlyMountSources"] = _docker_read_only_mount_sources(app, spec)
    _journal(state, "app-container-started")
    _safe_state_write(spec, state)
    _run(docker, ["network", "connect", names["appNetwork"], names["appContainer"]])
    _verify_caddy_peer(docker, spec, state)

    thumbprint, _ = _export_ca_root(docker, spec, state)
    state["resourceIds"]["caddyNetworkPeer"] = spec["caddyPeerIp"]
    _journal(state, "ca-root-exported")
    _safe_state_write(spec, state)
    health_status = _wait_for_https(spec)
    state["lifecycle"] = "active"
    drift, _ = _inspect_status(spec, state)
    if drift:
        state["lifecycle"] = "provisioning"
        state["drift"] = drift
        _safe_state_write(spec, state)
        raise DeploymentKitError(
            "Local HTTPS Auth failed full post-start identity verification; runtime remains recoverable."
        )
    state["lifecycle"] = "active"
    state["healthStatus"] = health_status
    state["readyAt"] = datetime.now(timezone.utc).isoformat()
    _journal(state, "ready")
    _safe_state_write(spec, state)
    return {
        "state": "ready",
        "mutated": True,
        "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
        "caddyPeerIp": spec["caddyPeerIp"],
        "caddyImage": CADDY_IMAGE,
        "appContainerId": app["Id"],
        "caddyContainerId": caddy["Id"],
        "caThumbprint": thumbprint,
        "healthStatus": health_status,
        "trustStoreChanged": False,
    }


def _cleanup_partial_apply(docker: str, spec: dict[str, Any], state: dict[str, Any]) -> None:
    resource_ids = state.get("resourceIds", {})
    for key, name_key, component in (
        ("appContainer", "appContainerName", "auth-app"),
        ("caddyContainer", "caddyContainerName", "caddy"),
    ):
        name = state.get(name_key)
        if not name:
            continue
        container = _inspect(docker, "container", name)
        if container is None:
            continue
        if (
            container.get("Id") != resource_ids.get(key)
            or not _labels_match(container.get("Config", {}).get("Labels"), _owner_labels(spec, component))
        ):
            raise DeploymentKitError(
                f"Refusing partial cleanup of an ambiguous local HTTPS Auth {component} container."
            )
        _run(docker, ["rm", "-f", name])

    for key, name_key, component in (
        ("egressNetwork", "egressNetworkName", "network-egress"),
        ("appNetwork", "appNetworkName", "network-app"),
        ("ingressNetwork", "ingressNetworkName", "network-ingress"),
    ):
        name = state.get(name_key)
        if not name:
            continue
        network = _inspect(docker, "network", name)
        if network is None:
            continue
        if (
            network.get("Id") != resource_ids.get(key)
            or not _labels_match(network.get("Labels"), _network_labels(spec, component.removeprefix("network-")))
            or network.get("Containers")
        ):
            raise DeploymentKitError(
                f"Refusing partial cleanup of an ambiguous local HTTPS Auth network {name}."
            )
        _run(docker, ["network", "rm", name])

    for key, name_key, component in (
        ("caddyDataVolume", "caddyDataVolumeName", "caddy-data"),
        ("caddyConfigVolume", "caddyConfigVolumeName", "caddy-config"),
    ):
        name = state.get(name_key)
        if not name:
            continue
        volume = _inspect(docker, "volume", name)
        if volume is None:
            continue
        if (
            _volume_id(volume) != resource_ids.get(key)
            or not _labels_match(volume.get("Labels"), _owner_labels(spec, component))
        ):
            raise DeploymentKitError(
                f"Refusing partial cleanup of an ambiguous local HTTPS Auth {component} volume."
            )
        _run(docker, ["volume", "rm", name])


def apply_local_https_auth(plan: dict[str, Any]) -> dict[str, Any]:
    spec = plan.get("spec") if isinstance(plan, dict) else None
    if not isinstance(spec, dict):
        return _apply_local_https_auth_unlocked(plan)
    try:
        with _lifecycle_lock(spec):
            try:
                return _apply_local_https_auth_unlocked(plan)
            except (DeploymentKitError, OSError, subprocess.SubprocessError) as error:
                state = _load_state(spec)
                if isinstance(state, dict) and state.get("lifecycle") in {"provisioning", "partial"}:
                    state["lifecycle"] = "blocked"
                    state["cleanup"] = "required"
                    state["cleanupError"] = str(error)
                    _safe_state_write(spec, state)
                raise error
    except _LifecycleLockContention:
        raise


def _certificate_thumbprint(path: Path) -> tuple[str | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="ascii")
        if text.count("-----BEGIN CERTIFICATE-----") != 1 or "PRIVATE KEY" in text:
            return None, None
        der = ssl.PEM_cert_to_DER_cert(text)
    except (OSError, UnicodeError, ValueError):
        return None, None
    return hashlib.sha1(der).hexdigest().upper(), hashlib.sha256(der).hexdigest()


def _powershell(script: str) -> str:
    _require_supported_host()
    executable = shutil.which("powershell.exe")
    if not executable:
        raise DeploymentKitError("Windows PowerShell is unavailable from this WSL2 Ubuntu session.")
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError("Windows CurrentUser certificate operation failed" + (f": {detail}" if detail else "."))
    return completed.stdout.strip()


def _windows_path(path: Path) -> str:
    executable = shutil.which("wslpath")
    if not executable:
        raise DeploymentKitError("wslpath is required to address the public CA root from Windows PowerShell.")
    completed = subprocess.run(
        [executable, "-w", str(path)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = (completed.stderr or completed.stdout).strip()
        raise DeploymentKitError("Cannot resolve the public CA root's Windows path" + (f": {detail}" if detail else "."))
    return completed.stdout.strip().replace("'", "''")


def local_https_auth_trust_status(spec: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(spec)
    if not state:
        return {"state": "not-configured", "mutated": False}
    expected = state.get("caThumbprint")
    observed, sha256 = _certificate_thumbprint(_root_certificate_file(spec))
    if not expected:
        return {
            "state": "stale",
            "certificateState": "missing",
            "expectedThumbprint": None,
            "observedThumbprint": observed,
            "mutated": False,
            "nextAction": "Inspect the exact app-scoped CA volume and state before any trust operation.",
        }
    path = f"Cert:\\CurrentUser\\Root\\{expected}"
    found = _powershell(
        f"$item = Get-Item -LiteralPath '{path}' -ErrorAction SilentlyContinue; "
        "if ($null -eq $item) { 'ABSENT' } else { $item.Thumbprint }"
    )
    certificate_valid = observed == expected and bool(sha256) and sha256 == state.get("caSha256")
    if found.upper() == "ABSENT":
        status = "not-installed"
    elif found.replace(" ", "").upper() == expected:
        status = "trusted" if certificate_valid else "stale-trusted"
    else:
        raise DeploymentKitError("Windows returned an unexpected CurrentUser root thumbprint.")
    return {
        "state": status,
        "certificateState": "valid" if certificate_valid else "stale",
        "thumbprint": expected,
        "observedThumbprint": observed,
        "certificatePath": str(_root_certificate_file(spec)),
        "store": "Windows CurrentUser Root",
        "mutated": False,
    }


def _install_local_https_auth_trust_unlocked(spec: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(spec)
    if not state or state.get("lifecycle") != "active":
        raise DeploymentKitError("A ready local HTTPS Auth runtime is required before installing its CA root.")
    trust = local_https_auth_trust_status(spec)
    if trust["state"] == "trusted":
        raise DeploymentKitError("The exact local HTTPS Auth CA root is already installed.")
    if trust["state"] != "not-installed" or trust.get("certificateState") != "valid":
        raise DeploymentKitError("The local HTTPS Auth CA root is stale; reconcile its exact recorded thumbprint first.")
    path = _windows_path(_root_certificate_file(spec))
    expected = state["caThumbprint"]
    state["trustOwnership"] = "installing"
    _safe_state_write(spec, state)
    imported = _powershell(
        f"$certificate = Import-Certificate -FilePath '{path}' "
        "-CertStoreLocation 'Cert:\\CurrentUser\\Root' -ErrorAction Stop; "
        "$certificate.Thumbprint"
    ).replace(" ", "").upper()
    if imported != expected:
        raise DeploymentKitError(
            "Windows imported a certificate with an unexpected thumbprint; inspect the exact CurrentUser root entry."
        )
    result = local_https_auth_trust_status(spec)
    if result["state"] != "trusted":
        raise DeploymentKitError("The exact local HTTPS Auth root was imported but did not verify in CurrentUser Root.")
    return {**result, "mutated": True}


def _remove_local_https_auth_trust_unlocked(spec: dict[str, Any], thumbprint: str) -> dict[str, Any]:
    state = _load_state(spec)
    if not state or not isinstance(thumbprint, str) or thumbprint.replace(":", "").replace(" ", "").upper() != state.get("caThumbprint"):
        raise DeploymentKitError("Trust removal requires the exact recorded local HTTPS Auth CA thumbprint.")
    if state.get("trustOwnership") not in {"project", "installing"}:
        raise DeploymentKitError("Refusing to remove a preexisting or unowned CurrentUser CA root.")
    exact = state["caThumbprint"]
    path = f"Cert:\\CurrentUser\\Root\\{exact}"
    result = _powershell(
        f"$item = Get-Item -LiteralPath '{path}' -ErrorAction SilentlyContinue; "
        "if ($null -eq $item) { 'ABSENT' } else { "
        "Remove-Item -LiteralPath $item.PSPath -ErrorAction Stop; 'REMOVED' }"
    )
    if result not in {"ABSENT", "REMOVED"}:
        raise DeploymentKitError("Windows returned an unexpected result while removing the exact CA root.")
    verified = _powershell(
        f"if (Test-Path -LiteralPath '{path}') {{ 'PRESENT' }} else {{ 'ABSENT' }}"
    )
    if verified != "ABSENT":
        raise DeploymentKitError("The exact local HTTPS Auth CA thumbprint remains in Windows CurrentUser Root.")
    return {
        "state": "not-installed",
        "thumbprint": exact,
        "store": "Windows CurrentUser Root",
        "mutated": result == "REMOVED",
    }


def install_local_https_auth_trust(spec: dict[str, Any]) -> dict[str, Any]:
    with _lifecycle_lock(spec):
        result = _install_local_https_auth_trust_unlocked(spec)
        state = _load_state(spec)
        if isinstance(state, dict):
            state["trustOwnership"] = "project"
            _safe_state_write(spec, state)
        return result


def remove_local_https_auth_trust(spec: dict[str, Any], thumbprint: str) -> dict[str, Any]:
    with _lifecycle_lock(spec):
        result = _remove_local_https_auth_trust_unlocked(spec, thumbprint)
        state = _load_state(spec)
        if isinstance(state, dict):
            state["trustOwnership"] = "uninstalled"
            _safe_state_write(spec, state)
        return result


def _inspect_status(spec: dict[str, Any], state: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    spec["readOnlyMounts"] = state.get("readOnlyMounts", [])
    try:
        current_material = snapshot_material(spec)
    except DeploymentKitError:
        current_material = None
        drift = ["protected-material-missing-or-unsafe"]
    else:
        drift = []
        if state.get("materialSnapshot") and current_material != state.get("materialSnapshot"):
            drift.append("protected-material-rotated-or-replaced")
    docker = _docker()
    if state.get("dockerEngineId") and _docker_engine_identity(docker) != state["dockerEngineId"]:
        drift.append("docker-engine-or-context-changed")
    names = _resource_names(spec)
    resources = _resource_snapshot(docker, spec)
    # Preserve protected-material findings from the preflight above.
    observed: dict[str, Any] = {}
    if state.get("lifecycle") == "removed":
        for kind in ("containers", "networks"):
            for name, value in resources[kind].items():
                if value is not None:
                    drift.append(f"unexpected-{kind}-{name}")
        if resources["volumes"]["caddyDataVolume"] is not None:
            drift.append("caddy-ca-volume-still-exists")
        if resources["volumes"]["caddyConfigVolume"] is not None:
            drift.append("caddy-config-volume-still-exists")
        data_volume = resources["volumes"]["appDataVolume"]
        if data_volume is None or not _labels_match(data_volume.get("Labels"), _owner_labels(spec, "app-data")):
            drift.append("preserved-app-data-volume-missing-or-unowned")
        elif _volume_id(data_volume) != state.get("resourceIds", {}).get("appDataVolume"):
            drift.append("preserved-app-data-volume-identity-changed")
        return drift, {"resources": "removed", "dataPreserved": not drift}
    if state.get("lifecycle") != "active":
        return [], {"resources": "incomplete", "lifecycle": state.get("lifecycle")}

    caddy = resources["containers"]["caddyContainer"]
    app = resources["containers"]["appContainer"]
    if caddy is None or app is None:
        drift.append("container-missing")
    else:
        caddy_id = caddy.get("Id")
        app_id = app.get("Id")
        observed.update({"caddyContainerId": caddy_id, "appContainerId": app_id})
        caddy_config = caddy.get("Config", {})
        app_config = app.get("Config", {})
        if caddy_id != state.get("resourceIds", {}).get("caddyContainer"):
            drift.append("caddy-container-identity-changed")
        if app_id != state.get("resourceIds", {}).get("appContainer"):
            drift.append("app-container-identity-changed")
        if caddy_config.get("Image") != CADDY_IMAGE or not _labels_match(caddy_config.get("Labels"), _owner_labels(spec, "caddy")):
            drift.append("caddy-image-or-ownership-drift")
        if app_config.get("Image") != spec["image"] or not _labels_match(app_config.get("Labels"), _owner_labels(spec, "auth-app")):
            drift.append("app-image-or-ownership-drift")
        caddy_restart = caddy.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
        app_restart = app.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
        if caddy_restart != "no":
            drift.append("caddy-automatic-restart-policy-drift")
        if app_restart != "no":
            drift.append("app-automatic-restart-policy-drift")
        if not caddy.get("State", {}).get("Running"):
            drift.append("caddy-container-not-running")
        if not app.get("State", {}).get("Running"):
            drift.append("app-container-not-running")
        if app_config.get("User") != _AUTH_UID_GID:
            drift.append("app-user-identity-drift")
        environment = app_config.get("Env", [])
        environment_values: dict[str, str] = {}
        if not isinstance(environment, list):
            drift.append("app-environment-evidence-malformed")
        else:
            for entry in environment:
                if isinstance(entry, str) and "=" in entry:
                    key, value = entry.split("=", 1)
                    environment_values[key] = value
            expected_environment = {
                "ASPNETCORE_URLS": f"http://0.0.0.0:{state['runtimePort']}",
                "ProjectForge__Authentication__DbPath": _AUTH_DB_PATH,
                "ProjectForge__Authentication__DataProtectionKeysPath": _AUTH_KEYS_PATH,
                "ProjectForge__Authentication__PublicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
                "ProjectForge__Authentication__TrustedProxyIp": state["caddyPeerIp"],
                "ProjectForge__Authentication__Google__ClientSecretFile": state["secretFileContainerPath"],
            }
            if any(environment_values.get(key) != value for key, value in expected_environment.items()):
                drift.append("app-auth-environment-drift")
            if not set(state["environmentVariableNames"]).issubset(environment_values):
                drift.append("app-environment-variable-missing")
            if any(_is_inline_secret_environment_key(key) for key in environment_values):
                drift.append("app-inline-secret-environment-present")
        expected_caddy_ports = {"443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "443"}]}
        if caddy.get("HostConfig", {}).get("PortBindings") != expected_caddy_ports:
            drift.append("caddy-loopback-port-binding-drift")
        app_bindings = app.get("HostConfig", {}).get("PortBindings") or {}
        if not isinstance(app_bindings, dict) or any(app_bindings.values()):
            drift.append("app-host-port-published")
        if caddy.get("HostConfig", {}).get("NetworkMode") != names["ingressNetwork"]:
            drift.append("caddy-primary-network-drift")
        if app.get("HostConfig", {}).get("NetworkMode") != names["egressNetwork"]:
            drift.append("app-primary-egress-network-drift")
        caddy_networks = caddy.get("NetworkSettings", {}).get("Networks", {})
        app_networks = app.get("NetworkSettings", {}).get("Networks", {})
        if set(caddy_networks) != {names["ingressNetwork"], names["appNetwork"]}:
            drift.append("caddy-network-membership-drift")
        if set(app_networks) != {names["egressNetwork"], names["appNetwork"]}:
            drift.append("app-network-membership-drift")
        if caddy.get("State", {}).get("Running") and caddy_networks.get(names["appNetwork"], {}).get("IPAddress") != state.get("caddyPeerIp"):
            drift.append("caddy-physical-peer-drift")
        if caddy_networks.get(names["appNetwork"], {}).get("NetworkID") != state.get("resourceIds", {}).get("appNetwork"):
            drift.append("caddy-app-network-identity-drift")
        caddy_mounts = {
            _mount_signature(item)
            for item in caddy.get("Mounts", [])
        }
        app_mounts = {
            _mount_signature(item)
            for item in app.get("Mounts", [])
        }
        expected_caddy_mounts = {
            ("volume", names["caddyDataVolume"], None, "/data", True),
            ("volume", names["caddyConfigVolume"], None, "/etc/caddy", False),
        }
        if caddy_mounts != expected_caddy_mounts:
            drift.append("caddy-volume-or-config-mount-drift")
        if caddy.get("State", {}).get("Running"):
            config = _run(
                docker,
                ["exec", names["caddyContainer"], "cat", "/etc/caddy/Caddyfile"],
                check=False,
            )
            if config.returncode != 0 or config.stdout != _expected_caddyfile_content(spec):
                drift.append("caddy-config-content-drift")
        expected_app_mounts = {
            ("volume", names["appDataVolume"], None, "/data", True),
        }
        source_records = state.get("dockerReadOnlyMountSources", {})
        expected_targets = {item["target"] for item in state.get("readOnlyMounts", [])}
        if (
            not isinstance(source_records, dict)
            or set(source_records) != expected_targets
            or any(not isinstance(source, str) or not source for source in source_records.values())
        ):
            drift.append("app-material-mount-source-identity-drift")
            source_records = {}
        expected_app_mounts.update(
            ("bind", None, source_records[item["target"]], item["target"], False)
            for item in state.get("readOnlyMounts", [])
            if item["target"] in source_records
        )
        if app_mounts != expected_app_mounts:
            drift.append("app-volume-or-read-only-material-mount-drift")

    caddy_member = state.get("resourceIds", {}).get("caddyContainer") if (
        caddy and caddy.get("State", {}).get("Running")
    ) else None
    app_member = state.get("resourceIds", {}).get("appContainer") if (
        app and app.get("State", {}).get("Running")
    ) else None
    expected_members = {
        "ingressNetwork": {caddy_member},
        "appNetwork": {caddy_member, app_member},
        "egressNetwork": {app_member},
    }
    for key, members in expected_members.items():
        network = resources["networks"][key]
        if network is None:
            drift.append(f"network-missing-{key}")
            continue
        observed_id = network.get("Id")
        observed[key] = {"id": observed_id, "members": sorted(
            item.get("Name", "") for item in network.get("Containers", {}).values()
        )}
        if observed_id != state.get("resourceIds", {}).get(key):
            drift.append(f"network-identity-changed-{key}")
        expected_component = {
            "ingressNetwork": "network-ingress",
            "appNetwork": "network-app",
            "egressNetwork": "network-egress",
        }[key]
        if not _labels_match(network.get("Labels"), _owner_labels(spec, expected_component)):
            drift.append(f"network-ownership-drift-{key}")
        actual_ids = set(network.get("Containers", {}))
        if actual_ids != {value for value in members if value}:
            drift.append(f"network-membership-drift-{key}")
        config = network.get("IPAM", {}).get("Config", [])
        expected_subnet = state.get("appNetworkSubnets", {}).get(
            {"ingressNetwork": "ingress", "appNetwork": "app", "egressNetwork": "egress"}[key]
        )
        if not config or config[0].get("Subnet") != expected_subnet:
            drift.append(f"network-subnet-drift-{key}")
        if bool(network.get("Internal")) != (key == "appNetwork"):
            drift.append(f"network-internal-flag-drift-{key}")

    for key, component in (
        ("appDataVolume", "app-data"),
        ("caddyDataVolume", "caddy-data"),
        ("caddyConfigVolume", "caddy-config"),
    ):
        volume = resources["volumes"][key]
        if volume is None:
            drift.append(f"volume-missing-{key}")
            continue
        if not _labels_match(volume.get("Labels"), _owner_labels(spec, component)):
            drift.append(f"volume-ownership-drift-{key}")
        if _volume_id(volume) != state.get("resourceIds", {}).get(key):
            drift.append(f"volume-identity-drift-{key}")

    thumbprint, sha256 = _certificate_thumbprint(_root_certificate_file(spec))
    observed["caThumbprint"] = thumbprint
    if not thumbprint or thumbprint != state.get("caThumbprint") or sha256 != state.get("caSha256"):
        drift.append("caddy-ca-root-missing-or-replaced")
    return drift, observed


def local_https_auth_status(spec: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(spec)
    if not state:
        return {"state": "not-configured", "mutated": False, "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN}
    drift, observed = _inspect_status(spec, state)
    if state.get("lifecycle") == "removed":
        return {
            "state": "removed" if not drift else "drift",
            "mutated": False,
            "dataPreserved": not drift,
            "appDataVolume": state["appDataVolumeName"],
            "drift": drift,
        }
    if state.get("lifecycle") != "active":
        return {
            "state": "incomplete",
            "mutated": False,
            "lifecycle": state.get("lifecycle"),
            "resourceIds": state.get("resourceIds", {}),
            "drift": drift,
        }
    health_status = _https_status(spec) if not drift else None
    return {
        "state": "drift" if drift else ("ready" if health_status in {200, 401} else "not-ready"),
        "mutated": False,
        "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN,
        "caddyPeerIp": state["caddyPeerIp"],
        "hostAddress": "127.0.0.1",
        "hostPort": LOCAL_HTTPS_AUTH_PORT,
        "caddyImage": CADDY_IMAGE,
        "caddyContainerId": observed.get("caddyContainerId"),
        "appContainerId": observed.get("appContainerId"),
        "networkIds": {
            key: observed.get(key, {}).get("id")
            for key in ("ingressNetwork", "appNetwork", "egressNetwork")
        },
        "networkMembers": {
            key: observed.get(key, {}).get("members")
            for key in ("ingressNetwork", "appNetwork", "egressNetwork")
        },
        "caThumbprint": observed.get("caThumbprint"),
        "healthStatus": health_status,
        "trust": local_https_auth_trust_status(spec),
        "drift": drift,
    }


def local_https_auth_status_for_identity(
    *, owner_repo: str, app_slug: str, environment: str
) -> dict[str, Any]:
    identity = {"ownerRepo": owner_repo, "appSlug": app_slug, "environment": environment}
    state = _load_state(identity)
    if not state:
        return {"state": "not-configured", "mutated": False, "publicOrigin": LOCAL_HTTPS_AUTH_ORIGIN}
    spec = {
        **identity,
        "image": state["appImage"],
        "runtimePort": state["runtimePort"],
        "healthPath": state["healthPath"],
        "specSha256": state["specSha256"],
        "networkSubnets": state["appNetworkSubnets"],
        "caddyPeerIp": state["caddyPeerIp"],
        "readOnlyMounts": state.get("readOnlyMounts", []),
    }
    return local_https_auth_status(spec)


def _remove_exact_container(docker: str, spec: dict[str, Any], state: dict[str, Any], key: str) -> None:
    name_key = "appContainerName" if key == "appContainer" else "caddyContainerName"
    container = _inspect(docker, "container", state[name_key])
    if container is None:
        return
    if (
        container.get("Id") != state.get("resourceIds", {}).get(key)
        or not _labels_match(container.get("Config", {}).get("Labels"), _owner_labels(spec, "auth-app" if key == "appContainer" else "caddy"))
    ):
        raise DeploymentKitError(f"Refusing to remove unverified local HTTPS Auth container {state[name_key]}.")
    _run(docker, ["rm", "-f", state[name_key]])


def _remove_local_https_auth_unlocked(spec: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(spec)
    if not state or state.get("lifecycle") != "active":
        raise DeploymentKitError("Only an active, state-backed local HTTPS Auth runtime can be removed.")
    trust = local_https_auth_trust_status(spec)
    if trust["state"] != "not-installed":
        raise DeploymentKitError(
            "Remove the exact CurrentUser CA thumbprint in a separate authorized operation before runtime teardown."
        )
    drift, _ = _inspect_status(spec, state)
    if drift:
        raise DeploymentKitError(
            "Local HTTPS Auth has resource drift; refusing teardown until exact ownership and membership are reconciled."
        )
    docker = _docker()
    _remove_exact_container(docker, spec, state, "appContainer")
    _remove_exact_container(docker, spec, state, "caddyContainer")
    network_names = (
        ("egressNetworkName", "network-egress", "egressNetwork"),
        ("appNetworkName", "network-app", "appNetwork"),
        ("ingressNetworkName", "network-ingress", "ingressNetwork"),
    )
    for key, component, resource_key in network_names:
        name = state[key]
        network = _inspect(docker, "network", name)
        if network is None:
            continue
        if not _labels_match(network.get("Labels"), _network_labels(spec, component.removeprefix("network-"))):
            raise DeploymentKitError(f"Refusing to remove unverified local HTTPS Auth network {name}.")
        if network.get("Id") != state.get("resourceIds", {}).get(resource_key):
            raise DeploymentKitError(f"Refusing to remove replaced local HTTPS Auth network {name}.")
        _run(docker, ["network", "rm", name])
    for key, component in (
        ("caddyDataVolumeName", "caddy-data"),
        ("caddyConfigVolumeName", "caddy-config"),
    ):
        volume = _inspect(docker, "volume", state[key])
        resource_key = "caddyDataVolume" if component == "caddy-data" else "caddyConfigVolume"
        if volume is None:
            continue
        if (
            not _labels_match(volume.get("Labels"), _owner_labels(spec, component))
            or _volume_id(volume) != state.get("resourceIds", {}).get(resource_key)
        ):
            raise DeploymentKitError(f"Refusing to remove an unverified local HTTPS Auth {component} volume.")
        _run(docker, ["volume", "rm", state[key]])
    state["lifecycle"] = "removed"
    state["removedAt"] = datetime.now(timezone.utc).isoformat()
    _safe_state_write(spec, state)
    return {
        "state": "removed",
        "mutated": True,
        "dataPreserved": True,
        "appDataVolume": state["appDataVolumeName"],
        "caTrustChanged": False,
    }


def recover_local_https_auth(spec: dict[str, Any]) -> dict[str, Any]:
    with _lifecycle_lock(spec):
        state = _load_state(spec)
        if not isinstance(state, dict) or state.get("lifecycle") not in {"provisioning", "partial", "blocked"}:
            raise DeploymentKitError("Only provisioning, partial or blocked local HTTPS Auth lifecycles can be recovered.")
        reconstructed = {
            **spec,
            "image": state.get("appImage"),
            "runtimePort": state.get("runtimePort"),
            "healthPath": state.get("healthPath"),
            "specSha256": state.get("specSha256"),
            "networkSubnets": state.get("appNetworkSubnets"),
            "caddyPeerIp": state.get("caddyPeerIp"),
            "readOnlyMounts": state.get("readOnlyMounts", []),
        }
        docker = _docker()
        if (
            state.get("dockerContext") != "default"
            or not state.get("dockerEngineId")
            or _docker_engine_identity(docker) != state["dockerEngineId"]
            or state.get("workspaceIdentity") != _workspace_identity()
        ):
            raise DeploymentKitError("The recorded local HTTPS Auth Docker engine or workspace changed; refusing recovery.")
        app_data_name = state.get("appDataVolumeName")
        app_data = _inspect(docker, "volume", app_data_name) if app_data_name else None
        recorded_id = state.get("resourceIds", {}).get("appDataVolume")
        if app_data is not None:
            if not _labels_match(app_data.get("Labels"), _owner_labels(reconstructed, "app-data")):
                raise DeploymentKitError("The retained app-data volume has ambiguous ownership and is blocked.")
            if not recorded_id or _volume_id(app_data) != recorded_id:
                raise DeploymentKitError("The retained app-data volume identity changed; explicit reconciliation is required.")
        elif recorded_id:
            raise DeploymentKitError("The retained app-data volume is missing; explicit reconciliation is required.")
        root = _root_certificate_file(reconstructed)
        if state.get("caThumbprint"):
            trust = local_https_auth_trust_status(reconstructed)
            if trust["state"] != "not-installed":
                raise DeploymentKitError("Remove the exact CurrentUser CA thumbprint before recovering local HTTPS Auth.")
            if root.exists() and _certificate_thumbprint(root) != (state["caThumbprint"], state.get("caSha256")):
                raise DeploymentKitError("The retained public CA file differs from its recorded identity.")
        elif root.exists():
            raise DeploymentKitError("The public CA root has no recorded identity; explicit reconciliation is required.")
        _cleanup_partial_apply(docker, reconstructed, state)
        if root.exists():
            root.unlink()
        state["lifecycle"] = "partial-clean"
        state["cleanup"] = "completed"
        _safe_state_write(reconstructed, state)
        return {"state": "partial-clean", "mutated": True, "dataPreserved": app_data is not None}


def remove_local_https_auth(spec: dict[str, Any]) -> dict[str, Any]:
    state = _load_state(spec)
    reconstructed = dict(spec)
    if isinstance(state, dict):
        reconstructed.update(
            {
                "ownerRepo": state.get("ownerRepo", spec.get("ownerRepo")),
                "appSlug": state.get("appSlug", spec.get("appSlug")),
                "environment": state.get("environment", spec.get("environment")),
                "image": state.get("appImage"),
                "runtimePort": state.get("runtimePort"),
                "healthPath": state.get("healthPath"),
                "specSha256": state.get("specSha256"),
                "networkSubnets": state.get("appNetworkSubnets"),
                "caddyPeerIp": state.get("caddyPeerIp"),
                "readOnlyMounts": state.get("readOnlyMounts", []),
            }
        )
    with _lifecycle_lock(reconstructed):
        return _remove_local_https_auth_unlocked(reconstructed)


__all__ = [
    "LOCAL_HTTPS_AUTH_DEPLOY_WRITE_PHRASE",
    "LOCAL_HTTPS_AUTH_ORIGIN",
    "LOCAL_HTTPS_AUTH_PORT",
    "LOCAL_HTTPS_AUTH_REMOVE_PHRASE",
    "LOCAL_HTTPS_AUTH_RECOVER_PHRASE",
    "LOCAL_HTTPS_AUTH_TRUST_REMOVE_PHRASE",
    "LOCAL_HTTPS_AUTH_TRUST_WRITE_PHRASE",
    "apply_local_https_auth",
    "install_local_https_auth_trust",
    "local_https_auth_status",
    "local_https_auth_status_for_identity",
    "local_https_auth_trust_status",
    "normalize_local_https_auth_spec",
    "plan_local_https_auth",
    "recover_local_https_auth",
    "remove_local_https_auth",
    "remove_local_https_auth_trust",
]
