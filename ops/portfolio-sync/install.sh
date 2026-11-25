#!/usr/bin/env bash
# Install isolated Project Forge Portfolio sync service. No repo, npm, or FMP writes.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo: sudo bash install.sh [--interval 15m]' >&2; exit 1; }
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
interval='15m'
if (($#)); then
  [[ $# -eq 2 && "$1" == --interval ]] || { echo 'Usage: sudo bash install.sh [--interval 15m]' >&2; exit 1; }
  interval="$2"
fi
command -v systemctl >/dev/null || { echo 'systemctl not installed (Ubuntu systemd required).' >&2; exit 1; }
command -v gh >/dev/null || { echo 'GitHub CLI (gh) missing on Production. Install gh first; no service changes made.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'python3 missing on Production; no service changes made.' >&2; exit 1; }
[[ -d /run/systemd/system ]] || { echo 'Host is not running systemd; no service changes made.' >&2; exit 1; }
# Validate interval before creating system users/directories.
[[ "$interval" =~ ^([1-9][0-9]*)(s|m|h|d)$ ]] || { echo 'Interval must be 5m to 24h (e.g. 15m).' >&2; exit 1; }
n="${BASH_REMATCH[1]}"; unit="${BASH_REMATCH[2]}"; case "$unit" in s) secs="$n";;m) secs=$((n*60));;h) secs=$((n*3600));;d) secs=$((n*86400));;esac
((secs >= 300 && secs <= 86400)) || { echo 'Interval must be 5m to 24h.' >&2; exit 1; }
if ! id -u pf-portfolio-sync >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/project-forge-portfolio-sync --shell /usr/sbin/nologin pf-portfolio-sync
fi
home='/var/lib/project-forge-portfolio-sync'
[[ "$(getent passwd pf-portfolio-sync | cut -d: -f6)" == "$home" ]] || { echo 'Existing service account has unexpected HOME; refusing.' >&2; exit 1; }
install -d -o pf-portfolio-sync -g pf-portfolio-sync -m 0700 "$home" "$home/.config" "$home/.config/gh"
install -d -m 0755 /usr/local/libexec/project-forge-portfolio-sync /etc/project-forge-portfolio-sync
install -m 0755 "$BASE/sync.py" /usr/local/libexec/project-forge-portfolio-sync/sync.py
install -m 0755 "$BASE/set-interval.sh" /usr/local/libexec/project-forge-portfolio-sync/set-interval.sh
if [[ ! -f /etc/project-forge-portfolio-sync/config.json ]]; then
  install -m 0644 "$BASE/config.json" /etc/project-forge-portfolio-sync/config.json
fi
install -m 0644 "$BASE/systemd/project-forge-portfolio-sync.service" /etc/systemd/system/project-forge-portfolio-sync.service
install -m 0644 "$BASE/systemd/project-forge-portfolio-sync.timer" /etc/systemd/system/project-forge-portfolio-sync.timer
systemctl daemon-reload
bash /usr/local/libexec/project-forge-portfolio-sync/set-interval.sh "$interval"
cat <<'OUT'

Project Forge Portfolio sync service installed, NOT enabled yet.
Next: authorize GitHub on this host as the isolated service account:
  sudo bash /usr/local/libexec/project-forge-portfolio-sync/authorize-and-enable.sh

This authorizes a NEW GitHub CLI login through the browser/device flow.
It does not copy the WSL token or use FMP's Feedback App keys.
No FMP container/Production application was changed or restarted.
OUT
# Authorization helper is separately installed and does not enable the timer until verification succeeds.
install -m 0755 "$BASE/authorize-and-enable.sh" /usr/local/libexec/project-forge-portfolio-sync/authorize-and-enable.sh
