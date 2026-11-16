"""Remote Ubuntu script template for shared Cloudflare Tunnel ingress."""

REMOTE_SCRIPT = r"""#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ACTION="$1"
SCOPE="$2"
META="${3:-}"
SPEC="${4:-}"
EXPECTED="${5:-}"
AUTHENTICATED_ORIGIN="${6:-false}"

PLATFORM_ROOT="__PLATFORM_ROOT__"
NETWORK_NAME="__NETWORK_NAME__"
CADDY_CONTAINER="__CADDY_CONTAINER__"
CLOUDFLARED_IMAGE="__CLOUDFLARED_IMAGE__@sha256:c6c7ae1d5dfdcb094ad344ed68ccffc26635c9c6be80965664c33baf064b0515"
SCHEMA_VERSION="__SCHEMA_VERSION__"
INGRESS_VERSION="__INGRESS_VERSION__"
DISTRIBUTION="__DISTRIBUTION__"
TOKEN_B64="__TOKEN_B64__"

valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_hostname() {
    local host="$1" label
    [[ -n "$host" && ${#host} -le 253 ]] || return 1
    [[ "$host" != *:* && "$host" != *" "* && "$host" != */* && "$host" != *,* ]] || return 1
    IFS='.' read -r -a labels <<< "$host"
    (( ${#labels[@]} >= 2 )) || return 1
    for label in "${labels[@]}"; do
        [[ "$label" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || return 1
    done
}

valid_slug "$SCOPE" || { echo "Invalid Cloudflare ingress scope." >&2; exit 20; }

ROOT="$PLATFORM_ROOT/ingress/cloudflare/$SCOPE"
MARKER="$ROOT/ingress.env"
TOKEN_FILE="$ROOT/tunnel-token"
COMPOSE_FILE="$ROOT/compose.yaml"
ROUTE_ROOT="$ROOT/routes"
AUTH_ROOT="$PLATFORM_ROOT/proxy/data/authenticated/$SCOPE"
AUTH_ROUTES="$AUTH_ROOT/routes"
AUTH_CADDY="$PLATFORM_ROOT/proxy/conf.d/90-project-forge-auth-$SCOPE.caddy"
AUTH_SOCKET="$AUTH_ROOT/origin.sock"
MIGRATION_MARKER_BACKUP="$ROOT/.authenticated-origin-migration.marker"
MIGRATION_COMPOSE_BACKUP="$ROOT/.authenticated-origin-migration.compose"
MIGRATION_RECEIPT="$ROOT/.authenticated-origin-migration.receipt"
CONTAINER="project-forge-cloudflared-$SCOPE"
LOCK_FILE="/run/lock/project-forge-cloudflare-$SCOPE.lock"

marker_value() {
    local key="$1"
    [[ -f "$MARKER" ]] || return 1
    sed -n "s/^${key}=//p" "$MARKER" | head -n1
}

# Legacy markers can predate AUTHENTICATED_ORIGIN; an empty explicit value
# or any other invalid mode must not be treated as an absent key.
legacy_origin_mode() {
    local mode
    [[ -f "$MARKER" && ! -L "$MARKER" ]] || return 1
    mode="$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)"
    [[ "$mode" == false ]] && return 0
    [[ -z "$mode" ]] && ! grep -q '^AUTHENTICATED_ORIGIN=' "$MARKER"
}

# The pinned root-run Caddy listener creates the Unix socket (0:0:0222).
# cloudflared owns the containing 0700 directory, not the socket.
auth_socket_metadata_valid() {
    [[ -S "$AUTH_SOCKET" && ! -L "$AUTH_SOCKET" &&
       "$(stat -c '%u:%g:%a' "$AUTH_SOCKET")" == "0:0:222" ]]
}

platform_ready() {
    [[ "$(docker inspect --format '{{.State.Status}}' "$CADDY_CONTAINER" 2>/dev/null || true)" == "running" ]] &&
    docker network inspect "$NETWORK_NAME" >/dev/null 2>&1
}

container_running() {
    [[ "$(docker inspect --format '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true)" == "running" ]]
}

container_image() {
    docker inspect --format '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true
}

network_attached() {
    docker network inspect "$NETWORK_NAME" --format '{{range .Containers}}{{println .Name}}{{end}}' 2>/dev/null |
        grep -Fxq "$CONTAINER"
}

status() {
    local marker=false token=false running=false attached=false platform=false
    [[ -f "$MARKER" ]] && marker=true
    [[ -f "$TOKEN_FILE" ]] && token=true
    container_running && running=true || true
    network_attached && attached=true || true
    platform_ready && platform=true || true

    local state marker_schema marker_version marker_distribution marker_image runtime_image mode
    mode="$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)"
    [[ "$mode" == true ]] || mode=false
    marker_schema="$(marker_value SCHEMA_VERSION 2>/dev/null || true)"
    marker_version="$(marker_value INGRESS_VERSION 2>/dev/null || true)"
    marker_distribution="$(marker_value DISTRIBUTION 2>/dev/null || true)"
    marker_image="$(marker_value CLOUDFLARED_IMAGE 2>/dev/null || true)"
    runtime_image="$(container_image)"

    if [[ "$platform" != true ]]; then
        state="blocked-platform"
    elif [[ "$marker" == false ]]; then
        state="installable"
    elif [[ "$marker_schema" != "$SCHEMA_VERSION" || "$marker_distribution" != "$DISTRIBUTION" ]]; then
        state="incompatible"
    elif [[ "$marker_version" != "$INGRESS_VERSION" || "$marker_image" != "$CLOUDFLARED_IMAGE" ]]; then
        state="upgrade-required"
    elif [[ "$running" == true && "$runtime_image" != "$CLOUDFLARED_IMAGE" ]]; then
        state="drifted"
    elif [[ "$mode" == true && ( ! -S "$AUTH_SOCKET" || ! -f "$AUTH_CADDY" ) ]]; then
        state="drifted"
    elif [[ "$token" == true && "$running" == true && "$attached" == true && -f "$COMPOSE_FILE" && -d "$ROUTE_ROOT" ]]; then
        state="ready"
    else
        state="drifted"
    fi

    printf 'state=%s\n' "$state"
    printf 'scope=%s\n' "$SCOPE"
    printf 'markerPresent=%s\n' "$marker"
    printf 'markerSchemaVersion=%s\n' "$marker_schema"
    printf 'markerIngressVersion=%s\n' "$marker_version"
    printf 'markerDistribution=%s\n' "$marker_distribution"
    printf 'platformReady=%s\n' "$platform"
    printf 'tokenPresent=%s\n' "$token"
    printf 'containerRunning=%s\n' "$running"
    printf 'networkAttached=%s\n' "$attached"
    printf 'containerName=%s\n' "$CONTAINER"
    printf 'cloudflaredImage=%s\n' "$CLOUDFLARED_IMAGE"
    printf 'accountId=%s\n' "$(marker_value ACCOUNT_ID 2>/dev/null || true)"
    printf 'zoneId=%s\n' "$(marker_value ZONE_ID 2>/dev/null || true)"
    printf 'zoneName=%s\n' "$(marker_value ZONE_NAME 2>/dev/null || true)"
    printf 'tunnelId=%s\n' "$(marker_value TUNNEL_ID 2>/dev/null || true)"
    printf 'tunnelName=%s\n' "$(marker_value TUNNEL_NAME 2>/dev/null || true)"
    printf 'authenticatedOrigin=%s\n' "$mode"
}

parse_meta() {
    IFS=$'\t' read -r M_ACCOUNT M_ZONE_ID M_ZONE_NAME M_TUNNEL_ID M_TUNNEL_NAME extra <<< "$META"
    [[ -z "${extra:-}" && -n "$M_ACCOUNT" && -n "$M_ZONE_ID" && -n "$M_ZONE_NAME" && -n "$M_TUNNEL_ID" && -n "$M_TUNNEL_NAME" ]] || {
        echo "Malformed Cloudflare ingress metadata." >&2
        exit 20
    }
    valid_hostname "$M_ZONE_NAME" || { echo "Invalid Cloudflare zone name." >&2; exit 20; }
}

write_marker() {
    local tmp="$MARKER.tmp.$$"
    cat > "$tmp" <<EOF
SCHEMA_VERSION=$SCHEMA_VERSION
INGRESS_VERSION=$INGRESS_VERSION
DISTRIBUTION=$DISTRIBUTION
ACCOUNT_ID=$M_ACCOUNT
ZONE_ID=$M_ZONE_ID
ZONE_NAME=$M_ZONE_NAME
TUNNEL_ID=$M_TUNNEL_ID
TUNNEL_NAME=$M_TUNNEL_NAME
CLOUDFLARED_IMAGE=$CLOUDFLARED_IMAGE
AUTHENTICATED_ORIGIN=$AUTHENTICATED_ORIGIN
EOF
    chmod 0600 "$tmp"
    mv -f "$tmp" "$MARKER"
}

write_compose() {
    local tmp="$COMPOSE_FILE.tmp.$$"
    cat > "$tmp" <<EOF
services:
  cloudflared:
    image: $CLOUDFLARED_IMAGE
    container_name: $CONTAINER
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token-file /run/secrets/tunnel-token
    volumes:
      - $TOKEN_FILE:/run/secrets/tunnel-token:ro
EOF
    if [[ "$AUTHENTICATED_ORIGIN" == true ]]; then
        printf '      - %s:/run/project-forge-origin:ro\n' "$AUTH_ROOT" >> "$tmp"
    fi
    cat >> "$tmp" <<EOF
    networks:
      - $NETWORK_NAME
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

networks:
  $NETWORK_NAME:
    external: true
EOF
    chmod 0600 "$tmp"
    docker compose -f "$tmp" config >/dev/null
    mv -f "$tmp" "$COMPOSE_FILE"
}


setup_authenticated_origin() {
    [[ "$AUTHENTICATED_ORIGIN" == true ]] || return 0
    [[ ! -L "$AUTH_ROOT" && ! -L "$AUTH_CADDY" ]] || {
        echo "Authenticated origin path is a symbolic link." >&2; exit 27;
    }
    install -d -m 0700 "$AUTH_ROOT" "$AUTH_ROUTES"
    chown 65532:65532 "$AUTH_ROOT"
    chmod 0700 "$AUTH_ROOT"
    local tmp="$AUTH_CADDY.tmp.$BASHPID"
    cat > "$tmp" <<EOF
http://:19078 {
    bind unix//data/authenticated/$SCOPE/origin.sock|0222
    import /data/authenticated/$SCOPE/routes/*.caddy
    respond "Not Found" 404
}
EOF
    chmod 0644 "$tmp"
    mv -f "$tmp" "$AUTH_CADDY"
    MIGRATION_CADDY_HASH="$(sha256sum "$AUTH_CADDY" | cut -d' ' -f1)"
    docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null
    [[ -S "$AUTH_SOCKET" ]] || {
        echo "Authenticated private origin socket did not appear." >&2; exit 27;
    }
}

# Public-only Caddy handler: the LAN listener never receives this virtual host.
# All routing metadata comes from the existing, owned LAN route on this host.
auth_route_path() { printf '%s/%s.caddy' "$AUTH_ROUTES" "$1"; }
auth_route_verify_lan() {
    local lan="$PLATFORM_ROOT/routes/$R_ROUTE.route" hosts
    [[ -f "$lan" && ! -L "$lan" ]] || { echo "Owned LAN route missing." >&2; exit 35; }
    [[ "$(route_value "$lan" OWNER_REPO)" == "$R_OWNER" &&
       "$(route_value "$lan" ENVIRONMENT)" == "$R_ENV" &&
       "$(route_value "$lan" APP_SLUG)" == "$R_APP" &&
       "$(route_value "$lan" ROUTE_ID)" == "$R_ROUTE" ]] || {
        echo "LAN route ownership changed." >&2; exit 35;
    }
    hosts="$(route_value "$lan" HOSTNAMES)"
    [[ ",$hosts," == *",$R_ORIGIN,"* ]] || {
        echo "LAN origin hostname is no longer owned." >&2; exit 35;
    }
    AUTH_UPSTREAM="$(route_value "$lan" UPSTREAM_CONTAINER)"
    AUTH_PORT="$(route_value "$lan" UPSTREAM_PORT)"
    [[ "$AUTH_UPSTREAM" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ &&
       "$AUTH_PORT" =~ ^[0-9]+$ ]] || {
        echo "LAN upstream is malformed." >&2; exit 35;
    }
    (( 10#$AUTH_PORT >= 1 && 10#$AUTH_PORT <= 65535 )) || {
        echo "LAN port out of range." >&2; exit 35;
    }
}
auth_route_write() {
    [[ "$(marker_value AUTHENTICATED_ORIGIN)" == true ]] || return 0
    auth_route_verify_lan
    local file tmp backup
    file="$(auth_route_path "$R_ROUTE")"
    [[ ! -L "$file" ]] || { echo "Unsafe authenticated route symlink." >&2; exit 35; }
    tmp="$file.tmp.$BASHPID"
    backup="$file.backup.$BASHPID"
    [[ ! -f "$file" ]] || cp -a "$file" "$backup"
    auth_route_content > "$tmp"
    chmod 0644 "$tmp"
    mv -f "$tmp" "$file"
    if ! docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null; then
        if [[ -f "$backup" ]]; then mv -f "$backup" "$file"; else rm -f "$file"; fi
        docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
        echo "Authenticated Caddy route failed validation; restored previous state." >&2
        exit 35
    fi
    rm -f "$backup"
}
auth_route_content() {
    cat <<EOF
@pf_$R_ROUTE host $R_PUBLIC
handle @pf_$R_ROUTE {
    request_header -X-Forwarded-*
    request_header -X-Real-IP
    reverse_proxy $AUTH_UPSTREAM:$AUTH_PORT {
        header_up Host $R_PUBLIC
        header_up -Forwarded
        header_up -True-Client-IP
        header_up -CF-Visitor
        header_up -CF-Connecting-IP
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host $R_PUBLIC
        header_up X-Forwarded-For {http.request.header.Cf-Connecting-Ip}
        header_up X-Real-IP {http.request.header.Cf-Connecting-Ip}
    }
}
EOF
}
auth_route_remove() {
    [[ "$(marker_value AUTHENTICATED_ORIGIN)" == true ]] || return 0
    local file backup
    file="$(auth_route_path "$R_ROUTE")"
    [[ -f "$file" && ! -L "$file" ]] || {
        echo "Expected authenticated Caddy route is missing." >&2; exit 35;
    }
    backup="$file.backup.$BASHPID"
    mv -f "$file" "$backup"
    if ! docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null; then
        mv -f "$backup" "$file"
        docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
        echo "Authenticated Caddy removal failed; restored previous route." >&2
        exit 35
    fi
    rm -f "$backup"
}

write_token() {
    [[ -n "$TOKEN_B64" ]] || { echo "Tunnel token was not supplied." >&2; exit 20; }
    local tmp="$TOKEN_FILE.tmp.$$"
    printf '%s' "$TOKEN_B64" | base64 --decode > "$tmp"
    [[ -s "$tmp" ]] || { rm -f "$tmp"; echo "Tunnel token decoded empty." >&2; exit 20; }
    chmod 0444 "$tmp"
    mv -f "$tmp" "$TOKEN_FILE"
}

install_or_upgrade() {
    platform_ready || { echo "Shared Project Forge Caddy/network platform is not ready." >&2; exit 21; }
    parse_meta
    if [[ "$ACTION" == install && -f "$MARKER" ]]; then
        echo "Cloudflare ingress marker already exists; use upgrade." >&2
        exit 22
    fi
    if [[ "$ACTION" == upgrade && ! -f "$MARKER" ]]; then
        echo "Cloudflare ingress marker is absent; use install." >&2
        exit 22
    fi
    install -d -m 0700 "$ROOT" "$ROUTE_ROOT"
    if [[ "$AUTHENTICATED_ORIGIN" == true ]]; then
        setup_authenticated_origin
    fi
    write_token
    write_compose
    write_marker
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate
    container_running || { echo "cloudflared container did not become running." >&2; exit 23; }
    [[ "$(container_image)" == "$CLOUDFLARED_IMAGE" ]] || { echo "cloudflared container is not running the expected pinned image." >&2; exit 23; }
    network_attached || { echo "cloudflared container is not attached to the shared Caddy network." >&2; exit 23; }
}

parse_spec_value() {
    IFS=$'\t' read -r R_SCHEMA R_OWNER R_ENV R_APP R_ROUTE R_PUBLIC R_ORIGIN extra <<< "$1"
    [[ -z "${extra:-}" ]] || { echo "Malformed public-ingress route spec." >&2; exit 30; }
    [[ "$R_SCHEMA" == "$SCHEMA_VERSION" ]] || { echo "Unsupported public-ingress route schema." >&2; exit 30; }
    valid_repo "$R_OWNER" || { echo "Invalid route owner repo." >&2; exit 30; }
    valid_slug "$R_ENV" || { echo "Invalid route environment." >&2; exit 30; }
    valid_slug "$R_APP" || { echo "Invalid route app slug." >&2; exit 30; }
    [[ "$R_ROUTE" == "$R_APP--$R_ENV" ]] || { echo "Public-ingress route ID mismatch." >&2; exit 30; }
    valid_hostname "$R_PUBLIC" || { echo "Invalid public hostname." >&2; exit 30; }
    [[ "$R_PUBLIC" != *.local ]] || { echo "Public hostname must not use .local." >&2; exit 30; }
    valid_hostname "$R_ORIGIN" || { echo "Invalid origin hostname." >&2; exit 30; }
    [[ "$R_ORIGIN" == *.local ]] || { echo "Origin hostname must be a trusted-LAN .local route." >&2; exit 30; }
}

route_path() { printf '%s/%s.route' "$ROUTE_ROOT" "$1"; }
route_value() {
    local path="$1" key="$2"
    sed -n "s/^${key}=//p" "$path" | head -n1
}
emit_route() {
    local path="$1"
    printf 'ROUTE\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$(route_value "$path" SCHEMA_VERSION)" \
        "$(route_value "$path" OWNER_REPO)" \
        "$(route_value "$path" ENVIRONMENT)" \
        "$(route_value "$path" APP_SLUG)" \
        "$(route_value "$path" ROUTE_ID)" \
        "$(route_value "$path" PUBLIC_HOSTNAME)" \
        "$(route_value "$path" ORIGIN_HOSTNAME)"
}
route_inventory() {
    [[ -f "$MARKER" ]] || { echo "Cloudflare ingress is not installed." >&2; exit 31; }
    local count=0 path
    for path in "$ROUTE_ROOT"/*.route; do [[ -f "$path" ]] && count=$((count + 1)); done
    printf 'SUMMARY\tscope\t%s\n' "$SCOPE"
    printf 'SUMMARY\tmanagedRouteCount\t%s\n' "$count"
    for path in "$ROUTE_ROOT"/*.route; do [[ -f "$path" ]] && emit_route "$path"; done
    return 0
}

route_inventory_digest() {
    route_inventory | sha256sum | cut -d' ' -f1
}

auth_files_digest() {
    if [[ ! -d "$AUTH_ROOT" ]]; then
        printf ''
        return
    fi
    (
        cd "$AUTH_ROOT"
        find . -type f -print0 | sort -z | xargs -0r sha256sum
    ) | sha256sum | cut -d' ' -f1
}

receipt_value() {
    local key="$1"
    [[ -f "$MIGRATION_RECEIPT" && ! -L "$MIGRATION_RECEIPT" ]] || return 1
    sed -n "s/^${key}=//p" "$MIGRATION_RECEIPT" | head -n1
}

migration_pending_valid() {
    [[ -f "$MIGRATION_MARKER_BACKUP" && ! -L "$MIGRATION_MARKER_BACKUP" &&
       -f "$MIGRATION_COMPOSE_BACKUP" && ! -L "$MIGRATION_COMPOSE_BACKUP" &&
       -f "$MIGRATION_RECEIPT" && ! -L "$MIGRATION_RECEIPT" &&
       -f "$MARKER" && ! -L "$MARKER" &&
       -f "$COMPOSE_FILE" && ! -L "$COMPOSE_FILE" &&
       -f "$AUTH_CADDY" && ! -L "$AUTH_CADDY" &&
       -d "$AUTH_ROOT" && ! -L "$AUTH_ROOT" &&
       -d "$AUTH_ROUTES" && ! -L "$AUTH_ROUTES" ]] || return 1
    [[ "$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)" == true ]] || return 1
    [[ "$(route_inventory_digest)" == "$(receipt_value ROUTE_SNAPSHOT_SHA256)" ]] || return 1
    [[ "$(sha256sum "$MARKER" | cut -d' ' -f1)" == "$(receipt_value MARKER_SHA256)" ]] || return 1
    [[ "$(sha256sum "$COMPOSE_FILE" | cut -d' ' -f1)" == "$(receipt_value COMPOSE_SHA256)" ]] || return 1
    [[ "$(sha256sum "$AUTH_CADDY" | cut -d' ' -f1)" == "$(receipt_value CADDY_SHA256)" ]] || return 1
    [[ "$(auth_files_digest)" == "$(receipt_value AUTH_FILES_SHA256)" ]] || return 1
    return 0
}

migration_inspect() {
    local mode state
    mode="$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)"
    if [[ "$mode" == true ]]; then
        if migration_pending_valid; then
            state=pending
        elif [[ ! -e "$MIGRATION_MARKER_BACKUP" && ! -e "$MIGRATION_COMPOSE_BACKUP" &&
                ! -e "$MIGRATION_RECEIPT" ]]; then
            state=complete
        else
            echo "Authenticated-origin migration recovery evidence is incomplete or changed." >&2
            exit 37
        fi
    elif legacy_origin_mode && [[ ! -e "$MIGRATION_MARKER_BACKUP" &&
            ! -e "$MIGRATION_COMPOSE_BACKUP" && ! -e "$MIGRATION_RECEIPT" &&
            ! -e "$AUTH_ROOT" && ! -e "$AUTH_CADDY" ]]; then
        state=clean
    else
        echo "Authenticated-origin migration paths conflict with unowned or incomplete state." >&2
        exit 37
    fi
    printf 'migrationState=%s\n' "$state"
}

migration_rollback_on_error() {
    local original_status="$1" rollback_failed=false path
    trap - ERR EXIT
    set +e
    if [[ -f "$MIGRATION_MARKER_BACKUP" && ! -L "$MIGRATION_MARKER_BACKUP" ]]; then
        cp -p "$MIGRATION_MARKER_BACKUP" "$MARKER.rollback.$$" &&
            mv -f "$MARKER.rollback.$$" "$MARKER" || rollback_failed=true
    fi
    if [[ -f "$MIGRATION_COMPOSE_BACKUP" && ! -L "$MIGRATION_COMPOSE_BACKUP" ]]; then
        cp -p "$MIGRATION_COMPOSE_BACKUP" "$COMPOSE_FILE.rollback.$$" &&
            mv -f "$COMPOSE_FILE.rollback.$$" "$COMPOSE_FILE" || rollback_failed=true
        docker compose -f "$COMPOSE_FILE" up -d --force-recreate >/dev/null 2>&1 || rollback_failed=true
    fi
    if [[ -e "$AUTH_CADDY" ]]; then
        if [[ -f "$AUTH_CADDY" && ! -L "$AUTH_CADDY" &&
              "$(sha256sum "$AUTH_CADDY" | cut -d' ' -f1)" == "${MIGRATION_CADDY_HASH:-}" ]]; then
            rm -f "$AUTH_CADDY"
            docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 ||
                rollback_failed=true
        else
            rollback_failed=true
        fi
    fi
    local index
    for index in "${!MIGRATION_CREATED_ROUTES[@]}"; do
        path="${MIGRATION_CREATED_ROUTES[$index]}"
        if [[ "$path" == "$AUTH_ROUTES/"*.caddy && -f "$path" && ! -L "$path" &&
              "$(sha256sum "$path" | cut -d' ' -f1)" == "${MIGRATION_CREATED_ROUTE_HASHES[$index]}" ]]; then
            rm -f "$path"
        else
            rollback_failed=true
        fi
    done
    if [[ -e "$AUTH_SOCKET" ]]; then
        if auth_socket_metadata_valid; then
            rm -f "$AUTH_SOCKET"
        else
            rollback_failed=true
        fi
    fi
    if [[ -d "$AUTH_ROUTES" ]] && ! rmdir "$AUTH_ROUTES" 2>/dev/null; then rollback_failed=true; fi
    if [[ -d "$AUTH_ROOT" ]] && ! rmdir "$AUTH_ROOT" 2>/dev/null; then rollback_failed=true; fi
    if [[ "$rollback_failed" == false ]]; then
        rm -f "$MIGRATION_MARKER_BACKUP" "$MIGRATION_COMPOSE_BACKUP" "$MIGRATION_RECEIPT"
        echo "Authenticated-origin host preparation failed and was rolled back." >&2
    else
        echo "Authenticated-origin host preparation failed; rollback is incomplete and recovery evidence was retained." >&2
    fi
    exit "$original_status"
}

migrate_authenticated_origin() {
    local expected_route_digest="$EXPECTED" state path route_spec
    [[ "$AUTHENTICATED_ORIGIN" == true ]] || { echo "Authenticated-origin migration must opt in explicitly." >&2; exit 37; }
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready ]] &&
        legacy_origin_mode || {
        echo "Authenticated-origin migration requires a ready legacy scope." >&2; exit 37;
    }
    [[ "$(route_inventory_digest)" == "$expected_route_digest" ]] || {
        echo "Managed public-route inventory changed after planning." >&2; exit 37;
    }
    state="$(migration_inspect | sed -n 's/^migrationState=//p')"
    [[ "$state" == clean ]] || { echo "Authenticated-origin migration is not in a clean host state." >&2; exit 37; }
    parse_meta
    [[ "$(marker_value ACCOUNT_ID)" == "$M_ACCOUNT" &&
       "$(marker_value ZONE_ID)" == "$M_ZONE_ID" &&
       "$(marker_value ZONE_NAME)" == "$M_ZONE_NAME" &&
       "$(marker_value TUNNEL_ID)" == "$M_TUNNEL_ID" &&
       "$(marker_value TUNNEL_NAME)" == "$M_TUNNEL_NAME" ]] || {
        echo "Existing host tunnel binding changed after planning." >&2; exit 37;
    }
    [[ -f "$MARKER" && ! -L "$MARKER" && -f "$COMPOSE_FILE" && ! -L "$COMPOSE_FILE" &&
       -f "$TOKEN_FILE" && ! -L "$TOKEN_FILE" && -d "$ROUTE_ROOT" && ! -L "$ROUTE_ROOT" ]] || {
        echo "Existing ingress host files are incomplete or unsafe." >&2; exit 37;
    }
    local route_count=0
    MIGRATION_CREATED_ROUTES=()
    MIGRATION_CREATED_ROUTE_HASHES=()
    trap 'migration_rollback_on_error "$?"' EXIT
    cp -p "$MARKER" "$MIGRATION_MARKER_BACKUP"
    cp -p "$COMPOSE_FILE" "$MIGRATION_COMPOSE_BACKUP"
    chmod 0600 "$MIGRATION_MARKER_BACKUP" "$MIGRATION_COMPOSE_BACKUP"
    setup_authenticated_origin
    AUTHENTICATED_ORIGIN=true
    write_marker
    write_compose
    for path in "$ROUTE_ROOT"/*.route; do
        [[ -f "$path" ]] || continue
        route_spec="$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s' \
            "$(route_value "$path" SCHEMA_VERSION)" "$(route_value "$path" OWNER_REPO)" \
            "$(route_value "$path" ENVIRONMENT)" "$(route_value "$path" APP_SLUG)" \
            "$(route_value "$path" ROUTE_ID)" "$(route_value "$path" PUBLIC_HOSTNAME)" \
            "$(route_value "$path" ORIGIN_HOSTNAME)")"
        parse_spec_value "$route_spec"
        [[ "$(basename "$path")" == "$R_ROUTE.route" ]] || {
            echo "Managed public-route identity is malformed." >&2; exit 37;
        }
        SPEC="$route_spec"
        auth_route_write
        MIGRATION_CREATED_ROUTES+=("$(auth_route_path "$R_ROUTE")")
        MIGRATION_CREATED_ROUTE_HASHES+=("$(sha256sum "$(auth_route_path "$R_ROUTE")" | cut -d' ' -f1)")
        route_count=$((route_count + 1))
    done
    (( route_count > 0 )) || { echo "No managed public routes are available to migrate." >&2; exit 37; }
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate >/dev/null
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready &&
       "$(marker_value AUTHENTICATED_ORIGIN)" == true ]] || {
        echo "Authenticated-origin connector did not become ready." >&2; exit 37;
    }
    cat > "$MIGRATION_RECEIPT.tmp.$$" <<EOF
ROUTE_SNAPSHOT_SHA256=$expected_route_digest
MARKER_SHA256=$(sha256sum "$MARKER" | cut -d' ' -f1)
COMPOSE_SHA256=$(sha256sum "$COMPOSE_FILE" | cut -d' ' -f1)
CADDY_SHA256=$(sha256sum "$AUTH_CADDY" | cut -d' ' -f1)
AUTH_FILES_SHA256=$(auth_files_digest)
EOF
    chmod 0600 "$MIGRATION_RECEIPT.tmp.$$"
    mv -f "$MIGRATION_RECEIPT.tmp.$$" "$MIGRATION_RECEIPT"
    migration_pending_valid || { echo "Authenticated-origin recovery receipt validation failed." >&2; exit 37; }
    trap - ERR EXIT
    printf 'migrationState=pending\n'
}

rollback_authenticated_origin() {
    migration_pending_valid || { echo "Authenticated-origin migration rollback evidence is stale or unsafe." >&2; exit 38; }
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready ]] || {
        echo "Authenticated-origin host is not ready for rollback." >&2; exit 38;
    }
    cp -p "$MIGRATION_MARKER_BACKUP" "$MARKER.rollback.$$"
    mv -f "$MARKER.rollback.$$" "$MARKER"
    cp -p "$MIGRATION_COMPOSE_BACKUP" "$COMPOSE_FILE.rollback.$$"
    mv -f "$COMPOSE_FILE.rollback.$$" "$COMPOSE_FILE"
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate >/dev/null
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready ]] &&
        legacy_origin_mode || {
        echo "Legacy connector did not become ready after authenticated-origin rollback." >&2; exit 38;
    }
    [[ -f "$AUTH_CADDY" && ! -L "$AUTH_CADDY" ]] || {
        echo "Authenticated Caddy configuration changed before rollback." >&2; exit 38;
    }
    rm -f "$AUTH_CADDY"
    docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile >/dev/null
    for path in "$AUTH_ROUTES"/*.caddy; do [[ -f "$path" ]] && rm -f "$path"; done
    if [[ -e "$AUTH_SOCKET" ]]; then
        auth_socket_metadata_valid || {
            echo "Authenticated origin socket changed before rollback." >&2; exit 38;
        }
        rm -f "$AUTH_SOCKET"
    fi
    rmdir "$AUTH_ROUTES" "$AUTH_ROOT"
    rm -f "$MIGRATION_MARKER_BACKUP" "$MIGRATION_COMPOSE_BACKUP" "$MIGRATION_RECEIPT"
    printf 'migrationState=rolled-back\n'
}

finalize_authenticated_origin() {
    migration_pending_valid || { echo "Authenticated-origin migration receipt is stale or unsafe." >&2; exit 39; }
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready ]] || {
        echo "Authenticated-origin host is not ready for finalization." >&2; exit 39;
    }
    rm -f "$MIGRATION_MARKER_BACKUP" "$MIGRATION_COMPOSE_BACKUP" "$MIGRATION_RECEIPT"
    printf 'migrationState=complete\n'
}

verify_authenticated_origin() {
    local expected_route_digest="$EXPECTED" path route_spec
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready &&
       "$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)" == true &&
       -d "$AUTH_ROOT" && ! -L "$AUTH_ROOT" &&
       "$(stat -c '%u:%g:%a' "$AUTH_ROOT")" == "65532:65532:700" ]] &&
        auth_socket_metadata_valid || {
        echo "Authenticated-origin socket or scope is not ready." >&2; exit 40;
    }
    [[ "$(route_inventory_digest)" == "$expected_route_digest" ]] || {
        echo "Managed public-route inventory changed during migration." >&2; exit 40;
    }
    grep -Fqx "      - $AUTH_ROOT:/run/project-forge-origin:ro" "$COMPOSE_FILE" || {
        echo "Connector Compose file does not grant the exact read-only origin mount." >&2; exit 40;
    }
    path_overlap() {
        local left="${1%/}" right="${2%/}"
        [[ -n "$left" && -n "$right" ]] || return 1
        [[ "$left" == "$right" || "$left" == "$right/"* || "$right" == "$left/"* ]]
    }
    local connector_id caddy_id mount_count other_id mounts source destination writable source_mount
    connector_id="$(docker inspect --format '{{.Id}}' "$CONTAINER")"
    caddy_id="$(docker inspect --format '{{.Id}}' "$CADDY_CONTAINER")"
    mapfile -t mounts < <(docker inspect --format '{{range .Mounts}}{{printf "%s|%s|%t\n" .Source .Destination .RW}}{{end}}' "$CONTAINER")
    mount_count=0
    for source_mount in "${mounts[@]}"; do
        [[ -n "$source_mount" ]] || continue
        IFS='|' read -r source destination writable <<< "$source_mount"
        if path_overlap "$source" "$AUTH_ROOT" || path_overlap "$destination" "/run/project-forge-origin"; then
            [[ "$source" == "$AUTH_ROOT" && "$destination" == "/run/project-forge-origin" &&
               "$writable" == false ]] || {
                echo "Connector has an unexpected mount overlapping the authenticated-origin socket." >&2; exit 40;
            }
            mount_count=$((mount_count + 1))
        fi
    done
    [[ "$mount_count" == 1 ]] || {
        echo "Running connector does not have exactly the expected read-only origin mount." >&2; exit 40;
    }
    while IFS= read -r other_id; do
        [[ -n "$other_id" && "$other_id" != "$connector_id" && "$other_id" != "$caddy_id" ]] || continue
        mapfile -t mounts < <(docker inspect --format '{{range .Mounts}}{{printf "%s|%s\n" .Source .Destination}}{{end}}' "$other_id")
        for source_mount in "${mounts[@]}"; do
            [[ -n "$source_mount" ]] || continue
            IFS='|' read -r source destination <<< "$source_mount"
            if path_overlap "$source" "$AUTH_ROOT" ||
               path_overlap "$destination" "/run/project-forge-origin"; then
                echo "Authenticated-origin mount is present on a non-connector container." >&2
                exit 40
            fi
        done
    done < <(docker ps -aq --no-trunc)
    [[ -f "$AUTH_CADDY" && ! -L "$AUTH_CADDY" ]] &&
        grep -Fqx "    bind unix//data/authenticated/$SCOPE/origin.sock|0222" "$AUTH_CADDY" &&
        grep -Fqx "    import /data/authenticated/$SCOPE/routes/*.caddy" "$AUTH_CADDY" || {
        echo "Authenticated Caddy Unix listener configuration is missing or changed." >&2; exit 40;
    }
    docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile >/dev/null
    local route_count=0
    for path in "$ROUTE_ROOT"/*.route; do
        [[ -f "$path" ]] || continue
        route_spec="$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s' \
            "$(route_value "$path" SCHEMA_VERSION)" "$(route_value "$path" OWNER_REPO)" \
            "$(route_value "$path" ENVIRONMENT)" "$(route_value "$path" APP_SLUG)" \
            "$(route_value "$path" ROUTE_ID)" "$(route_value "$path" PUBLIC_HOSTNAME)" \
            "$(route_value "$path" ORIGIN_HOSTNAME)")"
        parse_spec_value "$route_spec"
        auth_route_verify_lan
        local expected_file tmp
        expected_file="$(auth_route_path "$R_ROUTE")"
        [[ -f "$expected_file" && ! -L "$expected_file" ]] || {
            echo "Authenticated Caddy route file is missing or unsafe." >&2; exit 40;
        }
        tmp="$AUTH_ROUTES/.verify-$R_ROUTE.$$"
        auth_route_content > "$tmp"
        if ! cmp -s "$tmp" "$expected_file"; then
            rm -f "$tmp"
            echo "Authenticated Caddy route differs from the sanitized reviewed contract." >&2
            exit 40
        fi
        rm -f "$tmp"
        route_count=$((route_count + 1))
    done
    printf 'evidenceLevel=structural-only\n'
    printf 'connectorOriginMount=read-only\n'
    printf 'socketMetadataVerified=true\n'
    printf 'caddyConfigValidated=true\n'
    printf 'sanitizedRouteConfigVerified=true\n'
    printf 'managedRouteCount=%s\n' "$route_count"
}

metadata_matches() {
    local path="$1" encoded="$2"
    parse_spec_value "$encoded"
    [[ "$(route_value "$path" SCHEMA_VERSION)" == "$R_SCHEMA" &&
       "$(route_value "$path" OWNER_REPO)" == "$R_OWNER" &&
       "$(route_value "$path" ENVIRONMENT)" == "$R_ENV" &&
       "$(route_value "$path" APP_SLUG)" == "$R_APP" &&
       "$(route_value "$path" ROUTE_ID)" == "$R_ROUTE" &&
       "$(route_value "$path" PUBLIC_HOSTNAME)" == "$R_PUBLIC" &&
       "$(route_value "$path" ORIGIN_HOSTNAME)" == "$R_ORIGIN" ]]
}

route_register() {
    [[ "$(status | sed -n 's/^state=//p' | head -n1)" == ready ]] || {
        echo "Cloudflare ingress runtime is not ready." >&2; exit 31;
    }
    parse_spec_value "$SPEC"
    local path other public
    path="$(route_path "$R_ROUTE")"
    if [[ "$EXPECTED" == NONE ]]; then
        [[ ! -e "$path" ]] || { echo "Public-ingress route appeared after planning." >&2; exit 32; }
    else
        [[ -f "$path" && ! -L "$path" ]] || { echo "Expected public-ingress route is missing or unsafe." >&2; exit 32; }
        metadata_matches "$path" "$EXPECTED" || { echo "Public-ingress route changed after planning." >&2; exit 32; }
        parse_spec_value "$SPEC"
    fi
    for other in "$ROUTE_ROOT"/*.route; do
        [[ -f "$other" ]] || continue
        [[ "$other" == "$path" ]] && continue
        public="$(route_value "$other" PUBLIC_HOSTNAME)"
        [[ "$public" != "$R_PUBLIC" ]] || { echo "Public hostname is already owned by another managed route." >&2; exit 33; }
    done
    if [[ -f "$path" ]]; then
        [[ "$(route_value "$path" OWNER_REPO)" == "$R_OWNER" &&
           "$(route_value "$path" ENVIRONMENT)" == "$R_ENV" &&
           "$(route_value "$path" APP_SLUG)" == "$R_APP" ]] || {
            echo "Existing public-ingress route ownership mismatch." >&2; exit 33;
        }
    fi
    local tmp="$path.tmp.$$"
    cat > "$tmp" <<EOF
SCHEMA_VERSION=$R_SCHEMA
OWNER_REPO=$R_OWNER
ENVIRONMENT=$R_ENV
APP_SLUG=$R_APP
ROUTE_ID=$R_ROUTE
PUBLIC_HOSTNAME=$R_PUBLIC
ORIGIN_HOSTNAME=$R_ORIGIN
EOF
    chmod 0600 "$tmp"
    if [[ "$(marker_value AUTHENTICATED_ORIGIN 2>/dev/null || true)" == true ]]; then
        auth_route_write
    fi
    mv -f "$tmp" "$path"
}

route_remove() {
    parse_spec_value "$SPEC"
    local path
    path="$(route_path "$R_ROUTE")"
    [[ -f "$path" && ! -L "$path" ]] || { echo "Managed public-ingress route does not exist." >&2; exit 34; }
    metadata_matches "$path" "$SPEC" || { echo "Public-ingress route ownership/state mismatch." >&2; exit 34; }
    auth_route_remove
    rm -f "$path"
}

case "$ACTION" in
    status)
        status
        ;;
    route-lock)
        exec 9>>"$LOCK_FILE"
        flock -n 9 || { echo "Another Cloudflare ingress operation holds the lock." >&2; exit 75; }
        printf 'LOCKED\n'
        cat >/dev/null
        ;;
    install|upgrade)
        exec 9>>"$LOCK_FILE"
        flock -n 9 || { echo "Another Cloudflare ingress operation holds the lock." >&2; exit 75; }
        install_or_upgrade
        status
        ;;
    route-inventory)
        route_inventory
        ;;
    migration-inspect)
        migration_inspect
        ;;
    migrate-authenticated)
        migrate_authenticated_origin
        ;;
    rollback-authenticated)
        rollback_authenticated_origin
        ;;
    finalize-authenticated)
        finalize_authenticated_origin
        ;;
    verify-authenticated)
        verify_authenticated_origin
        ;;
    route-register|route-remove)
        exec 9>>"$LOCK_FILE"
        flock -n 9 || { echo "Another Cloudflare ingress operation holds the lock." >&2; exit 75; }
        if [[ "$ACTION" == route-register ]]; then route_register; else route_remove; fi
        route_inventory
        ;;
    route-register-locked|route-remove-locked)
        if [[ "$ACTION" == route-register-locked ]]; then route_register; else route_remove; fi
        route_inventory
        ;;
    *)
        echo "Unsupported Cloudflare ingress action: $ACTION" >&2
        exit 2
        ;;
esac
"""
