"""Remote script for owned route registration on a Kit-managed Ubuntu box."""

REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="$1"
SPEC="${2:-}"
EXPECTED_SPEC="${3:-}"
PLATFORM_ROOT="__PLATFORM_ROOT__"
PROXY_ROOT="$PLATFORM_ROOT/proxy"
ROUTE_ROOT="$PLATFORM_ROOT/routes"
MARKER="$PLATFORM_ROOT/platform.env"
LOCK_FILE="/run/lock/project-forge-platform.lock"
NETWORK_NAME="__NETWORK_NAME__"
CADDY_CONTAINER="__CADDY_CONTAINER__"
CADDY_IMAGE="__CADDY_IMAGE__"
PLATFORM_SCHEMA_VERSION="__PLATFORM_SCHEMA_VERSION__"
PLATFORM_VERSION="__PLATFORM_VERSION__"
PLATFORM_DISTRIBUTION="__PLATFORM_DISTRIBUTION__"
ROUTE_SCHEMA_VERSION="__ROUTE_SCHEMA_VERSION__"
ALIAS_ROOT="/etc/project-forge-platform/aliases"
ALIAS_SERVICE="project-forge-avahi-alias@"

platform_value() {
    local key="$1"
    [[ -f "$MARKER" ]] || return 1
    sed -n "s/^${key}=//p" "$MARKER" | head -n1
}
platform_state() {
    if [[ ! -f "$MARKER" ]]; then
        printf 'missing-platform'
        return
    fi
    if [[ "$(platform_value SCHEMA_VERSION || true)" != "$PLATFORM_SCHEMA_VERSION" || \
          "$(platform_value DISTRIBUTION || true)" != "$PLATFORM_DISTRIBUTION" ]]; then
        printf 'incompatible'
        return
    fi
    if [[ "$(platform_value PLATFORM_VERSION || true)" != "$PLATFORM_VERSION" ]]; then
        printf 'upgrade-required'
        return
    fi
    if [[ "$(docker inspect --format '{{.State.Status}}' "$CADDY_CONTAINER" 2>/dev/null || true)" != "running" ]]; then
        printf 'drifted'
        return
    fi
    if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
        printf 'drifted'
        return
    fi
    if [[ ! -f "$PROXY_ROOT/Caddyfile" || ! -d "$PROXY_ROOT/conf.d" || ! -d "$ROUTE_ROOT" ]]; then
        printf 'drifted'
        return
    fi
    printf 'ready'
}

valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_container() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; }
valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && (( 1 <= 10#$1 && 10#$1 <= 65535 )); }
valid_hostname() {
    local host="$1" label
    [[ "$host" == *.local ]] || return 1
    [[ ${#host} -le 253 ]] || return 1
    [[ "$host" != *:* && "$host" != *" "* && "$host" != */* && "$host" != *,* ]] || return 1
    IFS='.' read -r -a LABELS <<< "$host"
    (( ${#LABELS[@]} >= 2 )) || return 1
    for label in "${LABELS[@]}"; do
        [[ "$label" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || return 1
    done
}

parse_spec() {
    IFS=$'\t' read -r S_SCHEMA S_OWNER S_ENV S_APP S_ROUTE S_UPSTREAM S_PORT S_HOSTS extra <<< "$SPEC"
    [[ -z "${extra:-}" ]] || { echo "Route spec has too many fields." >&2; exit 20; }
    [[ "$S_SCHEMA" == "$ROUTE_SCHEMA_VERSION" ]] || { echo "Unsupported route schema." >&2; exit 20; }
    valid_repo "$S_OWNER" || { echo "Invalid owner repo." >&2; exit 20; }
    valid_slug "$S_ENV" || { echo "Invalid environment slug." >&2; exit 20; }
    valid_slug "$S_APP" || { echo "Invalid app slug." >&2; exit 20; }
    [[ "$S_ROUTE" == "$S_APP--$S_ENV" ]] || { echo "Route ID mismatch." >&2; exit 20; }
    valid_container "$S_UPSTREAM" || { echo "Invalid upstream container." >&2; exit 20; }
    valid_port "$S_PORT" || { echo "Invalid upstream port." >&2; exit 20; }
    [[ -n "$S_HOSTS" ]] || { echo "No route hostnames supplied." >&2; exit 20; }
    IFS=',' read -r -a HOST_ARRAY <<< "$S_HOSTS"
    local host seen="|"
    for host in "${HOST_ARRAY[@]}"; do
        valid_hostname "$host" || { echo "Invalid route hostname: $host" >&2; exit 20; }
        [[ "$seen" != *"|$host|"* ]] || { echo "Duplicate route hostname: $host" >&2; exit 20; }
        seen="$seen$host|"
    done
}

metadata_path() { printf '%s/%s.route' "$ROUTE_ROOT" "$1"; }
route_path() { printf '%s/conf.d/20-%s.caddy' "$PROXY_ROOT" "$1"; }
alias_path() { printf '%s/%s.env' "$ALIAS_ROOT" "$1"; }

metadata_value() {
    local path="$1" key="$2"
    sed -n "s/^${key}=//p" "$path" | head -n1
}

emit_route() {
    local path="$1" schema owner env app route upstream port hosts
    schema="$(metadata_value "$path" SCHEMA_VERSION)"
    owner="$(metadata_value "$path" OWNER_REPO)"
    env="$(metadata_value "$path" ENVIRONMENT)"
    app="$(metadata_value "$path" APP_SLUG)"
    route="$(metadata_value "$path" ROUTE_ID)"
    upstream="$(metadata_value "$path" UPSTREAM_CONTAINER)"
    port="$(metadata_value "$path" UPSTREAM_PORT)"
    hosts="$(metadata_value "$path" HOSTNAMES)"
    printf 'ROUTE\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$schema" "$owner" "$env" "$app" "$route" "$upstream" "$port" "$hosts"
}

inventory() {
    local state count=0 path
    state="$(platform_state)"
    if [[ -d "$ROUTE_ROOT" ]]; then
        while IFS= read -r path; do
            [[ -n "$path" ]] || continue
            count=$((count + 1))
        done < <(find "$ROUTE_ROOT" -maxdepth 1 -type f -name '*.route' -print 2>/dev/null | sort)
    fi
    printf 'SUMMARY\tplatformState\t%s\n' "$state"
    printf 'SUMMARY\tmanagedRouteCount\t%s\n' "$count"
    if [[ -d "$ROUTE_ROOT" ]]; then
        while IFS= read -r path; do
            [[ -n "$path" ]] || continue
            emit_route "$path"
        done < <(find "$ROUTE_ROOT" -maxdepth 1 -type f -name '*.route' -print 2>/dev/null | sort)
    fi
}

require_ready() {
    local state
    state="$(platform_state)"
    [[ "$state" == ready ]] || { echo "Kit-owned shared platform is not ready: $state" >&2; exit 21; }
}

metadata_matches_spec() {
    local path="$1" encoded="$2"
    local e_schema e_owner e_env e_app e_route e_upstream e_port e_hosts e_extra
    IFS=$'\t' read -r e_schema e_owner e_env e_app e_route e_upstream e_port e_hosts e_extra <<< "$encoded"
    [[ -z "${e_extra:-}" ]] || return 1
    [[ "$(metadata_value "$path" SCHEMA_VERSION)" == "$e_schema" && \
       "$(metadata_value "$path" OWNER_REPO)" == "$e_owner" && \
       "$(metadata_value "$path" ENVIRONMENT)" == "$e_env" && \
       "$(metadata_value "$path" APP_SLUG)" == "$e_app" && \
       "$(metadata_value "$path" ROUTE_ID)" == "$e_route" && \
       "$(metadata_value "$path" UPSTREAM_CONTAINER)" == "$e_upstream" && \
       "$(metadata_value "$path" UPSTREAM_PORT)" == "$e_port" && \
       "$(metadata_value "$path" HOSTNAMES)" == "$e_hosts" ]]
}

assert_expected_previous() {
    local meta
    meta="$(metadata_path "$S_ROUTE")"
    if [[ "$EXPECTED_SPEC" == "NONE" ]]; then
        [[ ! -e "$meta" ]] || { echo "Route appeared after planning; create a fresh plan." >&2; exit 28; }
        return 0
    fi
    [[ -f "$meta" && ! -L "$meta" ]] || { echo "Expected previous route metadata is missing or unsafe." >&2; exit 28; }
    metadata_matches_spec "$meta" "$EXPECTED_SPEC" || {
        echo "Registered route changed after planning; create a fresh plan." >&2
        exit 28
    }
}

check_alias_collisions() {
    local meta current_hosts="" host apath
    meta="$(metadata_path "$S_ROUTE")"
    if [[ -f "$meta" ]]; then current_hosts="$(metadata_value "$meta" HOSTNAMES)"; fi
    for host in "${HOST_ARRAY[@]}"; do
        apath="$(alias_path "$host")"
        if [[ -L "$apath" ]]; then
            echo "Alias registration path is a symbolic link: $apath" >&2
            exit 29
        fi
        if [[ -e "$apath" && ",${current_hosts}," != *",${host},"* ]]; then
            echo "Alias collision: $host already has unmanaged or differently owned alias state." >&2
            exit 29
        fi
        if systemctl is-active --quiet "$ALIAS_SERVICE$host.service" 2>/dev/null && [[ ",${current_hosts}," != *",${host},"* ]]; then
            echo "Alias collision: active service already publishes $host outside this route." >&2
            exit 29
        fi
    done
}

check_collisions() {
    local current="$1" path hosts host other_route
    for path in "$ROUTE_ROOT"/*.route; do
        [[ -f "$path" ]] || continue
        other_route="$(metadata_value "$path" ROUTE_ID)"
        [[ "$other_route" == "$current" ]] && continue
        hosts="$(metadata_value "$path" HOSTNAMES)"
        IFS=',' read -r -a EXISTING_HOSTS <<< "$hosts"
        for host in "${HOST_ARRAY[@]}"; do
            local existing
            for existing in "${EXISTING_HOSTS[@]}"; do
                if [[ "$host" == "$existing" ]]; then
                    echo "Hostname collision: $host is already owned by route $other_route" >&2
                    exit 22
                fi
            done
        done
    done
}

assert_same_owner_if_existing() {
    local meta
    meta="$(metadata_path "$S_ROUTE")"
    [[ -f "$meta" ]] || return 0
    [[ "$(metadata_value "$meta" OWNER_REPO)" == "$S_OWNER" && \
       "$(metadata_value "$meta" ENVIRONMENT)" == "$S_ENV" && \
       "$(metadata_value "$meta" APP_SLUG)" == "$S_APP" ]] || {
        echo "Existing route ownership does not match requested owner/environment/app." >&2
        exit 23
    }
}

render_route() {
    local dest="$1" host first=true
    : > "$dest"
    for host in "${HOST_ARRAY[@]}"; do
        if [[ "$first" == true ]]; then
            printf 'http://%s' "$host" >> "$dest"
            first=false
        else
            printf ', http://%s' "$host" >> "$dest"
        fi
    done
    cat >> "$dest" <<EOF
 {
    reverse_proxy $S_UPSTREAM:$S_PORT
}
EOF
}

write_metadata() {
    local dest="$1"
    cat > "$dest" <<EOF
SCHEMA_VERSION=$S_SCHEMA
OWNER_REPO=$S_OWNER
ENVIRONMENT=$S_ENV
APP_SLUG=$S_APP
ROUTE_ID=$S_ROUTE
UPSTREAM_CONTAINER=$S_UPSTREAM
UPSTREAM_PORT=$S_PORT
HOSTNAMES=$S_HOSTS
EOF
}

validate_candidate_conf() {
    local candidate_conf="$1"
    docker run --rm \
      -v "$PROXY_ROOT/Caddyfile:/etc/caddy/Caddyfile:ro" \
      -v "$candidate_conf:/etc/caddy/conf.d:ro" \
      "$CADDY_IMAGE" caddy validate --config /etc/caddy/Caddyfile >/dev/null
}

copy_conf_for_candidate() {
    local candidate="$1" target_route="$2"
    install -d -m 0755 "$candidate"
    local path
    for path in "$PROXY_ROOT/conf.d"/*.caddy; do
        [[ -f "$path" ]] || continue
        [[ "$path" == "$target_route" ]] && continue
        cp -a "$path" "$candidate/$(basename "$path")"
    done
}

require_upstream_ready() {
    local state
    state="$(docker inspect --format '{{.State.Status}}' "$S_UPSTREAM" 2>/dev/null || true)"
    [[ "$state" == running ]] || { echo "Upstream container is not running: $S_UPSTREAM" >&2; exit 24; }
    if ! docker network inspect "$NETWORK_NAME" --format '{{range .Containers}}{{println .Name}}{{end}}' | grep -Fxq "$S_UPSTREAM"; then
        echo "Upstream container is not attached to $NETWORK_NAME; application deployment must attach it before route registration." >&2
        exit 27
    fi
}

register_route() {
    require_ready
    parse_spec
    install -d -m 0750 "$ROUTE_ROOT"
    install -d -m 0755 "$ALIAS_ROOT"
    assert_expected_previous
    assert_same_owner_if_existing
    check_alias_collisions
    check_collisions "$S_ROUTE"

    local route_file meta_file candidate_dir candidate_route temp_meta backup_dir old_hosts=""
    route_file="$(route_path "$S_ROUTE")"
    meta_file="$(metadata_path "$S_ROUTE")"
    candidate_dir="$(mktemp -d)"
    backup_dir="$(mktemp -d)"
    candidate_route="$candidate_dir/$(basename "$route_file")"
    copy_conf_for_candidate "$candidate_dir" "$route_file"
    render_route "$candidate_route"
    validate_candidate_conf "$candidate_dir"

    if [[ -f "$meta_file" ]]; then old_hosts="$(metadata_value "$meta_file" HOSTNAMES)"; fi
    [[ -f "$route_file" ]] && cp -a "$route_file" "$backup_dir/route.caddy"
    [[ -f "$meta_file" ]] && cp -a "$meta_file" "$backup_dir/route.meta"
    IFS=',' read -r -a OLD_HOST_ARRAY <<< "$old_hosts"
    local host
    for host in "${OLD_HOST_ARRAY[@]}" "${HOST_ARRAY[@]}"; do
        [[ -n "$host" ]] || continue
        local apath
        apath="$(alias_path "$host")"
        if [[ -f "$apath" && ! -f "$backup_dir/alias-$host.env" ]]; then cp -a "$apath" "$backup_dir/alias-$host.env"; fi
    done

    rollback() {
        echo "Route registration failed; restoring previous route/alias state." >&2
        if [[ -f "$backup_dir/route.caddy" ]]; then cp -f "$backup_dir/route.caddy" "$route_file"; else rm -f "$route_file"; fi
        if [[ -f "$backup_dir/route.meta" ]]; then cp -f "$backup_dir/route.meta" "$meta_file"; else rm -f "$meta_file"; fi
        local rollback_host
        for rollback_host in "${OLD_HOST_ARRAY[@]}" "${HOST_ARRAY[@]}"; do
            [[ -n "$rollback_host" ]] || continue
            if [[ -f "$backup_dir/alias-$rollback_host.env" ]]; then
                cp -f "$backup_dir/alias-$rollback_host.env" "$(alias_path "$rollback_host")"
                systemctl enable --now "$ALIAS_SERVICE$rollback_host.service" >/dev/null 2>&1 || true
                systemctl restart "$ALIAS_SERVICE$rollback_host.service" >/dev/null 2>&1 || true
            else
                systemctl disable --now "$ALIAS_SERVICE$rollback_host.service" >/dev/null 2>&1 || true
                rm -f "$(alias_path "$rollback_host")"
            fi
        done
        docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
    }

    require_upstream_ready
    local tmp_route="${route_file}.tmp.$$" tmp_meta="${meta_file}.tmp.$$"
    cp -f "$candidate_route" "$tmp_route" && chmod 0644 "$tmp_route" && mv -f "$tmp_route" "$route_file"
    write_metadata "$tmp_meta" && chmod 0644 "$tmp_meta" && mv -f "$tmp_meta" "$meta_file"

    local rc=0
    set +e
    for host in "${HOST_ARRAY[@]}"; do
        printf 'ALIAS_HOSTNAME=%s\n' "$host" > "$(alias_path "$host")"
        chmod 0644 "$(alias_path "$host")"
        systemctl enable --now "$ALIAS_SERVICE$host.service" >/dev/null
        rc=$?; [[ $rc -eq 0 ]] || break
        systemctl restart "$ALIAS_SERVICE$host.service" >/dev/null
        rc=$?; [[ $rc -eq 0 ]] || break
    done
    [[ $rc -eq 0 ]] && docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null
    rc=$(( rc == 0 ? $? : rc ))
    set -e
    if [[ $rc -ne 0 ]]; then
        rollback
        rm -rf "$candidate_dir" "$backup_dir"
        exit "$rc"
    fi

    for host in "${OLD_HOST_ARRAY[@]}"; do
        [[ -n "$host" ]] || continue
        if [[ ",${S_HOSTS}," != *",${host},"* ]]; then
            systemctl disable --now "$ALIAS_SERVICE$host.service" >/dev/null 2>&1 || true
            rm -f "$(alias_path "$host")"
        fi
    done
    rm -rf "$candidate_dir" "$backup_dir"
}

remove_route() {
    require_ready
    parse_spec
    local route_file meta_file existing_hosts host candidate_dir
    route_file="$(route_path "$S_ROUTE")"
    meta_file="$(metadata_path "$S_ROUTE")"
    [[ -f "$meta_file" ]] || { echo "Managed route is missing: $S_ROUTE" >&2; exit 25; }
    assert_same_owner_if_existing
    existing_hosts="$(metadata_value "$meta_file" HOSTNAMES)"
    [[ "$existing_hosts" == "$S_HOSTS" && "$(metadata_value "$meta_file" UPSTREAM_CONTAINER)" == "$S_UPSTREAM" && "$(metadata_value "$meta_file" UPSTREAM_PORT)" == "$S_PORT" ]] || {
        echo "Registered route changed since the authorized plan." >&2; exit 26;
    }

    candidate_dir="$(mktemp -d)"
    copy_conf_for_candidate "$candidate_dir" "$route_file"
    validate_candidate_conf "$candidate_dir"

    local backup_dir
    backup_dir="$(mktemp -d)"
    cp -a "$route_file" "$backup_dir/route.caddy"
    cp -a "$meta_file" "$backup_dir/route.meta"
    IFS=',' read -r -a OLD_HOST_ARRAY <<< "$existing_hosts"
    for host in "${OLD_HOST_ARRAY[@]}"; do
        [[ -f "$(alias_path "$host")" ]] && cp -a "$(alias_path "$host")" "$backup_dir/alias-$host.env"
    done

    rollback() {
        cp -f "$backup_dir/route.caddy" "$route_file"
        cp -f "$backup_dir/route.meta" "$meta_file"
        local rollback_host
        for rollback_host in "${OLD_HOST_ARRAY[@]}"; do
            [[ -f "$backup_dir/alias-$rollback_host.env" ]] || continue
            cp -f "$backup_dir/alias-$rollback_host.env" "$(alias_path "$rollback_host")"
            systemctl enable --now "$ALIAS_SERVICE$rollback_host.service" >/dev/null 2>&1 || true
            systemctl restart "$ALIAS_SERVICE$rollback_host.service" >/dev/null 2>&1 || true
        done
        docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
    }

    rm -f "$route_file" "$meta_file"
    local rc=0
    set +e
    docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null
    rc=$?
    if [[ $rc -eq 0 ]]; then
        for host in "${OLD_HOST_ARRAY[@]}"; do
            systemctl disable --now "$ALIAS_SERVICE$host.service" >/dev/null 2>&1 || true
            rm -f "$(alias_path "$host")"
        done
    fi
    set -e
    if [[ $rc -ne 0 ]]; then
        rollback
        rm -rf "$candidate_dir" "$backup_dir"
        exit "$rc"
    fi
    rm -rf "$candidate_dir" "$backup_dir"
}

case "$ACTION" in
    inventory)
        inventory
        ;;
    register|remove)
        exec 9>>"$LOCK_FILE"
        if ! flock -n 9; then echo "Another platform/route operation holds the lock." >&2; exit 75; fi
        if [[ "$ACTION" == register ]]; then register_route; else remove_route; fi
        inventory
        ;;
    *)
        echo "Unsupported route-registry action: $ACTION" >&2
        exit 2
        ;;
esac
'''
