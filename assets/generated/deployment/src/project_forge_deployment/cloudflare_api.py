"""Minimal Cloudflare API client for Project Forge public-ingress orchestration.

The API token is supplied by the caller and is never persisted by this module.
Only the exact zone/tunnel/DNS surfaces needed by the Deployment Kit are exposed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import DeploymentKitError

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareApiError(DeploymentKitError):
    """Cloudflare API request or response validation failure."""


def _api_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            parts = []
            for item in errors:
                if isinstance(item, dict):
                    code = item.get("code")
                    message = item.get("message")
                    if message:
                        parts.append(f"{code}: {message}" if code is not None else str(message))
            if parts:
                return "; ".join(parts)
    return "Cloudflare API returned an unsuccessful response."


def _request(
    method: str,
    path: str,
    *,
    token: str,
    body: dict[str, Any] | None = None,
    query: dict[str, str | int | bool] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    if not isinstance(token, str) or not token.strip():
        raise CloudflareApiError("Cloudflare API token is required.")
    url = API_BASE + path
    if query:
        encoded = urllib.parse.urlencode(
            {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in query.items()}
        )
        url += "?" + encoded
    data = None
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Accept": "application/json",
        "User-Agent": "project-forge-deployment-kit/1",
    }
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeError):
            payload = None
        raise CloudflareApiError(
            f"Cloudflare API {method} {path} failed with HTTP {error.code}: {_api_error_message(payload)}"
        ) from error
    except urllib.error.URLError as error:
        raise CloudflareApiError(f"Cloudflare API {method} {path} could not be reached: {error.reason}") from error

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise CloudflareApiError(f"Cloudflare API {method} {path} returned malformed JSON.") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise CloudflareApiError(_api_error_message(payload))
    return payload


def resolve_zone(token: str, zone_name: str) -> dict[str, Any]:
    """Resolve one exact active Cloudflare zone and its owning account."""
    if not isinstance(zone_name, str) or not zone_name.strip():
        raise CloudflareApiError("Cloudflare zone name is required.")
    normalized = zone_name.strip().lower().rstrip(".")
    payload = _request(
        "GET",
        "/zones",
        token=token,
        query={"name": normalized, "status": "active", "per_page": 50},
    )
    result = payload.get("result")
    if not isinstance(result, list):
        raise CloudflareApiError("Cloudflare zone lookup returned an unexpected result.")
    exact = [
        item for item in result
        if isinstance(item, dict) and str(item.get("name", "")).lower().rstrip(".") == normalized
    ]
    if len(exact) != 1:
        raise CloudflareApiError(
            f"Expected exactly one active Cloudflare zone named {normalized}; found {len(exact)}."
        )
    zone = exact[0]
    account = zone.get("account")
    if not isinstance(account, dict) or not account.get("id"):
        raise CloudflareApiError("Cloudflare zone response did not include its account ID.")
    if not zone.get("id"):
        raise CloudflareApiError("Cloudflare zone response did not include its zone ID.")
    return {
        "zoneId": str(zone["id"]),
        "zoneName": normalized,
        "accountId": str(account["id"]),
        "status": zone.get("status"),
    }


def list_tunnels(token: str, account_id: str, *, name: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, str | int | bool] = {"is_deleted": False, "per_page": 1000}
    if name is not None:
        query["name"] = name
    payload = _request(
        "GET",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel",
        token=token,
        query=query,
    )
    result = payload.get("result")
    if not isinstance(result, list):
        raise CloudflareApiError("Cloudflare tunnel list returned an unexpected result.")
    return [item for item in result if isinstance(item, dict)]


def find_tunnel(token: str, account_id: str, name: str) -> dict[str, Any] | None:
    matches = [
        item for item in list_tunnels(token, account_id, name=name)
        if item.get("name") == name and item.get("deleted_at") in {None, ""}
    ]
    if len(matches) > 1:
        raise CloudflareApiError(f"Multiple active Cloudflare tunnels are named {name}; refusing ambiguous adoption.")
    return matches[0] if matches else None


def create_tunnel(token: str, account_id: str, name: str) -> dict[str, Any]:
    payload = _request(
        "POST",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel",
        token=token,
        body={"name": name, "config_src": "cloudflare"},
    )
    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("id"):
        raise CloudflareApiError("Cloudflare tunnel creation did not return a tunnel ID.")
    if result.get("config_src") not in {None, "cloudflare"}:
        raise CloudflareApiError("Cloudflare created a tunnel with an unexpected configuration source.")
    return result


def get_tunnel_token(token: str, account_id: str, tunnel_id: str) -> str:
    payload = _request(
        "GET",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel/{urllib.parse.quote(tunnel_id, safe='')}/token",
        token=token,
    )
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise CloudflareApiError("Cloudflare tunnel-token response was empty.")
    return result.strip()


def get_tunnel_configuration(token: str, account_id: str, tunnel_id: str) -> dict[str, Any]:
    payload = _request(
        "GET",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel/{urllib.parse.quote(tunnel_id, safe='')}/configurations",
        token=token,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise CloudflareApiError("Cloudflare tunnel configuration returned an unexpected result.")
    config = result.get("config")
    if config is None:
        return {"ingress": [{"service": "http_status:404"}]}
    if not isinstance(config, dict):
        raise CloudflareApiError("Cloudflare tunnel configuration 'config' must be an object.")
    return config


def update_tunnel_configuration(
    token: str,
    account_id: str,
    tunnel_id: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    payload = _request(
        "PUT",
        f"/accounts/{urllib.parse.quote(account_id, safe='')}/cfd_tunnel/{urllib.parse.quote(tunnel_id, safe='')}/configurations",
        token=token,
        body={"config": config},
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise CloudflareApiError("Cloudflare tunnel configuration update returned an unexpected result.")
    returned = result.get("config")
    return returned if isinstance(returned, dict) else config


def list_dns_records(token: str, zone_id: str, *, name: str) -> list[dict[str, Any]]:
    payload = _request(
        "GET",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
        token=token,
        query={"name": name, "per_page": 100},
    )
    result = payload.get("result")
    if not isinstance(result, list):
        raise CloudflareApiError("Cloudflare DNS lookup returned an unexpected result.")
    return [item for item in result if isinstance(item, dict)]


def create_dns_cname(
    token: str,
    zone_id: str,
    *,
    name: str,
    content: str,
    comment: str,
) -> dict[str, Any]:
    payload = _request(
        "POST",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records",
        token=token,
        body={
            "type": "CNAME",
            "name": name,
            "content": content,
            "proxied": True,
            "ttl": 1,
            "comment": comment,
        },
    )
    result = payload.get("result")
    if not isinstance(result, dict) or not result.get("id"):
        raise CloudflareApiError("Cloudflare DNS creation did not return a record ID.")
    return result


def delete_dns_record(token: str, zone_id: str, record_id: str) -> None:
    _request(
        "DELETE",
        f"/zones/{urllib.parse.quote(zone_id, safe='')}/dns_records/{urllib.parse.quote(record_id, safe='')}",
        token=token,
    )
