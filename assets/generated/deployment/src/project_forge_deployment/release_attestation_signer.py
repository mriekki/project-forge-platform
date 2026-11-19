"""Host-only building block for a release attestation *after* verified apply.

IMPORTANT: This module is not a Production deployment controller and does not
inspect or attest a remote host by itself. The eventual authorized Deployment
Kit stage must supply a fresh privileged observer and a root/signer-owned
monotonic host generation. A callback returning JSON from a Project container
or a request is NOT a trusted observer. The signing key is never distributed to
applications, bundled in npm, or exposed via a CLI command.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable

from .release_attestation import (
    ReleaseAttestationError, _canonical, _check_release, _ID
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._:/-]{2,300}@sha256:[0-9a-f]{64}\Z")
_RUNTIME_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?\Z")

# These observed fields are NOT accepted as HTTP body, query or user-selected CLI.
# They must come from the approved host-owned live post-apply inspection adapter.
_OBSERVATION = frozenset({
    "ownerRepo", "appSlug", "environment", "sourceCommit",
    "registryImage", "runtimeImageId", "specSha256",
    "releaseVersion", "manifestSha256", "deploymentGeneration",
    "containerPresent", "imageMatchesRelease", "containerRunning",
    "connectedToSharedNetwork", "httpHealthy", "materialMountsVerified",
    "postApplyOperationId"
})

def _safe_private_key(path: Path) -> bytes:
    """Open one physically protected file only; never follow symlinks."""
    if not path.is_absolute():
        raise ReleaseAttestationError("signing key path must be absolute")
    for parent in (path, *path.parents):
        try:
            st = os.lstat(parent)
        except OSError as error:
            raise ReleaseAttestationError("signing key path unavailable") from error
        if stat.S_ISLNK(st.st_mode):
            raise ReleaseAttestationError("signing key path contains a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise ReleaseAttestationError("protected release signer cannot open key") from error
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o177):
            raise ReleaseAttestationError("release key ownership or permissions unsafe")
        with os.fdopen(fd, "rb", closefd=False) as source:
            material = source.read(8193)
        if not 1 <= len(material) <= 8192:
            raise ReleaseAttestationError("release signing key size invalid")
        return material
    finally:
        os.close(fd)


def _checked_observation(observed: object, *, expected: dict[str, Any]) -> dict[str, Any]:
    if type(observed) is not dict or set(observed) != _OBSERVATION:
        raise ReleaseAttestationError("post-apply host observation is incomplete")
    for flag in (
        "containerPresent", "imageMatchesRelease", "containerRunning",
        "connectedToSharedNetwork", "httpHealthy", "materialMountsVerified",
    ):
        if observed[flag] is not True:
            raise ReleaseAttestationError("post-apply runtime lacks verified health")
    for field, value in expected.items():
        if observed.get(field) != value or type(observed.get(field)) is not type(value):
            raise ReleaseAttestationError("host runtime does not match authorized release")
    for field, pattern in (
        ("sourceCommit", _SHA1), ("registryImage", _IMAGE),
        ("runtimeImageId", _RUNTIME_ID), ("specSha256", _SHA),
        ("releaseVersion", _VERSION), ("postApplyOperationId", _ID),
    ):
        value = observed[field]
        if type(value) is not str or not pattern.fullmatch(value):
            raise ReleaseAttestationError("unverified host release field")
    digest = observed["manifestSha256"]
    if digest is not None and (type(digest) is not str or not _SHA.fullmatch(digest)):
        raise ReleaseAttestationError("unverified host manifest hash")
    generation = observed["deploymentGeneration"]
    if type(generation) is not int or not 1 <= generation < 2**63:
        raise ReleaseAttestationError("monotonic host deployment generation missing")
    return observed


def sign_postapply_release(
    *,
    observe_privileged_host: Callable[[], dict[str, Any]],
    authorized_expected: dict[str, Any],
    signer_key_path: Path,
    pinned_key_id: str,
    verified_at_utc: datetime,
) -> bytes:
    """Produce canonical signed event *only* from a rechecked healthy host state.

    The authorized orchestrator MUST establish its live/privileged observer,
    immutable source-image provenance, authenticated build lineage, protected
    signer custody, and monotonic generation before calling this API.
    This method refuses missing/mismatched evidence; it is never invoked from
    normal CI, source builds, application endpoints or browser code.
    """
    required = {
        "ownerRepo", "appSlug", "environment", "sourceCommit",
        "registryImage", "runtimeImageId", "specSha256", "releaseVersion",
        "manifestSha256", "deploymentGeneration", "postApplyOperationId",
    }
    if type(authorized_expected) is not dict or set(authorized_expected) != required:
        raise ReleaseAttestationError("authorized deployment expectation incomplete")
    if not callable(observe_privileged_host):
        raise ReleaseAttestationError("authorized privileged live observer unavailable")
    if type(pinned_key_id) is not str or not _ID.fullmatch(pinned_key_id):
        raise ReleaseAttestationError("unrecognized authorized release signer")
    if (not isinstance(verified_at_utc, datetime) or
            verified_at_utc.tzinfo is None or
            verified_at_utc.utcoffset() is None or
            verified_at_utc.utcoffset().total_seconds() != 0 or
            verified_at_utc > datetime.now(timezone.utc)):
        raise ReleaseAttestationError("post-apply verification must have a real past UTC time")

    # Re-observe after apply; preflight or previously captured host JSON is
    # insufficient. A malicious/untrusted callback is beyond this helper's
    # authority and must never be wired to it.
    observed = _checked_observation(observe_privileged_host(),
                                    expected=authorized_expected)
    if observed["environment"] != "production":
        raise ReleaseAttestationError("release-note activation signer requires Production")
    payload = {
        "schemaVersion": 1,
        "kind": "verified-application-release",
        "idempotencyKey": observed["postApplyOperationId"],
        "ownerRepo": observed["ownerRepo"],
        "appSlug": observed["appSlug"],
        "environment": observed["environment"],
        "deploymentState": "verified-deployed",
        "sourceCommit": observed["sourceCommit"],
        "registryImage": observed["registryImage"],
        "runtimeImageId": observed["runtimeImageId"],
        "specSha256": observed["specSha256"],
        "verifiedAtUtc": verified_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidenceDigest": "sha256:" + hashlib.sha256(_canonical(observed)).hexdigest(),
        "manifestSha256": observed["manifestSha256"],
        "releaseVersion": observed["releaseVersion"],
        "deploymentGeneration": observed["deploymentGeneration"],
    }
    _check_release(payload)

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = serialization.load_pem_private_key(
            _safe_private_key(signer_key_path), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ReleaseAttestationError("unapproved signing key algorithm")
        signed = key.sign(_canonical(payload), ec.ECDSA(hashes.SHA256()))
    except ReleaseAttestationError:
        raise
    except (ImportError, ValueError, TypeError) as error:
        raise ReleaseAttestationError("protected release signer unavailable") from error
    envelope = {
        "schemaVersion": 1,
        "algorithm": "ecdsa-p256-sha256-der",
        "keyId": pinned_key_id,
        "release": payload,
        "signature": base64.urlsafe_b64encode(signed).decode("ascii").rstrip("="),
    }
    result = _canonical(envelope)
    if len(result) > 16384:
        raise ReleaseAttestationError("signed release attestation exceeds size bound")
    return result
