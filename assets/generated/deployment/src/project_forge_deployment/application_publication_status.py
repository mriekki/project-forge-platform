"""Read-only #205 adapter for the existing private application publisher receipt.

Checks GitHub run/artifact metadata and exact archive bytes. It does not verify
registry availability, cryptographic source-build provenance, approval, or host
state. Supports the existing generated Project publisher contract only.
"""
import hashlib
import io
import re
import stat
import subprocess
import zipfile
import zlib

from .evidence_records import github_get, read_blob, repository_name, COMMIT, read_record

MAX_ARCHIVE = 1024 * 1024
MAX_RECEIPT = 32 * 1024
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
VERSION = re.compile(r"[0-9]+[.][0-9]+[.][0-9]+(?:[-+][0-9A-Za-z.-]+)?")
RECEIPT_FIELDS = {
    "schemaVersion", "ownerRepo", "image", "tag", "commit", "defaultBranch",
    "projectCiRunId", "releaseWorkflowRunId", "releaseAttempt", "buildNumber",
    "releaseVersion", "localImageId", "platform", "visibility",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def positive_id(value):
    return type(value) is int and 0 < value < 2**63


def download_archive(repository, artifact_id):
    repository_name(repository)
    require(positive_id(artifact_id), "invalid artifact identity")
    response = subprocess.run(
        ["gh", "api", "--hostname", "github.com", "--method", "GET",
         f"repos/{repository}/actions/artifacts/{artifact_id}/zip"],
        capture_output=True, check=True, timeout=60, stdin=subprocess.DEVNULL,
    )
    require(isinstance(response.stdout, bytes) and len(response.stdout) <= MAX_ARCHIVE,
            "invalid publication archive size")
    return response.stdout


def read_receipt(archive, *, size, digest, member_name="release-image.json"):
    require(member_name in {"release-image.json", "proof.json"}, "unsupported evidence member name")
    require(isinstance(archive, bytes) and positive_id(size)
            and len(archive) == size <= MAX_ARCHIVE and matches(DIGEST, digest)
            and "sha256:" + hashlib.sha256(archive).hexdigest() == digest,
            "publication archive identity mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            require(len(members) == 1, "expected one receipt member")
            entry = members[0]
            mode = stat.S_IFMT(entry.external_attr >> 16)
            require(entry.filename == member_name and not entry.is_dir()
                    and mode in (0, stat.S_IFREG) and not entry.flag_bits & 1
                    and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and 0 < entry.file_size <= MAX_RECEIPT,
                    "unsupported receipt archive member")
            with bundle.open(entry) as handle:
                data = handle.read(MAX_RECEIPT + 1)
            require(len(data) == entry.file_size, "invalid receipt member size")
        return read_record(data)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error):
        raise ValueError("invalid publication archive") from None


def run_identity(run, repository, run_id, *, path, event, commit=None, branch=None):
    repo, head = run.get("repository"), run.get("head_repository")
    require(isinstance(repo, dict) and isinstance(head, dict)
            and repo.get("full_name") == head.get("full_name") == repository
            and positive_id(repo.get("id")) and repo["id"] == head.get("id")
            and run.get("id") == run_id and run.get("path") == path
            and run.get("event") == event and run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and matches(COMMIT, run.get("head_sha"))
            and isinstance(run.get("head_branch"), str) and bool(run["head_branch"])
            and (commit is None or run["head_sha"] == commit)
            and (branch is None or run["head_branch"] == branch),
            "publication or CI workflow identity inconsistent")
    return repo["id"]


def publication_status(repository, run_id, *, get=github_get, download=download_archive):
    """Observe one explicitly selected historical publisher run, not latest desired state."""
    repository_name(repository)
    require(positive_id(run_id), "exact publication run required")
    endpoint = f"repos/{repository}/actions/runs/{run_id}"
    run = get(endpoint)
    repo_id = run_identity(run, repository, run_id, path=".github/workflows/publish-image.yml",
                           event="workflow_dispatch")
    commit, branch = run["head_sha"], run["head_branch"]
    require(positive_id(run.get("run_attempt")) and positive_id(run.get("run_number")),
            "invalid publication run attempt or number")
    manifest_data, manifest_blob = read_blob(repository, commit, "PROJECT_BOOTSTRAP.json", get)
    manifest = read_record(manifest_data)
    project = manifest.get("project")
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2
            and manifest.get("state") == "generated" and isinstance(project, dict)
            and project.get("repository") == repository and matches(SLUG, project.get("slug")),
            "unsupported generated Project identity")
    slug = project["slug"]
    listing = get(endpoint + "/artifacts?per_page=100")
    artifacts = listing.get("artifacts")
    require(isinstance(artifacts, list) and type(listing.get("total_count")) is int
            and listing["total_count"] == len(artifacts) <= 100
            and all(isinstance(a, dict) for a in artifacts), "incomplete artifact listing")
    candidates = [a for a in artifacts if a.get("name") == "immutable-private-release"]
    require(len(candidates) == 1, "publication artifact missing or ambiguous")
    artifact = candidates[0]
    binding = artifact.get("workflow_run")
    artifact_id, size, digest = artifact.get("id"), artifact.get("size_in_bytes"), artifact.get("digest")
    require(artifact.get("expired") is False and positive_id(artifact_id)
            and positive_id(size) and size <= MAX_ARCHIVE and matches(DIGEST, digest)
            and isinstance(binding, dict) and binding.get("id") == run_id
            and binding.get("repository_id") == binding.get("head_repository_id") == repo_id
            and binding.get("head_sha") == commit and binding.get("head_branch") == branch,
            "publication artifact unavailable or incorrectly scoped")
    receipt = read_receipt(download(repository, artifact_id), size=size, digest=digest)
    registry = f"ghcr.io/{repository.split('/')[0].lower()}/{slug}"
    image_pattern = re.compile(re.escape(registry) + r"@sha256:[0-9a-f]{64}")
    tag = f"{registry}:sha-{commit}-run-{run_id}-attempt-{run['run_attempt']}"
    ci_id = receipt.get("projectCiRunId")
    require(set(receipt) == RECEIPT_FIELDS and type(receipt.get("schemaVersion")) is int
            and receipt["schemaVersion"] == 1 and receipt.get("ownerRepo") == repository
            and receipt.get("commit") == commit and receipt.get("defaultBranch") == branch
            and receipt.get("releaseWorkflowRunId") == str(run_id)
            and receipt.get("releaseAttempt") == str(run["run_attempt"])
            and receipt.get("buildNumber") == str(run["run_number"])
            and positive_id(ci_id) and receipt.get("tag") == tag
            and matches(image_pattern, receipt.get("image"))
            and matches(DIGEST, receipt.get("localImageId"))
            and matches(VERSION, receipt.get("releaseVersion"))
            and receipt.get("platform") == "linux/amd64" and receipt.get("visibility") == "private",
            "receipt identity or supported publisher contract mismatch")
    ci = get(f"repos/{repository}/actions/runs/{ci_id}")
    require(run_identity(ci, repository, ci_id, path=".github/workflows/ci.yml", event="push",
                         commit=commit, branch=branch) == repo_id,
            "CI repository identity mismatch")
    # Refuse observed reruns or changed artifact metadata during acquisition.
    require(get(endpoint) == run and get(endpoint + "/artifacts?per_page=100") == listing,
            "publication run or artifacts changed during acquisition")
    return {
        "schemaVersion": 1, "projectRepository": repository, "projectRepositoryId": repo_id, "appSlug": slug,
        "sourceCommit": commit, "defaultBranch": branch, "registryImage": receipt["image"],
        "recordedLocalImageId": receipt["localImageId"], "releaseVersion": receipt["releaseVersion"],
        "publicationRunId": run_id, "publicationAttempt": run["run_attempt"], "projectCiRunId": ci_id,
        "artifactId": artifact_id, "archiveDigest": digest, "manifestGitBlob": manifest_blob,
        "evidenceAuthority": "github-run-and-artifact-record-consistency",
        "publisherRecord": "matched", "sourceBuildProvenance": "not-verified",
        "registryAvailability": "not-evaluated", "approvedDesiredRelease": "not-evaluated",
        "compatibility": "not-evaluated", "authorizesMutation": False,
    }


def compare_managed_image(publication, runtime):
    """Compare only inventory's reported managed image, never infer actual running digest."""
    if publication is None or not isinstance(runtime, dict):
        return "unknown"
    scope = runtime.get("scope")
    if (not isinstance(scope, dict)
            or scope.get("ownerRepo") != publication["projectRepository"]
            or scope.get("appSlug") != publication["appSlug"]
            or runtime.get("freshness") != "within-reported-window"
            or not isinstance(runtime.get("managedRegistryImage"), str)):
        return "unknown"
    return ("reported-managed-image-matches-publisher-record"
            if runtime["managedRegistryImage"] == publication["registryImage"]
            else "reported-managed-image-differs-from-publisher-record")
