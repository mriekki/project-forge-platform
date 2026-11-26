"""Shared, advisory lifecycle evidence assessment (#195/#205).

No approval event or privileged attestation producer is enabled by this
module. Only the existing verified transport or bounded read-only commands
may acquire records. A portable report is not an authorization source.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import subprocess
from urllib.parse import quote

from .errors import DeploymentKitError
from .private_image_publication import (
    COMMIT, DIGEST, PACKAGE, REPOSITORY, MAX_MANIFEST, check_manifest_config,
    check_private_package, matches, positive_int, require, unique_keys, reject_constant,
)

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
MAX_METADATA = 1024 * 1024


def _get_json(endpoint, *, run=subprocess.run):
    """Use existing gh context, never export or create credentials."""
    completed = run(["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
                    check=True, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
    data = completed.stdout
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_METADATA,
            "bounded GitHub metadata required")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=unique_keys,
                           parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise DeploymentKitError("invalid GitHub metadata") from None
    require(isinstance(value, dict), "GitHub metadata object required")
    return value


def _private_identity(repository, slug, *, get):
    repo = get(f"repos/{repository}")
    require(isinstance(repo, dict) and repo.get("full_name") == repository
            and positive_int(repo.get("id")) and repo.get("private") is True
            and isinstance(repo.get("owner"), dict)
            and repo["owner"].get("login") == repository.split("/")[0]
            and positive_int(repo["owner"].get("id")), "exact private Project repository required")
    owner = repo["owner"]
    # Support only the existing private user-owned GHCR publisher scope.
    # An org/unlinked/unsupported package is unknown, not first-publication permission.
    require(owner.get("type") == "User", "unsupported private package owner type")
    # The username-specific endpoint is documented for public packages.
    # For the supported private owner scope, use the authenticated-user
    # endpoint and independently bind the account to the repository owner.
    actor = get("user")
    require(isinstance(actor, dict) and actor.get("login") == owner["login"]
            and positive_int(actor.get("id")) and actor["id"] == owner["id"]
            and actor.get("type") == "User", "authenticated package owner identity required")
    pkg = get(f"user/packages/container/{quote(slug, safe='')}")
    package_id = check_private_package({"ownerRepo": repository, "packageName": slug}, pkg)
    linked = pkg.get("repository")
    require(isinstance(linked, dict) and linked.get("id") == repo["id"]
            and linked.get("full_name") == repository
            and pkg["owner"].get("id") == owner["id"],
            "private package repository/owner identity mismatch")
    return repo["id"], owner["id"], package_id


def observe_registry_manifest(publication, *, get=_get_json, run=subprocess.run, clock=None):
    """Read exact existing GHCR digest with the workstation's Docker client.

    Only use a successful #205 publisher collector result in the caller;
    no accepting JSON flags as authorization. The independent GitHub package
    and Docker raw manifest reads do not authenticate source-build lineage.
    Buildx may append one newline to stdout; accept either byte sequence only
    if it exactly hashes to the requested immutable digest.
    """
    require(isinstance(publication, dict)
            and publication.get("publisherRecord") == "matched"
            and publication.get("evidenceAuthority") == "github-run-and-artifact-record-consistency"
            and publication.get("sourceBuildProvenance") == "not-verified"
            and publication.get("authorizesMutation") is False, "coherent publisher record required")
    repo, slug = publication.get("projectRepository"), publication.get("appSlug")
    commit, image = publication.get("sourceCommit"), publication.get("registryImage")
    config = publication.get("recordedLocalImageId")
    require(matches(REPOSITORY, repo) and repo.split("/")[1] not in (".", "..")
            and matches(SLUG, slug) and matches(PACKAGE, slug)
            and matches(COMMIT, commit) and matches(DIGEST, config)
            and positive_int(publication.get("projectRepositoryId"))
            and positive_int(publication.get("publicationRunId"))
            and positive_int(publication.get("publicationAttempt"))
            and positive_int(publication.get("projectCiRunId"))
            and matches(DIGEST, publication.get("archiveDigest")),
            "invalid exact publisher identity")
    registry = "ghcr.io/" + repo.split("/")[0].lower() + "/" + slug
    require(matches(re.compile(re.escape(registry) + r"@sha256:[0-9a-f]{64}"), image),
            "invalid immutable registry image scope")
    digest = image.rsplit("@", 1)[1]
    started = (clock or (lambda: datetime.now(timezone.utc)))()
    require(isinstance(started, datetime) and started.utcoffset() is not None,
            "timezone-aware registry observation required")
    try:
        identity = _private_identity(repo, slug, get=get)
        require(identity[0] == publication["projectRepositoryId"],
                "private package repository differs from publisher repository")
        completed = run(["docker", "buildx", "imagetools", "inspect", "--raw", image],
                        check=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
        raw = completed.stdout
        require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_MANIFEST + 1,
                "bounded raw registry manifest required")
        if ("sha256:" + hashlib.sha256(raw).hexdigest() != digest
                and raw.endswith(b"\n")):
            raw = raw[:-1]
        actual_config = check_manifest_config(raw, digest, config)
        require(_private_identity(repo, slug, get=get) == identity,
                "private package identity changed during collection")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, RecursionError):
        raise DeploymentKitError("registry evidence unavailable or inconsistent") from None
    return {
        "schemaVersion": 1, "projectRepository": repo, "appSlug": slug,
        "sourceCommit": commit, "registryImage": image, "manifestDigest": digest,
        "recordedConfigDigest": actual_config, "publicationRunId": publication["publicationRunId"],
        "publicationAttempt": publication["publicationAttempt"], "projectCiRunId": publication["projectCiRunId"],
        "publisherArchiveDigest": publication["archiveDigest"], "repositoryId": identity[0],
        "ownerId": identity[1], "packageId": identity[2], "observedAt": started.isoformat(),
        "evidenceAuthority": "authenticated-package-metadata-and-exact-registry-manifest",
        "manifestConfigComparison": "exact-record-match", "visibility": "private",
        "configBytes": "not-verified", "platform": "not-verified",
        "sourceBuildProvenance": "not-verified", "approvedDesiredRelease": "not-evaluated",
        "authorizesMutation": False,
    }


REGISTRY_FIELDS = frozenset({
    "schemaVersion", "projectRepository", "appSlug", "sourceCommit", "registryImage",
    "manifestDigest", "recordedConfigDigest", "publicationRunId", "publicationAttempt",
    "projectCiRunId", "publisherArchiveDigest", "repositoryId", "ownerId", "packageId",
    "observedAt", "evidenceAuthority", "manifestConfigComparison", "visibility",
    "configBytes", "platform", "sourceBuildProvenance", "approvedDesiredRelease",
    "authorizesMutation",
})


def validate_registry_observation(report, publication):
    """Validate the exact internal collector projection, not arbitrary claims.

    Never deserialize a saved report as a verified registry observation.
    """
    require(isinstance(report, dict) and set(report) == REGISTRY_FIELDS
            and type(report["schemaVersion"]) is int and report["schemaVersion"] == 1
            and report["evidenceAuthority"] == "authenticated-package-metadata-and-exact-registry-manifest"
            and report["manifestConfigComparison"] == "exact-record-match"
            and report["visibility"] == "private"
            and all(report[k] == "not-verified" for k in ("configBytes", "platform", "sourceBuildProvenance"))
            and report["approvedDesiredRelease"] == "not-evaluated"
            and report["authorizesMutation"] is False
            and all(positive_int(report[k]) for k in (
                "repositoryId", "ownerId", "packageId", "publicationRunId", "publicationAttempt", "projectCiRunId"))
            and all(report[k] == publication.get(k) for k in (
                "projectRepository", "appSlug", "sourceCommit", "registryImage", "publicationRunId",
                "publicationAttempt", "projectCiRunId"))
            and report["repositoryId"] == publication.get("projectRepositoryId")
            and report["publisherArchiveDigest"] == publication.get("archiveDigest")
            and report["recordedConfigDigest"] == publication.get("recordedLocalImageId")
            and matches(DIGEST, report["manifestDigest"])
            and isinstance(report["registryImage"], str)
            and report["registryImage"].endswith("@" + report["manifestDigest"]),
            "registry observation scope or authority mismatch")
    try:
        stamp = datetime.fromisoformat(report["observedAt"].replace("Z", "+00:00"))
        require(stamp.utcoffset() is not None, "timezone required")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise DeploymentKitError("invalid registry observation timestamp") from None
    return dict(report)


def _record(value):
    return value if isinstance(value, dict) else {}


def _fact(state, source, reason):
    return {"state": state, "source": source, "reason": reason}


def _final_freshness(report, stamp_key, label, current_label, stale_label, now, max_age):
    """Recheck the original stage observation at the final evaluation time.

    A previous stale/unknown/future label can never be upgraded to current.
    Missing, invalid and future timestamps do not establish even stale evidence.
    """
    if label not in (current_label, stale_label):
        return "unknown"
    stamp = report.get(stamp_key)
    if not isinstance(stamp, str):
        return "unknown"
    try:
        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if observed.utcoffset() is None:
            return "unknown"
        age = now - observed
    except (ValueError, TypeError, OverflowError):
        return "unknown"
    if age < timedelta(0):
        return "unknown"
    if label == stale_label or age > max_age:
        return "stale"
    return "current"


def lifecycle_assessment(*, package=None, package_proof=None, checkout=None, impact=None,
                         publication=None, registry=None, runtime=None, desired=None,
                         shared=None, now=None, registry_max_age=timedelta(minutes=5),
                         runtime_max_age=timedelta(minutes=5),
                         desired_max_age=timedelta(days=1),
                         package_proof_max_age=timedelta(days=7)):
    """Project the *current supported* evidence boundary, not an approval engine.

    These arguments are already collected in-process projections, not a public
    deserialization contract. No positive readiness based on caller booleans,
    reports, prior disposable qualification or missing applicability evidence.
    The required matrix is deliberately conservative until authorized
    approval, provenance, target-specific and service producers exist.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    require(isinstance(now, datetime) and now.utcoffset() is not None
            and all(isinstance(limit, timedelta) and limit > timedelta(0)
                    for limit in (registry_max_age, runtime_max_age, desired_max_age, package_proof_max_age)),
            "valid lifecycle evaluation clock required")
    package, proof, checkout, impact, pub, registry, runtime, desired, shared = map(
        _record, (package, package_proof, checkout, impact, publication, registry, runtime, desired, shared))
    records = _record(package.get("packageRecords"))
    components = _record(records.get("componentComparison"))
    record_match = (records.get("baselineReceiptComparison") == "same-recorded-version"
                    and bool(components) and all(v == "record-match" for v in components.values()))
    discrepancy = ("record-mismatch" in components.values()
                   or checkout.get("comparison") == "sampled-mismatch")
    package_state = ("discrepancy" if discrepancy else "record-match" if record_match else "unknown")
    # Proof of the baseline release is not proof of a different stable candidate.
    proof_state = "unknown"
    if (record_match and proof.get("evidenceAuthority") == "github-reviewed-main-verifier-observation"
            and proof.get("projectRepository") == package.get("projectRepository")
            and proof.get("platformCommit") == package.get("platformCommit")
            and _record(proof.get("package")).get("version") == records.get("baselineVersion")
            and proof.get("receiptSha256") is not None
            and proof["receiptSha256"] == _record(records.get("recordDigests")).get("receipt")
            and proof.get("authorizesMutation") is False):
        proof_label = ("stale" if proof.get("provenanceObservation") == "stale"
                       or proof.get("freshness") == "stale"
                       else "within-window" if proof.get("provenanceObservation") == "verified-by-platform-workflow"
                       and proof.get("freshness") == "within-window" else "unknown")
        proof_freshness = _final_freshness(proof, "observedAt", proof_label,
                                           "within-window", "stale", now, package_proof_max_age)
        if proof_freshness == "stale":
            proof_state = "stale"
        elif proof_freshness == "current":
            proof_state = "historical-verified-baseline"
    publisher_match = (pub.get("publisherRecord") == "matched"
                       and pub.get("evidenceAuthority") == "github-run-and-artifact-record-consistency"
                       and pub.get("authorizesMutation") is False)
    registry_match = False
    if publisher_match and registry:
        try:
            validate_registry_observation(registry, pub)
            registry_match = True
        except (DeploymentKitError, TypeError, KeyError, ValueError):
            pass
    registry_state = "unknown"
    if registry_match:
        try:
            observed = datetime.fromisoformat(registry["observedAt"].replace("Z", "+00:00"))
            require(observed.utcoffset() is not None, "timezone required")
            age = now - observed
            if timedelta(0) <= age <= registry_max_age:
                registry_state = "manifest-config-match"
            elif age > registry_max_age:
                registry_state = "stale"
        except (DeploymentKitError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            pass
    runtime_freshness = _final_freshness(runtime, "observedAtReported", runtime.get("freshness"),
                                        "within-reported-window", "stale-reported", now, runtime_max_age)
    runtime_state = "unknown"
    if runtime_freshness == "stale":
        runtime_state = "stale"
    elif runtime_freshness == "current":
        comparison = runtime.get("managedReleaseComparison")
        if (comparison in ("reported-mismatch", "reported-container-absent", "reported-not-listed")
                or runtime.get("health") == "reported-not-healthy"):
            runtime_state = "reported-discrepancy"
        elif comparison == "reported-match" and runtime.get("health") == "reported-healthy":
            runtime_state = "reported-healthy"
    managed_publisher_differs = (publisher_match
        and runtime_freshness == "current"
        and _record(runtime.get("scope")).get("ownerRepo") == pub.get("projectRepository")
        and _record(runtime.get("scope")).get("appSlug") == pub.get("appSlug")
        and isinstance(runtime.get("managedRegistryImage"), str)
        and runtime["managedRegistryImage"] != pub.get("registryImage"))
    if managed_publisher_differs:
        runtime_state = "reported-discrepancy"
    desired_freshness = _final_freshness(desired, "observedAtReported", desired.get("desiredEvidence"),
                                        "claimed-verified", "stale", now, desired_max_age)
    desired_state = "unknown"
    if desired_freshness == "stale":
        desired_state = "stale"
    elif desired_freshness == "current" and desired.get("desiredApprovalReported") is True:
        desired_state = "reported-unverified"
    shared_freshness = _final_freshness(shared, "observedAtReported", shared.get("freshness"),
                                        "within-reported-window", "stale-reported", now, runtime_max_age)
    shared_state = "unknown"
    if shared_freshness == "stale":
        shared_state = "stale"
    elif shared_freshness == "current":
        if shared.get("reportedPlatformState") == "ready":
            shared_state = "reported-ready-marker"
        elif shared.get("reportedPlatformState") not in (None, "unknown"):
            shared_state = "reported-discrepancy"
    dimensions = {
        "packageRecords": _fact(package_state, "pinned-package-receipt", "record comparison, not installed bytes"),
        "baselineProvenance": _fact(proof_state, "reviewed-platform-proof", "baseline only; candidate proof separate"),
        "stableCandidateProvenance": _fact(
            proof_state if record_match and records.get("stableVersionComparison") == "same-recorded-version" else "unknown",
            "reviewed-platform-proof", "baseline proof cannot verify a different stable candidate"),
        "completeManagedBytes": _fact("unknown", None, "sampled managed-file evidence is not complete"),
        "impactClassification": _fact("unknown", None, "affirmative package/application/shared-service impact required"),
        "managedBytes": _fact("sampled-discrepancy" if checkout.get("comparison") == "sampled-mismatch"
                              else "sampled-match" if checkout.get("comparison") == "sampled-match" else "unknown",
                              "managed-checkout-sample", "complete managed manifest not established"),
        "packageImpact": _fact("record-change-observed" if impact.get("direction") in ("stable-newer", "stable-older")
                               else "record-same-version" if impact.get("direction") == "same-recorded-version" else "unknown",
                               "mapped-component-receipts", "package shell/profile and runtime impact not established"),
        "publisher": _fact("historical-record-match" if publisher_match else "unknown",
                           "github-publisher-record", "source/CI/receipt record, not registry or provenance"),
        "registry": _fact(registry_state,
                          "authenticated-registry-read", "exact manifest/config relationship only"),
        "runtime": _fact(runtime_state, "scoped-kit-inventory", "reported managed image/health, not actual runtime attestation"),
        "desiredClaim": _fact(desired_state, "reported-desired-selection", "claim, not authenticated approval"),
        "sharedPlatform": _fact(shared_state, "kit-platform-doctor", "marker/liveness, not shared service provenance"),
        "authenticatedApproval": _fact("unknown", None, "no supported authenticated approval producer established"),
        "applicationProvenance": _fact("unknown", None, "no independently verified source-build attestation"),
        "actualRuntimeIdentity": _fact("unknown", None, "no trusted current host/generation and signer context established"),
        "sharedServiceIdentity": _fact("unknown", None, "service-specific release evidence required"),
        "compatibility": _fact("unknown", None, "exact target/profile/service applicability not established"),
        "rollback": _fact("unknown", None, "exact prior image, backup and recovery applicability not established"),
        "formalAcceptance": _fact("unknown", None, "separate work-item acceptance event required"),
    }
    # Applicability is not known for an arbitrary Project; never mark absent
    # collectors as not-applicable. Generic qualification is historical evidence.
    common = ("authenticatedApproval", "compatibility")
    matrix = {
        "package-only": ("packageRecords", "stableCandidateProvenance", "completeManagedBytes", "impactClassification",
                         "sharedServiceIdentity") + common,
        "application-release": ("publisher", "registry", "applicationProvenance", "actualRuntimeIdentity",
                                "rollback", "sharedServiceIdentity") + common,
        "shared-service": ("sharedPlatform", "sharedServiceIdentity", "rollback") + common,
        "coordinated": ("packageRecords", "stableCandidateProvenance", "completeManagedBytes", "impactClassification",
                         "publisher", "registry", "applicationProvenance", "actualRuntimeIdentity",
                         "sharedPlatform", "sharedServiceIdentity", "rollback") + common,
        "no-change": ("packageRecords", "stableCandidateProvenance", "completeManagedBytes", "impactClassification",
                      "actualRuntimeIdentity", "sharedServiceIdentity") + common,
    }
    # No currently supported producer can establish complete readiness.
    paths = {name: {"state": "insufficient-evidence",
                    "requiredEvidence": list(keys),
                    "unresolvedEvidence": [key for key in keys if dimensions[key]["state"] not in
                                           ("record-match", "historical-verified-baseline",
                                            "historical-record-match", "manifest-config-match")],
                    "applicability": "not-established"} for name, keys in matrix.items()}
    desired_differs = (desired_state == "reported-unverified"
                       and ((publisher_match
                             and _record(desired.get("scope")).get("ownerRepo") == pub.get("projectRepository")
                             and _record(desired.get("scope")).get("appSlug") == pub.get("appSlug")
                             and desired.get("publisherComparison") == "reported-desired-differs-from-publisher-record")
                            or (runtime_freshness == "current"
                                and isinstance(desired.get("scope"), dict)
                                and desired["scope"] == runtime.get("scope")
                                and desired.get("managedImageComparison") == "reported-desired-differs-from-managed-image")))
    if discrepancy or desired_differs or runtime_state == "reported-discrepancy" or shared_state == "reported-discrepancy":
        action = "investigate-observed-discrepancy"
    elif impact.get("direction") == "stable-older":
        action = "investigate-stable-older-than-baseline"
    elif records.get("stableVersionComparison") == "different-recorded-version":
        action = "assess-stable-package-impact"
    elif publisher_match and registry_state != "manifest-config-match":
        action = "obtain-exact-registry-evidence"
    else:
        action = "resolve-authoritative-evidence"
    return {"schemaVersion": 1, "evaluatedAt": now.isoformat(), "assessment": "insufficient-evidence", "dimensions": dimensions,
            "outcomePaths": paths, "recommendedAction": action,
            "releaseReadiness": "not-established", "authorizesMutation": False,
            "publicationAuthorized": False, "productionAuthorized": False,
            "dashboardImportAuthorized": False}
