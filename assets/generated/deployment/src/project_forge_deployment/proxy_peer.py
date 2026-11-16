"""Read-only exact Caddy peer observation and reconciliation proposal (PF-06).

No Docker/network/provider writes, no configuration mutation, no trust bypass.
A completed observation is an input to a separately reviewed application
convergence plan, never automatic authorization to rewrite trusted peer IPs.
"""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

from .box_platform_assets import CADDY_CONTAINER, CADDY_IMAGE, NETWORK_NAME
from .errors import DeploymentKitError

_SCHEMA_VERSION = 1
_HEX_ID = re.compile(r"[0-9a-f]{64}")
_KEYS = frozenset({
    "containerId", "containerName", "containerState", "containerImage",
    "networkId", "networks", "members",
})
_MAX_BYTES = 65536


def _require_exact_ip(raw: Any) -> str:
    if not isinstance(raw, str):
        raise DeploymentKitError("Managed proxy address is not an IPv4 string.")
    try:
        address = ipaddress.IPv4Address(raw)
    except ipaddress.AddressValueError as error:
        raise DeploymentKitError("Managed proxy address is invalid.") from error
    if not address.is_private or address.is_unspecified or address.is_loopback or address.is_multicast or address.is_link_local:
        raise DeploymentKitError("Managed proxy address is not a suitable private-network peer.")
    return str(address)


def parse_peer_observation(stdout: str) -> dict[str, Any]:
    """Validate an allowlisted remote observation without propagating raw output."""
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > _MAX_BYTES:
        raise DeploymentKitError("Managed proxy observation exceeds the bounded read-only format.")
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            raise DeploymentKitError("Malformed managed proxy observation.")
        name, value = line.split("=", 1)
        if name not in _KEYS or name in fields or not value:
            raise DeploymentKitError("Unexpected or duplicate managed proxy observation field.")
        fields[name] = value
    if set(fields) != _KEYS:
        raise DeploymentKitError("Managed proxy observation is incomplete.")

    container_id, network_id = fields["containerId"], fields["networkId"]
    if not _HEX_ID.fullmatch(container_id) or not _HEX_ID.fullmatch(network_id):
        raise DeploymentKitError("Managed proxy identity is not an exact full Docker identifier.")
    if fields["containerName"] != CADDY_CONTAINER or fields["containerState"] != "running":
        raise DeploymentKitError("Expected managed proxy container is not running.")
    if fields["containerImage"] != CADDY_IMAGE:
        raise DeploymentKitError("Managed proxy image differs from the pinned Kit image.")
    try:
        networks = json.loads(fields["networks"])
        members = json.loads(fields["members"])
    except json.JSONDecodeError as error:
        raise DeploymentKitError("Managed proxy Docker network observation is malformed.") from error
    if not isinstance(networks, dict) or set(networks) != {NETWORK_NAME}:
        raise DeploymentKitError("Managed proxy has an unexpected network attachment.")
    net = networks[NETWORK_NAME]
    if not isinstance(net, dict) or net.get("NetworkID") != network_id:
        raise DeploymentKitError("Managed proxy network identity mismatch.")
    address = _require_exact_ip(net.get("IPAddress"))
    if not isinstance(members, dict) or container_id not in members:
        raise DeploymentKitError("Managed proxy is missing from the named network member registry.")
    member = members[container_id]
    if not isinstance(member, dict) or member.get("Name") != CADDY_CONTAINER:
        raise DeploymentKitError("Managed proxy membership does not match its exact identity.")
    cidr = member.get("IPv4Address")
    if not isinstance(cidr, str) or cidr.split("/", 1)[0] != address:
        raise DeploymentKitError("Managed proxy IP disagrees with Docker network membership.")
    # The network may contain unrelated application peers. Do not trust the
    # entire network, require its exclusivity, or grant those peers authority.
    for other_id, other in members.items():
        if not isinstance(other_id, str) or not _HEX_ID.fullmatch(other_id):
            raise DeploymentKitError("Managed network member identity is malformed.")
        if not isinstance(other, dict):
            raise DeploymentKitError("Managed network member record is malformed.")
        other_ip = other.get("IPv4Address")
        if not isinstance(other_ip, str):
            raise DeploymentKitError("Managed network member address is malformed.")
        if other_id != container_id and other_ip.split("/", 1)[0] == address:
            raise DeploymentKitError("Managed proxy address conflicts with another network member.")
    return {
        "schemaVersion": _SCHEMA_VERSION,
        "containerName": CADDY_CONTAINER,
        "containerId": container_id,
        "containerImage": CADDY_IMAGE,
        "networkName": NETWORK_NAME,
        "networkId": network_id,
        "peerIp": address,
        "verifiedBy": "read-only-docker-observation",
        "mutated": False,
    }


def assess_configured_peer(
    observation: dict[str, Any],
    configured_peer: str | None,
    *,
    previous_container_id: str | None = None,
    previous_network_id: str | None = None,
) -> dict[str, Any]:
    """Produce a no-write convergence decision requiring separate review."""
    if not isinstance(observation, dict) or observation.get("schemaVersion") != _SCHEMA_VERSION:
        raise DeploymentKitError("Managed proxy observation schema is unsupported.")
    required = {
        "schemaVersion", "containerName", "containerId", "containerImage",
        "networkName", "networkId", "peerIp", "verifiedBy", "mutated",
    }
    if set(observation) != required or observation.get("mutated") is not False or (
        observation.get("verifiedBy") != "read-only-docker-observation"
    ):
        raise DeploymentKitError("Untrusted managed proxy observation.")
    for id_value in (observation["containerId"], observation["networkId"]):
        if not isinstance(id_value, str) or not _HEX_ID.fullmatch(id_value):
            raise DeploymentKitError("Managed proxy observation lacks exact identity.")
    observed = _require_exact_ip(observation["peerIp"])
    if (observation["containerName"] != CADDY_CONTAINER or
        observation["containerImage"] != CADDY_IMAGE or
        observation["networkName"] != NETWORK_NAME):
        raise DeploymentKitError("Managed proxy observation is for a different owned component.")

    if configured_peer is not None:
        configured_peer = _require_exact_ip(configured_peer)
    for prior in (previous_container_id, previous_network_id):
        if prior is not None and (not isinstance(prior, str) or not _HEX_ID.fullmatch(prior)):
            raise DeploymentKitError("Prior peer identity must be the exact reviewed Docker ID.")
    changed = (
        (configured_peer is not None and configured_peer != observed) or
        (previous_container_id is not None and previous_container_id != observation["containerId"]) or
        (previous_network_id is not None and previous_network_id != observation["networkId"])
    )
    state = (
        "requires-reviewed-convergence" if changed
        else "needs-explicit-initial-binding" if configured_peer is None
        else "needs-reviewed-identity-baseline" if (
            previous_container_id is None or previous_network_id is None
        )
        else "observed-match"
    )
    return {
        **observation,
        "state": state,
        "configuredPeerIp": configured_peer,
        "nextAction": (
            "review-peer-and-application-configuration" if changed
            else "review-initial-peer-binding" if configured_peer is None
            else "record-reviewed-peer-identities" if state == "needs-reviewed-identity-baseline"
            else "retain-reviewed-peer-binding"
        ),
        "requiresAuthorization": state != "observed-match",
        "doesNotProve": [
            "application trust middleware enforcement",
            "live public-origin request contract",
            "exclusive Docker network ownership",
            "future Docker address stability",
        ],
        "mutated": False,
    }
