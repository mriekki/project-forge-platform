#!/usr/bin/env bash
# Configures monotonic systemd timer without altering any application units.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
interval="${1:-}"
[[ "$interval" =~ ^([1-9][0-9]*)(s|m|h|d)$ ]] || { echo 'Usage: sudo set-interval.sh 15m (5m minimum, 24h maximum)' >&2; exit 1; }
number="${BASH_REMATCH[1]}"; unit="${BASH_REMATCH[2]}"
case "$unit" in s) seconds=$number ;; m) seconds=$((number*60)) ;; h) seconds=$((number*3600)) ;; d) seconds=$((number*86400)) ;; esac
((seconds >= 300 && seconds <= 86400)) || { echo 'Interval must be between 5m and 24h.' >&2; exit 1; }
confdir='/etc/systemd/system/project-forge-portfolio-sync.timer.d'
install -d -m 0755 "$confdir"
cat >"$confdir/interval.conf" <<EOF
[Timer]
OnUnitInactiveSec=
OnUnitInactiveSec=$interval
EOF
chmod 0644 "$confdir/interval.conf"
systemctl daemon-reload
systemctl try-restart project-forge-portfolio-sync.timer
printf 'Configured Project Forge Portfolio interval: %s\n' "$interval"
systemctl list-timers --all project-forge-portfolio-sync.timer --no-pager || true
