#!/usr/bin/env bash
# Rollback only this timer/service, never FMP, other units, Project, or Issue records.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
systemctl disable --now project-forge-portfolio-sync.timer || true
systemctl stop project-forge-portfolio-sync.service || true
rm -f /etc/systemd/system/project-forge-portfolio-sync.timer /etc/systemd/system/project-forge-portfolio-sync.service
rm -rf /etc/systemd/system/project-forge-portfolio-sync.timer.d
systemctl daemon-reload
echo 'Units removed; GitHub Project and Issues unchanged.'
echo 'Dedicated user and gh authorization intentionally retained for inspection/revocation.'
echo 'Revoke the dedicated GitHub CLI authorization in GitHub account settings if permanently decommissioning.'
