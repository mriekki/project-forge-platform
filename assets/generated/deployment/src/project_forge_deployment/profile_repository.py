"""Personal GitHub project-forge-profile repository and validated local cache."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .portable_profile import (
    BUNDLE_KIND,
    BUNDLE_SCHEMA_VERSION,
    apply_import,
    export_bundle,
    plan_import,
    validate_bundle,
)
from .profiles import config_root


PROFILE_REPOSITORY = "project-forge-profile"
PROFILE_FILE = "project-forge-profile.json"
PERSONAL_PROFILE_WRITE_PHRASE = "[PERSONAL PROFILE WRITE]"
LOCAL_PROFILE_SYNC_PHRASE = "[LOCAL PROFILE SYNC]"


def _gh() -> str:
    path = shutil.which("gh")
    if path is None:
        raise DeploymentKitError("GitHub CLI is unavailable; personal profile sync cannot reach GitHub.")
    return path


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_gh(), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"


def _not_found(result: subprocess.CompletedProcess[str]) -> bool:
    text = (result.stderr + "\n" + result.stdout).lower()
    return result.returncode != 0 and (
        "http 404" in text
        or "not found" in text
        or "could not resolve to a repository" in text
        or "could not resolve to a resource" in text
    )


def authenticated_login() -> str:
    result = _run_gh(["api", "user"])
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot resolve authenticated GitHub identity: {_detail(result)}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DeploymentKitError("GitHub CLI returned malformed authenticated-user data.") from error
    login = value.get("login") if isinstance(value, dict) else None
    if not isinstance(login, str) or not login:
        raise DeploymentKitError("GitHub CLI authenticated-user data omitted login.")
    return login


def repository_status() -> dict[str, Any]:
    login = authenticated_login()
    full_name = f"{login}/{PROFILE_REPOSITORY}"
    result = _run_gh(["api", f"repos/{full_name}"])
    if _not_found(result):
        return {
            "login": login,
            "repository": full_name,
            "state": "missing",
            "private": None,
            "mutated": False,
        }
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot inspect personal Project Forge profile repository: {_detail(result)}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DeploymentKitError("GitHub CLI returned malformed repository data.") from error
    if not isinstance(value, dict):
        raise DeploymentKitError("GitHub CLI returned malformed repository data.")
    owner = (value.get("owner") or {}).get("login") if isinstance(value.get("owner"), dict) else None
    name = value.get("name")
    private = value.get("private")
    if owner != login or name != PROFILE_REPOSITORY or type(private) is not bool:
        raise DeploymentKitError("Personal Project Forge profile repository identity could not be verified.")
    if not private:
        raise DeploymentKitError(
            f"Personal Project Forge profile repository {full_name} is public; it must be private before Project Forge will use it."
        )
    return {
        "login": login,
        "repository": full_name,
        "state": "ready",
        "private": True,
        "mutated": False,
    }


def _profile_dirs() -> tuple[Path, Path, Path]:
    root = config_root() / "profile"
    return root / "current", root / "last-known-good", root / "sync-state.json"


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise DeploymentKitError(f"Refusing to write profile cache through a symbolic link: {path}")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def cache_valid_profile(bundle: dict[str, Any], *, source: str, remote_sha: str | None) -> dict[str, Any]:
    normalized = validate_bundle(bundle)
    current, lkg, state_path = _profile_dirs()
    current_file = current / PROFILE_FILE
    lkg_file = lkg / PROFILE_FILE
    _write_json_atomic(current_file, normalized)
    _write_json_atomic(lkg_file, normalized)
    state = {
        "schemaVersion": 1,
        "lastValidatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": source,
        "remoteSha": remote_sha,
        "current": str(current_file),
        "lastKnownGood": str(lkg_file),
    }
    _write_json_atomic(state_path, state)
    return state


def load_last_known_good() -> dict[str, Any]:
    _, lkg, _ = _profile_dirs()
    path = lkg / PROFILE_FILE
    if path.is_symlink() or not path.is_file():
        raise DeploymentKitError("No validated last-known-good personal Project Forge profile is cached on this workstation.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read last-known-good personal Project Forge profile: {error}") from error
    return validate_bundle(value)


def _empty_bundle() -> dict[str, Any]:
    return {"schemaVersion": BUNDLE_SCHEMA_VERSION, "kind": BUNDLE_KIND, "targets": []}


def fetch_remote_profile() -> dict[str, Any]:
    status = repository_status()
    if status["state"] != "ready":
        raise DeploymentKitError(f"Personal Project Forge profile repository does not exist: {status['repository']}")
    full_name = status["repository"]
    result = _run_gh(["api", f"repos/{full_name}/contents/{PROFILE_FILE}"])
    if _not_found(result):
        return {"bundle": _empty_bundle(), "sha": None, "repository": full_name}
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot fetch personal Project Forge profile: {_detail(result)}")
    try:
        value = json.loads(result.stdout)
        encoded = value["content"]
        sha = value["sha"]
        if value.get("encoding") != "base64" or not isinstance(encoded, str) or not isinstance(sha, str):
            raise ValueError("unexpected content payload")
        decoded = base64.b64decode(encoded.encode("ascii"), validate=False).decode("utf-8")
        bundle = validate_bundle(json.loads(decoded))
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(
            "Remote personal Project Forge profile is invalid; the validated local last-known-good profile was not replaced."
        ) from error
    return {"bundle": bundle, "sha": sha, "repository": full_name}


def sync_profile(*, apply: bool) -> dict[str, Any]:
    try:
        remote = fetch_remote_profile()
        state = cache_valid_profile(remote["bundle"], source="github", remote_sha=remote["sha"])
        bundle = remote["bundle"]
        source = "github"
        remote_error = None
    except DeploymentKitError as error:
        bundle = load_last_known_good()
        state = {"source": "last-known-good"}
        source = "last-known-good"
        remote_error = str(error)

    plan = plan_import(bundle)
    result: dict[str, Any] = {
        "source": source,
        "targetCount": len(bundle["targets"]),
        "importPlan": plan,
        "cache": state,
        "remoteError": remote_error,
        "mutated": False,
    }
    if apply and not plan["hasConflicts"]:
        applied = apply_import(plan)
        result["importResult"] = applied
        result["mutated"] = bool(applied["mutated"])
    elif apply and plan["hasConflicts"]:
        result["blocked"] = "Local target-definition conflicts require explicit resolution; no target was overwritten."
    return result


def _create_repository(login: str) -> None:
    full_name = f"{login}/{PROFILE_REPOSITORY}"
    result = _run_gh(
        [
            "repo",
            "create",
            full_name,
            "--private",
            "--description",
            "Portable non-secret Project Forge developer environment definitions",
        ]
    )
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot create personal Project Forge profile repository: {_detail(result)}")
    status = repository_status()
    if status["state"] != "ready" or not status["private"]:
        raise DeploymentKitError("Personal Project Forge profile repository creation returned without a verified private repository.")


def _put_remote_profile(repository: str, bundle: dict[str, Any], *, current_sha: str | None) -> str:
    normalized = validate_bundle(bundle)
    encoded = base64.b64encode((json.dumps(normalized, indent=2) + "\n").encode("utf-8")).decode("ascii")
    args = [
        "api",
        "--method",
        "PUT",
        f"repos/{repository}/contents/{PROFILE_FILE}",
        "-f",
        "message=Update personal Project Forge profile",
        "-f",
        f"content={encoded}",
    ]
    if current_sha:
        args.extend(["-f", f"sha={current_sha}"])
    result = _run_gh(args)
    if result.returncode != 0:
        raise DeploymentKitError(f"Cannot publish personal Project Forge profile: {_detail(result)}")
    try:
        value = json.loads(result.stdout)
        sha = value["content"]["sha"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise DeploymentKitError("GitHub returned malformed profile publication evidence.") from error
    if not isinstance(sha, str) or not sha:
        raise DeploymentKitError("GitHub profile publication omitted content SHA.")
    return sha


def ensure_profile_repository() -> dict[str, Any]:
    status = repository_status()
    created = False
    if status["state"] == "missing":
        _create_repository(status["login"])
        created = True
        status = repository_status()
    remote = fetch_remote_profile()
    if remote["sha"] is None:
        local = export_bundle(None)
        sha = _put_remote_profile(status["repository"], local, current_sha=None)
        cache = cache_valid_profile(local, source="github", remote_sha=sha)
        return {
            "repository": status["repository"],
            "createdRepository": created,
            "publishedInitialProfile": True,
            "targetCount": len(local["targets"]),
            "cache": cache,
            "mutated": True,
        }
    cache = cache_valid_profile(remote["bundle"], source="github", remote_sha=remote["sha"])
    return {
        "repository": status["repository"],
        "createdRepository": created,
        "publishedInitialProfile": False,
        "targetCount": len(remote["bundle"]["targets"]),
        "cache": cache,
        "mutated": created,
    }


def _merge_non_conflicting(remote: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    remote = validate_bundle(remote)
    local = validate_bundle(local)
    by_name = {item["targetName"]: item for item in remote["targets"]}
    conflicts: list[str] = []
    for item in local["targets"]:
        current = by_name.get(item["targetName"])
        if current is not None and current != item:
            conflicts.append(item["targetName"])
            continue
        by_name[item["targetName"]] = item
    if conflicts:
        raise DeploymentKitError(
            "Personal profile publish found conflicting existing definitions: "
            + ", ".join(sorted(conflicts))
            + ". Resolve explicitly; remote definitions were not overwritten."
        )
    return validate_bundle(
        {
            "schemaVersion": BUNDLE_SCHEMA_VERSION,
            "kind": BUNDLE_KIND,
            "targets": [by_name[name] for name in sorted(by_name)],
        }
    )


def publish_profile() -> dict[str, Any]:
    status = repository_status()
    if status["state"] != "ready":
        raise DeploymentKitError("Create/ensure the private personal Project Forge profile repository before publishing.")
    remote = fetch_remote_profile()
    local = export_bundle(None)
    merged = _merge_non_conflicting(remote["bundle"], local)
    if merged == remote["bundle"]:
        cache = cache_valid_profile(merged, source="github", remote_sha=remote["sha"])
        return {
            "repository": status["repository"],
            "status": "already-current",
            "targetCount": len(merged["targets"]),
            "cache": cache,
            "mutated": False,
        }
    sha = _put_remote_profile(status["repository"], merged, current_sha=remote["sha"])
    cache = cache_valid_profile(merged, source="github", remote_sha=sha)
    return {
        "repository": status["repository"],
        "status": "published",
        "targetCount": len(merged["targets"]),
        "cache": cache,
        "mutated": True,
    }
