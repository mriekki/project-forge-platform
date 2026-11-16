"""Recover a verified SQLite import that failed before reservation metadata was written."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
from typing import Any

from .app_runtime import APP_ROOT
from .box_platform import platform_status
from .errors import DeploymentKitError
from .profiles import load_profile
from .sqlite_adapter import reservation_sha, sqlite_inventory
from .ssh import ssh_args, verify_access

SQLITE_IMPORT_RECOVERY_WRITE_PHRASE = "[SQLITE IMPORT RECOVERY WRITE]"
PRODUCTION_SQLITE_IMPORT_RECOVERY_WRITE_PHRASE = "[PRODUCTION SQLITE IMPORT RECOVERY]"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _require_request(request: dict[str, Any]) -> None:
    for key in ("ownerRepo", "environment", "appSlug", "image", "maintenanceEnvironment", "runAs", "databaseFile", "sourceDatabase"):
        if request.get(key) in (None, ""):
            raise DeploymentKitError(f"SQLite import recovery requires {key}.")


def _require_ready_platform(name: str) -> None:
    state = platform_status(name)["state"]
    if state != "ready":
        raise DeploymentKitError(
            f"SQLite import recovery requires a ready shared platform; target '{name}' is '{state}'."
        )


REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="$1"
EXPECTED_DB_SHA="${2:-}"
EXPECTED_SOURCE_SHA="${3:-}"
DEPLOY_USER="${4:-}"
APP_ROOT="__APP_ROOT__"
OWNER="$(printf '%s' '__OWNER_B64__' | base64 --decode)"
ENVIRONMENT="$(printf '%s' '__ENV_B64__' | base64 --decode)"
APP_SLUG="$(printf '%s' '__APP_B64__' | base64 --decode)"
IMAGE="$(printf '%s' '__IMAGE_B64__' | base64 --decode)"
RUN_AS="$(printf '%s' '__RUN_AS_B64__' | base64 --decode)"
DATABASE_FILE="$(printf '%s' '__DB_FILE_B64__' | base64 --decode)"
SOURCE_DATABASE="$(printf '%s' '__SOURCE_DB_B64__' | base64 --decode)"
DATABASE_FILE_B64="__DB_FILE_B64__"
RESERVATION_SHA="__RESERVATION_SHA__"
ENV_KEYS=(__ENV_KEYS__)
ENV_VALUES=(__ENV_VALUES__)

valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_image() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$ ]]; }
valid_run_as() { [[ "$1" =~ ^[0-9]+(:[0-9]+)?$ ]]; }
valid_db_file() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ && "$1" != "." && "$1" != ".." ]]; }
valid_env_key() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }
b64d() { printf '%s' "$1" | base64 --decode; }

validate_spec() {
    valid_repo "$OWNER" || { echo "Invalid recovery owner repository." >&2; exit 61; }
    valid_slug "$ENVIRONMENT" || { echo "Invalid recovery environment." >&2; exit 61; }
    valid_slug "$APP_SLUG" || { echo "Invalid recovery app slug." >&2; exit 61; }
    valid_image "$IMAGE" || { echo "Recovery image must be an immutable digest reference." >&2; exit 61; }
    valid_run_as "$RUN_AS" || { echo "Invalid recovery runAs." >&2; exit 61; }
    valid_db_file "$DATABASE_FILE" || { echo "Invalid recovery database file." >&2; exit 61; }
    [[ "$RESERVATION_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid recovery reservation fingerprint." >&2; exit 61; }
    [[ "$SOURCE_DATABASE" == /srv/* && "$SOURCE_DATABASE" != "$APP_ROOT"/* ]] || {
        echo "Recovery source must be outside the Kit app root under /srv." >&2; exit 61;
    }
    [[ "${#ENV_KEYS[@]}" -eq "${#ENV_VALUES[@]}" && "${#ENV_KEYS[@]}" -gt 0 ]] || {
        echo "Invalid recovery maintenance environment payload." >&2; exit 61;
    }
    local index key
    for index in "${!ENV_KEYS[@]}"; do
        key="$(b64d "${ENV_KEYS[$index]}")"
        valid_env_key "$key" || { echo "Invalid recovery maintenance environment key." >&2; exit 61; }
    done
}

configure_registry_auth() {
    [[ -n "$DEPLOY_USER" && "$DEPLOY_USER" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,31}$ ]] || {
        echo "Deployment account is invalid." >&2; exit 62;
    }
    local home config dir_mode file_mode deploy_uid
    home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
    [[ -n "$home" && "$home" == /* ]] || { echo "Could not resolve deployment account home." >&2; exit 62; }
    config="$home/.docker"
    if [[ ! -e "$config/config.json" ]]; then return 0; fi
    [[ -d "$config" && ! -L "$config" && -f "$config/config.json" && ! -L "$config/config.json" ]] || {
        echo "Docker credential path is not a regular protected directory/file." >&2; exit 62;
    }
    dir_mode="$(stat -c '%a' "$config")"
    file_mode="$(stat -c '%a' "$config/config.json")"
    deploy_uid="$(id -u "$DEPLOY_USER")"
    if (( (8#$dir_mode & 077) != 0 || (8#$file_mode & 077) != 0 )) ||
       [[ "$(stat -c '%u' "$config")" != "$deploy_uid" || "$(stat -c '%u' "$config/config.json")" != "$deploy_uid" ]]; then
        echo "Docker credentials must be owned by the deployment account and deny group/other access." >&2
        exit 62
    fi
    export DOCKER_CONFIG="$config"
}

set_paths() {
    ROOT="$APP_ROOT/$APP_SLUG/$ENVIRONMENT"
    DATA="$ROOT/data"
    BACKUPS="$ROOT/backups"
    DB="$DATA/$DATABASE_FILE"
    MARKER="$ROOT/persistence.env"
    DEPLOYMENT="$ROOT/deployment.env"
    EVIDENCE="$ROOT/sqlite-evidence.jsonl"
    LOCK_FILE="/run/lock/project-forge-app-$APP_SLUG--$ENVIRONMENT.lock"
}

expected_ids() {
    EXPECTED_UID="${RUN_AS%%:*}"
    [[ "$RUN_AS" == *:* ]] && EXPECTED_GID="${RUN_AS#*:}" || EXPECTED_GID="$EXPECTED_UID"
}

inspect_orphan() {
    local source_real root_entries data_entries db_mode db_sha source_sha bytes
    expected_ids

    [[ -d "$ROOT" && ! -L "$ROOT" && "$(realpath -e "$ROOT")" == "$ROOT" ]] || {
        echo "Recovery root is missing, invalid, or contains a symlinked path component." >&2; exit 63;
    }
    [[ "$(stat -c '%u' "$ROOT")" == "0" && "$(stat -c '%g' "$ROOT")" == "0" && "$(stat -c '%a' "$ROOT")" == "750" ]] || {
        echo "Recovery root ownership or mode does not match the failed-import footprint." >&2; exit 63;
    }
    for path in "$DATA" "$BACKUPS"; do
        [[ -d "$path" && ! -L "$path" && "$(realpath -e "$path")" == "$path" ]] || {
            echo "Recovery data/backup directory is missing or invalid: $path" >&2; exit 63;
        }
        [[ "$(stat -c '%u' "$path")" == "$EXPECTED_UID" && "$(stat -c '%g' "$path")" == "$EXPECTED_GID" && "$(stat -c '%a' "$path")" == "750" ]] || {
            echo "Recovery data/backup ownership or mode does not match runAs." >&2; exit 63;
        }
    done
    [[ -f "$DB" && ! -L "$DB" && "$(realpath -e "$DB")" == "$DB" ]] || {
        echo "Recovery database must be an existing non-symlink regular file." >&2; exit 63;
    }
    [[ "$(stat -c '%u' "$DB")" == "$EXPECTED_UID" && "$(stat -c '%g' "$DB")" == "$EXPECTED_GID" ]] || {
        echo "Recovery database ownership does not match runAs." >&2; exit 63;
    }
    db_mode="$(stat -c '%a' "$DB")"
    (( (8#$db_mode & 077) == 0 )) || { echo "Recovery database grants group/other permissions." >&2; exit 63; }

    [[ ! -e "$MARKER" && ! -e "$DEPLOYMENT" && ! -e "$EVIDENCE" ]] || {
        echo "Recovery requires no reservation, deployment state, or prior SQLite evidence." >&2; exit 63;
    }
    root_entries="$(find "$ROOT" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)"
    [[ "$root_entries" == $'backups\ndata' ]] || {
        echo "Recovery root contains unexpected entries." >&2; exit 63;
    }
    data_entries="$(find "$DATA" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)"
    [[ "$data_entries" == "$DATABASE_FILE" ]] || {
        echo "Recovery data directory contains unexpected entries." >&2; exit 63;
    }
    [[ -z "$(find "$BACKUPS" -mindepth 1 -maxdepth 1 -print -quit)" ]] || {
        echo "Recovery backup directory must still be empty." >&2; exit 63;
    }

    source_real="$(realpath -e "$SOURCE_DATABASE" 2>/dev/null || true)"
    [[ "$source_real" == "$SOURCE_DATABASE" && -f "$SOURCE_DATABASE" && ! -L "$SOURCE_DATABASE" ]] || {
        echo "Recovery source must remain an existing non-symlink regular file with no symlinked path components." >&2; exit 63;
    }
    [[ "$(basename "$SOURCE_DATABASE")" == "$DATABASE_FILE" ]] || {
        echo "Recovery source database file name mismatch." >&2; exit 63;
    }

    db_sha="$(sha256sum "$DB" | awk '{print $1}')"
    source_sha="$(sha256sum "$SOURCE_DATABASE" | awk '{print $1}')"
    bytes="$(stat -c '%s' "$DB")"
    [[ "$db_sha" =~ ^[0-9a-f]{64}$ && "$source_sha" =~ ^[0-9a-f]{64}$ && "$bytes" =~ ^[0-9]+$ && "$bytes" -gt 0 ]] || {
        echo "Recovery database fingerprint is invalid." >&2; exit 63;
    }
    printf 'RECOVERY\t%s\t%s\t%s\n' "$db_sha" "$source_sha" "$bytes"
}

maintenance_args() {
    local -n out_ref=$1
    local index key value
    out_ref=(docker run --rm --network none --user "$RUN_AS")
    for index in "${!ENV_KEYS[@]}"; do
        key="$(b64d "${ENV_KEYS[$index]}")"
        value="$(b64d "${ENV_VALUES[$index]}")"
        out_ref+=(--env "$key=$value")
    done
}

run_check() {
    local -a args
    maintenance_args args
    args+=(--mount "type=bind,src=$DATA,dst=/data" "$IMAGE" --check-rollback-compatibility)
    "${args[@]}"
}

write_marker() {
    local tmp
    tmp="$MARKER.tmp.$$"
    {
        printf 'SCHEMA_VERSION=1\n'
        printf 'ADAPTER=sqlite\n'
        printf 'OWNER_REPO=%s\n' "$OWNER"
        printf 'ENVIRONMENT=%s\n' "$ENVIRONMENT"
        printf 'APP_SLUG=%s\n' "$APP_SLUG"
        printf 'RUN_AS=%s\n' "$RUN_AS"
        printf 'DATABASE_FILE_B64=%s\n' "$DATABASE_FILE_B64"
        printf 'RESERVATION_SHA256=%s\n' "$RESERVATION_SHA"
    } > "$tmp"
    chmod 0600 "$tmp"
    mv -f "$tmp" "$MARKER"
}

record_evidence() {
    local timestamp
    timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf '{"timestamp":"%s","action":"import-recovery","ownerRepo":"%s","environment":"%s","appSlug":"%s","image":"%s","databaseFile":"%s","reservationSha256":"%s","artifact":"%s","outcome":"recovered"}\n' \
        "$timestamp" "$OWNER" "$ENVIRONMENT" "$APP_SLUG" "$IMAGE" "$DATABASE_FILE" "$RESERVATION_SHA" "$SOURCE_DATABASE" >> "$EVIDENCE"
    chmod 0600 "$EVIDENCE"
}

recover() {
    local inspection kind db_sha source_sha bytes
    exec 9>>"$LOCK_FILE"
    flock -n 9 || { echo "Another app/persistence operation holds the recovery lock." >&2; exit 75; }
    inspection="$(inspect_orphan)"
    IFS=$'\t' read -r kind db_sha source_sha bytes <<< "$inspection"
    [[ "$kind" == "RECOVERY" && "$db_sha" == "$EXPECTED_DB_SHA" && "$source_sha" == "$EXPECTED_SOURCE_SHA" ]] || {
        echo "Recovery state changed after planning; create and authorize a fresh recovery plan." >&2; exit 64;
    }
    configure_registry_auth
    docker pull "$IMAGE" >/dev/null
    run_check
    write_marker
    record_evidence
    printf 'SQLite import recovery completed and verified: %s\n' "$DB"
}

validate_spec
set_paths
case "$ACTION" in
    inspect) inspect_orphan ;;
    recover) recover ;;
    *) echo "Unsupported SQLite import recovery action: $ACTION" >&2; exit 2 ;;
esac
'''


def _build_remote_script(request: dict[str, Any]) -> str:
    _require_request(request)
    reservation = reservation_sha(
        owner_repo=request["ownerRepo"],
        environment=request["environment"],
        app_slug=request["appSlug"],
        run_as=request["runAs"],
        database_file=request["databaseFile"],
    )
    env = request["maintenanceEnvironment"]
    replacements = {
        "__APP_ROOT__": APP_ROOT,
        "__OWNER_B64__": _b64(request["ownerRepo"]),
        "__ENV_B64__": _b64(request["environment"]),
        "__APP_B64__": _b64(request["appSlug"]),
        "__IMAGE_B64__": _b64(request["image"]),
        "__RUN_AS_B64__": _b64(request["runAs"]),
        "__DB_FILE_B64__": _b64(request["databaseFile"]),
        "__SOURCE_DB_B64__": _b64(request["sourceDatabase"]),
        "__RESERVATION_SHA__": reservation,
        "__ENV_KEYS__": " ".join(f"'{_b64(key)}'" for key in env),
        "__ENV_VALUES__": " ".join(f"'{_b64(value)}'" for value in env.values()),
    }
    script = REMOTE_SCRIPT
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, value)
    if "__" in script:
        raise DeploymentKitError("Internal SQLite import recovery script contains an unresolved placeholder.")
    return script


def _run_remote(
    profile: dict[str, Any],
    address: str,
    action: str,
    request: dict[str, Any],
    *,
    expected_db_sha: str = "",
    expected_source_sha: str = "",
) -> str:
    if action not in {"inspect", "recover"}:
        raise DeploymentKitError(f"Unsupported SQLite import recovery action: {action}")
    args = [action]
    if action == "recover":
        args.extend([expected_db_sha, expected_source_sha, profile["user"]])
    completed = subprocess.run(
        ssh_args(profile, address, command="sudo -n bash -s -- " + " ".join(args)),
        input=_build_remote_script(request).encode("utf-8"),
        check=False,
        capture_output=True,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentKitError(f"Remote SQLite import recovery {action} failed: {detail}")
    return stdout


def _parse_inspection(output: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line]
    if len(lines) != 1:
        raise DeploymentKitError("Malformed SQLite import recovery inspection output.")
    parts = lines[0].split("\t")
    if len(parts) != 4 or parts[0] != "RECOVERY":
        raise DeploymentKitError("Malformed SQLite import recovery inspection record.")
    if _SHA_RE.fullmatch(parts[1]) is None or _SHA_RE.fullmatch(parts[2]) is None:
        raise DeploymentKitError("Malformed SQLite import recovery fingerprint.")
    try:
        database_bytes = int(parts[3])
    except ValueError as error:
        raise DeploymentKitError("Malformed SQLite import recovery database size.") from error
    if database_bytes <= 0:
        raise DeploymentKitError("SQLite import recovery database must be non-empty.")
    return {
        "databaseSha256": parts[1],
        "sourceSha256": parts[2],
        "databaseBytes": database_bytes,
    }


def inspect_sqlite_import_recovery(name: str, request: dict[str, Any]) -> dict[str, Any]:
    _require_ready_platform(name)
    _require_request(request)
    profile = load_profile(name)
    evidence = verify_access(profile)
    result = _parse_inspection(_run_remote(profile, evidence["address"], "inspect", request))
    result.update(targetName=name, verifiedAddress=evidence["address"], mutated=False)
    return result


def _snapshot(inspection: dict[str, Any]) -> str:
    value = {
        "databaseSha256": inspection["databaseSha256"],
        "sourceSha256": inspection["sourceSha256"],
        "databaseBytes": inspection["databaseBytes"],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def plan_sqlite_import_recovery(
    name: str,
    request: dict[str, Any],
    *,
    production: bool = False,
) -> dict[str, Any]:
    if not isinstance(production, bool):
        raise DeploymentKitError("SQLite Production classification must be a boolean.")
    production_classified = production or request["environment"] == "production"
    inspection = inspect_sqlite_import_recovery(name, request)
    return {
        "targetName": name,
        "action": "recover-import",
        "ownerRepo": request["ownerRepo"],
        "environment": request["environment"],
        "productionClassified": production_classified,
        "appSlug": request["appSlug"],
        "image": request["image"],
        "runAs": request["runAs"],
        "databaseFile": request["databaseFile"],
        "sourceDatabase": request["sourceDatabase"],
        "databaseSha256": inspection["databaseSha256"],
        "sourceSha256": inspection["sourceSha256"],
        "databaseBytes": inspection["databaseBytes"],
        "stateSnapshot": _snapshot(inspection),
        "overwritesDatabase": False,
        "deletesPersistentData": False,
        "createsReservation": True,
        "reverifiesDatabase": True,
        "request": request,
    }


def authorization_phrase(plan: dict[str, Any]) -> str:
    production = plan.get("productionClassified")
    if not isinstance(production, bool):
        raise DeploymentKitError("Malformed SQLite import recovery Production classification.")
    return (
        PRODUCTION_SQLITE_IMPORT_RECOVERY_WRITE_PHRASE
        if production
        else SQLITE_IMPORT_RECOVERY_WRITE_PHRASE
    )


def apply_sqlite_import_recovery(plan: dict[str, Any]) -> dict[str, Any]:
    required = {
        "targetName", "action", "ownerRepo", "environment", "productionClassified", "appSlug", "image", "runAs",
        "databaseFile", "sourceDatabase", "databaseSha256", "sourceSha256", "databaseBytes",
        "stateSnapshot", "overwritesDatabase", "deletesPersistentData", "createsReservation",
        "reverifiesDatabase", "request",
    }
    if (
        not isinstance(plan, dict)
        or set(plan) != required
        or plan["action"] != "recover-import"
        or not isinstance(plan["productionClassified"], bool)
    ):
        raise DeploymentKitError("Malformed SQLite import recovery plan.")
    if plan["environment"] == "production" and not plan["productionClassified"]:
        raise DeploymentKitError("Literal production environment must remain Production-classified.")
    current = inspect_sqlite_import_recovery(plan["targetName"], plan["request"])
    if _snapshot(current) != plan["stateSnapshot"]:
        raise DeploymentKitError(
            "SQLite import recovery state changed after the plan was reviewed; create and authorize a fresh plan."
        )
    profile = load_profile(plan["targetName"])
    evidence = verify_access(profile)
    output = _run_remote(
        profile,
        evidence["address"],
        "recover",
        plan["request"],
        expected_db_sha=plan["databaseSha256"],
        expected_source_sha=plan["sourceSha256"],
    )
    inventory = sqlite_inventory(plan["targetName"])
    reservation = next(
        (
            item for item in inventory["sqlite"]
            if item["appSlug"] == plan["appSlug"] and item["environment"] == plan["environment"]
        ),
        None,
    )
    if reservation is None or not reservation["databasePresent"]:
        raise DeploymentKitError("SQLite import recovery completed remotely but reservation verification failed.")
    expected_reservation = reservation_sha(
        owner_repo=plan["ownerRepo"],
        environment=plan["environment"],
        app_slug=plan["appSlug"],
        run_as=plan["runAs"],
        database_file=plan["databaseFile"],
    )
    if reservation["reservationSha256"] != expected_reservation:
        raise DeploymentKitError("Recovered SQLite reservation fingerprint does not match the reviewed plan.")
    inventory["mutated"] = True
    inventory["operation"] = "recover-import"
    inventory["operationOutput"] = output.strip()
    inventory["productionClassified"] = plan["productionClassified"]
    return inventory
