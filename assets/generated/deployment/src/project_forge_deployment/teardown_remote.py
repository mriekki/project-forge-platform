"""Remote destructive tear-down for one Kit-managed Project environment."""

REMOTE_SCRIPT = r'''#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="/srv/project-forge-apps"
OWNER="$1"
APP="$2"
ENVIRONMENT="$3"

valid_slug() { [[ "$1" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; }
valid_repo() { [[ "$1" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; }
valid_image() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/:+-]*@sha256:[0-9a-f]{64}$ ]]; }
meta_value() {
    local path="$1" key="$2"
    [[ -f "$path" && ! -L "$path" ]] || return 1
    sed -n "s/^${key}=//p" "$path" | head -n1
}
assert_owned_marker() {
    local path="$1"
    [[ -f "$path" && ! -L "$path" ]] || return 1
    [[ "$(meta_value "$path" OWNER_REPO || true)" == "$OWNER" && \
       "$(meta_value "$path" APP_SLUG || true)" == "$APP" && \
       "$(meta_value "$path" ENVIRONMENT || true)" == "$ENVIRONMENT" ]]
}
append_unique_image() {
    local value="$1" existing
    for existing in "${IMAGES[@]:-}"; do
        [[ "$existing" == "$value" ]] && return 0
    done
    IMAGES+=("$value")
}

valid_repo "$OWNER" || { echo "Invalid owner repository." >&2; exit 20; }
valid_slug "$APP" || { echo "Invalid application slug." >&2; exit 20; }
valid_slug "$ENVIRONMENT" || { echo "Invalid environment slug." >&2; exit 20; }

ROOT="$APP_ROOT/$APP/$ENVIRONMENT"
STATE="$ROOT/deployment.env"
PERSISTENCE="$ROOT/persistence.env"

if [[ ! -e "$ROOT" ]]; then
    printf 'TEAR_DOWN\tabsent\t%s\t%s\n' "$APP" "$ENVIRONMENT"
    exit 0
fi

[[ -d "$ROOT" && ! -L "$ROOT" ]] || {
    echo "Project environment root is not a safe managed directory: $ROOT" >&2
    exit 21
}

HAS_STATE=false
HAS_PERSISTENCE=false
[[ -f "$STATE" && ! -L "$STATE" ]] && HAS_STATE=true
[[ -f "$PERSISTENCE" && ! -L "$PERSISTENCE" ]] && HAS_PERSISTENCE=true
[[ "$HAS_STATE" == true || "$HAS_PERSISTENCE" == true ]] || {
    echo "Project environment root has no managed ownership marker: $ROOT" >&2
    exit 21
}

if [[ "$HAS_STATE" == true ]] && ! assert_owned_marker "$STATE"; then
    echo "Project deployment ownership mismatch for $ROOT" >&2
    exit 22
fi
if [[ "$HAS_PERSISTENCE" == true ]] && ! assert_owned_marker "$PERSISTENCE"; then
    echo "Project persistence ownership mismatch for $ROOT" >&2
    exit 22
fi

CONTAINER=""
IMAGES=()
if [[ -d "$ROOT/releases" && ! -L "$ROOT/releases" ]]; then
    while IFS= read -r release_file; do
        [[ -f "$release_file" && ! -L "$release_file" ]] || continue
        assert_owned_marker "$release_file" || {
            echo "Managed release ownership does not match selected environment: $release_file" >&2
            exit 23
        }
        image="$(meta_value "$release_file" IMAGE || true)"
        valid_image "$image" || {
            echo "Managed release contains an invalid immutable image reference: $release_file" >&2
            exit 23
        }
        append_unique_image "$image"
    done < <(find "$ROOT/releases" -mindepth 2 -maxdepth 2 -type f -name release.env -print 2>/dev/null || true)
fi

if [[ "$HAS_STATE" == true ]]; then
    CURRENT_RELEASE="$(meta_value "$STATE" CURRENT_RELEASE || true)"
    [[ -n "$CURRENT_RELEASE" && "$CURRENT_RELEASE" != */* && "$CURRENT_RELEASE" != *..* ]] || {
        echo "Managed deployment state has an invalid current release." >&2
        exit 23
    }

    RELEASE_FILE="$ROOT/releases/$CURRENT_RELEASE/release.env"
    [[ -f "$RELEASE_FILE" && ! -L "$RELEASE_FILE" ]] || {
        echo "Managed current release metadata is missing: $RELEASE_FILE" >&2
        exit 23
    }
    assert_owned_marker "$RELEASE_FILE" || {
        echo "Managed release ownership does not match deployment state." >&2
        exit 23
    }
    CONTAINER="$(meta_value "$RELEASE_FILE" CONTAINER_NAME || true)"
    [[ "$CONTAINER" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]] || {
        echo "Managed release contains an invalid container name." >&2
        exit 23
    }

    if docker inspect "$CONTAINER" >/dev/null 2>&1; then
        docker rm -f "$CONTAINER" >/dev/null
    fi
fi

# The verified environment root is owned by this Project/environment. Tear-down
# removes releases, evidence, persistent data, and backups together.
rm -rf --one-file-system -- "$ROOT"

APP_DIR="$APP_ROOT/$APP"
if [[ -d "$APP_DIR" ]] && ! find "$APP_DIR" -mindepth 1 -print -quit | grep -q .; then
    rmdir "$APP_DIR"
fi

RETAINED_IMAGE=false
for IMAGE in "${IMAGES[@]:-}"; do
    [[ -n "$IMAGE" ]] || continue
    IMAGE_REFERENCED_ELSEWHERE=false
    while IFS= read -r candidate; do
        [[ -f "$candidate" && ! -L "$candidate" ]] || continue
        if [[ "$(meta_value "$candidate" IMAGE || true)" == "$IMAGE" ]]; then
            IMAGE_REFERENCED_ELSEWHERE=true
            break
        fi
    done < <(find "$APP_ROOT" -mindepth 5 -maxdepth 5 -type f -name release.env -print 2>/dev/null || true)

    if [[ "$IMAGE_REFERENCED_ELSEWHERE" == true ]] || \
       docker ps -a --filter "ancestor=$IMAGE" --format '{{.ID}}' | grep -q .; then
        RETAINED_IMAGE=true
        continue
    fi
    if docker image inspect "$IMAGE" >/dev/null 2>&1; then
        if ! docker image rm "$IMAGE" >/dev/null 2>&1; then
            RETAINED_IMAGE=true
        fi
    fi
done

IMAGES_CSV=""
if [[ ${#IMAGES[@]} -gt 0 ]]; then
    IMAGES_CSV="$(IFS=,; echo "${IMAGES[*]}")"
fi
ALL_IMAGES_REMOVED=true
[[ "$RETAINED_IMAGE" == true ]] && ALL_IMAGES_REMOVED=false

printf 'TEAR_DOWN\tremoved\t%s\t%s\t%s\t%s\t%s\n' \
    "$APP" "$ENVIRONMENT" "$CONTAINER" "$IMAGES_CSV" "$ALL_IMAGES_REMOVED"
'''
