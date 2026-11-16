"""Remote Ubuntu host-platform script template."""

REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

ACTION="$1"
PLATFORM_ROOT="__PLATFORM_ROOT__"
PROXY_ROOT="$PLATFORM_ROOT/proxy"
ROUTE_ROOT="$PLATFORM_ROOT/routes"
MARKER="$PLATFORM_ROOT/platform.env"
LOCK_FILE="/run/lock/project-forge-platform.lock"
NETWORK_NAME="__NETWORK_NAME__"
CADDY_CONTAINER="__CADDY_CONTAINER__"
CADDY_IMAGE="__CADDY_IMAGE__"
SCHEMA_VERSION="__SCHEMA_VERSION__"
PLATFORM_VERSION="__PLATFORM_VERSION__"
DISTRIBUTION="__DISTRIBUTION__"
COMPOSE_B64="__COMPOSE_B64__"
CADDYFILE_B64="__CADDYFILE_B64__"
PUBLISH_ALIAS_B64="__PUBLISH_ALIAS_B64__"
AVAHI_SERVICE_B64="__AVAHI_SERVICE_B64__"

marker_value() {
    local key="$1"
    [[ -f "$MARKER" ]] || return 1
    sed -n "s/^${key}=//p" "$MARKER" | head -n1
}
port80_in_use() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltn '( sport = :80 )' 2>/dev/null | tail -n +2 | grep -q .
    else
        return 1
    fi
}
prereqs_ready() {
    command -v docker >/dev/null 2>&1 &&
    docker compose version >/dev/null 2>&1 &&
    command -v systemctl >/dev/null 2>&1 &&
    command -v avahi-publish >/dev/null 2>&1 &&
    command -v flock >/dev/null 2>&1 &&
    command -v base64 >/dev/null 2>&1 &&
    command -v install >/dev/null 2>&1 &&
    command -v mktemp >/dev/null 2>&1 &&
    command -v ss >/dev/null 2>&1
}

status() {
    local marker_present=false prereqs=false network=false caddy_running=false avahi=false port80=false
    [[ -f "$MARKER" ]] && marker_present=true
    prereqs_ready && prereqs=true || true
    docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 && network=true || true
    [[ "$(docker inspect --format '{{.State.Status}}' "$CADDY_CONTAINER" 2>/dev/null || true)" == "running" ]] && caddy_running=true || true
    systemctl is-active --quiet avahi-daemon 2>/dev/null && avahi=true || true
    port80_in_use && port80=true || true

    local state marker_schema marker_distribution marker_version
    marker_schema="$(marker_value SCHEMA_VERSION 2>/dev/null || true)"
    marker_distribution="$(marker_value DISTRIBUTION 2>/dev/null || true)"
    marker_version="$(marker_value PLATFORM_VERSION 2>/dev/null || true)"

    if [[ "$marker_present" == false ]]; then
        if [[ "$prereqs" != true ]]; then
            state="blocked"
        elif [[ "$port80" == true ]]; then
            state="blocked-port-80"
        else
            state="installable"
        fi
    elif [[ "$marker_schema" != "$SCHEMA_VERSION" || "$marker_distribution" != "$DISTRIBUTION" ]]; then
        state="incompatible"
    elif [[ "$prereqs" != true ]]; then
        state="blocked"
    elif [[ "$marker_version" != "$PLATFORM_VERSION" ]]; then
        state="upgrade-required"
    elif [[ "$network" == true && "$caddy_running" == true && "$avahi" == true && -f "$PROXY_ROOT/compose.yaml" && -f "$PROXY_ROOT/Caddyfile" && -d "$ROUTE_ROOT" && -f /usr/local/lib/project-forge-platform/publish-alias.sh && -f /etc/systemd/system/project-forge-avahi-alias@.service ]]; then
        state="ready"
    else
        state="drifted"
    fi

    printf 'state=%s\n' "$state"
    printf 'markerPresent=%s\n' "$marker_present"
    printf 'markerSchemaVersion=%s\n' "$marker_schema"
    printf 'markerDistribution=%s\n' "$marker_distribution"
    printf 'markerPlatformVersion=%s\n' "$marker_version"
    printf 'expectedPlatformVersion=%s\n' "$PLATFORM_VERSION"
    printf 'prerequisitesReady=%s\n' "$prereqs"
    printf 'networkPresent=%s\n' "$network"
    printf 'caddyRunning=%s\n' "$caddy_running"
    printf 'avahiRunning=%s\n' "$avahi"
    printf 'port80InUse=%s\n' "$port80"
    printf 'platformRoot=%s\n' "$PLATFORM_ROOT"
    printf 'networkName=%s\n' "$NETWORK_NAME"
    printf 'caddyContainer=%s\n' "$CADDY_CONTAINER"
}

require_write_prereqs() {
    if ! prereqs_ready; then
        echo "Required host prerequisites are missing. Docker Engine + Compose, systemd, avahi-utils, iproute2/ss, flock, base64, install, and mktemp must be prepared separately." >&2
        exit 3
    fi
}

write_marker() {
    local tmp="$MARKER.tmp.$$"
    cat > "$tmp" <<EOF
SCHEMA_VERSION=$SCHEMA_VERSION
DISTRIBUTION=$DISTRIBUTION
PLATFORM_VERSION=$PLATFORM_VERSION
NETWORK_NAME=$NETWORK_NAME
CADDY_CONTAINER=$CADDY_CONTAINER
CADDY_IMAGE=$CADDY_IMAGE
EOF
    chmod 0644 "$tmp"
    mv -f "$tmp" "$MARKER"
}

decode_to() {
    local payload="$1" dest="$2" mode="$3"
    local tmp="${dest}.tmp.$$"
    printf '%s' "$payload" | base64 --decode > "$tmp"
    chmod "$mode" "$tmp"
    mv -f "$tmp" "$dest"
}

validate_candidate() {
    local candidate_compose="$1" candidate_caddy="$2"
    docker compose -f "$candidate_compose" config >/dev/null
    docker run --rm \
        -v "$candidate_caddy:/etc/caddy/Caddyfile:ro" \
        -v "$PROXY_ROOT/conf.d:/etc/caddy/conf.d:ro" \
        "$CADDY_IMAGE" caddy validate --config /etc/caddy/Caddyfile >/dev/null
}

install_platform() {
    require_write_prereqs
    if [[ -f "$MARKER" ]]; then
        echo "Platform marker already exists; use explicit upgrade instead of install." >&2
        exit 4
    fi
    if port80_in_use; then
        echo "Port 80 is already occupied; prepare a clean host before platform install." >&2
        exit 6
    fi

    install -d -m 0750 "$PLATFORM_ROOT" "$PROXY_ROOT" "$ROUTE_ROOT"
    install -d -m 0755 "$PROXY_ROOT/conf.d" "$PROXY_ROOT/data" "$PROXY_ROOT/config"
    install -d -m 0750 "$ROUTE_ROOT"
    install -d -m 0755 /usr/local/lib/project-forge-platform /etc/project-forge-platform/aliases
    if [[ ! -e "$PROXY_ROOT/conf.d/00-platform-empty.caddy" ]]; then
        printf '# Platform-owned placeholder; application routes are registered separately.\n' > "$PROXY_ROOT/conf.d/00-platform-empty.caddy"
        chmod 0644 "$PROXY_ROOT/conf.d/00-platform-empty.caddy"
    fi

    if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
        docker network create "$NETWORK_NAME" >/dev/null
    fi

    local candidate_dir candidate_compose candidate_caddy
    candidate_dir="$(mktemp -d)"
    trap 'rm -rf "$candidate_dir"' RETURN
    candidate_compose="$candidate_dir/compose.yaml"
    candidate_caddy="$candidate_dir/Caddyfile"
    printf '%s' "$COMPOSE_B64" | base64 --decode > "$candidate_compose"
    printf '%s' "$CADDYFILE_B64" | base64 --decode > "$candidate_caddy"
    validate_candidate "$candidate_compose" "$candidate_caddy"

    decode_to "$COMPOSE_B64" "$PROXY_ROOT/compose.yaml" 0644
    decode_to "$CADDYFILE_B64" "$PROXY_ROOT/Caddyfile" 0644
    decode_to "$PUBLISH_ALIAS_B64" /usr/local/lib/project-forge-platform/publish-alias.sh 0755
    decode_to "$AVAHI_SERVICE_B64" /etc/systemd/system/project-forge-avahi-alias@.service 0644

    systemctl daemon-reload
    systemctl enable --now avahi-daemon >/dev/null
    docker compose -f "$PROXY_ROOT/compose.yaml" up -d
    docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile >/dev/null
    write_marker
}

upgrade_platform() {
    require_write_prereqs
    if [[ ! -f "$MARKER" ]]; then
        echo "Platform marker is absent; use install on a fresh host." >&2
        exit 7
    fi
    local marker_schema marker_distribution marker_version
    marker_schema="$(marker_value SCHEMA_VERSION || true)"
    marker_distribution="$(marker_value DISTRIBUTION || true)"
    marker_version="$(marker_value PLATFORM_VERSION || true)"
    if [[ "$marker_schema" != "$SCHEMA_VERSION" || "$marker_distribution" != "$DISTRIBUTION" ]]; then
        echo "Existing platform marker is incompatible; refusing in-place upgrade." >&2
        exit 8
    fi
    if [[ "$marker_version" == "$PLATFORM_VERSION" ]]; then
        echo "Platform is already at version $PLATFORM_VERSION; no upgrade applied."
        return 0
    fi

    install -d -m 0755 "$PROXY_ROOT/conf.d" "$PROXY_ROOT/data" "$PROXY_ROOT/config"
    install -d -m 0750 "$ROUTE_ROOT"
    if [[ ! -e "$PROXY_ROOT/conf.d/00-platform-empty.caddy" ]]; then
        printf '# Platform-owned placeholder; application routes are registered separately.\n' > "$PROXY_ROOT/conf.d/00-platform-empty.caddy"
        chmod 0644 "$PROXY_ROOT/conf.d/00-platform-empty.caddy"
    fi
    if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
        docker network create "$NETWORK_NAME" >/dev/null
    fi
    local candidate_dir candidate_compose candidate_caddy backup_dir
    candidate_dir="$(mktemp -d)"
    backup_dir="$(mktemp -d)"
    candidate_compose="$candidate_dir/compose.yaml"
    candidate_caddy="$candidate_dir/Caddyfile"
    printf '%s' "$COMPOSE_B64" | base64 --decode > "$candidate_compose"
    printf '%s' "$CADDYFILE_B64" | base64 --decode > "$candidate_caddy"
    validate_candidate "$candidate_compose" "$candidate_caddy"

    for path in "$PROXY_ROOT/compose.yaml" "$PROXY_ROOT/Caddyfile" /usr/local/lib/project-forge-platform/publish-alias.sh /etc/systemd/system/project-forge-avahi-alias@.service "$MARKER"; do
        if [[ -f "$path" ]]; then cp -a "$path" "$backup_dir/$(basename "$path")"; fi
    done

    rollback() {
        echo "Upgrade failed; restoring previous platform-managed files." >&2
        [[ -f "$backup_dir/compose.yaml" ]] && cp -f "$backup_dir/compose.yaml" "$PROXY_ROOT/compose.yaml"
        [[ -f "$backup_dir/Caddyfile" ]] && cp -f "$backup_dir/Caddyfile" "$PROXY_ROOT/Caddyfile"
        [[ -f "$backup_dir/publish-alias.sh" ]] && cp -f "$backup_dir/publish-alias.sh" /usr/local/lib/project-forge-platform/publish-alias.sh
        [[ -f "$backup_dir/project-forge-avahi-alias@.service" ]] && cp -f "$backup_dir/project-forge-avahi-alias@.service" /etc/systemd/system/project-forge-avahi-alias@.service
        [[ -f "$backup_dir/platform.env" ]] && cp -f "$backup_dir/platform.env" "$MARKER"
        systemctl daemon-reload || true
        docker compose -f "$PROXY_ROOT/compose.yaml" up -d || true
        docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile || true
    }

    set +e
    decode_to "$COMPOSE_B64" "$PROXY_ROOT/compose.yaml" 0644
    rc=$?
    [[ $rc -eq 0 ]] && decode_to "$CADDYFILE_B64" "$PROXY_ROOT/Caddyfile" 0644; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && decode_to "$PUBLISH_ALIAS_B64" /usr/local/lib/project-forge-platform/publish-alias.sh 0755; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && decode_to "$AVAHI_SERVICE_B64" /etc/systemd/system/project-forge-avahi-alias@.service 0644; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && systemctl daemon-reload; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && systemctl enable --now avahi-daemon >/dev/null; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && docker compose -f "$PROXY_ROOT/compose.yaml" up -d; rc=$(( rc == 0 ? $? : rc ))
    [[ $rc -eq 0 ]] && docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile; rc=$(( rc == 0 ? $? : rc ))
    if [[ $rc -eq 0 ]]; then write_marker; rc=$?; fi
    set -e
    if [[ $rc -ne 0 ]]; then
        rollback
        rm -rf "$candidate_dir" "$backup_dir"
        exit "$rc"
    fi
    rm -rf "$candidate_dir" "$backup_dir"
}

# PF-06: read the exact managed Caddy container/network identity.
# Only selected fields are returned; no Config.Env, mounts or provider secrets.
# This cannot make an application accept a changed proxy peer.
proxy_peer_status() {
    local id name state image network_id networks members
    id="$(docker inspect --format '{{.Id}}' "$CADDY_CONTAINER" 2>/dev/null)" || {
        echo "Managed proxy container is missing or unavailable." >&2; exit 31;
    }
    name="$(docker inspect --format '{{.Name}}' "$CADDY_CONTAINER" 2>/dev/null)" || exit 31
    name="${name#/}"
    state="$(docker inspect --format '{{.State.Status}}' "$CADDY_CONTAINER" 2>/dev/null)" || exit 31
    image="$(docker inspect --format '{{.Config.Image}}' "$CADDY_CONTAINER" 2>/dev/null)" || exit 31
    network_id="$(docker network inspect --format '{{.Id}}' "$NETWORK_NAME" 2>/dev/null)" || {
        echo "Managed proxy network is missing or unavailable." >&2; exit 32;
    }
    networks="$(docker inspect --format '{{json .NetworkSettings.Networks}}' "$CADDY_CONTAINER" 2>/dev/null)" || exit 33
    members="$(docker network inspect --format '{{json .Containers}}' "$NETWORK_NAME" 2>/dev/null)" || exit 33
    printf 'containerId=%s\ncontainerName=%s\ncontainerState=%s\ncontainerImage=%s\nnetworkId=%s\nnetworks=%s\nmembers=%s\n' \
        "$id" "$name" "$state" "$image" "$network_id" "$networks" "$members"
}

case "$ACTION" in
    proxy-peer)
        proxy_peer_status
        ;;
    status)
        status
        ;;
    install|upgrade)
        exec 9>>"$LOCK_FILE"
        if ! flock -n 9; then
            echo "Another host-platform operation holds the lock." >&2
            exit 75
        fi
        if [[ "$ACTION" == install ]]; then install_platform; else upgrade_platform; fi
        status
        ;;
    *)
        echo "Unsupported platform action: $ACTION" >&2
        exit 2
        ;;
esac
'''
