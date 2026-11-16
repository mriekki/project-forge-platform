"""Remote Bash template for the SQLite persistence adapter."""

REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="$1"
EXPECTED_RESERVATION_SHA="${2:-}"
DEPLOY_USER="${3:-}"
# Optional Kit-verified handoff from an already-locked privileged remote session.
# This is a remote file descriptor, not a workstation/SSH descriptor.
HELD_LOCK_FD="${4:-}"
APP_ROOT="__APP_ROOT__"
SQLITE_SCHEMA_VERSION="__SQLITE_SCHEMA_VERSION__"
OWNER_B64="__OWNER_B64__"
ENV_B64="__ENV_B64__"
APP_B64="__APP_B64__"
IMAGE_B64="__IMAGE_B64__"
PREPARED_IMAGE_ID="__PREPARED_IMAGE_ID__"
PUBLIC_LABEL_KEYS_B64="__PUBLIC_LABEL_KEYS_B64__"
EXECUTION_IMAGE=""
RUN_AS_B64="__RUN_AS_B64__"
DB_FILE_B64="__DB_FILE_B64__"
SOURCE_DB_B64="__SOURCE_DB_B64__"
FIRST_INSTALL="__FIRST_INSTALL__"
RESERVATION_SHA="__RESERVATION_SHA__"
ENV_KEYS=(__ENV_KEYS__)
ENV_VALUES=(__ENV_VALUES__)
RECOVERY_EVIDENCE_B64="__RECOVERY_EVIDENCE_B64__"

b64d() { printf '%s' "$1" | base64 --decode; }
meta_value() {
    local path="$1" key="$2"
    [[ -f "$path" ]] || return 1
    sed -n "s/^${key}=//p" "$path" | head -n1
}
valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_image() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$ ]]; }
valid_image_id() { [[ "$1" =~ ^sha256:[0-9a-f]{64}$ ]]; }
valid_label_key() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; }
valid_run_as() { [[ "$1" =~ ^[0-9]+(:[0-9]+)?$ ]]; }
valid_db_file() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ && "$1" != "." && "$1" != ".." ]]; }
valid_env_key() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }

configure_registry_auth() {
    [[ -n "$DEPLOY_USER" && "$DEPLOY_USER" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,31}$ ]] || {
        echo "Deployment account is invalid." >&2; exit 42;
    }
    local home config dir_mode file_mode deploy_uid
    home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
    [[ -n "$home" && "$home" == /* ]] || { echo "Could not resolve deployment account home." >&2; exit 42; }
    config="$home/.docker"
    if [[ ! -e "$config/config.json" ]]; then return 0; fi
    [[ -d "$config" && ! -L "$config" && -f "$config/config.json" && ! -L "$config/config.json" ]] || {
        echo "Docker credential path is not a regular protected directory/file." >&2; exit 42;
    }
    dir_mode="$(stat -c '%a' "$config")"
    file_mode="$(stat -c '%a' "$config/config.json")"
    deploy_uid="$(id -u "$DEPLOY_USER")"
    if (( (8#$dir_mode & 077) != 0 || (8#$file_mode & 077) != 0 )) ||
       [[ "$(stat -c '%u' "$config")" != "$deploy_uid" || "$(stat -c '%u' "$config/config.json")" != "$deploy_uid" ]]; then
        echo "Docker credentials must be owned by the deployment account and deny group/other access." >&2
        exit 42
    fi
    export DOCKER_CONFIG="$config"
}

managed_runtime_info() {
    local root state current file
    root="$1"
    state="$root/deployment.env"
    MANAGED_CONTAINER=""
    MANAGED_IMAGE=""
    MANAGED_RUNNING=false
    [[ -f "$state" && ! -L "$state" ]] || return 0
    current="$(meta_value "$state" CURRENT_RELEASE || true)"
    [[ -n "$current" ]] || { echo "Managed application state is malformed." >&2; exit 43; }
    file="$root/releases/$current/release.env"
    [[ -f "$file" && ! -L "$file" ]] || { echo "Managed application release metadata is missing." >&2; exit 43; }
    MANAGED_CONTAINER="$(meta_value "$file" CONTAINER_NAME || true)"
    MANAGED_IMAGE="$(meta_value "$file" IMAGE || true)"
    [[ -n "$MANAGED_CONTAINER" && -n "$MANAGED_IMAGE" ]] || { echo "Managed application release metadata is malformed." >&2; exit 43; }
    [[ "$(docker inspect --format '{{.State.Status}}' "$MANAGED_CONTAINER" 2>/dev/null || true)" == "running" ]] && MANAGED_RUNNING=true || true
}

inventory() {
    local marker root owner env app run_as db_b64 db file present bytes backups running image count=0 sha
    if [[ -d "$APP_ROOT" ]]; then
        while IFS= read -r marker; do
            [[ -n "$marker" ]] || continue
            [[ ! -L "$marker" ]] || { echo "SQLite reservation marker must not be a symbolic link: $marker" >&2; exit 44; }
            [[ "$(meta_value "$marker" ADAPTER || true)" == "sqlite" ]] || continue
            owner="$(meta_value "$marker" OWNER_REPO || true)"
            env="$(meta_value "$marker" ENVIRONMENT || true)"
            app="$(meta_value "$marker" APP_SLUG || true)"
            run_as="$(meta_value "$marker" RUN_AS || true)"
            db_b64="$(meta_value "$marker" DATABASE_FILE_B64 || true)"
            db="$(b64d "$db_b64")"
            sha="$(meta_value "$marker" RESERVATION_SHA256 || true)"
            [[ -n "$owner" && -n "$env" && -n "$app" && -n "$run_as" && -n "$db" && "$sha" =~ ^[0-9a-f]{64}$ ]] || {
                echo "SQLite reservation marker is malformed: $marker" >&2; exit 44;
            }
            root="$(dirname "$marker")"
            file="$root/data/$db"
            present=false; bytes=0
            if [[ -e "$file" ]]; then
                [[ -f "$file" && ! -L "$file" ]] || { echo "Managed SQLite database is not a regular file: $file" >&2; exit 44; }
                present=true
                bytes="$(stat -c '%s' "$file")"
            fi
            backups=0
            if [[ -d "$root/backups" && ! -L "$root/backups" ]]; then
                backups="$(find "$root/backups" -maxdepth 1 -type f -printf '.' | wc -c)"
            fi
            managed_runtime_info "$root"
            running="$MANAGED_RUNNING"; image="$MANAGED_IMAGE"
            printf 'SQLITE\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
                "$owner" "$env" "$app" "$run_as" "$db" "$sha" "$present" "$bytes" "$backups" "$running" "$image"
            count=$((count + 1))
        done < <(find "$APP_ROOT" -mindepth 3 -maxdepth 3 -type f -name persistence.env -print 2>/dev/null | sort)
    fi
    printf 'SUMMARY\tsqliteCount\t%s\n' "$count"
}

decode_spec() {
    OWNER="$(b64d "$OWNER_B64")"
    ENVIRONMENT="$(b64d "$ENV_B64")"
    APP_SLUG="$(b64d "$APP_B64")"
    IMAGE="$(b64d "$IMAGE_B64")"
    RUN_AS="$(b64d "$RUN_AS_B64")"
    DATABASE_FILE="$(b64d "$DB_FILE_B64")"
    SOURCE_DATABASE="$(b64d "$SOURCE_DB_B64")"
    RECOVERY_EVIDENCE_JSON="$(b64d "$RECOVERY_EVIDENCE_B64")"
    valid_repo "$OWNER" || { echo "Invalid SQLite owner repository." >&2; exit 45; }
    valid_slug "$ENVIRONMENT" || { echo "Invalid SQLite environment." >&2; exit 45; }
    valid_slug "$APP_SLUG" || { echo "Invalid SQLite app slug." >&2; exit 45; }
    valid_image "$IMAGE" || { echo "SQLite maintenance image is not an immutable digest reference." >&2; exit 45; }
    [[ -z "$PREPARED_IMAGE_ID" ]] || valid_image_id "$PREPARED_IMAGE_ID" || {
        echo "Bound SQLite Docker image ID is malformed." >&2; exit 45;
    }
    valid_run_as "$RUN_AS" || { echo "Invalid SQLite runAs." >&2; exit 45; }
    valid_db_file "$DATABASE_FILE" || { echo "Invalid SQLite database file name." >&2; exit 45; }
    [[ "$RESERVATION_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid SQLite reservation fingerprint." >&2; exit 45; }
    [[ "${#ENV_KEYS[@]}" -eq "${#ENV_VALUES[@]}" && "${#ENV_KEYS[@]}" -gt 0 ]] || { echo "Invalid SQLite maintenance environment payload." >&2; exit 45; }
    [[ "$RECOVERY_EVIDENCE_JSON" == \{*\} ]] || { echo "Invalid SQLite recovery evidence payload." >&2; exit 45; }
    local index key
    for index in "${!ENV_KEYS[@]}"; do
        key="$(b64d "${ENV_KEYS[$index]}")"
        valid_env_key "$key" || { echo "Invalid SQLite maintenance environment key." >&2; exit 45; }
    done
}

assert_marker() {
    local marker="$1" expected="$2"
    [[ -f "$marker" && ! -L "$marker" ]] || { echo "SQLite reservation is missing." >&2; exit 46; }
    [[ "$(meta_value "$marker" ADAPTER || true)" == "sqlite" &&
       "$(meta_value "$marker" OWNER_REPO || true)" == "$OWNER" &&
       "$(meta_value "$marker" ENVIRONMENT || true)" == "$ENVIRONMENT" &&
       "$(meta_value "$marker" APP_SLUG || true)" == "$APP_SLUG" &&
       "$(meta_value "$marker" RUN_AS || true)" == "$RUN_AS" &&
       "$(b64d "$(meta_value "$marker" DATABASE_FILE_B64 || true)")" == "$DATABASE_FILE" &&
       "$(meta_value "$marker" RESERVATION_SHA256 || true)" == "$RESERVATION_SHA" ]] || {
        echo "SQLite reservation ownership/configuration mismatch." >&2; exit 46;
    }
    [[ "$expected" != "NONE" && "$expected" == "$RESERVATION_SHA" ]] || {
        echo "SQLite reservation changed after planning." >&2; exit 47;
    }
}

write_marker() {
    local marker tmp
    marker="$1"
    tmp="$marker.tmp.$$"
    {
        printf 'SCHEMA_VERSION=%s\n' "$SQLITE_SCHEMA_VERSION"
        printf 'ADAPTER=sqlite\n'
        printf 'OWNER_REPO=%s\n' "$OWNER"
        printf 'ENVIRONMENT=%s\n' "$ENVIRONMENT"
        printf 'APP_SLUG=%s\n' "$APP_SLUG"
        printf 'RUN_AS=%s\n' "$RUN_AS"
        printf 'DATABASE_FILE_B64=%s\n' "$DB_FILE_B64"
        printf 'RESERVATION_SHA256=%s\n' "$RESERVATION_SHA"
    } > "$tmp"
    chmod 0600 "$tmp"
    mv -f "$tmp" "$marker"
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

run_backup() {
    local source_dir="$1" backup_dir="$2" backup_name="$3"
    local -a args
    maintenance_args args
    args+=(--mount "type=bind,src=$source_dir,dst=/data" --mount "type=bind,src=$backup_dir,dst=/backup" "$EXECUTION_IMAGE" --backup --backup-path "/backup/$backup_name")
    "${args[@]}"
}

run_check() {
    local data_dir="$1"
    local -a args
    maintenance_args args
    args+=(--mount "type=bind,src=$data_dir,dst=/data" "$EXECUTION_IMAGE" --check-rollback-compatibility)
    "${args[@]}"
}

run_migrate() {
    local data_dir="$1"
    local -a args
    maintenance_args args
    args+=(--mount "type=bind,src=$data_dir,dst=/data" "$EXECUTION_IMAGE" --migrate)
    [[ "$FIRST_INSTALL" == true ]] && args+=(--first-install)
    "${args[@]}"
}

record_evidence() {
    local root="$1" action="$2" outcome="$3" artifact="${4:-}" timestamp
    timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf '{"timestamp":"%s","action":"%s","ownerRepo":"%s","environment":"%s","appSlug":"%s","image":"%s","databaseFile":"%s","reservationSha256":"%s","artifact":"%s","outcome":"%s","recovery":%s}\n' \
        "$timestamp" "$action" "$OWNER" "$ENVIRONMENT" "$APP_SLUG" "$IMAGE" "$DATABASE_FILE" "$RESERVATION_SHA" "$artifact" "$outcome" "$RECOVERY_EVIDENCE_JSON" >> "$root/sqlite-evidence.jsonl"
    chmod 0600 "$root/sqlite-evidence.jsonl"
}

set_paths() {
    ROOT="$APP_ROOT/$APP_SLUG/$ENVIRONMENT"
    DATA="$ROOT/data"
    BACKUPS="$ROOT/backups"
    MARKER="$ROOT/persistence.env"
    LOCK_FILE="/run/lock/project-forge-app-$APP_SLUG--$ENVIRONMENT.lock"
    for path in "$ROOT" "$DATA" "$BACKUPS" "$MARKER" "$ROOT/deployment.env" "$ROOT/sqlite-evidence.jsonl"; do
        [[ ! -L "$path" ]] || { echo "SQLite managed path must not be a symbolic link: $path" >&2; exit 48; }
    done
}

expected_ids() {
    EXPECTED_UID="${RUN_AS%%:*}"
    [[ "$RUN_AS" == *:* ]] && EXPECTED_GID="${RUN_AS#*:}" || EXPECTED_GID="$EXPECTED_UID"
}

create_reserved_dirs() {
    expected_ids
    install -d -m 0750 "$APP_ROOT" "$APP_ROOT/$APP_SLUG" "$ROOT"
    if [[ ! -e "$DATA" ]]; then install -d -m 0750 -o "$EXPECTED_UID" -g "$EXPECTED_GID" "$DATA"; fi
    if [[ ! -e "$BACKUPS" ]]; then install -d -m 0750 -o "$EXPECTED_UID" -g "$EXPECTED_GID" "$BACKUPS"; fi
    verify_reserved_dirs
}

verify_reserved_dirs() {
    expected_ids
    [[ -d "$DATA" && ! -L "$DATA" && -d "$BACKUPS" && ! -L "$BACKUPS" ]] || {
        echo "SQLite reserved data/backup directories are missing or invalid." >&2; exit 48;
    }
    [[ "$(stat -c '%u' "$DATA")" == "$EXPECTED_UID" && "$(stat -c '%g' "$DATA")" == "$EXPECTED_GID" &&
       "$(stat -c '%u' "$BACKUPS")" == "$EXPECTED_UID" && "$(stat -c '%g' "$BACKUPS")" == "$EXPECTED_GID" ]] || {
        echo "SQLite data/backup directory ownership does not match runAs." >&2; exit 48;
    }
}

acquire_operation_lock() {
    if [[ -z "$HELD_LOCK_FD" ]]; then
        exec 9>>"$LOCK_FILE"
        flock -n 9 || { echo "Another app/persistence operation holds the lock for $APP_SLUG--$ENVIRONMENT." >&2; exit 75; }
        return 0
    fi

    # Never convert an untrusted flag into permission to skip the lock.
    # Inherited lock sharing is limited to existing-reservation migration and
    # compatibility verification; other mutations retain their own lock.
    [[ "$ACTION" == migrate || "$ACTION" == rollback-check || "$ACTION" == prepare-image ]] && [[ "$FIRST_INSTALL" == false ]] || {
        echo "An inherited lock is not supported for this SQLite action." >&2; exit 75;
    }
    [[ "$HELD_LOCK_FD" =~ ^[0-9]+$ ]] && (( 10#$HELD_LOCK_FD >= 3 && 10#$HELD_LOCK_FD <= 256 )) || {
        echo "Inherited SQLite lock descriptor is invalid." >&2; exit 75;
    }
    [[ -f "$LOCK_FILE" && ! -L "$LOCK_FILE" ]] || {
        echo "Inherited SQLite lock path is invalid." >&2; exit 75;
    }
    local inherited_inode expected_inode
    inherited_inode="$(stat -Lc '%d:%i' "/proc/self/fd/$HELD_LOCK_FD" 2>/dev/null || true)"
    expected_inode="$(stat -Lc '%d:%i' "$LOCK_FILE" 2>/dev/null || true)"
    [[ -n "$inherited_inode" && "$inherited_inode" == "$expected_inode" ]] || {
        echo "Inherited SQLite lock descriptor does not match this app/environment." >&2; exit 75;
    }
    grep -Eq '^lock:[[:space:]]+[0-9]+:[[:space:]]+FLOCK[[:space:]]+ADVISORY[[:space:]]+WRITE([[:space:]]|$)' \
        "/proc/self/fdinfo/$HELD_LOCK_FD" || {
        echo "Inherited SQLite lock was not held by this descriptor." >&2; exit 75;
    }
}

prepare_image() {
    [[ "$ACTION" == prepare-image && -z "$PREPARED_IMAGE_ID" && -n "$PUBLIC_LABEL_KEYS_B64" ]] || {
        echo "Image preparation requires a held lock and public label selection." >&2; exit 49;
    }
    # The deployment account's protected registry config was verified.
    # Suppress Docker stderr, which may contain sensitive registry details.
    docker pull "$IMAGE" >/dev/null 2>&1 || {
        echo "Exact immutable SQLite image pull failed." >&2; exit 49;
    }
    local image_id label_key label_value encoded count=0 label_length
    image_id="$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)" || {
        echo "Pulled SQLite image is not inspectable." >&2; exit 49;
    }
    valid_image_id "$image_id" || {
        echo "Remote SQLite Docker image ID is malformed." >&2; exit 49;
    }
    printf 'IMAGE_PREPARED\t%s\t%s\n' "$IMAGE" "$image_id"
    while IFS= read -r label_key; do
        valid_label_key "$label_key" || {
            echo "Requested public image label name is invalid." >&2; exit 49;
        }
        label_value="$(docker image inspect --format "{{json (index .Config.Labels \"$label_key\")}}" "$image_id" 2>/dev/null)" || {
            echo "Requested public image label could not be read." >&2; exit 49;
        }
        [[ -n "$label_value" && "$label_value" != "null" && "$label_value" != '""' &&
           "$label_value" != *$'\n'* && "$label_value" != *$'\r'* &&
           "$label_value" != *$'\t'* ]] || {
            echo "Requested public image label is missing or unsafe." >&2; exit 49;
        }
        label_length="$(printf '%s' "$label_value" | wc -c)"
        (( label_length <= 4096 )) || {
            echo "Requested public image label exceeds the evidence limit." >&2; exit 49;
        }
        encoded="$(printf '%s' "$label_value" | base64 -w0)"
        printf 'LABEL\t%s\t%s\n' "$label_key" "$encoded"
        count=$((count + 1))
    done < <(printf '%s' "$PUBLIC_LABEL_KEYS_B64" | base64 --decode)
    [[ "$count" -ge 1 && "$count" -le 16 ]] || {
        echo "Public image label selection is invalid." >&2; exit 49;
    }
    printf 'IMAGE_PREPARED_END\n'
}

select_execution_image() {
    if [[ -z "$PREPARED_IMAGE_ID" ]]; then
        docker pull "$IMAGE" >/dev/null
        EXECUTION_IMAGE="$IMAGE"
        return 0
    fi
    [[ -n "$HELD_LOCK_FD" && "$FIRST_INSTALL" == false ]] &&
        [[ "$ACTION" == migrate || "$ACTION" == rollback-check ]] || {
        echo "Bound SQLite execution requires a supported inherited lock." >&2; exit 49;
    }
    local resolved
    resolved="$(docker image inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null)" || {
        echo "Prepared digest reference is no longer inspectable." >&2; exit 49;
    }
    [[ "$resolved" == "$PREPARED_IMAGE_ID" ]] &&
        [[ "$(docker image inspect --format '{{.Id}}' "$PREPARED_IMAGE_ID" 2>/dev/null)" == "$PREPARED_IMAGE_ID" ]] || {
        echo "Prepared digest-to-image-ID binding changed; SQLite execution is blocked." >&2; exit 49;
    }
    EXECUTION_IMAGE="$PREPARED_IMAGE_ID"
}

operate() {
    decode_spec
    configure_registry_auth
    set_paths
    acquire_operation_lock

    local db="$DATA/$DATABASE_FILE" stamp backup_name source_real source_parent
    managed_runtime_info "$ROOT"

    if [[ "$ACTION" == prepare-image ]]; then
        assert_marker "$MARKER" "$EXPECTED_RESERVATION_SHA"
        verify_reserved_dirs
        [[ -f "$db" && ! -L "$db" ]] || {
            echo "Image preparation requires reserved SQLite storage." >&2; exit 49;
        }
        prepare_image
        return 0
    fi

    case "$ACTION" in
        import)
            [[ "$EXPECTED_RESERVATION_SHA" == "NONE" && ! -e "$MARKER" ]] || { echo "SQLite import destination was reserved after planning." >&2; exit 47; }
            [[ ! -e "$ROOT/deployment.env" ]] || { echo "SQLite import must occur before the first managed application deployment." >&2; exit 49; }
            [[ ! -e "$db" ]] || { echo "SQLite import refuses to overwrite an existing destination database." >&2; exit 49; }
            [[ "$SOURCE_DATABASE" == /srv/* && "$SOURCE_DATABASE" != "$APP_ROOT"/* ]] || { echo "SQLite import source must be outside the Kit app root under /srv." >&2; exit 49; }
            source_real="$(realpath -e "$SOURCE_DATABASE" 2>/dev/null || true)"
            [[ "$source_real" == "$SOURCE_DATABASE" && -f "$SOURCE_DATABASE" && ! -L "$SOURCE_DATABASE" ]] || { echo "SQLite import source must be an existing non-symlink regular file with no symlinked path components." >&2; exit 49; }
            [[ "$(basename "$SOURCE_DATABASE")" == "$DATABASE_FILE" ]] || { echo "SQLite import source file name mismatch." >&2; exit 49; }
            create_reserved_dirs
            select_execution_image
            source_parent="$(dirname "$SOURCE_DATABASE")"
            run_backup "$source_parent" "$DATA" "$DATABASE_FILE"
            run_check "$DATA"
            write_marker "$MARKER"
            record_evidence "$ROOT" import imported "$SOURCE_DATABASE"
            printf 'SQLite import completed and verified: %s\n' "$db"
            ;;
        backup)
            assert_marker "$MARKER" "$EXPECTED_RESERVATION_SHA"
            verify_reserved_dirs
            [[ -f "$db" && ! -L "$db" ]] || { echo "SQLite backup requires the reserved database file." >&2; exit 49; }
            select_execution_image
            stamp="$(date -u +'%Y%m%dT%H%M%SZ')"
            backup_name="backup-$stamp-$DATABASE_FILE"
            run_backup "$DATA" "$BACKUPS" "$backup_name"
            record_evidence "$ROOT" backup backed-up "$backup_name"
            printf 'SQLite verified database backup created: %s\n' "$BACKUPS/$backup_name"
            ;;
        migrate)
            if [[ "$FIRST_INSTALL" == true ]]; then
                [[ "$EXPECTED_RESERVATION_SHA" == "NONE" && ! -e "$MARKER" ]] || { echo "First-install SQLite destination was reserved after planning." >&2; exit 47; }
                [[ ! -e "$ROOT/deployment.env" && ! -e "$db" ]] || { echo "First-install SQLite migration requires no runtime state or database." >&2; exit 49; }
                create_reserved_dirs
                select_execution_image
                run_migrate "$DATA"
                run_check "$DATA"
                write_marker "$MARKER"
                record_evidence "$ROOT" migrate migrated-first-install ""
                printf 'SQLite first-install migration completed and verified.\n'
            else
                assert_marker "$MARKER" "$EXPECTED_RESERVATION_SHA"
                verify_reserved_dirs
                [[ -f "$db" && ! -L "$db" ]] || { echo "SQLite migration requires the reserved database file." >&2; exit 49; }
                select_execution_image
                stamp="$(date -u +'%Y%m%dT%H%M%SZ')"
                backup_name="pre-migrate-$stamp-$DATABASE_FILE"
                run_backup "$DATA" "$BACKUPS" "$backup_name"
                if [[ "$MANAGED_RUNNING" == true ]]; then docker stop "$MANAGED_CONTAINER" >/dev/null; fi
                if ! run_migrate "$DATA"; then
                    record_evidence "$ROOT" migrate failed "$backup_name"
                    echo "SQLite migration failed; verified pre-migration database backup is retained and managed runtime remains stopped." >&2
                    exit 50
                fi
                run_check "$DATA"
                record_evidence "$ROOT" migrate migrated "$backup_name"
                printf 'SQLite migration completed; verified pre-migration database backup: %s\n' "$BACKUPS/$backup_name"
            fi
            ;;
        rollback-check)
            assert_marker "$MARKER" "$EXPECTED_RESERVATION_SHA"
            verify_reserved_dirs
            [[ -f "$db" && ! -L "$db" ]] || { echo "SQLite rollback check requires the reserved database file." >&2; exit 49; }
            select_execution_image
            run_check "$DATA"
            record_evidence "$ROOT" rollback-check compatible ""
            printf 'SQLite rollback compatibility check passed for image %s.\n' "$IMAGE"
            ;;
        *) echo "Unsupported SQLite adapter action: $ACTION" >&2; exit 2 ;;
    esac
}

case "$ACTION" in
    inventory) inventory ;;
    import|backup|migrate|rollback-check|prepare-image) operate ;;
    *) echo "Unsupported SQLite adapter action: $ACTION" >&2; exit 2 ;;
esac
'''
