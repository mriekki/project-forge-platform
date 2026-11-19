"""Strict *verification* of signed application release evidence, not an emitter.

Only a Deployment Kit production verifier, after independently checking the
authorized running immutable image and app provenance, may produce an event.
The application must obtain current host generation/image identity through its
approved read-only trust boundary before calling this verifier. JSON content
and a type named 'trusted' are never proof of a deployed release.

The optional cryptography dependency is used for ECDSA P-256 signatures.
This module does not sign events, inspect hosts, deploy, read secret keys or
change any application state.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import re
from typing import Any

from .errors import DeploymentKitError


class ReleaseAttestationError(DeploymentKitError):
    """Invalid, untrusted or inapplicable signed release projection."""


_ENVELOPE = frozenset({"schemaVersion", "algorithm", "keyId", "release", "signature"})
_RELEASE = frozenset({
    "schemaVersion", "kind", "idempotencyKey", "ownerRepo", "appSlug",
    "environment", "deploymentState", "sourceCommit", "registryImage",
    "runtimeImageId", "specSha256", "verifiedAtUtc", "evidenceDigest",
    "manifestSha256", "releaseVersion", "deploymentGeneration",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_SLUG = re.compile(r"[a-z0-9][a-z0-9.-]{0,79}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{15,127}\Z")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._:/-]{2,300}@sha256:([0-9a-f]{64})\Z")
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?\Z")
_B64 = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def _strict_json(content: bytes) -> dict[str, Any]:
    if not 1 <= len(content) <= 16_384:
        raise ReleaseAttestationError("signed release evidence size is invalid")

    def no_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseAttestationError("duplicate signed release field")
            result[key] = value
        return result

    try:
        payload = json.loads(content.decode("utf-8", errors="strict"),
                             object_pairs_hook=no_duplicate)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseAttestationError("invalid signed release JSON") from error
    if type(payload) is not dict:
        raise ReleaseAttestationError("signed release must be a JSON object")
    return payload


def _check_release(body: object) -> dict[str, Any]:
    if type(body) is not dict or set(body) != _RELEASE:
        raise ReleaseAttestationError("release evidence field set differs from schema v1")
    if type(body["schemaVersion"]) is not int or body["schemaVersion"] != 1:
        raise ReleaseAttestationError("unsupported release evidence schema")
    if body["kind"] != "verified-application-release":
        raise ReleaseAttestationError("invalid release evidence kind")
    if body["deploymentState"] not in ("verified-deployed", "rolled-back", "failed", "unknown"):
        raise ReleaseAttestationError("invalid deployment state")
    for field, pattern in (
        ("ownerRepo", _REPO), ("appSlug", _SLUG), ("environment", _SLUG),
        ("sourceCommit", _SHA1), ("specSha256", _SHA),
        ("registryImage", _IMAGE), ("runtimeImageId", re.compile(r"sha256:[0-9a-f]{64}\Z")),
        ("evidenceDigest", re.compile(r"sha256:[0-9a-f]{64}\Z")),
        ("idempotencyKey", _ID), ("releaseVersion", _VERSION),
    ):
        value = body[field]
        if type(value) is not str or not pattern.fullmatch(value):
            raise ReleaseAttestationError(f"invalid release evidence {field}")
    digest = body["manifestSha256"]
    if digest is not None and (type(digest) is not str or not _SHA.fullmatch(digest)):
        raise ReleaseAttestationError("invalid optional manifest digest")
    generation = body["deploymentGeneration"]
    if type(generation) is not int or not 1 <= generation < 2**63:
        raise ReleaseAttestationError("invalid deployment generation")
    stamp = body["verifiedAtUtc"]
    if type(stamp) is not str or not _DATE.fullmatch(stamp):
        raise ReleaseAttestationError("invalid exact UTC timestamp")
    try:
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ReleaseAttestationError("invalid release evidence date") from error
    return body


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def verify_release_attestation(
    encoded_envelope: bytes, *,
    pinned_public_key_pem: bytes,
    pinned_key_id: str,
    expected_repo: str,
    expected_app_slug: str,
    expected_environment: str,
    expected_source_commit: str,
    expected_runtime_image_id: str,
    expected_deployment_generation: int,
    expected_manifest_sha256: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an attested exact release only when every trusted runtime fact matches.

    The public key/key ID and expected runtime facts MUST come from separately
    authorized deployment/host configuration, never from this envelope, query
    parameters, caller-controlled environment or app-writable files. The
    function does not prove current host facts or key custody by itself.
    """
    envelope = _strict_json(encoded_envelope)
    if set(envelope) != _ENVELOPE or type(envelope["schemaVersion"]) is not int or envelope["schemaVersion"] != 1:
        raise ReleaseAttestationError("invalid signed release envelope")
    if envelope["algorithm"] != "ecdsa-p256-sha256-der" or not isinstance(pinned_key_id, str) or not _ID.fullmatch(pinned_key_id) or envelope["keyId"] != pinned_key_id:
        raise ReleaseAttestationError("invalid pinned release signer")
    body = _check_release(envelope["release"])
    signature_text = envelope["signature"]
    if type(signature_text) is not str or not _B64.fullmatch(signature_text) or len(signature_text) % 4 == 1:
        raise ReleaseAttestationError("invalid release evidence signature encoding")
    try:
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * ((4 - len(signature_text) % 4) % 4))
    except (ValueError, base64.binascii.Error) as error:
        raise ReleaseAttestationError("invalid signature data") from error

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        public_key = serialization.load_pem_public_key(pinned_public_key_pem)
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(public_key.curve, ec.SECP256R1):
            raise ReleaseAttestationError("unapproved release signing algorithm/key")
        public_key.verify(signature, _canonical(body), ec.ECDSA(hashes.SHA256()))
    except ReleaseAttestationError:
        raise
    except ImportError as error:
        raise ReleaseAttestationError("release evidence crypto verification is unavailable") from error
    except (InvalidSignature, ValueError, TypeError) as error:
        raise ReleaseAttestationError("release evidence signature verification failed") from error

    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ReleaseAttestationError("release evidence requires a timezone-aware clock")
    actual_time = datetime.strptime(body["verifiedAtUtc"],
                                    "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if actual_time > clock.astimezone(timezone.utc):
        raise ReleaseAttestationError("release evidence claims a future verification")
    if (
        body["deploymentState"] != "verified-deployed"
        or body["ownerRepo"] != expected_repo
        or body["appSlug"] != expected_app_slug
        or body["environment"] != expected_environment
        or body["sourceCommit"] != expected_source_commit
        or body["runtimeImageId"] != expected_runtime_image_id
        or body["deploymentGeneration"] != expected_deployment_generation
        or body["manifestSha256"] != expected_manifest_sha256
    ):
        raise ReleaseAttestationError("signed release is not the exact active deployment")
    if expected_manifest_sha256 is not None and not _SHA.fullmatch(expected_manifest_sha256):
        raise ReleaseAttestationError("invalid pinned manifest digest")
    return dict(body)
