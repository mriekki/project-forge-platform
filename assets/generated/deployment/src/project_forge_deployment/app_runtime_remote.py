"""Remote Bash template for generic application runtime deployment."""

REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="$1"
EXPECTED_SPEC_SHA="${2:-}"
DEPLOY_USER="${3:-}"
HELD_LOCK_FD="${4:-}"
APP_ROOT="__APP_ROOT__"
MATERIAL_ROOT="__MATERIAL_ROOT__"
AUTH_EPOCH_ROOT="__AUTH_EPOCH_ROOT__"
AUTH_EPOCH_TARGET="__AUTH_EPOCH_TARGET__"
AUTH_EPOCH_ENV_KEY="__AUTH_EPOCH_ENV_KEY__"
APP_SCHEMA_VERSION="__APP_SCHEMA_VERSION__"
NETWORK_NAME="__NETWORK_NAME__"
CADDY_CONTAINER="__CADDY_CONTAINER__"
DESIRED_PRESENT="__DESIRED_PRESENT__"

D_OWNER_B64="__D_OWNER_B64__"
D_ENV_B64="__D_ENV_B64__"
D_APP_B64="__D_APP_B64__"
D_CONTAINER_B64="__D_CONTAINER_B64__"
D_IMAGE_B64="__D_IMAGE_B64__"
D_PORT="__D_PORT__"
D_HEALTH_B64="__D_HEALTH_B64__"
D_RUN_AS_B64="__D_RUN_AS_B64__"
D_PERSISTENCE="__D_PERSISTENCE__"
D_DATA_TARGET_B64="__D_DATA_TARGET_B64__"
D_SPEC_SHA="__D_SPEC_SHA__"
D_AUTH_EPOCH="__D_AUTH_EPOCH__"
D_ENV_KEYS=(__D_ENV_KEYS__)
D_ENV_VALUES=(__D_ENV_VALUES__)
D_MATERIAL_NAMES=(__D_MATERIAL_NAMES__)
D_MATERIAL_TARGETS=(__D_MATERIAL_TARGETS__)
D_MATERIAL_EXPECTED=(__D_MATERIAL_EXPECTED__)

b64d() { printf '%s' "$1" | base64 --decode; }
meta_value() {
    local path="$1" key="$2"
    [[ -f "$path" ]] || return 1
    sed -n "s/^${key}=//p" "$path" | head -n1
}
valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_container() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; }
valid_image() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$ ]]; }
valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( 1 <= 10#$1 && 10#$1 <= 65535 )); }
valid_run_as() { [[ "$1" =~ ^[0-9]+(:[0-9]+)?$ ]]; }
valid_env_key() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; }

platform_ready() {
    [[ -f /srv/project-forge-platform/platform.env ]] &&
    docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 &&
    [[ "$(docker inspect --format '{{.State.Status}}' "$CADDY_CONTAINER" 2>/dev/null || true)" == "running" ]]
}

network_has_container() {
    local container="$1"
    docker network inspect "$NETWORK_NAME" --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}' 2>/dev/null |
        grep -Fxq "$container"
}

container_identity() {
    local name="$1" names
    CONTAINER_ID="$(docker inspect --format '{{.Id}}' "$name" 2>/dev/null)" || {
        names="$(docker container ls --all --no-trunc --format '{{.Names}}' 2>/dev/null)" || {
            echo "Unable to inspect Docker container inventory." >&2; return 1;
        }
        if grep -Fxq -- "$name" <<< "$names"; then
            echo "Existing application container could not be inspected." >&2; return 1
        fi
        CONTAINER_ID=""
        return 0
    }
    [[ "$CONTAINER_ID" =~ ^[0-9a-f]{64}$ ]] || {
        echo "Application container identity is malformed." >&2; return 1;
    }
}

container_image_matches_release() {
    local release="$1" container="$2" name="$3" image expected resolved actual configured actual_name
    image="$(meta_value "$release" IMAGE || true)"
    valid_image "$image" || return 1
    expected="$(meta_value "$release" RUNTIME_IMAGE_ID || true)"
    if [[ -n "$expected" ]]; then
        [[ "$expected" =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
        resolved="$(docker image inspect --format '{{.Id}}' "$expected" 2>/dev/null)" || return 1
    else
        resolved="$(docker image inspect --format '{{.Id}}' "$image" 2>/dev/null)" || return 1
        expected="$resolved"
    fi
    actual="$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null)" || return 1
    configured="$(docker inspect --format '{{.Config.Image}}' "$container" 2>/dev/null)" || return 1
    actual_name="$(docker inspect --format '{{.Name}}' "$container" 2>/dev/null)" || return 1
    [[ "$expected" =~ ^sha256:[0-9a-f]{64}$ &&
       "$resolved" == "$expected" && "$actual" == "$expected" &&
       ( "$configured" == "$image" || "$configured" == "$expected" ) && "$actual_name" == "/$name" ]]
}


material_source() {
    printf '%s/%s/%s/%s' "$MATERIAL_ROOT" "$D_APP" "$D_ENV" "$1"
}
material_identity() {
    local source="$1" run_as="$2" uid gid dir owner mode hazards
    uid="${run_as%%:*}"
    gid="$uid"
    [[ "$run_as" != *:* ]] || gid="${run_as#*:}"
    command -v setpriv >/dev/null 2>&1 || {
        echo "setpriv is required to verify read-only material access for runAs." >&2; return 1;
    }
    for dir in /srv "$MATERIAL_ROOT" "$MATERIAL_ROOT/$D_APP" "$MATERIAL_ROOT/$D_APP/$D_ENV" "$source"; do
        [[ -d "$dir" && ! -L "$dir" ]] || {
            echo "Read-only material directory missing or linked: $dir" >&2; return 1;
        }
        owner="$(stat -c '%u' "$dir")"
        mode="$(stat -c '%a' "$dir")"
        [[ "$owner" == 0 ]] && (( (8#$mode & 022) == 0 )) || {
            echo "Read-only material directory ownership or mode is unsafe: $dir" >&2; return 1;
        }
    done
    hazards="$(find -P "$source" -mindepth 1 \( -type l -o ! -uid 0 -o -perm /022 -o \( ! -type f -a ! -type d \) \) -print -quit)" || return 1
    [[ -z "$hazards" ]] || {
        echo "Read-only material tree has linked, writable, unowned or special entries." >&2; return 1;
    }
    setpriv --reuid "$uid" --regid "$gid" --clear-groups -- bash -c '
        cd / || exit 1
        path="$1"
        [[ -r "$path" && -x "$path" ]] || exit 1
        invalid="$(find -P "$path" \( -type d \( ! -readable -o ! -executable \) -o -type f ! -readable \) -print -quit)" || exit 1
        [[ -z "$invalid" ]]
    ' -- "$source" || {
        echo "Read-only material tree is not readable/traversable by runAs." >&2; return 1;
    }
    stat -c '%d:%i' "$source"
}
validate_material_entries() {
    [[ "${#D_MATERIAL_NAMES[@]}" -eq "${#D_MATERIAL_TARGETS[@]}" &&
       "${#D_MATERIAL_NAMES[@]}" -eq "${#D_MATERIAL_EXPECTED[@]}" ]] || {
        echo "Read-only material argument count mismatch." >&2; exit 33;
    }
    local index name target part prior data
    local -a segments targets=()
    data="$D_DATA_TARGET"
    for index in "${!D_MATERIAL_NAMES[@]}"; do
        name="$(b64d "${D_MATERIAL_NAMES[$index]}")"
        target="$(b64d "${D_MATERIAL_TARGETS[$index]}")"
        valid_slug "$name" || { echo "Invalid read-only material name." >&2; exit 33; }
        [[ "$target" == /* && "$target" != / && "$target" =~ ^/[A-Za-z0-9._~+:/-]+$ ]] || {
            echo "Invalid read-only material target." >&2; exit 33;
        }
        IFS='/' read -r -a segments <<< "${target#/}"
        for part in "${segments[@]}"; do
            [[ -n "$part" && "$part" != . && "$part" != .. ]] || {
                echo "Read-only material target is not normalized." >&2; exit 33;
            }
        done
        case "$target/" in
            /proc/*|/sys/*|/dev/*|/run/*|/var/run/*)
                echo "Read-only material target overlaps a system path." >&2; exit 33;;
        esac
        for prior in "${targets[@]}" "$data"; do
            [[ -z "$prior" ]] && continue
            if [[ "$target" == "$prior" || "$target" == "$prior/"* || "$prior" == "$target/"* ]]; then
                echo "Read-only material target overlaps another mount." >&2; exit 33
            fi
        done
        targets+=("$target")
    done
}
material_probe() {
    local check_expected="$1" index name source identity expected
    for index in "${!D_MATERIAL_NAMES[@]}"; do
        name="$(b64d "${D_MATERIAL_NAMES[$index]}")"
        source="$(material_source "$name")"
        identity="$(material_identity "$source" "$D_RUN_AS")" || return 1
        expected="${D_MATERIAL_EXPECTED[$index]}"
        if [[ "$check_expected" == true && "$identity" != "$expected" ]]; then
            echo "Read-only material directory changed after planning: $name" >&2; return 1
        fi
        if [[ "$check_expected" != true ]]; then
            printf 'MATERIAL\t%s\t%s\n' "$name" "$identity"
        fi
    done
}


epoch_source() { printf '%s/%s/%s' "$AUTH_EPOCH_ROOT" "$D_APP" "$D_ENV"; }
epoch_identity() {
    local source marker uid gid parent mode identity unsafe
    source="$(epoch_source)"; marker="$source.owner"
    uid="${D_RUN_AS%%:*}"; gid="$uid"
    [[ "$D_RUN_AS" != *:* ]] || gid="${D_RUN_AS#*:}"
    for parent in /var /var/lib "$AUTH_EPOCH_ROOT" "$AUTH_EPOCH_ROOT/$D_APP"; do
        [[ -d "$parent" && ! -L "$parent" && "$(stat -c '%u' "$parent")" == 0 ]] || return 1
        mode="$(stat -c '%a' "$parent")"
        (( (8#$mode & 022) == 0 )) || return 1
    done
    [[ -d "$source" && ! -L "$source" && -f "$marker" && ! -L "$marker" ]] || return 1
    [[ "$(stat -c '%u:%g:%a' "$source")" == "$uid:$gid:700" ]] || return 1
    [[ "$(stat -c '%u:%g:%a' "$marker")" == "0:0:600" ]] || return 1
    [[ "$(meta_value "$marker" OWNER_REPO)" == "$D_OWNER" &&
       "$(meta_value "$marker" APP_SLUG)" == "$D_APP" &&
       "$(meta_value "$marker" ENVIRONMENT)" == "$D_ENV" &&
       "$(meta_value "$marker" RUN_AS)" == "$D_RUN_AS" ]] || return 1
    identity="$(stat -c '%d:%i' "$source")" || return 1
    [[ "$(meta_value "$marker" SOURCE_ID)" == "$identity" ]] || return 1
    unsafe="$(find -P "$source" -mindepth 1 \( -type l -o ! -uid "$uid" -o ! -gid "$gid" -o -perm /022 -o \( ! -type f -a ! -type d \) \) -print -quit)" || return 1
    [[ -z "$unsafe" ]] || return 1
    printf '%s' "$identity"
}
epoch_provision() {
    [[ "$D_AUTH_EPOCH" == true ]] || return 0
    local source marker uid gid identity parent
    source="$(epoch_source)"; marker="$source.owner"
    uid="${D_RUN_AS%%:*}"; gid="$uid"
    [[ "$D_RUN_AS" != *:* ]] || gid="${D_RUN_AS#*:}"
    if [[ -e "$source" || -L "$source" || -e "$marker" || -L "$marker" ]]; then
        epoch_identity >/dev/null || { echo "External epoch store identity drift." >&2; return 1; }
        return 0
    fi
    [[ -d /var && ! -L /var && -d /var/lib && ! -L /var/lib ]] || return 1
    [[ "$(stat -c '%u' /var)" == 0 && "$(stat -c '%u' /var/lib)" == 0 ]] || return 1
    [[ ! -L "$AUTH_EPOCH_ROOT" && ! -L "$AUTH_EPOCH_ROOT/$D_APP" ]] || return 1
    if [[ ! -e "$AUTH_EPOCH_ROOT" ]]; then install -d -m 0711 -o 0 -g 0 "$AUTH_EPOCH_ROOT"; fi
    if [[ ! -e "$AUTH_EPOCH_ROOT/$D_APP" ]]; then install -d -m 0711 -o 0 -g 0 "$AUTH_EPOCH_ROOT/$D_APP"; fi
    for parent in "$AUTH_EPOCH_ROOT" "$AUTH_EPOCH_ROOT/$D_APP"; do
        [[ -d "$parent" && ! -L "$parent" && "$(stat -c '%u:%g:%a' "$parent")" == "0:0:711" ]] || return 1
    done
    install -d -m 0700 -o "$uid" -g "$gid" "$source" || return 1
    identity="$(stat -c '%d:%i' "$source")" || return 1
    (umask 077; printf 'OWNER_REPO=%s\nAPP_SLUG=%s\nENVIRONMENT=%s\nRUN_AS=%s\nSOURCE_ID=%s\n' "$D_OWNER" "$D_APP" "$D_ENV" "$D_RUN_AS" "$identity" > "$marker") || return 1
    chown 0:0 "$marker" && chmod 0600 "$marker" || return 1
    epoch_identity >/dev/null || { echo "External epoch provisioning failed." >&2; return 1; }
}
epoch_mount_verified() {
    local release="$1" container="$2" source identity mounts expected number
    [[ "$(meta_value "$release" AUTH_EPOCH_STORE || true)" == true ]] || return 1
    identity="$(epoch_identity)" || return 1
    [[ "$(meta_value "$release" AUTH_EPOCH_ID || true)" == "$identity" ]] || return 1
    source="$(epoch_source)"
    mounts="$(docker inspect --format '{{range .Mounts}}{{printf "%s@%s@%t@%s\n" .Source .Destination .RW .Type}}{{end}}' "$container" 2>/dev/null)" || return 1
    grep -Fxq -- "$source@$AUTH_EPOCH_TARGET@true@bind" <<< "$mounts" || return 1
    local actual_env data_target
    actual_env="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" 2>/dev/null)" || return 1
    grep -Fxq -- "$AUTH_EPOCH_ENV_KEY=$AUTH_EPOCH_TARGET/state.sqlite" <<< "$actual_env" || return 1
    if [[ "$(meta_value "$release" PERSISTENCE_MODE || true)" == directory ]]; then
        data_target="$(b64d "$(meta_value "$release" DATA_TARGET_B64 || true)")" || return 1
        grep -Fxq -- "$APP_ROOT/$D_APP/$D_ENV/data@$data_target@true@bind" <<< "$mounts" || return 1
    fi
    number="$(meta_value "$release" MATERIAL_COUNT || true)"
    expected=1
    [[ -z "$number" ]] || expected=$((expected + number))
    [[ "$(meta_value "$release" PERSISTENCE_MODE || true)" != directory ]] || expected=$((expected + 1))
    [[ "$(grep -c '.' <<< "$mounts" || true)" == "$expected" ]] || return 1
}

probe_http() {
    local container="$1" port="$2" path="$3"
    docker exec "$CADDY_CONTAINER" \
        wget -q -T 5 -O /dev/null "http://${container}:${port}${path}" >/dev/null 2>&1
}

wait_ready() {
    local container="$1" port="$2" path="$3"
    local deadline=$((SECONDS + 120)) state=""
    while (( SECONDS < deadline )); do
        state="$(docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)"
        if [[ "$state" == "running" ]] && network_has_container "$container" && probe_http "$container" "$port" "$path"; then
            return 0
        fi
        if [[ "$state" == "exited" || "$state" == "dead" ]]; then
            return 1
        fi
        sleep 2
    done
    return 1
}


material_inventory_state() {
    local file="$1" app="$2" env="$3" container="$4" persistence="$5"
    local number index name target source recorded current raw mounts run_as data_target line
    number="$(meta_value "$file" MATERIAL_COUNT || true)"
    MATERIAL_OK=true
    MATERIAL_ENTRIES=""
    [[ -n "$number" ]] || return 0
    [[ "$number" =~ ^[1-8]$ ]] || { echo "Invalid saved material count." >&2; return 1; }
    D_APP="$app"
    D_ENV="$env"
    run_as="$(meta_value "$file" RUN_AS || true)"
    valid_run_as "$run_as" || { echo "Invalid saved material runAs." >&2; return 1; }
    mounts="$(docker inspect --format '{{range .Mounts}}{{printf "%s@%s@%t@%s\n" .Source .Destination .RW .Type}}{{end}}' "$container" 2>/dev/null)" || {
        MATERIAL_OK=false
        mounts=""
    }
    local expected_count="$number"
    if [[ "$persistence" == directory ]]; then
        data_target="$(b64d "$(meta_value "$file" DATA_TARGET_B64 || true)")"
        line="$APP_ROOT/$app/$env/data@$data_target@true@bind"
        grep -Fxq -- "$line" <<< "$mounts" || MATERIAL_OK=false
        expected_count="$((number + 1))"
    fi
    [[ "$(meta_value "$file" AUTH_EPOCH_STORE || true)" != true ]] || expected_count=$((expected_count + 1))
    [[ "$(grep -c '.' <<< "$mounts" || true)" == "$expected_count" ]] || MATERIAL_OK=false
    for ((index=0; index < number; index++)); do
        name="$(b64d "$(meta_value "$file" MATERIAL_NAME_B64_"$index" || true)")"
        target="$(b64d "$(meta_value "$file" MATERIAL_TARGET_B64_"$index" || true)")"
        recorded="$(meta_value "$file" MATERIAL_ID_"$index" || true)"
        valid_slug "$name" && [[ "$target" =~ ^/[A-Za-z0-9._~+:/-]+$ && "$recorded" =~ ^[0-9]+:[0-9]+$ ]] || {
            echo "Invalid saved material mount metadata." >&2; return 1;
        }
        source="$(material_source "$name")"
        current="$(material_identity "$source" "$run_as" 2>/dev/null)" || { MATERIAL_OK=false; current=""; }
        [[ "$current" == "$recorded" ]] || MATERIAL_OK=false
        grep -Fxq -- "$source@$target@false@bind" <<< "$mounts" || MATERIAL_OK=false
        [[ -z "$MATERIAL_ENTRIES" ]] || MATERIAL_ENTRIES+=";"
        MATERIAL_ENTRIES+="$name@$target@$recorded"
    done
}

inventory() {
    local count=0 state current previous release_file
    local owner env app container image spec_sha port health persistence
    local running connected healthy present image_matches container_id
    if [[ -d "$APP_ROOT" ]]; then
        while IFS= read -r state; do
            [[ -n "$state" ]] || continue
            owner="$(meta_value "$state" OWNER_REPO || true)"
            env="$(meta_value "$state" ENVIRONMENT || true)"
            app="$(meta_value "$state" APP_SLUG || true)"
            current="$(meta_value "$state" CURRENT_RELEASE || true)"
            previous="$(meta_value "$state" PREVIOUS_RELEASE || true)"
            spec_sha="$(meta_value "$state" SPEC_SHA256 || true)"
            [[ -n "$owner" && -n "$env" && -n "$app" && -n "$current" && -n "$spec_sha" ]] || {
                echo "Managed application state is malformed: $state" >&2
                exit 31
            }
            release_file="$(dirname "$state")/releases/$current/release.env"
            [[ -f "$release_file" && ! -L "$release_file" ]] || {
                echo "Current application release metadata is missing: $release_file" >&2
                exit 31
            }
            container="$(meta_value "$release_file" CONTAINER_NAME || true)"
            image="$(meta_value "$release_file" IMAGE || true)"
            port="$(meta_value "$release_file" RUNTIME_PORT || true)"
            health="$(b64d "$(meta_value "$release_file" HEALTH_PATH_B64 || true)")"
            persistence="$(meta_value "$release_file" PERSISTENCE_MODE || true)"
            [[ "$(meta_value "$release_file" SPEC_SHA256 || true)" == "$spec_sha" ]] || {
                echo "Application state/release fingerprint mismatch: $state" >&2
                exit 31
            }
            valid_container "$container" || { echo "Invalid saved container name." >&2; exit 31; }
            container_identity "$container" || exit 31
            container_id="$CONTAINER_ID"
            running=false
            connected=false
            healthy=false
            present=false
            image_matches=false
            if [[ -n "$container_id" ]]; then
                present=true
                container_image_matches_release "$release_file" "$container_id" "$container" && image_matches=true || true
                [[ "$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true)" == "running" ]] && running=true || true
                network_has_container "$container" && connected=true || true
            fi
            if [[ "$running" == true && "$connected" == true && "$image_matches" == true ]]; then
                probe_http "$container" "$port" "$health" && healthy=true || true
            fi
            material_inventory_state "$release_file" "$app" "$env" "$container" "$persistence" || exit 31
            local epoch_opted=false epoch_ok=false epoch_id=""
            if [[ "$(meta_value "$release_file" AUTH_EPOCH_STORE || true)" == true ]]; then
                epoch_opted=true
                D_OWNER="$owner"; D_APP="$app"; D_ENV="$env"
                D_RUN_AS="$(meta_value "$release_file" RUN_AS || true)"
                epoch_id="$(meta_value "$release_file" AUTH_EPOCH_ID || true)"
                [[ "$epoch_id" =~ ^[0-9]+:[0-9]+$ ]] || { echo "Malformed saved epoch identity." >&2; exit 31; }
                if [[ -n "$container_id" ]]; then
                    epoch_mount_verified "$release_file" "$container_id" && epoch_ok=true || true
                fi
                [[ "$epoch_ok" == true ]] || healthy=false
            fi
            if [[ -n "$MATERIAL_ENTRIES" ]]; then
                printf 'APP\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
                    "$owner" "$env" "$app" "$container" "$image" "$spec_sha" "$port" "$health" "$persistence" \
                    "$current" "$previous" "$running" "$connected" "$healthy" "$MATERIAL_OK" "$MATERIAL_ENTRIES" \
                    "$present" "$image_matches"
            else
                printf 'APP\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
                    "$owner" "$env" "$app" "$container" "$image" "$spec_sha" "$port" "$health" "$persistence" \
                    "$current" "$previous" "$running" "$connected" "$healthy" "$present" "$image_matches"
            fi
            if [[ "$epoch_opted" == true ]]; then
                printf '\tEPOCH\t%s\t%s\n' "$epoch_ok" "$epoch_id"
            else
                printf '\n'
            fi
            count=$((count + 1))
        done < <(find "$APP_ROOT" -mindepth 3 -maxdepth 3 -type f -name deployment.env -print 2>/dev/null | sort)
    fi
    printf 'SUMMARY\tappCount\t%s\n' "$count"
}

configure_registry_auth() {
    [[ -n "$DEPLOY_USER" ]] || { echo "Deployment account is required." >&2; exit 32; }
    [[ "$DEPLOY_USER" =~ ^[A-Za-z_][A-Za-z0-9_.-]{0,31}$ ]] || {
        echo "Deployment account contains unsupported characters." >&2
        exit 32
    }
    local home config dir_mode file_mode deploy_uid
    home="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
    [[ -n "$home" && "$home" == /* ]] || { echo "Could not resolve deployment account home." >&2; exit 32; }
    config="$home/.docker"
    if [[ ! -e "$config/config.json" ]]; then
        return 0
    fi
    [[ -d "$config" && ! -L "$config" && -f "$config/config.json" && ! -L "$config/config.json" ]] || {
        echo "Docker credential path is not a regular protected directory/file." >&2
        exit 32
    }
    dir_mode="$(stat -c '%a' "$config")"
    file_mode="$(stat -c '%a' "$config/config.json")"
    deploy_uid="$(id -u "$DEPLOY_USER")"
    if (( (8#$dir_mode & 077) != 0 || (8#$file_mode & 077) != 0 )) ||
       [[ "$(stat -c '%u' "$config")" != "$deploy_uid" || "$(stat -c '%u' "$config/config.json")" != "$deploy_uid" ]]; then
        echo "Docker credentials must be owned by the deployment account and deny group/other access." >&2
        exit 32
    fi
    export DOCKER_CONFIG="$config"
}

decode_desired() {
    [[ "$DESIRED_PRESENT" == true ]] || { echo "Deploy action omitted desired runtime spec." >&2; exit 33; }
    D_OWNER="$(b64d "$D_OWNER_B64")"
    D_ENV="$(b64d "$D_ENV_B64")"
    D_APP="$(b64d "$D_APP_B64")"
    D_CONTAINER="$(b64d "$D_CONTAINER_B64")"
    D_IMAGE="$(b64d "$D_IMAGE_B64")"
    D_HEALTH="$(b64d "$D_HEALTH_B64")"
    D_RUN_AS="$(b64d "$D_RUN_AS_B64")"
    D_DATA_TARGET="$(b64d "$D_DATA_TARGET_B64")"

    valid_repo "$D_OWNER" || { echo "Invalid owner repository." >&2; exit 33; }
    valid_slug "$D_ENV" || { echo "Invalid environment slug." >&2; exit 33; }
    valid_slug "$D_APP" || { echo "Invalid application slug." >&2; exit 33; }
    valid_container "$D_CONTAINER" || { echo "Invalid container name." >&2; exit 33; }
    valid_image "$D_IMAGE" || { echo "Image is not an immutable sha256 digest reference." >&2; exit 33; }
    valid_port "$D_PORT" || { echo "Invalid runtime port." >&2; exit 33; }
    [[ "$D_HEALTH" == /* && "$D_HEALTH" != *$'\n'* && "$D_HEALTH" != *$'\r'* ]] || {
        echo "Invalid health path." >&2
        exit 33
    }
    valid_run_as "$D_RUN_AS" || { echo "Invalid numeric runAs value." >&2; exit 33; }
    [[ "$D_AUTH_EPOCH" == true || "$D_AUTH_EPOCH" == false ]] || { echo "Invalid epoch option." >&2; exit 33; }
    if [[ "$D_AUTH_EPOCH" == true ]]; then
        for index in "${!D_ENV_KEYS[@]}"; do
            [[ "$(b64d "${D_ENV_KEYS[$index]}")" != "$AUTH_EPOCH_ENV_KEY" ]] || { echo "Epoch environment override denied." >&2; exit 33; }
        done
        [[ -z "$D_DATA_TARGET" || ( "$D_DATA_TARGET" != "$AUTH_EPOCH_TARGET" && "$D_DATA_TARGET" != "$AUTH_EPOCH_TARGET/"* && "$AUTH_EPOCH_TARGET" != "$D_DATA_TARGET/"* ) ]] || {
            echo "Epoch path overlaps persistence." >&2; exit 33;
        }
    fi
    validate_material_entries
    [[ "$D_PERSISTENCE" == "none" || "$D_PERSISTENCE" == "directory" ]] || {
        echo "Invalid persistence mode." >&2
        exit 33
    }
    if [[ "$D_PERSISTENCE" == "directory" ]]; then
        [[ "$D_DATA_TARGET" == /* && "$D_DATA_TARGET" != *"/../"* && "$D_DATA_TARGET" != *$'\n'* ]] || {
            echo "Invalid persistent data container path." >&2
            exit 33
        }
    elif [[ -n "$D_DATA_TARGET" ]]; then
        echo "Non-persistent runtime unexpectedly supplied a data path." >&2
        exit 33
    fi
    [[ "$D_SPEC_SHA" =~ ^[0-9a-f]{64}$ ]] || { echo "Invalid runtime spec fingerprint." >&2; exit 33; }
    [[ "${#D_ENV_KEYS[@]}" -eq "${#D_ENV_VALUES[@]}" ]] || { echo "Environment payload mismatch." >&2; exit 33; }

    local index key
    for index in "${!D_ENV_KEYS[@]}"; do
        key="$(b64d "${D_ENV_KEYS[$index]}")"
        valid_env_key "$key" || { echo "Invalid environment variable name." >&2; exit 33; }
    done
}

release_value() {
    meta_value "$1" "$2"
}

write_release_metadata() {
    local release_file="$1"
    local tmp="$release_file.tmp.$$" index key_b64 value_b64
    {
        printf 'SCHEMA_VERSION=%s\n' "$APP_SCHEMA_VERSION"
        printf 'OWNER_REPO=%s\n' "$D_OWNER"
        printf 'ENVIRONMENT=%s\n' "$D_ENV"
        printf 'APP_SLUG=%s\n' "$D_APP"
        printf 'CONTAINER_NAME=%s\n' "$D_CONTAINER"
        printf 'IMAGE=%s\n' "$D_IMAGE"
        printf 'RUNTIME_IMAGE_ID=%s\n' "$D_RUNTIME_IMAGE_ID"
        printf 'RUNTIME_PORT=%s\n' "$D_PORT"
        printf 'HEALTH_PATH_B64=%s\n' "$D_HEALTH_B64"
        printf 'RUN_AS=%s\n' "$D_RUN_AS"
        printf 'PERSISTENCE_MODE=%s\n' "$D_PERSISTENCE"
        printf 'DATA_TARGET_B64=%s\n' "$D_DATA_TARGET_B64"
        printf 'SPEC_SHA256=%s\n' "$D_SPEC_SHA"
        if [[ "$D_AUTH_EPOCH" == true ]]; then
            printf 'AUTH_EPOCH_STORE=true\n'
            printf 'AUTH_EPOCH_ID=%s\n' "$(epoch_identity)"
        fi
        if (( ${#D_MATERIAL_NAMES[@]} > 0 )); then
            printf 'MATERIAL_COUNT=%s\n' "${#D_MATERIAL_NAMES[@]}"
            for index in "${!D_MATERIAL_NAMES[@]}"; do
                printf 'MATERIAL_NAME_B64_%s=%s\n' "$index" "${D_MATERIAL_NAMES[$index]}"
                printf 'MATERIAL_TARGET_B64_%s=%s\n' "$index" "${D_MATERIAL_TARGETS[$index]}"
                printf 'MATERIAL_ID_%s=%s\n' "$index" "${D_MATERIAL_EXPECTED[$index]}"
            done
        fi
        printf 'ENV_COUNT=%s\n' "${#D_ENV_KEYS[@]}"
        for index in "${!D_ENV_KEYS[@]}"; do
            key_b64="${D_ENV_KEYS[$index]}"
            value_b64="${D_ENV_VALUES[$index]}"
            printf 'ENV_KEY_B64_%s=%s\n' "$index" "$key_b64"
            printf 'ENV_VALUE_B64_%s=%s\n' "$index" "$value_b64"
        done
    } > "$tmp"
    chmod 0600 "$tmp"
    mv -f "$tmp" "$release_file"
}

start_desired_container() {
    local root data
    local uid gid index key value created_id
    local -a D_MATERIAL_NAMES=("${D_MATERIAL_NAMES[@]}")
    root="$1"
    data="$root/data"
    uid="${D_RUN_AS%%:*}"
    if [[ "$D_RUN_AS" == *:* ]]; then gid="${D_RUN_AS#*:}"; else gid="$uid"; fi

    if [[ "$D_PERSISTENCE" == "directory" ]]; then
        if [[ -L "$data" ]]; then
            echo "Persistent data directory must not be a symbolic link." >&2
            return 1
        fi
        if [[ ! -e "$data" ]]; then
            install -d -m 0750 -o "$uid" -g "$gid" "$data"
        elif [[ ! -d "$data" ]]; then
            echo "Persistent data path is not a directory." >&2
            return 1
        elif [[ "$(stat -c '%u' "$data")" != "$uid" || "$(stat -c '%g' "$data")" != "$gid" ]]; then
            echo "Persistent data directory ownership does not match runAs; use the persistence adapter/import path." >&2
            return 1
        fi
    fi

    local -a docker_args
    docker_args=(
        docker run -d
        --name "$D_CONTAINER"
        --restart unless-stopped
        --network "$NETWORK_NAME"
        --user "$D_RUN_AS"
        --log-driver json-file
        --log-opt max-size=10m
        --log-opt max-file=3
    )
    if [[ "$D_PERSISTENCE" == "directory" ]]; then
        docker_args+=(--mount "type=bind,src=$data,dst=$D_DATA_TARGET")
    fi
    for index in "${!D_ENV_KEYS[@]}"; do
        key="$(b64d "${D_ENV_KEYS[$index]}")"
        value="$(b64d "${D_ENV_VALUES[$index]}")"
        docker_args+=(--env "$key=$value")
    done
    if [[ "${D_AUTH_EPOCH:-false}" == true ]]; then
        epoch_identity >/dev/null || { echo "Epoch identity drift before container create." >&2; return 1; }
        docker_args+=(--mount "type=bind,src=$(epoch_source),dst=$AUTH_EPOCH_TARGET")
        docker_args+=(--env "$AUTH_EPOCH_ENV_KEY=$AUTH_EPOCH_TARGET/state.sqlite")
    fi
    for index in "${!D_MATERIAL_NAMES[@]}"; do
        local source target name
        name="$(b64d "${D_MATERIAL_NAMES[$index]}")"
        target="$(b64d "${D_MATERIAL_TARGETS[$index]}")"
        source="$(material_source "$name")"
        docker_args+=(--mount "type=bind,src=$source,dst=$target,readonly")
    done
    docker_args+=("$D_IMAGE")
    created_id="$("${docker_args[@]}")" || return 1
    [[ "$created_id" =~ ^[0-9a-f]{64}$ ]] || {
        echo "Docker did not return an exact new container ID." >&2; return 1;
    }
    STARTED_CONTAINER_ID="$created_id"
}

record_evidence() {
    local root="$1" outcome="$2" release_id="$3" previous="$4"
    local timestamp
    timestamp="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf '{"timestamp":"%s","ownerRepo":"%s","environment":"%s","appSlug":"%s","container":"%s","image":"%s","specSha256":"%s","release":"%s","previousRelease":"%s","persistence":"%s","outcome":"%s"}\n' \
        "$timestamp" "$D_OWNER" "$D_ENV" "$D_APP" "$D_CONTAINER" "$D_IMAGE" "$D_SPEC_SHA" \
        "$release_id" "$previous" "$D_PERSISTENCE" "$outcome" >> "$root/deployment-evidence.jsonl"
    chmod 0600 "$root/deployment-evidence.jsonl"
}

acquire_deployment_lock() {
    local lock_file="$1"
    if [[ -z "$HELD_LOCK_FD" ]]; then
        exec 9>>"$lock_file"
        flock -n 9 || {
            echo "Another application deployment holds the lock for $D_APP--$D_ENV." >&2
            exit 75
        }
        return 0
    fi

    [[ "$ACTION" == "deploy" && "$EXPECTED_SPEC_SHA" =~ ^[0-9a-f]{64}$ ]] || {
        echo "An inherited lock is supported only for existing application deployments." >&2
        exit 75
    }
    [[ "$HELD_LOCK_FD" =~ ^[0-9]+$ ]] && (( 10#$HELD_LOCK_FD >= 3 && 10#$HELD_LOCK_FD <= 256 )) || {
        echo "Inherited application lock descriptor is invalid." >&2
        exit 75
    }
    [[ -f "$lock_file" && ! -L "$lock_file" ]] || {
        echo "Inherited application lock path is invalid." >&2
        exit 75
    }
    local inherited_inode expected_inode
    inherited_inode="$(stat -Lc '%d:%i' "/proc/self/fd/$HELD_LOCK_FD" 2>/dev/null || true)"
    expected_inode="$(stat -Lc '%d:%i' "$lock_file" 2>/dev/null || true)"
    [[ -n "$inherited_inode" && "$inherited_inode" == "$expected_inode" ]] || {
        echo "Inherited application lock descriptor does not match this app/environment." >&2
        exit 75
    }
    grep -Eq '^lock:[[:space:]]+[0-9]+:[[:space:]]+FLOCK[[:space:]]+ADVISORY[[:space:]]+WRITE([[:space:]]|$)' \
        "/proc/self/fdinfo/$HELD_LOCK_FD" || {
        echo "Inherited application lock was not held by this descriptor." >&2
        exit 75
    }
}

deploy() {
    platform_ready || { echo "Kit shared platform is not ready." >&2; exit 34; }
    decode_desired
    configure_registry_auth

    local root releases state current_release="" previous_release="" current_spec="" current_container="" current_id="" next_previous=""
    local digest release_id release_dir release_file lock_file tmp recorded_image_id
    local previous_generation=0 next_generation
    root="$APP_ROOT/$D_APP/$D_ENV"
    releases="$root/releases"
    state="$root/deployment.env"
    lock_file="/run/lock/project-forge-app-$D_APP--$D_ENV.lock"
    digest="${D_IMAGE##*@sha256:}"
    release_id="sha256-${digest}-${D_SPEC_SHA:0:16}"
    release_dir="$releases/$release_id"
    release_file="$release_dir/release.env"

    acquire_deployment_lock "$lock_file"
    material_probe true || { echo "Read-only material preflight failed." >&2; exit 40; }

    for path in "$root" "$releases" "$state" "$root/data" "$root/deployment-evidence.jsonl"; do
        [[ ! -L "$path" ]] || { echo "Managed application path must not be a symbolic link: $path" >&2; exit 35; }
    done

    if [[ -f "$state" ]]; then
        [[ "$(meta_value "$state" OWNER_REPO || true)" == "$D_OWNER" &&
           "$(meta_value "$state" ENVIRONMENT || true)" == "$D_ENV" &&
           "$(meta_value "$state" APP_SLUG || true)" == "$D_APP" ]] || {
            echo "Existing application state has different ownership." >&2
            exit 35
        }
        current_release="$(meta_value "$state" CURRENT_RELEASE || true)"
        previous_release="$(meta_value "$state" PREVIOUS_RELEASE || true)"
        current_spec="$(meta_value "$state" SPEC_SHA256 || true)"
        previous_generation="$(meta_value "$state" DEPLOYMENT_GENERATION || true)"
        # Legacy state has no generation and cannot be attested until the next
        # authorized, successfully verified managed deployment.
        [[ -n "$previous_generation" ]] || previous_generation=0
        [[ "$previous_generation" =~ ^(0|[1-9][0-9]*)$ &&
           "${#previous_generation}" -le 18 ]] || {
            echo "Managed deployment generation is not a bounded integer." >&2
            exit 35
        }
        [[ -n "$current_release" && "$current_spec" =~ ^[0-9a-f]{64}$ ]] || {
            echo "Existing application state is malformed." >&2
            exit 35
        }
        [[ "$EXPECTED_SPEC_SHA" != "NONE" && "$current_spec" == "$EXPECTED_SPEC_SHA" ]] || {
            echo "Application state changed after planning; create a fresh plan." >&2
            exit 36
        }
        local current_file="$releases/$current_release/release.env"
        [[ -f "$current_file" && ! -L "$current_file" ]] || {
            echo "Current release metadata is missing." >&2
            exit 35
        }
        [[ "$(release_value "$current_file" SPEC_SHA256 || true)" == "$current_spec" ]] || {
            echo "Current release fingerprint differs from application state." >&2; exit 35;
        }
        current_container="$(release_value "$current_file" CONTAINER_NAME || true)"
        valid_container "$current_container" || { echo "Current release container metadata is malformed." >&2; exit 35; }
        container_identity "$current_container" || exit 35
        current_id="$CONTAINER_ID"
        if [[ -n "$current_id" ]] && ! container_image_matches_release "$current_file" "$current_id" "$current_container"; then
            echo "Live container image differs from the managed release; reconcile ownership before deploying." >&2
            exit 35
        fi
        if [[ "$current_spec" == "$D_SPEC_SHA" ]]; then
            next_previous="$previous_release"
        else
            next_previous="$current_release"
        fi
    else
        [[ "$EXPECTED_SPEC_SHA" == "NONE" ]] || {
            echo "Application state disappeared after planning; create a fresh plan." >&2
            exit 36
        }
    fi

    if [[ -n "$current_release" && "$(meta_value "$current_file" AUTH_EPOCH_STORE || true)" == true ]]; then
        [[ "$D_AUTH_EPOCH" == true ]] || { echo "Removing epoch storage requires reconciliation." >&2; exit 35; }
        epoch_identity >/dev/null || { echo "Existing authentication epoch store cannot be verified." >&2; exit 35; }
        [[ "$(meta_value "$current_file" AUTH_EPOCH_ID)" =~ ^[0-9]+:[0-9]+$ &&
           "$(meta_value "$current_file" AUTH_EPOCH_ID)" == "$(epoch_identity)" ]] || { echo "Existing authentication epoch identity drift." >&2; exit 35; }
        if [[ -n "$current_id" ]]; then
            epoch_mount_verified "$current_file" "$current_id" || { echo "Existing epoch mount identity changed." >&2; exit 35; }
        fi
    fi
    if [[ "$D_AUTH_EPOCH" == true ]]; then
        epoch_provision || { echo "Authentication epoch provisioning failed." >&2; exit 35; }
    fi

    # Root-owned Project/environment state is under the existing deployment
    # lock and outside application data/backup volumes. A normal update or
    # rollback must not reuse the earlier generation.
    next_generation=$((previous_generation + 1))
    [[ "$next_generation" -gt "$previous_generation" &&
       "$next_generation" -lt 9223372036854775807 ]] || {
        echo "Managed deployment generation would overflow." >&2
        exit 35
    }

    if docker inspect "$D_CONTAINER" >/dev/null 2>&1 && [[ "$D_CONTAINER" != "$current_container" ]]; then
        echo "Desired container name is already occupied outside this managed runtime." >&2
        exit 37
    fi

    install -d -m 0750 "$APP_ROOT" "$APP_ROOT/$D_APP" "$root" "$releases"
    if [[ -L "$release_dir" || -L "$release_file" || ( -e "$release_dir" && ! -d "$release_dir" ) ]]; then
        echo "Release path exists and is not a directory." >&2
        exit 35
    fi
    install -d -m 0750 "$release_dir"
    docker pull "$D_IMAGE" >/dev/null
    D_RUNTIME_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$D_IMAGE")" || {
        echo "Pulled application image could not be inspected." >&2; exit 35;
    }
    [[ "$D_RUNTIME_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || {
        echo "Pulled application image has an invalid Docker config ID." >&2; exit 35;
    }
    if [[ -f "$release_file" ]]; then
        [[ "$(release_value "$release_file" SPEC_SHA256 || true)" == "$D_SPEC_SHA" ]] || {
            echo "Release directory collision with different runtime metadata." >&2
            exit 35
        }
        if [[ "$D_AUTH_EPOCH" == true ]]; then
            [[ "$(release_value "$release_file" AUTH_EPOCH_STORE || true)" == true &&
               "$(release_value "$release_file" AUTH_EPOCH_ID || true)" == "$(epoch_identity)" ]] || {
                echo "Previously recorded release has different epoch directory identity." >&2; exit 35;
            }
        elif [[ "$(release_value "$release_file" AUTH_EPOCH_STORE || true)" == true ]]; then
            echo "Existing release requires its authentication epoch store." >&2; exit 35;
        fi
        recorded_image_id="$(release_value "$release_file" RUNTIME_IMAGE_ID || true)"
        [[ -z "$recorded_image_id" || "$recorded_image_id" == "$D_RUNTIME_IMAGE_ID" ]] || {
            echo "Release image ID differs from previously recorded runtime identity." >&2; exit 35;
        }
        if (( ${#D_MATERIAL_NAMES[@]} > 0 )); then
            [[ "$(release_value "$release_file" MATERIAL_COUNT || true)" == "${#D_MATERIAL_NAMES[@]}" ]] || {
                echo "Existing release material metadata mismatch." >&2; exit 35;
            }
            for index in "${!D_MATERIAL_NAMES[@]}"; do
                [[ "$(release_value "$release_file" MATERIAL_ID_"$index" || true)" == "${D_MATERIAL_EXPECTED[$index]}" ]] || {
                    echo "Existing release material directory identity changed." >&2; exit 35;
                }
            done
        fi
        if [[ -z "$recorded_image_id" ]]; then
            tmp="$release_file.tmp.$$"
            cat "$release_file" > "$tmp"
            printf 'RUNTIME_IMAGE_ID=%s\n' "$D_RUNTIME_IMAGE_ID" >> "$tmp"
            chmod 0600 "$tmp"
            mv -f "$tmp" "$release_file"
        fi
    else
        write_release_metadata "$release_file"
    fi

    material_probe true || { echo "Read-only material source changed before runtime replacement." >&2; exit 40; }
    if [[ "$D_AUTH_EPOCH" == true ]]; then
        [[ "$(epoch_identity)" == "$(release_value "$release_file" AUTH_EPOCH_ID || true)" ]] || {
            echo "Epoch identity drift before replacement." >&2; exit 40;
        }
    fi

    if [[ -n "$current_id" ]]; then
        container_image_matches_release "$current_file" "$current_id" "$current_container" || {
            echo "Live container image or identity changed before replacement." >&2; exit 35;
        }
        docker rm -f "$current_id" >/dev/null
    fi

    if ! start_desired_container "$root"; then
        record_evidence "$root" "failed-start" "$release_id" "$current_release"
        echo "Application container failed to start; an unverified container was not removed, and runtime rollback was not attempted." >&2
        exit 38
    fi
    if ! wait_ready "$D_CONTAINER" "$D_PORT" "$D_HEALTH"; then
        if container_image_matches_release "$release_file" "$STARTED_CONTAINER_ID" "$D_CONTAINER"; then
            docker rm -f "$STARTED_CONTAINER_ID" >/dev/null || echo "Failed to remove the verified unready container." >&2
        else
            echo "Unverified new container was not removed." >&2
        fi
        record_evidence "$root" "failed-readiness" "$release_id" "$current_release"
        echo "Application failed readiness; previous release metadata was retained but runtime rollback was not attempted." >&2
        exit 39
    fi
    if [[ "$D_AUTH_EPOCH" == true ]]; then
        epoch_mount_verified "$release_file" "$STARTED_CONTAINER_ID" || {
            echo "New runtime epoch mount differs from exact expected identity." >&2; exit 39;
        }
    fi
    container_image_matches_release "$release_file" "$STARTED_CONTAINER_ID" "$D_CONTAINER" || {
        echo "New container identity changed before readiness was recorded." >&2; exit 39;
    }

    tmp="$state.tmp.$$"
    {
        printf 'SCHEMA_VERSION=%s\n' "$APP_SCHEMA_VERSION"
        printf 'OWNER_REPO=%s\n' "$D_OWNER"
        printf 'ENVIRONMENT=%s\n' "$D_ENV"
        printf 'APP_SLUG=%s\n' "$D_APP"
        printf 'CURRENT_RELEASE=%s\n' "$release_id"
        printf 'PREVIOUS_RELEASE=%s\n' "$next_previous"
        printf 'SPEC_SHA256=%s\n' "$D_SPEC_SHA"
        printf 'DEPLOYMENT_GENERATION=%s\n' "$next_generation"
    } > "$tmp"
    chmod 0600 "$tmp"
    mv -f "$tmp" "$state"
    record_evidence "$root" "deployed" "$release_id" "$next_previous"
}


# Read-only privileged observation of the exact live managed release. This is
# neither a signed attestation nor a Production deployment authorization.
inspect_release_for_attestation() {
    decode_desired
    platform_ready || { echo "Shared host is not ready for release observation." >&2; exit 41; }
    local root state current release_file actual recorded generation
    local source version manifest_hash revision_source release_id operation_hash state_before state_after status
    root="$APP_ROOT/$D_APP/$D_ENV"
    state="$root/deployment.env"
    [[ -d "$root" && ! -L "$root" && -f "$state" && ! -L "$state" ]] || {
        echo "Trusted managed release state is missing." >&2; exit 41;
    }
    [[ "$(stat -c '%u' "$state")" == 0 &&
       "$(stat -c '%a' "$state")" == 600 ]] || {
        echo "Release state ownership is unsafe." >&2; exit 41;
    }
    state_before="$(sha256sum "$state" | cut -d ' ' -f1)"
    [[ "$(meta_value "$state" OWNER_REPO || true)" == "$D_OWNER" &&
       "$(meta_value "$state" ENVIRONMENT || true)" == "$D_ENV" &&
       "$(meta_value "$state" APP_SLUG || true)" == "$D_APP" &&
       "$(meta_value "$state" SPEC_SHA256 || true)" == "$D_SPEC_SHA" ]] || {
        echo "Release state differs from the authorized application." >&2; exit 41;
    }
    current="$(meta_value "$state" CURRENT_RELEASE || true)"
    generation="$(meta_value "$state" DEPLOYMENT_GENERATION || true)"
    [[ "$current" =~ ^sha256-[0-9a-f]{64}-[0-9a-f]{16}$ &&
       "$generation" =~ ^[1-9][0-9]*$ &&
       "${#generation}" -le 18 ]] || {
        echo "Unverified legacy release or invalid host deployment generation." >&2; exit 41;
    }
    release_file="$root/releases/$current/release.env"
    [[ -f "$release_file" && ! -L "$release_file" &&
       "$(stat -c '%u' "$release_file")" == 0 &&
       "$(stat -c '%a' "$release_file")" == 600 ]] || {
        echo "Privileged release record unavailable." >&2; exit 41;
    }
    release_id="$(meta_value "$release_file" IMAGE || true)"
    recorded="$(meta_value "$release_file" RUNTIME_IMAGE_ID || true)"
    [[ "$release_id" == "$D_IMAGE" &&
       "$(meta_value "$release_file" SPEC_SHA256 || true)" == "$D_SPEC_SHA" &&
       "$(meta_value "$release_file" OWNER_REPO || true)" == "$D_OWNER" &&
       "$(meta_value "$release_file" ENVIRONMENT || true)" == "$D_ENV" &&
       "$(meta_value "$release_file" CONTAINER_NAME || true)" == "$D_CONTAINER" &&
       "$recorded" =~ ^sha256:[0-9a-f]{64}$ ]] || {
        echo "Release image metadata does not match the authorized spec." >&2; exit 41;
    }
    container_identity "$D_CONTAINER" || exit 41
    [[ -n "$CONTAINER_ID" ]] || {
        echo "No verified application container exists." >&2; exit 41;
    }
    container_image_matches_release "$release_file" "$CONTAINER_ID" "$D_CONTAINER" || {
        echo "Live Docker image differs from the approved release." >&2; exit 41;
    }
    status="$(docker inspect --format '{{.State.Status}}' "$CONTAINER_ID" 2>/dev/null)" || exit 41
    [[ "$status" == running ]] && network_has_container "$D_CONTAINER" &&
       probe_http "$D_CONTAINER" "$D_PORT" "$D_HEALTH" || {
        echo "Live runtime is not verified healthy." >&2; exit 41;
    }
    material_inventory_state "$release_file" "$D_APP" "$D_ENV" "$D_CONTAINER" "$D_PERSISTENCE" || exit 41
    if [[ "$(meta_value "$release_file" AUTH_EPOCH_STORE || true)" == true ]]; then
        epoch_mount_verified "$release_file" "$CONTAINER_ID" || { echo "Release epoch mount is unverified." >&2; exit 41; }
    fi
    [[ "$MATERIAL_OK" == true ]] || {
        echo "Approved read-only runtime material mounts are not verified." >&2; exit 41;
    }
    actual="$(docker inspect --format '{{.Image}}' "$CONTAINER_ID" 2>/dev/null)" || exit 41
    [[ "$actual" == "$recorded" ]] || {
        echo "Live image and root-owned release identity differ." >&2; exit 41;
    }
    revision_source="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.source"}}' "$actual" 2>/dev/null)" || exit 41
    source="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$actual" 2>/dev/null)" || exit 41
    version="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$actual" 2>/dev/null)" || exit 41
    manifest_hash="$(docker image inspect --format '{{index .Config.Labels "com.mriekki.application.release-notes-manifest-sha256"}}' "$actual" 2>/dev/null)" || exit 41
    [[ "$revision_source" == "https://github.com/$D_OWNER" &&
       "$source" =~ ^[0-9a-f]{40}$ &&
       "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ &&
       "$manifest_hash" =~ ^[0-9a-f]{64}$ ]] || {
        echo "Image has no approved source, semantic version or manifest digest." >&2; exit 41;
    }
    state_after="$(sha256sum "$state" | cut -d ' ' -f1)"
    [[ "$state_before" == "$state_after" ]] || {
        echo "Release changed during host observation; verify again." >&2; exit 41;
    }
    operation_hash="$(printf '%s' "$D_OWNER|$D_APP|$D_ENV|$current|$generation|$CONTAINER_ID" | sha256sum | cut -d ' ' -f1)"
    [[ "$operation_hash" =~ ^[0-9a-f]{64}$ ]] || exit 41
    printf 'RELEASE_OBSERVATION\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\tpfrelease:%s\n' \
        "$D_OWNER" "$D_APP" "$D_ENV" "$D_IMAGE" "$D_SPEC_SHA" "$source" \
        "$manifest_hash" "$version" "$actual" "$generation" "$operation_hash"
}

case "$ACTION" in
    inventory)
        inventory
        ;;
    deploy)
        deploy
        ;;
    material-inspect)
        decode_desired
        material_probe false || exit 40
        ;;
    release-inspect)
        inspect_release_for_attestation
        ;;
    *)
        echo "Unsupported application-runtime action: $ACTION" >&2
        exit 2
        ;;
esac
'''