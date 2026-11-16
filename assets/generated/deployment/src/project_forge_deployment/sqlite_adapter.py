"""SQLite persistence adapter for Kit-managed application runtimes."""

from __future__ import annotations

import base64
import hashlib
import json
import posixpath
import re
import shlex
import subprocess
from typing import Any, Iterable

from .app_runtime import APP_ROOT
from .box_platform import platform_status
from .errors import DeploymentKitError
from .profiles import load_profile
from .recovery_scope import normalize_recovery_scope, public_recovery_scope, recovery_evidence, recovery_readiness
from .sqlite_adapter_remote import REMOTE_SCRIPT
from .ssh import ssh_args, verify_access

SQLITE_SCHEMA_VERSION = 1
SQLITE_IMPORT_WRITE_PHRASE = "[SQLITE IMPORT WRITE]"
PRODUCTION_SQLITE_IMPORT_WRITE_PHRASE = "[PRODUCTION SQLITE IMPORT]"
SQLITE_BACKUP_WRITE_PHRASE = "[SQLITE BACKUP WRITE]"
PRODUCTION_SQLITE_BACKUP_WRITE_PHRASE = "[PRODUCTION SQLITE BACKUP]"
SQLITE_MIGRATE_WRITE_PHRASE = "[SQLITE MIGRATE WRITE]"
PRODUCTION_SQLITE_MIGRATE_WRITE_PHRASE = "[PRODUCTION SQLITE MIGRATE]"
SQLITE_ROLLBACK_CHECK_PHRASE = "[SQLITE ROLLBACK CHECK]"
PRODUCTION_SQLITE_ROLLBACK_CHECK_PHRASE = "[PRODUCTION SQLITE ROLLBACK CHECK]"

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$")
_RUN_AS_RE = re.compile(r"^[0-9]+(?::[0-9]+)?$")
_DB_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_RE = re.compile(r"^/srv/[A-Za-z0-9._/+-]+$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PUBLIC_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _slug(value: str, field: str) -> str:
    if not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None:
        raise DeploymentKitError(f"{field} must use lowercase letters, digits, and internal hyphens.")
    return value


def _owner_repo(value: str) -> str:
    if not isinstance(value, str) or _REPO_RE.fullmatch(value) is None:
        raise DeploymentKitError("ownerRepo must use GitHub owner/repository form without URL syntax.")
    return value


def _image(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_RE.fullmatch(value) is None:
        raise DeploymentKitError("image must be an immutable image reference ending in @sha256:<64 lowercase hex>.")
    return value


def _run_as(value: str) -> str:
    if not isinstance(value, str) or _RUN_AS_RE.fullmatch(value) is None:
        raise DeploymentKitError("runAs must be a numeric UID or UID:GID.")
    return value


def _database_file(value: str) -> str:
    if not isinstance(value, str) or _DB_FILE_RE.fullmatch(value) is None or value in {".", ".."}:
        raise DeploymentKitError("databaseFile must be a safe file name without path separators.")
    return value


def _source_database(value: str) -> str:
    if not isinstance(value, str) or _SOURCE_RE.fullmatch(value) is None:
        raise DeploymentKitError("sourceDatabase must be a safe absolute path under /srv.")
    normalized = posixpath.normpath(value)
    if normalized != value or "/../" in f"{value}/":
        raise DeploymentKitError("sourceDatabase must not contain path traversal or normalization changes.")
    if value.startswith(APP_ROOT + "/"):
        raise DeploymentKitError("sourceDatabase must be outside the Kit-managed application root.")
    return value


def _normalize_env(items: dict[str, str] | Iterable[tuple[str, str]]) -> dict[str, str]:
    pairs = items.items() if isinstance(items, dict) else items
    result: dict[str, str] = {}
    for key, value in pairs:
        if not isinstance(key, str) or _ENV_KEY_RE.fullmatch(key) is None:
            raise DeploymentKitError(f"Invalid maintenance environment variable name: {key!r}")
        if key in result:
            raise DeploymentKitError(f"Duplicate maintenance environment variable: {key}")
        if not isinstance(value, str) or any(ch in value for ch in ("\x00", "\n", "\r")):
            raise DeploymentKitError(f"Maintenance environment variable {key} contains unsupported control characters.")
        result[key] = value
    if not result:
        raise DeploymentKitError("At least one maintenance environment value is required.")
    return dict(sorted(result.items()))


def reservation_sha(*, owner_repo: str, environment: str, app_slug: str, run_as: str, database_file: str) -> str:
    value = {
        "schemaVersion": SQLITE_SCHEMA_VERSION,
        "adapter": "sqlite",
        "ownerRepo": owner_repo,
        "environment": environment,
        "appSlug": app_slug,
        "runAs": run_as,
        "databaseFile": database_file,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize_sqlite_request(
    *, owner_repo: str, environment: str, app_slug: str, image: str,
    maintenance_environment: dict[str, str] | Iterable[tuple[str, str]],
    run_as: str | None = None, database_file: str | None = None,
    source_database: str | None = None, first_install: bool = False,
    recovery_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = {
        "ownerRepo": _owner_repo(owner_repo),
        "environment": _slug(environment, "environment"),
        "appSlug": _slug(app_slug, "appSlug"),
        "image": _image(image),
        "maintenanceEnvironment": _normalize_env(maintenance_environment),
        "firstInstall": bool(first_install),
        "runAs": _run_as(run_as) if run_as is not None else None,
        "databaseFile": _database_file(database_file) if database_file is not None else None,
        "sourceDatabase": _source_database(source_database) if source_database is not None else None,
        "recoveryScope": normalize_recovery_scope(recovery_scope),
    }
    if request["sourceDatabase"] is not None:
        if request["runAs"] is None or request["databaseFile"] is None:
            raise DeploymentKitError("SQLite import requires runAs and databaseFile.")
        if posixpath.basename(request["sourceDatabase"]) != request["databaseFile"]:
            raise DeploymentKitError("sourceDatabase file name must match databaseFile.")
    if request["firstInstall"] and (request["runAs"] is None or request["databaseFile"] is None):
        raise DeploymentKitError("First-install SQLite migration requires runAs and databaseFile.")
    return request


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode("ascii")


def _public_label_keys(keys: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(keys, (list, tuple)) or not 1 <= len(keys) <= 16:
        raise DeploymentKitError("Image preparation requires 1-16 explicitly public label keys.")
    if any(not isinstance(key, str) or _PUBLIC_LABEL_RE.fullmatch(key) is None for key in keys):
        raise DeploymentKitError("Image preparation label keys must be safe public metadata names.")
    if len(set(keys)) != len(keys):
        raise DeploymentKitError("Image preparation label keys must be unique.")
    return tuple(keys)


def _prepared_image_id(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_ID_RE.fullmatch(value) is None:
        raise DeploymentKitError("Bound SQLite maintenance requires an exact sha256 Docker image ID.")
    return value


def build_remote_script(spec: dict[str, Any] | None = None) -> str:
    spec = spec or {}
    prepared_id = spec.get("preparedImageId")
    if prepared_id is not None:
        _prepared_image_id(prepared_id)
    keys = spec.get("publicLabelKeys", ())
    if keys:
        keys = _public_label_keys(keys)
    env = spec.get("maintenanceEnvironment", {})
    recovery_payload = json.dumps(spec.get("recoveryEvidence", {}), sort_keys=True, separators=(",", ":"))
    replacements = {
        "__APP_ROOT__": APP_ROOT,
        "__SQLITE_SCHEMA_VERSION__": str(SQLITE_SCHEMA_VERSION),
        "__OWNER_B64__": _b64(spec.get("ownerRepo", "")),
        "__ENV_B64__": _b64(spec.get("environment", "")),
        "__APP_B64__": _b64(spec.get("appSlug", "")),
        "__IMAGE_B64__": _b64(spec.get("image", "")),
        "__PREPARED_IMAGE_ID__": prepared_id or "",
        "__PUBLIC_LABEL_KEYS_B64__": _b64("\n".join(keys) + "\n") if keys else "",
        "__RUN_AS_B64__": _b64(spec.get("runAs") or ""),
        "__DB_FILE_B64__": _b64(spec.get("databaseFile") or ""),
        "__SOURCE_DB_B64__": _b64(spec.get("sourceDatabase") or ""),
        "__FIRST_INSTALL__": "true" if spec.get("firstInstall") else "false",
        "__RESERVATION_SHA__": spec.get("reservationSha256", ""),
        "__ENV_KEYS__": " ".join(f"'{_b64(k)}'" for k in env),
        "__ENV_VALUES__": " ".join(f"'{_b64(v)}'" for v in env.values()),
        "__RECOVERY_EVIDENCE_B64__": _b64(recovery_payload),
    }
    script = REMOTE_SCRIPT
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    if "__" in script:
        raise DeploymentKitError("Internal SQLite adapter script contains an unresolved placeholder.")
    return script


def _parse_inventory(output: str) -> dict[str, Any]:
    summary: dict[str, str] = {}
    adapters: list[dict[str, Any]] = []
    for raw in output.splitlines():
        if not raw:
            continue
        parts = raw.split("\t")
        if parts[0] == "SUMMARY":
            if len(parts) != 3 or parts[1] in summary:
                raise DeploymentKitError("Malformed or duplicate SQLite inventory summary.")
            summary[parts[1]] = parts[2]
            continue
        if parts[0] != "SQLITE" or len(parts) != 12:
            raise DeploymentKitError("Malformed SQLite inventory record.")
        if parts[7] not in {"true", "false"} or parts[10] not in {"true", "false"}:
            raise DeploymentKitError("Malformed SQLite inventory boolean value.")
        try:
            database_bytes = int(parts[8]); backup_count = int(parts[9])
        except ValueError as error:
            raise DeploymentKitError("Malformed SQLite inventory numeric value.") from error
        if re.fullmatch(r"[0-9a-f]{64}", parts[6]) is None:
            raise DeploymentKitError("Malformed SQLite reservation fingerprint.")
        adapters.append({
            "ownerRepo": _owner_repo(parts[1]), "environment": _slug(parts[2], "environment"),
            "appSlug": _slug(parts[3], "appSlug"), "runAs": _run_as(parts[4]),
            "databaseFile": _database_file(parts[5]), "reservationSha256": parts[6],
            "databasePresent": parts[7] == "true", "databaseBytes": database_bytes,
            "backupCount": backup_count, "managedRuntimeRunning": parts[10] == "true",
            "currentRuntimeImage": parts[11] or None,
        })
    if set(summary) != {"sqliteCount"}:
        raise DeploymentKitError("SQLite inventory omitted sqliteCount.")
    try:
        count = int(summary["sqliteCount"])
    except ValueError as error:
        raise DeploymentKitError("Malformed SQLite inventory count.") from error
    if count != len(adapters):
        raise DeploymentKitError("SQLite inventory count does not match records.")
    return {"sqlite": sorted(adapters, key=lambda item: (item["appSlug"], item["environment"]))}


def _run_remote(profile: dict[str, Any], address: str, action: str, *, spec: dict[str, Any] | None = None, expected_reservation_sha: str = "") -> str:
    if action not in {"inventory", "import", "backup", "migrate", "rollback-check"}:
        raise DeploymentKitError(f"Unsupported SQLite adapter action: {action}")
    args = [action]
    if action != "inventory":
        args.extend([expected_reservation_sha or "NONE", profile["user"]])
    completed = subprocess.run(
        ssh_args(profile, address, command="sudo -n bash -s -- " + " ".join(args)),
        input=build_remote_script(spec).encode("utf-8"), check=False, capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote SQLite adapter {action} failed: {detail}")
    return stdout


def sqlite_inventory(name: str) -> dict[str, Any]:
    profile = load_profile(name); evidence = verify_access(profile)
    result = _parse_inventory(_run_remote(profile, evidence["address"], "inventory"))
    result.update(targetName=name, verifiedAddress=evidence["address"], mutated=False)
    return result


def _snapshot(inventory: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"sqlite": inventory["sqlite"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _find(inventory: dict[str, Any], app_slug: str, environment: str) -> dict[str, Any] | None:
    return next((item for item in inventory["sqlite"] if item["appSlug"] == app_slug and item["environment"] == environment), None)


def _require_ready_platform(name: str) -> None:
    state = platform_status(name)["state"]
    if state != "ready":
        raise DeploymentKitError(f"SQLite operation requires a ready shared platform; target '{name}' is '{state}'.")


def _reservation_from_request(request: dict[str, Any]) -> dict[str, Any]:
    if request["runAs"] is None or request["databaseFile"] is None:
        raise DeploymentKitError("SQLite reservation requires runAs and databaseFile.")
    return {
        "runAs": request["runAs"], "databaseFile": request["databaseFile"],
        "reservationSha256": reservation_sha(owner_repo=request["ownerRepo"], environment=request["environment"], app_slug=request["appSlug"], run_as=request["runAs"], database_file=request["databaseFile"]),
    }


def plan_sqlite_operation(
    name: str,
    action: str,
    request: dict[str, Any],
    *,
    production: bool = False,
) -> dict[str, Any]:
    if action not in {"import", "backup", "migrate", "rollback-check"}:
        raise DeploymentKitError("Unsupported SQLite plan action.")
    if not isinstance(production, bool):
        raise DeploymentKitError("SQLite Production classification must be a boolean.")
    production_classified = production or request["environment"] == "production"
    _require_ready_platform(name)
    inventory = sqlite_inventory(name)
    existing = _find(inventory, request["appSlug"], request["environment"])
    expected_sha = existing["reservationSha256"] if existing else ""
    if existing and existing["ownerRepo"] != request["ownerRepo"]:
        raise DeploymentKitError("SQLite reservation ownership does not match the requested repository.")
    spec = dict(request)
    if action == "import":
        if request["sourceDatabase"] is None:
            raise DeploymentKitError("SQLite import requires sourceDatabase.")
        if existing:
            raise DeploymentKitError("SQLite import requires an unreserved destination.")
        spec.update(_reservation_from_request(request))
    elif action == "migrate" and request["firstInstall"]:
        if existing:
            raise DeploymentKitError("First-install SQLite migration requires an unreserved destination.")
        spec.update(_reservation_from_request(request))
    else:
        if existing is None:
            raise DeploymentKitError(f"SQLite {action} requires an existing adapter reservation.")
        if request["runAs"] is not None and request["runAs"] != existing["runAs"]:
            raise DeploymentKitError("Requested runAs does not match the existing SQLite reservation.")
        if request["databaseFile"] is not None and request["databaseFile"] != existing["databaseFile"]:
            raise DeploymentKitError("Requested databaseFile does not match the existing SQLite reservation.")
        spec.update(runAs=existing["runAs"], databaseFile=existing["databaseFile"], reservationSha256=existing["reservationSha256"])
        if action in {"backup", "migrate", "rollback-check"} and not existing["databasePresent"]:
            raise DeploymentKitError(f"SQLite {action} requires an existing database.")
    creates_verified_backup = bool(action == "backup" or (action == "migrate" and not request["firstInstall"]))
    recovery_scope = request["recoveryScope"]
    spec["recoveryEvidence"] = recovery_evidence(
        recovery_scope,
        database_backup_verified=creates_verified_backup,
    )
    return {
        "targetName": name, "action": action, "ownerRepo": request["ownerRepo"],
        "environment": request["environment"], "productionClassified": production_classified,
        "appSlug": request["appSlug"], "image": request["image"],
        "databaseFile": spec["databaseFile"], "runAs": spec["runAs"],
        "sourceDatabase": request["sourceDatabase"] if action == "import" else None,
        "firstInstall": bool(request["firstInstall"] if action == "migrate" else False),
        "stopsManagedRuntime": bool(action == "migrate" and existing and existing["managedRuntimeRunning"]),
        "createsVerifiedBackup": creates_verified_backup,
        "verifiedBackupScope": "database" if creates_verified_backup else None,
        "recoveryScope": public_recovery_scope(recovery_scope),
        "applicationRecoveryReadyAfterOperation": False,
        "inventorySnapshot": _snapshot(inventory), "expectedReservationSha256": expected_sha, "spec": spec,
    }


def authorization_phrase(plan: dict[str, Any]) -> str:
    production = plan.get("productionClassified")
    if not isinstance(production, bool):
        raise DeploymentKitError("Malformed SQLite operation plan Production classification.")
    mapping = {
        "import": (SQLITE_IMPORT_WRITE_PHRASE, PRODUCTION_SQLITE_IMPORT_WRITE_PHRASE),
        "backup": (SQLITE_BACKUP_WRITE_PHRASE, PRODUCTION_SQLITE_BACKUP_WRITE_PHRASE),
        "migrate": (SQLITE_MIGRATE_WRITE_PHRASE, PRODUCTION_SQLITE_MIGRATE_WRITE_PHRASE),
        "rollback-check": (SQLITE_ROLLBACK_CHECK_PHRASE, PRODUCTION_SQLITE_ROLLBACK_CHECK_PHRASE),
    }
    normal, prod = mapping[plan["action"]]
    return prod if production else normal


def _validate_sqlite_plan(plan: dict[str, Any]) -> None:
    required = {
        "targetName", "action", "ownerRepo", "environment", "productionClassified", "appSlug", "image",
        "databaseFile", "runAs", "sourceDatabase", "firstInstall", "stopsManagedRuntime", "createsVerifiedBackup",
        "verifiedBackupScope", "recoveryScope", "applicationRecoveryReadyAfterOperation", "inventorySnapshot",
        "expectedReservationSha256", "spec",
    }
    if not isinstance(plan, dict) or set(plan) != required or not isinstance(plan["productionClassified"], bool):
        raise DeploymentKitError("Malformed SQLite operation plan.")
    if plan["environment"] == "production" and not plan["productionClassified"]:
        raise DeploymentKitError("Literal production environment must remain Production-classified.")
    if plan["applicationRecoveryReadyAfterOperation"] is not False:
        raise DeploymentKitError("SQLite operations cannot claim application recovery readiness.")


def apply_sqlite_operation(plan: dict[str, Any]) -> dict[str, Any]:
    _validate_sqlite_plan(plan)
    _require_ready_platform(plan["targetName"])
    current = sqlite_inventory(plan["targetName"])
    if _snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError("SQLite state changed after the plan was reviewed; create and authorize a fresh plan.")
    profile = load_profile(plan["targetName"]); evidence = verify_access(profile)
    output = _run_remote(profile, evidence["address"], plan["action"], spec=plan["spec"], expected_reservation_sha=plan["expectedReservationSha256"])
    result = sqlite_inventory(plan["targetName"])
    result["mutated"] = True
    result["operation"] = plan["action"]; result["operationOutput"] = output.strip()
    result["productionClassified"] = plan["productionClassified"]
    result["recoveryReadiness"] = recovery_readiness(
        plan["spec"]["recoveryScope"],
        database_backup_verified=plan["createsVerifiedBackup"],
    )
    return result


def assert_app_spec_matches_persistence(name: str, app_spec: dict[str, Any]) -> None:
    inventory = sqlite_inventory(name)
    existing = _find(inventory, app_spec["appSlug"], app_spec["environment"])
    if existing is None:
        return
    if existing["ownerRepo"] != app_spec["ownerRepo"]:
        raise DeploymentKitError("Prepared SQLite persistence belongs to a different repository.")
    if existing["runAs"] != app_spec["runAs"]:
        raise DeploymentKitError("Application runAs does not match the prepared SQLite persistence reservation.")
    if app_spec.get("persistence", {}).get("mode") != "directory":
        raise DeploymentKitError("Prepared SQLite persistence requires directory application persistence.")


def _render_locked_sqlite_stage(
    plan: dict[str, Any], *, inherited_lock_fd: int, authorization: str,
    action: str, prepared_image_id: str | None = None,
    public_label_keys: tuple[str, ...] = (),
) -> dict[str, str]:
    _validate_sqlite_plan(plan)
    if plan["action"] not in {"migrate", "rollback-check"} or plan["firstInstall"]:
        raise DeploymentKitError("Lock handoff is limited to existing-database migration and rollback-check.")
    if action not in {"migrate", "rollback-check", "prepare-image"} or (
        action != "prepare-image" and action != plan["action"]
    ):
        raise DeploymentKitError("Image preparation or SQLite operation action differs from the reviewed plan.")
    if type(inherited_lock_fd) is not int or not 3 <= inherited_lock_fd <= 256:
        raise DeploymentKitError("Inherited remote lock descriptor must be an integer between 3 and 256.")
    if authorization != authorization_phrase(plan):
        raise DeploymentKitError("Exact reviewed SQLite operation authorization phrase is required.")
    if action == "prepare-image" and (prepared_image_id is not None or not public_label_keys):
        raise DeploymentKitError("Image preparation requires explicitly selected public labels and no prior binding.")
    if action != "prepare-image" and public_label_keys:
        raise DeploymentKitError("Public label enumeration belongs only to image preparation.")
    if prepared_image_id is not None:
        _prepared_image_id(prepared_image_id)

    _require_ready_platform(plan["targetName"])
    current = sqlite_inventory(plan["targetName"])
    if _snapshot(current) != plan["inventorySnapshot"]:
        raise DeploymentKitError("SQLite state changed after the plan was reviewed; create and authorize a fresh plan.")
    profile = load_profile(plan["targetName"])
    evidence = verify_access(profile)
    spec = dict(plan["spec"])
    if prepared_image_id is not None:
        spec["preparedImageId"] = _prepared_image_id(prepared_image_id)
    if public_label_keys:
        spec["publicLabelKeys"] = public_label_keys
    script = build_remote_script(spec)
    delimiter = "PROJECT_FORGE_SQLITE_STAGE_" + hashlib.sha256(script.encode()).hexdigest()[:24]
    if delimiter in script:
        raise DeploymentKitError("Unsafe SQLite script delimiter collision.")
    args = [action, plan["expectedReservationSha256"] or "NONE", profile["user"], str(inherited_lock_fd)]
    command = "bash -s -- " + " ".join(shlex.quote(arg) for arg in args)
    return {
        "targetName": plan["targetName"],
        "verifiedAddress": evidence["address"],
        "action": action,
        "script": f"{command} <<'{delimiter}'\n{script.rstrip()}\n{delimiter}\n",
    }


def render_locked_sqlite_operation_stage(
    plan: dict[str, Any], *, inherited_lock_fd: int, authorization: str,
    prepared_image_id: str | None = None,
) -> dict[str, str]:
    """Render a migration/check stage inside the same privileged lock-owning shell.

    Opt-in prepared_image_id rechecks the remote digest-to-image-ID mapping and
    runs all maintenance commands by that exact ID, without pulling again.
    Without a binding, legacy pull-by-digest operation behavior remains.
    The consumer must validate preparation label evidence before this stage.
    """
    return _render_locked_sqlite_stage(
        plan, inherited_lock_fd=inherited_lock_fd, authorization=authorization,
        action=plan.get("action"), prepared_image_id=prepared_image_id,
    )


def render_locked_sqlite_image_preparation_stage(
    plan: dict[str, Any], *, inherited_lock_fd: int, authorization: str,
    public_label_keys: list[str] | tuple[str, ...],
) -> dict[str, str]:
    """Render a lock-held remote pull/inspection stage, not a database operation.

    Pulls through the protected deployment-account registry config and emits
    selected public labels, the requested immutable digest and remote Docker ID.
    This DOES mutate Docker cache, but does not stop the runtime/change SQLite.
    """
    return _render_locked_sqlite_stage(
        plan, inherited_lock_fd=inherited_lock_fd, authorization=authorization,
        action="prepare-image", public_label_keys=_public_label_keys(public_label_keys),
    )


def parse_locked_sqlite_image_evidence(
    output: str, *, image: str, public_label_keys: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Fail closed on incomplete, reordered, extra, or malformed image evidence."""
    exact_image = _image(image)
    keys = _public_label_keys(public_label_keys)
    if not isinstance(output, str):
        raise DeploymentKitError("Malformed image preparation evidence.")
    rows = output.splitlines()
    if len(rows) != len(keys) + 2 or rows[-1] != "IMAGE_PREPARED_END":
        raise DeploymentKitError("Incomplete or malformed image preparation evidence.")
    header = rows[0].split("\t")
    if (len(header) != 3 or header[0] != "IMAGE_PREPARED" or header[1] != exact_image
            or _IMAGE_ID_RE.fullmatch(header[2]) is None):
        raise DeploymentKitError("Image preparation digest or Docker image ID differs from the reviewed image.")
    labels: dict[str, str] = {}
    for key, row in zip(keys, rows[1:-1]):
        parts = row.split("\t")
        if len(parts) != 3 or parts[0] != "LABEL" or parts[1] != key:
            raise DeploymentKitError("Image preparation label evidence is malformed or reordered.")
        try:
            raw = base64.b64decode(parts[2], validate=True)
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise DeploymentKitError("Image preparation label evidence is not valid base64 UTF-8.") from error
        if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
            raise DeploymentKitError("Image preparation label evidence contains missing/unsafe metadata.")
        labels[key] = value
    return {
        "schemaVersion": 1,
        "registryDigest": exact_image,
        "remoteImageId": header[2],
        "labels": labels,
        "capabilityProved": "remote-pulled-digest-bound-image-id",
        "remoteImageCacheWritten": True,
    }
