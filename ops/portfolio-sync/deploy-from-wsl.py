#!/usr/bin/env python3
"""Deploy/operate the standalone Project Forge Portfolio systemd service from WSL2.

Uses the existing Deployment Kit strict target profile; neither the caller's
GitHub token nor an SSH private key is sent to Production. No FMP or npm writes.
"""
from __future__ import annotations

import argparse
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
USERNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}\Z")
REMOTE_DIR_RE = re.compile(r"/tmp/pf-portfolio-sync\.[A-Za-z0-9]{6,32}\Z")
INTERVAL_RE = re.compile(r"([1-9][0-9]*)([smhd])\Z")
SERVICE = "project-forge-portfolio-sync"
BUNDLE_FILES = (
    "README.md", "config.json", "sync.py", "install.sh", "set-interval.sh",
    "authorize-and-enable.sh", "uninstall.sh",
    "systemd/project-forge-portfolio-sync.service",
    "systemd/project-forge-portfolio-sync.timer",
)


class DeploymentError(Exception):
    pass


def interval_valid(value: str) -> bool:
    match = INTERVAL_RE.fullmatch(value)
    if not match:
        return False
    unit_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return 300 <= int(match[1]) * unit_seconds[match[2]] <= 86400


def profile_load(target: str, base: Path | None = None) -> dict:
    if not TARGET_RE.fullmatch(target):
        raise DeploymentError("Invalid target name")
    root = base or Path.home() / ".project-forge" / "targets"
    path = root / f"{target}.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeploymentError(f"Cannot read configured Project Forge target: {path}") from exc
    if not isinstance(profile, dict) or profile.get("targetName") != target:
        raise DeploymentError("Target name mismatch; refusing SSH")
    fields = ("hostName", "sshAlias", "user", "identityFile", "knownHostsFile")
    if any(not isinstance(profile.get(f), str) or not profile[f] for f in fields):
        raise DeploymentError("Incomplete Project Forge SSH profile")
    if not USERNAME_RE.fullmatch(profile["user"]):
        raise DeploymentError("Unexpected remote username")
    # Host aliases and DNS are only routing input; SSH identity remains host-key pinned.
    for field in ("hostName", "sshAlias"):
        if any(x in profile[field] for x in "\x00\r\n ") or profile[field].startswith("-"):
            raise DeploymentError(f"Unsafe SSH {field}")
    port = profile.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise DeploymentError("Invalid SSH port in target profile")
    override = profile.get("addressOverride")
    if override:
        try:
            ipaddress.ip_address(override)
        except ValueError as exc:
            raise DeploymentError("Target address override is not a valid verified IP") from exc
    for field in ("identityFile", "knownHostsFile"):
        val = Path(profile[field]).expanduser()
        if not val.is_absolute() or not val.is_file():
            raise DeploymentError(f"Missing trusted SSH material: {field} ({val})")
        profile[field] = str(val)
    return profile


def command_options(profile: dict) -> list[str]:
    """Mirror Deployment Kit's pinned target SSH transport, not global ssh config."""
    return [
        "-F", "none", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no",
        "-o", "CheckHostIP=no", "-o", "VerifyHostKeyDNS=no",
        "-o", "GlobalKnownHostsFile=none",
        "-o", f"UserKnownHostsFile={profile['knownHostsFile']}",
        "-o", f"HostKeyAlias={profile['sshAlias']}",
        "-o", "ForwardAgent=no", "-o", "ForwardX11=no",
        "-o", "ClearAllForwardings=yes",
        "-o", f"IdentityFile={profile['identityFile']}",
        "-o", "IdentitiesOnly=yes", "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "PreferredAuthentications=publickey",
        "-p", str(profile['port'])
    ]


def ssh_args(profile: dict, remote_command: str, *, interactive=False) -> list[str]:
    addr = profile.get("addressOverride") or profile["hostName"]
    return ["ssh", *command_options(profile), "-tt" if interactive else "-T",
            f"{profile['user']}@{addr}", remote_command]


def run_remote(profile: dict, command: str, *, stdin: bytes | None = None,
               interactive: bool = False, capture: bool = False) -> str:
    args = ssh_args(profile, command, interactive=interactive)
    try:
        result = subprocess.run(args, input=stdin, capture_output=capture,
                                timeout=600 if interactive else 180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError(f"Remote SSH operation could not complete: {type(exc).__name__}") from exc
    if result.returncode:
        raise DeploymentError(f"Remote command failed (exit {result.returncode}). See output above.")
    return result.stdout.decode("utf-8", errors="replace").strip() if capture else ""


def make_archive(src: Path = HERE) -> bytes:
    """Build a fresh archive from reviewed source only, no .git or credentials."""
    with io.BytesIO() as output:
        with tarfile.open(fileobj=output, mode="w:gz") as tar:
            for name in BUNDLE_FILES:
                file = src / name
                if not file.is_file() or file.is_symlink():
                    raise DeploymentError(f"Missing or unsafe bundle source: {name}")
                tar.add(file, arcname=f"project-forge-portfolio-sync/{name}", recursive=False)
        return output.getvalue()


def check_tools(profile: dict) -> None:
    # Verified SSH target, noninteractive sudo; install only a missing Ubuntu gh package.
    preflight = (
        "set -eu; "
        "test \"$(uname -s)\" = Linux; "
        "command -v sudo; command -v systemctl; command -v python3; "
        "command -v tar; command -v mktemp; "
        "sudo -n true; test -d /run/systemd/system; "
        "if ! command -v gh >/dev/null 2>&1; then "
        "  . /etc/os-release; test \"${ID:-}\" = ubuntu; "
        "  command -v apt-get; "
        "  printf 'Installing missing GitHub CLI from Ubuntu apt...\\n'; "
        "  sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq; "
        "  sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends gh; "
        "fi; command -v gh; "
        "printf 'PASS: remote host verified; sudo, gh, python3, systemd ready\\n'"
    )
    run_remote(profile, preflight)


def install(profile: dict, interval: str) -> None:
    if not interval_valid(interval):
        raise DeploymentError("Interval must be between 5m and 24h, e.g. 15m or 1h")
    print("Verifying pinned Project Forge SSH target and Production prerequisites...", flush=True)
    check_tools(profile)
    remote_dir = run_remote(profile, "mktemp -d /tmp/pf-portfolio-sync.XXXXXXXX", capture=True)
    if not REMOTE_DIR_RE.fullmatch(remote_dir):
        raise DeploymentError("Unexpected remote temporary path; aborting without data transfer")
    archive = make_archive()
    print(f"Transferring {len(archive)} bytes of service source over verified SSH...", flush=True)
    extract = f"tar -xz -C {shlex.quote(remote_dir)} -f -"
    try:
        run_remote(profile, extract, stdin=archive)
        print("Installing isolated systemd units (no FMP changes)...", flush=True)
        run_remote(profile, "sudo -n bash " +
                   shlex.quote(remote_dir + "/project-forge-portfolio-sync/install.sh") +
                   " --interval " + shlex.quote(interval))
        print("Authorizing dedicated GitHub service identity if needed; complete device flow in browser...", flush=True)
        run_remote(profile, "sudo -n bash /usr/local/libexec/project-forge-portfolio-sync/authorize-and-enable.sh",
                   interactive=True)
        print("Verifying active timer and the latest successful synchronization...", flush=True)
        run_remote(profile,
                   "set -eu; sudo -n systemctl is-active --quiet " + SERVICE + ".timer; "
                   "sudo -n systemctl show " + SERVICE + ".service -p Result --value | grep -Fx success; "
                   "sudo -n systemctl list-timers --all " + SERVICE + ".timer --no-pager; "
                   "sudo -n journalctl -u " + SERVICE + ".service -n 8 --no-pager")
        print("PASS: Production portfolio sync installed, timer active, initial run verified.", flush=True)
    finally:
        # Delete only our independently validated mktemp path, as the SSH user.
        try:
            run_remote(profile, "rm -rf -- " + shlex.quote(remote_dir))
        except DeploymentError:
            print("WARNING: Could not remove isolated temporary transfer directory", file=sys.stderr)


def status(profile: dict) -> None:
    run_remote(profile,
               "sudo -n systemctl status " + SERVICE + ".timer --no-pager; "
               "sudo -n systemctl list-timers --all " + SERVICE + ".timer --no-pager; "
               "sudo -n journalctl -u " + SERVICE + ".service -n 25 --no-pager")


def set_interval(profile: dict, interval: str) -> None:
    if not interval_valid(interval):
        raise DeploymentError("Invalid interval (5m to 24h)")
    run_remote(profile, "sudo -n bash /usr/local/libexec/project-forge-portfolio-sync/set-interval.sh " +
               shlex.quote(interval))


def uninstall(profile: dict) -> None:
    print("Removing ONLY the Portfolio sync timer and service, retaining credentials for revocation...", flush=True)
    run_remote(profile, "sudo -n bash /usr/local/libexec/project-forge-portfolio-sync/uninstall.sh")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Manage Portfolio sync on verified Project Forge Ubuntu target")
    ap.add_argument("--target", default="production", help="Existing ~/.project-forge/targets/<target>.json")
    ap.add_argument("--action", choices=("install", "status", "set-interval", "uninstall"), default="install")
    ap.add_argument("--interval", default="15m", help="Timer interval (5m to 24h)")
    args = ap.parse_args(argv)
    try:
        profile = profile_load(args.target)
        if args.action == "install":
            install(profile, args.interval)
        elif args.action == "status":
            status(profile)
        elif args.action == "set-interval":
            set_interval(profile, args.interval)
        else:
            uninstall(profile)
    except DeploymentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
