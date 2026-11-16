"""Read-only strict target-access diagnosis with optional temporary address evidence."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
from typing import Any

from .errors import DeploymentKitError
from .profiles import load_profile
from .ssh import diagnose_access


def _temporary_address(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as error:
        raise DeploymentKitError("Temporary target address must be an exact IPv4 or IPv6 address.") from error
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.scope_id is not None:
        raise DeploymentKitError("Temporary target address must not include an IPv6 scope identifier.")
    return str(parsed)


def _route_interface(address: str) -> str | None:
    if sys.platform == "darwin":
        route = shutil.which("route") or ("/sbin/route" if os.path.exists("/sbin/route") else None)
        if route:
            result = subprocess.run(
                [route, "-n", "get", address],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                match = re.search(r"^\s*interface:\s*(\S+)\s*$", result.stdout, re.MULTILINE)
                if match:
                    return match.group(1)
    elif os.name != "nt":
        ip = shutil.which("ip")
        if ip:
            result = subprocess.run(
                [ip, "route", "get", address],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0:
                match = re.search(r"\bdev\s+(\S+)", result.stdout)
                if match:
                    return match.group(1)
    return None


def route_source_evidence(address: str, port: int) -> dict[str, Any]:
    """Return the local route-selected source for one exact target address without scanning."""
    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if isinstance(parsed, ipaddress.IPv6Address) else socket.AF_INET
    evidence: dict[str, Any] = {
        "targetAddress": str(parsed),
        "targetPort": int(port),
        "sourceAddress": None,
        "interface": _route_interface(str(parsed)),
    }
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as probe:
            probe.connect((str(parsed), int(port)))
            evidence["sourceAddress"] = probe.getsockname()[0]
    except OSError as error:
        evidence["sourceProbeError"] = str(error)
    return evidence


def diagnose_target_access(name: str, *, temporary_address: str | None = None) -> dict[str, Any]:
    """Diagnose strict SSH access without persisting a temporary address override."""
    profile = load_profile(name)
    address = _temporary_address(temporary_address)
    effective = dict(profile)
    if address is not None:
        effective["addressOverride"] = address

    diagnosis = diagnose_access(effective)
    used_address = diagnosis.get("address")
    if used_address is None and address is not None:
        used_address = address

    result: dict[str, Any] = {
        **diagnosis,
        "addressInput": (
            {
                "source": "temporary-operator-confirmed",
                "address": address,
                "persisted": False,
            }
            if address is not None
            else {
                "source": "profile",
                "address": profile.get("addressOverride"),
                "persisted": profile.get("addressOverride") is not None,
            }
        ),
        "mutated": False,
    }
    if used_address is not None:
        result["routeSource"] = route_source_evidence(used_address, int(profile["port"]))
    return result
