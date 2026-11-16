"""Safe public-route apply wrapper for Cloudflare provider normalization.

Cloudflare currently adds ``warp-routing: {enabled: false}`` when returning a
remotely managed tunnel configuration even when that provider default was not
submitted.  Project Forge tolerates only that observed no-op normalization;
all reviewed ingress rules and every other configuration value remain exact.
"""

from __future__ import annotations

from typing import Any

from . import cloudflare_api
from . import cloudflare_ingress as ingress
from .errors import CloudflarePostWriteVerificationError, DeploymentKitError


def _reviewed_config_matches(actual: Any, reviewed: Any) -> bool:
    """Match reviewed config after removing only the observed safe provider default."""
    return ingress._reviewed_config_matches(actual, reviewed)


def _read_final_state(plan: dict[str, Any], *, api_token: str) -> dict[str, Any]:
    name = plan["targetName"]
    scope = plan["scope"]
    spec = plan["route"]
    host = ingress.cloudflare_ingress_status(name, scope)
    if ingress._status_snapshot(host) != plan["hostStatusSnapshot"]:
        raise DeploymentKitError(
            "Cloudflare host binding changed after route apply; recovery was stopped before reading provider state."
        )
    inventory = ingress.cloudflare_route_inventory(name, scope)
    route = ingress._find_route(inventory, spec["routeId"])
    config = cloudflare_api.get_tunnel_configuration(api_token, host["accountId"], host["tunnelId"])
    records = cloudflare_api.list_dns_records(api_token, host["zoneId"], name=spec["publicHostname"])
    dns_error: str | None = None
    try:
        dns = ingress._exact_dns_record(records, spec=spec, tunnel_id=host["tunnelId"])
    except DeploymentKitError as error:
        dns = None
        dns_error = str(error)
    return {
        "host": host,
        "route": route,
        "config": config,
        "dns": dns,
        "dnsError": dns_error,
    }


def _rollback_final_state(
    plan: dict[str, Any],
    state: dict[str, Any],
    *,
    api_token: str,
) -> list[str]:
    """Best-effort reverse only mutations that can still be attributed safely."""
    errors: list[str] = []
    host = state["host"]
    spec = plan["route"]

    if plan["dnsRecord"] is None:
        dns = state["dns"]
        if dns is not None:
            try:
                ingress._reconcile_public_route_dns(
                    api_token,
                    host,
                    spec,
                    should_exist=False,
                )
            except Exception as error:  # pragma: no cover - provider failure detail only
                errors.append(f"DNS rollback failed: {error}")
        elif state["dnsError"] is not None:
            errors.append("DNS rollback skipped because current DNS ownership is ambiguous.")

    if plan["desiredTunnelConfig"] != plan["tunnelConfig"]:
        current = state["config"]
        if _reviewed_config_matches(current, plan["desiredTunnelConfig"]):
            try:
                ingress._restore_tunnel_configuration_if_unchanged(
                    api_token,
                    host,
                    expected_current=plan["desiredTunnelConfig"],
                    previous=plan["tunnelConfig"],
                )
            except Exception as error:  # pragma: no cover - provider failure detail only
                errors.append(f"tunnel configuration rollback failed: {error}")
        elif not _reviewed_config_matches(current, plan["tunnelConfig"]):
            errors.append(
                "Tunnel configuration rollback skipped because current provider state cannot be safely attributed to this apply."
            )

    if plan["previousRoute"] is None and state["route"] == spec:
        try:
            profile = ingress.load_profile(plan["targetName"])
            access = ingress.verify_access(profile)
            ingress._run_remote(
                profile,
                access["address"],
                "route-remove-locked",
                scope=plan["scope"],
                spec=spec,
            )
        except Exception as error:  # pragma: no cover - remote failure detail only
            errors.append(f"host route rollback failed: {error}")

    return errors


def apply_public_route(plan: dict[str, Any], *, api_token: str) -> dict[str, Any]:
    """Apply a reviewed public route with bounded post-write recovery.

    The underlying apply retains all pre-write stale-state checks and its write
    rollback. Recovery is entered only for the typed error emitted by the
    post-write verification phase, so preflight failures can never be turned
    into success by observing later provider state.
    """
    if (
        not isinstance(plan, dict)
        or plan.get("action") != "register"
        or not {"targetName", "scope"}.issubset(plan)
    ):
        return ingress.apply_public_route(plan, api_token=api_token)
    with ingress.route_transaction_lock(plan["targetName"], plan["scope"]):
        return _apply_public_route_locked(plan, api_token=api_token)


def _apply_public_route_locked(plan: dict[str, Any], *, api_token: str) -> dict[str, Any]:
    try:
        return ingress.apply_public_route(plan, api_token=api_token, _lock_held=True)
    except CloudflarePostWriteVerificationError as original_error:
        required = {
            "targetName", "scope", "route", "previousRoute", "hostStatusSnapshot",
            "tunnelConfig", "desiredTunnelConfig", "dnsRecord", "dnsMarker",
        }
        if not required.issubset(plan):
            raise

        try:
            state = _read_final_state(plan, api_token=api_token)
        except Exception as recovery_error:
            raise _uncertain_recovery_error(original_error, recovery_error) from recovery_error

        if ingress._status_snapshot(state["host"]) != plan["hostStatusSnapshot"]:
            recovery_error = DeploymentKitError(
                "Cloudflare host binding changed after route apply; recovery was stopped."
            )
            raise _uncertain_recovery_error(original_error, recovery_error) from recovery_error

        route_ok = state["route"] == plan["route"]
        config_ok = _reviewed_config_matches(state["config"], plan["desiredTunnelConfig"])
        dns_ok = state["dns"] is not None
        if route_ok and config_ok and dns_ok:
            return {
                "targetName": plan["targetName"],
                "scope": plan["scope"],
                "route": plan["route"],
                "dnsRecordId": str(state["dns"]["id"]),
                "publicUrl": f"https://{plan['route']['publicHostname']}",
                "mutated": True,
            }

        rollback_errors = _rollback_final_state(plan, state, api_token=api_token)
        if rollback_errors:
            raise DeploymentKitError(
                "Cloudflare public-route final verification failed and rollback was incomplete; "
                "external state may remain changed. "
                + "; ".join(rollback_errors)
                + " Inspect the managed host route, tunnel configuration, and DNS record before retrying."
            ) from original_error
        raise original_error


def _uncertain_recovery_error(
    original_error: Exception,
    recovery_error: Exception,
) -> DeploymentKitError:
    return DeploymentKitError(
        "Cloudflare public-route final verification failed, and recovery could not confirm "
        "the reviewed host binding and current provider state. External state is uncertain "
        "and rollback was not attempted because ownership could not be verified safely. "
        f"Original verification error: {original_error} "
        f"Recovery check failed: {recovery_error} "
        "Inspect the managed host route, tunnel configuration, and DNS record before retrying."
    )


def apply_public_route_removal(plan: dict[str, Any], *, api_token: str) -> dict[str, Any]:
    if (
        not isinstance(plan, dict)
        or plan.get("action") != "remove"
        or not {"targetName", "scope"}.issubset(plan)
    ):
        return ingress.apply_public_route_removal(plan, api_token=api_token)
    with ingress.route_transaction_lock(plan["targetName"], plan["scope"]):
        return ingress.apply_public_route_removal(plan, api_token=api_token, _lock_held=True)
