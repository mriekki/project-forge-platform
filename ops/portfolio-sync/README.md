# Project Forge Portfolio Sync — Production Linux

**Purpose:** Mirror *open* GitHub Issues from seven `mriekki` repositories into the existing private [Project Forge Portfolio](https://github.com/users/mriekki/projects/1). No custom dashboard, database, GitHub Actions workflow, or npm package change.

**Status:** source/tests/systemd units validated locally; installation and GitHub authorization on the Production host must be performed by the operator. The package does **not** claim Production is already running.

## Behavior / boundaries

- Uses a dedicated Linux system user `pf-portfolio-sync`, separate from FMP containers, the Feedback GitHub App, system-level SSH agent, and operator's WSL GitHub credentials.
- Does not change GitHub Issues, titles, labels, Project Status/Priority, relationships, or any fields. Only calls `gh project item-add` for missing original Issue URLs.
- Verifies the authenticated user is `mriekki`, the exact Project URL/title/number, privacy `public == false`, and all seven linked repositories *before* attempting any write.
- Reads all existing Project items before finding new ones, and fetches all seven Issue lists before mutating the Project. Fails closed on API, auth, invalid JSON, unexpected URL, or pagination problems; retries on next run, with no destructive rollback.
- Excludes Issues with `[project-forge-release]` / `[project-forge-publish]` title prefixes, while retaining ordinary release-qualification work.
- Uses `systemd` **system** timer (not a per-login user timer), with default `OnUnitInactiveSec=15m` and initial `OnBootSec=2min`. It runs while the Production host is running, even if WSL is off. Configurable 5m–24h.
- Logs brief structured counts to journald; no Issue bodies, tokens, or private payload content in normal logs.

## Requirements

Ubuntu/Linux with systemd, `python3`, `gh` GitHub CLI, `runuser`, `useradd`, and root `sudo` for installation. The Production host must reach `github.com`/`api.github.com` over HTTPS. `gh` should be installed before running the installer. **Do not copy your WSL token or use FMP Feedback's GitHub App private key.**

The service account authorizes its **own** GitHub CLI OAuth session using the browser/device flow. Because the Project is user-owned and six repositories are private, this uses `repo,project,read:project` OAuth scopes. Note that the OAuth `repo` scope is broader than the read-only Issue access actually used. Credentials are stored in the dedicated account's private home, not in any repository, environment file, or application container. If you prefer a narrower GitHub App/fine-grained token in the future, qualify that token's **personal Projects v2** API permissions before switching.

## Preferred: one WSL2-to-Production command

This source is owned by `mriekki/project-forge-platform` under `ops/portfolio-sync/`, **outside the npm distribution**, and does not touch the active package-release branch. Use the separately configured Project Forge Deployment Kit target profile at `~/.project-forge/targets/production.json` in WSL2; do **not** type an IP or disable SSH host-key verification.

For a first-time WSL run, use the pinned operator launcher (downloadable from PR #296):

```bash
bash run-from-wsl.sh --target production --interval 15m
```

Or, from an isolated checkout of the Platform repository containing this directory:

```bash
python3 ops/portfolio-sync/deploy-from-wsl.py --target production --interval 15m
```

The command verifies the configured SSH identity and Production prerequisites, installs `gh` from Ubuntu's apt repositories *only if missing*, transfers this exact reviewed source over strict SSH to an isolated temporary directory, installs/updates the dedicated service, and opens a one-time GitHub device approval for the service account if needed. It then runs a dry-run, performs an initial sync, enables/verifies the timer, shows recent journal output, and cleans the temporary transfer. No copied WSL OAuth tokens, SSH keys, or FMP Feedback App secrets.

Subsequent operations from the same WSL checkout:

```bash
python3 ops/portfolio-sync/deploy-from-wsl.py --target production --action status
python3 ops/portfolio-sync/deploy-from-wsl.py --target production --action set-interval --interval 30m
python3 ops/portfolio-sync/deploy-from-wsl.py --target production --action uninstall
```

The WSL operator requires the already-approved, trusted Project Forge `production` target profile and its SSH agent key loaded, plus noninteractive `sudo` on the target. If any of those prerequisites fail, the helper stops and reports the blocker, rather than weakening trust or falling back to guessed connection parameters. A one-time GitHub browser/device approval is still required for the dedicated Production identity; this cannot safely be bypassed.

`--action uninstall` affects only these systemd units; it does not revoke credentials or delete Project items. The existing application deployment and npm release are separate.

## Alternative: manual installation on Production

Transfer `project-forge-portfolio-sync.tar.gz` to the Production Linux machine using your already configured and authorized SSH transport (or retrieve it from a trusted local transfer); do not put it under the FMP app-data directory.

On Production:

```bash
mkdir -p /tmp/project-forge-portfolio-sync
cd /tmp/project-forge-portfolio-sync
tar -xzf /tmp/project-forge-portfolio-sync.tar.gz
sudo bash project-forge-portfolio-sync/install.sh --interval 15m
sudo bash /usr/local/libexec/project-forge-portfolio-sync/authorize-and-enable.sh
```

The **second** command is a one-time GitHub device-authorization flow for the dedicated service account; approve it in your own browser. Installation will not enable the timer until identity, privacy, links and read-only dry-run checks pass. It then runs one real sync and enables the timer. Do not share the device code or resulting token in chat.

## Configure timer

```bash
sudo bash /usr/local/libexec/project-forge-portfolio-sync/set-interval.sh 30m
sudo systemctl list-timers --all project-forge-portfolio-sync.timer
```

Supported examples: `5m`, `15m`, `30m`, `1h`, `6h`, `1d` (between five minutes and 24 hours). Configured as a systemd timer override at `/etc/systemd/system/project-forge-portfolio-sync.timer.d/interval.conf`. The interval starts after the **previous run completes**. A boot trigger runs once two minutes after boot. It is not an exact wall-clock schedule and does not replay intervals missed during downtime.

## Verify, manual run, debug

```bash
sudo systemctl status project-forge-portfolio-sync.timer --no-pager
sudo systemctl start project-forge-portfolio-sync.service
sudo journalctl -u project-forge-portfolio-sync.service -n 50 --no-pager
sudo systemctl list-timers --all project-forge-portfolio-sync.timer
```

Expected first run: `{"repositories_checked":7, "open_candidates":..., "added":...}`. On subsequent runs, typically `"added":0`.

To run a read-only check under the service identity:

```bash
sudo runuser -u pf-portfolio-sync -- env -u GH_TOKEN -u GITHUB_TOKEN \
  HOME=/var/lib/project-forge-portfolio-sync \
  GH_CONFIG_DIR=/var/lib/project-forge-portfolio-sync/.config/gh \
  /usr/bin/python3 /usr/local/libexec/project-forge-portfolio-sync/sync.py --dry-run
```

To inspect the config (nonsecret) and change repository selection, see `/etc/project-forge-portfolio-sync/config.json`. Changing the Issue scope requires manually editing this root-owned file and verifying links. **Do not** change the Project identity/visibility to work around an authentication error.

## Rollback

```bash
sudo bash project-forge-portfolio-sync/uninstall.sh
```

The rollback removes **only** this service and timer units. It intentionally does not delete Project items, close Issues, change app containers, remove the service account, or revoke its OAuth token. To fully retire the service, revoke its GitHub CLI authorization in GitHub account settings, and securely remove `/var/lib/project-forge-portfolio-sync` after verifying no other work uses it.

## Tests (on any developer Linux environment)

```bash
python3 -m unittest discover -s project-forge-portfolio-sync/tests -v
for script in project-forge-portfolio-sync/*.sh; do bash -n "$script"; done
systemd-analyze verify project-forge-portfolio-sync/systemd/*.service project-forge-portfolio-sync/systemd/*.timer
```

**GitHub API cost:** No per-request fee for ordinary API use. The default 15-minute polling is typically ~8-10 GitHub reads per sync (~32-40/hour), plus writes only for new Issues, well below typical authenticated limits of ~5,000 requests or GraphQL points per hour. GitHub can also enforce secondary limits. There is no GitHub Actions runner usage; the host's existing power/network overhead is negligible. This is an estimate, not a measured live quota.