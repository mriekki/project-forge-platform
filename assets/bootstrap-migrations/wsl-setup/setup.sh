#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_ENGINE="$ROOT/tools/dev-environment/setup.py"
WSL_SETUP_ENGINE="$ROOT/tools/dev-environment/setup-wsl.py"

if [[ "$(/usr/bin/uname -s)" == "Linux" ]]; then
  if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! /bin/grep -Eqi '(microsoft|wsl)' /proc/sys/kernel/osrelease 2>/dev/null; then
    echo "ERROR: this generated Linux setup path currently supports WSL2 only." >&2
    exit 2
  fi

  PYTHON_BIN="$(command -v python3 || true)"
  if [[ -z "$PYTHON_BIN" ]]; then
    if [[ " ${*:-} " == *" --check "* ]]; then
      echo "ERROR: python3 is required to run the read-only Project Forge WSL2 setup check." >&2
      exit 2
    fi
    echo "Project Forge: installing the Python setup runtime inside WSL."
    sudo apt-get update
    sudo apt-get install -y python3
    PYTHON_BIN="$(command -v python3 || true)"
    if [[ -z "$PYTHON_BIN" ]]; then
      echo "ERROR: python3 installation completed but python3 is still unavailable." >&2
      exit 2
    fi
  fi

  exec "$PYTHON_BIN" "$WSL_SETUP_ENGINE" "$@"
fi

# Project Forge treats Homebrew as the macOS package-management substrate for
# generated workstation setup. Keep the installer immutable and verify the
# exact Git blob before executing it; never execute Homebrew/install HEAD.
HOMEBREW_INSTALL_REVISION="85d1a3fc80d8a63932f632aca8f787de11d14a64"
HOMEBREW_INSTALL_BLOB_SHA="30615f54182a9d600455ad979783f3cebcdc58aa"
HOMEBREW_INSTALL_URL="https://raw.githubusercontent.com/Homebrew/install/${HOMEBREW_INSTALL_REVISION}/install.sh"

CHECK_ONLY=0
for argument in "$@"; do
  if [[ "$argument" == "--check" ]]; then
    CHECK_ONLY=1
    break
  fi
done

find_brew() {
  local candidate
  if command -v brew >/dev/null 2>&1; then
    command -v brew
    return 0
  fi
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

activate_brew() {
  local brew_bin="$1"
  local python_prefix=""
  eval "$("$brew_bin" shellenv)"

  # Homebrew intentionally keeps unversioned Python shims such as `python`
  # under the Python formula's libexec/bin. The generated catalog historically
  # probes `python`, so expose that formula-owned directory to this setup
  # process without modifying the developer's shell startup files.
  python_prefix="$("$brew_bin" --prefix python 2>/dev/null || true)"
  if [[ -n "$python_prefix" && -d "$python_prefix/libexec/bin" ]]; then
    export PATH="$python_prefix/libexec/bin:$PATH"
  fi
}

verify_homebrew_installer() {
  local installer="$1"
  local size actual
  size="$(/usr/bin/wc -c < "$installer" | /usr/bin/tr -d '[:space:]')"
  actual="$({ printf 'blob %s\0' "$size"; /bin/cat "$installer"; } | /usr/bin/shasum -a 1 | /usr/bin/awk '{print $1}')"
  if [[ "$actual" != "$HOMEBREW_INSTALL_BLOB_SHA" ]]; then
    echo "ERROR: Homebrew installer integrity mismatch." >&2
    echo "Expected Git blob $HOMEBREW_INSTALL_BLOB_SHA but got $actual." >&2
    return 2
  fi
}

install_homebrew() {
  local installer
  if [[ "$(/usr/bin/uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS setup launcher cannot bootstrap Homebrew on this platform." >&2
    return 2
  fi
  if [[ ! -x /usr/bin/curl ]]; then
    echo "ERROR: macOS setup requires /usr/bin/curl to bootstrap Homebrew." >&2
    return 2
  fi
  if [[ ! -x /usr/bin/shasum ]]; then
    echo "ERROR: macOS setup requires /usr/bin/shasum to verify the Homebrew installer." >&2
    return 2
  fi

  installer="$(/usr/bin/mktemp "${TMPDIR:-/tmp}/project-forge-homebrew.XXXXXX")"
  if ! /usr/bin/curl -fsSL "$HOMEBREW_INSTALL_URL" -o "$installer"; then
    /bin/rm -f "$installer"
    echo "ERROR: Unable to download the pinned Homebrew installer." >&2
    return 2
  fi
  if ! verify_homebrew_installer "$installer"; then
    /bin/rm -f "$installer"
    return 2
  fi

  echo "Project Forge: Homebrew is required for supported macOS tool installation."
  echo "Project Forge: running verified Homebrew installer ${HOMEBREW_INSTALL_REVISION}."
  if [[ -t 0 ]]; then
    if ! /bin/bash "$installer"; then
      /bin/rm -f "$installer"
      echo "ERROR: Homebrew bootstrap did not complete." >&2
      echo "If macOS requested administrator or Command Line Tools approval, complete that native prompt and rerun /setup." >&2
      return 2
    fi
  else
    if ! NONINTERACTIVE=1 /bin/bash "$installer"; then
      /bin/rm -f "$installer"
      echo "ERROR: Homebrew bootstrap needs macOS administrator or Command Line Tools interaction that is unavailable in this non-interactive terminal." >&2
      echo "Rerun /setup from an interactive terminal; Project Forge will continue the same setup flow without requiring manual install commands." >&2
      return 2
    fi
  fi
  /bin/rm -f "$installer"
}

preflight_interactive_casks() {
  local pending
  pending="$("$PYTHON_BIN" - "$ROOT" "$BREW_BIN" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
brew = sys.argv[2]
config = json.loads((root / "DEV_ENVIRONMENT.json").read_text(encoding="utf-8"))
catalog = root / "tools" / "dev-environment" / "catalog"
pending = []
for entry in config.get("tools", []):
    spec = json.loads((catalog / f"{entry['id']}.json").read_text(encoding="utf-8"))
    install = spec.get("install", {}).get("macos") or {}
    if install.get("interactive") is not True:
        continue
    package = install.get("package")
    if not package and install.get("packageTemplate"):
        version = entry.get("version")
        if not version:
            continue
        package = install["packageTemplate"].format(major=version.split(".")[0], version=version)
    if not package:
        continue
    result = subprocess.run(
        [brew, "list", "--cask", package],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        pending.append(f"{entry['id']} ({package})")
print(", ".join(pending))
PY
)"

  if [[ -z "$pending" ]]; then
    return 0
  fi

  echo "Project Forge: macOS interactive-install preflight: $pending"
  echo "Project Forge: these declared tools may require an administrator/native installer prompt during this setup run."
  if [[ ! -t 0 ]]; then
    echo "ERROR: required macOS tool installation needs an interactive terminal before Project Forge starts the install sequence." >&2
    echo "Rerun this same generated setup command from an interactive terminal; do not install the listed packages manually." >&2
    return 2
  fi
}

BREW_BIN="$(find_brew || true)"
if [[ -z "$BREW_BIN" && "$CHECK_ONLY" -eq 0 ]]; then
  install_homebrew
  BREW_BIN="$(find_brew || true)"
  if [[ -z "$BREW_BIN" ]]; then
    echo "ERROR: Homebrew installation completed but brew is still unavailable." >&2
    exit 2
  fi
fi

if [[ -n "$BREW_BIN" ]]; then
  activate_brew "$BREW_BIN"
fi

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "ERROR: python3 is required to run the read-only Project Forge setup check." >&2
    exit 2
  fi
  if [[ -z "$BREW_BIN" ]]; then
    echo "ERROR: Homebrew is unavailable, so Project Forge cannot install the Python setup runtime." >&2
    exit 2
  fi

  echo "Project Forge: installing the Python setup runtime through Homebrew."
  "$BREW_BIN" install python
  activate_brew "$BREW_BIN"
  PYTHON_BIN="$(command -v python3 || true)"
  if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: Homebrew installed Python but python3 is still unavailable." >&2
    exit 2
  fi
fi

if [[ "$CHECK_ONLY" -eq 0 && -n "$BREW_BIN" ]]; then
  preflight_interactive_casks
fi

exec "$PYTHON_BIN" "$SETUP_ENGINE" "$@"
