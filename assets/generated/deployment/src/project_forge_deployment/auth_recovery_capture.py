"""Exact provenance + stopped-Docker adapter for isolated Auth Kit capture.

Internal library only. Never stops/restarts a service, configures a provider,
logs Docker environment or offers an operator-ready Production backup CLI.
The caller independently manages quiescence and must validate service
resumption/health, scheduling, alert receipt and application restore.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types

from .auth_recovery_guard import docker_auth_quiescence_guard
from .errors import DeploymentKitError

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
HELPER_PATH = "tools/project-forge-auth-kit/project_auth_recovery.py"
BASELINE_NAME = "AUTHENTICATION_BASELINE.json"


def _safe_regular(path: Path) -> os.stat_result:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise DeploymentKitError("Managed recovery source contains a symlink.")
    try:
        st = path.lstat()
    except OSError as exc:
        raise DeploymentKitError("Managed recovery source is missing.") from exc
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise DeploymentKitError("Managed recovery source is not a regular owned file.")
    return st


def _load_pinned_helper(
    project_root: Path, reviewed_revision: str, reviewed_sha256: str
):
    """Load exactly reviewed source bytes, not an attacker-modified pathname."""
    if (type(reviewed_revision) is not str or
            REVISION.fullmatch(reviewed_revision) is None or
            type(reviewed_sha256) is not str or
            SHA256.fullmatch(reviewed_sha256) is None):
        raise DeploymentKitError("Exact reviewed Auth component provenance required.")
    root = Path(os.path.abspath(project_root))
    for part in (root, *root.parents):
        if part.is_symlink():
            raise DeploymentKitError("Project root may not contain a symlink.")
    if not root.is_dir():
        raise DeploymentKitError("Generated Project root does not exist.")
    baseline_path = root / BASELINE_NAME
    helper_path = root / HELPER_PATH
    _safe_regular(baseline_path)
    _safe_regular(helper_path)
    try:
        if baseline_path.stat().st_size > 512 * 1024:
            raise DeploymentKitError("Auth baseline is too large.")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise DeploymentKitError("Auth baseline is unreadable.") from exc
    if (type(baseline) is not dict or
            baseline.get("schemaVersion") != 2 or
            baseline.get("component") != "authentication" or
            baseline.get("distribution") != "greenfield-project" or
            baseline.get("revision") != reviewed_revision):
        raise DeploymentKitError("Installed Authentication baseline identity differs from reviewed revision.")
    entries = baseline.get("managedPaths")
    if type(entries) is not list or not entries or len(entries) > 1000:
        raise DeploymentKitError("Installed Authentication managed-file ledger is invalid.")
    matching = []
    seen = set()
    for entry in entries:
        if (type(entry) is not dict or
                set(entry) != {"source", "path", "sha256"} or
                type(entry["path"]) is not str or
                type(entry["sha256"]) is not str or
                SHA256.fullmatch(entry["sha256"]) is None or
                entry["path"] in seen):
            raise DeploymentKitError("Installed Authentication managed-file ledger is malformed.")
        seen.add(entry["path"])
        if entry["path"] == HELPER_PATH:
            matching.append(entry)
    if len(matching) != 1 or matching[0]["sha256"] != reviewed_sha256:
        raise DeploymentKitError("Auth recovery helper is missing from reviewed managed baseline.")

    # Hash and compile the same bytes; no check-then-import path race.
    try:
        with helper_path.open("rb") as source:
            data = source.read(256 * 1024 + 1)
        if (not data or len(data) > 256 * 1024 or
                hashlib.sha256(data).hexdigest() != reviewed_sha256):
            raise DeploymentKitError("Auth recovery helper bytes differ from reviewed release.")
        module = types.ModuleType("_project_forge_verified_auth_recovery")
        module.__file__ = str(helper_path)
        exec(compile(data, str(helper_path), "exec"), module.__dict__)
    except DeploymentKitError:
        raise
    except (OSError, SyntaxError, UnicodeError, ValueError, RuntimeError) as exc:
        raise DeploymentKitError("Reviewed Auth recovery helper cannot be loaded.") from exc
    if not callable(getattr(module, "capture_quiesced_set", None)):
        raise DeploymentKitError("Reviewed Auth recovery helper is missing its capture contract.")
    return module


def capture_reviewed_stopped_auth_project(
    *, project_root: Path, source_data_root: Path, destination: Path,
    declaration: dict, reviewed_auth_revision: str,
    reviewed_recovery_sha256: str, reviewed_docker_binding: dict
) -> dict:
    """Write only a new private capture when exact reviewed Docker is stopped.

    The source/storage, expected image, labels, container name and binding must
    come from separately reviewed Project deployment evidence. The helper's
    accepted SHA and component revision must come from an independent immutable
    release/provenance receipt, not merely the editable local baseline.
    """
    if sys.platform != "linux":
        raise DeploymentKitError("Stopped Auth Project capture is Linux-host only.")
    source = Path(os.path.abspath(source_data_root))
    if type(reviewed_docker_binding) is not dict or set(reviewed_docker_binding) != {
        "container_name", "expected_owner", "expected_environment",
        "expected_image_digest", "expected_data_source",
        "expected_data_destination", "owner_label", "environment_label",
        "required_auth_environment",
    }:
        raise DeploymentKitError("Exact reviewed Docker binding is required.")
    bind_source = reviewed_docker_binding["expected_data_source"]
    if not isinstance(bind_source, Path) or Path(os.path.abspath(bind_source)) != source:
        raise DeploymentKitError("Reviewed Docker data source differs from Auth data root.")
    required = reviewed_docker_binding["required_auth_environment"]
    mount = reviewed_docker_binding["expected_data_destination"]
    if (type(required) is not dict or type(mount) is not str or
            required.get("ProjectForge__Authentication__DbPath") !=
            mount.rstrip("/") + "/auth.sqlite" or
            required.get("ProjectForge__Authentication__DataProtectionKeysPath") !=
            mount.rstrip("/") + "/keys"):
        raise DeploymentKitError("Exact Auth database and key-ring container bindings required.")
    helper = _load_pinned_helper(
        project_root, reviewed_auth_revision, reviewed_recovery_sha256)
    try:
        guard = docker_auth_quiescence_guard(**reviewed_docker_binding)
        proof = guard()
        if (type(proof) is not dict or proof.get("stopped") is not True):
            raise DeploymentKitError("Exact stopped Auth service not proven.")
        report = helper.capture_quiesced_set(
            source, Path(destination), declaration, guard)
    except DeploymentKitError:
        raise
    except Exception as exc:
        # Do not print Docker inspect, private host paths, credential env or
        # key files on failure; never return apparent success.
        raise DeploymentKitError("Reviewed Auth backup capture failed closed.") from exc
    if (type(report) is not dict or
            report.get("backupArtifactIntegrityVerified") is not True or
            report.get("applicationRecoveryReady") is not False or
            report.get("quiescenceGuardRuntimeId") != proof.get("runtimeId") or
            report.get("quiescenceGuardImageDigest") != proof.get("imageDigest")):
        raise DeploymentKitError("Auth recovery helper did not prove expected capture receipt.")
    return report
