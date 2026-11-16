"""Strict *candidate shape* for Feedback's proposed verified-release event.

This does NOT attest a deployment, sign an event, query runtime, establish
source-image provenance, or authorize a Feedback 'Released' transition.
It only rejects malformed inputs *before* any future trusted producer handles
verified deployment/build evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from .errors import DeploymentKitError


class ReleaseEvidenceCandidateError(DeploymentKitError):
    """A proposed release event is structurally invalid or out of scope."""


_KEYS = frozenset({
    "schemaVersion", "kind", "idempotencyKey", "ownerRepo", "appSlug",
    "environment", "deploymentState", "sourceCommit", "registryImage",
    "runtimeImageId", "specSha256", "verifiedAtUtc", "evidenceDigest",
})
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
_SLUG = re.compile(r"[a-z0-9][a-z0-9.-]{0,79}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{15,127}\Z")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._:/-]{2,300}@sha256:([0-9a-f]{64})\Z")


def validate_release_evidence_candidate(
    event: object, *, expected_repo: str, expected_environment: str,
    max_age_seconds: int = 900, now: datetime | None = None
) -> dict:
    """Return a strict copy of one structural candidate; **not** an attestation.

    The caller must independently verify the trusted Deployment Kit emission
    identity, canonical signature, immutable image/build/source provenance,
    actual reviewed host/target, rollback and idempotency. Never use this alone
    to mark a Feedback record Released.
    """
    if not isinstance(event, dict) or set(event) != _KEYS:
        raise ReleaseEvidenceCandidateError("candidate schema mismatch")
    if type(event["schemaVersion"]) is not int or event["schemaVersion"] != 1:
        raise ReleaseEvidenceCandidateError("unsupported candidate schema version")
    if event["kind"] != "verified-application-release":
        raise ReleaseEvidenceCandidateError("invalid candidate kind")
    if event["deploymentState"] != "verified-deployed":
        raise ReleaseEvidenceCandidateError("not a deployment candidate")
    if not isinstance(expected_repo, str) or not _REPO.fullmatch(expected_repo):
        raise ReleaseEvidenceCandidateError("invalid expected Project owner")
    if not isinstance(expected_environment, str) or not _SLUG.fullmatch(expected_environment):
        raise ReleaseEvidenceCandidateError("invalid expected environment")
    for key, pattern in (
        ("ownerRepo", _REPO), ("appSlug", _SLUG), ("environment", _SLUG),
        ("idempotencyKey", _ID), ("sourceCommit", _SHA1),
        ("specSha256", _HASH), ("registryImage", _IMAGE),
        ("runtimeImageId", re.compile(r"sha256:[0-9a-f]{64}\Z")),
        ("evidenceDigest", re.compile(r"sha256:[0-9a-f]{64}\Z")),
    ):
        value = event[key]
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ReleaseEvidenceCandidateError(f"invalid candidate {key}")
    if event["ownerRepo"] != expected_repo or event["environment"] != expected_environment:
        raise ReleaseEvidenceCandidateError("cross-Project or environment candidate")
    stamp = event["verifiedAtUtc"]
    if not isinstance(stamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp
    ):
        raise ReleaseEvidenceCandidateError("invalid candidate UTC verification time")
    try:
        observed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ReleaseEvidenceCandidateError("invalid candidate UTC verification date") from None
    check_now = now or datetime.now(timezone.utc)
    if check_now.tzinfo is None or not 1 <= max_age_seconds <= 86400:
        raise ReleaseEvidenceCandidateError("invalid verification clock policy")
    delta = (check_now.astimezone(timezone.utc) - observed).total_seconds()
    if delta < -30 or delta > max_age_seconds:
        raise ReleaseEvidenceCandidateError("candidate evidence is stale or in the future")
    return dict(event)
