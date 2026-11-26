"""Optional private GHCR publication record checks; no I/O or authority.

The Project owns authenticated acquisition, build, manual authorization,
registry push and durable receipt writing. These comparisons cannot
authenticate caller-supplied records or prove that any push took place.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from .errors import DeploymentKitError

COMMIT = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
PACKAGE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9][A-Za-z0-9._-]*\.ya?ml")
PLATFORM = re.compile(r"linux/(amd64|arm64)")
MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json": "application/vnd.oci.image.config.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json": "application/vnd.docker.container.image.v1+json",
}
MAX_MANIFEST = 1024 * 1024


def require(condition, message):
    if not condition:
        raise DeploymentKitError(message)


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def record(value):
    require(isinstance(value, dict), "Expected an object evidence record.")
    return value


def positive_int(value):
    return type(value) is int and value > 0


def repository_identity(value, expected):
    return isinstance(value, dict) and value.get("full_name") == expected


def scope(repository, package_name, commit, platform, ci_workflow, release_version):
    require(matches(REPOSITORY, repository) and repository.split("/")[1] not in {".", ".."},
            "Invalid Project repository identity.")
    require(matches(PACKAGE, package_name), "Invalid explicit private package name.")
    require(matches(COMMIT, commit), "Exact source commit required.")
    require(matches(PLATFORM, platform), "Explicit supported single Linux platform required.")
    require(matches(WORKFLOW, ci_workflow), "Explicit Project CI workflow path required.")
    require(matches(VERSION, release_version), "Invalid explicit release version.")
    return {"ownerRepo": repository, "packageName": package_name,
            "registry": f"ghcr.io/{repository.split('/')[0].lower()}/{package_name}",
            "commit": commit, "platform": platform, "ciWorkflow": ci_workflow,
            "releaseVersion": release_version}


def check_private_package(expected, package):
    package = record(package)
    owner = record(package.get("owner"))
    require(package.get("package_type") == "container"
            and package.get("visibility") == "private"
            and package.get("name") == expected["packageName"]
            and owner.get("login") == expected["ownerRepo"].split("/")[0],
            "Private registry package identity or visibility is not established.")
    require(positive_int(package.get("id")), "Exact existing package ID required.")
    return package["id"]


def check_prepublication(expected, *, repository, branch, checkout, ci, dispatch, package, image):
    """Compare acquired records. Reacquire source and package just before push.

    Only already-existing private packages are supported. A 404/absent
    package does not prove that first publication will be private.
    """
    expected = record(expected)
    canonical = scope(expected.get("ownerRepo"), expected.get("packageName"),
                      expected.get("commit"), expected.get("platform"),
                      expected.get("ciWorkflow"), expected.get("releaseVersion"))
    require(expected == canonical, "Invalid publication scope.")
    repository, branch, checkout, ci, dispatch, image = map(
        record, (repository, branch, checkout, ci, dispatch, image))
    commit = expected["commit"]
    owner_repo = expected["ownerRepo"]
    default = repository.get("default_branch")
    require(repository_identity(repository, owner_repo) and isinstance(default, str)
            and bool(default) and len(default) <= 255 and not any(ord(c) < 33 for c in default),
            "Repository/default branch evidence mismatch.")
    require(branch.get("name") == default and record(branch.get("commit")).get("sha") == commit,
            "Requested commit is not the observed default-branch tip.")
    require(checkout.get("commit") == commit and checkout.get("clean") is True,
            "Exact clean release checkout required.")
    require(ci.get("head_sha") == commit and ci.get("head_branch") == default
            and ci.get("event") == "push" and ci.get("status") == "completed"
            and ci.get("conclusion") == "success" and ci.get("path") == expected["ciWorkflow"]
            and repository_identity(ci.get("repository"), owner_repo)
            and repository_identity(ci.get("head_repository"), owner_repo)
            and positive_int(ci.get("id")), "Successful exact-source Project CI evidence required.")
    require(dispatch.get("event") == "workflow_dispatch"
            and dispatch.get("repository") == owner_repo
            and dispatch.get("ref") == "refs/heads/" + default
            and dispatch.get("sha") == commit
            and dispatch.get("requestedCommit") == commit
            and all(positive_int(dispatch.get(key)) for key in ("runId", "attempt", "buildNumber")),
            "Exact manually dispatched release context required.")
    package_id = check_private_package(expected, package)
    image_id = image.get("builtImageId")
    require(matches(DIGEST, image_id) and image.get("inspectedImageId") == image_id,
            "Inspected image must match the exact built image ID.")
    require(image.get("platform") == expected["platform"], "Built image platform mismatch.")
    labels = record(image.get("labels"))
    required = {"org.opencontainers.image.source": "https://github.com/" + owner_repo,
                "org.opencontainers.image.revision": commit,
                "org.opencontainers.image.version": expected["releaseVersion"],
                "com.mriekki.project-forge.build-kind": "ci",
                "com.mriekki.project-forge.build-number": str(dispatch["buildNumber"])}
    require(all(labels.get(key) == value for key, value in required.items()),
            "Built image labels do not match the intended source and release.")
    created = labels.get("org.opencontainers.image.created")
    try:
        require(isinstance(created, str) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created),
            "Invalid image creation timestamp.")
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise DeploymentKitError("Invalid image creation timestamp.") from None
    tag = (expected["registry"] + ":sha-" + commit + "-run-" + str(dispatch["runId"])
           + "-attempt-" + str(dispatch["attempt"]))
    require(len(tag.rsplit(":", 1)[1]) <= 128, "Release tag exceeds registry limit.")
    return {**expected, "defaultBranch": default, "projectCiRunId": ci["id"],
            "releaseWorkflowRunId": dispatch["runId"], "releaseAttempt": dispatch["attempt"],
            "buildNumber": dispatch["buildNumber"], "packageId": package_id,
            "localImageId": image_id, "tag": tag,
            "evidenceAuthority": "caller-supplied-unverified", "comparisonOnly": True,
            "publicationAuthorized": False, "authorizesMutation": False}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate registry manifest key.")
        result[key] = value
    return result


def reject_constant(_):
    raise DeploymentKitError("Invalid registry manifest constant.")


def check_manifest_config(manifest_bytes, manifest_digest, expected_config_digest):
    """Compare exact raw manifest bytes and recorded config identity; no I/O.

    This verifies a digest relationship, not the config bytes, platform,
    source-build attestation, access, approval or publication authorization.
    """
    require(matches(DIGEST, manifest_digest) and matches(DIGEST, expected_config_digest),
            "Exact immutable manifest and config digests required.")
    require(isinstance(manifest_bytes, bytes) and 0 < len(manifest_bytes) <= MAX_MANIFEST,
            "Bounded exact registry manifest bytes required.")
    require("sha256:" + hashlib.sha256(manifest_bytes).hexdigest() == manifest_digest,
            "Registry manifest bytes do not match the reported digest.")
    try:
        manifest = record(json.loads(manifest_bytes.decode("utf-8"),
                                    object_pairs_hook=unique_keys, parse_constant=reject_constant))
    except (ValueError, UnicodeError, RecursionError):
        raise DeploymentKitError("Invalid registry manifest bytes.") from None
    media = manifest.get("mediaType")
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2
            and isinstance(media, str) and media in MANIFEST_TYPES
            and "manifests" not in manifest and isinstance(manifest.get("layers"), list),
            "Only a single image manifest is supported; indexes are not accepted.")
    config = record(manifest.get("config"))
    require(config.get("mediaType") == MANIFEST_TYPES[media]
            and matches(DIGEST, config.get("digest"))
            and config["digest"] == expected_config_digest
            and positive_int(config.get("size")),
            "Registry manifest config does not match the exact built image ID.")
    return config["digest"]


def check_published_records(expected, *, prepublication, refreshed, package,
                            pushed_tag, tag_digest, manifest_digest, manifest_bytes):
    """Compare exact raw single-image manifest bytes and built config digest.

    refreshed must be an independently reacquired check_prepublication result
    immediately before the caller attempts push. The caller must authenticate
    all inputs, and acquire tag/manifest evidence from the intended registry.
    """
    expected = record(expected)
    require(expected == scope(expected.get("ownerRepo"), expected.get("packageName"),
                              expected.get("commit"), expected.get("platform"),
                              expected.get("ciWorkflow"), expected.get("releaseVersion")),
            "Invalid publication scope.")
    prepublication, refreshed = map(record, (prepublication, refreshed))
    require(prepublication == refreshed and all(prepublication.get(k) == v for k, v in expected.items())
            and prepublication.get("evidenceAuthority") == "caller-supplied-unverified"
            and prepublication.get("comparisonOnly") is True
            and prepublication.get("publicationAuthorized") is False
            and prepublication.get("authorizesMutation") is False,
            "Prepublication records changed or have conflicting authority.")
    require(all(positive_int(prepublication.get(key)) for key in
                ("packageId", "projectCiRunId", "releaseWorkflowRunId", "releaseAttempt", "buildNumber"))
            and matches(DIGEST, prepublication.get("localImageId")),
            "Invalid prepublication identity fields.")
    expected_tag = (expected["registry"] + ":sha-" + expected["commit"] + "-run-"
                    + str(prepublication["releaseWorkflowRunId"]) + "-attempt-"
                    + str(prepublication["releaseAttempt"]))
    require(prepublication.get("tag") == expected_tag and len(expected_tag.rsplit(":", 1)[1]) <= 128,
            "Invalid prepublication release tag.")
    require(check_private_package(expected, package) == prepublication.get("packageId"),
            "Registry package changed after attempted publication.")
    require(pushed_tag == prepublication.get("tag"), "Unexpected release tag.")
    require(matches(DIGEST, tag_digest) and tag_digest == manifest_digest,
            "Tag and immutable manifest digest are not an exact match.")
    config_digest = check_manifest_config(manifest_bytes, manifest_digest, prepublication["localImageId"])
    # No arbitrary caller fields are forwarded into the shareable projection.
    return {"schemaVersion": 1, "kind": "private-image-publication-record-comparison",
            "ownerRepo": expected["ownerRepo"], "commit": expected["commit"],
            "projectCiRunId": prepublication["projectCiRunId"],
            "releaseWorkflowRunId": prepublication["releaseWorkflowRunId"],
            "releaseAttempt": prepublication["releaseAttempt"],
            "releaseVersion": expected["releaseVersion"], "platform": expected["platform"],
            "localImageId": config_digest, "image": expected["registry"] + "@" + manifest_digest,
            "tag": pushed_tag, "packageId": prepublication["packageId"],
            "reportedVisibility": "private", "comparison": "reported-record-match",
            "evidenceAuthority": "caller-supplied-unverified", "comparisonOnly": True,
            "publicationAuthorized": False, "publicationVerified": False,
            "sourceBuildProvenance": "not-verified", "authorizesMutation": False}


def failure_disposition(*, push_attempted):
    """A caller tracks this flag before invoking push, not after it succeeds."""
    require(type(push_attempted) is bool, "Explicit push-attempt state required.")
    return {"publicationState": "tag-may-have-been-pushed" if push_attempted else "no-push-attempted-by-caller",
            "evidenceAuthority": "caller-supplied-unverified",
            "publicationVerified": False, "rollbackVerified": False, "authorizesMutation": False}
