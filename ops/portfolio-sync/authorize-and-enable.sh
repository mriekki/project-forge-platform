#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
home='/var/lib/project-forge-portfolio-sync'
[[ -f /usr/local/libexec/project-forge-portfolio-sync/sync.py ]] || { echo 'Run install.sh first.' >&2; exit 1; }
command -v runuser >/dev/null || { echo 'runuser missing' >&2; exit 1; }
svc() {
  runuser -u pf-portfolio-sync -- env -u GH_TOKEN -u GITHUB_TOKEN \
    HOME="$home" GH_CONFIG_DIR="$home/.config/gh" GH_PROMPT_DISABLED=0 "$@"
}
if ! svc gh auth status -h github.com >/dev/null 2>&1; then
  echo 'Authorize this isolated Production sync account with GitHub. Keep the device code private.'
  svc gh auth login -h github.com --web -s repo,project,read:project
fi
echo 'Checking GitHub identity, project visibility, and seven repository links...'
svc /usr/bin/python3 /usr/local/libexec/project-forge-portfolio-sync/sync.py --check
printf '\nPreflight sync (no write):\n'
svc /usr/bin/python3 /usr/local/libexec/project-forge-portfolio-sync/sync.py --dry-run
systemctl enable --now project-forge-portfolio-sync.timer
systemctl start project-forge-portfolio-sync.service
systemctl is-active --quiet project-forge-portfolio-sync.timer
systemctl is-failed --quiet project-forge-portfolio-sync.service && {
  echo 'Service failed; inspect: sudo journalctl -u project-forge-portfolio-sync.service -n 50 --no-pager' >&2
  exit 1
}
echo 'PASS: Project Forge Portfolio sync enabled on Production.'
systemctl list-timers --all project-forge-portfolio-sync.timer --no-pager
