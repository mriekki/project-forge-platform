#!/usr/bin/env bash
# WSL2: obtain the exact reviewed Platform operations source, then deploy using
# the existing trusted Project Forge Production SSH profile.
set -Eeuo pipefail
REPO='https://github.com/mriekki/project-forge-platform.git'
BRANCH='ops/portfolio-sync-production-ssh-20261115'
PIN='119d2e0c5e07539da3a4ef1bf04dc2796e6ecf15'
ROOT="$HOME/.project-forge/portfolio-sync-operator"
DEST="$ROOT/$PIN"
command -v git >/dev/null && command -v python3 >/dev/null || {
  echo 'ERROR: git and python3 are required in WSL2.' >&2; exit 1;
}
mkdir -p -m 0700 "$ROOT"
if [[ ! -d "$DEST/.git" ]]; then
  [[ ! -e "$DEST" ]] || { echo 'ERROR: unexpected source destination exists.' >&2; exit 1; }
  TEMP="$(mktemp -d "$ROOT/.checkout.XXXXXXXX")"
  trap 'rm -rf -- "$TEMP"' EXIT
  git clone --quiet --depth 20 --filter=blob:none --sparse --branch "$BRANCH" "$REPO" "$TEMP/source"
  git -C "$TEMP/source" sparse-checkout set ops/portfolio-sync
  if ! git -C "$TEMP/source" cat-file -e "$PIN^{commit}" 2>/dev/null; then
    git -C "$TEMP/source" fetch --quiet --depth 1 origin "$PIN"
  fi
  git -C "$TEMP/source" checkout --quiet --detach "$PIN"
  [[ "$(git -C "$TEMP/source" rev-parse HEAD)" == "$PIN" ]] || {
    echo 'ERROR: reviewed source SHA not available; refusing.' >&2; exit 1;
  }
  mv -- "$TEMP/source" "$DEST"
fi
[[ "$(git -C "$DEST" remote get-url origin)" == "$REPO" ]] || {
  echo 'ERROR: unexpected Portfolio source origin; refusing.' >&2; exit 1;
}
[[ "$(git -C "$DEST" rev-parse HEAD)" == "$PIN" ]] || {
  echo 'ERROR: Portfolio source commit mismatch; refusing.' >&2; exit 1;
}
[[ -z "$(git -C "$DEST" status --porcelain --untracked-files=no)" ]] || {
  echo 'ERROR: source checkout has local edits; refusing.' >&2; exit 1;
}
exec python3 "$DEST/ops/portfolio-sync/deploy-from-wsl.py" "$@"
