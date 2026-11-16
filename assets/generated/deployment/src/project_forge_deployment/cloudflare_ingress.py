"""Optional Cloudflare Tunnel public ingress for remote Project Forge targets.

Cloudflare is an ingress provider, not a deployment transport.  The existing
remote-ssh target and trusted-LAN Caddy route remain authoritative.  This
module owns an optional shared cloudflared runtime plus Project-scoped public
hostname/DNS registrations that forward to those existing Caddy routes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import subprocess
import tempfile
import urllib.parse
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Iterator

from . import cloudflare_api
from .box_platform import platform_status
from .box_platform_assets import CADDY_CONTAINER, NETWORK_NAME, PLATFORM_ROOT
from .cloudflare_ingress_remote import REMOTE_SCRIPT
from .errors import CloudflarePostWriteVerificationError, DeploymentKitError
from .profiles import load_profile
from .route_registry import route_inventory
from .ssh import ssh_args, verify_access

INGRESS_SCHEMA_VERSION = 1
INGRESS_VERSION = "1"
INGRESS_DISTRIBUTION = "cloudflare-remote-managed-tunnel"
CLOUDFLARED_VERSION = "2026.10.4"
CLOUDFLARED_IMAGE = f"cloudflare/cloudflared:{CLOUDFLARED_VERSION}"
HOST_PUBLIC_INGRESS_WRITE_PHRASE = "[HOST PUBLIC INGRESS WRITE]"
PUBLIC_INGRESS_ROUTE_WRITE_PHRASE = "[PUBLIC INGRESS ROUTE WRITE]"
PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE = "[PUBLIC INGRESS ROUTE REMOVE]"
AUTHENTICATED_ORIGIN_MIGRATION_PHRASE = "[CLOUDFLARE AUTHENTICATED ORIGIN MIGRATION]"
AUTHENTICATED_ORIGIN_CHANGE_FREEZE_PHRASE = "[CLOUDFLARE EXTERNAL CHANGE FREEZE]"
CLOUDFLARE_API_TOKEN_ENV = "PROJECT_FORGE_CLOUDFLARE_API_TOKEN"


_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BOOL_STATUS_KEYS = {"markerPresent", "platformReady", "tokenPresent", "containerRunning", "networkAttached", "authenticatedOrigin"}
_STATUS_KEYS = {
    "state", "scope", "markerPresent", "markerSchemaVersion", "markerIngressVersion",
    "markerDistribution", "platformReady", "tokenPresent", "containerRunning",
    "networkAttached", "containerName", "cloudflaredImage", "accountId", "zoneId",
    "zoneName", "tunnelId", "tunnelName", "authenticatedOrigin",
}


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _hostname(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise DeploymentKitError(f"{field} must be a non-empty DNS hostname.")
    normalized = value.lower().rstrip(".")
    labels = normalized.split(".")
    if len(labels) < 2 or any(_LABEL_RE.fullmatch(label) is None for label in labels):
        raise DeploymentKitError(f"Invalid {field}: {normalized}")
    return normalized


def _first_level_public_hostname(value: str, zone_name: str) -> str:
    host = _hostname(value, "public hostname")
    zone = _hostname(zone_name, "Cloudflare zone")
    suffix = "." + zone
    if not host.endswith(suffix):
        raise DeploymentKitError(f"Public hostname {host} must belong to Cloudflare zone {zone}.")
    relative = host[: -len(suffix)]
    if "." in relative or not relative:
        raise DeploymentKitError(
            "The current partial Cloudflare adapter supports one first-level subdomain per application "
            "(for example app.example.com). Deeper names require an explicit certificate/support review."
        )
    return host


def _origin_hostname(value: str) -> str:
    host = _hostname(value, "origin hostname")
    if not host.endswith(".local"):
        raise DeploymentKitError("Cloudflare origin hostname must be an existing trusted-LAN .local route.")
    return host


def tunnel_name_for_scope(scope: str) -> str:
    return f"project-forge-{_slug(scope, 'scope')}"


def build_remote_script(*, tunnel_token: str | None = None) -> str:
    token_b64 = ""
    if tunnel_token is not None:
        if not isinstance(tunnel_token, str) or not tunnel_token.strip():
            raise DeploymentKitError("Cloudflare tunnel token is empty.")
        token_b64 = base64.b64encode(tunnel_token.strip().encode("utf-8")).decode("ascii")
    replacements = {
        "__PLATFORM_ROOT__": PLATFORM_ROOT,
        "__NETWORK_NAME__": NETWORK_NAME,
        "__CADDY_CONTAINER__": CADDY_CONTAINER,
        "__CLOUDFLARED_IMAGE__": CLOUDFLARED_IMAGE,
        "__SCHEMA_VERSION__": str(INGRESS_SCHEMA_VERSION),
        "__INGRESS_VERSION__": INGRESS_VERSION,
        "__DISTRIBUTION__": INGRESS_DISTRIBUTION,
        "__TOKEN_B64__": token_b64,
    }
    script = REMOTE_SCRIPT
    for placeholder, replacement in replacements.items():
        script = script.replace(placeholder, replacement)
    if "__" in script:
        raise DeploymentKitError("Internal Cloudflare ingress script contains an unresolved placeholder.")
    return script


def _parse_status(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in output.splitlines():
        if not raw.strip():
            continue
        if "=" not in raw:
            raise DeploymentKitError(f"Malformed Cloudflare ingress status line: {raw!r}")
        key, value = raw.split("=", 1)
        if key not in _STATUS_KEYS or key in result:
            raise DeploymentKitError(f"Unexpected or duplicate Cloudflare ingress status key: {key!r}")
        if key in _BOOL_STATUS_KEYS:
            if value not in {"true", "false"}:
                raise DeploymentKitError(f"Invalid boolean Cloudflare ingress status value for {key}.")
            result[key] = value == "true"
        else:
            result[key] = value
    missing = _STATUS_KEYS - result.keys()
    if missing:
        raise DeploymentKitError("Cloudflare ingress status omitted keys: " + ", ".join(sorted(missing)))
    return result


def _metadata_tsv(values: dict[str, Any]) -> str:
    return "\t".join(
        str(values[key])
        for key in ("accountId", "zoneId", "zoneName", "tunnelId", "tunnelName")
    )


def _route_spec(
    *,
    owner_repo: str,
    environment: str,
    app_slug: str,
    public_hostname: str,
    origin_hostname: str,
) -> dict[str, Any]:
    owner_repo = _owner_repo(owner_repo)
    environment = _slug(environment, "environment")
    app_slug = _slug(app_slug, "appSlug")
    public_hostname = _hostname(public_hostname, "public hostname")
    if public_hostname.endswith(".local"):
        raise DeploymentKitError("Public hostname must not use the .local suffix.")
    origin_hostname = _origin_hostname(origin_hostname)
    return {
        "schemaVersion": INGRESS_SCHEMA_VERSION,
        "ownerRepo": owner_repo,
        "environment": environment,
        "appSlug": app_slug,
        "routeId": f"{app_slug}--{environment}",
        "publicHostname": public_hostname,
        "originHostname": origin_hostname,
    }


def _route_tsv(spec: dict[str, Any]) -> str:
    return "\t".join(
        str(spec[key])
        for key in (
            "schemaVersion", "ownerRepo", "environment", "appSlug", "routeId",
            "publicHostname", "originHostname",
        )
    )


def _run_remote(
    profile: dict[str, Any],
    address: str,
    action: str,
    *,
    scope: str,
    metadata: dict[str, Any] | None = None,
    spec: dict[str, Any] | None = None,
    expected: dict[str, Any] | str | None = None,
    tunnel_token: str | None = None,
    authenticated_origin: bool = False,
) -> str:
    if action not in {
        "status", "install", "upgrade", "route-inventory",
        "route-register", "route-remove", "route-register-locked", "route-remove-locked",
        "migration-inspect", "migrate-authenticated", "rollback-authenticated",
        "finalize-authenticated", "verify-authenticated",
    }:
        raise DeploymentKitError(f"Unsupported Cloudflare ingress action: {action}")
    args = [action, _slug(scope, "scope")]
    args.append(_metadata_tsv(metadata) if metadata is not None else "")
    args.append(_route_tsv(spec) if spec is not None else "")
    if action in {"route-register", "route-register-locked"}:
        args.append(_route_tsv(expected) if expected is not None else "NONE")
    elif action in {"route-remove", "route-remove-locked"}:
        args.append("")
    elif action in {
        "migration-inspect", "migrate-authenticated", "rollback-authenticated",
        "finalize-authenticated", "verify-authenticated",
    }:
        args.append(str(expected) if expected is not None else "")
    args.append("true" if authenticated_origin else "false")
    remote_command = "sudo -n bash -s -- " + " ".join(shlex.quote(item) for item in args)
    completed = subprocess.run(
        ssh_args(profile, address, command=remote_command),
        input=build_remote_script(tunnel_token=tunnel_token).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote Cloudflare ingress {action} failed: {detail}")
    return stdout


@contextmanager
def route_transaction_lock(name: str, scope: str) -> Iterator[None]:
    """Serialize route mutations and recovery through the target's shared-scope lock."""
    scope = _slug(scope, "scope")
    profile = load_profile(name)
    access = verify_access(profile)
    remote_command = "sudo -n bash -s -- " + " ".join(
        shlex.quote(item) for item in ("route-lock", scope, "", "", "")
    )
    args = ssh_args(profile, access["address"], command=remote_command)
    args[1:1] = ["-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2"]

    with tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_file,
            )
        except OSError as error:
            raise DeploymentKitError(f"Could not start the Cloudflare route transaction lock: {error}") from error
        if process.stdin is None or process.stdout is None:
            process.kill()
            process.wait()
            raise DeploymentKitError("Could not establish the Cloudflare route transaction lock pipes.")
        try:
            process.stdin.write(build_remote_script().encode("utf-8"))
            process.stdin.flush()
            ready = process.stdout.readline()
        except OSError as error:
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise DeploymentKitError(f"Could not establish the Cloudflare route transaction lock: {error}") from error
        if ready != b"LOCKED\n":
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                return_code = process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait()
            stderr_file.seek(0)
            detail = stderr_file.read().decode("utf-8", errors="replace").strip()
            if not detail:
                detail = f"remote lock exited with status {return_code}"
            raise DeploymentKitError(f"Could not acquire the Cloudflare route transaction lock: {detail}")

        body_failed = False
        try:
            yield
        except BaseException:
            body_failed = True
            raise
        finally:
            release_error: OSError | None = None
            try:
                process.stdin.close()
            except OSError as error:
                release_error = error
            timed_out = False
            try:
                return_code = process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                timed_out = True
            if not body_failed and timed_out:
                raise DeploymentKitError("Cloudflare route transaction lock did not release cleanly.")
            if not body_failed and release_error is not None:
                raise DeploymentKitError(
                    f"Could not release the Cloudflare route transaction lock: {release_error}"
                ) from release_error
            if return_code != 0 and not body_failed:
                stderr_file.seek(0)
                detail = stderr_file.read().decode("utf-8", errors="replace").strip()
                raise DeploymentKitError(
                    "Cloudflare route transaction lock exited unsuccessfully"
                    + (f": {detail}" if detail else f" (status {return_code}).")
                )


def cloudflare_ingress_status(name: str, scope: str) -> dict[str, Any]:
    scope = _slug(scope, "scope")
    profile = load_profile(name)
    access = verify_access(profile)
    status = _parse_status(
        _run_remote(profile, access["address"], "status", scope=scope)
    )
    status["targetName"] = name
    status["verifiedAddress"] = access["address"]
    status["mutated"] = False
    return status


def cloudflare_ingress_doctor(name: str, scope: str) -> dict[str, Any]:
    status = cloudflare_ingress_status(name, scope)
    status["nextAction"] = {
        "installable": "configure-cloudflare-ingress",
        "upgrade-required": "upgrade-cloudflare-ingress",
        "drifted": "inspect-cloudflare-ingress-drift",
        "blocked-platform": "prepare-shared-host-platform",
        "incompatible": "manual-cloudflare-ingress-recovery",
        "ready": "none",
    }.get(status["state"], "manual-review")
    return status


def _status_snapshot(status: dict[str, Any]) -> str:
    selected = {key: status[key] for key in sorted(_STATUS_KEYS)}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _config_snapshot(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _reviewed_config_matches(actual: Any, reviewed: Any) -> bool:
    if not isinstance(actual, dict) or not isinstance(reviewed, dict):
        return False
    normalized = deepcopy(actual)
    if "warp-routing" not in reviewed and normalized.get("warp-routing") == {"enabled": False}:
        normalized.pop("warp-routing")
    return normalized == reviewed


def _restore_tunnel_configuration_if_unchanged(
    api_token: str,
    host: dict[str, Any],
    *,
    expected_current: dict[str, Any],
    previous: dict[str, Any],
) -> None:
    current = cloudflare_api.get_tunnel_configuration(
        api_token, host["accountId"], host["tunnelId"]
    )
    if _reviewed_config_matches(current, previous):
        return
    if not _reviewed_config_matches(current, expected_current):
        raise DeploymentKitError(
            "Tunnel configuration rollback was skipped because current provider state changed "
            "after this operation; concurrent changes were preserved."
        )
    try:
        cloudflare_api.update_tunnel_configuration(
            api_token, host["accountId"], host["tunnelId"], previous
        )
    except Exception as write_error:
        try:
            restored = cloudflare_api.get_tunnel_configuration(
                api_token, host["accountId"], host["tunnelId"]
            )
        except Exception as read_error:
            raise DeploymentKitError(
                "Tunnel configuration rollback response was uncertain and current state could "
                f"not be verified: {read_error}"
            ) from write_error
        if not _reviewed_config_matches(restored, previous):
            raise DeploymentKitError(
                "Tunnel configuration rollback failed and current state does not match the "
                f"previous configuration: {write_error}"
            ) from write_error


def _tunnel_summary(tunnel: dict[str, Any] | None) -> dict[str, Any] | None:
    if tunnel is None:
        return None
    return {
        "id": tunnel.get("id"),
        "name": tunnel.get("name"),
        "configSrc": tunnel.get("config_src"),
        "status": tunnel.get("status"),
        "deletedAt": tunnel.get("deleted_at"),
    }


def _empty_tunnel_config(config: dict[str, Any]) -> bool:
    ingress = config.get("ingress")
    return isinstance(ingress, list) and ingress == [{"service": "http_status:404"}]


def plan_cloudflare_ingress(
    name: str,
    *,
    scope: str,
    zone_name: str,
    api_token: str,
    tunnel_name: str | None = None,
    authenticated_origin: bool = False,
) -> dict[str, Any]:
    """Plan creation/adoption of one shared remotely managed Cloudflare tunnel."""
    scope = _slug(scope, "scope")
    if type(authenticated_origin) is not bool:
        raise DeploymentKitError("Authenticated origin must be an explicit boolean opt-in.")
    zone = cloudflare_api.resolve_zone(api_token, zone_name)
    expected_tunnel_name = tunnel_name or tunnel_name_for_scope(scope)
    if not isinstance(expected_tunnel_name, str) or not expected_tunnel_name.strip():
        raise DeploymentKitError("Cloudflare tunnel name must be non-empty.")
    expected_tunnel_name = expected_tunnel_name.strip()

    platform = platform_status(name)
    if platform["state"] != "ready":
        raise DeploymentKitError(
            f"Cloudflare ingress requires a ready shared Project Forge platform; target {name} is {platform['state']}."
        )
    host = cloudflare_ingress_status(name, scope)
    if host["state"] not in {"installable", "upgrade-required", "ready"}:
        raise DeploymentKitError(
            f"Cloudflare ingress cannot be configured while host scope {scope} is {host['state']}."
        )

    tunnel = cloudflare_api.find_tunnel(api_token, zone["accountId"], expected_tunnel_name)
    tunnel_config: dict[str, Any] | None = None
    if tunnel is not None:
        if tunnel.get("config_src") not in {None, "cloudflare"}:
            raise DeploymentKitError("Project Forge supports adoption only of remotely managed Cloudflare tunnels.")
        tunnel_config = cloudflare_api.get_tunnel_configuration(api_token, zone["accountId"], str(tunnel["id"]))

    if host["state"] in {"ready", "upgrade-required"}:
        if bool(host["authenticatedOrigin"]) != authenticated_origin:
            raise DeploymentKitError("Origin authentication mode cannot change on an existing scope; use a new isolated scope.")
        expected = {
            "accountId": zone["accountId"],
            "zoneId": zone["zoneId"],
            "zoneName": zone["zoneName"],
            "tunnelName": expected_tunnel_name,
        }
        for key, value in expected.items():
            if host[key] != value:
                raise DeploymentKitError(
                    f"Host Cloudflare ingress scope {scope} is already bound to different {key}; explicit migration is required."
                )
        if tunnel is None or host["tunnelId"] != str(tunnel.get("id")):
            raise DeploymentKitError("Host Cloudflare tunnel identity no longer matches the provider; refusing implicit replacement.")
        action = "upgrade" if host["state"] == "upgrade-required" else "refresh-token"
    else:
        action = "adopt-and-install" if tunnel is not None else "create-and-install"
        if tunnel_config is not None and not _empty_tunnel_config(tunnel_config):
            raise DeploymentKitError(
                "An existing tunnel with the desired name already has ingress configuration. "
                "Project Forge will not implicitly adopt or overwrite it."
            )

    return {
        "targetName": name,
        "scope": scope,
        "action": action,
        "zone": zone,
        "tunnelName": expected_tunnel_name,
        "existingTunnel": _tunnel_summary(tunnel),
        "existingTunnelConfigSha256": _config_snapshot(tunnel_config) if tunnel_config is not None else None,
        "hostState": host["state"],
        "hostStatusSnapshot": _status_snapshot(host),
        "cloudflaredImage": CLOUDFLARED_IMAGE,
        "authenticatedOrigin": authenticated_origin,
        "requiredAuthorization": HOST_PUBLIC_INGRESS_WRITE_PHRASE,
        "secrets": {
            "apiToken": "workstation-only; not persisted by Deployment Kit",
            "tunnelToken": "written only to the selected host scope through verified SSH",
        },
    }


def _delete_tunnel(api_token: str, account_id: str, tunnel_id: str) -> None:
    cloudflare_api._request(  # package-internal bounded rollback helper
        "DELETE",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel/{urllib.parse.quote(tunnel_id, safe='')}",
        token=api_token,
    )


def apply_cloudflare_ingress(plan: dict[str, Any], *, api_token: str) -> dict[str, Any]:
    """Apply exactly one reviewed shared Cloudflare ingress plan."""
    required = {
        "targetName", "scope", "action", "zone", "tunnelName", "existingTunnel",
        "existingTunnelConfigSha256", "hostState", "hostStatusSnapshot", "cloudflaredImage",
        "requiredAuthorization", "secrets", "authenticatedOrigin",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise DeploymentKitError("Malformed Cloudflare ingress plan.")
    if type(plan["authenticatedOrigin"]) is not bool:
        raise DeploymentKitError("Malformed authenticated-origin plan mode.")
    if plan["cloudflaredImage"] != CLOUDFLARED_IMAGE:
        raise DeploymentKitError("Cloudflare ingress plan uses a different cloudflared image; re-plan with the current package.")

    name = plan["targetName"]
    scope = plan["scope"]
    zone = cloudflare_api.resolve_zone(api_token, plan["zone"]["zoneName"])
    if zone != plan["zone"]:
        raise DeploymentKitError("Cloudflare zone identity changed after planning; create a fresh plan.")
    current_host = cloudflare_ingress_status(name, scope)
    if _status_snapshot(current_host) != plan["hostStatusSnapshot"]:
        raise DeploymentKitError("Host Cloudflare ingress state changed after planning; create a fresh plan.")

    current_tunnel = cloudflare_api.find_tunnel(api_token, zone["accountId"], plan["tunnelName"])
    if _tunnel_summary(current_tunnel) != plan["existingTunnel"]:
        raise DeploymentKitError("Cloudflare tunnel state changed after planning; create a fresh plan.")
    if current_tunnel is not None:
        current_config = cloudflare_api.get_tunnel_configuration(api_token, zone["accountId"], str(current_tunnel["id"]))
        if _config_snapshot(current_config) != plan["existingTunnelConfigSha256"]:
            raise DeploymentKitError("Cloudflare tunnel configuration changed after planning; create a fresh plan.")

    created = False
    tunnel = current_tunnel
    if tunnel is None:
        tunnel = cloudflare_api.create_tunnel(api_token, zone["accountId"], plan["tunnelName"])
        created = True
    tunnel_id = str(tunnel["id"])
    metadata = {
        **zone,
        "tunnelId": tunnel_id,
        "tunnelName": plan["tunnelName"],
    }

    try:
        config = cloudflare_api.get_tunnel_configuration(api_token, zone["accountId"], tunnel_id)
        if not _empty_tunnel_config(config):
            raise DeploymentKitError(
                "Cloudflare tunnel acquired non-empty ingress configuration during apply; refusing overwrite."
            )
        token = cloudflare_api.get_tunnel_token(api_token, zone["accountId"], tunnel_id)
        profile = load_profile(name)
        access = verify_access(profile)
        remote_action = "upgrade" if plan["hostState"] == "upgrade-required" else (
            "upgrade" if plan["hostState"] == "ready" else "install"
        )
        _run_remote(
            profile,
            access["address"],
            remote_action,
            scope=scope,
            metadata=metadata,
            tunnel_token=token,
            authenticated_origin=plan["authenticatedOrigin"],
        )
        final = cloudflare_ingress_status(name, scope)
        if final["state"] != "ready":
            raise DeploymentKitError(f"Cloudflare ingress apply completed but host readiness is {final['state']}.")
        for key in ("accountId", "zoneId", "zoneName", "tunnelId", "tunnelName"):
            if final[key] != str(metadata[key]):
                raise DeploymentKitError(f"Host Cloudflare ingress returned mismatched {key} after apply.")
        final["mutated"] = True
        final["providerTunnel"] = _tunnel_summary(tunnel)
        return final
    except Exception:
        if created:
            try:
                _delete_tunnel(api_token, zone["accountId"], tunnel_id)
            except Exception:
                pass
        raise


def _parse_route_inventory(output: str) -> dict[str, Any]:
    summary: dict[str, str] = {}
    routes: list[dict[str, Any]] = []
    for raw in output.splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        if parts[0] == "SUMMARY":
            if len(parts) != 3 or parts[1] in summary:
                raise DeploymentKitError("Malformed Cloudflare public-route inventory summary.")
            summary[parts[1]] = parts[2]
        elif parts[0] == "ROUTE":
            if len(parts) != 8:
                raise DeploymentKitError("Malformed Cloudflare public-route inventory record.")
            try:
                schema = int(parts[1])
            except ValueError as error:
                raise DeploymentKitError("Malformed Cloudflare public-route schema.") from error
            spec = _route_spec(
                owner_repo=parts[2],
                environment=parts[3],
                app_slug=parts[4],
                public_hostname=parts[6],
                origin_hostname=parts[7],
            )
            if schema != INGRESS_SCHEMA_VERSION or spec["routeId"] != parts[5]:
                raise DeploymentKitError("Cloudflare public-route schema or route ID mismatch.")
            routes.append(spec)
        else:
            raise DeploymentKitError("Unexpected Cloudflare public-route inventory record.")
    if set(summary) != {"scope", "managedRouteCount"}:
        raise DeploymentKitError("Cloudflare public-route inventory omitted summary fields.")
    try:
        count = int(summary["managedRouteCount"])
    except ValueError as error:
        raise DeploymentKitError("Malformed Cloudflare managed route count.") from error
    if count != len(routes):
        raise DeploymentKitError("Cloudflare managed route count does not match inventory.")
    return {"scope": summary["scope"], "managedRoutes": sorted(routes, key=lambda item: item["routeId"])}


def cloudflare_route_inventory(name: str, scope: str) -> dict[str, Any]:
    profile = load_profile(name)
    access = verify_access(profile)
    result = _parse_route_inventory(
        _run_remote(profile, access["address"], "route-inventory", scope=scope)
    )
    result["targetName"] = name
    result["verifiedAddress"] = access["address"]
    result["mutated"] = False
    return result


def _route_inventory_snapshot(value: dict[str, Any]) -> str:
    selected = {"scope": value["scope"], "managedRoutes": value["managedRoutes"]}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _route_inventory_wire_snapshot(value: dict[str, Any]) -> str:
    routes = sorted(value["managedRoutes"], key=lambda item: item["routeId"])
    lines = [
        f"SUMMARY\tscope\t{value['scope']}",
        f"SUMMARY\tmanagedRouteCount\t{len(routes)}",
    ]
    for spec in routes:
        lines.append(
            "ROUTE\t" + "\t".join(
                str(spec[key])
                for key in (
                    "schemaVersion", "ownerRepo", "environment", "appSlug", "routeId",
                    "publicHostname", "originHostname",
                )
            )
        )
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def _find_route(inventory: dict[str, Any], route_id: str) -> dict[str, Any] | None:
    return next((item for item in inventory["managedRoutes"] if item["routeId"] == route_id), None)


def _lan_route(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    inventory = route_inventory(name)
    route = next((item for item in inventory["managedRoutes"] if item["routeId"] == spec["routeId"]), None)
    if route is None:
        raise DeploymentKitError(
            f"Trusted-LAN Caddy route {spec['routeId']} must exist before public ingress can be registered."
        )
    for key in ("ownerRepo", "environment", "appSlug"):
        if route[key] != spec[key]:
            raise DeploymentKitError("Trusted-LAN route ownership does not match the requested public-ingress route.")
    if spec["originHostname"] not in route["hostnames"]:
        raise DeploymentKitError(
            f"Origin hostname {spec['originHostname']} is not owned by trusted-LAN route {spec['routeId']}."
        )
    return route


def _cloudflare_rule(spec: dict[str, Any], *, authenticated_origin: bool = False) -> dict[str, Any]:
    if authenticated_origin:
        return {
            "hostname": spec["publicHostname"],
            "service": "unix:/run/project-forge-origin/origin.sock",
            "originRequest": {"httpHostHeader": spec["publicHostname"]},
        }
    return {
        "hostname": spec["publicHostname"],
        "service": f"http://{CADDY_CONTAINER}:80",
        "originRequest": {"httpHostHeader": spec["originHostname"]},
    }


def _split_ingress(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise DeploymentKitError("Cloudflare tunnel configuration must contain ingress rules.")
    if ingress[-1] != {"service": "http_status:404"}:
        raise DeploymentKitError("Cloudflare tunnel must retain the Project Forge fail-closed final 404 ingress rule.")
    rules = ingress[:-1]
    if any(not isinstance(item, dict) for item in rules):
        raise DeploymentKitError("Cloudflare tunnel contains a malformed ingress rule.")
    return [deepcopy(item) for item in rules], deepcopy(ingress[-1])


def _migration_ingress_config(
    config: dict[str, Any],
    routes: list[dict[str, Any]],
    *,
    host_authenticated: bool,
) -> tuple[dict[str, Any], int]:
    rules, final_rule = _split_ingress(config)
    if not routes:
        raise DeploymentKitError("Authenticated-origin migration requires at least one managed public route.")
    desired_rules = deepcopy(rules)
    seen_route_ids: set[str] = set()
    seen_hostnames: set[str] = set()
    for spec in routes:
        route_id = spec["routeId"]
        hostname = spec["publicHostname"]
        if route_id in seen_route_ids or hostname in seen_hostnames:
            raise DeploymentKitError("Managed public-route identities are ambiguous; migration was not planned.")
        seen_route_ids.add(route_id)
        seen_hostnames.add(hostname)
        legacy = _cloudflare_rule(spec)
        authenticated = _cloudflare_rule(spec, authenticated_origin=True)
        matches = [index for index, rule in enumerate(rules) if rule.get("hostname") == hostname]
        if len(matches) != 1:
            raise DeploymentKitError(
                f"Managed public route {route_id} does not have exactly one provider ingress rule; refusing takeover."
            )
        index = matches[0]
        if rules[index] == legacy:
            desired_rules[index] = authenticated
        elif rules[index] == authenticated and host_authenticated:
            desired_rules[index] = authenticated
        elif rules[index] == authenticated:
            raise DeploymentKitError(
                "Provider ingress is already authenticated while the managed connector is in legacy mode."
            )
        else:
            raise DeploymentKitError(
                f"Provider ingress for managed route {route_id} has conflicting, unowned, or changed fields."
            )
    desired = deepcopy(config)
    desired["ingress"] = desired_rules + [final_rule]
    return desired, sum(left != right for left, right in zip(rules, desired_rules))


def _unmanaged_ingress_summary(
    config: dict[str, Any],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    rules, _ = _split_ingress(config)
    managed_hostnames = {spec["publicHostname"] for spec in routes}
    unmanaged = [rule for rule in rules if rule.get("hostname") not in managed_hostnames]
    return {
        "unmanagedIngressRuleCount": len(unmanaged),
        "unmanagedIngressRulesSha256": _config_snapshot({"rules": unmanaged}),
    }


def _migration_dns_snapshot(
    api_token: str,
    host: dict[str, Any],
    routes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for spec in routes:
        records = cloudflare_api.list_dns_records(
            api_token, host["zoneId"], name=spec["publicHostname"]
        )
        record = _exact_dns_record(records, spec=spec, tunnel_id=host["tunnelId"])
        if record is None or not record.get("id"):
            raise DeploymentKitError(
                f"Managed route {spec['routeId']} has no exact owned DNS record; refusing migration."
            )
        result.append(
            {
                "routeId": spec["routeId"],
                "recordId": str(record["id"]),
                "recordSha256": _config_snapshot(record),
            }
        )
    return result


def _migration_freeze_context(plan: dict[str, Any]) -> str:
    context = {
        "scope": plan["scope"],
        "hostStatusSnapshot": plan["hostStatusSnapshot"],
        "zone": plan["zone"],
        "tunnel": plan["tunnel"],
        "routeInventorySnapshot": plan["routeInventorySnapshot"],
        "dnsSnapshot": plan["dnsSnapshot"],
        "tunnelConfigSha256": plan["tunnelConfigSha256"],
        "desiredTunnelConfigSha256": plan["desiredTunnelConfigSha256"],
    }
    return hashlib.sha256(
        json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _required_change_freeze_acknowledgement(plan: dict[str, Any]) -> str:
    return (
        f"{AUTHENTICATED_ORIGIN_CHANGE_FREEZE_PHRASE} "
        f"scope={plan['scope']} context={_migration_freeze_context(plan)}"
    )


def _required_preplan_change_freeze_acknowledgement(scope: str) -> str:
    return f"{AUTHENTICATED_ORIGIN_CHANGE_FREEZE_PHRASE} ACTIVE scope={scope}"


def _remote_migration_state(name: str, scope: str) -> str:
    profile = load_profile(name)
    access = verify_access(profile)
    output = _run_remote(profile, access["address"], "migration-inspect", scope=scope)
    lines = output.splitlines()
    if len(lines) != 1 or not lines[0].startswith("migrationState="):
        raise DeploymentKitError("Remote authenticated-origin migration state is malformed.")
    state = lines[0].split("=", 1)[1]
    if state not in {"clean", "pending", "complete"}:
        raise DeploymentKitError("Remote authenticated-origin migration state is unsupported.")
    return state


def plan_authenticated_origin_migration(
    name: str,
    *,
    scope: str,
    zone_name: str,
    api_token: str,
    change_freeze_active_acknowledgement: str,
) -> dict[str, Any]:
    """Plan a guarded migration of one existing legacy ingress scope."""
    scope = _slug(scope, "scope")
    if change_freeze_active_acknowledgement != _required_preplan_change_freeze_acknowledgement(scope):
        raise DeploymentKitError(
            "Planning requires an explicit scope-bound acknowledgement that the operator-controlled Cloudflare change freeze is active."
        )
    zone = cloudflare_api.resolve_zone(api_token, zone_name)
    host = cloudflare_ingress_status(name, scope)
    if host["state"] != "ready":
        raise DeploymentKitError(f"Cloudflare ingress scope {scope} is not ready on target {name}.")
    if (
        host["accountId"] != zone["accountId"]
        or host["zoneId"] != zone["zoneId"]
        or host["zoneName"] != zone["zoneName"]
    ):
        raise DeploymentKitError("Cloudflare zone does not match the existing ingress scope binding.")
    tunnel = cloudflare_api.find_tunnel(api_token, zone["accountId"], host["tunnelName"])
    if (
        tunnel is None
        or str(tunnel.get("id")) != host["tunnelId"]
        or tunnel.get("config_src") not in {None, "cloudflare"}
    ):
        raise DeploymentKitError("Existing remotely managed tunnel identity changed; refusing migration.")

    migration_state = _remote_migration_state(name, scope)
    host_authenticated = bool(host["authenticatedOrigin"])
    if host_authenticated and migration_state != "pending":
        raise DeploymentKitError(
            "This scope is already authenticated and has no pending migration receipt; no migration is required."
        )
    if not host_authenticated and migration_state != "clean":
        raise DeploymentKitError(
            "Legacy ingress scope has conflicting or incomplete authenticated-origin migration state."
        )

    inventory = cloudflare_route_inventory(name, scope)
    if inventory["scope"] != scope:
        raise DeploymentKitError("Remote managed-route inventory belongs to a different ingress scope.")
    routes = sorted(inventory["managedRoutes"], key=lambda item: item["routeId"])
    if not routes:
        raise DeploymentKitError("Authenticated-origin migration requires at least one managed public route.")
    for spec in routes:
        _lan_route(name, spec)
    config = cloudflare_api.get_tunnel_configuration(api_token, zone["accountId"], host["tunnelId"])
    desired_config, converted_count = _migration_ingress_config(
        config, routes, host_authenticated=host_authenticated
    )
    if converted_count == 0 and not host_authenticated:
        raise DeploymentKitError("No legacy managed route rules were found to migrate.")
    dns_snapshot = _migration_dns_snapshot(api_token, host, routes)
    unmanaged_summary = _unmanaged_ingress_summary(config, routes)
    return {
        "targetName": name,
        "scope": scope,
        "action": "resume" if migration_state == "pending" else "prepare",
        "migrationState": migration_state,
        "hostStatusSnapshot": _status_snapshot(host),
        "zone": zone,
        "tunnel": _tunnel_summary(tunnel),
        "routeInventorySnapshot": _route_inventory_snapshot(inventory),
        "routeInventoryWireSnapshot": _route_inventory_wire_snapshot(inventory),
        "managedRoutes": routes,
        "dnsSnapshot": dns_snapshot,
        "tunnelConfigSha256": _config_snapshot(config),
        "desiredTunnelConfigSha256": _config_snapshot(desired_config),
        "convertedRouteCount": converted_count,
        **unmanaged_summary,
        "requiredAuthorization": AUTHENTICATED_ORIGIN_MIGRATION_PHRASE,
        "requiredPrePlanChangeFreezeAcknowledgement":
            _required_preplan_change_freeze_acknowledgement(scope),
        "changeFreezePrerequisite": (
            "Operator has stopped all Cloudflare dashboard/API tunnel-configuration writers for this scope "
            "before planning and will keep them stopped through apply, verification, rollback, or recovery. "
            "Deployment Kit cannot enforce or prove this external change freeze."
        ),
        "requiredChangeFreezeAcknowledgement": _required_change_freeze_acknowledgement({
            "scope": scope,
            "hostStatusSnapshot": _status_snapshot(host),
            "zone": zone,
            "tunnel": _tunnel_summary(tunnel),
            "routeInventorySnapshot": _route_inventory_snapshot(inventory),
            "dnsSnapshot": dns_snapshot,
            "tunnelConfigSha256": _config_snapshot(config),
            "desiredTunnelConfigSha256": _config_snapshot(desired_config),
        }),
        "secrets": {
            "apiToken": "workstation-only; not persisted by Deployment Kit",
            "tunnelToken": "existing tunnel token is unchanged and never displayed",
            "providerConfiguration": "not included in this migration plan",
        },
    }


def _migration_remote_action(
    name: str,
    scope: str,
    action: str,
    *,
    zone: dict[str, Any],
    tunnel: dict[str, Any],
    route_snapshot: str,
    authenticated_origin: bool = True,
) -> str:
    profile = load_profile(name)
    access = verify_access(profile)
    return _run_remote(
        profile,
        access["address"],
        action,
        scope=scope,
        metadata={
            **zone,
            "tunnelId": str(tunnel["id"]),
            "tunnelName": str(tunnel["name"]),
        },
        expected=route_snapshot,
        authenticated_origin=authenticated_origin,
    )


def _rollback_prepared_migration(
    name: str,
    scope: str,
    *,
    zone: dict[str, Any],
    tunnel: dict[str, Any],
    route_snapshot: str,
) -> None:
    _migration_remote_action(
        name,
        scope,
        "rollback-authenticated",
        zone=zone,
        tunnel=tunnel,
        route_snapshot=route_snapshot,
    )
    restored_host = cloudflare_ingress_status(name, scope)
    if restored_host["state"] != "ready" or restored_host["authenticatedOrigin"]:
        raise DeploymentKitError("Legacy host rollback did not restore a ready unauthenticated scope.")


def _parse_migration_proof(output: str, expected_route_count: int) -> dict[str, Any]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            raise DeploymentKitError("Authenticated-origin final proof was malformed.")
        key, value = line.split("=", 1)
        if key in result:
            raise DeploymentKitError("Authenticated-origin final proof contained duplicate fields.")
        result[key] = value
    expected = {
        "evidenceLevel": "structural-only",
        "connectorOriginMount": "read-only",
        "socketMetadataVerified": "true",
        "caddyConfigValidated": "true",
        "sanitizedRouteConfigVerified": "true",
        "managedRouteCount": str(expected_route_count),
    }
    if result != expected:
        raise DeploymentKitError("Authenticated-origin structural checks did not match the reviewed contract.")
    return {
        "evidenceLevel": "structural-only",
        "connectorOriginMountReadOnly": True,
        "socketMetadataVerified": True,
        "caddyConfigValidated": True,
        "sanitizedRouteConfigVerified": True,
        "managedRouteCount": expected_route_count,
        "liveSocketForwardingVerified": False,
    }


def apply_authenticated_origin_migration(
    plan: dict[str, Any],
    *,
    api_token: str,
    change_freeze_acknowledgement: str,
    _lock_held: bool = False,
) -> dict[str, Any]:
    """Apply one reviewed existing-scope mode migration without replacing identities."""
    required = {
        "targetName", "scope", "action", "migrationState", "hostStatusSnapshot",
        "zone", "tunnel", "routeInventorySnapshot", "routeInventoryWireSnapshot",
        "managedRoutes", "dnsSnapshot", "tunnelConfigSha256",
        "desiredTunnelConfigSha256", "convertedRouteCount", "unmanagedIngressRuleCount",
        "unmanagedIngressRulesSha256", "requiredAuthorization",
        "changeFreezePrerequisite", "requiredChangeFreezeAcknowledgement", "secrets",
        "requiredPrePlanChangeFreezeAcknowledgement",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise DeploymentKitError("Malformed authenticated-origin migration plan.")
    if (
        plan["requiredAuthorization"] != AUTHENTICATED_ORIGIN_MIGRATION_PHRASE
        or plan["action"] not in {"prepare", "resume"}
        or plan["migrationState"] not in {"clean", "pending"}
        or type(plan["convertedRouteCount"]) is not int
        or not isinstance(plan["managedRoutes"], list)
        or not plan["managedRoutes"]
    ):
        raise DeploymentKitError("Malformed authenticated-origin migration authorization or route plan.")
    if (
        plan["requiredChangeFreezeAcknowledgement"]
        != _required_change_freeze_acknowledgement(plan)
        or plan["requiredPrePlanChangeFreezeAcknowledgement"]
        != _required_preplan_change_freeze_acknowledgement(plan["scope"])
        or change_freeze_acknowledgement != plan["requiredChangeFreezeAcknowledgement"]
    ):
        raise DeploymentKitError(
            "The required scope- and context-bound Cloudflare change-freeze acknowledgement is missing or invalid."
        )
    if not _lock_held:
        with route_transaction_lock(plan["targetName"], plan["scope"]):
            return apply_authenticated_origin_migration(
                plan,
                api_token=api_token,
                change_freeze_acknowledgement=change_freeze_acknowledgement,
                _lock_held=True,
            )

    name, scope = plan["targetName"], _slug(plan["scope"], "scope")
    zone = cloudflare_api.resolve_zone(api_token, plan["zone"]["zoneName"])
    if zone != plan["zone"]:
        raise DeploymentKitError("Cloudflare zone identity changed after migration planning; create a fresh plan.")
    host = cloudflare_ingress_status(name, scope)
    if _status_snapshot(host) != plan["hostStatusSnapshot"]:
        raise DeploymentKitError("Host Cloudflare ingress state changed after migration planning.")
    if host["state"] != "ready" or host["authenticatedOrigin"] != (plan["migrationState"] == "pending"):
        raise DeploymentKitError("Host mode no longer matches the reviewed migration phase.")
    migration_state = _remote_migration_state(name, scope)
    if migration_state != plan["migrationState"]:
        raise DeploymentKitError("Host migration receipt changed after planning; create a fresh plan.")

    tunnel_value = cloudflare_api.find_tunnel(api_token, zone["accountId"], host["tunnelName"])
    if (
        _tunnel_summary(tunnel_value) != plan["tunnel"]
        or tunnel_value is None
        or str(tunnel_value.get("id")) != host["tunnelId"]
        or tunnel_value.get("config_src") not in {None, "cloudflare"}
    ):
        raise DeploymentKitError("Existing Cloudflare tunnel identity changed after migration planning.")
    tunnel = {"id": host["tunnelId"], "name": host["tunnelName"]}

    inventory = cloudflare_route_inventory(name, scope)
    if (
        _route_inventory_snapshot(inventory) != plan["routeInventorySnapshot"]
        or _route_inventory_wire_snapshot(inventory) != plan["routeInventoryWireSnapshot"]
        or sorted(inventory["managedRoutes"], key=lambda item: item["routeId"]) != plan["managedRoutes"]
    ):
        raise DeploymentKitError("Managed public-route ownership changed after migration planning.")
    for spec in plan["managedRoutes"]:
        _lan_route(name, spec)

    config = cloudflare_api.get_tunnel_configuration(api_token, zone["accountId"], host["tunnelId"])
    if _config_snapshot(config) != plan["tunnelConfigSha256"]:
        raise DeploymentKitError("Cloudflare tunnel configuration changed after migration planning.")
    desired_config, converted_count = _migration_ingress_config(
        config, plan["managedRoutes"], host_authenticated=host["authenticatedOrigin"]
    )
    unmanaged_summary = _unmanaged_ingress_summary(config, plan["managedRoutes"])
    if (
        _config_snapshot(desired_config) != plan["desiredTunnelConfigSha256"]
        or converted_count != plan["convertedRouteCount"]
        or unmanaged_summary["unmanagedIngressRuleCount"] != plan["unmanagedIngressRuleCount"]
        or unmanaged_summary["unmanagedIngressRulesSha256"] != plan["unmanagedIngressRulesSha256"]
    ):
        raise DeploymentKitError("Managed ingress rule ownership no longer matches the reviewed migration.")
    dns_snapshot = _migration_dns_snapshot(api_token, host, plan["managedRoutes"])
    if dns_snapshot != plan["dnsSnapshot"]:
        raise DeploymentKitError("Cloudflare DNS ownership or record identities changed after planning.")

    host_prepared_by_this_apply = plan["migrationState"] == "clean"
    if host_prepared_by_this_apply:
        _migration_remote_action(
            name,
            scope,
            "migrate-authenticated",
            zone=zone,
            tunnel=tunnel,
            route_snapshot=plan["routeInventoryWireSnapshot"],
        )
        prepared_host = cloudflare_ingress_status(name, scope)
        prepared_inventory = cloudflare_route_inventory(name, scope)
        if (
            prepared_host["state"] != "ready"
            or not prepared_host["authenticatedOrigin"]
            or _route_inventory_snapshot(prepared_inventory) != plan["routeInventorySnapshot"]
            or _remote_migration_state(name, scope) != "pending"
        ):
            raise DeploymentKitError(
                "Authenticated-origin host preparation failed verification; provider ingress was not changed."
            )

    prewrite_host = cloudflare_ingress_status(name, scope)
    prewrite_inventory = cloudflare_route_inventory(name, scope)
    prewrite_tunnel = cloudflare_api.find_tunnel(api_token, zone["accountId"], host["tunnelName"])
    if (
        prewrite_host["state"] != "ready"
        or not prewrite_host["authenticatedOrigin"]
        or prewrite_host["tunnelId"] != host["tunnelId"]
        or prewrite_host["tunnelName"] != host["tunnelName"]
        or _route_inventory_snapshot(prewrite_inventory) != plan["routeInventorySnapshot"]
        or _tunnel_summary(prewrite_tunnel) != plan["tunnel"]
        or _migration_dns_snapshot(api_token, prewrite_host, plan["managedRoutes"]) != plan["dnsSnapshot"]
        or _remote_migration_state(name, scope) != "pending"
    ):
        raise DeploymentKitError(
            "Host, tunnel, managed-route, DNS, or recovery evidence changed before provider apply; "
            "the authenticated host phase was retained."
        )
    prewrite_config = cloudflare_api.get_tunnel_configuration(
        api_token, zone["accountId"], host["tunnelId"]
    )
    if _reviewed_config_matches(prewrite_config, desired_config):
        desired_already_applied = True
    elif _config_snapshot(prewrite_config) != plan["tunnelConfigSha256"]:
        raise DeploymentKitError(
            "Cloudflare tunnel configuration changed during host preparation; "
            "provider state was preserved and the authenticated host phase was retained."
        )
    else:
        desired_already_applied = False

    # Cloudflare exposes a whole-configuration PUT without compare-and-swap.
    # The operator's external-writer freeze is the concurrency prerequisite;
    # these reads detect stale evidence but cannot enforce that freeze.
    if not desired_already_applied:
        try:
            cloudflare_api.update_tunnel_configuration(
                api_token, zone["accountId"], host["tunnelId"], desired_config
            )
        except Exception as write_error:
            try:
                after_error = cloudflare_api.get_tunnel_configuration(
                    api_token, zone["accountId"], host["tunnelId"]
                )
            except Exception:
                raise DeploymentKitError(
                    "Provider migration response is uncertain. The authenticated host phase and recovery receipt "
                    "were retained; inspect Cloudflare state and re-plan before retrying."
                ) from write_error
            if _reviewed_config_matches(after_error, prewrite_config):
                if host_prepared_by_this_apply:
                    try:
                        _rollback_prepared_migration(
                            name, scope, zone=zone, tunnel=tunnel,
                            route_snapshot=plan["routeInventoryWireSnapshot"],
                        )
                    except Exception as rollback_error:
                        raise DeploymentKitError(
                            "Provider state is unchanged, but authenticated host rollback did not complete. "
                            "The migration receipt was retained for safe recovery."
                        ) from rollback_error
                raise DeploymentKitError(
                    "Cloudflare provider update failed before changing the reviewed configuration; "
                    "the operation was rolled back or remains safely resumable."
                ) from write_error
            if not _reviewed_config_matches(after_error, desired_config):
                raise DeploymentKitError(
                    "Provider migration response is uncertain and current configuration differs from both "
                    "reviewed states. The authenticated host phase was retained; no rollback overwrote provider state."
                ) from write_error

    final_config = cloudflare_api.get_tunnel_configuration(
        api_token, zone["accountId"], host["tunnelId"]
    )
    if not _reviewed_config_matches(final_config, desired_config):
        raise DeploymentKitError(
            "Provider migration did not produce the exact reviewed authenticated rules; "
            "the host recovery receipt was retained."
        )
    final_host = cloudflare_ingress_status(name, scope)
    final_inventory = cloudflare_route_inventory(name, scope)
    final_dns_snapshot = _migration_dns_snapshot(api_token, final_host, plan["managedRoutes"])
    if (
        final_host["state"] != "ready"
        or not final_host["authenticatedOrigin"]
        or final_host["tunnelId"] != host["tunnelId"]
        or final_host["tunnelName"] != host["tunnelName"]
        or _route_inventory_snapshot(final_inventory) != plan["routeInventorySnapshot"]
        or final_dns_snapshot != plan["dnsSnapshot"]
    ):
        raise DeploymentKitError(
            "Final migration state changed or did not preserve the reviewed tunnel, routes, or DNS identities; "
            "host recovery evidence was retained."
        )
    proof_output = _migration_remote_action(
        name,
        scope,
        "verify-authenticated",
        zone=zone,
        tunnel=tunnel,
        route_snapshot=plan["routeInventoryWireSnapshot"],
    )
    proof = _parse_migration_proof(proof_output, len(plan["managedRoutes"]))

    _migration_remote_action(
        name,
        scope,
        "finalize-authenticated",
        zone=zone,
        tunnel=tunnel,
        route_snapshot=plan["routeInventoryWireSnapshot"],
    )
    if _remote_migration_state(name, scope) != "complete":
        raise DeploymentKitError(
            "Migration is verified but the host recovery receipt could not be finalized; inspect before retrying."
        )
    post_finalize_host = cloudflare_ingress_status(name, scope)
    if (
        post_finalize_host["state"] != "ready"
        or not post_finalize_host["authenticatedOrigin"]
        or post_finalize_host["tunnelId"] != host["tunnelId"]
    ):
        raise DeploymentKitError("Final host status changed after migration finalization.")
    return {
        "targetName": name,
        "scope": scope,
        "tunnelId": host["tunnelId"],
        "tunnelName": host["tunnelName"],
        "authenticatedOrigin": True,
        "managedRoutes": [
            {"routeId": spec["routeId"], "publicHostname": spec["publicHostname"]}
            for spec in plan["managedRoutes"]
        ],
        "preservedDnsRecordIds": [
            {"routeId": item["routeId"], "recordId": item["recordId"]}
            for item in plan["dnsSnapshot"]
        ],
        "structuralEvidence": proof,
        "liveSocketForwardingVerified": False,
        "endToEndReadiness": "unproven",
        "requiredAuthorization": AUTHENTICATED_ORIGIN_MIGRATION_PHRASE,
        "mutated": True,
    }


def _dns_marker(spec: dict[str, Any]) -> str:
    identity = "|".join((spec["ownerRepo"], spec["environment"], spec["appSlug"])).encode("utf-8")
    return "Project Forge " + hashlib.sha256(identity).hexdigest()[:20]


def _exact_dns_record(records: list[dict[str, Any]], *, spec: dict[str, Any], tunnel_id: str) -> dict[str, Any] | None:
    if not records:
        return None
    if len(records) != 1:
        raise DeploymentKitError(f"Public hostname {spec['publicHostname']} has multiple Cloudflare DNS records; refusing takeover.")
    record = records[0]
    expected_content = f"{tunnel_id}.cfargotunnel.com"
    if (
        record.get("type") != "CNAME"
        or str(record.get("content", "")).lower().rstrip(".") != expected_content
        or record.get("proxied") is not True
        or record.get("comment") != _dns_marker(spec)
    ):
        raise DeploymentKitError(
            f"Public hostname {spec['publicHostname']} already has DNS state not owned by this Project Forge route."
        )
    return record


def _read_public_route_dns(
    api_token: str,
    host: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any] | None:
    records = cloudflare_api.list_dns_records(
        api_token, host["zoneId"], name=spec["publicHostname"]
    )
    return _exact_dns_record(records, spec=spec, tunnel_id=host["tunnelId"])


def _reconcile_public_route_dns(
    api_token: str,
    host: dict[str, Any],
    spec: dict[str, Any],
    *,
    should_exist: bool,
) -> None:
    current = _read_public_route_dns(api_token, host, spec)
    if should_exist:
        if current is not None:
            return
        try:
            cloudflare_api.create_dns_cname(
                api_token,
                host["zoneId"],
                name=spec["publicHostname"],
                content=f"{host['tunnelId']}.cfargotunnel.com",
                comment=_dns_marker(spec),
            )
        except Exception as write_error:
            try:
                created = _read_public_route_dns(api_token, host, spec)
            except Exception as read_error:
                raise DeploymentKitError(
                    "DNS restoration response was uncertain and current state could not be "
                    f"verified: {read_error}"
                ) from write_error
            if created is None:
                raise
        return

    if current is None:
        return
    try:
        cloudflare_api.delete_dns_record(api_token, host["zoneId"], str(current["id"]))
    except Exception as write_error:
        try:
            remaining = _read_public_route_dns(api_token, host, spec)
        except Exception as read_error:
            raise DeploymentKitError(
                "DNS cleanup response was uncertain and current state could not be "
                f"verified: {read_error}"
            ) from write_error
        if remaining is not None:
            raise
        return
    if _read_public_route_dns(api_token, host, spec) is not None:
        raise DeploymentKitError("Owned Cloudflare DNS record remained after cleanup.")


def plan_public_route(
    name: str,
    *,
    scope: str,
    owner_repo: str,
    environment: str,
    app_slug: str,
    public_hostname: str,
    origin_hostname: str,
    api_token: str,
) -> dict[str, Any]:
    host = cloudflare_ingress_status(name, scope)
    if host["state"] != "ready":
        raise DeploymentKitError(f"Cloudflare ingress scope {scope} is not ready on target {name}.")
    public_hostname = _first_level_public_hostname(public_hostname, host["zoneName"])
    spec = _route_spec(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        public_hostname=public_hostname,
        origin_hostname=origin_hostname,
    )
    _lan_route(name, spec)

    inventory = cloudflare_route_inventory(name, scope)
    existing = _find_route(inventory, spec["routeId"])
    if existing is not None and existing != spec:
        raise DeploymentKitError(
            "This Project/environment already owns a different public-ingress route. Remove it explicitly before rebinding."
        )
    for other in inventory["managedRoutes"]:
        if other["routeId"] != spec["routeId"] and other["publicHostname"] == spec["publicHostname"]:
            raise DeploymentKitError("Public hostname is already owned by another Project Forge route on this ingress scope.")

    config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
    rules, final_rule = _split_ingress(config)
    desired_rule = _cloudflare_rule(spec, authenticated_origin=host["authenticatedOrigin"])
    conflicting = [item for item in rules if item.get("hostname") == spec["publicHostname"] and item != desired_rule]
    if conflicting:
        raise DeploymentKitError("Cloudflare tunnel already has a conflicting ingress rule for this hostname.")
    exact_rules = [item for item in rules if item == desired_rule]
    if len(exact_rules) > 1:
        raise DeploymentKitError("Cloudflare tunnel contains duplicate exact Project Forge ingress rules.")

    records = cloudflare_api.list_dns_records(api_token, host["zoneId"], name=spec["publicHostname"])
    dns = _exact_dns_record(records, spec=spec, tunnel_id=host["tunnelId"])
    return {
        "targetName": name,
        "scope": scope,
        "action": "already-configured" if existing == spec and exact_rules and dns is not None else "register",
        "route": spec,
        "previousRoute": existing,
        "routeInventorySnapshot": _route_inventory_snapshot(inventory),
        "hostStatusSnapshot": _status_snapshot(host),
        "tunnelConfig": config,
        "tunnelConfigSha256": _config_snapshot(config),
        "desiredTunnelConfig": {**config, "ingress": rules + ([] if exact_rules else [desired_rule]) + [final_rule]},
        "dnsRecord": deepcopy(dns),
        "dnsMarker": _dns_marker(spec),
        "requiredAuthorization": PUBLIC_INGRESS_ROUTE_WRITE_PHRASE,
    }


def apply_public_route(
    plan: dict[str, Any],
    *,
    api_token: str,
    _lock_held: bool = False,
) -> dict[str, Any]:
    if plan.get("action") == "already-configured":
        return {**plan, "mutated": False}
    required = {
        "targetName", "scope", "action", "route", "previousRoute", "routeInventorySnapshot",
        "hostStatusSnapshot", "tunnelConfig", "tunnelConfigSha256", "desiredTunnelConfig",
        "dnsRecord", "dnsMarker", "requiredAuthorization",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan["action"] != "register":
        raise DeploymentKitError("Malformed Cloudflare public-route plan.")
    if not _lock_held:
        with route_transaction_lock(plan["targetName"], plan["scope"]):
            return apply_public_route(plan, api_token=api_token, _lock_held=True)
    name = plan["targetName"]
    scope = plan["scope"]
    spec = plan["route"]
    host = cloudflare_ingress_status(name, scope)
    if _status_snapshot(host) != plan["hostStatusSnapshot"]:
        raise DeploymentKitError("Cloudflare host ingress changed after planning; create a fresh route plan.")
    inventory = cloudflare_route_inventory(name, scope)
    if _route_inventory_snapshot(inventory) != plan["routeInventorySnapshot"]:
        raise DeploymentKitError("Cloudflare public-route inventory changed after planning; create a fresh plan.")
    _lan_route(name, spec)
    config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
    if _config_snapshot(config) != plan["tunnelConfigSha256"]:
        raise DeploymentKitError("Cloudflare tunnel configuration changed after planning; create a fresh route plan.")
    records = cloudflare_api.list_dns_records(api_token, host["zoneId"], name=spec["publicHostname"])
    current_dns = _exact_dns_record(records, spec=spec, tunnel_id=host["tunnelId"])
    if current_dns != plan["dnsRecord"]:
        raise DeploymentKitError("Cloudflare DNS state changed after planning; create a fresh route plan.")

    profile = load_profile(name)
    access = verify_access(profile)
    host_written = False
    config_write_attempted = False
    dns_create_attempted = False
    try:
        _run_remote(
            profile,
            access["address"],
            "route-register-locked",
            scope=scope,
            spec=spec,
            expected=plan["previousRoute"],
        )
        host_written = True
        if plan["desiredTunnelConfig"] != plan["tunnelConfig"]:
            config_write_attempted = True
            cloudflare_api.update_tunnel_configuration(
                api_token, host["accountId"], host["tunnelId"], plan["desiredTunnelConfig"]
            )
        if current_dns is None:
            dns_create_attempted = True
            cloudflare_api.create_dns_cname(
                api_token,
                host["zoneId"],
                name=spec["publicHostname"],
                content=f"{host['tunnelId']}.cfargotunnel.com",
                comment=plan["dnsMarker"],
            )
    except Exception as original_error:
        rollback_errors: list[str] = []
        if dns_create_attempted:
            try:
                _reconcile_public_route_dns(api_token, host, spec, should_exist=False)
            except Exception as error:
                rollback_errors.append(f"DNS rollback failed: {error}")
        if config_write_attempted:
            try:
                _restore_tunnel_configuration_if_unchanged(
                    api_token,
                    host,
                    expected_current=plan["desiredTunnelConfig"],
                    previous=plan["tunnelConfig"],
                )
            except Exception as error:
                rollback_errors.append(str(error))
        if host_written and plan["previousRoute"] is None:
            try:
                _run_remote(profile, access["address"], "route-remove-locked", scope=scope, spec=spec)
            except Exception as error:
                rollback_errors.append(f"Host route rollback failed: {error}")
        if rollback_errors:
            raise DeploymentKitError(
                "Cloudflare public-route apply failed and rollback was incomplete; external state "
                "may remain changed. " + "; ".join(rollback_errors)
            ) from original_error
        raise

    try:
        final_host = cloudflare_ingress_status(name, scope)
        if _status_snapshot(final_host) != plan["hostStatusSnapshot"]:
            raise CloudflarePostWriteVerificationError(
                "Cloudflare host binding changed during public-route apply."
            )
        final_inventory = cloudflare_route_inventory(name, scope)
        if _find_route(final_inventory, spec["routeId"]) != spec:
            raise CloudflarePostWriteVerificationError(
                "Public route registration returned without exact host ownership metadata."
            )
        final_config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
        if final_config != plan["desiredTunnelConfig"]:
            raise CloudflarePostWriteVerificationError(
                "Cloudflare tunnel configuration does not match the reviewed route plan after apply."
            )
        final_dns = _exact_dns_record(
            cloudflare_api.list_dns_records(api_token, host["zoneId"], name=spec["publicHostname"]),
            spec=spec,
            tunnel_id=host["tunnelId"],
        )
        if final_dns is None:
            raise CloudflarePostWriteVerificationError(
                "Cloudflare DNS record is missing after public-route apply."
            )
    except CloudflarePostWriteVerificationError:
        raise
    except Exception as error:
        raise CloudflarePostWriteVerificationError(
            f"Cloudflare public-route post-write verification could not confirm provider state: {error}"
        ) from error
    return {
        "targetName": name,
        "scope": scope,
        "route": spec,
        "dnsRecordId": str(final_dns["id"]),
        "publicUrl": f"https://{spec['publicHostname']}",
        "mutated": True,
    }


def plan_public_route_removal(
    name: str,
    *,
    scope: str,
    owner_repo: str,
    environment: str,
    app_slug: str,
    api_token: str,
) -> dict[str, Any]:
    route_id = f"{_slug(app_slug, 'appSlug')}--{_slug(environment, 'environment')}"
    owner_repo = _owner_repo(owner_repo)
    host = cloudflare_ingress_status(name, scope)
    if host["state"] != "ready":
        raise DeploymentKitError("Cloudflare ingress must be ready before removing a managed public route.")
    inventory = cloudflare_route_inventory(name, scope)
    route = _find_route(inventory, route_id)
    if route is None:
        raise DeploymentKitError(f"Managed Cloudflare public route does not exist: {route_id}")
    if route["ownerRepo"] != owner_repo or route["environment"] != environment or route["appSlug"] != app_slug:
        raise DeploymentKitError("Cloudflare public-route removal ownership does not match.")
    config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
    rules, final_rule = _split_ingress(config)
    expected_rule = _cloudflare_rule(route, authenticated_origin=host["authenticatedOrigin"])
    matches = [item for item in rules if item == expected_rule]
    if len(matches) != 1:
        raise DeploymentKitError("Cloudflare tunnel does not contain exactly one expected managed rule for this route.")
    desired = {**config, "ingress": [item for item in rules if item != expected_rule] + [final_rule]}
    dns = _exact_dns_record(
        cloudflare_api.list_dns_records(api_token, host["zoneId"], name=route["publicHostname"]),
        spec=route,
        tunnel_id=host["tunnelId"],
    )
    if dns is None:
        raise DeploymentKitError("Managed public route DNS record is missing; inspect drift before removal.")
    return {
        "targetName": name,
        "scope": scope,
        "action": "remove",
        "route": route,
        "routeInventorySnapshot": _route_inventory_snapshot(inventory),
        "hostStatusSnapshot": _status_snapshot(host),
        "tunnelConfig": config,
        "tunnelConfigSha256": _config_snapshot(config),
        "desiredTunnelConfig": desired,
        "dnsRecord": deepcopy(dns),
        "requiredAuthorization": PUBLIC_INGRESS_ROUTE_REMOVE_PHRASE,
    }


def apply_public_route_removal(
    plan: dict[str, Any],
    *,
    api_token: str,
    _lock_held: bool = False,
) -> dict[str, Any]:
    required = {
        "targetName", "scope", "action", "route", "routeInventorySnapshot", "hostStatusSnapshot",
        "tunnelConfig", "tunnelConfigSha256", "desiredTunnelConfig", "dnsRecord", "requiredAuthorization",
    }
    if not isinstance(plan, dict) or set(plan) != required or plan["action"] != "remove":
        raise DeploymentKitError("Malformed Cloudflare public-route removal plan.")
    if not _lock_held:
        with route_transaction_lock(plan["targetName"], plan["scope"]):
            return apply_public_route_removal(plan, api_token=api_token, _lock_held=True)
    name = plan["targetName"]
    scope = plan["scope"]
    route = plan["route"]
    host = cloudflare_ingress_status(name, scope)
    if _status_snapshot(host) != plan["hostStatusSnapshot"]:
        raise DeploymentKitError("Cloudflare ingress host state changed after removal planning.")
    inventory = cloudflare_route_inventory(name, scope)
    if _route_inventory_snapshot(inventory) != plan["routeInventorySnapshot"]:
        raise DeploymentKitError("Cloudflare public-route inventory changed after removal planning.")
    config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
    if _config_snapshot(config) != plan["tunnelConfigSha256"]:
        raise DeploymentKitError("Cloudflare tunnel configuration changed after removal planning.")
    dns = _exact_dns_record(
        cloudflare_api.list_dns_records(api_token, host["zoneId"], name=route["publicHostname"]),
        spec=route,
        tunnel_id=host["tunnelId"],
    )
    if dns is None or str(dns.get("id")) != str(plan["dnsRecord"].get("id")):
        raise DeploymentKitError("Cloudflare DNS record changed after removal planning.")

    try:
        cloudflare_api.update_tunnel_configuration(
            api_token, host["accountId"], host["tunnelId"], plan["desiredTunnelConfig"]
        )
    except Exception as original_error:
        try:
            _restore_tunnel_configuration_if_unchanged(
                api_token,
                host,
                expected_current=plan["desiredTunnelConfig"],
                previous=plan["tunnelConfig"],
            )
        except Exception as rollback_error:
            raise DeploymentKitError(
                "Cloudflare public-route removal failed during tunnel update and rollback was "
                f"incomplete: {rollback_error}"
            ) from original_error
        raise
    try:
        cloudflare_api.delete_dns_record(api_token, host["zoneId"], str(dns["id"]))
    except Exception as original_error:
        rollback_errors: list[str] = []
        try:
            _restore_tunnel_configuration_if_unchanged(
                api_token,
                host,
                expected_current=plan["desiredTunnelConfig"],
                previous=plan["tunnelConfig"],
            )
        except Exception as rollback_error:
            rollback_errors.append(f"Tunnel configuration rollback failed: {rollback_error}")
        try:
            _reconcile_public_route_dns(api_token, host, route, should_exist=True)
        except Exception as rollback_error:
            rollback_errors.append(f"DNS rollback failed: {rollback_error}")
        if rollback_errors:
            raise DeploymentKitError(
                "Cloudflare public-route removal failed and rollback was incomplete; external "
                "state may remain changed. " + "; ".join(rollback_errors)
            ) from original_error
        raise

    profile = load_profile(name)
    access = verify_access(profile)
    try:
        _run_remote(profile, access["address"], "route-remove-locked", scope=scope, spec=route)
    except Exception as original_error:
        rollback_errors: list[str] = []
        try:
            _restore_tunnel_configuration_if_unchanged(
                api_token,
                host,
                expected_current=plan["desiredTunnelConfig"],
                previous=plan["tunnelConfig"],
            )
        except Exception as error:
            rollback_errors.append(f"Tunnel configuration rollback failed: {error}")
        try:
            _reconcile_public_route_dns(api_token, host, route, should_exist=True)
        except Exception as error:
            rollback_errors.append(f"DNS rollback failed: {error}")
        try:
            current_inventory = cloudflare_route_inventory(name, scope)
            current_route = _find_route(current_inventory, route["routeId"])
            if current_route is None:
                _run_remote(
                    profile,
                    access["address"],
                    "route-register-locked",
                    scope=scope,
                    spec=route,
                    expected=None,
                )
            elif current_route != route:
                raise DeploymentKitError(
                    "Host route restoration was skipped because route ownership changed."
                )
        except Exception as error:
            rollback_errors.append(f"Host route rollback failed: {error}")
        if rollback_errors:
            raise DeploymentKitError(
                "Cloudflare public-route removal failed and rollback was incomplete; external "
                "state may remain changed. " + "; ".join(rollback_errors)
            ) from original_error
        raise

    final = cloudflare_route_inventory(name, scope)
    if _find_route(final, route["routeId"]) is not None:
        raise DeploymentKitError("Cloudflare public route remains in host ownership registry after removal.")
    return {"targetName": name, "scope": scope, "routeId": route["routeId"], "mutated": True}
