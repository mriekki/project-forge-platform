"""Non-destructive workstation SQLite lifecycle helpers."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .errors import DeploymentKitError
from .profiles import config_root


_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_DB_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_METADATA_FILE = "sqlite-local.json"


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _database_file(value: str) -> str:
    if not isinstance(value, str) or _DB_FILE_RE.fullmatch(value) is None or value in {".", ".."}:
        raise DeploymentKitError("databaseFile must be a safe file name without path separators.")
    return value


def _state_root(app_slug: str, environment: str) -> Path:
    return config_root() / "local-apps" / app_slug / environment


def _data_dir(app_slug: str, environment: str) -> Path:
    return _state_root(app_slug, environment) / "data"


def _metadata_path(app_slug: str, environment: str) -> Path:
    return _state_root(app_slug, environment) / _METADATA_FILE


def _database_path(app_slug: str, environment: str, database_file: str) -> Path:
    return _data_dir(app_slug, environment) / database_file


def _load_metadata(app_slug: str, environment: str) -> dict[str, Any] | None:
    path = _metadata_path(app_slug, environment)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentKitError(f"Cannot read local SQLite metadata {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise DeploymentKitError(f"Unsupported local SQLite metadata: {path}")
    return value


def _write_metadata(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _quick_check(path: Path) -> str:
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as error:
        raise DeploymentKitError(f"Local SQLite database is not valid: {path}: {error}") from error
    result = str(row[0]) if row else "missing-result"
    if result.lower() != "ok":
        raise DeploymentKitError(f"Local SQLite quick_check failed for {path}: {result}")
    return result


def local_sqlite_status(
    *, owner_repo: str, environment: str, app_slug: str, database_file: str
) -> dict[str, Any]:
    owner_repo = _owner_repo(owner_repo)
    environment = _slug(environment, "environment")
    app_slug = _slug(app_slug, "appSlug")
    database_file = _database_file(database_file)
    metadata = _load_metadata(app_slug, environment)
    path = _database_path(app_slug, environment, database_file)

    if metadata is not None:
        expected = {
            "ownerRepo": owner_repo,
            "environment": environment,
            "appSlug": app_slug,
            "databaseFile": database_file,
        }
        for key, value in expected.items():
            if metadata.get(key) != value:
                raise DeploymentKitError(
                    f"Local SQLite metadata ownership mismatch for {app_slug}/{environment}: {key}."
                )

    if path.exists() and metadata is None:
        return {
            "schemaVersion": 1,
            "ownerRepo": owner_repo,
            "environment": environment,
            "appSlug": app_slug,
            "databaseFile": database_file,
            "databasePath": str(path),
            "state": "unmanaged-existing",
            "managed": False,
            "present": True,
            "valid": False,
            "mutated": False,
        }

    if not path.exists():
        return {
            "schemaVersion": 1,
            "ownerRepo": owner_repo,
            "environment": environment,
            "appSlug": app_slug,
            "databaseFile": database_file,
            "databasePath": str(path),
            "state": "missing",
            "managed": metadata is not None,
            "present": False,
            "valid": False,
            "mutated": False,
        }

    _quick_check(path)
    return {
        "schemaVersion": 1,
        "ownerRepo": owner_repo,
        "environment": environment,
        "appSlug": app_slug,
        "databaseFile": database_file,
        "databasePath": str(path),
        "state": "ready",
        "managed": True,
        "present": True,
        "valid": True,
        "bytes": path.stat().st_size,
        "mutated": False,
    }


def ensure_local_sqlite(
    *, owner_repo: str, environment: str, app_slug: str, database_file: str
) -> dict[str, Any]:
    owner_repo = _owner_repo(owner_repo)
    environment = _slug(environment, "environment")
    app_slug = _slug(app_slug, "appSlug")
    database_file = _database_file(database_file)

    status = local_sqlite_status(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        database_file=database_file,
    )
    if status["state"] == "unmanaged-existing":
        raise DeploymentKitError(
            "Refusing to adopt an existing unmanaged local SQLite database automatically. "
            "Review its ownership/data before using or moving it."
        )
    if status["state"] == "ready":
        return status

    path = _database_path(app_slug, environment, database_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA user_version")
            connection.commit()
    except sqlite3.DatabaseError as error:
        raise DeploymentKitError(f"Unable to create local SQLite database {path}: {error}") from error

    metadata = {
        "schemaVersion": 1,
        "ownerRepo": owner_repo,
        "environment": environment,
        "appSlug": app_slug,
        "databaseFile": database_file,
    }
    _write_metadata(_metadata_path(app_slug, environment), metadata)
    _quick_check(path)
    result = local_sqlite_status(
        owner_repo=owner_repo,
        environment=environment,
        app_slug=app_slug,
        database_file=database_file,
    )
    result["mutated"] = True
    result["created"] = True
    return result
